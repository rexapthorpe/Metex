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
CARD_RATE = 0.0299   # Display only; canonical math uses integer basis points.

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
        _log.error('[Tax] Stripe Tax unavailable; checkout must fail closed: %s', exc)
        return 0, None


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
                # Canonical finalize: verify the bound immutable snapshot, then commit
                # execution, legacy UI projections, inventory, payables and ledger once.
                from services.flow_of_funds import FlowError, finalize_payment
                data = request.get_json(silent=True) or {}
                checkout_id = session.get('canonical_checkout_id')
                pi_id = (data.get('payment_intent_id') or '').strip()
                if not checkout_id or not pi_id:
                    conn.close()
                    return jsonify({'success':False,'message':'Canonical checkout identity is missing.',
                                    'error_code':'CHECKOUT_IDENTITY_MISSING'}), 409
                try:
                    pi = stripe.PaymentIntent.retrieve(pi_id)
                    result, created = finalize_payment(checkout_id, pi)
                    session.pop('checkout_nonce', None)
                    session.pop('canonical_checkout_id', None)
                    session.pop('checkout_items', None)
                    conn.close()
                    return jsonify({'success':True,'order_id':result['legacy_order_id'],
                                    'execution_id':result['id'],'created':created})
                except FlowError as exc:
                    conn.close()
                    return jsonify({'success':False,'message':str(exc),'error_code':exc.code}), exc.status
                except stripe.error.StripeError:
                    conn.close()
                    return jsonify({'success':False,'message':'Payment verification is temporarily unavailable.',
                                    'error_code':'PAYMENT_VERIFICATION_UNAVAILABLE'}), 503

                raise AssertionError('canonical finalize returned without a response')

            conn.close()
            flash('Please complete payment through the secure checkout form.', 'error')
            return redirect(url_for('checkout.checkout'))

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
@frozen_check
def create_payment_intent():
    """Reserve inventory, freeze checkout economics, then create one bound PI."""
    import logging
    from services.flow_of_funds import (
        FlowError, bind_provider_payment, claim_operation, ensure_flow_schema,
        prepare_checkout, require_approved_policy,
    )
    log = logging.getLogger(__name__)
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    from services.system_settings_service import get_checkout_enabled, get_payments_pause_reason
    if not get_checkout_enabled():
        return jsonify({'error': get_payments_pause_reason() or 'Checkout is temporarily unavailable.'}), 503
    user_id = session['user_id']
    body = request.get_json(silent=True) or {}
    nonce = session.get('checkout_nonce')
    if not nonce:
        return jsonify({'error': 'Checkout session expired. Please refresh.'}), 409
    conn = get_db_connection()
    try:
        ensure_flow_schema(conn)
        require_approved_policy(conn, 'tracking_upload_deadline_days',
                                'ups_coverage_and_claim_policy')
        session_items = session.get('checkout_items')
        if session_items:
            cart_data = [dict(i, requires_grading=bool(i.get('requires_grading', False))) for i in session_items]
        else:
            from services.reference_price_service import get_current_spots_from_snapshots
            summary = build_cart_summary(conn, user_id, spot_prices=get_current_spots_from_snapshots(conn))
            cart_data = [{'listing_id': x['listing_id'], 'quantity': x['quantity'],
                          'price_each': x['effective_price'],
                          'requires_grading': bool(x.get('requires_grading'))}
                         for b in summary['buckets'].values() for x in b['listings']]
        if not cart_data:
            return jsonify({'error': 'Cart is empty.'}), 400
        subtotal_cents = sum(int(round(float(i['price_each'])*100))*int(i['quantity']) for i in cart_data)
        tax_cents, tax_calc_id = _get_stripe_tax(
            subtotal_cents, body.get('zip_code',''), body.get('state',''), body.get('country','US'))
        if not tax_calc_id or tax_calc_id == 'fallback_rate':
            return jsonify({'error': 'Tax could not be verified. Check the delivery address and try again.'}), 503
        shipping = {'shipping_address': body.get('shipping_address',''),
                    'recipient_first': body.get('recipient_first',''),
                    'recipient_last': body.get('recipient_last',''),
                    'city': body.get('city',''), 'state': body.get('state',''),
                    'postal_code': body.get('zip_code',''), 'country': body.get('country','US'),
                    'tax_calculation_id': tax_calc_id}
        checkout, snapshot, _ = prepare_checkout(
            user_id, cart_data, 'card', tax_cents, shipping,
            idempotency_key=f'browser:{user_id}:{nonce}', conn=conn)
        existing = conn.execute('SELECT * FROM financial_operations WHERE aggregate_id=? AND operation_type=\'PAYMENT\'',
                                (checkout['id'],)).fetchone()
        if existing and existing['provider_object_id']:
            conn.commit(); pi = stripe.PaymentIntent.retrieve(existing['provider_object_id'])
            session['canonical_checkout_id'] = checkout['id']
            return jsonify({'clientSecret': pi.client_secret, 'paymentIntentId': pi.id,
                            'checkoutId': checkout['id']})
        op, _ = claim_operation(conn, 'PAYMENT', f'payment:{checkout["id"]}', 'checkout', checkout['id'],
                                snapshot['buyer_total_cents'], {'snapshot_hash':snapshot['snapshot_hash']})
        customer_id = None
        try:
            from core.blueprints.account.payment_methods import _ensure_stripe_customer
            customer_id = _ensure_stripe_customer(user_id, conn)
        except Exception:
            log.warning('Could not bind Stripe customer for buyer %s', user_id, exc_info=True)
        conn.commit()
        kwargs = {'amount': snapshot['buyer_total_cents'], 'currency':'usd',
                  'payment_method_types':['card','us_bank_account'],
                  'metadata': {'checkout_id':checkout['id'], 'snapshot_hash':snapshot['snapshot_hash'],
                               'buyer_id':str(user_id), 'policy_version':'flow-of-funds-v1'}}
        if customer_id:
            kwargs.update(customer=customer_id, setup_future_usage='off_session')
        pi = stripe.PaymentIntent.create(**kwargs, idempotency_key=op['idempotency_key'])
        bind_provider_payment(checkout['id'], pi.id, op['id'], conn=conn)
        conn.commit(); session['canonical_checkout_id'] = checkout['id']
        return jsonify({'clientSecret':pi.client_secret,'paymentIntentId':pi.id,'checkoutId':checkout['id']})
    except FlowError as exc:
        conn.rollback(); return jsonify({'error':str(exc),'error_code':exc.code}), exc.status
    except stripe.error.StripeError:
        conn.rollback(); log.exception('Stripe PI creation failed')
        return jsonify({'error':'Payment setup failed. Please try again.'}), 502
    except Exception:
        conn.rollback(); log.exception('Canonical checkout preparation failed')
        return jsonify({'error':'Checkout could not be prepared.'}), 500
    finally:
        conn.close()


