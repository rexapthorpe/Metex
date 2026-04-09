"""
Checkout Routes

Checkout routes: checkout page, order confirmation.

Spot pricing at checkout:
  All spot price lookups during checkout go through
  services.checkout_spot_service.get_spot_map_for_checkout(), which reads from
  the spot_price_snapshots time-series table and triggers at most ONE external
  refresh if the data is stale.  Direct calls to get_current_spot_prices() or
  the external spot API are NOT made during checkout.
"""

import secrets

import stripe
from flask import render_template, redirect, url_for, request, session, flash, jsonify
from database import get_db_connection
from services.order_service import create_order
from utils.cart_utils import build_cart_summary
from services.notification_service import notify_listing_sold, notify_order_confirmed
from services.pricing_service import get_effective_price, create_price_lock
from services.checkout_spot_service import SpotUnavailableError, SpotExpiredError
from utils.auth_utils import frozen_check
from config import STRIPE_PUBLISHABLE_KEY

from . import checkout_bp

# ---------------------------------------------------------------------------
# Fee constants
# ---------------------------------------------------------------------------
#
# CARD_RATE / CARD_FLAT are Stripe's pass-through card processing fee components.
# The buyer card fee is applied to the TAXED subtotal (subtotal + tax), not the
# raw subtotal, because that is the actual amount being processed by Stripe.
#
# Tax is no longer computed with a fixed rate. Sales tax is determined by
# calling the Stripe Tax API (stripe.tax.Calculation) with the buyer's address
# and the order subtotal. The resulting tax_amount is stored on the order and
# used in all downstream calculations. This makes Stripe the single source of
# truth for tax — no manual rates in Python or JavaScript.
#
CARD_RATE = 0.0299   # 2.99%
CARD_FLAT = 0.30     # $0.30 fixed per transaction
FALLBACK_TAX_RATE = 0.0825  # Used when Stripe Tax API is unavailable

# Map common full country names → ISO 3166-1 alpha-2 codes accepted by Stripe Tax.
_COUNTRY_NAME_TO_CODE = {
    'united states': 'US',
    'united states of america': 'US',
    'canada': 'CA',
    'united kingdom': 'GB',
    'great britain': 'GB',
    'australia': 'AU',
    'germany': 'DE',
    'france': 'FR',
    'japan': 'JP',
}


def _normalize_country(country: str) -> str:
    """Convert full country name to ISO code if needed, e.g. 'United States' → 'US'."""
    if not country:
        return 'US'
    stripped = country.strip()
    if len(stripped) == 2:
        return stripped.upper()
    return _COUNTRY_NAME_TO_CODE.get(stripped.lower(), stripped[:2].upper())


