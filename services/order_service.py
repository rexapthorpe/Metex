import database as _db_module
from config import GRADING_FEE_PER_UNIT


def _get_conn():
    return _db_module.get_db_connection()


def calculate_cart_total(cart_items):
    """Calculate item-only total (excludes grading fees)."""
    total = 0
    for item in cart_items:
        total += item['price_each'] * item['quantity']
    return round(total, 2)


def _item_requires_grading(item):
    """Return True if this cart item has 3rd-party grading requested.

    Uses only the canonical boolean field `requires_grading`.
    grading_preference is a derived text artifact and must not drive this decision.
    """
    return bool(item.get('requires_grading'))


def create_order(buyer_id, cart_items, shipping_address, recipient_first='', recipient_last=''):
    """
    Create a new order and related order items.

    Each item in cart_items must have: listing_id, quantity, price_each.
    Optionally: requires_grading (bool) or grading_preference (str 'ANY'/'NONE').

    Grading fee (GRADING_FEE_PER_UNIT × qty) is added per item and included
    in orders.total_price.  grading_fee_charged is written to each order_item.
    """
    conn = _get_conn()
    cursor = conn.cursor()

    items_total = calculate_cart_total(cart_items)
    grading_total = round(sum(
        GRADING_FEE_PER_UNIT * item['quantity']
        for item in cart_items
        if _item_requires_grading(item)
    ), 2)
    total_price = round(items_total + grading_total, 2)

    cursor.execute('''
        INSERT INTO orders (buyer_id, total_price, shipping_address, recipient_first_name, recipient_last_name)
        VALUES (?, ?, ?, ?, ?)
    ''', (buyer_id, total_price, shipping_address, recipient_first, recipient_last))

    order_id = cursor.lastrowid

    for item in cart_items:
        requires_grading = _item_requires_grading(item)
        tpg_requested = 1 if requires_grading else 0
        grading_fee_charged = round(GRADING_FEE_PER_UNIT * item['quantity'], 2) if requires_grading else 0.0
        grading_status = 'requested' if requires_grading else 'not_requested'

        # Spot audit fields (populated when checkout_spot_service was used)
        spot_info = item.get('spot_info')  # {price_usd, as_of, source} or None
        spot_price_at_purchase = spot_info['price_usd'] if spot_info else None
        spot_as_of_used = spot_info['as_of'] if spot_info else None
        spot_source_used = spot_info['source'] if spot_info else None
        pricing_mode_at_purchase = item.get('pricing_mode_used')
        spot_premium_used = item.get('spot_premium_used')
        weight_used = item.get('weight_used')

        cursor.execute('''
            INSERT INTO order_items (order_id, listing_id, quantity, price_each,
                                     third_party_grading_requested, grading_fee_charged,
                                     grading_status,
                                     spot_price_at_purchase, spot_as_of_used,
                                     spot_source_used, pricing_mode_at_purchase,
                                     spot_premium_used, weight_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (order_id, item['listing_id'], item['quantity'], item['price_each'],
              tpg_requested, grading_fee_charged, grading_status,
              spot_price_at_purchase, spot_as_of_used,
              spot_source_used, pricing_mode_at_purchase,
              spot_premium_used, weight_used))

    conn.commit()
    conn.close()

    return order_id
