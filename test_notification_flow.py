"""
Test the complete notification flow
Simulates purchases and bid fills to test notification creation
"""
import sqlite3
from services.notification_service import notify_listing_sold, notify_bid_filled, get_user_notifications

print("=" * 80)
print("NOTIFICATION FLOW TEST")
print("=" * 80)

# Connect to database
conn = sqlite3.connect('database.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Step 1: Get or create test users
print("\n[STEP 1] Setting up test users...")
cursor.execute("SELECT id, username FROM users LIMIT 2")
users = cursor.fetchall()

if len(users) < 2:
    print("❌ ERROR: Need at least 2 users in database for testing")
    conn.close()
    exit(1)

buyer_id = users[0]['id']
seller_id = users[1]['id']
print(f"[OK] Buyer: User #{buyer_id} ({users[0]['username']})")
print(f"[OK] Seller: User #{seller_id} ({users[1]['username']})")

# Step 2: Create a test order
print("\n[STEP 2] Creating test order...")
cursor.execute('''
    INSERT INTO orders (
        buyer_id, seller_id, quantity,
        price_each, status, delivery_address, created_at
    ) VALUES (?, ?, 10, 25.50, 'Pending Shipment', '123 Test St', datetime('now'))
''', (buyer_id, seller_id))

order_id = cursor.lastrowid
conn.commit()
print(f"[OK] Created order #{order_id}")

# Step 3: Test notify_listing_sold
print("\n[STEP 3] Testing notify_listing_sold...")
try:
    result = notify_listing_sold(
        seller_id=seller_id,
        order_id=order_id,
        listing_id=999,
        item_description="2023 American Gold Eagle 1 oz",
        quantity_sold=10,
        price_per_unit=25.50,
        total_amount=255.00,
        shipping_address="123 Test St",
        is_partial=False,
        remaining_quantity=0
    )

    if result:
        print("[OK] notify_listing_sold returned True")
    else:
        print("[ERROR] notify_listing_sold returned False")
except Exception as e:
    print(f"[ERROR] ERROR in notify_listing_sold: {e}")
    import traceback
    traceback.print_exc()

# Step 4: Test notify_bid_filled
print("\n[STEP 4] Testing notify_bid_filled...")
try:
    result = notify_bid_filled(
        buyer_id=buyer_id,
        order_id=order_id,
        bid_id=888,
        item_description="2023 American Gold Eagle 1 oz",
        quantity_filled=10,
        price_per_unit=25.50,
        total_amount=255.00,
        is_partial=False,
        remaining_quantity=0
    )

    if result:
        print("[OK] notify_bid_filled returned True")
    else:
        print("[ERROR] notify_bid_filled returned False")
except Exception as e:
    print(f"[ERROR] ERROR in notify_bid_filled: {e}")
    import traceback
    traceback.print_exc()

# Step 5: Check if notifications were created
print("\n[STEP 5] Checking database for notifications...")
cursor.execute("SELECT * FROM notifications ORDER BY created_at DESC LIMIT 10")
notifications = cursor.fetchall()

print(f"\nTotal notifications in database: {len(notifications)}")

if notifications:
    print("\nRecent notifications:")
    print("-" * 80)
    for notif in notifications:
        print(f"  ID: {notif['id']}")
        print(f"  User: #{notif['user_id']}")
        print(f"  Type: {notif['type']}")
        print(f"  Title: {notif['title']}")
        print(f"  Created: {notif['created_at']}")
        print(f"  Read: {'Yes' if notif['is_read'] else 'No'}")
        print("-" * 80)
else:
    print("[ERROR] NO NOTIFICATIONS FOUND IN DATABASE!")

# Step 6: Check seller's notifications using service function
print("\n[STEP 6] Getting seller's notifications via service...")
try:
    seller_notifs = get_user_notifications(seller_id)
    print(f"Seller has {len(seller_notifs)} notification(s)")
    for notif in seller_notifs:
        print(f"  - {notif['title']}")
except Exception as e:
    print(f"[ERROR] ERROR getting seller notifications: {e}")

# Step 7: Check buyer's notifications using service function
print("\n[STEP 7] Getting buyer's notifications via service...")
try:
    buyer_notifs = get_user_notifications(buyer_id)
    print(f"Buyer has {len(buyer_notifs)} notification(s)")
    for notif in buyer_notifs:
        print(f"  - {notif['title']}")
except Exception as e:
    print(f"[ERROR] ERROR getting buyer notifications: {e}")

# Cleanup: Delete test order and notifications
print("\n[CLEANUP] Removing test data...")
cursor.execute("DELETE FROM orders WHERE id = ?", (order_id,))
cursor.execute("DELETE FROM notifications WHERE related_order_id = ?", (order_id,))
conn.commit()
conn.close()

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
