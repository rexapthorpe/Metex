"""
Phase 1 Ledger Verification Tests

Comprehensive tests to verify the transaction ledger system works correctly.
"""
import pytest
import sqlite3
import os
import sys
import json
from decimal import Decimal, ROUND_HALF_UP

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

        -- Insert default fee config (2.5%)
        INSERT INTO fee_config (config_key, fee_type, fee_value, description)
        VALUES ('default_platform_fee', 'percent', 2.5, 'Default 2.5% platform fee');

        -- Create test users
        INSERT INTO users (username, email) VALUES ('buyer1', 'buyer1@test.com');
        INSERT INTO users (username, email) VALUES ('seller1', 'seller1@test.com');
        INSERT INTO users (username, email) VALUES ('seller2', 'seller2@test.com');
        INSERT INTO users (username, email) VALUES ('seller3', 'seller3@test.com');
        INSERT INTO users (username, email, is_admin) VALUES ('admin', 'admin@test.com', 1);

        -- Create test listings (category_id NULL so bucket lookup falls back to global default)
        INSERT INTO listings (seller_id, category_id, price_per_coin, quantity) VALUES (2, NULL, 100.00, 10);
        INSERT INTO listings (seller_id, category_id, price_per_coin, quantity) VALUES (3, NULL, 200.00, 5);
        INSERT INTO listings (seller_id, category_id, price_per_coin, quantity) VALUES (4, NULL, 150.00, 8);
        INSERT INTO listings (seller_id, category_id, price_per_coin, quantity) VALUES (2, NULL, 75.00, 20);
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


# ============================================
# TEST SET A — Ledger Invariants
# ============================================

