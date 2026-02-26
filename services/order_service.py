from database import get_db_connection

def calculate_cart_total(cart_items):
    """Calculate total price based on cart items."""
    total = 0
    for item in cart_items:
        total += item['price_each'] * item['quantity']
    return round(total, 2)

def create_order(buyer_id, cart_items, shipping_address, recipient_first='', recipient_last=''):
    """Create a new order and related order items."""
    conn = get_db_connection()
    cursor = conn.cursor()

    total_price = calculate_cart_total(cart_items)

    cursor.execute('''
        INSERT INTO orders (buyer_id, total_price, shipping_address, recipient_first_name, recipient_last_name)
        VALUES (?, ?, ?, ?, ?)
    ''', (buyer_id, total_price, shipping_address, recipient_first, recipient_last))

    order_id = cursor.lastrowid

    for item in cart_items:
        grading_pref = item.get('grading_preference', 'NONE') or 'NONE'
        tpg_requested = 1 if grading_pref not in ('NONE', '', None) else 0
        grading_status = 'requested' if tpg_requested else 'not_requested'
        cursor.execute('''
            INSERT INTO order_items (order_id, listing_id, quantity, price_each,
                                     third_party_grading_requested, grading_service, grading_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (order_id, item['listing_id'], item['quantity'], item['price_each'],
              tpg_requested, grading_pref, grading_status))

    conn.commit()
    conn.close()

    return order_id