def _get_stripe_tax(subtotal_cents: int, postal_code: str,
                    state: str = '', country: str = 'US'):
    """
    Call the Stripe Tax Calculation API to determine sales tax.

    Args:
        subtotal_cents: Taxable amount in cents (item subtotal only, no fees).
        postal_code:    Buyer's postal/ZIP code (required for tax lookup).
        state:          Buyer's state abbreviation, e.g. 'CA'.
        country:        Buyer's country code or full name (normalized internally).

    Returns:
        (tax_cents: int, calculation_id: str | None)
        Returns (0, None) when address is incomplete.
        Returns (fallback_cents, 'fallback_rate') when Stripe Tax is unavailable
        but an address was provided — so the UI can show an estimate.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)
    if not postal_code or subtotal_cents <= 0:
        return 0, None

    country_code = _normalize_country(country)

    try:
        calc = stripe.tax.Calculation.create(
            currency='usd',
            line_items=[{
                'amount': subtotal_cents,
                'reference': 'order_subtotal',
            }],
            customer_details={
                'address': {
                    'postal_code': str(postal_code).strip(),
                    'state': str(state).strip() if state else '',
                    'country': country_code,
                },
                'address_source': 'shipping',
            },
        )
        _log.info('[Tax] Stripe calc %s subtotal=%d tax=%d',
                  calc.id, subtotal_cents, calc.tax_amount_exclusive)
        return int(calc.tax_amount_exclusive), calc.id
    except Exception as exc:
        _log.warning('[Tax] Stripe Tax unavailable — using fallback rate %.2f%%: %s',
                     FALLBACK_TAX_RATE * 100, exc)
        fallback_cents = round(subtotal_cents * FALLBACK_TAX_RATE)
        return fallback_cents, 'fallback_rate'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_weight_oz(weight_str):
    """
    Parse a display weight string (e.g. '1 oz', '1/4 oz', '10 g') to a float
    suitable for insertion into the REAL column weight_used.

    Returns float or None if the string is absent or unparseable.
    """
    if not weight_str:
        return None
    import re
    s = str(weight_str).strip()
    # Match optional fraction or decimal followed by optional unit
    m = re.match(r'^(\d+)\s*/\s*(\d+)|^(\d+(?:\.\d+)?)', s)
    if not m:
        return None
    if m.group(1) and m.group(2):          # fraction: "1/4 oz"
        return float(m.group(1)) / float(m.group(2))
    return float(m.group(3))               # integer or decimal: "1 oz", "2.5 g"

def _create_ledger_for_order(buyer_id, order_id, cart_data, conn):
    """
    Create ledger records for an order.
    This is a minimal integration point that builds a cart_snapshot from cart_data
    and calls the ledger service.

    Args:
        buyer_id: The buyer's user ID
        order_id: The created order ID
        cart_data: List of dicts with listing_id, quantity, price_each
        conn: Database connection for fetching seller_ids
    """
    try:
        from services.ledger_service import LedgerService

        # Build cart_snapshot with seller_ids
        cart_snapshot = []
        for item in cart_data:
            # Get seller_id from the listing
            listing = conn.execute(
                'SELECT seller_id FROM listings WHERE id = ?',
                (item['listing_id'],)
            ).fetchone()

            if listing:
                cart_snapshot.append({
                    'seller_id': listing['seller_id'],
                    'listing_id': item['listing_id'],
                    'quantity': item['quantity'],
                    'unit_price': item['price_each']
                    # fee_type and fee_value will use defaults from ledger service
                })

        if cart_snapshot:
            ledger_id = LedgerService.create_order_ledger_from_cart(
                buyer_id=buyer_id,
                cart_snapshot=cart_snapshot,
                payment_method=None,  # Stripe not integrated yet
                order_id=order_id
            )
            print(f"[CHECKOUT] Created ledger record {ledger_id} for order {order_id}")
            return ledger_id
    except Exception as e:
        # Don't fail checkout if ledger creation fails - log and continue
        print(f"[CHECKOUT] Warning: Failed to create ledger for order {order_id}: {e}")
        import traceback
        traceback.print_exc()
    return None


def _fetch_listing_pricing_meta(conn, listing_ids):
    """
    Return {listing_id: {pricing_mode, spot_premium, pricing_metal, metal, weight}}
    for the given listing IDs. Used to populate order_items audit columns.
    """
    if not listing_ids:
        return {}
    placeholders = ','.join('?' * len(listing_ids))
    rows = conn.execute(
        f"SELECT l.id, l.pricing_mode, l.spot_premium, l.pricing_metal, "
        f"       l.price_per_coin, l.floor_price, "
        f"       c.metal, c.weight "
        f"FROM listings l JOIN categories c ON l.category_id = c.id "
        f"WHERE l.id IN ({placeholders})",
        listing_ids,
    ).fetchall()
    return {row['id']: dict(row) for row in rows}


def _enrich_cart_data_with_spot_audit(cart_data, spot_map, listing_meta):
    """
    Add spot audit fields to each item in cart_data in-place.

    Args:
        cart_data:    list of cart item dicts (mutated in-place)
        spot_map:     {metal_lower: spot_info_dict | None}
        listing_meta: {listing_id: pricing metadata dict}
    """
    for item in cart_data:
        meta = listing_meta.get(item['listing_id'], {})
        item['pricing_mode_used'] = meta.get('pricing_mode')
        item['spot_premium_used'] = meta.get('spot_premium')
        item['weight_used'] = _parse_weight_oz(meta.get('weight'))

        if meta.get('pricing_mode') == 'premium_to_spot':
            metal = (meta.get('pricing_metal') or meta.get('metal') or '').lower()
            item['spot_info'] = spot_map.get(metal)
        else:
            item['spot_info'] = None


def _get_cart_metals_for_spot(conn, user_id):
    """
    Return set of lower-case metal names needed for premium_to_spot listings
    in the user's cart.  Used to pre-fetch spot prices before pricing.
    """
    rows = conn.execute(
        "SELECT DISTINCT COALESCE(l.pricing_metal, c.metal) AS m "
        "FROM cart ct "
        "JOIN listings l ON ct.listing_id = l.id "
        "JOIN categories c ON l.category_id = c.id "
        "WHERE ct.user_id = ? AND l.pricing_mode = 'premium_to_spot'",
        (user_id,),
    ).fetchall()
    return {row['m'].lower() for row in rows if row['m']}


def _build_spot_prices_dict(spot_map):
    """
    Convert spot_map ({metal: spot_info | None}) to a plain {metal: price_usd}
    dict suitable for passing to get_effective_price() / build_cart_summary().
    """
    return {m: info['price_usd'] for m, info in spot_map.items() if info}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@checkout_bp.route('/checkout', methods=['GET', 'POST'])
@frozen_check
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    conn = get_db_connection()

    if request.method == 'POST':
        # Check for bucket purchase first (before AJAX cart checkout)
        bucket_id = request.form.get('bucket_id')
        quantity = int(request.form.get('quantity') or 1)  # Handle empty string

        if bucket_id:
            # User is buying directly from a bucket (not from cart)
            bucket_id = int(bucket_id)
            random_year = request.form.get('random_year') == '1'

            # Initialize user_listings_skipped early (before any potential early returns)
            user_listings_skipped = False

            # Get bucket_ids to query based on Random Year mode
            if random_year:
                # Get the base bucket info
                bucket = conn.execute('SELECT * FROM categories WHERE bucket_id = ? LIMIT 1', (bucket_id,)).fetchone()

                if not bucket:
                    flash("Item not found.", "error")
                    conn.close()
                    return redirect(url_for('buy.buy'))

                # Find all matching buckets (same specs except year)
                matching_buckets_query = '''
                    SELECT bucket_id FROM categories
                    WHERE metal = ? AND product_type = ? AND weight = ? AND purity = ?
                      AND mint = ? AND finish = ? AND grade = ? AND product_line = ?
                      AND condition_category IS NOT DISTINCT FROM ?
                      AND series_variant IS NOT DISTINCT FROM ?
                      AND is_isolated = 0
                '''
                matching_buckets = conn.execute(matching_buckets_query, (
                    bucket['metal'], bucket['product_type'], bucket['weight'], bucket['purity'],
                    bucket['mint'], bucket['finish'], bucket['grade'], bucket['product_line'],
                    bucket['condition_category'], bucket['series_variant']
                )).fetchall()

                bucket_ids = [row['bucket_id'] for row in matching_buckets] if matching_buckets else [bucket_id]
                bucket_id_clause = f"c.bucket_id IN ({','.join('?' * len(bucket_ids))})"
                params = bucket_ids.copy()
            else:
                bucket_ids = [bucket_id]
                bucket_id_clause = "c.bucket_id = ?"
                params = [bucket_id]

            # Get listings with pricing fields for effective price calculation
            # IMPORTANT: Include ALL listings (including user's own) to detect when they're skipped
            query = f'''
                SELECT l.id, l.quantity, l.price_per_coin, l.pricing_mode,
                       l.spot_premium, l.floor_price, l.pricing_metal, l.seller_id,
                       c.metal, c.weight, c.product_type, c.year
                FROM listings l
                JOIN categories c ON l.category_id = c.id
                WHERE {bucket_id_clause} AND l.active = 1 AND l.quantity > 0
            '''

            listings_raw = conn.execute(query, params).fetchall()

            # ── Checkout spot pricing (bounded staleness, single-flight refresh) ──
            # Collect metals needed for premium_to_spot listings; fetch once.
            from services.checkout_spot_service import get_spot_map_for_checkout
            bucket_metals = set()
            for listing in listings_raw:
                if listing['pricing_mode'] == 'premium_to_spot':
                    m = (listing['pricing_metal'] or listing['metal'] or '').lower()
                    if m:
                        bucket_metals.add(m)

            # Policy A: block checkout if live pricing cannot be refreshed within SLA.
            try:
                spot_map = get_spot_map_for_checkout(bucket_metals) if bucket_metals else {}
            except SpotUnavailableError:
                conn.close()
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': False,
                        'error_code': 'SPOT_UNAVAILABLE',
                        'message': SpotUnavailableError.USER_MESSAGE,
                    }), 503
                flash(SpotUnavailableError.USER_MESSAGE, 'error')
                return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

            spot_prices_dict = _build_spot_prices_dict(spot_map)

            # Calculate effective prices using checkout-validated spot prices
            listings_with_prices = []
            for listing in listings_raw:
                listing_dict = dict(listing)
                listing_dict['effective_price'] = get_effective_price(listing_dict, spot_prices=spot_prices_dict)
                listings_with_prices.append(listing_dict)

            # Sort by effective price (cheapest first)
            listings_sorted = sorted(listings_with_prices, key=lambda x: x['effective_price'])

            # Separate user's listings from others
            user_listings = []
            other_listings = []

            for listing in listings_sorted:
                if listing['seller_id'] == user_id:
                    user_listings.append(listing)
                else:
                    other_listings.append(listing)

            # Try to fill from other sellers' listings only (skip user's own listings)
            selected = []
            selected_prices = []
            remaining = quantity

            for listing in other_listings:
                if remaining <= 0:
                    break
                take = min(listing['quantity'], remaining)
                # Determine spot audit info for this listing
                if listing['pricing_mode'] == 'premium_to_spot':
                    metal = (listing.get('pricing_metal') or listing.get('metal') or '').lower()
                    spot_info = spot_map.get(metal)
                else:
                    spot_info = None

                selected.append({
                    'listing_id': listing['id'],
                    'quantity': take,
                    'price_each': listing['effective_price'],
                    'spot_info': spot_info,
                    'pricing_mode_used': listing.get('pricing_mode'),
                    'spot_premium_used': listing.get('spot_premium'),
                    'weight_used': _parse_weight_oz(listing.get('weight')),
                })
                selected_prices.append(listing['effective_price'])
                remaining -= take

            # Check if we skipped any competitive user listings
            if user_listings and selected_prices and len(selected) > 0:
                # If any user listing price is <= the highest price we selected, it was competitive
                max_selected_price = max(selected_prices)
                for user_listing in user_listings:
                    if user_listing['effective_price'] <= max_selected_price:
                        user_listings_skipped = True
                        print(f"[CHECKOUT] User listing at ${user_listing['effective_price']:.2f} was skipped")
                        break

            if remaining > 0:
                flash("Not enough inventory to fulfill your request.")
                conn.close()
                return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

            # Check if this is an AJAX request (from Buy Item button)
            is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

            # Phase 0A: grading deactivated — always treat as non-grading.
            buy_tpg_int = 0

            if is_ajax:
                # Return JSON for AJAX requests (so modal can be shown before redirect)
                print(f"[CHECKOUT] AJAX request. user_listings_skipped={user_listings_skipped}, items_selected={len(selected)}")
                # Store selection in session for when user is redirected
                # Note: spot audit fields are NOT stored in session (not serializable);
                # they will be re-derived from the DB at final POST time.
                session['checkout_items'] = [
                    {'listing_id': s['listing_id'], 'quantity': s['quantity'], 'price_each': s['price_each']}
                    for s in selected
                ]
                session['checkout_tpg'] = buy_tpg_int
                conn.close()
                return jsonify({
                    'success': True,
                    'user_listings_skipped': user_listings_skipped and len(selected) > 0,
                    'items_selected': len(selected),
                    'message': f'{len(selected)} item(s) selected for checkout'
                })
            else:
                # Traditional redirect for non-AJAX requests (backward compatibility)
                if user_listings_skipped and len(selected) > 0:
                    session['show_own_listings_skipped_modal'] = True
                    print(f"[CHECKOUT] User listings were skipped. Setting session flag. User ID: {user_id}")

                # Keep the selection in session for the GET render and final POST
                session['checkout_items'] = [
                    {'listing_id': s['listing_id'], 'quantity': s['quantity'], 'price_each': s['price_each']}
                    for s in selected
                ]
                session['checkout_tpg'] = buy_tpg_int
                conn.close()
                return redirect(url_for('checkout.checkout'))

        else:
            # Not a bucket purchase - handle cart checkout (or bucket finalize via AJAX)
            is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

            if is_ajax:
                # ── Unified AJAX finalize handler ──────────────────────────────
                # Handles both bucket finalize (session_items present) and cart
                # checkout.  Uses modal-first spot check: raises SPOT_EXPIRED if
                # stale instead of auto-refreshing, so the frontend can prompt the
                # user to recalculate before proceeding.
                try:
                    data = request.get_json() or {}
                    shipping_address = data.get('shipping_address', 'Default Address')
                    recipient_first = data.get('recipient_first', '')
                    recipient_last = data.get('recipient_last', '')
                    payment_intent_id = data.get('payment_intent_id', '')
                    # 'card' is the default; frontend sends _stripeSelectedMethod
                    payment_method_type = data.get('payment_method_type', 'card')

                    # ── Idempotency guard: validate one-time checkout nonce ─────
                    # Prevents duplicate orders from double-submit or simultaneous
                    # requests. The nonce is generated on GET and validated here.
                    # It is NOT consumed yet — it is consumed only at the point of
                    # order creation so that earlier failures (SPOT_EXPIRED, etc.)
                    # leave the nonce intact for the user to retry.
                    submitted_nonce = data.get('checkout_nonce')
                    if not submitted_nonce or submitted_nonce != session.get('checkout_nonce'):
                        conn.close()
                        return jsonify({
                            'success': False,
                            'message': 'Order already submitted or session expired. Please refresh the page.',
                        }), 409

                    from services.checkout_spot_service import check_spot_map_freshness

                    session_items = session.pop('checkout_items', None)
                    # Phase 0A: discard any stale tpg session value.
                    session.pop('checkout_tpg', None)
                    buy_tpg = False

                    if session_items:
                        # ── Bucket finalize: use locked prices from session ──
                        cart_data = [
                            {
                                'listing_id': i['listing_id'],
                                'quantity': i['quantity'],
                                'price_each': i['price_each'],
                                'requires_grading': False,  # Phase 0A: grading deactivated
                            }
                            for i in session_items
                        ]

                        # Check that spot used when prices were locked is still fresh.
                        # No auto-refresh — stale → SPOT_EXPIRED so frontend shows modal.
                        listing_ids_si = [i['listing_id'] for i in cart_data]
                        listing_meta_si = _fetch_listing_pricing_meta(conn, listing_ids_si)
                        si_metals = {
                            (m.get('pricing_metal') or m.get('metal') or '').lower()
                            for m in listing_meta_si.values()
                            if m.get('pricing_mode') == 'premium_to_spot'
                        }
                        try:
                            spot_map = check_spot_map_freshness(si_metals) if si_metals else {}
                        except SpotExpiredError:
                            # Restore session so recalculate endpoint can find items
                            session['checkout_items'] = session_items
                            session['checkout_tpg'] = 0  # Phase 0A: always 0
                            conn.close()
                            return jsonify({
                                'success': False,
                                'error_code': 'SPOT_EXPIRED',
                                'message': SpotExpiredError.USER_MESSAGE,
                            }), 409
                        except SpotUnavailableError:
                            session['checkout_items'] = session_items
                            session['checkout_tpg'] = 0  # Phase 0A: always 0
                            conn.close()
                            return jsonify({
                                'success': False,
                                'error_code': 'SPOT_UNAVAILABLE',
                                'message': SpotUnavailableError.USER_MESSAGE,
                            }), 503

                        _enrich_cart_data_with_spot_audit(cart_data, spot_map, listing_meta_si)

                    else:
                        # ── Cart checkout: build fresh cart summary ──
                        cart_metals = _get_cart_metals_for_spot(conn, user_id)
                        try:
                            spot_map = check_spot_map_freshness(cart_metals) if cart_metals else {}
                        except SpotExpiredError:
                            conn.close()
                            return jsonify({
                                'success': False,
                                'error_code': 'SPOT_EXPIRED',
                                'message': SpotExpiredError.USER_MESSAGE,
                            }), 409
                        except SpotUnavailableError:
                            conn.close()
                            return jsonify({
                                'success': False,
                                'error_code': 'SPOT_UNAVAILABLE',
                                'message': SpotUnavailableError.USER_MESSAGE,
                            }), 503

                        spot_prices_dict = _build_spot_prices_dict(spot_map)
                        summary = build_cart_summary(conn, user_id, spot_prices=spot_prices_dict)

                        if not summary['buckets']:
                            conn.close()
                            return jsonify({
                                'success': False,
                                'message': 'Your cart is empty or items are no longer available',
                            })

                        cart_data = [
                            {
                                'listing_id': listing['listing_id'],
                                'quantity': listing['quantity'],
                                'price_each': listing['effective_price'],
                                'requires_grading': listing['requires_grading'],
                            }
                            for bucket in summary['buckets'].values()
                            for listing in bucket['listings']
                        ]
                        listing_ids = [item['listing_id'] for item in cart_data]
                        listing_meta = _fetch_listing_pricing_meta(conn, listing_ids)
                        _enrich_cart_data_with_spot_audit(cart_data, spot_map, listing_meta)

                    if not cart_data:
                        conn.close()
                        return jsonify({
                            'success': False,
                            'message': 'Your cart is empty or items are no longer available',
                        })

                    # ── Tax (Stripe) → buyer card fee → total ──────────────────
                    #
                    # 1. Subtotal   = sum of item line totals (no fees).
                    # 2. Tax        = stripe.tax.Calculation on subtotal with buyer address.
                    #                 Stripe is the single source of truth for tax amount.
                    # 3. Card fee   = round((subtotal + tax) × CARD_RATE + CARD_FLAT, 2)
                    #                 Fee is on the taxed subtotal because that is the actual
                    #                 amount Stripe will process.  ACH = $0.00.
                    # 4. Total      = subtotal + tax + card_fee  (= Stripe charge amount)
                    #
                    # The PaymentIntent is updated with the final total so what Stripe
                    # charges, what we store, and what the buyer sees all match exactly.
                    _items_subtotal = round(
                        sum(item['price_each'] * item['quantity'] for item in cart_data), 2
                    )
                    # ── Stripe Tax: look up address components from JSON body ──
                    _tax_postal  = data.get('zip_code', '') or data.get('postal_code', '')
                    _tax_state   = data.get('state', '')
                    _tax_country = data.get('country', 'US') or 'US'
                    _tax_cents, _tax_calc_id = _get_stripe_tax(
                        int(round(_items_subtotal * 100)),
                        _tax_postal, _tax_state, _tax_country,
                    )
                    _tax_amount = round(_tax_cents / 100, 2)
                    _taxed_subtotal = _items_subtotal + _tax_amount

                    if payment_method_type == 'us_bank_account':
                        buyer_card_fee = 0.0
                    else:
                        buyer_card_fee = round(_taxed_subtotal * CARD_RATE + CARD_FLAT, 2)

                    _charged_total = _taxed_subtotal + buyer_card_fee
                    _charged_total_cents = int(round(_charged_total * 100))

                    import logging as _co_logging
                    _co_log = _co_logging.getLogger(__name__)
                    _co_log.info(
                        '[CHECKOUT] subtotal=%.2f tax=%.2f card_fee=%.2f total=%.2f '
                        'pi_cents=%d pi_id=%s method=%s',
                        _items_subtotal, _tax_amount, buyer_card_fee, _charged_total,
                        _charged_total_cents, payment_intent_id or '(missing)',
                        payment_method_type,
                    )

                    # Update the PaymentIntent amount to the final taxed+fee total so
                    # what Stripe charges matches what we store.  Only called when a PI
                    # ID is present (the frontend always provides one in production; it
                    # may be absent in test environments where Stripe is mocked).
                    if payment_intent_id:
                        try:
                            stripe.PaymentIntent.modify(
                                payment_intent_id,
                                amount=_charged_total_cents,
                            )
                            _co_log.info('[CHECKOUT] PI %s amount set to %d cents (%.2f)',
                                         payment_intent_id, _charged_total_cents, _charged_total)
                        except stripe.error.StripeError as _pi_err:
                            conn.close()
                            return jsonify({
                                'success': False,
                                'message': f'Payment setup error: {str(_pi_err)}',
                            }), 500

                    # ── Consume nonce immediately before order creation ──────────
                    # All validation has passed; remove the nonce so any duplicate
                    # request that reaches this point is rejected as "already submitted".
                    session.pop('checkout_nonce', None)

                    # ── Create order ────────────────────────────────────────────
                    # Effective tax rate stored for display; Stripe is authoritative source.
                    _effective_tax_rate = round(_tax_amount / _items_subtotal, 6) if _items_subtotal else 0.0
                    order_id = create_order(
                        user_id, cart_data, shipping_address, recipient_first, recipient_last,
                        placed_from_ip=request.remote_addr,
                        payment_intent_id=payment_intent_id or None,
                        buyer_card_fee=buyer_card_fee,
                        tax_amount=_tax_amount,
                        tax_rate=_effective_tax_rate,
                    )
                    _create_ledger_for_order(user_id, order_id, cart_data, conn)

                    # Decrement inventory + collect notification data
                    total_items = 0
                    order_total = 0.0
                    notifications_to_send = []

                    for item in cart_data:
                        # Atomic decrement: only deducts if quantity >= purchase amount
                        # This prevents overselling under concurrent checkout (race condition fix)
                        result = conn.execute('''
                            UPDATE listings
                               SET quantity = quantity - ?,
                                   active = CASE WHEN quantity - ? <= 0 THEN 0 ELSE active END
                             WHERE id = ? AND quantity >= ? AND active = 1
                        ''', (item['quantity'], item['quantity'], item['listing_id'], item['quantity']))

                        if result.rowcount == 0:
                            # Concurrent buyer took the last stock.
                            # 1) Roll back all inventory decrements already applied in this
                            #    transaction (items processed before this one in the loop).
                            # 2) Clean up the order record that was committed by create_order()
                            #    in its own connection.
                            # 3) Clean up ledger records created by _create_ledger_for_order()
                            #    (committed in their own connection — not covered by rollback above).
                            conn.rollback()
                            try:
                                conn.execute('DELETE FROM order_items_ledger WHERE order_id = ?', (order_id,))
                                conn.execute('DELETE FROM order_payouts WHERE order_id = ?', (order_id,))
                                conn.execute('DELETE FROM order_events WHERE order_id = ?', (order_id,))
                                conn.execute('DELETE FROM orders_ledger WHERE order_id = ?', (order_id,))
                                conn.execute('DELETE FROM order_items WHERE order_id = ?', (order_id,))
                                conn.execute('DELETE FROM orders WHERE id = ?', (order_id,))
                                conn.commit()
                            except Exception:
                                pass
                            conn.close()
                            return jsonify({
                                'success': False,
                                'message': 'One or more items are no longer available. Please refresh your cart.',
                            }), 409

                        listing_info = conn.execute('''
                            SELECT listings.quantity, listings.seller_id, listings.category_id,
                                   categories.metal, categories.product_type
                            FROM listings
                            JOIN categories ON listings.category_id = categories.id
                            WHERE listings.id = ?
                        ''', (item['listing_id'],)).fetchone()

                        if listing_info:
                            new_quantity = listing_info['quantity']
                            item_description = f"{listing_info['metal']} {listing_info['product_type']}"
                            is_partial = new_quantity > 0
                            notifications_to_send.append({
                                'seller_id': listing_info['seller_id'],
                                'order_id': order_id,
                                'listing_id': item['listing_id'],
                                'item_description': item_description,
                                'quantity_sold': item['quantity'],
                                'price_per_unit': item['price_each'],
                                'total_amount': item['quantity'] * item['price_each'],
                                'shipping_address': shipping_address,
                                'is_partial': is_partial,
                                'remaining_quantity': new_quantity if is_partial else 0,
                            })

                        total_items += item['quantity']
                        order_total += item['quantity'] * item['price_each']

                    conn.execute('DELETE FROM cart WHERE user_id = ?', (user_id,))

                    # Store the Stripe PaymentIntent ID on the order now so the
                    # webhook can find the order by PI ID (no separate round-trip needed).
                    if payment_intent_id:
                        conn.execute(
                            'UPDATE orders SET stripe_payment_intent_id = ? WHERE id = ?',
                            (payment_intent_id, order_id)
                        )

                    conn.commit()
                    conn.close()

                    # Send notifications after commit
                    for notif_data in notifications_to_send:
                        try:
                            notify_listing_sold(**notif_data)
                        except Exception as e:
                            print(f"[CHECKOUT] Failed to send seller notification: {e}")

                    try:
                        item_descriptions = [n['item_description'] for n in notifications_to_send]
                        buyer_item_description = (
                            item_descriptions[0] if len(set(item_descriptions)) == 1
                            else f"{len(set(item_descriptions))} different items"
                        )
                        notify_order_confirmed(
                            buyer_id=user_id,
                            order_id=order_id,
                            item_description=buyer_item_description,
                            quantity_purchased=total_items,
                            price_per_unit=order_total / total_items if total_items > 0 else 0,
                            total_amount=round(order_total + _tax_amount + buyer_card_fee, 2),
                        )
                    except Exception as e:
                        print(f"[CHECKOUT] Failed to send buyer notification: {e}")

                    return jsonify({
                        'success': True,
                        'order_id': order_id,
                        'total_items': total_items,
                        'order_total': round(order_total + _tax_amount + buyer_card_fee, 2),
                    })

                except Exception as e:
                    conn.close()
                    return jsonify({
                        'success': False,
                        'message': f'Error processing order: {str(e)}',
                    }), 500

            # Final submit: create the order from either session-selected items or the cart
            shipping_address = request.form.get('shipping_address')
            recipient_first = request.form.get('recipient_first_name', '')
            recipient_last = request.form.get('recipient_last_name', '')

            # Prefer direct-bucket selection if present
            session_items = session.pop('checkout_items', None)
            # checkout_tpg is the canonical boolean (0/1 int) stored by the bucket POST.
            buy_tpg = bool(session.pop('checkout_tpg', 0))
            if session_items:
                cart_data = [{
                    'listing_id': item['listing_id'],
                    'quantity': item['quantity'],
                    'price_each': item['price_each'],
                    'requires_grading': buy_tpg,
                } for item in session_items]
            else:
                # Fallback to the user's cart via the authoritative summary.
                # Pre-fetch checkout-validated spot prices first.
                from services.checkout_spot_service import check_spot_map_freshness
                cart_metals = _get_cart_metals_for_spot(conn, user_id)
                # Modal-first: if snapshot is stale, redirect to checkout with a
                # message so the user sees the recalculate prompt on reload.
                try:
                    spot_map_fb = check_spot_map_freshness(cart_metals) if cart_metals else {}
                except SpotExpiredError:
                    conn.close()
                    flash(SpotExpiredError.USER_MESSAGE, 'error')
                    return redirect(url_for('checkout.checkout'))
                except SpotUnavailableError:
                    conn.close()
                    flash(SpotUnavailableError.USER_MESSAGE, 'error')
                    return redirect(url_for('buy.view_cart'))
                spot_prices_fb = _build_spot_prices_dict(spot_map_fb)

                _summary = build_cart_summary(conn, user_id, spot_prices=spot_prices_fb)
                cart_data = [
                    {
                        'listing_id': listing['listing_id'],
                        'quantity': listing['quantity'],
                        'price_each': listing['effective_price'],
                        'requires_grading': listing['requires_grading'],
                    }
                    for bucket in _summary['buckets'].values()
                    for listing in bucket['listings']
                ]
                # Enrich with spot audit for cart fallback path
                listing_ids_fb = [item['listing_id'] for item in cart_data]
                listing_meta_fb = _fetch_listing_pricing_meta(conn, listing_ids_fb)
                _enrich_cart_data_with_spot_audit(cart_data, spot_map_fb, listing_meta_fb)

            if not cart_data:
                flash("Your cart is empty or items are no longer available.")
                conn.close()
                return redirect(url_for('buy.view_cart'))

            # For session-items path: enrich with spot audit info from current snapshots
            if session_items:
                from services.checkout_spot_service import check_spot_map_freshness
                listing_ids_si = [item['listing_id'] for item in cart_data]
                listing_meta_si = _fetch_listing_pricing_meta(conn, listing_ids_si)
                si_metals = {
                    (meta.get('pricing_metal') or meta.get('metal') or '').lower()
                    for meta in listing_meta_si.values()
                    if meta.get('pricing_mode') == 'premium_to_spot'
                }
                # Modal-first: stale snapshot → restore session + redirect to checkout
                try:
                    spot_map_si = check_spot_map_freshness(si_metals) if si_metals else {}
                except SpotExpiredError:
                    session['checkout_items'] = session_items
                    session['checkout_tpg'] = int(buy_tpg)
                    conn.close()
                    flash(SpotExpiredError.USER_MESSAGE, 'error')
                    return redirect(url_for('checkout.checkout'))
                except SpotUnavailableError:
                    conn.close()
                    flash(SpotUnavailableError.USER_MESSAGE, 'error')
                    return redirect(url_for('buy.view_cart'))
                _enrich_cart_data_with_spot_audit(cart_data, spot_map_si, listing_meta_si)

            # Create the order record (service inserts into orders & order_items)
            order_id = create_order(
                user_id, cart_data, shipping_address, recipient_first, recipient_last,
                placed_from_ip=request.remote_addr,
            )

            # Create ledger records for this order
            _create_ledger_for_order(user_id, order_id, cart_data, conn)

            # Decrement inventory atomically to prevent overselling (race condition fix)
            for item in cart_data:
                # Atomic decrement: only updates if sufficient quantity remains
                result = conn.execute('''
                    UPDATE listings
                       SET quantity = quantity - ?,
                           active = CASE WHEN quantity - ? <= 0 THEN 0 ELSE active END
                     WHERE id = ? AND quantity >= ? AND active = 1
                ''', (item['quantity'], item['quantity'], item['listing_id'], item['quantity']))

                if result.rowcount == 0:
                    # Concurrent buyer took the last stock.
                    # 1) Roll back all inventory decrements already applied in this
                    #    transaction (items processed before this one in the loop).
                    # 2) Clean up the order record committed by create_order().
                    # 3) Clean up ledger records created by _create_ledger_for_order()
                    #    (committed in their own connection — not covered by rollback above).
                    conn.rollback()
                    try:
                        conn.execute('DELETE FROM order_items_ledger WHERE order_id = ?', (order_id,))
                        conn.execute('DELETE FROM order_payouts WHERE order_id = ?', (order_id,))
                        conn.execute('DELETE FROM order_events WHERE order_id = ?', (order_id,))
                        conn.execute('DELETE FROM orders_ledger WHERE order_id = ?', (order_id,))
                        conn.execute('DELETE FROM order_items WHERE order_id = ?', (order_id,))
                        conn.execute('DELETE FROM orders WHERE id = ?', (order_id,))
                        conn.commit()
                    except Exception:
                        pass
                    conn.close()
                    flash('One or more items are no longer available. Please review your cart.', 'error')
                    return redirect(url_for('buy.view_cart'))

                listing_info = conn.execute('''
                    SELECT listings.quantity, listings.seller_id, listings.category_id,
                           categories.metal, categories.product_type
                    FROM listings
                    JOIN categories ON listings.category_id = categories.id
                    WHERE listings.id = ?
                ''', (item['listing_id'],)).fetchone()

                if listing_info:
                    new_quantity = listing_info['quantity']
                    # Send notification to seller
                    try:
                        item_description = f"{listing_info['metal']} {listing_info['product_type']}"
                        is_partial = new_quantity > 0

                        notify_listing_sold(
                            seller_id=listing_info['seller_id'],
                            order_id=order_id,
                            listing_id=item['listing_id'],
                            item_description=item_description,
                            quantity_sold=item['quantity'],
                            price_per_unit=item['price_each'],
                            total_amount=item['quantity'] * item['price_each'],
                            shipping_address=shipping_address,
                            is_partial=is_partial,
                            remaining_quantity=new_quantity if is_partial else 0
                        )
                    except Exception as e:
                        print(f"[CHECKOUT] Failed to send notification to seller: {e}")

            # Clear cart regardless (safe if buying from bucket)
            conn.execute('DELETE FROM cart WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()

            # Send buyer notification AFTER commit
            try:
                # Phase 0A: no grading fee in total
                total_items = sum(item['quantity'] for item in cart_data)
                order_total = round(
                    sum(item['quantity'] * item['price_each'] for item in cart_data),
                    2
                )

                # Get unique item types for description
                conn_temp = get_db_connection()
                item_types = set()
                for item in cart_data:
                    listing = conn_temp.execute('''
                        SELECT categories.metal, categories.product_type
                        FROM listings
                        JOIN categories ON listings.category_id = categories.id
                        WHERE listings.id = ?
                    ''', (item['listing_id'],)).fetchone()
                    if listing:
                        item_types.add(f"{listing['metal']} {listing['product_type']}")
                conn_temp.close()

                # Use first item description or "Multiple items" if more than one type
                if len(item_types) == 1:
                    buyer_item_description = list(item_types)[0]
                else:
                    buyer_item_description = f"{len(item_types)} different items"

                notify_order_confirmed(
                    buyer_id=user_id,
                    order_id=order_id,
                    item_description=buyer_item_description,
                    quantity_purchased=total_items,
                    price_per_unit=order_total / total_items if total_items > 0 else 0,
                    total_amount=order_total
                )
            except Exception as e:
                print(f"[CHECKOUT] Failed to send buyer notification: {e}")

            return redirect(url_for('checkout.order_confirmation', order_id=order_id))

    else:
        # Render the checkout page
        # IMPORTANT: do NOT pop here; we still need the selection for the final POST
        session_items = session.get('checkout_items')

        if session_items:
            # ── Direct bucket-purchase display ────────────────────────────────
            # Phase 0A: grading deactivated — ignore any stale tpg session value.
            buy_tpg = False
            buy_grading = 'NONE'

            raw_cart_items = []
            subtotal = 0.0
            for item in session_items:
                listing = conn.execute('''
                    SELECT listings.id, listings.price_per_coin, listings.quantity as available_qty,
                           listings.pricing_mode, listings.spot_premium,
                           listings.floor_price, listings.pricing_metal, listings.seller_id,
                           listings.category_id,
                           categories.metal, categories.product_type, categories.product_line,
                           categories.weight, categories.mint, categories.year,
                           categories.finish, categories.grade, categories.purity,
                           categories.bucket_id,
                           users.username as seller_username,
                           (SELECT file_path FROM listing_photos WHERE listing_id = listings.id LIMIT 1) as photo_path
                    FROM listings
                    JOIN categories ON listings.category_id = categories.id
                    JOIN users ON listings.seller_id = users.id
                    WHERE listings.id = ?
                ''', (item['listing_id'],)).fetchone()

                if listing:
                    listing_dict = dict(listing)
                    listing_dict['quantity'] = item['quantity']
                    listing_dict['price_per_coin'] = item['price_each']
                    listing_dict['total_price'] = item['quantity'] * item['price_each']
                    listing_dict['grading_preference'] = buy_grading
                    subtotal += listing_dict['total_price']
                    raw_cart_items.append(listing_dict)

            # Group session items by bucket_id for display
            bucket_groups = {}
            for item in raw_cart_items:
                bid = item.get('bucket_id') or item.get('category_id')
                if bid not in bucket_groups:
                    bucket_groups[bid] = {
                        'metal': item['metal'],
                        'product_type': item['product_type'],
                        'product_line': item.get('product_line'),
                        'weight': item['weight'],
                        'year': item['year'],
                        'mint': item.get('mint'),
                        'finish': item.get('finish'),
                        'grade': item.get('grade'),
                        'purity': item.get('purity'),
                        'photo_path': item.get('photo_path'),
                        'quantity': 0,
                        'total_price': 0.0,
                        'price_per_coin': 0.0,
                        'sellers': set(),
                        'listing_ids': [],
                        'grading_preference': buy_grading,
                    }
                g = bucket_groups[bid]
                g['quantity'] += item['quantity']
                g['total_price'] += item['total_price']
                g['sellers'].add(item.get('seller_username', 'Seller'))
                g['listing_ids'].append(item.get('listing_id') or item.get('id'))
                if not g['photo_path'] and item.get('photo_path'):
                    g['photo_path'] = item['photo_path']

            cart_items = []
            for bid, g in bucket_groups.items():
                g['price_per_coin'] = g['total_price'] / g['quantity'] if g['quantity'] else 0
                sellers_list = list(g['sellers'])
                g['seller_username'] = sellers_list[0] if len(sellers_list) == 1 else f"{len(sellers_list)} sellers"
                del g['sellers']
                cart_items.append(g)

            item_count = sum(i['quantity'] for i in cart_items)
            grading_fee = 0.0
            cart_total = round(subtotal + grading_fee, 2)

        else:
            # ── Cart checkout display — authoritative summary ─────────────────
            from services.reference_price_service import get_current_spots_from_snapshots
            _spot_prices = get_current_spots_from_snapshots(conn)
            summary = build_cart_summary(conn, user_id, spot_prices=_spot_prices)

            if not summary['buckets']:
                conn.close()
                flash("Your cart is empty.", "error")
                return redirect(url_for('buy.view_cart'))

            cart_items = []
            for bucket in summary['buckets'].values():
                sellers = {l['seller_username'] for l in bucket['listings']}
                seller_display = (next(iter(sellers)) if len(sellers) == 1
                                  else f"{len(sellers)} sellers")
                cart_items.append({
                    'metal': bucket['category']['metal'],
                    'product_type': bucket['category']['product_type'],
                    'product_line': bucket['category'].get('product_line'),
                    'weight': bucket['category']['weight'],
                    'year': bucket['category'].get('year'),
                    'mint': bucket['category'].get('mint'),
                    'finish': bucket['category'].get('finish'),
                    'grade': bucket['category'].get('grade'),
                    'purity': bucket['category'].get('purity'),
                    'photo_path': bucket['cover_photo_url'],
                    'quantity': bucket['total_qty'],
                    'total_price': bucket['total_price'],
                    'price_per_coin': bucket['avg_price'],
                    'seller_username': seller_display,
                    'grading_preference': bucket['grading_preference'],
                    'listing_ids': [l['listing_id'] for l in bucket['listings']],
                })

            item_count = summary['item_count']
            subtotal = summary['subtotal']
            grading_fee = 0.0
            cart_total = round(subtotal, 2)

        # Fetch user info for auto-population (shared by both paths)
        user_info = conn.execute('''
            SELECT first_name, last_name, email, phone
            FROM users WHERE id = ?
        ''', (user_id,)).fetchone()

        conn.close()

        # Generate a one-time nonce to guard against duplicate order submission.
        # Stored in the session and consumed on the first successful AJAX finalize.
        checkout_nonce = secrets.token_hex(16)
        session['checkout_nonce'] = checkout_nonce

        _subtotal_rounded = round(subtotal, 2)
        # Tax is fetched from Stripe when the buyer provides their address.
        # Initial render shows $0.00; the frontend JS calls /checkout/api/tax-estimate
        # once the address fields are populated to display the correct tax amount.
        _tax_display = 0.0

        return render_template(
            'checkout_page.html',
            cart_items=cart_items,
            item_count=item_count,
            subtotal=_subtotal_rounded,
            grading_fee=0.0,
            grading_fee_per_unit=0.0,
            cart_total=cart_total,
            tax_amount=_tax_display,
            user_info=dict(user_info) if user_info else {},
            checkout_nonce=checkout_nonce,
            stripe_publishable_key=STRIPE_PUBLISHABLE_KEY or '',
        )


@checkout_bp.route('/checkout/api/tax-estimate', methods=['POST'])
@frozen_check
def tax_estimate():
    """
    Return a Stripe Tax estimate for the given subtotal and address.

    Called by the frontend when the buyer's address (ZIP / state) is available,
    so the order summary can display the correct tax amount before final submission.

    Request JSON:
      { subtotal: float, postal_code: str, state: str, country: str }

    Response JSON (200):
      { tax_amount: float, taxed_subtotal: float }
    Response JSON (400):
      { error: str }
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    body = request.get_json(silent=True) or {}
    subtotal     = float(body.get('subtotal') or 0)
    postal_code  = str(body.get('postal_code') or body.get('zip_code') or '').strip()
    state        = str(body.get('state') or '').strip()
    country      = str(body.get('country') or 'US').strip() or 'US'

    if subtotal <= 0:
        return jsonify({'error': 'subtotal must be positive'}), 400

    tax_cents, calc_id = _get_stripe_tax(int(round(subtotal * 100)), postal_code, state, country)
    tax_amount = round(tax_cents / 100, 2)
    # tax_calculated=True only when Stripe actually returned a result (calc_id present).
    # When no postal code or Stripe fails, calc_id is None and we report uncalculated.
    return jsonify({
        'tax_amount':     tax_amount,
        'taxed_subtotal': round(subtotal + tax_amount, 2),
        'tax_calculated': calc_id is not None,
    })


