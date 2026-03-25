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
                        pm_id: str, customer_id: str, amount_dollars: float) -> dict:
    """
    Create and confirm a Stripe PaymentIntent off-session for a bid auto-fill.

    Returns:
        {'success': True, 'pi_id': 'pi_xxx'}
        {'success': False, 'code': '...', 'message': '...', 'is_card_decline': bool}
    """
    try:
        pi = stripe.PaymentIntent.create(
            amount=max(1, round(amount_dollars * 100)),
            currency='usd',
            customer=customer_id,
            payment_method=pm_id,
            confirm=True,
            off_session=True,
            metadata={
                'user_id': str(buyer_id),
                'order_id': str(order_id),
                'bid_id': str(bid_id),
                'source': 'bid_auto_fill',
            },
            idempotency_key=f'bid-autofill-{bid_id}-{order_id}',
        )
        if pi.status == 'succeeded':
            return {'success': True, 'pi_id': pi.id}
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

        fill_total = sum(f['fill_qty'] * f['buyer_price_each'] for f in fills)
        fill_qty_total = sum(f['fill_qty'] for f in fills)

        # Create order as unpaid initially
        cursor.execute('''
            INSERT INTO orders (buyer_id, total_price, shipping_address, status, created_at,
                               recipient_first_name, recipient_last_name, payment_status, source_bid_id)
            VALUES (?, ?, ?, 'Pending Shipment', datetime('now'), ?, ?, 'unpaid', ?)
        ''', (buyer_id, fill_total, delivery_address, recipient_first_name, recipient_last_name, bid_id))
        order_id = cursor.lastrowid

        for fill in fills:
            cursor.execute('''
                INSERT INTO order_items (order_id, listing_id, quantity, price_each, seller_price_each)
                VALUES (?, ?, ?, ?, ?)
            ''', (order_id, fill['listing']['id'], fill['fill_qty'],
                  fill['buyer_price_each'], fill['seller_price_each']))

        # Charge buyer's saved card
        if bid_pm_id and buyer_customer_id:
            pay_result = _charge_bid_payment(
                bid_id=bid_id, order_id=order_id, buyer_id=buyer_id,
                pm_id=bid_pm_id, customer_id=buyer_customer_id,
                amount_dollars=fill_total,
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
            cursor.execute('''
                UPDATE orders
                   SET stripe_payment_intent_id = ?,
                       payment_status = 'paid',
                       status = 'paid',
                       paid_at = datetime('now'),
                       payment_method_type = 'card'
                 WHERE id = ?
            ''', (pay_result['pi_id'], order_id))

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

        avg_price = fill_total / fill_qty_total if fill_qty_total > 0 else effective_bid_price
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

    for bid in matched_bids:
        if remaining_inventory <= 0:
            break

        bid_id = bid['id']
        buyer_id = bid['buyer_id']
        bid_remaining = bid['remaining_quantity']
        delivery_address = bid['delivery_address']
        recipient_first_name = bid.get('recipient_first_name', '')
        recipient_last_name = bid.get('recipient_last_name', '')

        # Determine fill quantity
        fill_qty = min(remaining_inventory, bid_remaining)

        # Calculate prices using spread model
        buyer_price_each = bid['bid_effective_price']
        seller_price_each = bid['listing_effective_price']
        total_price = buyer_price_each * fill_qty

        # Create order
        cursor.execute('''
            INSERT INTO orders (buyer_id, total_price, shipping_address, status, created_at,
                               recipient_first_name, recipient_last_name, source_bid_id)
            VALUES (?, ?, ?, 'Pending Shipment', datetime('now'), ?, ?, ?)
        ''', (buyer_id, total_price, delivery_address, recipient_first_name, recipient_last_name, bid_id))

        order_id = cursor.lastrowid
        orders_created += 1

        # Create order item with both prices
        cursor.execute('''
            INSERT INTO order_items (order_id, listing_id, quantity, price_each, seller_price_each)
            VALUES (?, ?, ?, ?, ?)
        ''', (order_id, listing_id, fill_qty, buyer_price_each, seller_price_each))

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

        # Collect notification data for buyer
        notifications_to_send.append({
            'buyer_id': buyer_id,
            'order_id': order_id,
            'bid_id': bid_id,
            'item_description': item_description,
            'quantity_filled': fill_qty,
            'price_per_unit': buyer_price_each,
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
            }],
        })

        remaining_inventory -= fill_qty
        total_filled += fill_qty

    # Update listing quantity
    if remaining_inventory <= 0:
        cursor.execute('UPDATE listings SET quantity = 0, active = 0 WHERE id = ?', (listing_id,))
    else:
        cursor.execute('UPDATE listings SET quantity = ? WHERE id = ?', (remaining_inventory, listing_id))

    message = f'Listing auto-filled! Matched {total_filled} items to {orders_created} bid(s).'
    if remaining_inventory > 0:
        message += f' {remaining_inventory} items still available.'

    return {
        'filled_quantity': total_filled,
        'orders_created': orders_created,
        'message': message,
        'notifications': notifications_to_send,
        'ledger_orders': ledger_orders,
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
