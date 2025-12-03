"""
Comprehensive Notification System Test
Tests all notification creation pathways to find the issue
"""

import sys
from database import get_db_connection
from services.notification_service import (
    create_notification,
    notify_listing_sold,
    notify_bid_filled,
    get_user_notifications,
    get_unread_count
)

print("=" * 80)
print("COMPREHENSIVE NOTIFICATION SYSTEM TEST")
print("=" * 80)

# First, check if notifications table exists
conn = get_db_connection()
cursor = conn.cursor()
table_exists = cursor.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='notifications'"
).fetchone()

if not table_exists:
    print("[CRITICAL ERROR] Notifications table does not exist!")
    print("Run migration 004 to create it.")
    sys.exit(1)

print("[OK] Notifications table exists\n")

# Clean up any existing test notifications
cursor.execute("DELETE FROM notifications WHERE user_id IN (999, 1000)")
conn.commit()

# Get or create test users
print("Setting up test users...")
print("-" * 80)

# Create test users if they don't exist
cursor.execute("SELECT id, username, email FROM users WHERE id = 999")
seller = cursor.fetchone()
if not seller:
    cursor.execute("""
        INSERT INTO users (id, username, email, password_hash, first_name, last_name)
        VALUES (999, 'test_seller', 'seller@test.com', 'hash', 'Test', 'Seller')
    """)
    print("Created test seller (ID 999)")
    conn.commit()
    seller = cursor.execute("SELECT id, username, email FROM users WHERE id = 999").fetchone()
else:
    print(f"Using existing seller: {seller['username']} (ID {seller['id']})")

cursor.execute("SELECT id, username, email FROM users WHERE id = 1000")
buyer = cursor.fetchone()
if not buyer:
    cursor.execute("""
        INSERT INTO users (id, username, email, password_hash, first_name, last_name)
        VALUES (1000, 'test_buyer', 'buyer@test.com', 'hash', 'Test', 'Buyer')
    """)
    print("Created test buyer (ID 1000)")
    conn.commit()
    buyer = cursor.execute("SELECT id, username, email FROM users WHERE id = 1000").fetchone()
else:
    print(f"Using existing buyer: {buyer['username']} (ID {buyer['id']})")

conn.close()

# TEST 1: Basic notification creation
print("\n" + "=" * 80)
print("TEST 1: create_notification() function")
print("=" * 80)

try:
    notif_id = create_notification(
        user_id=999,
        notification_type='test',
        title='Test Notification',
        message='This is a test notification',
        metadata={'test': True}
    )

    if notif_id:
        print(f"[PASS] Notification created with ID: {notif_id}")

        # Verify it's in the database
        conn = get_db_connection()
        notif = conn.execute(
            "SELECT * FROM notifications WHERE id = ?", (notif_id,)
        ).fetchone()
        conn.close()

        if notif:
            print(f"[PASS] Notification found in database")
            print(f"       User ID: {notif['user_id']}")
            print(f"       Type: {notif['type']}")
            print(f"       Title: {notif['title']}")
        else:
            print(f"[FAIL] Notification NOT found in database!")
    else:
        print(f"[FAIL] create_notification() returned None")

except Exception as e:
    print(f"[FAIL] Exception occurred: {e}")
    import traceback
    traceback.print_exc()

# TEST 2: notify_listing_sold()
print("\n" + "=" * 80)
print("TEST 2: notify_listing_sold() function")
print("=" * 80)

try:
    result = notify_listing_sold(
        seller_id=999,
        order_id=99999,  # Fake order ID
        listing_id=88888,  # Fake listing ID
        item_description="1 oz 2024 Silver Eagle",
        quantity_sold=10,
        price_per_unit=32.50,
        total_amount=325.00,
        shipping_address="123 Main St, Brooklyn, NY 12345",
        is_partial=False,
        remaining_quantity=0
    )

    if result:
        print(f"[PASS] notify_listing_sold() returned True")

        # Check database
        conn = get_db_connection()
        notifs = conn.execute(
            "SELECT * FROM notifications WHERE user_id = ? AND type = 'listing_sold'",
            (999,)
        ).fetchall()
        conn.close()

        if notifs:
            print(f"[PASS] Found {len(notifs)} listing_sold notification(s) in database")
            for notif in notifs:
                print(f"       ID {notif['id']}: {notif['title']}")
        else:
            print(f"[FAIL] NO listing_sold notifications found in database!")
    else:
        print(f"[FAIL] notify_listing_sold() returned False")