@checkout_bp.route('/checkout/api/recalculate-spot', methods=['POST'])
@frozen_check
def recalculate_spot():
    """
    Refresh stale spot prices and recompute checkout totals.

    Called by the frontend "Recalculate" button inside the spot-expired modal.
    Uses get_spot_map_for_checkout() — which DOES trigger a live refresh if the
    snapshot is stale — unlike the finalize path, which uses the check-only
    variant.

    If session contains checkout_items (bucket purchase flow), recomputes
    price_each for each listing and updates the session so the next finalize
    uses the fresh prices.

    Returns JSON:
      200 {success:true, subtotal, grading_fee, cart_total, spot_as_of,
           updated_items:[{listing_id, quantity, price_each, total_price}]}
      503 {success:false, error_code:'SPOT_UNAVAILABLE', message}
    """
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        from services.checkout_spot_service import get_spot_map_for_checkout
        from services.pricing_service import get_effective_price

        session_items = session.get('checkout_items')
        buy_tpg = False  # Phase 0A: grading deactivated

        if session_items:
            # ── Bucket purchase: recompute price_each with fresh spot ──
            listing_ids = [i['listing_id'] for i in session_items]
            listing_meta = _fetch_listing_pricing_meta(conn, listing_ids)

            metals = {
                (m.get('pricing_metal') or m.get('metal') or '').lower()
                for m in listing_meta.values()
                if m.get('pricing_mode') == 'premium_to_spot'
            }
            try:
                spot_map = get_spot_map_for_checkout(metals) if metals else {}
            except SpotUnavailableError:
                conn.close()
                return jsonify({
                    'success': False,
                    'error_code': 'SPOT_UNAVAILABLE',
                    'message': SpotUnavailableError.USER_MESSAGE,
                }), 503

            spot_prices_dict = _build_spot_prices_dict(spot_map)

            updated_items = []
            subtotal = 0.0
            for item in session_items:
                meta = listing_meta.get(item['listing_id'], {})
                new_price = get_effective_price(dict(meta), spot_prices=spot_prices_dict)
                new_total = new_price * item['quantity']
                subtotal += new_total
                updated_items.append({
                    'listing_id': item['listing_id'],
                    'quantity': item['quantity'],
                    'price_each': new_price,
                    'total_price': new_total,
                })

            # Persist updated prices so the next finalize uses them
            session['checkout_items'] = [
                {'listing_id': i['listing_id'], 'quantity': i['quantity'],
                 'price_each': i['price_each']}
                for i in updated_items
            ]

            total_items = sum(i['quantity'] for i in updated_items)
            grading_fee = 0.0  # Phase 0A: grading deactivated

        else:
            # ── Cart checkout: rebuild summary with fresh spot ──
            cart_metals = _get_cart_metals_for_spot(conn, user_id)
            try:
                spot_map = get_spot_map_for_checkout(cart_metals) if cart_metals else {}
            except SpotUnavailableError:
                conn.close()
                return jsonify({
                    'success': False,
                    'error_code': 'SPOT_UNAVAILABLE',
                    'message': SpotUnavailableError.USER_MESSAGE,
                }), 503

            spot_prices_dict = _build_spot_prices_dict(spot_map)
            summary = build_cart_summary(conn, user_id, spot_prices=spot_prices_dict)

            subtotal = summary['subtotal']
            grading_fee = 0.0  # Phase 0A: grading deactivated
            total_items = summary['item_count']
            updated_items = [
                {
                    'listing_id': l['listing_id'],
                    'quantity': l['quantity'],
                    'price_each': l['effective_price'],
                    'total_price': l['quantity'] * l['effective_price'],
                }
                for b in summary['buckets'].values()
                for l in b['listings']
            ]

        # Pull spot_as_of from any returned spot_info
        spot_as_of = next(
            (info['as_of'] for info in spot_map.values() if info and info.get('as_of')),
            None,
        )
        cart_total = round(subtotal + grading_fee, 2)

        conn.close()
        return jsonify({
            'success': True,
            'subtotal': round(subtotal, 2),
            'grading_fee': round(grading_fee, 2),
            'cart_total': cart_total,
            'total_items': total_items,
            'spot_as_of': spot_as_of,
            'updated_items': updated_items,
        })

    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@checkout_bp.route('/checkout/confirm/<int:order_id>')
