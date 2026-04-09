"""
Tests for the Transaction Ledger System

Tests cover:
a) Per-item fee calculation (percent)
b) Per-item fee calculation (flat)
c) Multi-seller payout aggregation
d) Invariants fail if amounts mismatch
e) Order events written
f) Admin ledger order detail renders
"""
import pytest
import sqlite3
import os
import sys
import json
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def test_db(tmp_path):
    """Create a temporary test database with required tables"""
    db_path = tmp_path / "test_metex.db"

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
            payment_method_type TEXT,
            payment_status TEXT DEFAULT 'unpaid',
            requires_payment_clearance INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Categories table (needed for fee lookup fallback)
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

        -- Ledger tables from migration 021
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

        -- Insert default fee config
        INSERT INTO fee_config (config_key, fee_type, fee_value, description)
        VALUES ('default_platform_fee', 'percent', 2.5, 'Default 2.5% platform fee');

        -- Create test users
        INSERT INTO users (username, email) VALUES ('buyer1', 'buyer1@test.com');
        INSERT INTO users (username, email) VALUES ('seller1', 'seller1@test.com');
        INSERT INTO users (username, email) VALUES ('seller2', 'seller2@test.com');
        INSERT INTO users (username, email, is_admin) VALUES ('admin', 'admin@test.com', 1);

        -- Create test listings (category_id NULL so bucket lookup falls back to global default)
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

    # Mock both the module-level import and any direct imports
    import database
    monkeypatch.setattr(database, 'get_db_connection', get_test_connection)

    # Also patch in ledger_service module which imports get_db_connection directly
    import services.ledger_service as ledger_module
    monkeypatch.setattr(ledger_module, 'get_db_connection', get_test_connection)

    return get_test_connection


class TestFeeCalculation:
    """Test fee calculation logic"""

    def test_percent_fee_calculation(self, mock_get_db):
        """Test a) per-item fee calculation with percent type"""
        from services.ledger_service import LedgerService

        # Test 2.5% fee on $100
        fee = LedgerService.calculate_fee(100.00, 'percent', 2.5)
        assert fee == 2.50

        # Test 2.5% fee on $1000
        fee = LedgerService.calculate_fee(1000.00, 'percent', 2.5)
        assert fee == 25.00

        # Test 5% fee on $250.50
        fee = LedgerService.calculate_fee(250.50, 'percent', 5.0)
        assert fee == 12.53  # 250.50 * 0.05 = 12.525, rounded to 12.53

    def test_flat_fee_calculation(self, mock_get_db):
        """Test b) per-item fee calculation with flat type"""
        from services.ledger_service import LedgerService

        # Test $5 flat fee
        fee = LedgerService.calculate_fee(100.00, 'flat', 5.00)
        assert fee == 5.00

        # Test $10 flat fee on any amount
        fee = LedgerService.calculate_fee(1000.00, 'flat', 10.00)
        assert fee == 10.00

        # Test $2.50 flat fee
        fee = LedgerService.calculate_fee(50.00, 'flat', 2.50)
        assert fee == 2.50


