# core/blueprints/bids/auto_match.py
"""
Auto-matching helper functions for bids and listings.

These functions handle automatic matching of bids to listings and vice versa,
using the spread model pricing system.
"""

import logging
import os
import threading

import stripe

from core.services.ledger.order_creation import create_order_ledger_from_cart
from services.pricing_service import (
    get_effective_price,
    get_effective_bid_price,
    can_bid_fill_listing,
)
from services.notification_types import notify_bid_payment_failed

logger = logging.getLogger(__name__)

# Prevents concurrent rematch runs (scheduler tick + manual spot insert) from
# processing the same bids simultaneously and creating duplicate orders.
# Scoped to one process; deploy with --workers 1 --threads N (see render.yaml).
_rematch_lock = threading.Lock()

# Startup guard: warn if this process is one of several Gunicorn workers.
# WEB_CONCURRENCY is set by Render/Gunicorn when >1 worker is spawned.
_web_concurrency = int(os.environ.get('WEB_CONCURRENCY', 1))
if _web_concurrency > 1:
    logger.warning(
        "[bid_rematch] WEB_CONCURRENCY=%d — _rematch_lock is process-local. "
        "Concurrent rematches across workers can produce duplicate orders. "
        "Deploy with --workers 1 --threads N.",
        _web_concurrency,
    )

# ── Charge components ─────────────────────────────────────────────────────────
# These MUST stay in sync with core/blueprints/bids/accept_bid.py and
# core/blueprints/checkout/routes.py — all bid and checkout charge paths must
# use the exact same formula so buyers are always charged the same total.
_CARD_RATE = 0.0299   # 2.99%
_CARD_FLAT = 0.30     # $0.30 fixed per transaction

# Must match accept_bid.py and the preview rate in bid_modal_steps.js.
# Applied when Stripe Tax is unavailable but a postal code is present.
FALLBACK_TAX_RATE = 0.0825  # 8.25%


def _parse_address_for_tax(delivery_address: str):
    """
    Extract (postal_code, state) from a bullet-separated delivery_address string.
    Format: "Line1 [• Line2] • City, STATE ZIP"
    Returns ('', '') if parsing fails.

    NOTE: Duplicated from accept_bid.py — both copies must stay in sync.
    """
    import re
    if not delivery_address:
        return '', ''
    parts = [p.strip() for p in delivery_address.split('•')]
    last = parts[-1] if parts else ''
    m = re.search(r'\b([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\s*$', last)
    if m:
        return m.group(2), m.group(1)  # (postal_code, state)
    return '', ''


def _get_stripe_tax_for_bid(subtotal_cents: int, postal_code: str, state: str = '') -> int:
    """
    Look up sales tax via Stripe Tax for a bid-acceptance charge.
    Returns tax in cents.  Falls back to 0 on any error or missing address.

    NOTE: Duplicated from accept_bid.py — both copies must stay in sync.
    """
    if not postal_code or subtotal_cents <= 0:
        return 0
    try:
        calc = stripe.tax.Calculation.create(
            currency='usd',
            line_items=[{'amount': subtotal_cents, 'reference': 'bid_subtotal'}],
            customer_details={
                'address': {
                    'postal_code': str(postal_code).strip(),
                    'state': str(state).strip() if state else '',
                    'country': 'US',
                },
                'address_source': 'shipping',
            },
        )
        logger.info('[auto_match TAX] calc=%s subtotal_cents=%d tax_cents=%d',
                    calc.id, subtotal_cents, calc.tax_amount_exclusive)
        return int(calc.tax_amount_exclusive)
    except Exception as exc:
        # Stripe Tax unavailable (not activated, network error, etc.).
        # Apply fallback rate so the buyer is charged what the bid modal showed.
        # MUST match the fallback in accept_bid.py and bid_modal_steps.js.
        fallback = round(subtotal_cents * FALLBACK_TAX_RATE)
        logger.warning(
            '[auto_match TAX] Stripe Tax unavailable — using fallback %.2f%% (%d cents): %s',
            FALLBACK_TAX_RATE * 100, fallback, exc,
        )
        return fallback


def _get_spot_prices_from_cursor(cursor):
    """
    Fetch spot prices using the canonical source: spot_price_snapshots.

    This is the SAME source used by cart, checkout, and bucket page so bid
    matching always prices against the most recently committed snapshot
    (including manual admin inserts and scheduler ticks).

    Falls back to the legacy spot_prices cache table if no snapshots exist
    (backward-compatible with test environments that only populate spot_prices).

    Never calls an external API.
    """
    try:
        # MAX(id) per metal == most recently inserted row for that metal.
        rows = cursor.execute(
            "SELECT metal, price_usd FROM spot_price_snapshots "
            "WHERE id IN (SELECT MAX(id) FROM spot_price_snapshots GROUP BY metal)"
        ).fetchall()
        if rows:
            return {row["metal"].lower(): float(row["price_usd"]) for row in rows}
    except Exception:
        pass  # table may not exist in minimal test environments

    # Fallback: legacy spot_prices cache table
    try:
        rows = cursor.execute(
            "SELECT metal, price_usd_per_oz FROM spot_prices"
        ).fetchall()
        return {row["metal"].lower(): float(row["price_usd_per_oz"]) for row in rows}
    except Exception:
        return {}


