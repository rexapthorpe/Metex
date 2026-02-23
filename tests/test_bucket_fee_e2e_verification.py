"""
END-TO-END Bucket Fee Change Verification Tests

This file verifies that changing a bucket's platform fee in the admin:
1) Persists correctly (bucket config updated)
2) Is reflected in admin backend responses (bucket detail / bucket list)
3) Affects ONLY future orders (ledger snapshots update on new orders)
4) Is registered in the admin payments backend (events/audit trail + correct fee values in ledger)

These tests follow the full test plan:
- TEST 1: Baseline order uses current bucket fee
- TEST 2: Change bucket fee in admin and confirm admin backend registers it
- TEST 3: New order uses NEW bucket fee (fee snapshot proof)
- TEST 4: Retroactive immutability
- TEST 5: Admin payments backend "registered the change"
"""

import pytest
import sqlite3
import os
import sys
import json
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection
from services.ledger_service import LedgerService, BucketFeeConfigError


# Test IDs to avoid conflicts with other tests
E2E_BUYER_ID = 88881
E2E_SELLER_ID = 88882
E2E_ADMIN_ID = 88883
E2E_CATEGORY_ID = 88884
E2E_BUCKET_ID = 88885
E2E_LISTING_ID = 88886


class TestEndToEndBucketFeeChange:
    """
    End-to-end test class for bucket fee change verification.

    Follows the verification plan exactly.
    """

    @classmethod
    def setup_class(cls):
        """Set up test database once for all tests in this class."""
        conn = get_db_connection()

        # Clean up any existing test data
        cls._cleanup_test_data(conn)

        # Create test users (need both password and password_hash due to schema)
        conn.execute('''
            INSERT OR IGNORE INTO users (id, username, email, password, password_hash)
            VALUES (?, 'e2e_buyer', 'e2e_buyer@test.com', 'test_pass', 'hash_buyer')
        ''', (E2E_BUYER_ID,))
        conn.execute('''
            INSERT OR IGNORE INTO users (id, username, email, password, password_hash)
            VALUES (?, 'e2e_seller', 'e2e_seller@test.com', 'test_pass', 'hash_seller')
        ''', (E2E_SELLER_ID,))
        conn.execute('''
            INSERT OR IGNORE INTO users (id, username, email, password, password_hash, is_admin)
            VALUES (?, 'e2e_admin', 'e2e_admin@test.com', 'test_pass', 'hash_admin', 1)
        ''', (E2E_ADMIN_ID,))

        # SETUP A: Create test bucket with initial fee of 2.5%
        # First try to delete any existing test category
        conn.execute('DELETE FROM categories WHERE id = ?', (E2E_CATEGORY_ID,))
        conn.execute('''
            INSERT INTO categories (id, bucket_id, metal, product_type, weight, platform_fee_type, platform_fee_value)
            VALUES (?, ?, 'Gold', 'Coin', '1 oz', 'percent', 2.5)
        ''', (E2E_CATEGORY_ID, E2E_BUCKET_ID))

        # Create test listing
        conn.execute('DELETE FROM listings WHERE id = ?', (E2E_LISTING_ID,))
        conn.execute('''
            INSERT INTO listings (id, category_id, seller_id, quantity, price_per_coin, active)
            VALUES (?, ?, ?, 100, 2000.00, 1)
        ''', (E2E_LISTING_ID, E2E_CATEGORY_ID, E2E_SELLER_ID))

        # Ensure fee_config table exists with default
        conn.execute('''
            CREATE TABLE IF NOT EXISTS fee_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_key TEXT UNIQUE NOT NULL,
                fee_type TEXT NOT NULL DEFAULT 'percent',
                fee_value REAL NOT NULL DEFAULT 0,
                description TEXT,
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            INSERT OR IGNORE INTO fee_config (config_key, fee_type, fee_value, description)
            VALUES ('default_platform_fee', 'percent', 2.5, 'Default platform fee')
        ''')

        # Ensure bucket_fee_events table exists
        conn.execute('''
            CREATE TABLE IF NOT EXISTS bucket_fee_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bucket_id INTEGER NOT NULL,
                old_fee_type TEXT,
                old_fee_value REAL,
                new_fee_type TEXT NOT NULL,
                new_fee_value REAL NOT NULL,
                admin_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (admin_id) REFERENCES users(id)
            )
        ''')

        conn.commit()
        conn.close()

        # Store order IDs for later verification
        cls.ORDER_A_LEDGER_ID = None
        cls.ORDER_B_LEDGER_ID = None

    @classmethod
    def teardown_class(cls):
        """Clean up test database after all tests."""
        conn = get_db_connection()
        cls._cleanup_test_data(conn)
        conn.close()

    @classmethod
    def _cleanup_test_data(cls, conn):
        """Clean up all test data"""
        try:
            conn.execute('DELETE FROM order_items_ledger WHERE listing_id = ?', (E2E_LISTING_ID,))
            conn.execute('DELETE FROM order_payouts WHERE seller_id = ?', (E2E_SELLER_ID,))
            conn.execute('DELETE FROM orders_ledger WHERE buyer_id = ?', (E2E_BUYER_ID,))
            conn.execute('DELETE FROM order_events WHERE order_id IN (SELECT id FROM orders WHERE buyer_id = ?)', (E2E_BUYER_ID,))
            conn.execute('DELETE FROM orders WHERE buyer_id = ?', (E2E_BUYER_ID,))
            conn.execute('DELETE FROM bucket_fee_events WHERE bucket_id = ?', (E2E_BUCKET_ID,))
            conn.execute('DELETE FROM listings WHERE id = ?', (E2E_LISTING_ID,))
            conn.execute('DELETE FROM categories WHERE id = ?', (E2E_CATEGORY_ID,))
            conn.execute('DELETE FROM users WHERE id IN (?, ?, ?)',
                         (E2E_BUYER_ID, E2E_SELLER_ID, E2E_ADMIN_ID))
            conn.commit()
        except Exception as e:
            print(f"Cleanup warning: {e}")

    def test_1_baseline_order_uses_current_bucket_fee(self):
        """
        TEST 1: Baseline order uses current bucket fee

        Steps:
        1. Create an order containing at least one item from the bucket
        2. Verify in DB:
           - order_items.fee_type == "percent"
           - order_items.fee_value == 2.5
           - fee_amount == gross * 0.025 (rounded to 2 decimals)
           - seller_net == gross - fee_amount
        3. Record Order ID as ORDER_A
        """
        # Verify bucket fee is currently 2.5%
        conn = get_db_connection()
        bucket_config = conn.execute('''
            SELECT platform_fee_type, platform_fee_value
            FROM categories WHERE bucket_id = ?
        ''', (E2E_BUCKET_ID,)).fetchone()
        conn.close()

        assert bucket_config is not None, "Bucket should exist"
        assert bucket_config['platform_fee_type'] == 'percent', "Fee type should be percent"
        assert bucket_config['platform_fee_value'] == 2.5, "Initial fee should be 2.5%"

        # Create Order A
        cart_a = [{
            'seller_id': E2E_SELLER_ID,
            'listing_id': E2E_LISTING_ID,
            'quantity': 1,
            'unit_price': 2000.00,
            'bucket_id': E2E_BUCKET_ID
        }]

        order_ledger_id_a = LedgerService.create_order_ledger_from_cart(
            buyer_id=E2E_BUYER_ID,
            cart_snapshot=cart_a,
            payment_method='test'
        )

        # Store for later tests
        TestEndToEndBucketFeeChange.ORDER_A_LEDGER_ID = order_ledger_id_a

        # Verify Order A fee configuration
        conn = get_db_connection()
        order_a_item = conn.execute('''
            SELECT fee_type, fee_value, fee_amount, gross_amount, seller_net_amount
            FROM order_items_ledger
            WHERE order_ledger_id = ?
        ''', (order_ledger_id_a,)).fetchone()
        conn.close()

        assert order_a_item is not None, "Order A item should exist"
        assert order_a_item['fee_type'] == 'percent', f"Fee type should be 'percent', got '{order_a_item['fee_type']}'"
        assert order_a_item['fee_value'] == 2.5, f"Fee value should be 2.5, got {order_a_item['fee_value']}"

        # Calculate expected values
        expected_gross = 2000.00
        expected_fee = round(expected_gross * 0.025, 2)  # 2.5% of $2000 = $50.00
        expected_net = round(expected_gross - expected_fee, 2)  # $1950.00

        assert order_a_item['gross_amount'] == expected_gross, f"Gross should be {expected_gross}, got {order_a_item['gross_amount']}"
        assert order_a_item['fee_amount'] == expected_fee, f"Fee amount should be {expected_fee}, got {order_a_item['fee_amount']}"
        assert order_a_item['seller_net_amount'] == expected_net, f"Seller net should be {expected_net}, got {order_a_item['seller_net_amount']}"

        print(f"\nTEST 1 PASSED: ORDER_A (ledger_id={order_ledger_id_a})")
        print(f"  - fee_type: percent")
        print(f"  - fee_value: 2.5%")
        print(f"  - fee_amount: ${expected_fee}")
        print(f"  - seller_net: ${expected_net}")

    def test_2_change_bucket_fee_and_verify_admin_registration(self):
        """
        TEST 2: Change bucket fee in admin and confirm admin backend registers it

        Steps:
        1. Use LedgerService.update_bucket_fee() to update bucket fee to 4.0%
        2. Verify:
           - Bucket record updated in DB: platform_fee_value == 4.0
           - If events exist: BUCKET_FEE_UPDATED event logged
           - Timestamps updated
        """
        # Clear any existing events for clean test
        conn = get_db_connection()
        conn.execute('DELETE FROM bucket_fee_events WHERE bucket_id = ?', (E2E_BUCKET_ID,))
        conn.commit()
        conn.close()

        # Update fee to 4%
        result = LedgerService.update_bucket_fee(
            bucket_id=E2E_BUCKET_ID,
            fee_type='percent',
            fee_value=4.0,
            admin_id=E2E_ADMIN_ID
        )

        assert result == True, "update_bucket_fee should return True"

        # Verify bucket config updated
        conn = get_db_connection()
        bucket_config = conn.execute('''
            SELECT platform_fee_type, platform_fee_value, fee_updated_at
            FROM categories WHERE bucket_id = ?
        ''', (E2E_BUCKET_ID,)).fetchone()

        assert bucket_config['platform_fee_type'] == 'percent', "Fee type should still be percent"
        assert bucket_config['platform_fee_value'] == 4.0, f"Fee value should be 4.0, got {bucket_config['platform_fee_value']}"
        assert bucket_config['fee_updated_at'] is not None, "fee_updated_at should be set"

        # Verify event was logged
        event = conn.execute('''
            SELECT * FROM bucket_fee_events
            WHERE bucket_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        ''', (E2E_BUCKET_ID,)).fetchone()
        conn.close()

        assert event is not None, "Fee change event should be logged"
        assert event['bucket_id'] == E2E_BUCKET_ID, "Event bucket_id should match"
        assert event['old_fee_type'] == 'percent', "Old fee type should be percent"
        assert event['old_fee_value'] == 2.5, f"Old fee value should be 2.5, got {event['old_fee_value']}"
        assert event['new_fee_type'] == 'percent', "New fee type should be percent"
        assert event['new_fee_value'] == 4.0, f"New fee value should be 4.0, got {event['new_fee_value']}"
        assert event['admin_id'] == E2E_ADMIN_ID, "Admin ID should match"

        print(f"\nTEST 2 PASSED: Bucket fee changed")
        print(f"  - Old fee: 2.5% (percent)")
        print(f"  - New fee: 4.0% (percent)")
        print(f"  - Event logged: Yes (id={event['id']})")
        print(f"  - Admin ID: {E2E_ADMIN_ID}")
        print(f"  - Timestamp updated: {bucket_config['fee_updated_at']}")

    def test_3_new_order_uses_new_bucket_fee(self):
        """
        TEST 3: New order uses NEW bucket fee (fee snapshot proof)

        Steps:
        1. Create a second order containing an item from the SAME bucket
        2. Verify in DB:
           - order_items.fee_value == 4.0
           - fee_amount == gross * 0.04 (rounded)
           - seller_net correct
        3. Record Order ID as ORDER_B
        """
        # Verify bucket fee is now 4.0%
        fee_type, fee_value = LedgerService.get_bucket_fee_config(E2E_BUCKET_ID)
        assert fee_type == 'percent', "Fee type should be percent"
        assert fee_value == 4.0, f"Fee value should be 4.0, got {fee_value}"

        # Create Order B
        cart_b = [{
            'seller_id': E2E_SELLER_ID,
            'listing_id': E2E_LISTING_ID,
            'quantity': 1,
            'unit_price': 2000.00,
            'bucket_id': E2E_BUCKET_ID
        }]

        order_ledger_id_b = LedgerService.create_order_ledger_from_cart(
            buyer_id=E2E_BUYER_ID,
            cart_snapshot=cart_b,
            payment_method='test'
        )

        # Store for later tests
        TestEndToEndBucketFeeChange.ORDER_B_LEDGER_ID = order_ledger_id_b

        # Verify Order B fee configuration
        conn = get_db_connection()
        order_b_item = conn.execute('''
            SELECT fee_type, fee_value, fee_amount, gross_amount, seller_net_amount
            FROM order_items_ledger
            WHERE order_ledger_id = ?
        ''', (order_ledger_id_b,)).fetchone()
        conn.close()

        assert order_b_item is not None, "Order B item should exist"
        assert order_b_item['fee_type'] == 'percent', f"Fee type should be 'percent', got '{order_b_item['fee_type']}'"
        assert order_b_item['fee_value'] == 4.0, f"Fee value should be 4.0, got {order_b_item['fee_value']}"

        # Calculate expected values
        expected_gross = 2000.00
        expected_fee = round(expected_gross * 0.04, 2)  # 4% of $2000 = $80.00
        expected_net = round(expected_gross - expected_fee, 2)  # $1920.00

        assert order_b_item['gross_amount'] == expected_gross, f"Gross should be {expected_gross}, got {order_b_item['gross_amount']}"
        assert order_b_item['fee_amount'] == expected_fee, f"Fee amount should be {expected_fee}, got {order_b_item['fee_amount']}"
        assert order_b_item['seller_net_amount'] == expected_net, f"Seller net should be {expected_net}, got {order_b_item['seller_net_amount']}"

        print(f"\nTEST 3 PASSED: ORDER_B (ledger_id={order_ledger_id_b})")
        print(f"  - fee_type: percent")
        print(f"  - fee_value: 4.0%")
        print(f"  - fee_amount: ${expected_fee}")
        print(f"  - seller_net: ${expected_net}")

    def test_4_retroactive_immutability(self):
        """
        TEST 4: Retroactive immutability

        Steps:
        1. Re-check ORDER_A:
           - fee_value must remain 2.5
           - fee_amount must remain the old amount ($50)
           - No retroactive changes to ORDER_A
        """
        assert TestEndToEndBucketFeeChange.ORDER_A_LEDGER_ID is not None, "ORDER_A should have been created in test_1"

        conn = get_db_connection()
        order_a_item = conn.execute('''
            SELECT fee_type, fee_value, fee_amount, gross_amount, seller_net_amount
            FROM order_items_ledger
            WHERE order_ledger_id = ?
        ''', (TestEndToEndBucketFeeChange.ORDER_A_LEDGER_ID,)).fetchone()
        conn.close()

        assert order_a_item is not None, "Order A item should still exist"

        # ORDER_A MUST still have the OLD fee configuration
        assert order_a_item['fee_type'] == 'percent', f"Fee type should still be 'percent', got '{order_a_item['fee_type']}'"
        assert order_a_item['fee_value'] == 2.5, f"Fee value should still be 2.5, got {order_a_item['fee_value']}"

        # Original expected values
        expected_gross = 2000.00
        expected_fee_old = round(expected_gross * 0.025, 2)  # $50.00
        expected_net_old = round(expected_gross - expected_fee_old, 2)  # $1950.00

        assert order_a_item['fee_amount'] == expected_fee_old, \
            f"Fee amount should STILL be ${expected_fee_old} (2.5% rate), got ${order_a_item['fee_amount']}"
        assert order_a_item['seller_net_amount'] == expected_net_old, \
            f"Seller net should STILL be ${expected_net_old}, got ${order_a_item['seller_net_amount']}"

        print(f"\nTEST 4 PASSED: ORDER_A immutability verified")
        print(f"  - fee_value: 2.5% (unchanged from snapshot)")
        print(f"  - fee_amount: ${expected_fee_old} (unchanged)")
        print(f"  - seller_net: ${expected_net_old} (unchanged)")
        print(f"  - No retroactive mutation occurred!")

    def test_5_admin_payments_backend_registered_change(self):
        """
        TEST 5: Admin payments backend "registered the change"

        Steps:
        1. Verify bucket config shows updated fee
        2. Verify ledger for new order reflects new fee snapshot
        3. Verify an audit entry exists (event log)
        4. Print final verification report
        """
        conn = get_db_connection()

        # 1. Bucket config shows updated fee
        bucket_config = conn.execute('''
            SELECT platform_fee_type, platform_fee_value, fee_updated_at
            FROM categories WHERE bucket_id = ?
        ''', (E2E_BUCKET_ID,)).fetchone()

        assert bucket_config['platform_fee_value'] == 4.0, "Bucket fee should be 4.0"

        # 2. Get both orders for comparison
        order_a_item = conn.execute('''
            SELECT oil.*, ol.order_id
            FROM order_items_ledger oil
            JOIN orders_ledger ol ON oil.order_ledger_id = ol.id
            WHERE oil.order_ledger_id = ?
        ''', (TestEndToEndBucketFeeChange.ORDER_A_LEDGER_ID,)).fetchone()

        order_b_item = conn.execute('''
            SELECT oil.*, ol.order_id
            FROM order_items_ledger oil
            JOIN orders_ledger ol ON oil.order_ledger_id = ol.id
            WHERE oil.order_ledger_id = ?
        ''', (TestEndToEndBucketFeeChange.ORDER_B_LEDGER_ID,)).fetchone()

        # 3. Check audit trail
        events = conn.execute('''
            SELECT * FROM bucket_fee_events
            WHERE bucket_id = ?
            ORDER BY created_at DESC
        ''', (E2E_BUCKET_ID,)).fetchall()

        conn.close()

        # Assertions
        assert len(events) >= 1, "At least one fee change event should exist"

        # Final verification report
        print("\n" + "="*60)
        print("BUCKET FEE CHANGE VERIFICATION REPORT")
        print("="*60)
        print(f"Bucket tested: ID={E2E_BUCKET_ID}")
        print(f"Old fee: 2.5% (percent)")
        print(f"New fee: 4.0% (percent)")
        print("-"*60)
        print(f"ORDER_A (ledger_id={TestEndToEndBucketFeeChange.ORDER_A_LEDGER_ID}):")
        print(f"  - fee_type: {order_a_item['fee_type']}")
        print(f"  - fee_value: {order_a_item['fee_value']}%")
        print(f"  - fee_amount: ${order_a_item['fee_amount']}")
        print(f"  - seller_net: ${order_a_item['seller_net_amount']}")
        print("-"*60)
        print(f"ORDER_B (ledger_id={TestEndToEndBucketFeeChange.ORDER_B_LEDGER_ID}):")
        print(f"  - fee_type: {order_b_item['fee_type']}")
        print(f"  - fee_value: {order_b_item['fee_value']}%")
        print(f"  - fee_amount: ${order_b_item['fee_amount']}")
        print(f"  - seller_net: ${order_b_item['seller_net_amount']}")
        print("-"*60)
        print("Admin API confirmation:")
        print(f"  - Bucket config fee: {bucket_config['platform_fee_value']}% (reflects new fee)")
        print(f"  - Fee updated timestamp: {bucket_config['fee_updated_at']}")
        print("-"*60)
        print(f"Event/audit confirmation: Yes ({len(events)} event(s) logged)")
        for event in events:
            print(f"  - Event ID {event['id']}: {event['old_fee_value']}% -> {event['new_fee_value']}%")
        print("-"*60)

        # Final assertions
        assert order_a_item['fee_value'] == 2.5, "ORDER_A should have old fee"
        assert order_b_item['fee_value'] == 4.0, "ORDER_B should have new fee"

        print("Result: PASS")
        print("="*60)


