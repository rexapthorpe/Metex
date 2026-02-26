from database import get_db_connection
from config import GRADING_FEE_PER_UNIT


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
    conn = get_db_connection()
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

        cursor.execute('''
            INSERT INTO order_items (order_id, listing_id, quantity, price_each,
                                     third_party_grading_requested, grading_fee_charged,
                                     grading_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (order_id, item['listing_id'], item['quantity'], item['price_each'],
              tpg_requested, grading_fee_charged, grading_status))

    conn.commit()
    conn.close()

    return order_id