def _charge_bid_payment(bid_id: int, order_id: int, buyer_id: int,
                        pm_id: str, customer_id: str, amount_dollars: float,
                        pm_type: str = 'card') -> dict:
    """
    Create and confirm a Stripe PaymentIntent for a bid auto-fill.

    Supports both card and ACH bank account payment methods:
    - Cards:  off_session=True, payment_method_types=['card'], status must be 'succeeded'
    - ACH:    mandate required, no off_session, payment_method_types=['us_bank_account'],
              'processing' is success (ACH settles in 1-4 business days)

    Returns:
        {'success': True, 'pi_id': 'pi_xxx', 'pm_type': '...'}
        {'success': False, 'code': '...', 'message': '...', 'is_card_decline': bool}
    """
    is_ach = (pm_type == 'us_bank_account')

    try:
        create_kwargs = dict(
            amount=max(1, round(amount_dollars * 100)),
            currency='usd',
            customer=customer_id,
            payment_method=pm_id,
            payment_method_types=['us_bank_account'] if is_ach else ['card'],
            confirm=True,
            metadata={
                'user_id': str(buyer_id),
                'order_id': str(order_id),
                'bid_id': str(bid_id),
                'source': 'bid_auto_fill',
                'pm_type': pm_type,
            },
            idempotency_key=f'bid-autofill-{bid_id}-{order_id}',
        )
        if not is_ach:
            create_kwargs['off_session'] = True
        else:
            # ACH off-session debits require the mandate from the buyer's SetupIntent.
            mandate_id = None
            try:
                for si in stripe.SetupIntent.list(
                        customer=customer_id, limit=50).auto_paging_iter():
                    if (si.get('payment_method') == pm_id
                            and si.status == 'succeeded'
                            and si.get('mandate')):
                        mandate_id = si.mandate
                        break
            except stripe.error.StripeError as e:
                logger.warning('[auto_match] Could not list SetupIntents for mandate '
                               'lookup PM %s: %s', pm_id, e)
            if mandate_id:
                create_kwargs['mandate'] = mandate_id
            else:
                logger.error('[auto_match] No mandate found for ACH PM %s — '
                             'charge will fail', pm_id)

        pi = stripe.PaymentIntent.create(**create_kwargs)

        if pi.status in ('succeeded', 'processing'):
            return {'success': True, 'pi_id': pi.id, 'pm_type': pm_type}
        return {
            'success': False,
            'code': pi.status,
            'message': f'Payment could not be confirmed automatically (status: {pi.status}).',
            'is_card_decline': False,
        }
    except stripe.error.CardError as e:
        err = e.error
        return {
            'success': False,
            'code': getattr(err, 'code', 'card_error'),
            'message': getattr(err, 'message', str(e)) or 'Card declined.',
            'is_card_decline': True,
        }
    except stripe.error.InvalidRequestError as e:
        logger.error('[auto_match] InvalidRequest charging bid %s order %s pm_type=%s: %s',
                     bid_id, order_id, pm_type, e)
        return {'success': False, 'code': 'invalid_request', 'message': str(e), 'is_card_decline': False}
    except stripe.error.StripeError as e:
        logger.error('[auto_match] Stripe error charging bid %s order %s: %s', bid_id, order_id, e)
        return {'success': False, 'code': 'stripe_error', 'message': str(e), 'is_card_decline': False}