def order_confirmation(order_id):
    """Display order confirmation page with animated success"""
    # SECURITY: Must verify user is the buyer of this order
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    conn = get_db_connection()

    # Get order details - EXPLICITLY verify buyer ownership
    order = conn.execute('''
        SELECT o.id, o.total_price, o.created_at, o.buyer_id,
               COUNT(oi.id) as item_count,
               SUM(oi.quantity) as total_quantity
        FROM orders o
        LEFT JOIN order_items oi ON o.id = oi.order_id
        WHERE o.id = ? AND o.buyer_id = ?
        GROUP BY o.id
    ''', (order_id, user_id)).fetchone()

    conn.close()

    if not order:
        # Order doesn't exist or user is not the buyer
        flash("Order not found.", "error")
        return redirect(url_for('account.account'))

    return render_template(
        'order_confirmation.html',
        order_id=order_id,
        order_total=order['total_price'],
        item_count=order['total_quantity'] or order['item_count']
    )


@checkout_bp.route('/create-payment-intent', methods=['POST'])
def create_payment_intent():
    """
    Create a Stripe PaymentIntent for the current cart total.
    Returns the clientSecret so the frontend can mount the Payment Element.
    """
    import logging
    _log = logging.getLogger(__name__)

    # Global checkout safety switch — admin-controlled via system settings.
    from services.system_settings_service import get_checkout_enabled, get_payments_pause_reason
    if not get_checkout_enabled():
        reason = get_payments_pause_reason()
        msg = reason or "Checkout is temporarily unavailable. Please try again shortly."
        _log.warning('[PI] blocked — checkout disabled (admin toggle)')
        return jsonify({'error': msg}), 503

    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    # --- DB work: Stripe customer + cart total (same connection) -------------
    customer_id = None
    try:
        # Resolve or create the buyer's Stripe Customer so saved cards work.
        # Non-fatal: if this fails the PI is still created, just without a customer.
        try:
            from core.blueprints.account.payment_methods import _ensure_stripe_customer
            customer_id = _ensure_stripe_customer(user_id, conn)
            _log.info('[PI] resolved stripe customer %s for user %s', customer_id, user_id)
        except Exception:
            _log.warning('[PI] could not resolve Stripe customer for user %s — saved cards unavailable', user_id)

        session_items = session.get('checkout_items')
        # Phase 0A: grading deactivated — no grading fee in PaymentIntent.

        if session_items:
            subtotal = sum(i['price_each'] * i['quantity'] for i in session_items)
            grading_fee = 0.0
            _log.info('[PI] cart from session: subtotal=%.2f', subtotal)
        else:
            from services.reference_price_service import get_current_spots_from_snapshots
            spot_prices = get_current_spots_from_snapshots(conn)
            summary = build_cart_summary(conn, user_id, spot_prices=spot_prices)
            subtotal = summary['subtotal']
            grading_fee = 0.0
            _log.info('[PI] cart from DB: subtotal=%.2f buckets=%d',
                      subtotal, len(summary['buckets']))
    except Exception as e:
        _log.exception('[PI] failed to compute cart total for user %s', user_id)
        return jsonify({'error': 'Could not read cart: ' + str(e)}), 500
    finally:
        conn.close()  # always close — success and failure alike

    # --- Compute tax + card fee using address sent by the client -------------
    # The JS sends zip_code/state/country when it transitions to the payment
    # step, so we can compute the full charge amount right here instead of
    # relying on the modify() call later.
    req_json    = request.get_json(silent=True) or {}
    _pi_postal  = req_json.get('zip_code', '') or ''
    _pi_state   = req_json.get('state', '') or ''
    _pi_country = req_json.get('country', 'US') or 'US'

    _subtotal_cents = int(round((subtotal + grading_fee) * 100))
    _tax_cents, _tax_calc_id = _get_stripe_tax(
        _subtotal_cents, _pi_postal, _pi_state, _pi_country,
    )
    _tax_amount  = round(_tax_cents / 100, 2)
    _taxed_sub   = round((subtotal + grading_fee) + _tax_amount, 2)
    # Default to card fee (ACH path: fee is 0; determined at confirm time).
    # We default to card here so the PI amount is never *less* than needed.
    _card_fee    = round(_taxed_sub * CARD_RATE + CARD_FLAT, 2)
    _full_total  = round(_taxed_sub + _card_fee, 2)
    amount_cents = int(round(_full_total * 100))

    _log.info(
        '[PI] creating PaymentIntent subtotal=%.2f tax=%.2f card_fee=%.2f '
        'total=%.2f amount_cents=%d user=%s customer=%s',
        subtotal + grading_fee, _tax_amount, _card_fee,
        _full_total, amount_cents, user_id, customer_id,
    )

    if amount_cents <= 0:
        _log.warning('[PI] amount_cents=%d — cart may be empty, user=%s', amount_cents, user_id)
        return jsonify({'error': 'Cart total is zero. Please add items before checking out.'}), 400

    try:
        pi_kwargs = dict(
            amount=amount_cents,
            currency='usd',
            payment_method_types=['card', 'us_bank_account'],
            metadata={'user_id': str(user_id)},
        )
        if customer_id:
            pi_kwargs['customer'] = customer_id
            # Save the card to the customer so it appears in bid payment options
            pi_kwargs['setup_future_usage'] = 'off_session'
        payment_intent = stripe.PaymentIntent.create(**pi_kwargs)
        _log.info('[PI] created pi=%s user=%s customer=%s', payment_intent.id, user_id, customer_id)
    except stripe.error.StripeError as e:
        _log.error('[PI] Stripe error for user %s: %s', user_id, e)
        return jsonify({'error': str(e)}), 500

    return jsonify({
        'clientSecret': payment_intent.client_secret,
        'paymentIntentId': payment_intent.id,
    })