class TestLedgerCreation:
    """Test ledger creation from cart"""

    def test_single_seller_ledger_creation(self, mock_get_db):
        """Test ledger creation with single seller"""
        from services.ledger_service import LedgerService

        conn = mock_get_db()

        # Create an order first
        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 200.00, 'Pending')
        ''')
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Create cart snapshot
        cart_snapshot = [
            {
                'seller_id': 2,
                'listing_id': 1,
                'quantity': 2,
                'unit_price': 100.00
            }
        ]

        # Create ledger
        ledger_id = LedgerService.create_order_ledger_from_cart(
            buyer_id=1,
            cart_snapshot=cart_snapshot,
            payment_method='stripe',
            order_id=order_id
        )

        assert ledger_id is not None

        # Verify ledger record
        conn = mock_get_db()
        ledger = conn.execute('SELECT * FROM orders_ledger WHERE id = ?', (ledger_id,)).fetchone()
        assert ledger is not None
        assert ledger['order_id'] == order_id
        assert ledger['buyer_id'] == 1
        assert ledger['gross_amount'] == 200.00
        assert ledger['platform_fee_amount'] == 5.00  # 2.5% of 200

        # Verify payout record
        payout = conn.execute(
            'SELECT * FROM order_payouts WHERE order_ledger_id = ?', (ledger_id,)
        ).fetchone()
        assert payout is not None
        assert payout['seller_id'] == 2
        assert payout['seller_gross_amount'] == 200.00
        assert payout['fee_amount'] == 5.00
        assert payout['seller_net_amount'] == 195.00

        conn.close()

    def test_multi_seller_payout_aggregation(self, mock_get_db):
        """Test c) multi-seller payout aggregation"""
        from services.ledger_service import LedgerService

        conn = mock_get_db()

        # Create an order
        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 500.00, 'Pending')
        ''')
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Cart with items from 2 sellers
        cart_snapshot = [
            {
                'seller_id': 2,  # seller1
                'listing_id': 1,
                'quantity': 2,
                'unit_price': 100.00  # 200 gross
            },
            {
                'seller_id': 3,  # seller2
                'listing_id': 2,
                'quantity': 1,
                'unit_price': 200.00  # 200 gross
            },
            {
                'seller_id': 2,  # seller1 again (different listing in same order)
                'listing_id': 1,
                'quantity': 1,
                'unit_price': 100.00  # 100 gross
            }
        ]

        ledger_id = LedgerService.create_order_ledger_from_cart(
            buyer_id=1,
            cart_snapshot=cart_snapshot,
            order_id=order_id
        )

        # Verify payouts
        conn = mock_get_db()

        # Seller 2 should have: 300 gross, 7.50 fee (2.5%), 292.50 net
        payout_seller2 = conn.execute('''
            SELECT * FROM order_payouts
            WHERE order_ledger_id = ? AND seller_id = 2
        ''', (ledger_id,)).fetchone()

        assert payout_seller2 is not None
        assert payout_seller2['seller_gross_amount'] == 300.00
        assert payout_seller2['fee_amount'] == 7.50
        assert payout_seller2['seller_net_amount'] == 292.50

        # Seller 3 should have: 200 gross, 5.00 fee (2.5%), 195 net
        payout_seller3 = conn.execute('''
            SELECT * FROM order_payouts
            WHERE order_ledger_id = ? AND seller_id = 3
        ''', (ledger_id,)).fetchone()

        assert payout_seller3 is not None
        assert payout_seller3['seller_gross_amount'] == 200.00
        assert payout_seller3['fee_amount'] == 5.00
        assert payout_seller3['seller_net_amount'] == 195.00

        # Verify total order
        ledger = conn.execute(
            'SELECT * FROM orders_ledger WHERE id = ?', (ledger_id,)
        ).fetchone()
        assert ledger['gross_amount'] == 500.00
        assert ledger['platform_fee_amount'] == 12.50  # 2.5% of 500

        conn.close()


class TestInvariants:
    """Test invariant validation"""

    def test_invariant_gross_amount_mismatch_fails(self, mock_get_db):
        """Test d) invariants fail if amounts mismatch"""
        from services.ledger_service import LedgerService, LedgerInvariantError

        conn = mock_get_db()

        # Create order
        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 100.00, 'Pending')
        ''')
        order_id = cursor.lastrowid

        # Create ledger record with intentionally wrong gross
        cursor = conn.execute('''
            INSERT INTO orders_ledger (order_id, buyer_id, order_status, gross_amount, platform_fee_amount)
            VALUES (?, 1, 'CHECKOUT_INITIATED', 100.00, 2.50)
        ''', (order_id,))
        ledger_id = cursor.lastrowid

        # Create item with wrong gross (50 instead of 100)
        conn.execute('''
            INSERT INTO order_items_ledger
            (order_ledger_id, order_id, seller_id, listing_id, quantity, unit_price,
             gross_amount, fee_type, fee_value, fee_amount, seller_net_amount)
            VALUES (?, ?, 2, 1, 1, 50.00, 50.00, 'percent', 2.5, 1.25, 48.75)
        ''', (ledger_id, order_id))

        # Create payout record
        conn.execute('''
            INSERT INTO order_payouts
            (order_ledger_id, order_id, seller_id, payout_status, seller_gross_amount, fee_amount, seller_net_amount)
            VALUES (?, ?, 2, 'PAYOUT_NOT_READY', 50.00, 1.25, 48.75)
        ''', (ledger_id, order_id))

        conn.commit()
        conn.close()

        # Validation should fail because items sum (50) != order gross (100)
        with pytest.raises(LedgerInvariantError) as exc_info:
            LedgerService.validate_order_invariants(ledger_id)

        assert "sum(items.gross_amount)" in str(exc_info.value)

    def test_invariant_seller_net_mismatch_fails(self, mock_get_db):
        """Test invariant fails when seller net amounts don't match"""
        from services.ledger_service import LedgerService, LedgerInvariantError

        conn = mock_get_db()

        # Create order
        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 100.00, 'Pending')
        ''')
        order_id = cursor.lastrowid

        # Create ledger with correct gross
        cursor = conn.execute('''
            INSERT INTO orders_ledger (order_id, buyer_id, order_status, gross_amount, platform_fee_amount)
            VALUES (?, 1, 'CHECKOUT_INITIATED', 100.00, 2.50)
        ''', (order_id,))
        ledger_id = cursor.lastrowid

        # Create item with correct values
        conn.execute('''
            INSERT INTO order_items_ledger
            (order_ledger_id, order_id, seller_id, listing_id, quantity, unit_price,
             gross_amount, fee_type, fee_value, fee_amount, seller_net_amount)
            VALUES (?, ?, 2, 1, 1, 100.00, 100.00, 'percent', 2.5, 2.50, 97.50)
        ''', (ledger_id, order_id))

        # Create payout with WRONG seller net (80 instead of 97.50)
        conn.execute('''
            INSERT INTO order_payouts
            (order_ledger_id, order_id, seller_id, payout_status, seller_gross_amount, fee_amount, seller_net_amount)
            VALUES (?, ?, 2, 'PAYOUT_NOT_READY', 100.00, 2.50, 80.00)
        ''', (ledger_id, order_id))

        conn.commit()
        conn.close()

        # Validation should fail
        with pytest.raises(LedgerInvariantError) as exc_info:
            LedgerService.validate_order_invariants(ledger_id)

        assert "seller" in str(exc_info.value).lower()


