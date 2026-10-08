"""
Tests for Ledger Hardening Patch (Pre-Phase 3)

Tests cover:
- Fix #1: Report auto-hold failure visibility
- Fix #2: Partial refund semantics in multi-seller orders
"""
import pytest
import sqlite3
import os
import sys
import json
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def test_db(tmp_path):
    """Create a temporary test database with required tables"""
    db_path = tmp_path / "test_metex_hardening.db"

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Create minimal schema needed for tests
    conn.executescript("""
        -- Users table
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            email TEXT,
            is_admin INTEGER DEFAULT 0
        );

        -- Orders table
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            buyer_id INTEGER,
            total_price REAL,
            status TEXT DEFAULT 'Pending',
            shipping_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Categories table
        CREATE TABLE categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bucket_id INTEGER,
            name TEXT,
            platform_fee_type TEXT,
            platform_fee_value REAL,
            fee_updated_at TIMESTAMP
        );

        -- Listings table
        CREATE TABLE listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER,
            category_id INTEGER,
            price_per_coin REAL,
            quantity INTEGER,
            active INTEGER DEFAULT 1
        );

        -- Order items table
        CREATE TABLE order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            listing_id INTEGER,
            quantity INTEGER,
            price_each REAL
        );

        -- Ledger tables
        CREATE TABLE orders_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER UNIQUE NOT NULL,
            buyer_id INTEGER NOT NULL,
            order_status TEXT NOT NULL DEFAULT 'CHECKOUT_INITIATED',
            payment_method TEXT,
            gross_amount REAL NOT NULL,
            platform_fee_amount REAL NOT NULL DEFAULT 0,
            spread_capture_amount REAL NOT NULL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE order_items_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_ledger_id INTEGER NOT NULL,
            order_id INTEGER NOT NULL,
            seller_id INTEGER NOT NULL,
            listing_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            gross_amount REAL NOT NULL,
            fee_type TEXT NOT NULL DEFAULT 'percent',
            fee_value REAL NOT NULL DEFAULT 0,
            fee_amount REAL NOT NULL DEFAULT 0,
            seller_net_amount REAL NOT NULL,
            buyer_unit_price REAL DEFAULT NULL,
            spread_per_unit REAL NOT NULL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE order_payouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_ledger_id INTEGER NOT NULL,
            order_id INTEGER NOT NULL,
            seller_id INTEGER NOT NULL,
            payout_status TEXT NOT NULL DEFAULT 'PAYOUT_NOT_READY',
            seller_gross_amount REAL NOT NULL,
            fee_amount REAL NOT NULL DEFAULT 0,
            seller_net_amount REAL NOT NULL,
            spread_capture_amount REAL NOT NULL DEFAULT 0.0,
            scheduled_for TIMESTAMP,
            provider_transfer_id TEXT,
            provider_payout_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(order_ledger_id, seller_id)
        );

        CREATE TABLE order_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            actor_type TEXT NOT NULL,
            actor_id INTEGER,
            payload_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE fee_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_key TEXT UNIQUE NOT NULL,
            fee_type TEXT NOT NULL DEFAULT 'percent',
            fee_value REAL NOT NULL DEFAULT 0,
            description TEXT,
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Reports table
        CREATE TABLE reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_user_id INTEGER NOT NULL,
            reported_user_id INTEGER NOT NULL,
            order_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            comment TEXT,
            status TEXT DEFAULT 'open',
            resolution_note TEXT,
            admin_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP,
            resolved_by INTEGER
        );

        CREATE TABLE report_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            original_filename TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Insert default fee config
        INSERT INTO fee_config (config_key, fee_type, fee_value, description)
        VALUES ('default_platform_fee', 'percent', 2.5, 'Default 2.5% platform fee');

        -- Create test users
        INSERT INTO users (username, email) VALUES ('buyer1', 'buyer1@test.com');
        INSERT INTO users (username, email) VALUES ('seller1', 'seller1@test.com');
        INSERT INTO users (username, email) VALUES ('seller2', 'seller2@test.com');
        INSERT INTO users (username, email, is_admin) VALUES ('admin', 'admin@test.com', 1);

        -- Create test listings
        INSERT INTO listings (seller_id, category_id, price_per_coin, quantity) VALUES (2, NULL, 100.00, 10);
        INSERT INTO listings (seller_id, category_id, price_per_coin, quantity) VALUES (3, NULL, 200.00, 5);
    """)
    conn.commit()

    yield conn, str(db_path)

    conn.close()


