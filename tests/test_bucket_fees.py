"""
Tests for bucket-level fee configuration and snapshot behavior.

These tests verify:
1. Bucket fee configuration is correctly read from categories table
2. Fee snapshots are immutable in order_items_ledger
3. Changing bucket fee does NOT affect existing orders
4. Missing fee config causes deterministic failure
"""

import pytest
import sqlite3
import os
import sys
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection
from services.ledger_service import LedgerService, BucketFeeConfigError


# Use unique test IDs to avoid conflicts
TEST_BUYER_ID = 99991
TEST_SELLER_ID = 99992
TEST_ADMIN_ID = 99993
TEST_CATEGORY_ID = 99994
TEST_BUCKET_ID = 99995
TEST_LISTING_ID = 99996


def setup_module(module):
    """Set up test database once for all tests."""
    conn = get_db_connection()

    # Create test users
    conn.execute('''
        INSERT OR IGNORE INTO users (id, username, email, password_hash)
        VALUES (?, 'test_buyer_fees', 'buyer_fees@test.com', 'hash123')
    ''', (TEST_BUYER_ID,))
    conn.execute('''
        INSERT OR IGNORE INTO users (id, username, email, password_hash)
        VALUES (?, 'test_seller_fees', 'seller_fees@test.com', 'hash456')
    ''', (TEST_SELLER_ID,))
    conn.execute('''
        INSERT OR IGNORE INTO users (id, username, email, password_hash, is_admin)
        VALUES (?, 'test_admin_fees', 'admin_fees@test.com', 'hash789', 1)
    ''', (TEST_ADMIN_ID,))

    # Create test category with bucket_id
    conn.execute('''
        INSERT OR IGNORE INTO categories (id, bucket_id, metal, product_type, weight)
        VALUES (?, ?, 'Gold', 'Coin', '1 oz')
    ''', (TEST_CATEGORY_ID, TEST_BUCKET_ID))

    # Create test listing
    conn.execute('''
        INSERT OR IGNORE INTO listings (id, category_id, seller_id, quantity, price_per_coin, active)
        VALUES (?, ?, ?, 10, 2000.00, 1)
    ''', (TEST_LISTING_ID, TEST_CATEGORY_ID, TEST_SELLER_ID))

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


def teardown_module(module):
    """Clean up test database after all tests."""
    conn = get_db_connection()
    try:
        conn.execute('DELETE FROM order_items_ledger WHERE listing_id = ?', (TEST_LISTING_ID,))
        conn.execute('DELETE FROM orders_ledger WHERE buyer_id = ?', (TEST_BUYER_ID,))
        conn.execute('DELETE FROM bucket_fee_events WHERE bucket_id = ?', (TEST_BUCKET_ID,))
        conn.execute('DELETE FROM listings WHERE id = ?', (TEST_LISTING_ID,))
        conn.execute('DELETE FROM categories WHERE id = ?', (TEST_CATEGORY_ID,))
        conn.execute('DELETE FROM users WHERE id IN (?, ?, ?)',
                     (TEST_BUYER_ID, TEST_SELLER_ID, TEST_ADMIN_ID))
        conn.commit()
    except Exception as e:
        print(f"Teardown warning: {e}")
    finally:
        conn.close()