except Exception as e:
    print(f"[FAIL] Exception occurred: {e}")
    import traceback
    traceback.print_exc()

# TEST 3: notify_bid_filled()
print("\n" + "=" * 80)
print("TEST 3: notify_bid_filled() function")
print("=" * 80)

try:
    result = notify_bid_filled(
        buyer_id=1000,
        order_id=99998,  # Fake order ID
        bid_id=77777,  # Fake bid ID
        item_description="1 oz 2023 Gold Eagle",
        quantity_filled=5,
        price_per_unit=2050.00,
        total_amount=10250.00,
        is_partial=False,
        remaining_quantity=0
    )

    if result:
        print(f"[PASS] notify_bid_filled() returned True")

        # Check database
        conn = get_db_connection()
        notifs = conn.execute(
            "SELECT * FROM notifications WHERE user_id = ? AND type = 'bid_filled'",
            (1000,)
        ).fetchall()
        conn.close()

        if notifs:
            print(f"[PASS] Found {len(notifs)} bid_filled notification(s) in database")
            for notif in notifs:
                print(f"       ID {notif['id']}: {notif['title']}")
        else:
            print(f"[FAIL] NO bid_filled notifications found in database!")
    else:
        print(f"[FAIL] notify_bid_filled() returned False")

except Exception as e:
    print(f"[FAIL] Exception occurred: {e}")
    import traceback
    traceback.print_exc()

# TEST 4: get_user_notifications()
print("\n" + "=" * 80)
print("TEST 4: get_user_notifications() function")
print("=" * 80)

try:
    seller_notifs = get_user_notifications(999)
    buyer_notifs = get_user_notifications(1000)

    print(f"Seller (ID 999) notifications: {len(seller_notifs)}")
    for notif in seller_notifs:
        print(f"  - {notif['type']}: {notif['title']}")

    print(f"\nBuyer (ID 1000) notifications: {len(buyer_notifs)}")
    for notif in buyer_notifs:
        print(f"  - {notif['type']}: {notif['title']}")

    if len(seller_notifs) > 0 and len(buyer_notifs) > 0:
        print(f"\n[PASS] get_user_notifications() works correctly")
    else:
        print(f"\n[FAIL] Expected notifications not found")

except Exception as e:
    print(f"[FAIL] Exception occurred: {e}")
    import traceback
    traceback.print_exc()

# TEST 5: get_unread_count()
print("\n" + "=" * 80)
print("TEST 5: get_unread_count() function")
print("=" * 80)

try:
    seller_unread = get_unread_count(999)
    buyer_unread = get_unread_count(1000)

    print(f"Seller (ID 999) unread count: {seller_unread}")
    print(f"Buyer (ID 1000) unread count: {buyer_unread}")

    if seller_unread > 0 and buyer_unread > 0:
        print(f"[PASS] get_unread_count() works correctly")
    else:
        print(f"[WARNING] Expected unread notifications but count is 0")

except Exception as e:
    print(f"[FAIL] Exception occurred: {e}")
    import traceback
    traceback.print_exc()

# FINAL SUMMARY
print("\n" + "=" * 80)
print("FINAL DATABASE CHECK")
print("=" * 80)

conn = get_db_connection()
all_notifs = conn.execute("SELECT * FROM notifications ORDER BY created_at DESC LIMIT 10").fetchall()
total_count = conn.execute("SELECT COUNT(*) as count FROM notifications").fetchone()['count']
conn.close()

print(f"Total notifications in database: {total_count}")
print(f"\nMost recent 10 notifications:")
print("-" * 80)
for notif in all_notifs:
    print(f"ID {notif['id']}: User {notif['user_id']} - {notif['type']} - {notif['title']}")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)

# Cleanup test data
print("\nCleaning up test notifications...")
conn = get_db_connection()
conn.execute("DELETE FROM notifications WHERE user_id IN (999, 1000)")
conn.commit()
conn.close()
print("Test data cleaned up")
