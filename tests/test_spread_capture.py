"""
Tests for Spread Capture Accounting

Spread capture occurs when a buyer's bid price exceeds the seller's ask price.
The difference (spread) is platform revenue distinct from the percentage/flat fee.

Scenarios:
  SC-1  No spread — direct checkout, amounts match, recon is MATCHED (not AMOUNT_MISMATCH)
  SC-2  Bid fill with spread — gross < total_price, spread explains the gap, MATCHED
  SC-3  Spread + tax + card fee — full equation reconciles correctly
  SC-4  Unexplained delta — spread stored but real mismatch remains, AMOUNT_MISMATCH
  SC-5  Seller net uses seller price, not buyer price (spread not passed to seller)
  SC-6  Revenue reporting — spread_capture_amount queryable and summed correctly
  SC-7  Zero spread stored — backward compat, existing orders still reconcile
"""
import pytest
import sqlite3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def test_db(tmp_path):
    """In-memory SQLite DB with ledger schema including spread capture columns."""
    db_path = tmp_path / "test_spread.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT, email TEXT, is_admin INTEGER DEFAULT 0
        );
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            buyer_id INTEGER,
            total_price REAL,
            status TEXT DEFAULT 'Pending',
            shipping_address TEXT,
            payment_method_type TEXT,
            payment_status TEXT DEFAULT 'unpaid',
            requires_payment_clearance INTEGER DEFAULT 0,
            buyer_card_fee REAL NOT NULL DEFAULT 0.0,
            tax_amount REAL NOT NULL DEFAULT 0.0,
            tax_rate REAL NOT NULL DEFAULT 0.0,
            stripe_payment_intent_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bucket_id INTEGER, name TEXT,
            platform_fee_type TEXT, platform_fee_value REAL, fee_updated_at TIMESTAMP
        );
        CREATE TABLE listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER, category_id INTEGER,
            price_per_coin REAL, quantity INTEGER, active INTEGER DEFAULT 1
        );
        CREATE TABLE order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER, listing_id INTEGER, quantity INTEGER,
            price_each REAL, seller_price_each REAL
        );
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

        -- 5% platform fee for tests
        INSERT INTO fee_config (config_key, fee_type, fee_value, description)
        VALUES ('default_platform_fee', 'percent', 5.0, 'Test 5% platform fee');

        INSERT INTO users (username, email) VALUES ('buyer1', 'buyer@test.com');
        INSERT INTO users (username, email) VALUES ('seller1', 'seller@test.com');
        INSERT INTO listings (seller_id, category_id, price_per_coin, quantity)
        VALUES (2, NULL, 95.00, 10);
    """)
    conn.commit()
    yield conn, str(db_path)
    conn.close()


@pytest.fixture
def mock_get_db(test_db, monkeypatch):
    conn, db_path = test_db

    def get_test_connection():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        return c

    import database
    monkeypatch.setattr(database, 'get_db_connection', get_test_connection)

    import services.ledger_service as ledger_module
    monkeypatch.setattr(ledger_module, 'get_db_connection', get_test_connection)

    import core.services.ledger.order_creation as oc_module
    monkeypatch.setattr(oc_module, 'get_db_connection', get_test_connection)

    return get_test_connection


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_order(conn, total_price, buyer_card_fee=0.0, tax_amount=0.0,
                payment_status='paid', pi_id='pi_test123',
                payment_method_type='card'):
    """Insert an order row and return its id."""
    cur = conn.execute("""
        INSERT INTO orders (buyer_id, total_price, buyer_card_fee, tax_amount,
                            payment_status, stripe_payment_intent_id, payment_method_type)
        VALUES (1, ?, ?, ?, ?, ?, ?)
    """, (total_price, buyer_card_fee, tax_amount, payment_status, pi_id,
          payment_method_type))
    conn.commit()
    return cur.lastrowid


def _make_ledger(conn, order_id, gross, platform_fee=0.0, spread=0.0,
                 payout_status='PAID_OUT', transfer_id='tr_test123',
                 seller_net=None):
    """Insert orders_ledger + order_payouts and return ledger_id."""
    if seller_net is None:
        seller_net = round(gross - platform_fee, 2)
    cur = conn.execute("""
        INSERT INTO orders_ledger (order_id, buyer_id, order_status, payment_method,
                                   gross_amount, platform_fee_amount, spread_capture_amount)
        VALUES (?, 1, 'COMPLETED', 'card', ?, ?, ?)
    """, (order_id, gross, platform_fee, spread))
    ledger_id = cur.lastrowid
    conn.execute("""
        INSERT INTO order_payouts (order_ledger_id, order_id, seller_id, payout_status,
                                   seller_gross_amount, fee_amount, seller_net_amount,
                                   spread_capture_amount, provider_transfer_id)
        VALUES (?, ?, 2, ?, ?, ?, ?, ?, ?)
    """, (ledger_id, order_id, payout_status, gross, platform_fee, seller_net,
          spread, transfer_id))
    conn.commit()
    return ledger_id


def _recon_row(conn, order_id):
    """Return a dict matching what compute_recon_status expects."""
    row = conn.execute("""
        SELECT op.payout_status,
               o.total_price, o.payment_status, o.stripe_payment_intent_id,
               o.buyer_card_fee, o.tax_amount, o.payment_method_type,
               ol.gross_amount, COALESCE(ol.spread_capture_amount, 0) AS spread_capture_amount,
               op.provider_transfer_id
        FROM order_payouts op
        JOIN orders_ledger ol ON op.order_ledger_id = ol.id
        JOIN orders o ON op.order_id = o.id
        WHERE op.order_id = ?
    """, (order_id,)).fetchone()
    return dict(row)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestReconStatusWithSpread:
    """compute_recon_status correctly handles spread capture."""

    def _status(self, row):
        from core.blueprints.admin.reconciliation import compute_recon_status
        return compute_recon_status(row)

    # SC-1: No spread — direct checkout, amounts match exactly
    def test_sc1_no_spread_matched(self, mock_get_db):
        """SC-1: order with no spread reconciles as MATCHED."""
        conn = mock_get_db()
        # buyer pays $100 seller price + $3 card fee = $103
        oid = _make_order(conn, total_price=103.00, buyer_card_fee=3.00)
        _make_ledger(conn, oid, gross=100.00, platform_fee=5.00, spread=0.0,
                     seller_net=95.00)
        row = _recon_row(conn, oid)
        assert self._status(row) == 'MATCHED'
        conn.close()

    # SC-2: Bid fill with spread — MATCHED_SPREAD (spread explains the gap)
    def test_sc2_spread_matched(self, mock_get_db):
        """SC-2: buyer bid=$110, seller ask=$95, spread=$15, card fee=$3.
        total_price = $110 + $3 = $113
        gross_amount (seller side) = $95
        spread_capture = $15
        expected = $95 + $15 + $0 + $3 = $113 ✓ → MATCHED_SPREAD
        """
        conn = mock_get_db()
        oid = _make_order(conn, total_price=113.00, buyer_card_fee=3.00)
        _make_ledger(conn, oid, gross=95.00, platform_fee=4.75, spread=15.00,
                     seller_net=90.25)
        row = _recon_row(conn, oid)
        assert self._status(row) == 'MATCHED_SPREAD', \
            f"Expected MATCHED_SPREAD but got {self._status(row)}"
        conn.close()

    # SC-3: Spread + tax + card fee — full equation reconciles
    def test_sc3_spread_tax_card_fee_matched(self, mock_get_db):
        """SC-3: buyer=$110, seller=$95, spread=$15, tax=$9.08 (8.25%), card_fee=$3.56.
        total = $110 + $9.08 + $3.56 = $122.64
        expected = $95 + $15 + $9.08 + $3.56 = $122.64 ✓ → MATCHED_SPREAD
        """
        conn = mock_get_db()
        oid = _make_order(conn, total_price=122.64, buyer_card_fee=3.56,
                          tax_amount=9.08)
        _make_ledger(conn, oid, gross=95.00, platform_fee=4.75, spread=15.00,
                     seller_net=90.25)
        row = _recon_row(conn, oid)
        assert self._status(row) == 'MATCHED_SPREAD', \
            f"Expected MATCHED_SPREAD but got {self._status(row)}"
        conn.close()

    # SC-4: Real unexplained delta — still AMOUNT_MISMATCH
    def test_sc4_real_mismatch_flagged(self, mock_get_db):
        """SC-4: spread is $15, but there's an extra unexplained $5.
        total = $118 (should be $113), delta = $5 after accounting for spread.
        Must remain AMOUNT_MISMATCH.
        """
        conn = mock_get_db()
        # real total would be $113 but stored as $118 (unexplained $5)
        oid = _make_order(conn, total_price=118.00, buyer_card_fee=3.00)
        _make_ledger(conn, oid, gross=95.00, platform_fee=4.75, spread=15.00,
                     seller_net=90.25)
        row = _recon_row(conn, oid)
        assert self._status(row) == 'AMOUNT_MISMATCH', \
            f"Expected AMOUNT_MISMATCH but got {self._status(row)}"
        conn.close()

    # SC-7: Backward compat — old orders with no spread column default to 0
    def test_sc7_zero_spread_backward_compat(self, mock_get_db):
        """SC-7: rows without spread_capture_amount (coalesced to 0) still reconcile."""
        conn = mock_get_db()
        oid = _make_order(conn, total_price=105.00, buyer_card_fee=5.00)
        _make_ledger(conn, oid, gross=100.00, platform_fee=5.00, spread=0.0,
                     seller_net=95.00)
        row = _recon_row(conn, oid)
        # Force the column to be absent (simulate old row) — default is 0
        row_missing_spread = {k: v for k, v in row.items()
                               if k != 'spread_capture_amount'}
        assert self._status(row_missing_spread) == 'MATCHED'
        conn.close()


class TestLedgerSpreadStorage:
    """create_order_ledger_from_cart correctly stores spread_capture_amount."""

    def test_sc5_seller_net_uses_seller_price(self, mock_get_db):
        """SC-5: seller net is based on seller price, not buyer price.
        buyer=$110, seller=$95, fee=5%
        seller_net = $95 - ($95 * 5%) = $95 - $4.75 = $90.25
        (NOT $110 - $5.50 = $104.50)
        """
        from services.ledger_service import LedgerService
        conn = mock_get_db()
        oid = _make_order(conn, total_price=113.00, buyer_card_fee=3.00)
        conn.close()

        cart_snapshot = [{
            'seller_id': 2,
            'listing_id': 1,
            'quantity': 1,
            'unit_price': 95.00,        # seller price
            'buyer_unit_price': 110.00, # buyer price
        }]
        ledger_id = LedgerService.create_order_ledger_from_cart(
            buyer_id=1,
            cart_snapshot=cart_snapshot,
            payment_method='card',
            order_id=oid,
        )

        conn = mock_get_db()
        ledger = conn.execute('SELECT * FROM orders_ledger WHERE id = ?',
                               (ledger_id,)).fetchone()
        payout = conn.execute('SELECT * FROM order_payouts WHERE order_ledger_id = ?',
                               (ledger_id,)).fetchone()
        item = conn.execute('SELECT * FROM order_items_ledger WHERE order_ledger_id = ?',
                              (ledger_id,)).fetchone()

        # Gross uses SELLER price
        assert ledger['gross_amount'] == 95.00, \
            f"gross_amount should be seller price 95.00, got {ledger['gross_amount']}"
        # Spread stored on ledger
        assert ledger['spread_capture_amount'] == 15.00, \
            f"spread_capture_amount should be 15.00, got {ledger['spread_capture_amount']}"
        # Seller net = seller_gross - fee (NOT buyer_gross - fee)
        assert payout['seller_net_amount'] == 90.25, \
            f"seller_net should be 90.25 (95 - 4.75), got {payout['seller_net_amount']}"
        # Fee on seller side
        assert payout['fee_amount'] == 4.75, \
            f"fee should be 4.75 (5% of 95), got {payout['fee_amount']}"
        # Per-item spread columns
        assert item['buyer_unit_price'] == 110.00
        assert item['spread_per_unit'] == 15.00
        # Spread on payout row
        assert payout['spread_capture_amount'] == 15.00
        conn.close()

    def test_sc6_spread_revenue_queryable(self, mock_get_db):
        """SC-6: spread_capture_amount is stored and can be summed for revenue reporting."""
        from services.ledger_service import LedgerService
        conn = mock_get_db()

        # Create three orders with varying spread
        order_ids = []
        spreads = [5.00, 12.50, 0.00]  # third has no spread
        seller_prices = [95.00, 87.50, 100.00]
        buyer_prices = [100.00, 100.00, 100.00]

        for i, (sp, bp) in enumerate(zip(seller_prices, buyer_prices)):
            cur = conn.execute("""
                INSERT INTO orders (buyer_id, total_price, payment_status,
                                    stripe_payment_intent_id)
                VALUES (1, ?, 'paid', 'pi_test')
            """, (bp,))
            oid = cur.lastrowid
            conn.commit()
            order_ids.append(oid)
        conn.close()

        for i, (oid, sp, bp) in enumerate(zip(order_ids, seller_prices, buyer_prices)):
            LedgerService.create_order_ledger_from_cart(
                buyer_id=1,
                cart_snapshot=[{
                    'seller_id': 2,
                    'listing_id': 1,
                    'quantity': 1,
                    'unit_price': sp,
                    'buyer_unit_price': bp,
                }],
                payment_method='card',
                order_id=oid,
            )

        conn = mock_get_db()
        total_spread = conn.execute(
            'SELECT SUM(spread_capture_amount) AS total FROM orders_ledger'
        ).fetchone()['total']
        assert total_spread == 17.50, \
            f"Expected total spread 17.50, got {total_spread}"

        # Verify individual rows
        rows = conn.execute(
            'SELECT spread_capture_amount FROM orders_ledger ORDER BY id'
        ).fetchall()
        assert rows[0]['spread_capture_amount'] == 5.00
        assert rows[1]['spread_capture_amount'] == 12.50
        assert rows[2]['spread_capture_amount'] == 0.00
        conn.close()

    def test_no_spread_direct_checkout(self, mock_get_db):
        """Direct checkout (no buyer_unit_price) stores spread = 0.0."""
        from services.ledger_service import LedgerService
        conn = mock_get_db()
        oid = _make_order(conn, total_price=100.00)
        conn.close()

        # No buyer_unit_price key — simulates direct-checkout cart item
        cart_snapshot = [{
            'seller_id': 2,
            'listing_id': 1,
            'quantity': 1,
            'unit_price': 100.00,
        }]
        ledger_id = LedgerService.create_order_ledger_from_cart(
            buyer_id=1, cart_snapshot=cart_snapshot,
            payment_method='ach', order_id=oid,
        )

        conn = mock_get_db()
        ledger = conn.execute('SELECT * FROM orders_ledger WHERE id = ?',
                               (ledger_id,)).fetchone()
        payout = conn.execute('SELECT * FROM order_payouts WHERE order_ledger_id = ?',
                               (ledger_id,)).fetchone()
        assert ledger['spread_capture_amount'] == 0.0
        assert payout['spread_capture_amount'] == 0.0
        assert payout['seller_net_amount'] == 95.00  # 100 - 5% = 95
        conn.close()


class TestReconStatusMatchedSpread:
    """MATCHED_SPREAD is used for spread orders; MATCHED for non-spread orders."""

    def _status(self, row):
        from core.blueprints.admin.reconciliation import compute_recon_status
        return compute_recon_status(row)

    def _is_problem(self, status):
        from core.blueprints.admin.reconciliation import _is_problem_status
        return _is_problem_status(status)

    def test_no_spread_returns_matched(self, mock_get_db):
        """Non-spread order that reconciles → MATCHED (not MATCHED_SPREAD)."""
        conn = mock_get_db()
        oid = _make_order(conn, total_price=103.00, buyer_card_fee=3.00)
        _make_ledger(conn, oid, gross=100.00, platform_fee=5.00, spread=0.0,
                     seller_net=95.00)
        row = _recon_row(conn, oid)
        assert self._status(row) == 'MATCHED'
        conn.close()

    def test_spread_order_returns_matched_spread(self, mock_get_db):
        """Spread order that reconciles → MATCHED_SPREAD, not MATCHED."""
        conn = mock_get_db()
        oid = _make_order(conn, total_price=113.00, buyer_card_fee=3.00)
        _make_ledger(conn, oid, gross=95.00, platform_fee=4.75, spread=15.00,
                     seller_net=90.25)
        row = _recon_row(conn, oid)
        status = self._status(row)
        assert status == 'MATCHED_SPREAD', \
            f"Expected MATCHED_SPREAD, got {status}"

    def test_matched_spread_is_not_a_problem(self, mock_get_db):
        """MATCHED_SPREAD must NOT be classified as a problem status."""
        conn = mock_get_db()
        oid = _make_order(conn, total_price=113.00, buyer_card_fee=3.00)
        _make_ledger(conn, oid, gross=95.00, platform_fee=4.75, spread=15.00,
                     seller_net=90.25)
        row = _recon_row(conn, oid)
        status = self._status(row)
        assert not self._is_problem(status), \
            f"MATCHED_SPREAD should not be a problem status, got {status}"

    def test_spread_with_real_mismatch_stays_amount_mismatch(self, mock_get_db):
        """Even with spread stored, an unexplained delta keeps AMOUNT_MISMATCH."""
        conn = mock_get_db()
        # $113 expected, $120 stored — $7 unexplained after accounting for spread
        oid = _make_order(conn, total_price=120.00, buyer_card_fee=3.00)
        _make_ledger(conn, oid, gross=95.00, platform_fee=4.75, spread=15.00,
                     seller_net=90.25)
        row = _recon_row(conn, oid)
        assert self._status(row) == 'AMOUNT_MISMATCH'

    def test_spread_pending_payout_not_matched_spread(self, mock_get_db):
        """Spread order that hasn't been paid out yet → PENDING_PAYOUT, not MATCHED_SPREAD."""
        conn = mock_get_db()
        oid = _make_order(conn, total_price=113.00, buyer_card_fee=3.00)
        _make_ledger(conn, oid, gross=95.00, platform_fee=4.75, spread=15.00,
                     seller_net=90.25, payout_status='PAYOUT_NOT_READY',
                     transfer_id=None)
        row = _recon_row(conn, oid)
        assert self._status(row) == 'PENDING_PAYOUT'


