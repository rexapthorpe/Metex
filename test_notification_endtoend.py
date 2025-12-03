"""
END-TO-END NOTIFICATION TEST
Simulates the complete order creation flow to test notifications
"""
from database import get_db_connection
from services.notification_service import notify_listing_sold, notify_bid_filled, get_user_notifications
import traceback

print("="*80)
print("END-TO-END NOTIFICATION FLOW TEST")
print("="*80)

# Setup: Create test users, listings, and orders
conn = get_db_connection()
cursor = conn.cursor()

print("\n[SETUP] Creating test data...")
print("-"*80)

# Clean up any previous test data
cursor.execute("DELETE FROM notifications WHERE user_id IN (9990, 9991)")
cursor.execute("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE buyer_id = 9991)")
cursor.execute("DELETE FROM orders WHERE buyer_id = 9991")
cursor.execute("DELETE FROM listings WHERE seller_id = 9990")
cursor.execute("DELETE FROM users WHERE id IN (9990, 9991)")
conn.commit()

# Create test seller
cursor.execute("""
    INSERT INTO users (id, username, email, password_hash, first_name, last_name)
    VALUES (9990, 'test_endtoend_seller', 'seller_e2e@test.com', 'hash', 'End', 'Seller')
""")

# Create test buyer
cursor.execute("""
    INSERT INTO users (id, username, email, password_hash, first_name, last_name)
    VALUES (9991, 'test_endtoend_buyer', 'buyer_e2e@test.com', 'hash', 'End', 'Buyer')
""")

# Get a real category ID
category = cursor.execute("SELECT id, metal, product_type, weight, year FROM categories LIMIT 1").fetchone()
if not category:
    print("[ERROR] No categories found in database. Cannot create test listing.")
    conn.close()
    exit(1)

category_id = category['id']
print(f"Using category ID {category_id}: {category['metal']} {category['product_type']}")

# Create test listing
cursor.execute("""
    INSERT INTO listings (seller_id, category_id, quantity, price_per_coin, active)
    VALUES (9990, ?, 100, 35.50, 1)
""", (category_id,))
listing_id = cursor.lastrowid

print(f"Created test listing ID {listing_id} for seller 9990")

# Create test order
cursor.execute("""
    INSERT INTO orders (buyer_id, total_price, shipping_address, status, created_at)
    VALUES (9991, 355.00, '123 Test St, Test City, TS 12345', 'Pending Shipment', datetime('now'))
""")
order_id = cursor.lastrowid

print(f"Created test order ID {order_id} for buyer 9991")

# Create order item
cursor.execute("""
    INSERT INTO order_items (order_id, listing_id, quantity, price_each)
    VALUES (?, ?, 10, 35.50)
""", (order_id, listing_id))

conn.commit()
print("[OK] Test data created\n")

# TEST 1: Simulate notification call like in checkout_routes.py
print("="*80)
print("TEST 1: Simulating checkout_routes.py notification flow")
print("="*80)

try:
    # Get listing info (like checkout does)
    listing_info = cursor.execute('''
        SELECT listings.quantity, listings.seller_id, listings.category_id,
               categories.metal, categories.product_type
        FROM listings
        JOIN categories ON listings.category_id = categories.id
        WHERE listings.id = ?
    ''', (listing_id,)).fetchone()

    if listing_info:
        print(f"[INFO] Found listing info:")
        print(f"       Seller ID: {listing_info['seller_id']}")
        print(f"       Metal: {listing_info['metal']}")
        print(f"       Product Type: {listing_info['product_type']}")

        # Build item description (like checkout does)
        item_description = f"{listing_info['metal']} {listing_info['product_type']}"
        print(f"       Item Description: '{item_description}'")

        # Call notify_listing_sold (exactly like checkout does)
        print("\n[ACTION] Calling notify_listing_sold()...")
        result = notify_listing_sold(
            seller_id=listing_info['seller_id'],
            order_id=order_id,
            listing_id=listing_id,
            item_description=item_description,
            quantity_sold=10,
            price_per_unit=35.50,
            total_amount=355.00,
            shipping_address="123 Test St, Test City, TS 12345",
            is_partial=True,
            remaining_quantity=90
        )

        if result:
            print("[PASS] notify_listing_sold() returned True")
        else:
            print("[FAIL] notify_listing_sold() returned False")

    else:
        print("[ERROR] Could not find listing info")

except Exception as e:
    print(f"[FAIL] Exception occurred: {e}")
    traceback.print_exc()