def auto_match_bid_to_listings(bid_id, cursor):
    """
    Automatically match a bid to available listings.
    Called immediately after bid creation to auto-fill if possible.

    IMPORTANT: For premium-to-spot bids, this calculates the effective bid price
    (spot + premium, capped at ceiling) and only matches listings at or below that price.

    Args:
        bid_id: The ID of the newly created bid
        cursor: Database cursor (assumes transaction is already open)

    Returns:
        dict with 'filled_quantity', 'orders_created', 'message'
    """
    # Load the bid with all fields including metal and weight for price calculation
    bid = cursor.execute('''
        SELECT b.*, c.metal, c.weight, c.product_type
        FROM bids b
        JOIN categories c ON b.category_id = c.id
        WHERE b.id = ?
    ''', (bid_id,)).fetchone()

    if not bid or bid['remaining_quantity'] <= 0:
        return {'filled_quantity': 0, 'orders_created': 0, 'message': 'No quantity to fill'}

    bid_dict = dict(bid)
    category_id = bid_dict['category_id']
    buyer_id = bid_dict['buyer_id']
    delivery_address = bid_dict['delivery_address']
    quantity_needed = bid_dict['remaining_quantity']
    recipient_first_name = bid_dict['recipient_first_name']
    recipient_last_name = bid_dict['recipient_last_name']

    # Fetch buyer's Stripe credentials for auto-charge
    bid_pm_id = bid_dict.get('bid_payment_method_id')
    try:
        buyer_row = cursor.execute(
            'SELECT stripe_customer_id FROM users WHERE id = ?', (buyer_id,)
        ).fetchone()
        buyer_customer_id = buyer_row['stripe_customer_id'] if buyer_row else None
    except Exception:
        buyer_customer_id = None

    # Determine PM type once (needed for fee calc + PI creation).
    bid_pm_type = 'card'
    bid_is_ach = False
    if bid_pm_id:
        try:
            _pm_obj = stripe.PaymentMethod.retrieve(bid_pm_id)
            bid_pm_type = _pm_obj.type
            bid_is_ach = (bid_pm_type == 'us_bank_account')
        except stripe.error.StripeError as e:
            logger.warning('[auto_match] Could not check PM type for %s: %s — assuming card',
                           bid_pm_id, e)

    # Fetch spot prices from spot_price_snapshots (canonical source, same as cart/checkout/
    # bucket page).  Falls back to spot_prices legacy cache if no snapshots exist.
    # Never calls an external API.
    spot_prices = _get_spot_prices_from_cursor(cursor)

    # Calculate effective bid price (handles both static and premium-to-spot modes)
    # For premium-to-spot, this calculates spot + premium and enforces ceiling
    effective_bid_price = get_effective_bid_price(bid_dict, spot_prices=spot_prices)

    # This is the maximum price the buyer will pay
    bid_price = effective_bid_price

    # Query matching listings - fetch ALL fields needed for effective price calculation.
    # We'll filter by effective price in Python after calculating it for each listing.
    # IMPORTANT: Exclude listings from the same user (no self-trades).
    # Grading is NOT used as an eligibility constraint.
    random_year = bid_dict.get('random_year', 0)

    if random_year:
        # Random Year ON: match listings from any category with the same specs except year.
        # Fetch bid's category specs to use for cross-year matching.
        bid_cat = cursor.execute('''
            SELECT metal, product_line, product_type, weight, purity, mint, finish
            FROM categories WHERE id = ?
        ''', (category_id,)).fetchone()

        # Find all category IDs that share the same specs but any year.
        # Use IS for NULL-safe equality (SQLite: NULL IS NULL = TRUE).
        matching_cats = cursor.execute('''
            SELECT id FROM categories
            WHERE metal IS ?
              AND product_line IS ?
              AND product_type IS ?
              AND weight IS ?
              AND purity IS ?
              AND mint IS ?
              AND finish IS ?
        ''', (
            bid_cat['metal'], bid_cat['product_line'], bid_cat['product_type'],
            bid_cat['weight'], bid_cat['purity'], bid_cat['mint'], bid_cat['finish']
        )).fetchall()

        cat_ids = [row['id'] for row in matching_cats] or [category_id]
        placeholders = ','.join('?' * len(cat_ids))

        listings = cursor.execute(f'''
            SELECT l.id, l.seller_id, l.quantity, l.price_per_coin, l.grading_service,
                   l.pricing_mode, l.spot_premium, l.floor_price, l.pricing_metal,
                   c.metal, c.weight
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE l.category_id IN ({placeholders})
              AND l.seller_id != ?
              AND l.active = 1
              AND l.quantity > 0
        ''', cat_ids + [buyer_id]).fetchall()
    else:
        # Standard exact category match (Random Year OFF or unset).
        listings = cursor.execute('''
            SELECT l.id, l.seller_id, l.quantity, l.price_per_coin, l.grading_service,
                   l.pricing_mode, l.spot_premium, l.floor_price, l.pricing_metal,
                   c.metal, c.weight
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE l.category_id = ?
              AND l.seller_id != ?
              AND l.active = 1
              AND l.quantity > 0
        ''', (category_id, buyer_id)).fetchall()

    if not listings:
        return {'filled_quantity': 0, 'orders_created': 0, 'message': 'No matching listings found'}

    # ============================================================================
    # SPREAD MODEL MATCHING
    # Uses can_bid_fill_listing() to match all 4 combinations (fixed/variable)
    # ============================================================================

    # Calculate pricing info for each listing using spread model
    matched_listings = []
    for listing in listings:
        listing_dict = dict(listing)

        # Check if bid can fill this listing (works for all 4 combinations)
        pricing_info = can_bid_fill_listing(bid_dict, listing_dict, spot_prices=spot_prices)

        if pricing_info['can_fill']:
            # Store pricing info on the listing for later use
            listing_dict['bid_effective_price'] = pricing_info['bid_effective_price']
            listing_dict['listing_effective_price'] = pricing_info['listing_effective_price']
            listing_dict['spread'] = pricing_info['spread']
            matched_listings.append(listing_dict)

    # Sort by listing effective price (cheapest for seller first), then by id
    matched_listings.sort(key=lambda x: (x['listing_effective_price'], x['id']))

    if not matched_listings:
        return {'filled_quantity': 0, 'orders_created': 0, 'message': 'No matching listings found (bid price < listing price)'}

    # Determine fills (no DB changes yet) — group by seller so we can use SAVEPOINTs
    seller_fills = {}   # seller_id → [{'listing': dict, 'fill_qty': int, 'buyer_price_each': float, 'seller_price_each': float}]
    total_planned = 0

    for listing in matched_listings:
        if total_planned >= quantity_needed:
            break
        seller_id = listing['seller_id']
        fill_qty = min(listing['quantity'], quantity_needed - total_planned)
        if seller_id not in seller_fills:
            seller_fills[seller_id] = []
        seller_fills[seller_id].append({
            'listing': listing,
            'fill_qty': fill_qty,
            'buyer_price_each': listing['bid_effective_price'],
            'seller_price_each': listing['listing_effective_price'],
        })
        total_planned += fill_qty

    # Get item description for notifications
    category_info = cursor.execute('''
        SELECT metal, product_type, product_line, weight, year
        FROM categories WHERE id = ?
    ''', (category_id,)).fetchone()

    item_desc_parts = []
    if category_info:
        if category_info['metal']:
            item_desc_parts.append(category_info['metal'])
        if category_info['product_line']:
            item_desc_parts.append(category_info['product_line'])
        if category_info['weight']:
            item_desc_parts.append(category_info['weight'])
    item_description = ' '.join(item_desc_parts) if item_desc_parts else 'Item'

    # Per-seller: SAVEPOINT → deduct inventory → create order → charge card → RELEASE/ROLLBACK
    orders_created = 0
    total_filled = 0
    notifications_to_send = []
    ledger_orders = []
    payment_failed = False
    payment_failure_notifs = []

    for seller_id, fills in seller_fills.items():
        sp = f'amsp{bid_id}s{seller_id}'
        cursor.execute(f'SAVEPOINT {sp}')

        # Atomically deduct inventory for all of this seller's listings
        deduct_ok = True
        for fill in fills:
            _r = cursor.execute('''
                UPDATE listings
                   SET quantity = quantity - ?,
                       active   = CASE WHEN quantity - ? <= 0 THEN 0 ELSE active END
                 WHERE id = ? AND quantity >= ? AND active = 1
            ''', (fill['fill_qty'], fill['fill_qty'], fill['listing']['id'], fill['fill_qty']))
            if _r.rowcount == 0:
                deduct_ok = False
                break

        if not deduct_ok:
            cursor.execute(f'ROLLBACK TO SAVEPOINT {sp}')
            cursor.execute(f'RELEASE SAVEPOINT {sp}')
            continue

        fill_qty_total = sum(f['fill_qty'] for f in fills)

        # ── Compute full charge: subtotal → tax → card fee → total ───────────
        # All items are priced at buyer_price_each (bid effective price).
        _subtotal       = round(sum(f['fill_qty'] * f['buyer_price_each'] for f in fills), 2)
        _subtotal_cents = int(round(_subtotal * 100))

        # Parse buyer's delivery address to get postal code for Stripe Tax.
        _postal, _state = _parse_address_for_tax(delivery_address)
        _tax_cents      = _get_stripe_tax_for_bid(_subtotal_cents, _postal, _state)
        _tax_amount     = round(_tax_cents / 100, 2)
        _taxed_subtotal = _subtotal + _tax_amount

        # Card payments: 2.99% + $0.30 fee. ACH bank account: no card fee.
        _bid_card_fee   = 0.0 if bid_is_ach else round(_taxed_subtotal * _CARD_RATE + _CARD_FLAT, 2)

        # Final charge: subtotal + tax + card fee
        fill_total      = round(_taxed_subtotal + _bid_card_fee, 2)
        _charged_cents  = int(round(fill_total * 100))

        logger.info(
            '[auto_match] bid=%s seller=%s subtotal=%.2f tax=%.2f card_fee=%.2f '
            'total=%.2f pi_cents=%d postal=%r',
            bid_id, seller_id, _subtotal, _tax_amount, _bid_card_fee,
            fill_total, _charged_cents, _postal,
        )

        # Hard assertion: charged amount must equal subtotal + tax + fee exactly.
        # If this fails, abort loudly rather than silently undercharging.
        _fee_cents      = int(round(_bid_card_fee * 100))
        _expected_cents = _subtotal_cents + _tax_cents + _fee_cents
        if _charged_cents != _expected_cents:
            logger.error(
                '[auto_match] ASSERTION FAILED: charged_cents=%d != '
                'subtotal_cents=%d + tax_cents=%d + fee_cents=%d (=%d) for bid %s',
                _charged_cents, _subtotal_cents, _tax_cents, _fee_cents,
                _expected_cents, bid_id,
            )
            cursor.execute(f'ROLLBACK TO SAVEPOINT {sp}')
            cursor.execute(f'RELEASE SAVEPOINT {sp}')
            payment_failed = True
            payment_failure_notifs.append({
                'buyer_id': buyer_id,
                'bid_id': bid_id,
                'failure_message': 'Internal error computing charge amount.',
            })
            break

        # Sanity guard: charged amount must never be less than the subtotal alone.
        if _charged_cents < _subtotal_cents:
            logger.error(
                '[auto_match] BUG: charged_cents %d < subtotal_cents %d for bid %s',
                _charged_cents, _subtotal_cents, bid_id,
            )
            cursor.execute(f'ROLLBACK TO SAVEPOINT {sp}')
            cursor.execute(f'RELEASE SAVEPOINT {sp}')
            payment_failed = True
            payment_failure_notifs.append({
                'buyer_id': buyer_id,
                'bid_id': bid_id,
                'failure_message': 'Internal error computing charge amount.',
            })
            break

        _effective_tax_rate = round(_tax_amount / _subtotal, 6) if _subtotal else 0.0

        # Create order as unpaid initially (total = subtotal + tax + card_fee)
        cursor.execute('''
            INSERT INTO orders (buyer_id, total_price, buyer_card_fee, tax_amount, tax_rate,
                               shipping_address, status, created_at,
                               recipient_first_name, recipient_last_name, payment_status, source_bid_id)
            VALUES (?, ?, ?, ?, ?, ?, 'Pending Shipment', datetime('now'), ?, ?, 'unpaid', ?)
        ''', (buyer_id, fill_total, _bid_card_fee, _tax_amount, _effective_tax_rate,
              delivery_address, recipient_first_name, recipient_last_name, bid_id))
        order_id = cursor.lastrowid

        for fill in fills:
            cursor.execute('''
                INSERT INTO order_items (order_id, listing_id, quantity, price_each, seller_price_each)
                VALUES (?, ?, ?, ?, ?)
            ''', (order_id, fill['listing']['id'], fill['fill_qty'],
                  fill['buyer_price_each'], fill['seller_price_each']))

        # Charge buyer's saved payment method (card or ACH bank account)
        if bid_pm_id and buyer_customer_id:
            pay_result = _charge_bid_payment(
                bid_id=bid_id, order_id=order_id, buyer_id=buyer_id,
                pm_id=bid_pm_id, customer_id=buyer_customer_id,
                amount_dollars=fill_total,
                pm_type=bid_pm_type,
            )

            if not pay_result['success']:
                cursor.execute(f'ROLLBACK TO SAVEPOINT {sp}')
                cursor.execute(f'RELEASE SAVEPOINT {sp}')

                cursor.execute('''
                    UPDATE bids
                       SET bid_payment_status = 'failed',
                           bid_payment_failure_code = ?,
                           bid_payment_failure_message = ?,
                           bid_payment_attempted_at = datetime('now'),
                           active = 0,
                           status = 'Payment Failed'
                     WHERE id = ?
                ''', (pay_result.get('code'), pay_result.get('message'), bid_id))

                if pay_result.get('is_card_decline'):
                    cursor.execute('''
                        UPDATE users
                           SET bid_payment_strikes = COALESCE(bid_payment_strikes, 0) + 1
                         WHERE id = ?
                    ''', (buyer_id,))

                payment_failed = True
                payment_failure_notifs.append({
                    'buyer_id': buyer_id,
                    'bid_id': bid_id,
                    'failure_message': pay_result.get('message', 'Payment declined.'),
                })
                break

            # Payment succeeded — stamp order with payment info
            _paid_pm_type = pay_result.get('pm_type', 'card')
            cursor.execute('''
                UPDATE orders
                   SET stripe_payment_intent_id = ?,
                       payment_status = 'paid',
                       status = 'paid',
                       paid_at = datetime('now'),
                       payment_method_type = ?
                 WHERE id = ?
            ''', (pay_result['pi_id'], _paid_pm_type, order_id))

            cursor.execute('''
                UPDATE bids
                   SET bid_payment_status = 'charged',
                       bid_payment_intent_id = ?,
                       bid_payment_attempted_at = datetime('now')
                 WHERE id = ?
            ''', (pay_result['pi_id'], bid_id))
        else:
            logger.warning('[auto_match] Bid %s has no payment method — order %s created as unpaid', bid_id, order_id)

        cursor.execute(f'RELEASE SAVEPOINT {sp}')
        orders_created += 1
        total_filled += fill_qty_total

        # Use subtotal (not fill_total) for per-unit display — price_per_unit
        # should reflect the coin price, not the charge including tax/fees.
        avg_price = _subtotal / fill_qty_total if fill_qty_total > 0 else effective_bid_price
        notifications_to_send.append({
            'buyer_id': buyer_id,
            'order_id': order_id,
            'bid_id': bid_id,
            'item_description': item_description,
            'quantity_filled': fill_qty_total,
            'price_per_unit': avg_price,
            'total_amount': fill_total,
            'is_partial': False,
            'remaining_quantity': 0,
        })

        ledger_orders.append({
            'buyer_id': buyer_id,
            'order_id': order_id,
            'items': [
                {
                    'seller_id': seller_id,
                    'listing_id': fill['listing']['id'],
                    'quantity': fill['fill_qty'],
                    'unit_price': fill['seller_price_each'],
                    'buyer_unit_price': fill['buyer_price_each'],
                }
                for fill in fills
            ],
        })

    if payment_failed:
        return {
            'filled_quantity': 0,
            'orders_created': 0,
            'message': 'Auto-fill payment failed — bid closed.',
            'notifications': [],
            'ledger_orders': [],
            'payment_failure_notifs': payment_failure_notifs,
        }

    # Update bid status
    new_remaining = quantity_needed - total_filled
    if new_remaining <= 0:
        cursor.execute('''
            UPDATE bids
            SET remaining_quantity = 0,
                active = 0,
                status = 'Filled'
            WHERE id = ?
        ''', (bid_id,))
        message = f'Bid fully filled! Matched {total_filled} items from {orders_created} seller(s).'
    else:
        cursor.execute('''
            UPDATE bids
            SET remaining_quantity = ?,
                status = 'Partially Filled'
            WHERE id = ?
        ''', (new_remaining, bid_id))
        message = f'Bid partially filled! Matched {total_filled} of {quantity_needed} items from {orders_created} seller(s). {new_remaining} items still open.'

        for notif in notifications_to_send:
            notif['is_partial'] = True
            notif['remaining_quantity'] = new_remaining

    return {
        'filled_quantity': total_filled,
        'orders_created': orders_created,
        'message': message,
        'notifications': notifications_to_send,
        'ledger_orders': ledger_orders,
    }