class TestOrderEvents:
    """Test order event logging"""

    def test_events_written_on_creation(self, mock_get_db):
        """Test e) order events are written during ledger creation"""
        from services.ledger_service import LedgerService

        conn = mock_get_db()

        # Create order
        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 100.00, 'Pending')
        ''')
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Create ledger
        cart_snapshot = [
            {
                'seller_id': 2,
                'listing_id': 1,
                'quantity': 1,
                'unit_price': 100.00
            }
        ]

        LedgerService.create_order_ledger_from_cart(
            buyer_id=1,
            cart_snapshot=cart_snapshot,
            order_id=order_id
        )

        # Check events
        conn = mock_get_db()
        events = conn.execute('''
            SELECT * FROM order_events WHERE order_id = ? ORDER BY created_at
        ''', (order_id,)).fetchall()

        assert len(events) >= 2

        event_types = [e['event_type'] for e in events]
        assert 'ORDER_CREATED' in event_types
        assert 'LEDGER_CREATED' in event_types

        # Check ORDER_CREATED event payload
        order_created = next(e for e in events if e['event_type'] == 'ORDER_CREATED')
        payload = json.loads(order_created['payload_json'])
        assert payload['buyer_id'] == 1
        assert payload['gross_amount'] == 100.00

        conn.close()

    def test_log_order_event(self, mock_get_db):
        """Test manual event logging"""
        from services.ledger_service import LedgerService

        conn = mock_get_db()

        # Create order
        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 100.00, 'Pending')
        ''')
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Log custom event
        LedgerService.log_order_event(
            order_id=order_id,
            event_type='PAYMENT_INITIATED',
            actor_type='buyer',
            actor_id=1,
            payload={'payment_method': 'stripe', 'amount': 100.00}
        )

        # Verify event
        conn = mock_get_db()
        event = conn.execute('''
            SELECT * FROM order_events WHERE order_id = ? AND event_type = ?
        ''', (order_id, 'PAYMENT_INITIATED')).fetchone()

        assert event is not None
        assert event['actor_type'] == 'buyer'
        assert event['actor_id'] == 1

        payload = json.loads(event['payload_json'])
        assert payload['payment_method'] == 'stripe'

        conn.close()


