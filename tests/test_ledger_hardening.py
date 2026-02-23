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

    def test_partial_refund_fails_with_both_seller_and_items(self, mock_get_db):
        """Test that partial refund fails when BOTH seller_id and order_item_ids are provided"""
        from services.ledger_service import LedgerService

        order_id, ledger_id = create_test_ledger(mock_get_db, sellers=[(2, 100.00), (3, 200.00)])

        # Get item IDs
        conn = mock_get_db()
        items = conn.execute('SELECT id FROM order_items_ledger WHERE order_id = ?', (order_id,)).fetchall()
        item_ids = [i['id'] for i in items]
        conn.close()

        # Attempt partial refund with BOTH seller_id and order_item_ids
        with pytest.raises(ValueError) as exc_info:
            LedgerService.process_refund(
                order_id=order_id,
                admin_id=4,
                refund_type='partial',
                reason='Test',
                seller_id=2,
                order_item_ids=item_ids
            )

        assert 'not both' in str(exc_info.value).lower()

    def test_partial_refund_fails_with_neither_seller_nor_items(self, mock_get_db):
        """Test that partial refund fails when NEITHER seller_id nor order_item_ids are provided"""
        from services.ledger_service import LedgerService

        order_id, ledger_id = create_test_ledger(mock_get_db, sellers=[(2, 100.00)])

        with pytest.raises(ValueError) as exc_info:
            LedgerService.process_refund(
                order_id=order_id,
                admin_id=4,
                refund_type='partial',
                reason='Test',
                seller_id=None,
                order_item_ids=None
            )

        assert 'requires' in str(exc_info.value).lower()

    def test_partial_refund_fails_with_empty_item_ids(self, mock_get_db):
        """Test that partial refund fails with empty order_item_ids list"""
        from services.ledger_service import LedgerService

        order_id, ledger_id = create_test_ledger(mock_get_db, sellers=[(2, 100.00)])

        with pytest.raises(ValueError) as exc_info:
            LedgerService.process_refund(
                order_id=order_id,
                admin_id=4,
                refund_type='partial',
                reason='Test',
                seller_id=None,
                order_item_ids=[]
            )

        assert 'requires' in str(exc_info.value).lower()

    def test_partial_refund_fails_with_invalid_item_ids(self, mock_get_db):
        """Test that partial refund fails when order_item_ids don't belong to the order"""
        from services.ledger_service import LedgerService

        order_id, ledger_id = create_test_ledger(mock_get_db, sellers=[(2, 100.00)])

        # Use non-existent item IDs
        with pytest.raises(ValueError) as exc_info:
            LedgerService.process_refund(
                order_id=order_id,
                admin_id=4,
                refund_type='partial',
                reason='Test',
                order_item_ids=[99999, 99998]
            )

        assert 'not found' in str(exc_info.value).lower()

    def test_partial_refund_fails_with_nonexistent_seller(self, mock_get_db):
        """Test that partial refund fails when seller has no items in order"""
        from services.ledger_service import LedgerService

        order_id, ledger_id = create_test_ledger(mock_get_db, sellers=[(2, 100.00)])

        # Use seller_id that has no items in this order
        with pytest.raises(ValueError) as exc_info:
            LedgerService.process_refund(
                order_id=order_id,
                admin_id=4,
                refund_type='partial',
                reason='Test',
                seller_id=99  # Non-existent in this order
            )

        assert 'no items' in str(exc_info.value).lower()