def auto_match_listing_to_bids(listing_id, cursor):
    """
    Automatically match a listing to existing bids.
    Called immediately after listing creation to auto-fill if possible.

    This is the reverse of auto_match_bid_to_listings - when a new listing
    is created, check if any existing bids can be filled by this listing.

    Args:
        listing_id: The ID of the newly created listing
        cursor: Database cursor (assumes transaction is already open)

    Returns:
        dict with 'filled_quantity', 'orders_created', 'message', 'notifications'
    """
    # Load the listing with all fields including extra category specs for random_year matching.
    listing = cursor.execute('''
        SELECT l.*, c.metal, c.weight, c.product_type, c.bucket_id,
               c.product_line, c.purity, c.mint, c.finish
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.id = ?
    ''', (listing_id,)).fetchone()

    if not listing or listing['quantity'] <= 0:
        return {'filled_quantity': 0, 'orders_created': 0, 'message': 'No quantity available', 'notifications': []}

    category_id = listing['category_id']
    seller_id = listing['seller_id']
    quantity_available = listing['quantity']

    # Fetch spot prices from spot_price_snapshots (canonical source).
    spot_prices = _get_spot_prices_from_cursor(cursor)

    # Calculate effective listing price
    listing_dict = dict(listing)
    effective_listing_price = get_effective_price(listing_dict, spot_prices=spot_prices)

    # Query active bids: exact category match OR random_year=1 bids whose category
    # shares the same specs (metal, product_line, product_type, weight, purity, mint, finish)
    # as this listing's category, regardless of year.
    listing_metal = listing_dict.get('metal')
    listing_product_line = listing_dict.get('product_line')
    listing_product_type = listing_dict.get('product_type')
    listing_weight = listing_dict.get('weight')
    listing_purity = listing_dict.get('purity')
    listing_mint = listing_dict.get('mint')
    listing_finish = listing_dict.get('finish')

    bids = cursor.execute('''
        SELECT b.*, c.metal, c.weight, c.product_type
        FROM bids b
        JOIN categories c ON b.category_id = c.id
        WHERE b.buyer_id != ?
          AND b.active = 1
          AND b.remaining_quantity > 0
          AND (
            b.category_id = ?
            OR (
              b.random_year = 1
              AND c.metal IS ?
              AND c.product_line IS ?
              AND c.product_type IS ?
              AND c.weight IS ?
              AND c.purity IS ?
              AND c.mint IS ?
              AND c.finish IS ?
            )
          )
        ORDER BY b.created_at ASC
    ''', (
        seller_id, category_id,
        listing_metal, listing_product_line, listing_product_type,
        listing_weight, listing_purity, listing_mint, listing_finish
    )).fetchall()

    if not bids:
        return {'filled_quantity': 0, 'orders_created': 0, 'message': 'No matching bids found', 'notifications': []}

    # Get item description for notifications
    item_desc_parts = []
    if listing_dict.get('metal'):
        item_desc_parts.append(listing_dict['metal'])
    if listing_dict.get('product_type'):
        item_desc_parts.append(listing_dict['product_type'])
    if listing_dict.get('weight'):
        item_desc_parts.append(str(listing_dict['weight']))
    item_description = ' '.join(item_desc_parts) if item_desc_parts else 'Item'

    # Match bids that can fill this listing
    matched_bids = []
    for bid in bids:
        bid_dict = dict(bid)

        # Check if bid can fill this listing
        pricing_info = can_bid_fill_listing(bid_dict, listing_dict, spot_prices=spot_prices)

        if pricing_info['can_fill']:
            bid_dict['bid_effective_price'] = pricing_info['bid_effective_price']
            bid_dict['listing_effective_price'] = pricing_info['listing_effective_price']
            bid_dict['spread'] = pricing_info['spread']
            matched_bids.append(bid_dict)

    if not matched_bids:
        return {'filled_quantity': 0, 'orders_created': 0, 'message': 'No matching bids (bid price < listing price)', 'notifications': []}

    # Sort by bid effective price (highest paying bid first)
    matched_bids.sort(key=lambda x: (-x['bid_effective_price'], x['id']))

    # Fill bids with listing inventory
    orders_created = 0
    total_filled = 0
    remaining_inventory = quantity_available
    notifications_to_send = []
    ledger_orders = []  # Collected for ledger creation after caller commits
    payment_failure_notifs = []

    for bid in matched_bids:
        if remaining_inventory <= 0:
            break

        bid_id = bid['id']
        buyer_id = bid['buyer_id']
        bid_remaining = bid['remaining_quantity']
        delivery_address = bid['delivery_address']
        recipient_first_name = bid.get('recipient_first_name', '')
        recipient_last_name = bid.get('recipient_last_name', '')
        bid_pm_id = bid.get('bid_payment_method_id')

        # Determine PM type (card vs ACH) — needed for fee calc + PI creation.
        _l2b_pm_type = 'card'
        _l2b_is_ach = False
        if bid_pm_id:
            try:
                _pm_obj = stripe.PaymentMethod.retrieve(bid_pm_id)
                _l2b_pm_type = _pm_obj.type
                _l2b_is_ach = (_l2b_pm_type == 'us_bank_account')
            except stripe.error.StripeError as e:
                logger.warning('[auto_match L2B] Could not check PM type for %s: %s — assuming card',
                               bid_pm_id, e)

        # Determine fill quantity
        fill_qty = min(remaining_inventory, bid_remaining)

        # Calculate prices using spread model
        buyer_price_each = bid['bid_effective_price']
        seller_price_each = bid['listing_effective_price']

        # ── Compute full charge: subtotal → tax → card fee → total ──────────
        _subtotal       = round(fill_qty * buyer_price_each, 2)
        _subtotal_cents = int(round(_subtotal * 100))
        _postal, _state = _parse_address_for_tax(delivery_address)
        _tax_cents      = _get_stripe_tax_for_bid(_subtotal_cents, _postal, _state)
        _tax_amount     = round(_tax_cents / 100, 2)
        _taxed_subtotal = _subtotal + _tax_amount
        # Card payments: 2.99% + $0.30. ACH: no card processing fee.
        _bid_card_fee   = 0.0 if _l2b_is_ach else round(_taxed_subtotal * _CARD_RATE + _CARD_FLAT, 2)
        total_price     = round(_taxed_subtotal + _bid_card_fee, 2)
        _effective_tax_rate = round(_tax_amount / _subtotal, 6) if _subtotal else 0.0

        logger.info(
            '[auto_match L2B] bid=%s listing=%s subtotal=%.2f tax=%.2f card_fee=%.2f total=%.2f postal=%r',
            bid_id, listing_id, _subtotal, _tax_amount, _bid_card_fee, total_price, _postal,
        )

        # Load buyer's Stripe customer ID for off-session charge
        try:
            buyer_row = cursor.execute(
                'SELECT stripe_customer_id FROM users WHERE id = ?', (buyer_id,)
            ).fetchone()
            buyer_customer_id = buyer_row['stripe_customer_id'] if buyer_row else None
        except Exception:
            buyer_customer_id = None

        # SAVEPOINT: all DB mutations for this bid are atomic with the payment.
        sp_name = f'sp_l2b_{bid_id}'
        cursor.execute(f'SAVEPOINT {sp_name}')

        # Decrement listing inventory inside the savepoint so a payment failure
        # rolls back the inventory change atomically.
        new_listing_qty = remaining_inventory - fill_qty
        if new_listing_qty <= 0:
            cursor.execute(
                'UPDATE listings SET quantity = 0, active = 0 WHERE id = ?', (listing_id,)
            )
        else:
            cursor.execute(
                'UPDATE listings SET quantity = ? WHERE id = ?', (new_listing_qty, listing_id)
            )

        # Create order with full financial breakdown
        cursor.execute('''
            INSERT INTO orders (buyer_id, total_price, buyer_card_fee, tax_amount, tax_rate,
                               shipping_address, status, created_at,
                               recipient_first_name, recipient_last_name, payment_status,
                               source_bid_id)
            VALUES (?, ?, ?, ?, ?, ?, 'Pending Shipment', datetime('now'), ?, ?, 'unpaid', ?)
        ''', (buyer_id, total_price, _bid_card_fee, _tax_amount, _effective_tax_rate,
              delivery_address, recipient_first_name, recipient_last_name, bid_id))

        order_id = cursor.lastrowid

        # Create order item with both prices
        cursor.execute('''
            INSERT INTO order_items (order_id, listing_id, quantity, price_each, seller_price_each)
            VALUES (?, ?, ?, ?, ?)
        ''', (order_id, listing_id, fill_qty, buyer_price_each, seller_price_each))

        # ── Attempt payment ─────────────────────────────────────────────────
        if bid_pm_id and buyer_customer_id:
            pay_result = _charge_bid_payment(
                bid_id=bid_id, order_id=order_id, buyer_id=buyer_id,
                pm_id=bid_pm_id, customer_id=buyer_customer_id,
                amount_dollars=total_price,
                pm_type=_l2b_pm_type,
            )

            if not pay_result['success']:
                # Roll back all DB work for this bid (restores inventory + removes order/items)
                cursor.execute(f'ROLLBACK TO SAVEPOINT {sp_name}')
                cursor.execute(f'RELEASE SAVEPOINT {sp_name}')

                cursor.execute('''
                    UPDATE bids
                       SET bid_payment_status = 'failed',
                           bid_payment_failure_code = ?,
                           bid_payment_failure_message = ?,
                           bid_payment_attempted_at = datetime('now'),
                           active = 0,
                           status = 'Payment Failed'
                     WHERE id = ?
                ''', (pay_result.get('code'), pay_result.get('message'), bid_id))

                if pay_result.get('is_card_decline'):
                    cursor.execute('''
                        UPDATE users
                           SET bid_payment_strikes = COALESCE(bid_payment_strikes, 0) + 1
                         WHERE id = ?
                    ''', (buyer_id,))

                payment_failure_notifs.append({
                    'buyer_id': buyer_id,
                    'bid_id': bid_id,
                    'failure_message': pay_result.get('message', 'Payment declined.'),
                })
                continue  # Skip to next bid; don't decrement remaining_inventory

            # Payment succeeded — stamp order with payment info
            _l2b_paid_pm_type = pay_result.get('pm_type', 'card')
            cursor.execute('''
                UPDATE orders
                   SET stripe_payment_intent_id = ?,
                       payment_status = 'paid',
                       status = 'paid',
                       paid_at = datetime('now'),
                       payment_method_type = ?
                 WHERE id = ?
            ''', (pay_result['pi_id'], _l2b_paid_pm_type, order_id))

            cursor.execute('''
                UPDATE bids
                   SET bid_payment_status = 'charged',
                       bid_payment_intent_id = ?,
                       bid_payment_attempted_at = datetime('now')
                 WHERE id = ?
            ''', (pay_result['pi_id'], bid_id))
        else:
            logger.warning(
                '[auto_match L2B] bid=%s has no payment method — order %s created as unpaid',
                bid_id, order_id,
            )

        cursor.execute(f'RELEASE SAVEPOINT {sp_name}')
        orders_created += 1
        remaining_inventory -= fill_qty
        total_filled += fill_qty

        # Update bid remaining quantity
        new_bid_remaining = bid_remaining - fill_qty
        if new_bid_remaining <= 0:
            cursor.execute('''
                UPDATE bids SET remaining_quantity = 0, active = 0, status = 'Filled' WHERE id = ?
            ''', (bid_id,))
        else:
            cursor.execute('''
                UPDATE bids SET remaining_quantity = ?, status = 'Partially Filled' WHERE id = ?
            ''', (new_bid_remaining, bid_id))

        # Use subtotal (not total_price) for per-unit display in notifications.
        avg_price_per_unit = _subtotal / fill_qty if fill_qty > 0 else buyer_price_each
        notifications_to_send.append({
            'buyer_id': buyer_id,
            'order_id': order_id,
            'bid_id': bid_id,
            'item_description': item_description,
            'quantity_filled': fill_qty,
            'price_per_unit': avg_price_per_unit,
            'total_amount': total_price,
            'is_partial': new_bid_remaining > 0,
            'remaining_quantity': new_bid_remaining if new_bid_remaining > 0 else 0
        })

        # Build ledger snapshot (seller_price_each = basis for proceeds display in sold tab)
        ledger_orders.append({
            'buyer_id': buyer_id,
            'order_id': order_id,
            'items': [{
                'seller_id': seller_id,
                'listing_id': listing_id,
                'quantity': fill_qty,
                'unit_price': seller_price_each,
                'buyer_unit_price': buyer_price_each,
            }],
        })

    message = f'Listing auto-filled! Matched {total_filled} items to {orders_created} bid(s).'
    if remaining_inventory > 0:
        message += f' {remaining_inventory} items still available.'

    return {
        'filled_quantity': total_filled,
        'orders_created': orders_created,
        'message': message,
        'notifications': notifications_to_send,
        'ledger_orders': ledger_orders,
        'payment_failure_notifs': payment_failure_notifs,
    }


