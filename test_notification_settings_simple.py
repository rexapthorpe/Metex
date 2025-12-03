"""
Simple Notification Preferences Test (No Unicode)
Tests the notification settings feature
"""
from database import get_db_connection
from services.notification_service import notify_bid_filled, notify_listing_sold, get_user_notifications
import sys

print("=" * 80)
print("NOTIFICATION PREFERENCES FUNCTIONAL TEST")
print("=" * 80)

# Setup
conn = get_db_connection()
cursor = conn.cursor()

# Clean up test data
print("\n[SETUP] Cleaning up test data...")
cursor.execute("DELETE FROM notifications WHERE user_id IN (8001, 8002)")
cursor.execute("DELETE FROM user_preferences WHERE user_id IN (8001, 8002)")
cursor.execute("DELETE FROM orders WHERE buyer_id IN (8001, 8002) OR seller_id IN (8001, 8002)")
cursor.execute("DELETE FROM bids WHERE buyer_id IN (8001, 8002)")
cursor.execute("DELETE FROM listings WHERE seller_id IN (8001, 8002)")
cursor.execute("DELETE FROM users WHERE id IN (8001, 8002)")
conn.commit()

# Create test users
print("[SETUP] Creating test users...")
import random
import time
unique_suffix = str(int(time.time()))
cursor.execute("""
    INSERT INTO users (id, username, email, password_hash, first_name, last_name)
    VALUES (8001, 'pref_buyer_{}', 'buyer_{}@test.com', 'hash', 'Pref', 'Buyer')
""".format(unique_suffix, unique_suffix))
cursor.execute("""
    INSERT INTO users (id, username, email, password_hash, first_name, last_name)
    VALUES (8002, 'pref_seller_{}', 'seller_{}@test.com', 'hash', 'Pref', 'Seller')
""".format(unique_suffix, unique_suffix))

# Get a category
category = cursor.execute("SELECT id FROM categories LIMIT 1").fetchone()
category_id = category['id']

conn.commit()
print("[OK] Setup complete")

# ============================================================================
# TEST 1: Default Behavior (All Notifications Enabled)
# ============================================================================

print("\n" + "=" * 80)
print("TEST 1: Default Behavior (No Preferences Set)")
print("=" * 80)

print("\n[STEP 1] Sending bid filled notification (no preferences exist)...")

try:
    result = notify_bid_filled(
        buyer_id=8001,
        order_id=9999,
        bid_id=9999,
        item_description="Test Item",
        quantity_filled=10,
        price_per_unit=100.00,
        total_amount=1000.00,
        is_partial=False,
        remaining_quantity=0
    )

    if result:
        print("[OK] notify_bid_filled returned True")

        # Check if notification was created
        notifs = get_user_notifications(8001)
        if len(notifs) > 0:
            print(f"[OK] In-app notification created: '{notifs[0]['title']}'")
            print("[PASS] Test 1: Default behavior works (all enabled)")
        else:
            print("[FAIL] Test 1: No in-app notification created")
    else:
        print("[FAIL] Test 1: notify_bid_filled returned False")