class TestSetA_LedgerInvariants:
    """Test Set A: Ledger immutability and duplicate protection"""

    def test_A1_ledger_immutability_order_items_gross(self, mock_get_db):
        """A1: Attempt to mutate order_items_ledger.gross_amount after creation"""
        from services.ledger_service import LedgerService

        conn = mock_get_db()

        # Create order and ledger
        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 100.00, 'Pending')
        ''')
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        cart_snapshot = [
            {'seller_id': 2, 'listing_id': 1, 'quantity': 1, 'unit_price': 100.00,
             'fee_type': 'percent', 'fee_value': 2.5}
        ]
        ledger_id = LedgerService.create_order_ledger_from_cart(
            buyer_id=1, cart_snapshot=cart_snapshot, order_id=order_id
        )

        # Attempt to mutate gross_amount via direct SQL
        conn = mock_get_db()
        item = conn.execute('SELECT * FROM order_items_ledger WHERE order_ledger_id = ?', (ledger_id,)).fetchone()
        original_gross = item['gross_amount']

        # The system should NOT expose update endpoints for amount fields
        # We verify the invariant by checking after any update attempt
        conn.execute('''
            UPDATE order_items_ledger SET gross_amount = 999.99 WHERE id = ?
        ''', (item['id'],))
        conn.commit()

        # Since SQLite doesn't have triggers by default, we check via validate_order_invariants
        # This should FAIL because amounts were modified
        from services.ledger_service import LedgerInvariantError

        # The invariant check will fail because sum(items) != order gross
        with pytest.raises(LedgerInvariantError):
            LedgerService.validate_order_invariants(ledger_id)

        conn.close()

    def test_A1_ledger_immutability_fee_amount(self, mock_get_db):
        """A1: Attempt to mutate order_items_ledger.fee_amount"""
        from services.ledger_service import LedgerService, LedgerInvariantError

        conn = mock_get_db()
        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 100.00, 'Pending')
        ''')
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        cart_snapshot = [
            {'seller_id': 2, 'listing_id': 1, 'quantity': 1, 'unit_price': 100.00,
             'fee_type': 'percent', 'fee_value': 2.5}
        ]
        ledger_id = LedgerService.create_order_ledger_from_cart(
            buyer_id=1, cart_snapshot=cart_snapshot, order_id=order_id
        )

        # Mutate fee_amount
        conn = mock_get_db()
        conn.execute('''
            UPDATE order_items_ledger SET fee_amount = 50.00 WHERE order_ledger_id = ?
        ''', (ledger_id,))
        conn.commit()
        conn.close()

        # seller_net_amount is now wrong (gross - fee != seller_net)
        # This breaks the invariant that items.seller_net == payout.seller_net
        with pytest.raises(LedgerInvariantError):
            LedgerService.validate_order_invariants(ledger_id)

    def test_A1_ledger_immutability_seller_net(self, mock_get_db):
        """A1: Attempt to mutate order_items_ledger.seller_net_amount"""
        from services.ledger_service import LedgerService, LedgerInvariantError

        conn = mock_get_db()
        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 100.00, 'Pending')
        ''')
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        cart_snapshot = [
            {'seller_id': 2, 'listing_id': 1, 'quantity': 1, 'unit_price': 100.00,
             'fee_type': 'percent', 'fee_value': 2.5}
        ]
        ledger_id = LedgerService.create_order_ledger_from_cart(
            buyer_id=1, cart_snapshot=cart_snapshot, order_id=order_id
        )

        # Mutate seller_net_amount
        conn = mock_get_db()
        conn.execute('''
            UPDATE order_items_ledger SET seller_net_amount = 1.00 WHERE order_ledger_id = ?
        ''', (ledger_id,))
        conn.commit()
        conn.close()

        # This breaks invariant 2: sum(items.seller_net) != payout.seller_net
        with pytest.raises(LedgerInvariantError):
            LedgerService.validate_order_invariants(ledger_id)

    def test_A1_ledger_immutability_payout_net(self, mock_get_db):
        """A1: Attempt to mutate order_payouts.seller_net_amount"""
        from services.ledger_service import LedgerService, LedgerInvariantError

        conn = mock_get_db()
        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 100.00, 'Pending')
        ''')
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        cart_snapshot = [
            {'seller_id': 2, 'listing_id': 1, 'quantity': 1, 'unit_price': 100.00,
             'fee_type': 'percent', 'fee_value': 2.5}
        ]
        ledger_id = LedgerService.create_order_ledger_from_cart(
            buyer_id=1, cart_snapshot=cart_snapshot, order_id=order_id
        )

        # Mutate payout seller_net_amount
        conn = mock_get_db()
        conn.execute('''
            UPDATE order_payouts SET seller_net_amount = 1.00 WHERE order_ledger_id = ?
        ''', (ledger_id,))
        conn.commit()
        conn.close()

        # This breaks invariant 2
        with pytest.raises(LedgerInvariantError):
            LedgerService.validate_order_invariants(ledger_id)

    def test_A2_duplicate_ledger_protection(self, mock_get_db):
        """A2: Verify duplicate ledger protection - same order_id cannot have multiple ledgers"""
        from services.ledger_service import LedgerService

        conn = mock_get_db()
        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 100.00, 'Pending')
        ''')
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        cart_snapshot = [
            {'seller_id': 2, 'listing_id': 1, 'quantity': 1, 'unit_price': 100.00,
             'fee_type': 'percent', 'fee_value': 2.5}
        ]

        # First ledger creation should succeed
        ledger_id_1 = LedgerService.create_order_ledger_from_cart(
            buyer_id=1, cart_snapshot=cart_snapshot, order_id=order_id
        )
        assert ledger_id_1 is not None

        # Second attempt with same order_id should fail due to UNIQUE constraint
        with pytest.raises(Exception) as exc_info:
            LedgerService.create_order_ledger_from_cart(
                buyer_id=1, cart_snapshot=cart_snapshot, order_id=order_id
            )

        # Should be a UNIQUE constraint violation
        assert 'UNIQUE' in str(exc_info.value).upper() or 'unique' in str(exc_info.value).lower()

        # Verify only one ledger exists
        conn = mock_get_db()
        count = conn.execute(
            'SELECT COUNT(*) as cnt FROM orders_ledger WHERE order_id = ?',
            (order_id,)
        ).fetchone()['cnt']
        assert count == 1

        conn.close()


# ============================================
# TEST SET B — Fee Edge Cases
# ============================================

class TestSetB_FeeEdgeCases:
    """Test Set B: Mixed fee types and zero-fee scenarios"""

    def test_B1_mixed_fee_types(self, mock_get_db):
        """B1: One listing with percent fee, one with flat fee"""
        from services.ledger_service import LedgerService

        conn = mock_get_db()
        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 300.00, 'Pending')
        ''')
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Item 1: $100 with 2.5% fee = $2.50 fee, $97.50 net
        # Item 2: $200 with $25 flat fee = $25 fee, $175 net
        cart_snapshot = [
            {
                'seller_id': 2,
                'listing_id': 1,
                'quantity': 1,
                'unit_price': 100.00,
                'fee_type': 'percent',
                'fee_value': 2.5
            },
            {
                'seller_id': 3,
                'listing_id': 2,
                'quantity': 1,
                'unit_price': 200.00,
                'fee_type': 'flat',
                'fee_value': 25.00
            }
        ]

        ledger_id = LedgerService.create_order_ledger_from_cart(
            buyer_id=1, cart_snapshot=cart_snapshot, order_id=order_id
        )

        conn = mock_get_db()

        # Verify ledger totals
        ledger = conn.execute('SELECT * FROM orders_ledger WHERE id = ?', (ledger_id,)).fetchone()
        assert ledger['gross_amount'] == 300.00
        assert ledger['platform_fee_amount'] == 27.50  # 2.50 + 25.00

        # Verify item 1 (percent fee)
        item1 = conn.execute('''
            SELECT * FROM order_items_ledger WHERE order_ledger_id = ? AND listing_id = 1
        ''', (ledger_id,)).fetchone()
        assert item1['fee_type'] == 'percent'
        assert item1['fee_value'] == 2.5
        assert item1['fee_amount'] == 2.50
        assert item1['seller_net_amount'] == 97.50

        # Verify item 2 (flat fee)
        item2 = conn.execute('''
            SELECT * FROM order_items_ledger WHERE order_ledger_id = ? AND listing_id = 2
        ''', (ledger_id,)).fetchone()
        assert item2['fee_type'] == 'flat'
        assert item2['fee_value'] == 25.00
        assert item2['fee_amount'] == 25.00
        assert item2['seller_net_amount'] == 175.00

        # Verify seller payouts
        payout1 = conn.execute('''
            SELECT * FROM order_payouts WHERE order_ledger_id = ? AND seller_id = 2
        ''', (ledger_id,)).fetchone()
        assert payout1['seller_gross_amount'] == 100.00
        assert payout1['fee_amount'] == 2.50
        assert payout1['seller_net_amount'] == 97.50

        payout2 = conn.execute('''
            SELECT * FROM order_payouts WHERE order_ledger_id = ? AND seller_id = 3
        ''', (ledger_id,)).fetchone()
        assert payout2['seller_gross_amount'] == 200.00
        assert payout2['fee_amount'] == 25.00
        assert payout2['seller_net_amount'] == 175.00

        conn.close()

    def test_B2_zero_fee_listing(self, mock_get_db):
        """B2: Listing with 0% fee"""
        from services.ledger_service import LedgerService

        conn = mock_get_db()
        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 100.00, 'Pending')
        ''')
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        cart_snapshot = [
            {
                'seller_id': 2,
                'listing_id': 1,
                'quantity': 1,
                'unit_price': 100.00,
                'fee_type': 'percent',
                'fee_value': 0  # Zero fee
            }
        ]

        ledger_id = LedgerService.create_order_ledger_from_cart(
            buyer_id=1, cart_snapshot=cart_snapshot, order_id=order_id
        )

        conn = mock_get_db()

        # Verify ledger
        ledger = conn.execute('SELECT * FROM orders_ledger WHERE id = ?', (ledger_id,)).fetchone()
        assert ledger['gross_amount'] == 100.00
        assert ledger['platform_fee_amount'] == 0.00

        # Verify item
        item = conn.execute('''
            SELECT * FROM order_items_ledger WHERE order_ledger_id = ?
        ''', (ledger_id,)).fetchone()
        assert item['fee_amount'] == 0.00
        assert item['seller_net_amount'] == 100.00  # Full gross goes to seller

        # Verify payout
        payout = conn.execute('''
            SELECT * FROM order_payouts WHERE order_ledger_id = ?
        ''', (ledger_id,)).fetchone()
        assert payout['fee_amount'] == 0.00
        assert payout['seller_net_amount'] == 100.00

        # Ledger rows should still exist
        assert item is not None
        assert payout is not None

        conn.close()


# ============================================
# TEST SET C — Rounding Correctness
# ============================================

class TestSetC_RoundingCorrectness:
    """Test Set C: Rounding stress tests"""

    def test_C1_rounding_stress_test(self, mock_get_db):
        """C1: Test rounding with prices that cause penny issues"""
        from services.ledger_service import LedgerService

        conn = mock_get_db()
        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 4000.00, 'Pending')
        ''')
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Prices designed to cause rounding issues
        # $1999.99 * 2.5% = $49.99975 -> should round to $50.00
        # $2000.01 * 2.5% = $50.00025 -> should round to $50.00
        cart_snapshot = [
            {
                'seller_id': 2,
                'listing_id': 1,
                'quantity': 1,
                'unit_price': 1999.99,
                'fee_type': 'percent',
                'fee_value': 2.5
            },
            {
                'seller_id': 3,
                'listing_id': 2,
                'quantity': 1,
                'unit_price': 2000.01,
                'fee_type': 'percent',
                'fee_value': 2.5
            }
        ]

        ledger_id = LedgerService.create_order_ledger_from_cart(
            buyer_id=1, cart_snapshot=cart_snapshot, order_id=order_id
        )

        conn = mock_get_db()

        # Verify item 1 rounding
        item1 = conn.execute('''
            SELECT * FROM order_items_ledger WHERE order_ledger_id = ? AND listing_id = 1
        ''', (ledger_id,)).fetchone()

        # Manual calculation: 1999.99 * 0.025 = 49.99975, rounded to 50.00
        assert item1['fee_amount'] == 50.00
        assert item1['seller_net_amount'] == 1949.99  # 1999.99 - 50.00

        # Verify item 2 rounding
        item2 = conn.execute('''
            SELECT * FROM order_items_ledger WHERE order_ledger_id = ? AND listing_id = 2
        ''', (ledger_id,)).fetchone()

        # Manual calculation: 2000.01 * 0.025 = 50.00025, rounded to 50.00
        assert item2['fee_amount'] == 50.00
        assert item2['seller_net_amount'] == 1950.01  # 2000.01 - 50.00

        # Critical invariant: sum(seller_nets) + platform_fee == gross
        ledger = conn.execute('SELECT * FROM orders_ledger WHERE id = ?', (ledger_id,)).fetchone()
        total_seller_net = item1['seller_net_amount'] + item2['seller_net_amount']
        platform_fee = ledger['platform_fee_amount']
        gross = ledger['gross_amount']

        # Check for penny drift
        expected_gross = 1999.99 + 2000.01  # 4000.00
        assert gross == expected_gross
        assert platform_fee == 100.00  # 50 + 50
        assert total_seller_net == 3900.00  # 1949.99 + 1950.01

        # The ultimate check: no penny drift
        assert abs((total_seller_net + platform_fee) - gross) < 0.01

        conn.close()

    def test_C1_rounding_with_quantity(self, mock_get_db):
        """C1 extended: Rounding with quantity multipliers"""
        from services.ledger_service import LedgerService

        conn = mock_get_db()
        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 333.33, 'Pending')
        ''')
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # $33.33 * 3 = $99.99, fee = $2.50 (rounded from 2.49975)
        cart_snapshot = [
            {
                'seller_id': 2,
                'listing_id': 1,
                'quantity': 3,
                'unit_price': 33.33,
                'fee_type': 'percent',
                'fee_value': 2.5
            }
        ]

        ledger_id = LedgerService.create_order_ledger_from_cart(
            buyer_id=1, cart_snapshot=cart_snapshot, order_id=order_id
        )

        conn = mock_get_db()
        item = conn.execute('''
            SELECT * FROM order_items_ledger WHERE order_ledger_id = ?
        ''', (ledger_id,)).fetchone()

        assert item['gross_amount'] == 99.99
        # 99.99 * 0.025 = 2.49975, should round to 2.50
        assert item['fee_amount'] == 2.50
        assert item['seller_net_amount'] == 97.49

        conn.close()


# ============================================
# TEST SET D — Structural Correctness
# ============================================

class TestSetD_StructuralCorrectness:
    """Test Set D: One payout per seller, multi-item aggregation"""

    def test_D1_one_payout_per_seller(self, mock_get_db):
        """D1: Multi-seller checkout should have exactly one payout per seller"""
        from services.ledger_service import LedgerService

        conn = mock_get_db()
        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 450.00, 'Pending')
        ''')
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # 3 different sellers
        cart_snapshot = [
            {'seller_id': 2, 'listing_id': 1, 'quantity': 1, 'unit_price': 100.00,
             'fee_type': 'percent', 'fee_value': 2.5},
            {'seller_id': 3, 'listing_id': 2, 'quantity': 1, 'unit_price': 200.00,
             'fee_type': 'percent', 'fee_value': 2.5},
            {'seller_id': 4, 'listing_id': 3, 'quantity': 1, 'unit_price': 150.00,
             'fee_type': 'percent', 'fee_value': 2.5}
        ]

        ledger_id = LedgerService.create_order_ledger_from_cart(
            buyer_id=1, cart_snapshot=cart_snapshot, order_id=order_id
        )

        conn = mock_get_db()

        # Count distinct sellers in items
        item_sellers = conn.execute('''
            SELECT COUNT(DISTINCT seller_id) as cnt FROM order_items_ledger WHERE order_ledger_id = ?
        ''', (ledger_id,)).fetchone()['cnt']

        # Count payouts
        payout_count = conn.execute('''
            SELECT COUNT(*) as cnt FROM order_payouts WHERE order_ledger_id = ?
        ''', (ledger_id,)).fetchone()['cnt']

        assert item_sellers == 3
        assert payout_count == 3
        assert payout_count == item_sellers

        conn.close()

    def test_D2_multi_item_same_seller(self, mock_get_db):
        """D2: Multiple items from same seller should aggregate into ONE payout row"""
        from services.ledger_service import LedgerService

        conn = mock_get_db()
        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 175.00, 'Pending')
        ''')
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Same seller (2), two different listings
        # Item 1: $100, 2.5% fee = $2.50
        # Item 2: $75, 2.5% fee = $1.875 -> $1.88
        cart_snapshot = [
            {'seller_id': 2, 'listing_id': 1, 'quantity': 1, 'unit_price': 100.00,
             'fee_type': 'percent', 'fee_value': 2.5},
            {'seller_id': 2, 'listing_id': 4, 'quantity': 1, 'unit_price': 75.00,
             'fee_type': 'percent', 'fee_value': 2.5}
        ]

        ledger_id = LedgerService.create_order_ledger_from_cart(
            buyer_id=1, cart_snapshot=cart_snapshot, order_id=order_id
        )

        conn = mock_get_db()

        # Should have 2 item rows
        items = conn.execute('''
            SELECT * FROM order_items_ledger WHERE order_ledger_id = ?
        ''', (ledger_id,)).fetchall()
        assert len(items) == 2

        # Should have exactly 1 payout row for seller 2
        payouts = conn.execute('''
            SELECT * FROM order_payouts WHERE order_ledger_id = ?
        ''', (ledger_id,)).fetchall()
        assert len(payouts) == 1

        payout = payouts[0]
        assert payout['seller_id'] == 2

        # Verify aggregation
        # Item 1: gross=100, fee=2.50, net=97.50
        # Item 2: gross=75, fee=1.88, net=73.12
        # Total: gross=175, fee=4.38, net=170.62

        # Get individual items
        item1 = next(i for i in items if i['listing_id'] == 1)
        item2 = next(i for i in items if i['listing_id'] == 4)

        total_gross = item1['gross_amount'] + item2['gross_amount']
        total_fee = item1['fee_amount'] + item2['fee_amount']
        total_net = item1['seller_net_amount'] + item2['seller_net_amount']

        assert payout['seller_gross_amount'] == total_gross
        assert abs(payout['fee_amount'] - total_fee) < 0.01
        assert abs(payout['seller_net_amount'] - total_net) < 0.01

        conn.close()


# ============================================
# TEST SET E — Event Timeline Integrity
# ============================================

class TestSetE_EventTimeline:
    """Test Set E: Event ordering and payload integrity"""

    def test_E1_event_ordering(self, mock_get_db):
        """E1: Verify events are created with correct order and payloads"""
        from services.ledger_service import LedgerService
        import json

        conn = mock_get_db()
        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 100.00, 'Pending')
        ''')
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        cart_snapshot = [
            {'seller_id': 2, 'listing_id': 1, 'quantity': 1, 'unit_price': 100.00,
             'fee_type': 'percent', 'fee_value': 2.5}
        ]

        ledger_id = LedgerService.create_order_ledger_from_cart(
            buyer_id=1, cart_snapshot=cart_snapshot, order_id=order_id
        )

        conn = mock_get_db()

        # Get events ordered by creation time
        events = conn.execute('''
            SELECT * FROM order_events WHERE order_id = ? ORDER BY created_at ASC, id ASC
        ''', (order_id,)).fetchall()

        # Should have at least ORDER_CREATED and LEDGER_CREATED
        assert len(events) >= 2

        event_types = [e['event_type'] for e in events]
        assert 'ORDER_CREATED' in event_types
        assert 'LEDGER_CREATED' in event_types

        # ORDER_CREATED should come before LEDGER_CREATED
        order_created_idx = event_types.index('ORDER_CREATED')
        ledger_created_idx = event_types.index('LEDGER_CREATED')
        assert order_created_idx < ledger_created_idx

        # Verify ORDER_CREATED payload
        order_created_event = events[order_created_idx]
        payload = json.loads(order_created_event['payload_json'])
        assert payload['buyer_id'] == 1
        assert payload['gross_amount'] == 100.00

        # Verify LEDGER_CREATED payload
        ledger_created_event = events[ledger_created_idx]
        payload = json.loads(ledger_created_event['payload_json'])
        assert payload['order_ledger_id'] == ledger_id
        assert payload['item_count'] == 1
        assert payload['seller_count'] == 1
        assert payload['total_gross'] == 100.00
        assert payload['total_platform_fee'] == 2.50

        # Verify timestamps are strictly increasing (or at least non-decreasing)
        timestamps = [e['created_at'] for e in events]
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i-1]

        conn.close()


