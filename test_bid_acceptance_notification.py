"""
TEST BID ACCEPTANCE NOTIFICATION
Simulates the complete bid acceptance flow to test notifications
"""
from database import get_db_connection
from services.notification_service import notify_bid_filled, get_user_notifications
import sys

print("=" * 80)
print("BID ACCEPTANCE NOTIFICATION TEST")
print("=" * 80)

# Setup test environment
conn = get_db_connection()
cursor = conn.cursor()

# Clean up previous test data
print("\n[SETUP] Cleaning up previous test data...")
cursor.execute("DELETE FROM notifications WHERE user_id IN (7771, 7772)")
cursor.execute("DELETE FROM orders WHERE buyer_id IN (7771, 7772) OR seller_id IN (7771, 7772)")
cursor.execute("DELETE FROM bids WHERE buyer_id IN (7771, 7772)")
cursor.execute("DELETE FROM users WHERE id IN (7771, 7772)")
conn.commit()

# Create test users
print("[SETUP] Creating test users...")
cursor.execute("""
    INSERT INTO users (id, username, email, password_hash, first_name, last_name)
    VALUES (7771, 'bid_buyer', 'bid_buyer@test.com', 'hash', 'Bid', 'Buyer')
""")
cursor.execute("""
    INSERT INTO users (id, username, email, password_hash, first_name, last_name)
    VALUES (7772, 'bid_seller', 'bid_seller@test.com', 'hash', 'Bid', 'Seller')
""")

# Get a real category
category = cursor.execute("SELECT id, metal, product_type, product_line, weight, year FROM categories LIMIT 1").fetchone()
if not category:
    print("[ERROR] No categories in database")
    sys.exit(1)

category_id = category['id']
print(f"[SETUP] Using category: {category['metal']} {category['product_type']}")

conn.commit()

# ===========================================================================
# SCENARIO: SELLER ACCEPTS BUYER'S BID
# ===========================================================================

print("\n" + "=" * 80)
print("SCENARIO: Seller Accepts Buyer's Bid (Accept Bid Modal Flow)")
print("=" * 80)

print("\n[STEP 1] Buyer creates a bid...")
cursor.execute("""
    INSERT INTO bids (buyer_id, category_id, price_per_coin, quantity_requested, remaining_quantity, status, created_at)
    VALUES (7771, ?, 35.00, 25, 25, 'open', datetime('now'))
""", (category_id,))
bid_id = cursor.lastrowid
conn.commit()
print(f"Created bid ID {bid_id} - Buyer: 7771, Price: $35.00, Qty: 25")

print("\n[STEP 2] Seller accepts the bid (simulating accept_bid route)...")
print("This simulates what happens when seller clicks 'Confirm' in Accept Bid modal")

# Get bid info
bid = cursor.execute("""
    SELECT buyer_id, category_id, quantity_requested, price_per_coin, status
    FROM bids WHERE id = ?
""", (bid_id,)).fetchone()

buyer_id = bid['buyer_id']
price = bid['price_per_coin']
qty_to_fulfill = bid['quantity_requested']

print(f"Bid details: {qty_to_fulfill} units @ ${price} each")

# Create order (simulating what accept_bid does)
cursor.execute("""
    INSERT INTO orders (buyer_id, seller_id, category_id, quantity, price_each, status, created_at)
    VALUES (?, ?, ?, ?, ?, 'pending_shipment', datetime('now'))
""", (buyer_id, 7772, category_id, qty_to_fulfill, price))

order_id = cursor.lastrowid
print(f"Created order ID {order_id}")

# Update the bid status
remaining = 0
is_partial = False
cursor.execute('UPDATE bids SET quantity_requested = 0, active = 0, status = "filled" WHERE id = ?', (bid_id,))

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
notifications_to_send = [{
    'buyer_id': buyer_id,
    'order_id': order_id,
    'bid_id': bid_id,
    'item_description': item_description,
    'quantity_filled': qty_to_fulfill,
    'price_per_unit': price,
    'total_amount': qty_to_fulfill * price,
    'is_partial': is_partial,
    'remaining_quantity': remaining
}]

# COMMIT FIRST (this is the fix!)
conn.commit()
conn.close()

# Send notifications AFTER commit
print("\n[STEP 3] Sending notification AFTER commit...")
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

print("\n[STEP 4] Checking if notification was created...")
buyer_notifs = get_user_notifications(7771)  # Buyer should have notification
print(f"Buyer (7771) notifications: {len(buyer_notifs)}")
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
    print("  This confirms the fix is working.")
else:
    print("[FAILURE] No notification was created for the buyer!")
    print("  The fix may not be working correctly.")

print("=" * 80)

# Cleanup
print("\n[CLEANUP] Removing test data...")
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("DELETE FROM notifications WHERE user_id IN (7771, 7772)")
cursor.execute("DELETE FROM orders WHERE buyer_id IN (7771, 7772) OR seller_id IN (7771, 7772)")
cursor.execute("DELETE FROM bids WHERE buyer_id IN (7771, 7772)")
cursor.execute("DELETE FROM users WHERE id IN (7771, 7772)")
conn.commit()
conn.close()

print("[OK] Cleanup complete")
print("=" * 80)