# TEST 2: Check if notification was created
print("\n" + "="*80)
print("TEST 2: Verifying notification was created in database")
print("="*80)

notifs = cursor.execute(
    "SELECT * FROM notifications WHERE user_id = 9990 AND type = 'listing_sold'"
).fetchall()

if notifs:
    print(f"[PASS] Found {len(notifs)} listing_sold notification(s)")
    for notif in notifs:
        print(f"       ID {notif['id']}: {notif['title']}")
        print(f"       Message: {notif['message'][:100]}...")
else:
    print("[FAIL] NO listing_sold notifications found!")

# TEST 3: Test bid filled notification (simulating sell_routes.py)
print("\n" + "="*80)
print("TEST 3: Simulating sell_routes.py bid filled notification")
print("="*80)

try:
    # Create a fake bid
    cursor.execute("""
        INSERT INTO bids (user_id, category_id, price_per_coin, quantity, status)
        VALUES (9991, ?, 36.00, 20, 'filled')
    """, (category_id,))
    bid_id = cursor.lastrowid
    conn.commit()

    print(f"[INFO] Created test bid ID {bid_id}")

    # Build item description
    item_desc_parts = []
    if category['metal']:
        item_desc_parts.append(category['metal'])
    if category['weight']:
        item_desc_parts.append(category['weight'])
    if category['year']:
        item_desc_parts.append(str(category['year']))
    item_description = ' '.join(item_desc_parts) if item_desc_parts else 'Item'

    print(f"[INFO] Item Description: '{item_description}'")

    # Call notify_bid_filled
    print("\n[ACTION] Calling notify_bid_filled()...")
    result = notify_bid_filled(
        buyer_id=9991,
        order_id=order_id,
        bid_id=bid_id,
        item_description=item_description,
        quantity_filled=20,
        price_per_unit=36.00,
        total_amount=720.00,
        is_partial=False,
        remaining_quantity=0
    )

    if result:
        print("[PASS] notify_bid_filled() returned True")
    else:
        print("[FAIL] notify_bid_filled() returned False")

except Exception as e:
    print(f"[FAIL] Exception occurred: {e}")
    traceback.print_exc()

# TEST 4: Verify bid filled notification
print("\n" + "="*80)
print("TEST 4: Verifying bid_filled notification was created")
print("="*80)

notifs = cursor.execute(
    "SELECT * FROM notifications WHERE user_id = 9991 AND type = 'bid_filled'"
).fetchall()

if notifs:
    print(f"[PASS] Found {len(notifs)} bid_filled notification(s)")
    for notif in notifs:
        print(f"       ID {notif['id']}: {notif['title']}")
else:
    print("[FAIL] NO bid_filled notifications found!")

# FINAL CHECK: Get all notifications for both users
print("\n" + "="*80)
print("FINAL CHECK: All notifications for test users")
print("="*80)

seller_notifs = get_user_notifications(9990)
buyer_notifs = get_user_notifications(9991)

print(f"\nSeller (9990) notifications: {len(seller_notifs)}")
for n in seller_notifs:
    print(f"  - {n['type']}: {n['title']}")

print(f"\nBuyer (9991) notifications: {len(buyer_notifs)}")
for n in buyer_notifs:
    print(f"  - {n['type']}: {n['title']}")

# Summary
print("\n" + "="*80)
print("SUMMARY")
print("="*80)

if len(seller_notifs) > 0 and len(buyer_notifs) > 0:
    print("[SUCCESS] All tests passed! Notifications are working correctly.")
    print("          The notification system is functioning as expected.")
    print("\nNext steps:")
    print("  1. Check if you're actually placing orders in the live app")
    print("  2. Check server logs for any '[NOTIFICATION]' messages")
    print("  3. Verify you're logged in as the correct user to see notifications")
else:
    print("[FAILURE] Some notifications were not created.")
    print("          This indicates an issue with the notification system.")

# Cleanup
print("\n[CLEANUP] Removing test data...")
cursor.execute("DELETE FROM notifications WHERE user_id IN (9990, 9991)")
cursor.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
cursor.execute("DELETE FROM orders WHERE id = ?", (order_id,))
cursor.execute("DELETE FROM bids WHERE user_id = 9991")
cursor.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
cursor.execute("DELETE FROM users WHERE id IN (9990, 9991)")
conn.commit()
conn.close()

print("[OK] Cleanup complete")
print("="*80)