def check_all_pending_matches(conn):
    """
    Check all active bids against all active listings for potential matches.
    Called on page load to catch matches that became possible due to spot price changes.

    Args:
        conn: Database connection (will create its own cursor)

    Returns:
        dict with 'total_filled', 'orders_created', 'bids_matched'
    """
    cursor = conn.cursor()

    total_filled = 0
    orders_created = 0
    bids_matched = 0
    notifications_to_send = []
    all_ledger_orders = []

    # Get all active bids with remaining quantity
    active_bids = cursor.execute('''
        SELECT b.id, b.category_id, b.buyer_id, b.random_year
        FROM bids b
        WHERE b.active = 1
          AND b.remaining_quantity > 0
          AND b.status IN ('Open', 'Partially Filled')
        ORDER BY b.created_at ASC
    ''').fetchall()

    if not active_bids:
        return {'total_filled': 0, 'orders_created': 0, 'bids_matched': 0, 'notifications': []}

    for bid_row in active_bids:
        bid_id = bid_row['id']

        # Pre-check: skip bids that have no potential listings to save work.
        # For random_year=1 bids, matching listings may be in a DIFFERENT category
        # (same specs, different year), so we skip the pre-check for those bids and
        # let auto_match_bid_to_listings handle the cross-year lookup.
        if not bid_row['random_year']:
            potential_listings = cursor.execute('''
                SELECT 1 FROM listings l
                WHERE l.category_id = ?
                  AND l.seller_id != ?
                  AND l.active = 1
                  AND l.quantity > 0
                LIMIT 1
            ''', (bid_row['category_id'], bid_row['buyer_id'])).fetchone()

            if not potential_listings:
                continue

        # Try to match this bid
        result = auto_match_bid_to_listings(bid_id, cursor)

        if result.get('payment_failure_notifs'):
            # Payment failed — bid is already marked closed; send buyer notification after commit
            notifications_to_send.extend([
                {'type': 'payment_failed', **n} for n in result['payment_failure_notifs']
            ])
        elif result['filled_quantity'] > 0:
            total_filled += result['filled_quantity']
            orders_created += result['orders_created']
            bids_matched += 1
            if result.get('notifications'):
                notifications_to_send.extend(result['notifications'])
            if result.get('ledger_orders'):
                all_ledger_orders.extend(result['ledger_orders'])

    # Commit all changes
    conn.commit()

    # Send payment failure notifications (after commit so bid status is persisted)
    for notif in notifications_to_send:
        if notif.get('type') == 'payment_failed':
            try:
                notify_bid_payment_failed(notif['buyer_id'], notif['bid_id'], notif['failure_message'])
            except Exception as _ne:
                logger.warning('[auto_match] Failed to send payment failure notification: %s', _ne)

    # Create ledger entries AFTER commit (ledger service opens its own connection).
    # This locks in the correct bucket fee at execution time so seller proceeds
    # remain accurate even if admin changes the bucket fee later.
    for _ledger in all_ledger_orders:
        try:
            create_order_ledger_from_cart(
                buyer_id=_ledger['buyer_id'],
                cart_snapshot=_ledger['items'],
                order_id=_ledger['order_id'],
            )
        except Exception as _ledger_err:
            logger.warning(
                "[auto_match] Ledger creation failed for order %s: %s",
                _ledger['order_id'], _ledger_err
            )

    return {
        'total_filled': total_filled,
        'orders_created': orders_created,
        'bids_matched': bids_matched,
        'notifications': [n for n in notifications_to_send if n.get('type') != 'payment_failed'],
    }