class TestBucketFeeConfiguration:
    """Test suite for bucket fee configuration and snapshot behavior."""

    def test_get_bucket_fee_config_with_bucket_fee(self):
        """Test that bucket-level fee is returned when configured."""
        conn = get_db_connection()

        # Set bucket fee
        conn.execute('''
            UPDATE categories
            SET platform_fee_type = 'percent', platform_fee_value = 3.5
            WHERE bucket_id = ?
        ''', (TEST_BUCKET_ID,))
        conn.commit()
        conn.close()

        # Get fee config
        fee_type, fee_value = LedgerService.get_bucket_fee_config(TEST_BUCKET_ID)

        assert fee_type == 'percent'
        assert fee_value == 3.5

    def test_get_bucket_fee_config_falls_back_to_global(self):
        """Test that global default is used when no bucket fee is configured."""
        conn = get_db_connection()

        # Ensure no bucket fee set
        conn.execute('''
            UPDATE categories
            SET platform_fee_type = NULL, platform_fee_value = NULL
            WHERE bucket_id = ?
        ''', (TEST_BUCKET_ID,))
        conn.commit()
        conn.close()

        # Get fee config
        fee_type, fee_value = LedgerService.get_bucket_fee_config(TEST_BUCKET_ID)

        assert fee_type == 'percent'
        assert fee_value == 2.5  # Global default

    def test_get_bucket_fee_config_raises_on_missing(self):
        """Test that BucketFeeConfigError is raised when no config exists."""
        conn = get_db_connection()

        # Remove all fee config
        conn.execute('''
            UPDATE categories
            SET platform_fee_type = NULL, platform_fee_value = NULL
            WHERE bucket_id = ?
        ''', (TEST_BUCKET_ID,))
        conn.execute('DELETE FROM fee_config')
        conn.commit()
        conn.close()

        # Should raise error
        with pytest.raises(BucketFeeConfigError):
            LedgerService.get_bucket_fee_config(TEST_BUCKET_ID)

        # Restore default
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO fee_config (config_key, fee_type, fee_value, description)
            VALUES ('default_platform_fee', 'percent', 2.5, 'Default platform fee')
        ''')
        conn.commit()
        conn.close()

    def test_bucket_fee_snapshot_immutability(self):
        """
        Test B3: Verify that changing bucket fee does not affect existing orders.

        Steps:
        1. Create bucket with fee = 2.5%
        2. Checkout -> Order A
        3. Update bucket fee to 4%
        4. Checkout -> Order B

        Verify:
        - Order A uses 2.5%
        - Order B uses 4%
        - No retroactive mutation
        """
        conn = get_db_connection()

        # Step 1: Set bucket fee to 2.5%
        conn.execute('''
            UPDATE categories
            SET platform_fee_type = 'percent', platform_fee_value = 2.5
            WHERE bucket_id = ?
        ''', (TEST_BUCKET_ID,))
        conn.commit()
        conn.close()

        # Step 2: Create Order A
        cart_a = [{
            'seller_id': TEST_SELLER_ID,
            'listing_id': TEST_LISTING_ID,
            'quantity': 1,
            'unit_price': 2000.00,
            'bucket_id': TEST_BUCKET_ID
        }]

        order_ledger_id_a = LedgerService.create_order_ledger_from_cart(
            buyer_id=TEST_BUYER_ID,
            cart_snapshot=cart_a,
            payment_method='test'
        )

        # Verify Order A fee
        conn = get_db_connection()
        order_a_item = conn.execute('''
            SELECT fee_type, fee_value, fee_amount, gross_amount
            FROM order_items_ledger
            WHERE order_ledger_id = ?
        ''', (order_ledger_id_a,)).fetchone()

        assert order_a_item['fee_type'] == 'percent'
        assert order_a_item['fee_value'] == 2.5
        expected_fee_a = round(2000.00 * 0.025, 2)  # 2.5% of $2000 = $50
        assert order_a_item['fee_amount'] == expected_fee_a

        # Step 3: Update bucket fee to 4%
        conn.execute('''
            UPDATE categories
            SET platform_fee_type = 'percent', platform_fee_value = 4.0
            WHERE bucket_id = ?
        ''', (TEST_BUCKET_ID,))
        conn.commit()
        conn.close()

        # Step 4: Create Order B
        cart_b = [{
            'seller_id': TEST_SELLER_ID,
            'listing_id': TEST_LISTING_ID,
            'quantity': 1,
            'unit_price': 2000.00,
            'bucket_id': TEST_BUCKET_ID
        }]

        order_ledger_id_b = LedgerService.create_order_ledger_from_cart(
            buyer_id=TEST_BUYER_ID,
            cart_snapshot=cart_b,
            payment_method='test'
        )

        # Verify Order B fee
        conn = get_db_connection()
        order_b_item = conn.execute('''
            SELECT fee_type, fee_value, fee_amount
            FROM order_items_ledger
            WHERE order_ledger_id = ?
        ''', (order_ledger_id_b,)).fetchone()

        assert order_b_item['fee_type'] == 'percent'
        assert order_b_item['fee_value'] == 4.0
        expected_fee_b = round(2000.00 * 0.04, 2)  # 4% of $2000 = $80
        assert order_b_item['fee_amount'] == expected_fee_b

        # Verify Order A was NOT modified (no retroactive mutation)
        order_a_item_after = conn.execute('''
            SELECT fee_type, fee_value, fee_amount
            FROM order_items_ledger
            WHERE order_ledger_id = ?
        ''', (order_ledger_id_a,)).fetchone()

        assert order_a_item_after['fee_type'] == 'percent'
        assert order_a_item_after['fee_value'] == 2.5
        assert order_a_item_after['fee_amount'] == expected_fee_a

        conn.close()

        print("TEST PASSED: Order A fee = 2.5%, Order B fee = 4%, no retroactive mutation")

    def test_update_bucket_fee_logs_event(self):
        """Test that updating bucket fee creates an audit log entry."""
        conn = get_db_connection()

        # Clear any existing events
        conn.execute('DELETE FROM bucket_fee_events WHERE bucket_id = ?', (TEST_BUCKET_ID,))
        conn.commit()
        conn.close()

        # Update fee
        LedgerService.update_bucket_fee(
            bucket_id=TEST_BUCKET_ID,
            fee_type='percent',
            fee_value=5.0,
            admin_id=TEST_ADMIN_ID
        )

        # Verify event was logged
        conn = get_db_connection()
        event = conn.execute('''
            SELECT * FROM bucket_fee_events
            WHERE bucket_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        ''', (TEST_BUCKET_ID,)).fetchone()

        assert event is not None
        assert event['bucket_id'] == TEST_BUCKET_ID
        assert event['new_fee_type'] == 'percent'
        assert event['new_fee_value'] == 5.0
        assert event['admin_id'] == TEST_ADMIN_ID
        conn.close()

    def test_update_bucket_fee_validates_inputs(self):
        """Test that invalid fee configurations are rejected."""
        # Invalid fee type
        with pytest.raises(ValueError):
            LedgerService.update_bucket_fee(
                bucket_id=TEST_BUCKET_ID,
                fee_type='invalid',
                fee_value=5.0,
                admin_id=TEST_ADMIN_ID
            )

        # Negative fee value
        with pytest.raises(ValueError):
            LedgerService.update_bucket_fee(
                bucket_id=TEST_BUCKET_ID,
                fee_type='percent',
                fee_value=-5.0,
                admin_id=TEST_ADMIN_ID
            )

    def test_flat_fee_type(self):
        """Test that flat fee type works correctly."""
        conn = get_db_connection()

        # Set flat fee
        conn.execute('''
            UPDATE categories
            SET platform_fee_type = 'flat', platform_fee_value = 25.00
            WHERE bucket_id = ?
        ''', (TEST_BUCKET_ID,))
        conn.commit()
        conn.close()

        # Create order
        cart = [{
            'seller_id': TEST_SELLER_ID,
            'listing_id': TEST_LISTING_ID,
            'quantity': 1,
            'unit_price': 2000.00,
            'bucket_id': TEST_BUCKET_ID
        }]

        order_ledger_id = LedgerService.create_order_ledger_from_cart(
            buyer_id=TEST_BUYER_ID,
            cart_snapshot=cart,
            payment_method='test'
        )

        # Verify flat fee
        conn = get_db_connection()
        item = conn.execute('''
            SELECT fee_type, fee_value, fee_amount
            FROM order_items_ledger
            WHERE order_ledger_id = ?
        ''', (order_ledger_id,)).fetchone()

        assert item['fee_type'] == 'flat'
        assert item['fee_value'] == 25.00
        assert item['fee_amount'] == 25.00  # Flat fee, regardless of amount
        conn.close()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