@checkout_bp.route('/attach-order-to-payment', methods=['POST'])
def attach_order_to_payment():
    """Retired: provider payments are bound before confirmation."""
    return jsonify({'error':'This legacy payment path has been retired.'}), 410


@checkout_bp.route('/checkout/prepare-payment', methods=['POST'])
@frozen_check
def prepare_payment():
    """Freeze the selected rail and update the bound unconfirmed PI."""
    from services.flow_of_funds import FlowError, revise_payment_rail
    if 'user_id' not in session:
        return jsonify({'success':False,'error':'Not authenticated'}), 401
    data=request.get_json(silent=True) or {}; checkout_id=session.get('canonical_checkout_id')
    if not checkout_id or data.get('checkout_nonce') != session.get('checkout_nonce'):
        return jsonify({'success':False,'message':'Checkout session expired.'}), 409
    rail=data.get('payment_method_type') or 'card'; pi_id=(data.get('payment_intent_id') or '').strip()
    conn=get_db_connection()
    try:
        checkout=conn.execute('SELECT * FROM checkout_attempts WHERE id=? AND buyer_id=?',(checkout_id,session['user_id'])).fetchone()
        if not checkout or checkout['provider_payment_id'] != pi_id:
            raise FlowError('Payment is not bound to this checkout','PAYMENT_BINDING_MISMATCH',409)
        snapshot, changed=revise_payment_rail(checkout_id,rail,conn=conn)
        metadata={'checkout_id':checkout_id,'snapshot_hash':snapshot['snapshot_hash'],
                  'buyer_id':str(session['user_id']),'policy_version':'flow-of-funds-v1'}
        stripe.PaymentIntent.modify(pi_id,amount=snapshot['buyer_total_cents'],metadata=metadata)
        conn.execute('UPDATE financial_operations SET amount_cents=?,request_hash=?,updated_at=CURRENT_TIMESTAMP WHERE aggregate_id=? AND operation_type=\'PAYMENT\'',
                     (snapshot['buyer_total_cents'],snapshot['snapshot_hash'],checkout_id))
        conn.commit()
        return jsonify({'success':True,'tax_amount':snapshot['tax_cents']/100,
                        'buyer_card_fee':snapshot['card_surcharge_cents']/100,
                        'items_subtotal':snapshot['merchandise_cents']/100,
                        'total':snapshot['buyer_total_cents']/100,'total_cents':snapshot['buyer_total_cents']})
    except FlowError as exc:
        conn.rollback(); return jsonify({'success':False,'message':str(exc),'error_code':exc.code}),exc.status
    except stripe.error.StripeError:
        conn.rollback(); return jsonify({'success':False,'message':'Payment setup failed. Please try again.'}),502
    finally:
        conn.close()


@checkout_bp.route('/order-success')
def order_success():
    """Read-only recovery page; webhook or canonical finalize owns all writes."""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    pi_id=request.args.get('payment_intent'); conn=get_db_connection()
    order=conn.execute('SELECT id,total_price,status FROM orders WHERE stripe_payment_intent_id=? AND buyer_id=?',
                       (pi_id,session['user_id'])).fetchone() if pi_id else None
    if not order and pi_id:
        try:
            pi=stripe.PaymentIntent.retrieve(pi_id)
            checkout_id=(pi.to_dict() if hasattr(pi,'to_dict') else dict(pi)).get('metadata',{}).get('checkout_id')
            if checkout_id and pi.status=='succeeded':
                from services.flow_of_funds import finalize_payment
                result,_=finalize_payment(checkout_id,pi)
                order=conn.execute('SELECT id,total_price,status FROM orders WHERE id=?',(result['legacy_order_id'],)).fetchone()
        except Exception:
            import logging; logging.getLogger(__name__).exception('Payment recovery is awaiting webhook replay')
    conn.close()
    if not order:
        flash('Your payment is still being verified. Your order will appear automatically; do not pay again.','info')
        return redirect(url_for('account.account'))
    return render_template('order_success.html',order=dict(order),payment_received=True)