class TestLedgerSpreadStats:
    """get_ledger_stats returns total_spread_revenue summed from orders_ledger."""

    def test_spread_revenue_in_stats(self, mock_get_db):
        """total_spread_revenue is queryable from orders_ledger.SUM(spread_capture_amount)."""
        conn = mock_get_db()

        # Create two orders: one with spread, one without
        oid1 = _make_order(conn, total_price=113.00, buyer_card_fee=3.00,
                           pi_id='pi_s1')
        oid2 = _make_order(conn, total_price=103.00, buyer_card_fee=3.00,
                           pi_id='pi_s2')
        conn.close()

        from services.ledger_service import LedgerService
        LedgerService.create_order_ledger_from_cart(
            buyer_id=1,
            cart_snapshot=[{'seller_id': 2, 'listing_id': 1, 'quantity': 1,
                            'unit_price': 95.00, 'buyer_unit_price': 110.00}],
            payment_method='card',
            order_id=oid1,
        )
        LedgerService.create_order_ledger_from_cart(
            buyer_id=1,
            cart_snapshot=[{'seller_id': 2, 'listing_id': 1, 'quantity': 1,
                            'unit_price': 100.00}],
            payment_method='card',
            order_id=oid2,
        )

        conn = mock_get_db()
        total_spread = conn.execute(
            'SELECT COALESCE(SUM(spread_capture_amount), 0) AS total FROM orders_ledger'
        ).fetchone()['total']
        conn.close()

        assert total_spread == 15.00, \
            f"Expected total spread revenue 15.00, got {total_spread}"

    def test_zero_spread_revenue_when_no_bid_fills(self, mock_get_db):
        """When no bid fills exist, total_spread_revenue is 0."""
        conn = mock_get_db()
        oid = _make_order(conn, total_price=100.00, pi_id='pi_nospread')
        conn.close()

        from services.ledger_service import LedgerService
        LedgerService.create_order_ledger_from_cart(
            buyer_id=1,
            cart_snapshot=[{'seller_id': 2, 'listing_id': 1, 'quantity': 1,
                            'unit_price': 100.00}],
            payment_method='ach',
            order_id=oid,
        )

        conn = mock_get_db()
        total_spread = conn.execute(
            'SELECT COALESCE(SUM(spread_capture_amount), 0) AS total FROM orders_ledger'
        ).fetchone()['total']
        conn.close()

        assert total_spread == 0.0, \
            f"Expected 0.0 spread revenue, got {total_spread}"


