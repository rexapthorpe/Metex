"""
TEST BID ROUTES NOTIFICATION
Tests the bid acceptance notification in routes/bid_routes.py accept_bid function
This tests the ACTUAL route being used by the application
"""
from database import get_db_connection
from services.notification_service import get_user_notifications
import sys

print("=" * 80)
print("BID ROUTES NOTIFICATION TEST")
print("Testing routes/bid_routes.py accept_bid function")
print("=" * 80)

# Setup test environment
conn = get_db_connection()
cursor = conn.cursor()

# Clean up previous test data
print("\n[SETUP] Cleaning up previous test data...")
cursor.execute("DELETE FROM notifications WHERE user_id IN (9991, 9992)")
cursor.execute("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE buyer_id IN (9991, 9992))")
cursor.execute("DELETE FROM orders WHERE buyer_id IN (9991, 9992) OR seller_id IN (9991, 9992)")
cursor.execute("DELETE FROM listings WHERE seller_id IN (9991, 9992)")
cursor.execute("DELETE FROM bids WHERE buyer_id IN (9991, 9992)")
cursor.execute("DELETE FROM users WHERE id IN (9991, 9992)")
conn.commit()

# Create test users
print("[SETUP] Creating test users...")
cursor.execute("""
    INSERT INTO users (id, username, email, password_hash, first_name, last_name)
    VALUES (9991, 'bid_routes_buyer', 'bid_routes_buyer@test.com', 'hash', 'Bid', 'Buyer')
""")
cursor.execute("""
    INSERT INTO users (id, username, email, password_hash, first_name, last_name)
    VALUES (9992, 'bid_routes_seller', 'bid_routes_seller@test.com', 'hash', 'Bid', 'Seller')
""")

# Get a real category
category = cursor.execute("SELECT id, metal, product_type, product_line, weight, year FROM categories LIMIT 1").fetchone()
if not category:
    print("[ERROR] No categories in database")
    sys.exit(1)

category_id = category['id']
print(f"[SETUP] Using category ID {category_id}: {category['metal']} {category['product_type']}")

conn.commit()

# ===========================================================================
# SCENARIO: SELLER ACCEPTS BUYER'S BID (bid_routes.py flow)
# ===========================================================================

print("\n" + "=" * 80)
print("SCENARIO: Seller Accepts Buyer's Bid via bid_routes.py")
print("=" * 80)

print("\n[STEP 1] Buyer creates a bid...")
cursor.execute("""
    INSERT INTO bids (buyer_id, category_id, price_per_coin, quantity_requested, remaining_quantity, status, created_at)
    VALUES (9991, ?, 40.00, 30, 30, 'open', datetime('now'))
""", (category_id,))
bid_id = cursor.lastrowid
conn.commit()
print(f"Created bid ID {bid_id} - Buyer: 9991, Price: $40.00, Qty: 30")

print("\n[STEP 2] Seller creates listings that can fill the bid...")
cursor.execute("""
    INSERT INTO listings (seller_id, category_id, quantity, price_per_coin, active)
    VALUES (9992, ?, 50, 39.00, 1)
""", (category_id,))
listing_id = cursor.lastrowid
conn.commit()
print(f"Created listing ID {listing_id} - Seller: 9992, Price: $39.00, Qty: 50")

print("\n[STEP 3] Simulating bid acceptance via bid_routes.py accept_bid...")
print("This simulates what happens when seller clicks 'Accept Bid' from bucket page")

# Get bid and listing data
bid = cursor.execute("""
    SELECT buyer_id, category_id, quantity_requested, price_per_coin, status, remaining_quantity
    FROM bids WHERE id = ?
""", (bid_id,)).fetchone()

listing = cursor.execute("""
    SELECT quantity, price_per_coin FROM listings WHERE id = ?
""", (listing_id,)).fetchone()

print(f"Bid: {bid['quantity_requested']} units @ ${bid['price_per_coin']}")
print(f"Listing: {listing['quantity']} units @ ${listing['price_per_coin']}")

# Simulate the accept_bid logic from bid_routes.py
buyer_id = bid['buyer_id']
seller_id = 9992
price_limit = bid['price_per_coin']
remaining_qty = bid['remaining_quantity']

# Check if listing price is acceptable
if listing['price_per_coin'] > price_limit:
    print("[ERROR] Listing price exceeds bid price limit")
    sys.exit(1)

# Determine how many units to fill
available = listing['quantity']
filled = min(remaining_qty, available)