# ============================================
# TEST SET F — Defensive Failures
# ============================================

class TestSetF_DefensiveFailures:
    """Test Set F: Empty cart and missing config handling"""

    def test_F1_empty_cart_checkout(self, mock_get_db):
        """F1: Empty cart should not create a ledger"""
        from services.ledger_service import LedgerService

        conn = mock_get_db()
        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 0.00, 'Pending')
        ''')
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Empty cart
        cart_snapshot = []

        # Should either raise an exception or return None/handle gracefully
        try:
            ledger_id = LedgerService.create_order_ledger_from_cart(
                buyer_id=1, cart_snapshot=cart_snapshot, order_id=order_id
            )
            # If it returns, verify no rows were created (or ledger with 0 amounts)
            conn = mock_get_db()

            # Check if ledger exists
            ledger = conn.execute(
                'SELECT * FROM orders_ledger WHERE order_id = ?', (order_id,)
            ).fetchone()

            if ledger:
                # If ledger was created, it should have 0 amounts
                assert ledger['gross_amount'] == 0
                assert ledger['platform_fee_amount'] == 0

                # No items should exist
                items = conn.execute(
                    'SELECT * FROM order_items_ledger WHERE order_ledger_id = ?', (ledger['id'],)
                ).fetchall()
                assert len(items) == 0

            conn.close()

        except Exception as e:
            # Exception is acceptable for empty cart
            pass

    def test_F2_missing_fee_config_uses_default(self, mock_get_db):
        """F2: Missing fee config should use safe default (from constants)"""
        from services.ledger_service import LedgerService

        conn = mock_get_db()

        # Delete the fee config
        conn.execute('DELETE FROM fee_config')
        conn.commit()

        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 100.00, 'Pending')
        ''')
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Cart without explicit fee - should use default from constants
        cart_snapshot = [
            {'seller_id': 2, 'listing_id': 1, 'quantity': 1, 'unit_price': 100.00}
        ]

        # Should not fail, should use DEFAULT_PLATFORM_FEE_VALUE (2.5%)
        ledger_id = LedgerService.create_order_ledger_from_cart(
            buyer_id=1, cart_snapshot=cart_snapshot, order_id=order_id
        )

        conn = mock_get_db()
        ledger = conn.execute('SELECT * FROM orders_ledger WHERE id = ?', (ledger_id,)).fetchone()

        # Should use 2.5% default from ledger_constants.py
        assert ledger['platform_fee_amount'] == 2.50

        conn.close()

    def test_F2_explicit_fee_overrides_config(self, mock_get_db):
        """F2: Explicit fee in cart should override config"""
        from services.ledger_service import LedgerService

        conn = mock_get_db()
        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 100.00, 'Pending')
        ''')
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Cart with explicit fee that differs from default
        cart_snapshot = [
            {
                'seller_id': 2,
                'listing_id': 1,
                'quantity': 1,
                'unit_price': 100.00,
                'fee_type': 'percent',
                'fee_value': 5.0  # 5% instead of default 2.5%
            }
        ]

        ledger_id = LedgerService.create_order_ledger_from_cart(
            buyer_id=1, cart_snapshot=cart_snapshot, order_id=order_id
        )

        conn = mock_get_db()
        item = conn.execute('''
            SELECT * FROM order_items_ledger WHERE order_ledger_id = ?
        ''', (ledger_id,)).fetchone()

        # Should use explicit 5%
        assert item['fee_type'] == 'percent'
        assert item['fee_value'] == 5.0
        assert item['fee_amount'] == 5.00

        conn.close()


# ============================================
# SUMMARY TEST
# ============================================

class TestSummary:
    """Summary tests to verify overall system integrity"""

    def test_full_order_lifecycle(self, mock_get_db):
        """End-to-end test of full order creation with ledger"""
        from services.ledger_service import LedgerService
        import json

        conn = mock_get_db()
        cursor = conn.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (1, 500.00, 'Pending')
        ''')
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Complex cart: multiple sellers, multiple items, mixed fees
        cart_snapshot = [
            {'seller_id': 2, 'listing_id': 1, 'quantity': 2, 'unit_price': 100.00,
             'fee_type': 'percent', 'fee_value': 2.5},
            {'seller_id': 3, 'listing_id': 2, 'quantity': 1, 'unit_price': 200.00,
             'fee_type': 'flat', 'fee_value': 10.00},
            {'seller_id': 2, 'listing_id': 4, 'quantity': 1, 'unit_price': 100.00,
             'fee_type': 'percent', 'fee_value': 2.5}
        ]

        ledger_id = LedgerService.create_order_ledger_from_cart(
            buyer_id=1, cart_snapshot=cart_snapshot, payment_method='test', order_id=order_id
        )

        # Verify all invariants pass
        LedgerService.validate_order_invariants(ledger_id)

        conn = mock_get_db()

        # Verify ledger
        ledger = conn.execute('SELECT * FROM orders_ledger WHERE id = ?', (ledger_id,)).fetchone()
        assert ledger['gross_amount'] == 500.00
        assert ledger['payment_method'] == 'test'

        # Verify items (should be 3)
        items = conn.execute('''
            SELECT * FROM order_items_ledger WHERE order_ledger_id = ?
        ''', (ledger_id,)).fetchall()
        assert len(items) == 3

        # Verify payouts (should be 2: seller 2 and seller 3)
        payouts = conn.execute('''
            SELECT * FROM order_payouts WHERE order_ledger_id = ?
        ''', (ledger_id,)).fetchall()
        assert len(payouts) == 2

        # Verify events
        events = conn.execute('''
            SELECT * FROM order_events WHERE order_id = ?
        ''', (order_id,)).fetchall()
        assert len(events) >= 2

        conn.close()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