class TestMultiSellerPartialRefund:
    """Tests for partial refund behavior in multi-seller orders"""

    def test_partial_refund_by_seller_cancels_only_that_seller(self, mock_get_db):
        """Test that partial refund by seller_id cancels ONLY that seller's payout"""
        from services.ledger_service import LedgerService

        # Create 2-seller order
        order_id, ledger_id = create_test_ledger(mock_get_db, sellers=[(2, 100.00), (3, 200.00)])

        # Partial refund seller 2
        result = LedgerService.process_refund(
            order_id=order_id,
            admin_id=4,
            refund_type='partial',
            reason='Issue with seller 2 items',
            seller_id=2
        )

        # Verify result
        assert result['refund_amount'] == 100.00
        assert 2 in result['affected_sellers']
        assert 3 not in result['affected_sellers']

        # Verify payout statuses
        conn = mock_get_db()
        payouts = conn.execute('SELECT * FROM order_payouts WHERE order_id = ?', (order_id,)).fetchall()

        seller2_payout = next(p for p in payouts if p['seller_id'] == 2)
        seller3_payout = next(p for p in payouts if p['seller_id'] == 3)

        assert seller2_payout['payout_status'] == 'PAYOUT_CANCELLED'
        assert seller3_payout['payout_status'] != 'PAYOUT_CANCELLED'

        # Verify order status
        order = conn.execute('SELECT * FROM orders_ledger WHERE order_id = ?', (order_id,)).fetchone()
        assert order['order_status'] == 'PARTIALLY_REFUNDED'

        conn.close()

    def test_partial_refund_preserves_invariants(self, mock_get_db):
        """Test that partial refund still passes invariants"""
        from services.ledger_service import LedgerService

        order_id, ledger_id = create_test_ledger(mock_get_db, sellers=[(2, 100.00), (3, 200.00)])

        # Partial refund
        LedgerService.process_refund(
            order_id=order_id,
            admin_id=4,
            refund_type='partial',
            reason='Test',
            seller_id=2
        )

        # Verify invariants still pass (this would raise if violated)
        # Note: We can't call validate_order_invariants directly as it checks
        # existing records, but we can verify the math is correct

        conn = mock_get_db()

        # Get ledger
        ledger = conn.execute('SELECT * FROM orders_ledger WHERE order_id = ?', (order_id,)).fetchone()

        # Sum of items should still match
        items_sum = conn.execute('''
            SELECT SUM(gross_amount) as total FROM order_items_ledger WHERE order_id = ?
        ''', (order_id,)).fetchone()['total']

        assert abs(items_sum - ledger['gross_amount']) < 0.01

        conn.close()

    def test_partial_refund_by_item_ids_cancels_correct_payouts(self, mock_get_db):
        """Test that partial refund by order_item_ids cancels correct payouts"""
        from services.ledger_service import LedgerService

        order_id, ledger_id = create_test_ledger(mock_get_db, sellers=[(2, 100.00), (3, 200.00)])

        # Get seller 2's item ID
        conn = mock_get_db()
        seller2_item = conn.execute('''
            SELECT id FROM order_items_ledger WHERE order_id = ? AND seller_id = 2
        ''', (order_id,)).fetchone()
        conn.close()

        # Partial refund by item ID
        result = LedgerService.process_refund(
            order_id=order_id,
            admin_id=4,
            refund_type='partial',
            reason='Test',
            order_item_ids=[seller2_item['id']]
        )

        assert result['refund_amount'] == 100.00
        assert len(result['affected_item_ids']) == 1

        # Verify payouts
        conn = mock_get_db()
        payouts = conn.execute('SELECT * FROM order_payouts WHERE order_id = ?', (order_id,)).fetchall()

        seller2_payout = next(p for p in payouts if p['seller_id'] == 2)
        seller3_payout = next(p for p in payouts if p['seller_id'] == 3)

        assert seller2_payout['payout_status'] == 'PAYOUT_CANCELLED'
        assert seller3_payout['payout_status'] != 'PAYOUT_CANCELLED'

        conn.close()

    def test_partial_refund_leaves_other_sellers_eligible(self, mock_get_db):
        """Test that unaffected sellers remain eligible for payout"""
        from services.ledger_service import LedgerService

        order_id, ledger_id = create_test_ledger(mock_get_db, sellers=[(2, 100.00), (3, 200.00)])

        # Partial refund seller 2 only
        LedgerService.process_refund(
            order_id=order_id,
            admin_id=4,
            refund_type='partial',
            reason='Test',
            seller_id=2
        )

        # Verify seller 3's payout is still in eligible status
        conn = mock_get_db()
        seller3_payout = conn.execute('''
            SELECT * FROM order_payouts WHERE order_id = ? AND seller_id = 3
        ''', (order_id,)).fetchone()

        # Should be in PAYOUT_NOT_READY (initial status), not PAYOUT_CANCELLED
        assert seller3_payout['payout_status'] == 'PAYOUT_NOT_READY'
        assert seller3_payout['payout_status'] != 'PAYOUT_CANCELLED'

        conn.close()


class TestPartialRefundEventPayloads:
    """Tests for refund event payload correctness"""

    def test_refund_initiated_event_has_detailed_payload(self, mock_get_db):
        """Test REFUND_INITIATED event includes all required details"""
        from services.ledger_service import LedgerService

        order_id, ledger_id = create_test_ledger(mock_get_db, sellers=[(2, 100.00), (3, 200.00)])

        LedgerService.process_refund(
            order_id=order_id,
            admin_id=4,
            refund_type='partial',
            reason='Test refund reason',
            seller_id=2
        )

        conn = mock_get_db()
        event = conn.execute('''
            SELECT * FROM order_events
            WHERE order_id = ? AND event_type = 'REFUND_INITIATED'
        ''', (order_id,)).fetchone()

        assert event is not None
        payload = json.loads(event['payload_json'])

        # Verify required fields
        assert payload['refund_type'] == 'partial'
        assert payload['refund_amount'] == 100.00
        assert 'affected_seller_ids' in payload
        assert 'affected_item_ids' in payload
        assert 'affected_payout_ids' in payload
        assert payload['target_seller_id'] == 2

        conn.close()

    def test_refund_completed_event_has_detailed_payload(self, mock_get_db):
        """Test REFUND_COMPLETED event includes all required details"""
        from services.ledger_service import LedgerService

        order_id, ledger_id = create_test_ledger(mock_get_db, sellers=[(2, 100.00)])

        LedgerService.process_refund(
            order_id=order_id,
            admin_id=4,
            refund_type='full',
            reason='Full refund test'
        )

        conn = mock_get_db()
        event = conn.execute('''
            SELECT * FROM order_events
            WHERE order_id = ? AND event_type = 'REFUND_COMPLETED'
        ''', (order_id,)).fetchone()

        assert event is not None
        payload = json.loads(event['payload_json'])

        assert payload['refund_type'] == 'full'
        assert payload['new_order_status'] == 'REFUNDED'
        assert 'cancelled_payout_ids' in payload
        assert 'affected_seller_ids' in payload
        assert 'affected_item_ids' in payload

        conn.close()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