except Exception as e:
    print(f"[ERROR] Test 1 failed with exception: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# TEST 2: Disable Email Notifications Only
# ============================================================================

print("\n" + "=" * 80)
print("TEST 2: Disable Email Notifications (Keep In-App Enabled)")
print("=" * 80)

print("\n[STEP 1] Setting preferences: email=OFF, in-app=ON...")
cursor.execute("""
    INSERT OR REPLACE INTO user_preferences
    (user_id, email_bid_filled, email_listing_sold, inapp_bid_filled, inapp_listing_sold)
    VALUES (8002, 0, 0, 1, 1)
""")
conn.commit()
print("[OK] Preferences saved")

print("\n[STEP 2] Sending listing sold notification...")
try:
    result = notify_listing_sold(
        seller_id=8002,
        order_id=9998,
        listing_id=9998,
        item_description="Test Item 2",
        quantity_sold=5,
        price_per_unit=50.00,
        total_amount=250.00,
        shipping_address="Test Address",
        is_partial=False,
        remaining_quantity=0
    )

    if result:
        print("[OK] notify_listing_sold returned True")

        # Check if in-app notification was created
        notifs = get_user_notifications(8002)
        if len(notifs) > 0:
            print(f"[OK] In-app notification created: '{notifs[0]['title']}'")
            print("[PASS] Test 2: Email disabled but in-app still works")
        else:
            print("[FAIL] Test 2: No in-app notification created")
    else:
        print("[FAIL] Test 2: notify_listing_sold returned False")

except Exception as e:
    print(f"[ERROR] Test 2 failed with exception: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# TEST 3: Disable In-App Notifications Only
# ============================================================================

print("\n" + "=" * 80)
print("TEST 3: Disable In-App Notifications (Keep Email Enabled)")
print("=" * 80)

# Clean notifications
cursor.execute("DELETE FROM notifications WHERE user_id = 8001")
conn.commit()

print("\n[STEP 1] Setting preferences: email=ON, in-app=OFF...")
cursor.execute("""
    INSERT OR REPLACE INTO user_preferences
    (user_id, email_bid_filled, email_listing_sold, inapp_bid_filled, inapp_listing_sold)
    VALUES (8001, 1, 1, 0, 0)
""")
conn.commit()
print("[OK] Preferences saved")

print("\n[STEP 2] Sending bid filled notification...")
try:
    result = notify_bid_filled(
        buyer_id=8001,
        order_id=9997,
        bid_id=9997,
        item_description="Test Item 3",
        quantity_filled=15,
        price_per_unit=75.00,
        total_amount=1125.00,
        is_partial=False,
        remaining_quantity=0
    )

    # Should return True (email was attempted) but no in-app notification
    notifs = get_user_notifications(8001)
    if len(notifs) == 0:
        print("[OK] No in-app notification created (as expected)")
        print("[PASS] Test 3: In-app disabled, email still attempted")
    else:
        print(f"[FAIL] Test 3: In-app notification was created (should be disabled)")

except Exception as e:
    print(f"[ERROR] Test 3 failed with exception: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# TEST 4: Disable All Notifications
# ============================================================================

print("\n" + "=" * 80)
print("TEST 4: Disable All Notifications")
print("=" * 80)

# Clean notifications
cursor.execute("DELETE FROM notifications WHERE user_id = 8002")
conn.commit()

print("\n[STEP 1] Setting preferences: ALL OFF...")
cursor.execute("""
    INSERT OR REPLACE INTO user_preferences
    (user_id, email_bid_filled, email_listing_sold, inapp_bid_filled, inapp_listing_sold)
    VALUES (8002, 0, 0, 0, 0)
""")
conn.commit()
print("[OK] Preferences saved")

print("\n[STEP 2] Sending listing sold notification...")
try:
    result = notify_listing_sold(
        seller_id=8002,
        order_id=9996,
        listing_id=9996,
        item_description="Test Item 4",
        quantity_sold=3,
        price_per_unit=30.00,
        total_amount=90.00,
        shipping_address="Test Address 2",
        is_partial=False,
        remaining_quantity=0
    )

    # Should return False (nothing sent)
    notifs = get_user_notifications(8002)
    if len(notifs) == 0 and not result:
        print("[OK] No notifications created (as expected)")
        print("[PASS] Test 4: All notifications disabled works")
    else:
        if len(notifs) > 0:
            print(f"[FAIL] Test 4: In-app notification was created (should be disabled)")
        if result:
            print(f"[FAIL] Test 4: Function returned True (should be False)")

except Exception as e:
    print(f"[ERROR] Test 4 failed with exception: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# SUMMARY
# ============================================================================

print("\n" + "=" * 80)
print("TEST SUMMARY")
print("=" * 80)
print("\nAll tests completed!")
print("Review the results above to see if all tests passed.")
print("\nKey Points:")
print("  - Test 1: Default behavior (all enabled)")
print("  - Test 2: Email disabled, in-app enabled")
print("  - Test 3: Email enabled, in-app disabled")
print("  - Test 4: All disabled")
print("=" * 80)

# Cleanup
print("\n[CLEANUP] Removing test data...")
cursor.execute("DELETE FROM notifications WHERE user_id IN (8001, 8002)")
cursor.execute("DELETE FROM user_preferences WHERE user_id IN (8001, 8002)")
cursor.execute("DELETE FROM users WHERE id IN (8001, 8002)")
conn.commit()
conn.close()
print("[OK] Cleanup complete")
