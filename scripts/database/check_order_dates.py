"""Check order purchase dates"""
from database import get_db_connection
from datetime import datetime

conn = get_db_connection()

# Get orders for user 4
orders = conn.execute("""
    SELECT o.id, o.buyer_id, o.created_at, oi.order_item_id, oi.quantity, oi.price_each
    FROM orders o
    JOIN order_items oi ON o.id = oi.order_id
    WHERE o.buyer_id = 4
    ORDER BY o.created_at DESC
""").fetchall()

print("Orders for user 4:")
print("=" * 70)
for order in orders:
    created_at = order['created_at']
    print(f"Order {order['id']}, Item {order['order_item_id']}")
    print(f"  Created: {created_at}")
    print(f"  Quantity: {order['quantity']}, Price: ${order['price_each']}")

    # Parse the datetime
    created_dt = datetime.fromisoformat(created_at)
    now = datetime.now()
    days_ago = (now - created_dt).days
    print(f"  Days ago: {days_ago}")
    print()

conn.close()