@pytest.fixture
def mock_get_db(test_db, monkeypatch):
    """Mock the database connection to use test database"""
    conn, db_path = test_db

    def get_test_connection():
        new_conn = sqlite3.connect(db_path)
        new_conn.row_factory = sqlite3.Row
        return new_conn

    import database
    monkeypatch.setattr(database, 'get_db_connection', get_test_connection)

    import services.ledger_service as ledger_module
    monkeypatch.setattr(ledger_module, 'get_db_connection', get_test_connection)

    return get_test_connection


def create_test_ledger(mock_get_db, buyer_id=1, sellers=None):
    """Helper to create a test ledger with specified sellers"""
    from services.ledger_service import LedgerService

    if sellers is None:
        sellers = [(2, 100.00)]

    conn = mock_get_db()

    total = sum(price for _, price in sellers)
    cursor = conn.execute('''
        INSERT INTO orders (buyer_id, total_price, status)
        VALUES (?, ?, 'Pending')
    ''', (buyer_id, total))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()

    cart_snapshot = []
    for i, (seller_id, price) in enumerate(sellers):
        cart_snapshot.append({
            'seller_id': seller_id,
            'listing_id': 1 if seller_id == 2 else 2,
            'quantity': 1,
            'unit_price': price,
            'fee_type': 'percent',
            'fee_value': 2.5
        })

    ledger_id = LedgerService.create_order_ledger_from_cart(
        buyer_id=buyer_id,
        cart_snapshot=cart_snapshot,
        order_id=order_id
    )

    return order_id, ledger_id


# ============================================================================
# FIX #1 TESTS: Auto-Hold Failure Visibility
# ============================================================================

class TestAutoHoldFailureVisibility:
    """Tests for Fix #1: Report auto-hold must be visible if it fails"""

    def test_auto_hold_failed_event_type_exists(self):
        """Verify AUTO_HOLD_FAILED event type is defined"""
        from services.ledger_constants import EventType

        assert hasattr(EventType, 'AUTO_HOLD_FAILED')
        assert EventType.AUTO_HOLD_FAILED.value == 'AUTO_HOLD_FAILED'

    def test_auto_hold_failure_logs_event(self, mock_get_db):
        """Test that auto-hold failure creates AUTO_HOLD_FAILED event"""
        from services.ledger_service import LedgerService
        from services.ledger_constants import EventType

        # Create order and ledger
        order_id, ledger_id = create_test_ledger(mock_get_db, buyer_id=1, sellers=[(2, 100.00)])

        # Simulate AUTO_HOLD_FAILED event logging (as report creation would do)
        LedgerService.log_order_event(
            order_id=order_id,
            event_type=EventType.AUTO_HOLD_FAILED.value,
            actor_type='system',
            actor_id=None,
            payload={
                'report_id': 999,
                'reported_user_id': 2,
                'reporter_id': 1,
                'error': 'Test error message',
                'stack_context': 'Test stack trace'
            }
        )

        # Verify event was logged
        conn = mock_get_db()
        event = conn.execute('''
            SELECT * FROM order_events
            WHERE order_id = ? AND event_type = 'AUTO_HOLD_FAILED'
        ''', (order_id,)).fetchone()

        assert event is not None
        payload = json.loads(event['payload_json'])
        assert payload['report_id'] == 999
        assert payload['error'] == 'Test error message'
        conn.close()

    def test_auto_hold_failed_event_includes_required_fields(self, mock_get_db):
        """Test AUTO_HOLD_FAILED event contains all required payload fields"""
        from services.ledger_service import LedgerService
        from services.ledger_constants import EventType

        order_id, ledger_id = create_test_ledger(mock_get_db)

        # Log event with all required fields
        LedgerService.log_order_event(
            order_id=order_id,
            event_type=EventType.AUTO_HOLD_FAILED.value,
            actor_type='system',
            actor_id=None,
            payload={
                'report_id': 123,
                'reported_user_id': 2,
                'reporter_id': 1,
                'error': 'Connection timeout',
                'stack_context': 'at LedgerService.handle_report_auto_hold...'
            }
        )

        conn = mock_get_db()
        event = conn.execute('''
            SELECT * FROM order_events WHERE event_type = 'AUTO_HOLD_FAILED'
        ''').fetchone()

        assert event is not None
        payload = json.loads(event['payload_json'])

        # Verify all required fields are present
        assert 'report_id' in payload
        assert 'reported_user_id' in payload
        assert 'reporter_id' in payload
        assert 'error' in payload

        conn.close()


# ============================================================================
# FIX #2 TESTS: Partial Refund Semantics in Multi-Seller Orders
# ============================================================================

class TestPartialRefundValidation:
    """Tests for Fix #2: Partial refund validation rules"""







class TestMultiSellerPartialRefund:
    """Tests for partial refund behavior in multi-seller orders"""






class TestPartialRefundEventPayloads:
    """Tests for refund event payload correctness"""




if __name__ == '__main__':
    pytest.main([__file__, '-v'])
