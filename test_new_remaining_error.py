"""
TEST NEW_REMAINING UNBOUNDLOCALERROR
Reproduces the UnboundLocalError where new_remaining is used before it's defined
"""
from database import get_db_connection
import sys

print("=" * 80)
print("NEW_REMAINING UNBOUNDLOCALERROR TEST")
print("Reproducing the variable scoping issue")
print("=" * 80)

# Clean up test data
print("\n[SETUP] Cleaning up previous test data...")
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("DELETE FROM notifications WHERE user_id IN (8881, 8882)")
cursor.execute("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE buyer_id IN (8881, 8882))")
cursor.execute("DELETE FROM orders WHERE buyer_id IN (8881, 8882) OR seller_id IN (8881, 8882)")
cursor.execute("DELETE FROM listings WHERE seller_id IN (8881, 8882)")
cursor.execute("DELETE FROM bids WHERE buyer_id IN (8881, 8882)")
cursor.execute("DELETE FROM users WHERE id IN (8881, 8882)")
conn.commit()

# Create test users
print("[SETUP] Creating test users...")
cursor.execute("""
    INSERT INTO users (id, username, email, password_hash, first_name, last_name)
    VALUES (8881, 'error_buyer', 'error_buyer@test.com', 'hash', 'Error', 'Buyer')
""")
cursor.execute("""
    INSERT INTO users (id, username, email, password_hash, first_name, last_name)
    VALUES (8882, 'error_seller', 'error_seller@test.com', 'hash', 'Error', 'Seller')
""")

# Get a category
category = cursor.execute("SELECT id FROM categories LIMIT 1").fetchone()
if not category:
    print("[ERROR] No categories in database")
    sys.exit(1)

category_id = category['id']
conn.commit()

print("\n[STEP 1] Creating a bid...")
cursor.execute("""
    INSERT INTO bids (buyer_id, category_id, price_per_coin, quantity_requested, remaining_quantity, status, created_at)
    VALUES (8881, ?, 65.00, 40, 40, 'open', datetime('now'))
""", (category_id,))
bid_id = cursor.lastrowid
conn.commit()
print(f"Created bid ID {bid_id}")

print("\n[STEP 2] Creating seller listings...")
cursor.execute("""
    INSERT INTO listings (seller_id, category_id, quantity, price_per_coin, active)
    VALUES (8882, ?, 100, 62.00, 1)
""", (category_id,))
listing_id = cursor.lastrowid
conn.commit()
print(f"Created listing ID {listing_id}")

print("\n[STEP 3] Simulating accept_bid logic (REPRODUCING THE ERROR)...")

try:
    # This simulates the problematic code path in bid_routes.py

    # Variables from the route
    seller_id = 8882

    # Get bid
    bid = cursor.execute("""
        SELECT buyer_id, category_id, price_per_coin, remaining_quantity
        FROM bids WHERE id = ?
    """, (bid_id,)).fetchone()

    buyer_id = bid['buyer_id']
    price_limit = bid['price_per_coin']
    remaining_qty = bid['remaining_quantity']

    # Get listings
    listings = cursor.execute("""
        SELECT id, quantity, price_per_coin
        FROM listings
        WHERE category_id = ?
          AND seller_id = ?
          AND active = 1
          AND price_per_coin <= ?
        ORDER BY price_per_coin ASC
    """, (category_id, seller_id, price_limit)).fetchall()

    filled = 0
    order_items_to_create = []

    # Fill from listings
    for listing in listings:
        available = listing['quantity']
        to_fill = min(remaining_qty - filled, available)

        if to_fill > 0:
            order_items_to_create.append({
                'listing_id': listing['id'],
                'quantity': to_fill,
                'price_each': price_limit
            })
            filled += to_fill

    # THIS IS WHERE THE ERROR OCCURS
    if filled > 0 and order_items_to_create:
        total_price = sum(item['quantity'] * item['price_each'] for item in order_items_to_create)

        # Create order
        cursor.execute("""
            INSERT INTO orders (buyer_id, seller_id, total_price, status, created_at)
            VALUES (?, ?, ?, 'Pending Shipment', datetime('now'))
        """, (buyer_id, seller_id, total_price))

        order_id = cursor.lastrowid

        # Create order items
        for item in order_items_to_create:
            cursor.execute("""
                INSERT INTO order_items (order_id, listing_id, quantity, price_each)
                VALUES (?, ?, ?, ?)
            """, (order_id, item['listing_id'], item['quantity'], item['price_each']))

        print(f"Created order {order_id} with {filled} units")

        # THIS LINE CAUSES THE ERROR - new_remaining is not defined yet!
        print(f"\n[ERROR POINT] Trying to access new_remaining before it's defined...")
        try:
            notification_data = {
                'buyer_id': buyer_id,
                'order_id': order_id,
                'bid_id': bid_id,
                'item_description': 'Test Item',
                'quantity_filled': filled,
                'price_per_unit': price_limit,
                'total_amount': total_price,
                'is_partial': new_remaining > 0,  # ERROR: new_remaining not defined!
                'remaining_quantity': new_remaining  # ERROR: new_remaining not defined!
            }
            print("[UNEXPECTED] No error occurred - new_remaining was somehow defined")
        except UnboundLocalError as e:
            print(f"[EXPECTED ERROR] UnboundLocalError caught: {e}")
            print("This is the exact error users are experiencing!")

        # new_remaining is only defined AFTER the notification block
        new_remaining = remaining_qty - filled
        print(f"\n[INFO] new_remaining is defined here: {new_remaining}")

    conn.rollback()

except Exception as e:
    print(f"\n[ERROR] Exception during simulation: {e}")
    import traceback
    traceback.print_exc()
    conn.rollback()

print("\n" + "=" * 80)
print("DIAGNOSIS")
print("=" * 80)
print("\nThe error occurs because:")
print("  1. Notification data is collected inside 'if filled > 0' block (line 498)")
print("  2. Notification data references 'new_remaining' (line 506)")
print("  3. BUT new_remaining is not defined until AFTER the block (line 513)")
print("\nThis causes UnboundLocalError when the notification data is created.")
print("\nFIX: Move the calculation of new_remaining to BEFORE the notification")
print("     data collection (before line 498).")
print("=" * 80)

# Cleanup
cursor.execute("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE buyer_id = 8881)")
cursor.execute("DELETE FROM orders WHERE buyer_id = 8881 OR seller_id = 8882")
cursor.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
cursor.execute("DELETE FROM bids WHERE id = ?", (bid_id,))
cursor.execute("DELETE FROM users WHERE id IN (8881, 8882)")
conn.commit()
conn.close()

print("\n[CLEANUP] Test data removed")
print("=" * 80)
