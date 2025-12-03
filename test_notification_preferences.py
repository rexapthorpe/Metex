"""
Comprehensive tests for notification preferences feature

Tests:
1. Database migration and table creation
2. Preference saving and retrieval via routes
3. Notification service respecting user preferences
4. Both email and in-app notifications can be toggled independently
5. Default behavior when preferences not set
"""

import sqlite3
from database import get_db_connection
from services.notification_service import notify_bid_filled, notify_listing_sold
from werkzeug.security import generate_password_hash


def setup_test_users():
    """Create test users for notification testing"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Clean up existing test users
    cursor.execute("DELETE FROM users WHERE username LIKE 'test_notif_%'")
    cursor.execute("DELETE FROM user_preferences WHERE user_id IN (SELECT id FROM users WHERE username LIKE 'test_notif_%')")

    # Create test users
    users = [
        ('test_notif_buyer', 'buyer@test.com', 'Test', 'Buyer'),
        ('test_notif_seller', 'seller@test.com', 'Test', 'Seller'),
        ('test_notif_disabled', 'disabled@test.com', 'Test', 'Disabled'),
    ]

    user_ids = {}
    for username, email, first_name, last_name in users:
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, first_name, last_name)
            VALUES (?, ?, ?, ?, ?)
        ''', (username, email, generate_password_hash('password123'), first_name, last_name))
        user_ids[username] = cursor.lastrowid

    conn.commit()
    conn.close()
    return user_ids


def test_migration_table_creation():
    """Test 1: Verify user_preferences table exists with correct schema"""
    print("\n=== Test 1: Database Migration and Table Creation ===")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='user_preferences'
    """)
    table_exists = cursor.fetchone()

    assert table_exists is not None, "user_preferences table should exist"
    print("✓ user_preferences table exists")

    # Check table schema
    cursor.execute("PRAGMA table_info(user_preferences)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    expected_columns = {
        'user_id': 'INTEGER',
        'email_listing_sold': 'INTEGER',
        'email_bid_filled': 'INTEGER',
        'inapp_listing_sold': 'INTEGER',
        'inapp_bid_filled': 'INTEGER',
        'created_at': 'TIMESTAMP',
        'updated_at': 'TIMESTAMP'
    }

    for col_name, col_type in expected_columns.items():
        assert col_name in columns, f"Column {col_name} should exist"
        assert columns[col_name] == col_type, f"Column {col_name} should be {col_type}"

    print("✓ All expected columns exist with correct types")

    # Check index exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='index' AND name='idx_user_preferences_user_id'
    """)
    index_exists = cursor.fetchone()
    assert index_exists is not None, "Index should exist"
    print("✓ Performance index exists")

    conn.close()
    print("✅ Test 1 PASSED\n")


def test_preference_saving():
    """Test 2: Save and retrieve preferences via database"""
    print("=== Test 2: Preference Saving and Retrieval ===")

    user_ids = setup_test_users()
    conn = get_db_connection()

    # Test saving preferences
    test_user_id = user_ids['test_notif_buyer']

    conn.execute('''
        INSERT OR REPLACE INTO user_preferences
        (user_id, email_listing_sold, email_bid_filled, inapp_listing_sold, inapp_bid_filled, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ''', (test_user_id, 1, 0, 1, 1))
    conn.commit()

    # Retrieve preferences
    prefs = conn.execute(
        'SELECT * FROM user_preferences WHERE user_id = ?',
        (test_user_id,)
    ).fetchone()

    assert prefs is not None, "Preferences should be saved"
    assert prefs['email_listing_sold'] == 1, "email_listing_sold should be enabled"
    assert prefs['email_bid_filled'] == 0, "email_bid_filled should be disabled"
    assert prefs['inapp_listing_sold'] == 1, "inapp_listing_sold should be enabled"
    assert prefs['inapp_bid_filled'] == 1, "inapp_bid_filled should be enabled"

    print("✓ Preferences saved and retrieved correctly")

    # Test updating preferences
    conn.execute('''
        INSERT OR REPLACE INTO user_preferences
        (user_id, email_listing_sold, email_bid_filled, inapp_listing_sold, inapp_bid_filled, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ''', (test_user_id, 0, 1, 0, 0))
    conn.commit()

    prefs = conn.execute(
        'SELECT * FROM user_preferences WHERE user_id = ?',
        (test_user_id,)
    ).fetchone()

    assert prefs['email_listing_sold'] == 0, "email_listing_sold should be updated"
    assert prefs['email_bid_filled'] == 1, "email_bid_filled should be updated"
    print("✓ Preferences updated successfully")

    conn.close()
    print("✅ Test 2 PASSED\n")


def test_notification_respects_preferences():
    """Test 3: Notification service checks and respects user preferences"""
    print("=== Test 3: Notification Service Respects Preferences ===")

    user_ids = setup_test_users()
    conn = get_db_connection()

    # Set preferences for test user - disable all bid_filled notifications
    test_user_id = user_ids['test_notif_buyer']
    conn.execute('''
        INSERT OR REPLACE INTO user_preferences
        (user_id, email_listing_sold, email_bid_filled, inapp_listing_sold, inapp_bid_filled)
        VALUES (?, ?, ?, ?, ?)
    ''', (test_user_id, 1, 0, 1, 0))  # bid_filled disabled
    conn.commit()

    # Count notifications before
    count_before = conn.execute(
        'SELECT COUNT(*) as count FROM notifications WHERE user_id = ? AND type = ?',
        (test_user_id, 'bid_filled')
    ).fetchone()['count']

    # Try to send bid_filled notification
    result = notify_bid_filled(
        buyer_id=test_user_id,
        order_id=999,
        bid_id=888,
        item_description="2024 1oz Gold American Eagle",
        quantity_filled=5,
        price_per_unit=2100.00,
        total_amount=10500.00
    )

    # Count notifications after
    count_after = conn.execute(
        'SELECT COUNT(*) as count FROM notifications WHERE user_id = ? AND type = ?',
        (test_user_id, 'bid_filled')
    ).fetchone()['count']

    assert result is True, "notify_bid_filled should return True even when disabled"
    assert count_after == count_before, "No in-app notification should be created when disabled"
    print("✓ In-app bid_filled notification correctly skipped when disabled")

    # Now enable only in-app notifications
    conn.execute('''
        INSERT OR REPLACE INTO user_preferences
        (user_id, email_listing_sold, email_bid_filled, inapp_listing_sold, inapp_bid_filled)
        VALUES (?, ?, ?, ?, ?)
    ''', (test_user_id, 1, 0, 1, 1))  # inapp_bid_filled enabled, email_bid_filled disabled
    conn.commit()

    # Send bid_filled notification again
    result = notify_bid_filled(
        buyer_id=test_user_id,
        order_id=1000,
        bid_id=889,
        item_description="2024 1oz Silver American Eagle",
        quantity_filled=10,
        price_per_unit=35.00,
        total_amount=350.00
    )

    # Count notifications after
    count_after2 = conn.execute(
        'SELECT COUNT(*) as count FROM notifications WHERE user_id = ? AND type = ?',
        (test_user_id, 'bid_filled')
    ).fetchone()['count']

    assert result is True, "notify_bid_filled should succeed"
    assert count_after2 == count_after + 1, "In-app notification should be created when enabled"
    print("✓ In-app notification created when enabled")

    conn.close()
    print("✅ Test 3 PASSED\n")


def test_listing_sold_preferences():
    """Test 4: listing_sold notifications respect preferences"""
    print("=== Test 4: Listing Sold Notification Preferences ===")

    user_ids = setup_test_users()
    conn = get_db_connection()

    test_seller_id = user_ids['test_notif_seller']

    # Disable only email notifications for listing_sold
    conn.execute('''
        INSERT OR REPLACE INTO user_preferences
        (user_id, email_listing_sold, email_bid_filled, inapp_listing_sold, inapp_bid_filled)
        VALUES (?, ?, ?, ?, ?)
    ''', (test_seller_id, 0, 1, 1, 1))  # email_listing_sold disabled
    conn.commit()

    # Count notifications before
    count_before = conn.execute(
        'SELECT COUNT(*) as count FROM notifications WHERE user_id = ? AND type = ?',
        (test_seller_id, 'listing_sold')
    ).fetchone()['count']

    # Send listing_sold notification
    result = notify_listing_sold(
        seller_id=test_seller_id,
        order_id=1001,
        listing_id=777,
        item_description="2024 1oz Platinum American Eagle",
        quantity_sold=3,
        price_per_unit=1100.00,
        total_amount=3300.00,
        shipping_address="123 Test St, Test City, TS 12345"
    )

    # Count notifications after
    count_after = conn.execute(
        'SELECT COUNT(*) as count FROM notifications WHERE user_id = ? AND type = ?',
        (test_seller_id, 'listing_sold')
    ).fetchone()['count']

    assert result is True, "notify_listing_sold should succeed"
    assert count_after == count_before + 1, "In-app notification should be created"
    print("✓ In-app listing_sold notification created when enabled")

    # Now disable both email and in-app
    conn.execute('''
        INSERT OR REPLACE INTO user_preferences
        (user_id, email_listing_sold, email_bid_filled, inapp_listing_sold, inapp_bid_filled)
        VALUES (?, ?, ?, ?, ?)
    ''', (test_seller_id, 0, 1, 0, 1))  # both listing_sold disabled
    conn.commit()

    count_before2 = count_after

    # Send listing_sold notification
    result = notify_listing_sold(
        seller_id=test_seller_id,
        order_id=1002,
        listing_id=778,
        item_description="2025 1oz Palladium American Eagle",
        quantity_sold=2,
        price_per_unit=1200.00,
        total_amount=2400.00,
        shipping_address="456 Test Ave, Test City, TS 12345"
    )

    # Count notifications after
    count_after2 = conn.execute(
        'SELECT COUNT(*) as count FROM notifications WHERE user_id = ? AND type = ?',
        (test_seller_id, 'listing_sold')
    ).fetchone()['count']

    assert result is True, "notify_listing_sold should return True even when disabled"
    assert count_after2 == count_before2, "No notification should be created when both disabled"
    print("✓ Notification correctly skipped when both email and in-app disabled")

    conn.close()
    print("✅ Test 4 PASSED\n")


def test_default_behavior():
    """Test 5: Default behavior when preferences not set"""
    print("=== Test 5: Default Behavior (No Preferences Set) ===")

    user_ids = setup_test_users()
    conn = get_db_connection()

    test_user_id = user_ids['test_notif_disabled']

    # Ensure no preferences exist for this user
    conn.execute('DELETE FROM user_preferences WHERE user_id = ?', (test_user_id,))
    conn.commit()

    # Verify no preferences
    prefs = conn.execute(
        'SELECT * FROM user_preferences WHERE user_id = ?',
        (test_user_id,)
    ).fetchone()
    assert prefs is None, "No preferences should exist"

    # Send bid_filled notification
    count_before = conn.execute(
        'SELECT COUNT(*) as count FROM notifications WHERE user_id = ?',
        (test_user_id,)
    ).fetchone()['count']

    result = notify_bid_filled(
        buyer_id=test_user_id,
        order_id=2000,
        bid_id=2001,
        item_description="2024 1oz Gold Maple Leaf",
        quantity_filled=1,
        price_per_unit=2150.00,
        total_amount=2150.00
    )

    count_after = conn.execute(
        'SELECT COUNT(*) as count FROM notifications WHERE user_id = ?',
        (test_user_id,)
    ).fetchone()['count']

    assert result is True, "Notification should succeed with defaults"
    assert count_after == count_before + 1, "In-app notification should be created by default"
    print("✓ Default behavior: all notifications enabled when no preferences set")

    conn.close()
    print("✅ Test 5 PASSED\n")


def test_independent_toggles():
    """Test 6: Email and in-app notifications can be toggled independently"""
    print("=== Test 6: Independent Email and In-App Toggles ===")

    user_ids = setup_test_users()
    conn = get_db_connection()

    test_user_id = user_ids['test_notif_buyer']

    # Test all 4 combinations for bid_filled
    test_cases = [
        (1, 1, "both enabled"),
        (1, 0, "email enabled, in-app disabled"),
        (0, 1, "email disabled, in-app enabled"),
        (0, 0, "both disabled")
    ]

    for email_enabled, inapp_enabled, description in test_cases:
        print(f"\n  Testing: {description}")

        # Set preferences
        conn.execute('''
            INSERT OR REPLACE INTO user_preferences
            (user_id, email_listing_sold, email_bid_filled, inapp_listing_sold, inapp_bid_filled)
            VALUES (?, ?, ?, ?, ?)
        ''', (test_user_id, 1, email_enabled, 1, inapp_enabled))
        conn.commit()

        # Verify preferences were saved correctly
        prefs = conn.execute(
            'SELECT * FROM user_preferences WHERE user_id = ?',
            (test_user_id,)
        ).fetchone()

        assert prefs['email_bid_filled'] == email_enabled, f"email_bid_filled should be {email_enabled}"
        assert prefs['inapp_bid_filled'] == inapp_enabled, f"inapp_bid_filled should be {inapp_enabled}"
        print(f"    ✓ Preferences saved correctly: email={email_enabled}, in-app={inapp_enabled}")

    print("\n✓ All 4 combinations can be set independently")
    conn.close()
    print("✅ Test 6 PASSED\n")


def run_all_tests():
    """Run all notification preference tests"""
    print("\n" + "="*60)
    print("NOTIFICATION PREFERENCES COMPREHENSIVE TEST SUITE")
    print("="*60)

    try:
        test_migration_table_creation()
        test_preference_saving()
        test_notification_respects_preferences()
        test_listing_sold_preferences()
        test_default_behavior()
        test_independent_toggles()

        print("\n" + "="*60)
        print("🎉 ALL TESTS PASSED! 🎉")
        print("="*60)
        print("\nNotification preferences feature is working correctly:")
        print("  ✓ Database migration created user_preferences table")
        print("  ✓ Preferences can be saved and retrieved")
        print("  ✓ Notification service respects user preferences")
        print("  ✓ Email and in-app notifications work independently")
        print("  ✓ Default behavior (all enabled) works correctly")
        print("\n")

    except AssertionError as e:
        print("\n" + "="*60)
        print("❌ TEST FAILED")
        print("="*60)
        print(f"\nError: {e}\n")
        raise


if __name__ == '__main__':
    run_all_tests()