def run_bid_rematch_after_spot_update(metals=None):
    """
    Re-evaluate all active bids after a spot price update.

    Opens its own DB connection, runs check_all_pending_matches(), then closes.
    Safe to call synchronously from both the scheduler and manual-insert paths.

    A module-level lock prevents two concurrent calls (e.g. scheduler tick +
    manual admin spot insert arriving within the same second) from both
    processing the same bids and producing duplicate orders.

    Args:
        metals: Optional list of metal names that were updated (for logging only).

    Returns:
        dict: {total_filled, orders_created, bids_matched, notifications}
    """
    if not _rematch_lock.acquire(blocking=False):
        logger.info(
            "[bid_rematch] Skipping — another rematch is already in progress (metals=%s)", metals
        )
        return {'total_filled': 0, 'orders_created': 0, 'bids_matched': 0, 'notifications': []}

    import database as _db_module
    try:
        conn = _db_module.get_db_connection()
        try:
            result = check_all_pending_matches(conn)
            if result.get('bids_matched', 0) > 0:
                logger.info(
                    "[bid_rematch] %d bid(s) matched, %d order(s) created "
                    "after spot update (metals=%s)",
                    result['bids_matched'], result['orders_created'], metals,
                )
            return result
        finally:
            conn.close()
    except Exception as exc:
        logger.error("[bid_rematch] Failed after spot update (metals=%s): %s", metals, exc)
        return {'total_filled': 0, 'orders_created': 0, 'bids_matched': 0, 'notifications': []}
    finally:
        _rematch_lock.release()