# ── Live-path tests: _build_rows (the actual admin query used by the UI) ──────

@pytest.fixture
def live_db(tmp_path):
    """
    Full-schema DB that satisfies _BASE_QUERY in reconciliation.py.

    Includes all columns selected by the query: refund_status, stripe_refund_id,
    provider_payout_id, provider_reversal_id, payout_recovery_status, etc.
    """
    db_path = tmp_path / "test_live.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT, email TEXT
        );
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            buyer_id INTEGER,
            total_price REAL,
            payment_status TEXT DEFAULT 'unpaid',
            payment_method_type TEXT,
            stripe_payment_intent_id TEXT,
            stripe_refund_id TEXT,
            refund_status TEXT,
            buyer_card_fee REAL NOT NULL DEFAULT 0.0,
            tax_amount REAL NOT NULL DEFAULT 0.0,
            tax_rate REAL NOT NULL DEFAULT 0.0,
            source_bid_id INTEGER
        );
        CREATE TABLE order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER, listing_id INTEGER,
            quantity INTEGER, price_each REAL,
            seller_price_each REAL
        );
        CREATE TABLE orders_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER UNIQUE NOT NULL,
            buyer_id INTEGER NOT NULL,
            order_status TEXT NOT NULL DEFAULT 'PAID_IN_ESCROW',
            payment_method TEXT,
            gross_amount REAL NOT NULL,
            platform_fee_amount REAL NOT NULL DEFAULT 0,
            spread_capture_amount REAL NOT NULL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            provider_transfer_id TEXT,
            provider_payout_id TEXT,
            provider_reversal_id TEXT,
            payout_recovery_status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(order_ledger_id, seller_id)
        );

        INSERT INTO users (username, email) VALUES ('buyer1', 'b@test.com');
        INSERT INTO users (username, email) VALUES ('seller1', 's@test.com');
    """)
    conn.commit()
    yield conn
    conn.close()


def _insert_live_order(conn, *, buyer_bid, seller_ask, qty=1,
                       tax=0.0, card_fee=0.0, pi_id='pi_live1',
                       payout_status='PAID_OUT', transfer_id='tr_live1',
                       ledger_spread=None):
    """
    Insert a complete order + order_items + orders_ledger + order_payouts row.

    If ledger_spread is None, stores 0.0 (simulates the old auto_match bug).
    Returns order_id.
    """
    total_price = round(buyer_bid * qty + tax + card_fee, 2)
    cur = conn.execute(
        """INSERT INTO orders (buyer_id, total_price, payment_status,
                               stripe_payment_intent_id, buyer_card_fee,
                               tax_amount, payment_method_type)
           VALUES (1, ?, 'paid', ?, ?, ?, 'card')""",
        (total_price, pi_id, card_fee, tax),
    )
    order_id = cur.lastrowid

    conn.execute(
        "INSERT INTO order_items (order_id, listing_id, quantity, price_each, seller_price_each) "
        "VALUES (?, 1, ?, ?, ?)",
        (order_id, qty, buyer_bid, seller_ask),
    )

    gross = round(seller_ask * qty, 2)
    stored_spread = round((buyer_bid - seller_ask) * qty, 2) if ledger_spread is None and buyer_bid != seller_ask else (
        ledger_spread if ledger_spread is not None else 0.0
    )
    # Simulate old bug: store 0.0 when ledger_spread not explicitly set
    stored_spread_in_ledger = 0.0 if ledger_spread is None else ledger_spread

    cur2 = conn.execute(
        """INSERT INTO orders_ledger (order_id, buyer_id, order_status, payment_method,
                                      gross_amount, platform_fee_amount, spread_capture_amount)
           VALUES (?, 1, 'PAID_IN_ESCROW', 'card', ?, ?, ?)""",
        (order_id, gross, round(gross * 0.05, 2), stored_spread_in_ledger),
    )
    ledger_id = cur2.lastrowid

    fee = round(gross * 0.05, 2)
    conn.execute(
        """INSERT INTO order_payouts (order_ledger_id, order_id, seller_id, payout_status,
                                      seller_gross_amount, fee_amount, seller_net_amount,
                                      spread_capture_amount, provider_transfer_id)
           VALUES (?, ?, 2, ?, ?, ?, ?, ?, ?)""",
        (ledger_id, order_id, payout_status, gross, fee,
         round(gross - fee, 2), stored_spread_in_ledger, transfer_id),
    )
    conn.commit()
    return order_id


class TestLiveBuildRows:
    """
    Integration-style tests that call _build_rows() directly with a real SQLite
    connection — the same code path the admin UI executes.

    These tests catch bugs that are invisible to unit tests of compute_recon_status
    in isolation (because those tests pass a hand-crafted dict that already has the
    correct spread_capture_amount; they never exercise the SQL that derives it).
    """

    def _rows(self, conn, order_id):
        from core.blueprints.admin.reconciliation import _build_rows
        return _build_rows(conn, extra_where=' AND op.order_id = ?',
                           params=[order_id])

    # SC-LIVE-1: Old bid-fill order — spread in order_items, 0 in orders_ledger
    def test_live_old_bid_fill_not_mismatch(self, live_db):
        """
        Old bid-fill order (orders_ledger.spread_capture_amount = 0 due to bug).
        order_items has price_each=$110, seller_price_each=$95 → spread=$15.
        total_price = $110 + $3 fee = $113.
        Without fallback: expected = $95 + 0 + 0 + $3 = $98 ≠ $113 → AMOUNT_MISMATCH
        With fallback: derived_spread = $15, expected = $95 + $15 + 0 + $3 = $113 ✓
        """
        oid = _insert_live_order(
            live_db,
            buyer_bid=110.0, seller_ask=95.0, qty=1,
            card_fee=3.0, pi_id='pi_old1', transfer_id='tr_old1',
            ledger_spread=None,   # simulate old bug: stored as 0
        )
        rows = self._rows(live_db, oid)
        assert len(rows) == 1
        row = rows[0]
        assert row['recon_status'] in ('MATCHED_SPREAD', 'MATCHED'), \
            f"Expected MATCHED or MATCHED_SPREAD, got {row['recon_status']} " \
            f"(spread_capture_amount={row['spread_capture_amount']}, " \
            f"total_price={row['total_price']}, " \
            f"gross_amount={row['gross_amount']})"
        assert not row['is_problem'], \
            f"Old bid-fill order should not be flagged as a problem"

    # SC-LIVE-2: New bid-fill order — spread correctly stored in orders_ledger
    def test_live_new_bid_fill_matched_spread(self, live_db):
        """
        New bid-fill order with spread correctly stored.
        orders_ledger.spread_capture_amount = $15 (correctly persisted).
        Should show MATCHED_SPREAD.
        """
        oid = _insert_live_order(
            live_db,
            buyer_bid=110.0, seller_ask=95.0, qty=1,
            card_fee=3.0, pi_id='pi_new1', transfer_id='tr_new1',
            ledger_spread=15.0,  # correctly stored
        )
        rows = self._rows(live_db, oid)
        assert len(rows) == 1
        assert rows[0]['recon_status'] == 'MATCHED_SPREAD'
        assert not rows[0]['is_problem']

    # SC-LIVE-3: Regular checkout (no spread) — not affected by fallback
    def test_live_checkout_no_spread_matched(self, live_db):
        """
        Regular checkout: price_each == seller_price_each → spread = 0.
        total_price = $100 + $3 fee = $103.
        Should show MATCHED.
        """
        oid = _insert_live_order(
            live_db,
            buyer_bid=100.0, seller_ask=100.0, qty=1,
            card_fee=3.0, pi_id='pi_co1', transfer_id='tr_co1',
            ledger_spread=0.0,
        )
        rows = self._rows(live_db, oid)
        assert len(rows) == 1
        assert rows[0]['recon_status'] == 'MATCHED'
        assert not rows[0]['is_problem']

    # SC-LIVE-4: order_items.seller_price_each is NULL (old checkout before column existed)
    def test_live_null_seller_price_each_matched(self, live_db):
        """
        Checkout order with seller_price_each NULL in order_items (pre-migration).
        Fallback must treat NULL seller_price_each as no spread → MATCHED.
        """
        total = 103.0
        cur = live_db.execute(
            """INSERT INTO orders (buyer_id, total_price, payment_status,
                                   stripe_payment_intent_id, buyer_card_fee, payment_method_type)
               VALUES (1, ?, 'paid', 'pi_null1', 3.0, 'card')""",
            (total,),
        )
        oid = cur.lastrowid
        # seller_price_each explicitly NULL
        live_db.execute(
            "INSERT INTO order_items (order_id, listing_id, quantity, price_each, seller_price_each) "
            "VALUES (?, 1, 1, 100.0, NULL)",
            (oid,),
        )
        cur2 = live_db.execute(
            """INSERT INTO orders_ledger (order_id, buyer_id, gross_amount, platform_fee_amount,
                                          spread_capture_amount)
               VALUES (?, 1, 100.0, 5.0, 0.0)""",
            (oid,),
        )
        lid = cur2.lastrowid
        live_db.execute(
            """INSERT INTO order_payouts (order_ledger_id, order_id, seller_id, payout_status,
                                          seller_gross_amount, fee_amount, seller_net_amount,
                                          spread_capture_amount, provider_transfer_id)
               VALUES (?, ?, 2, 'PAID_OUT', 100.0, 5.0, 95.0, 0.0, 'tr_null1')""",
            (lid, oid),
        )
        live_db.commit()

        rows = self._rows(live_db, oid)
        assert len(rows) == 1
        assert rows[0]['recon_status'] == 'MATCHED', \
            f"Expected MATCHED, got {rows[0]['recon_status']}"

    # SC-LIVE-5: Unexplained delta even after fallback spread → still AMOUNT_MISMATCH
    def test_live_real_mismatch_still_flagged(self, live_db):
        """
        Bid-fill order with spread in order_items, but total_price has an extra $7
        that cannot be explained by derived spread.  Must remain AMOUNT_MISMATCH.
        """
        # correct total would be $110 + $3 = $113, but we store $120 (unexplained $7)
        cur = live_db.execute(
            """INSERT INTO orders (buyer_id, total_price, payment_status,
                                   stripe_payment_intent_id, buyer_card_fee, payment_method_type)
               VALUES (1, 120.0, 'paid', 'pi_mm1', 3.0, 'card')""",
        )
        oid = cur.lastrowid
        live_db.execute(
            "INSERT INTO order_items (order_id, listing_id, quantity, price_each, seller_price_each) "
            "VALUES (?, 1, 1, 110.0, 95.0)",  # correct spread = $15
            (oid,),
        )
        cur2 = live_db.execute(
            """INSERT INTO orders_ledger (order_id, buyer_id, gross_amount, platform_fee_amount,
                                          spread_capture_amount)
               VALUES (?, 1, 95.0, 4.75, 0.0)""",   # old bug: spread=0
            (oid,),
        )
        lid = cur2.lastrowid
        live_db.execute(
            """INSERT INTO order_payouts (order_ledger_id, order_id, seller_id, payout_status,
                                          seller_gross_amount, fee_amount, seller_net_amount,
                                          spread_capture_amount, provider_transfer_id)
               VALUES (?, ?, 2, 'PAID_OUT', 95.0, 4.75, 90.25, 0.0, 'tr_mm1')""",
            (lid, oid),
        )
        live_db.commit()

        rows = self._rows(live_db, oid)
        assert len(rows) == 1
        assert rows[0]['recon_status'] == 'AMOUNT_MISMATCH', \
            f"Expected AMOUNT_MISMATCH for unexplained $7, got {rows[0]['recon_status']}"
