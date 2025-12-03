"""
Comprehensive end-to-end test of the notification system
Tests database, service layer, and notification triggers
"""

from database import get_db_connection
from services.notification_service import (
    create_notification,
    notify_bid_filled,
    notify_listing_sold,
    get_user_notifications,
    get_unread_count,
    mark_notification_read,
    delete_notification
)
import json

def test_notification_system():
    """Test the complete notification system end-to-end"""
    print("\n" + "="*70)
    print("NOTIFICATION SYSTEM - END-TO-END TEST")
    print("="*70 + "\n")

    conn = get_db_connection()
    cursor = conn.cursor()

    # ========================================================================
    # TEST 1: Verify database table exists
    # ========================================================================
    print("TEST 1: Database Table Verification")
    print("-" * 70)

    table_check = cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='notifications'
    """).fetchone()

    if table_check:
        print("[PASS] Notifications table exists")

        # Check columns
        columns = cursor.execute("PRAGMA table_info(notifications)").fetchall()
        column_names = [col['name'] for col in columns]
        required_columns = ['id', 'user_id', 'type', 'title', 'message',
                          'is_read', 'related_order_id', 'related_bid_id',
                          'related_listing_id', 'metadata', 'created_at', 'read_at']

        missing = [col for col in required_columns if col not in column_names]
        if not missing:
            print("[PASS] All required columns present")
        else:
            print(f"[FAIL] Missing columns: {missing}")
            return False
    else:
        print("[FAIL] Notifications table does not exist")
        return False

    # ========================================================================
    # TEST 2: Create test users and data
    # ========================================================================
    print("\n" + "="*70)
    print("TEST 2: Setup Test Data")
    print("-" * 70)

    # Clean up any previous test data
    cursor.execute('DELETE FROM notifications WHERE user_id >= 8000 AND user_id <= 8002')
    cursor.execute('DELETE FROM users WHERE id >= 8000 AND id <= 8002')
    conn.commit()

    # Create test users
    test_buyer_id = 8000
    test_seller1_id = 8001
    test_seller2_id = 8002

    cursor.execute("""
        INSERT INTO users (id, username, password_hash, email)
        VALUES (?, ?, ?, ?)
    """, (test_buyer_id, 'test_buyer_notif', 'hash', 'buyer_notif@test.com'))

    cursor.execute("""
        INSERT INTO users (id, username, password_hash, email)
        VALUES (?, ?, ?, ?)
    """, (test_seller1_id, 'test_seller1_notif', 'hash', 'seller1_notif@test.com'))

    cursor.execute("""
        INSERT INTO users (id, username, password_hash, email)
        VALUES (?, ?, ?, ?)
    """, (test_seller2_id, 'test_seller2_notif', 'hash', 'seller2_notif@test.com'))

    conn.commit()
    print("[PASS] Test users created")

    # ========================================================================
    # TEST 3: Test notification service - create notification
    # ========================================================================
    print("\n" + "="*70)
    print("TEST 3: Create Notification")
    print("-" * 70)

    metadata = {
        'quantity': 10,
        'price': 25.50,
        'item': 'Silver Eagle'
    }

    notif_id = create_notification(
        user_id=test_buyer_id,
        notification_type='bid_filled',
        title='Bid Filled!',
        message='Your bid for 10 Silver Eagles has been filled',
        related_order_id=1001,
        related_bid_id=2001,
        metadata=metadata
    )

    if notif_id:
        print(f"[PASS] Notification created with ID: {notif_id}")

        # Verify it was saved correctly
        saved = cursor.execute(
            "SELECT * FROM notifications WHERE id = ?",
            (notif_id,)
        ).fetchone()

        if saved:
            print(f"  - User ID: {saved['user_id']}")
            print(f"  - Type: {saved['type']}")
            print(f"  - Title: {saved['title']}")
            print(f"  - Message: {saved['message']}")
            print(f"  - Is Read: {saved['is_read']}")

            # Parse metadata
            if saved['metadata']:
                parsed_meta = json.loads(saved['metadata'])
                print(f"  - Metadata: {parsed_meta}")

            print("[PASS] Notification saved correctly")
        else:
            print("[FAIL] Notification not found in database")
            return False
    else:
        print("[FAIL] Failed to create notification")
        return False

    # ========================================================================
    # TEST 4: Test get_user_notifications
    # ========================================================================
    print("\n" + "="*70)
    print("TEST 4: Get User Notifications")
    print("-" * 70)

    notifications = get_user_notifications(test_buyer_id)

    if notifications and len(notifications) >= 1:
        print(f"[PASS] Retrieved {len(notifications)} notification(s)")

        notif = notifications[0]
        print(f"  - Title: {notif['title']}")
        print(f"  - Message: {notif['message']}")
        print(f"  - Is Read: {notif['is_read']}")

        if 'metadata' in notif and notif['metadata']:
            print(f"  - Metadata: {notif['metadata']}")
    else:
        print("[FAIL] No notifications retrieved")
        return False

    # ========================================================================
    # TEST 5: Test get_unread_count
    # ========================================================================
    print("\n" + "="*70)
    print("TEST 5: Get Unread Count")
    print("-" * 70)

    unread_count = get_unread_count(test_buyer_id)

    if unread_count >= 1:
        print(f"[PASS] Unread count: {unread_count}")
    else:
        print(f"[FAIL] Expected unread count >= 1, got {unread_count}")
        return False

    # ========================================================================
    # TEST 6: Test mark_notification_read
    # ========================================================================
    print("\n" + "="*70)
    print("TEST 6: Mark Notification as Read")
    print("-" * 70)

    result = mark_notification_read(notif_id)

    if result:
        print("[PASS] Notification marked as read")

        # Verify it was updated
        updated = cursor.execute(
            "SELECT is_read, read_at FROM notifications WHERE id = ?",
            (notif_id,)
        ).fetchone()

        if updated and updated['is_read'] == 1 and updated['read_at']:
            print(f"  - Is Read: {updated['is_read']}")
            print(f"  - Read At: {updated['read_at']}")
            print("[PASS] Read status updated correctly")
        else:
            print("[FAIL] Read status not updated")
            return False

        # Check unread count decreased
        new_unread_count = get_unread_count(test_buyer_id)
        if new_unread_count == unread_count - 1:
            print(f"[PASS] Unread count decreased to {new_unread_count}")
        else:
            print(f"[FAIL] Unread count should be {unread_count - 1}, got {new_unread_count}")
            return False
    else:
        print("[FAIL] Failed to mark notification as read")
        return False

    # ========================================================================
    # TEST 7: Test notify_bid_filled (complete flow)
    # ========================================================================
    print("\n" + "="*70)
    print("TEST 7: Notify Bid Filled (Complete Flow)")
    print("-" * 70)

    try:
        # Note: This will try to send email, which may fail if email not configured
        # That's okay - we're testing the notification creation part
        bid_notif_id = notify_bid_filled(
            buyer_id=test_buyer_id,
            order_id=1002,
            bid_id=2002,
            item_description="2024 Silver Libertad 1oz",
            quantity_filled=5,
            price_per_unit=28.00,
            total_amount=140.00,
            is_partial=True,
            remaining_quantity=5
        )

        if bid_notif_id:
            print(f"[PASS] Bid filled notification created (ID: {bid_notif_id})")

            # Verify the notification
            bid_notif = cursor.execute(
                "SELECT * FROM notifications WHERE id = ?",
                (bid_notif_id,)
            ).fetchone()

            if bid_notif:
                print(f"  - Title: {bid_notif['title']}")
                print(f"  - Type: {bid_notif['type']}")
                print(f"  - Related Order: {bid_notif['related_order_id']}")
                print(f"  - Related Bid: {bid_notif['related_bid_id']}")

                if bid_notif['metadata']:
                    meta = json.loads(bid_notif['metadata'])
                    print(f"  - Quantity Filled: {meta.get('quantity_filled')}")
                    print(f"  - Total Amount: ${meta.get('total_amount')}")
                    print(f"  - Is Partial: {meta.get('is_partial')}")

                print("[PASS] Bid filled notification verified")
        else:
            print("[FAIL] Bid filled notification not created")
            return False
    except Exception as e:
        # Email sending might fail, but notification should still be created
        print(f"[INFO] Email sending may have failed (expected if not configured): {e}")

        # Check if notification was still created
        bid_notif = cursor.execute("""
            SELECT * FROM notifications
            WHERE user_id = ? AND type = 'bid_filled' AND related_order_id = 1002
        """, (test_buyer_id,)).fetchone()

        if bid_notif:
            print("[PASS] Notification created despite email error (acceptable)")
        else:
            print("[FAIL] Notification not created")
            return False

    # ========================================================================
    # TEST 8: Test notify_listing_sold (complete flow)
    # ========================================================================
    print("\n" + "="*70)
    print("TEST 8: Notify Listing Sold (Complete Flow)")
    print("-" * 70)

    try:
        listing_notif_id = notify_listing_sold(
            seller_id=test_seller1_id,
            order_id=1003,
            listing_id=3001,
            item_description="2023 Gold Eagle 1oz",
            quantity_sold=2,
            price_per_unit=2100.00,
            total_amount=4200.00,
            shipping_address="123 Test St, Test City, TS 12345",
            is_partial=False,
            remaining_quantity=0
        )

        if listing_notif_id:
            print(f"[PASS] Listing sold notification created (ID: {listing_notif_id})")

            # Verify the notification
            listing_notif = cursor.execute(
                "SELECT * FROM notifications WHERE id = ?",
                (listing_notif_id,)
            ).fetchone()

            if listing_notif:
                print(f"  - Title: {listing_notif['title']}")
                print(f"  - Type: {listing_notif['type']}")
                print(f"  - Related Order: {listing_notif['related_order_id']}")
                print(f"  - Related Listing: {listing_notif['related_listing_id']}")

                if listing_notif['metadata']:
                    meta = json.loads(listing_notif['metadata'])
                    print(f"  - Quantity Sold: {meta.get('quantity_sold')}")
                    print(f"  - Total Amount: ${meta.get('total_amount')}")
                    print(f"  - Shipping Address: {meta.get('shipping_address')}")

                print("[PASS] Listing sold notification verified")
        else:
            print("[FAIL] Listing sold notification not created")
            return False
    except Exception as e:
        print(f"[INFO] Email sending may have failed (expected if not configured): {e}")

        # Check if notification was still created
        listing_notif = cursor.execute("""
            SELECT * FROM notifications
            WHERE user_id = ? AND type = 'listing_sold' AND related_order_id = 1003
        """, (test_seller1_id,)).fetchone()

        if listing_notif:
            print("[PASS] Notification created despite email error (acceptable)")
        else:
            print("[FAIL] Notification not created")
            return False

    # ========================================================================
    # TEST 9: Test delete_notification
    # ========================================================================
    print("\n" + "="*70)
    print("TEST 9: Delete Notification")
    print("-" * 70)

    result = delete_notification(notif_id, test_buyer_id)

    if result:
        print("[PASS] Notification deleted")

        # Verify it was deleted
        deleted = cursor.execute(
            "SELECT * FROM notifications WHERE id = ?",
            (notif_id,)
        ).fetchone()

        if not deleted:
            print("[PASS] Notification removed from database")
        else:
            print("[FAIL] Notification still in database")
            return False
    else:
        print("[FAIL] Failed to delete notification")
        return False

    # ========================================================================
    # TEST 10: Test ownership check in delete
    # ========================================================================
    print("\n" + "="*70)
    print("TEST 10: Delete Notification - Ownership Check")
    print("-" * 70)

    # Try to delete a notification that belongs to another user
    # First create a notification for seller1
    other_notif_id = create_notification(
        user_id=test_seller1_id,
        notification_type='listing_sold',
        title='Test',
        message='Test message'
    )

    # Try to delete it as the buyer (should fail)
    result = delete_notification(other_notif_id, test_buyer_id)

    if not result:
        print("[PASS] Cannot delete other user's notification (correct)")
    else:
        print("[FAIL] Should not be able to delete other user's notification")
        return False

    # ========================================================================
    # CLEANUP
    # ========================================================================
    print("\n" + "="*70)
    print("CLEANUP")
    print("-" * 70)

    cursor.execute('DELETE FROM notifications WHERE user_id >= 8000 AND user_id <= 8002')
    cursor.execute('DELETE FROM users WHERE id >= 8000 AND id <= 8002')
    conn.commit()
    conn.close()

    print("[OK] Test data cleaned up")

    # ========================================================================
    # FINAL RESULTS
    # ========================================================================
    print("\n" + "="*70)
    print("FINAL RESULTS: ALL TESTS PASSED!")
    print("="*70)
    print("\nNotification system verified:")
    print("  [OK] Database table structure correct")
    print("  [OK] create_notification() works")
    print("  [OK] get_user_notifications() works")
    print("  [OK] get_unread_count() works")
    print("  [OK] mark_notification_read() works")
    print("  [OK] notify_bid_filled() works (creates notification + attempts email)")
    print("  [OK] notify_listing_sold() works (creates notification + attempts email)")
    print("  [OK] delete_notification() works")
    print("  [OK] Ownership checks work correctly")
    print("\nThe notification system is ready for production use!")

    return True

if __name__ == '__main__':
    success = test_notification_system()
    exit(0 if success else 1)