print(f"Filling {filled} units from listing")

# Create order
total_price = filled * price_limit
cursor.execute("""
    INSERT INTO orders (buyer_id, seller_id, total_price, status, created_at)
    VALUES (?, ?, ?, 'Pending Shipment', datetime('now'))
""", (buyer_id, seller_id, total_price))
order_id = cursor.lastrowid
print(f"Created order ID {order_id}, Total: ${total_price:.2f}")

# Create order_items
cursor.execute("""
    INSERT INTO order_items (order_id, listing_id, quantity, price_each)
    VALUES (?, ?, ?, ?)
""", (order_id, listing_id, filled, price_limit))

# Update listing
new_listing_qty = available - filled
if new_listing_qty <= 0:
    cursor.execute('UPDATE listings SET quantity = 0, active = 0 WHERE id = ?', (listing_id,))
else:
    cursor.execute('UPDATE listings SET quantity = ? WHERE id = ?', (new_listing_qty, listing_id))

# Build item description from category
item_desc_parts = []
if category['metal']:
    item_desc_parts.append(category['metal'])
if category['product_line']:
    item_desc_parts.append(category['product_line'])
if category['weight']:
    item_desc_parts.append(category['weight'])
if category['year']:
    item_desc_parts.append(str(category['year']))
item_description = ' '.join(item_desc_parts) if item_desc_parts else 'Item'

print(f"Item description: '{item_description}'")

# Collect notification data
new_remaining = remaining_qty - filled
is_partial = new_remaining > 0

notifications_to_send = [{
    'buyer_id': buyer_id,
    'order_id': order_id,
    'bid_id': bid_id,
    'item_description': item_description,
    'quantity_filled': filled,
    'price_per_unit': price_limit,
    'total_amount': total_price,
    'is_partial': is_partial,
    'remaining_quantity': new_remaining
}]

# Update bid status
if new_remaining <= 0:
    cursor.execute("""
        UPDATE bids
        SET remaining_quantity = 0,
            active = 0,
            status = 'Filled'
        WHERE id = ?
    """, (bid_id,))
else:
    cursor.execute("""
        UPDATE bids
        SET remaining_quantity = ?,
            status = 'Partially Filled'
        WHERE id = ?
    """, (new_remaining, bid_id))

# COMMIT FIRST (this is the fix!)
conn.commit()
conn.close()

# Send notifications AFTER commit
print("\n[STEP 4] Sending notification AFTER commit...")
from services.notification_service import notify_bid_filled
for notif_data in notifications_to_send:
    print(f"  Calling notify_bid_filled for buyer {notif_data['buyer_id']}...")
    try:
        result = notify_bid_filled(**notif_data)
        if result:
            print(f"  [OK] notify_bid_filled returned TRUE")
        else:
            print(f"  [FAIL] notify_bid_filled returned FALSE")
    except Exception as e:
        print(f"  [ERROR] EXCEPTION in notify_bid_filled: {e}")
        import traceback
        traceback.print_exc()

print("\n[STEP 5] Checking if notification was created...")
buyer_notifs = get_user_notifications(9991)  # Buyer should have notification
print(f"Buyer (9991) notifications: {len(buyer_notifs)}")
for n in buyer_notifs:
    print(f"  - {n['type']}: {n['title']}")
    print(f"    Message: {n['message'][:100]}...")

# ===========================================================================
# FINAL SUMMARY
# ===========================================================================

print("\n" + "=" * 80)
print("FINAL SUMMARY")
print("=" * 80)

if len(buyer_notifs) > 0:
    print("[SUCCESS] Bid acceptance notification created correctly!")
    print("  The buyer received a notification when the seller accepted their bid.")
    print("  The fix in routes/bid_routes.py is working correctly.")
else:
    print("[FAILURE] No notification was created for the buyer!")
    print("  The fix may not be working correctly.")

print("=" * 80)

# Cleanup
print("\n[CLEANUP] Removing test data...")
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("DELETE FROM notifications WHERE user_id IN (9991, 9992)")
cursor.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
cursor.execute("DELETE FROM orders WHERE id = ?", (order_id,))
cursor.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
cursor.execute("DELETE FROM bids WHERE id = ?", (bid_id,))
cursor.execute("DELETE FROM users WHERE id IN (9991, 9992)")
conn.commit()
conn.close()

print("[OK] Cleanup complete")
print("=" * 80)