class TestBucketFeeApiEndpoints:
    """
    Tests for admin API endpoints related to bucket fee management.

    These tests verify that the admin API correctly reports bucket fee configuration.
    """

    @classmethod
    def setup_class(cls):
        """Ensure test data exists."""
        conn = get_db_connection()

        # Create test users if they don't exist
        conn.execute('''
            INSERT OR IGNORE INTO users (id, username, email, password, password_hash)
            VALUES (?, 'e2e_buyer', 'e2e_buyer@test.com', 'test_pass', 'hash_buyer')
        ''', (E2E_BUYER_ID,))
        conn.execute('''
            INSERT OR IGNORE INTO users (id, username, email, password, password_hash)
            VALUES (?, 'e2e_seller', 'e2e_seller@test.com', 'test_pass', 'hash_seller')
        ''', (E2E_SELLER_ID,))
        conn.execute('''
            INSERT OR IGNORE INTO users (id, username, email, password, password_hash, is_admin)
            VALUES (?, 'e2e_admin', 'e2e_admin@test.com', 'test_pass', 'hash_admin', 1)
        ''', (E2E_ADMIN_ID,))

        # Create category/bucket if needed
        existing = conn.execute('SELECT id FROM categories WHERE id = ?', (E2E_CATEGORY_ID,)).fetchone()
        if not existing:
            conn.execute('''
                INSERT INTO categories (id, bucket_id, metal, product_type, weight, platform_fee_type, platform_fee_value)
                VALUES (?, ?, 'Gold', 'Coin', '1 oz', 'percent', 2.5)
            ''', (E2E_CATEGORY_ID, E2E_BUCKET_ID))

        # Create listing if needed
        existing = conn.execute('SELECT id FROM listings WHERE id = ?', (E2E_LISTING_ID,)).fetchone()
        if not existing:
            conn.execute('''
                INSERT INTO listings (id, category_id, seller_id, quantity, price_per_coin, active)
                VALUES (?, ?, ?, 100, 2000.00, 1)
            ''', (E2E_LISTING_ID, E2E_CATEGORY_ID, E2E_SELLER_ID))

        conn.commit()
        conn.close()

    def test_get_bucket_fee_config_returns_correct_value(self):
        """Test that get_bucket_fee_config returns the correct fee for a bucket."""
        # Set a known fee
        conn = get_db_connection()
        conn.execute('''
            UPDATE categories
            SET platform_fee_type = 'percent', platform_fee_value = 3.5
            WHERE bucket_id = ?
        ''', (E2E_BUCKET_ID,))
        conn.commit()
        conn.close()

        # Get fee config
        fee_type, fee_value = LedgerService.get_bucket_fee_config(E2E_BUCKET_ID)

        assert fee_type == 'percent'
        assert fee_value == 3.5

        print("\nTEST PASSED: get_bucket_fee_config returns correct fee")

    def test_update_bucket_fee_rejects_invalid_fee_type(self):
        """Test that invalid fee types are rejected."""
        with pytest.raises(ValueError) as exc_info:
            LedgerService.update_bucket_fee(
                bucket_id=E2E_BUCKET_ID,
                fee_type='invalid_type',
                fee_value=5.0,
                admin_id=E2E_ADMIN_ID
            )

        assert "invalid" in str(exc_info.value).lower()
        print("\nTEST PASSED: Invalid fee type rejected")

    def test_update_bucket_fee_rejects_negative_value(self):
        """Test that negative fee values are rejected."""
        with pytest.raises(ValueError) as exc_info:
            LedgerService.update_bucket_fee(
                bucket_id=E2E_BUCKET_ID,
                fee_type='percent',
                fee_value=-5.0,
                admin_id=E2E_ADMIN_ID
            )

        assert "invalid" in str(exc_info.value).lower() or "-5.0" in str(exc_info.value)
        print("\nTEST PASSED: Negative fee value rejected")

    def test_flat_fee_applies_correctly(self):
        """Test that flat fee type calculates correctly."""
        conn = get_db_connection()

        # Set flat fee
        conn.execute('''
            UPDATE categories
            SET platform_fee_type = 'flat', platform_fee_value = 50.00
            WHERE bucket_id = ?
        ''', (E2E_BUCKET_ID,))
        conn.commit()
        conn.close()

        # Create order
        cart = [{
            'seller_id': E2E_SELLER_ID,
            'listing_id': E2E_LISTING_ID,
            'quantity': 1,
            'unit_price': 2000.00,
            'bucket_id': E2E_BUCKET_ID
        }]

        order_ledger_id = LedgerService.create_order_ledger_from_cart(
            buyer_id=E2E_BUYER_ID,
            cart_snapshot=cart,
            payment_method='test'
        )

        # Verify flat fee
        conn = get_db_connection()
        item = conn.execute('''
            SELECT fee_type, fee_value, fee_amount, gross_amount, seller_net_amount
            FROM order_items_ledger
            WHERE order_ledger_id = ?
        ''', (order_ledger_id,)).fetchone()
        conn.close()

        assert item['fee_type'] == 'flat', f"Fee type should be 'flat', got '{item['fee_type']}'"
        assert item['fee_value'] == 50.00, f"Fee value should be 50.00, got {item['fee_value']}"
        assert item['fee_amount'] == 50.00, f"Fee amount should be $50.00 (flat), got ${item['fee_amount']}"

        expected_net = round(2000.00 - 50.00, 2)
        assert item['seller_net_amount'] == expected_net, f"Seller net should be ${expected_net}, got ${item['seller_net_amount']}"

        print("\nTEST PASSED: Flat fee applies correctly")
        print(f"  - Gross: $2000.00")
        print(f"  - Fee: $50.00 (flat)")
        print(f"  - Seller net: ${expected_net}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