class TestAdminLedger:
    """Test admin ledger functionality"""

    def test_get_order_ledger(self, mock_get_db):
        """Test getting full ledger data for an order"""
        from services.ledger_service import LedgerService

        conn = mock_get_db()

        # Create order
        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 300.00, 'Pending')
        ''')
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Create ledger with multiple sellers
        cart_snapshot = [
            {'seller_id': 2, 'listing_id': 1, 'quantity': 1, 'unit_price': 100.00},
            {'seller_id': 3, 'listing_id': 2, 'quantity': 1, 'unit_price': 200.00}
        ]

        LedgerService.create_order_ledger_from_cart(
            buyer_id=1,
            cart_snapshot=cart_snapshot,
            order_id=order_id
        )

        # Get ledger data (this would be used by admin detail view)
        ledger_data = LedgerService.get_order_ledger(order_id)

        assert ledger_data is not None
        assert 'order' in ledger_data
        assert 'items' in ledger_data
        assert 'payouts' in ledger_data
        assert 'events' in ledger_data

        # Verify order header
        assert ledger_data['order']['gross_amount'] == 300.00
        assert ledger_data['order']['buyer_id'] == 1

        # Verify items
        assert len(ledger_data['items']) == 2

        # Verify payouts (one per seller)
        assert len(ledger_data['payouts']) == 2
        seller_ids = [p['seller_id'] for p in ledger_data['payouts']]
        assert 2 in seller_ids
        assert 3 in seller_ids

        # Verify events
        assert len(ledger_data['events']) >= 2

    def test_get_orders_ledger_list_with_filters(self, mock_get_db):
        """Test f) admin ledger order list with filters (testing query building)"""
        from services.ledger_service import LedgerService

        conn = mock_get_db()

        # Create multiple orders
        for i in range(3):
            cursor = conn.execute('''
                INSERT INTO orders (buyer_id, total_price, status)
                VALUES (1, ?, 'Pending')
            ''', ((i + 1) * 100.00,))
            order_id = cursor.lastrowid
            conn.commit()

            conn_new = mock_get_db()
            cart_snapshot = [
                {'seller_id': 2, 'listing_id': 1, 'quantity': i + 1, 'unit_price': 100.00}
            ]
            LedgerService.create_order_ledger_from_cart(
                buyer_id=1,
                cart_snapshot=cart_snapshot,
                order_id=order_id
            )
            conn_new.close()

        conn.close()

        # Test unfiltered list
        orders = LedgerService.get_orders_ledger_list()
        assert len(orders) == 3

        # Test filter by min gross
        orders = LedgerService.get_orders_ledger_list(min_gross=150)
        assert len(orders) == 2  # 200 and 300

        # Test filter by max gross
        orders = LedgerService.get_orders_ledger_list(max_gross=150)
        assert len(orders) == 1  # 100

        # Test filter by status
        orders = LedgerService.get_orders_ledger_list(status_filter='CHECKOUT_INITIATED')
        assert len(orders) == 3

        # Test pagination
        orders = LedgerService.get_orders_ledger_list(limit=2)
        assert len(orders) == 2


class TestCustomFeePerItem:
    """Test custom fee configuration per item"""

    def test_custom_fee_per_item(self, mock_get_db):
        """Test items with custom fee types/values"""
        from services.ledger_service import LedgerService

        conn = mock_get_db()

        # Create order
        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 300.00, 'Pending')
        ''')
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Cart with custom fees
        cart_snapshot = [
            {
                'seller_id': 2,
                'listing_id': 1,
                'quantity': 1,
                'unit_price': 100.00,
                'fee_type': 'percent',
                'fee_value': 5.0  # 5% instead of default 2.5%
            },
            {
                'seller_id': 3,
                'listing_id': 2,
                'quantity': 1,
                'unit_price': 200.00,
                'fee_type': 'flat',
                'fee_value': 3.00  # $3 flat instead of percent
            }
        ]

        ledger_id = LedgerService.create_order_ledger_from_cart(
            buyer_id=1,
            cart_snapshot=cart_snapshot,
            order_id=order_id
        )

        # Verify item fees
        conn = mock_get_db()

        items = conn.execute('''
            SELECT * FROM order_items_ledger WHERE order_ledger_id = ?
        ''', (ledger_id,)).fetchall()

        # Item 1: 5% of 100 = 5.00
        item1 = next(i for i in items if i['listing_id'] == 1)
        assert item1['fee_type'] == 'percent'
        assert item1['fee_value'] == 5.0
        assert item1['fee_amount'] == 5.00
        assert item1['seller_net_amount'] == 95.00

        # Item 2: $3 flat
        item2 = next(i for i in items if i['listing_id'] == 2)
        assert item2['fee_type'] == 'flat'
        assert item2['fee_value'] == 3.00
        assert item2['fee_amount'] == 3.00
        assert item2['seller_net_amount'] == 197.00

        # Total platform fee should be 5 + 3 = 8
        ledger = conn.execute('SELECT * FROM orders_ledger WHERE id = ?', (ledger_id,)).fetchone()
        assert ledger['platform_fee_amount'] == 8.00

        conn.close()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