@checkout_bp.route('/attach-order-to-payment', methods=['POST'])
def attach_order_to_payment():
    """
    After order creation, stamp the order_id onto the PaymentIntent metadata
    so /order-success can look up the exact order by PI — not by "latest order".
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    user_id = session['user_id']
    body = request.get_json(silent=True) or {}
    payment_intent_id = body.get('payment_intent_id')
    order_id = body.get('order_id')

    if not payment_intent_id or not order_id:
        return jsonify({'error': 'Missing payment_intent_id or order_id'}), 400

    # Verify this order actually belongs to the current user before stamping it.
    conn = get_db_connection()
    row = conn.execute(
        "SELECT id FROM orders WHERE id = ? AND buyer_id = ?",
        (order_id, user_id)
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({'error': 'Order not found or access denied'}), 403

    try:
        stripe.PaymentIntent.modify(
            payment_intent_id,
            metadata={'user_id': str(user_id), 'order_id': str(order_id)},
        )
    except stripe.error.StripeError as e:
        return jsonify({'error': str(e)}), 500

    return jsonify({'ok': True})


@checkout_bp.route('/order-success')
def order_success():
    """
    Browser landing page after Stripe redirects the buyer back.

    This route is NOT the source of truth for payment finalization —
    the /stripe/webhook handler owns that responsibility.  This page
    only reads the current state of the order and renders an appropriate
    message.  It is safe to reload or revisit.
    """
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    payment_intent_id = request.args.get('payment_intent')

    if not payment_intent_id:
        flash('Payment information missing.', 'error')
        return redirect(url_for('buy.buy'))

    # Look up the order first via DB (PI ID stored during Phase 1 checkout).
    # This avoids depending on Stripe metadata stamping and is always fast.
    conn = get_db_connection()
    order = conn.execute(
        "SELECT id, total_price, status FROM orders WHERE stripe_payment_intent_id = ? AND buyer_id = ?",
        (payment_intent_id, user_id)
    ).fetchone()

    if not order:
        # Fallback: try metadata route (legacy or orders created before this change).
        try:
            pi_meta = stripe.PaymentIntent.retrieve(payment_intent_id)
            order_id_meta = pi_meta.metadata.get('order_id')
            if order_id_meta:
                order = conn.execute(
                    "SELECT id, total_price, status FROM orders WHERE id = ? AND buyer_id = ?",
                    (order_id_meta, user_id)
                ).fetchone()
        except Exception:
            pass

    conn.close()

    if not order:
        flash('Order not found. Please check your orders page.', 'error')
        return redirect(url_for('account.account'))

    # Check Stripe PI status to show confirmed vs processing state.
    # Non-fatal: if Stripe is unavailable, fall back to DB order status.
    pi_succeeded = False
    try:
        pi = stripe.PaymentIntent.retrieve(payment_intent_id)
        pi_succeeded = (pi.status == 'succeeded')
    except Exception:
        pass

    # Green checkmark if Stripe confirmed payment OR webhook already marked order paid.
    payment_received = pi_succeeded or (order['status'] == 'paid')

    return render_template(
        'order_success.html',
        order=dict(order),
        payment_received=payment_received,
    )
