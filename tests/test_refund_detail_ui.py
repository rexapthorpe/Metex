"""
Tests for the refund detail page UI.

Verifies that the ledger order detail page correctly renders:
- Three-way status section (Buyer Refund / Seller Recovery / Platform Coverage)
- Financial breakdown
- Platform-covered refund alert when platform_covered_amount > 0
- Correct statuses for each scenario
"""
import pytest
import sqlite3
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Minimal schema for the detail page route
# ---------------------------------------------------------------------------

_DETAIL_SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    email TEXT,
    is_admin INTEGER DEFAULT 0,
    stripe_account_id TEXT,
    stripe_payouts_enabled INTEGER DEFAULT 0
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_id INTEGER,
    total_price REAL DEFAULT 0.0,
    tax_amount REAL NOT NULL DEFAULT 0.0,
    tax_rate REAL NOT NULL DEFAULT 0.0,
    buyer_card_fee REAL NOT NULL DEFAULT 0.0,
    status TEXT DEFAULT 'paid',
    payment_status TEXT DEFAULT 'paid',
    payment_method_type TEXT DEFAULT 'card',
    refund_status TEXT DEFAULT 'not_refunded',
    refund_amount REAL DEFAULT 0.0,
    refund_subtotal REAL NOT NULL DEFAULT 0.0,
    refund_tax_amount REAL NOT NULL DEFAULT 0.0,
    refund_processing_fee REAL NOT NULL DEFAULT 0.0,
    platform_covered_amount REAL NOT NULL DEFAULT 0.0,
    stripe_payment_intent_id TEXT,
    stripe_refund_id TEXT,
    refunded_at TEXT,
    refund_reason TEXT,
    requires_payout_recovery INTEGER DEFAULT 0,
    requires_payment_clearance INTEGER DEFAULT 0,
    payment_cleared_at TEXT,
    payment_cleared_by_admin_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    paid_at TEXT
);
CREATE TABLE orders_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER UNIQUE NOT NULL,
    buyer_id INTEGER,
    order_status TEXT DEFAULT 'PAID_IN_ESCROW',
    gross_amount REAL DEFAULT 0.0,
    platform_fee_amount REAL DEFAULT 0.0,
    spread_capture_amount REAL NOT NULL DEFAULT 0.0,
    refunded_platform_fee_amount REAL NOT NULL DEFAULT 0.0,
    refunded_spread_capture_amount REAL NOT NULL DEFAULT 0.0,
    payment_method TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE order_items_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    order_ledger_id INTEGER,
    listing_id INTEGER,
    seller_id INTEGER,
    quantity INTEGER DEFAULT 1,
    unit_price REAL DEFAULT 0.0,
    gross_amount REAL DEFAULT 0.0,
    fee_amount REAL DEFAULT 0.0,
    fee_value REAL DEFAULT 0.0,
    fee_type TEXT DEFAULT 'percent',
    seller_net_amount REAL DEFAULT 0.0,
    buyer_unit_price REAL,
    spread_per_unit REAL NOT NULL DEFAULT 0.0
);
CREATE TABLE order_payouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_ledger_id INTEGER,
    order_id INTEGER,
    seller_id INTEGER,
    payout_status TEXT DEFAULT 'PAYOUT_NOT_READY',
    seller_gross_amount REAL DEFAULT 0.0,
    fee_amount REAL DEFAULT 0.0,
    seller_net_amount REAL DEFAULT 0.0,
    provider_transfer_id TEXT,
    payout_recovery_status TEXT DEFAULT 'not_needed',
    recovery_attempted_at TEXT,
    recovery_completed_at TEXT,
    recovery_attempted_by_admin_id INTEGER,
    recovery_failure_reason TEXT,
    provider_reversal_id TEXT,
    spread_capture_amount REAL NOT NULL DEFAULT 0.0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE order_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    event_type TEXT,
    actor_type TEXT DEFAULT 'system',
    actor_id INTEGER,
    payload_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE seller_order_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    seller_id INTEGER,
    tracking_number TEXT,
    carrier TEXT,
    updated_at TEXT,
    delivered_at TEXT
);
"""


@pytest.fixture
def detail_db(tmp_path):
    """SQLite test DB for detail page tests."""
    db_path = tmp_path / 'detail_test.db'
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_DETAIL_SCHEMA)
    conn.execute("INSERT INTO users VALUES (1,'buyer1','b@t.com',0,NULL,0)")
    conn.execute("INSERT INTO users VALUES (2,'seller1','s@t.com',0,'acct_s1',1)")
    conn.execute("INSERT INTO users VALUES (99,'admin1','a@t.com',1,NULL,0)")
    conn.commit()
    yield conn, str(db_path)
    conn.close()


def _seed_refunded_order(db_factory, refund_status='refunded',
                         platform_covered=0.0, payout_recovery='not_needed',
                         refund_subtotal=90.0, refund_tax=8.0, refund_fee=2.0,
                         refund_amount=100.0, provider_reversal_id=None):
    """Seed a fully refunded order. Returns (order_id, conn)."""
    conn, db_path = db_factory
    conn.execute(
        """INSERT INTO orders
           (buyer_id, total_price, tax_amount, buyer_card_fee, payment_status,
            refund_status, refund_amount, refund_subtotal, refund_tax_amount,
            refund_processing_fee, platform_covered_amount,
            stripe_payment_intent_id, stripe_refund_id, refunded_at, refund_reason)
           VALUES (1, 100.0, 8.0, 2.0, 'paid',
                   ?, ?, ?, ?, ?, ?,
                   'pi_test', 're_test001', '2026-04-08 12:00:00', 'Test refund')""",
        (refund_status, refund_amount, refund_subtotal, refund_tax, refund_fee,
         platform_covered)
    )
    order_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.execute(
        """INSERT INTO orders_ledger (order_id, buyer_id, order_status, gross_amount,
               platform_fee_amount, spread_capture_amount)
           VALUES (?, 1, 'REFUNDED', 90.0, 5.0, 2.0)""",
        (order_id,)
    )
    ledger_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.execute(
        """INSERT INTO order_payouts
           (order_ledger_id, order_id, seller_id, payout_status, seller_net_amount,
            payout_recovery_status, provider_reversal_id)
           VALUES (?, ?, 2, 'PAYOUT_CANCELLED', 85.0, ?, ?)""",
        (ledger_id, order_id, payout_recovery, provider_reversal_id)
    )
    conn.commit()
    return order_id


@pytest.fixture
def app_client(detail_db):
    """Flask test client with the test DB wired in."""
    import flask
    from core import create_app
    import database as _db_module

    conn, db_path = detail_db

    def _factory():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        return c

    app = create_app({'TESTING': True, 'WTF_CSRF_ENABLED': False,
                      'SECRET_KEY': 'test-secret-key-32-chars-long!!'})

    # Patch all get_db_connection entry points
    with app.test_client() as client:
        with app.app_context():
            # Create an admin session
            with client.session_transaction() as sess:
                sess['user_id'] = 99
                sess['is_admin'] = True
                sess['username'] = 'admin1'

            patches = [
                patch.object(_db_module, 'get_db_connection', side_effect=_factory),
                patch('utils.auth_utils.get_db_connection', side_effect=_factory),
            ]
            for p in patches:
                p.start()

            yield client, detail_db

            for p in patches:
                p.stop()


# ---------------------------------------------------------------------------
# Tests: refund_info fields returned by the route
# ---------------------------------------------------------------------------

class TestRefundInfoQueryFields:
    """The ledger route must include breakdown fields in refund_info."""

    def test_query_returns_platform_covered_amount(self, detail_db):
        """Direct DB query for refund_info returns platform_covered_amount."""
        conn, db_path = detail_db
        order_id = _seed_refunded_order(detail_db, platform_covered=93.0)

        row = conn.execute(
            '''SELECT payment_status, refund_status, refund_amount,
                      COALESCE(refund_subtotal, 0)         AS refund_subtotal,
                      COALESCE(refund_tax_amount, 0)       AS refund_tax_amount,
                      COALESCE(refund_processing_fee, 0)   AS refund_processing_fee,
                      COALESCE(platform_covered_amount, 0) AS platform_covered_amount
               FROM orders WHERE id = ?''',
            (order_id,)
        ).fetchone()

        assert row is not None
        assert float(row['platform_covered_amount']) == pytest.approx(93.0, abs=0.01)
        assert float(row['refund_subtotal']) == pytest.approx(90.0, abs=0.01)
        assert float(row['refund_tax_amount']) == pytest.approx(8.0, abs=0.01)
        assert float(row['refund_processing_fee']) == pytest.approx(2.0, abs=0.01)
        assert row['refund_status'] == 'refunded'

    def test_query_returns_zero_platform_covered_when_recovery_succeeded(self, detail_db):
        """When recovery succeeds, platform_covered_amount = 0."""
        conn, db_path = detail_db
        order_id = _seed_refunded_order(detail_db, platform_covered=0.0,
                                         payout_recovery='recovered',
                                         provider_reversal_id='trr_001')

        row = conn.execute(
            'SELECT COALESCE(platform_covered_amount, 0) AS platform_covered_amount FROM orders WHERE id = ?',
            (order_id,)
        ).fetchone()

        assert float(row['platform_covered_amount']) == pytest.approx(0.0, abs=0.01)

    def test_payout_recovery_status_available(self, detail_db):
        """Payout rows must have payout_recovery_status for the template."""
        conn, db_path = detail_db
        order_id = _seed_refunded_order(detail_db, payout_recovery='manual_review')

        payouts = conn.execute(
            'SELECT payout_recovery_status FROM order_payouts WHERE order_id = ?',
            (order_id,)
        ).fetchall()

        assert len(payouts) == 1
        assert payouts[0]['payout_recovery_status'] == 'manual_review'

    def test_partial_refund_fields(self, detail_db):
        """Partially refunded order has correct breakdown fields."""
        conn, db_path = detail_db
        order_id = _seed_refunded_order(
            detail_db,
            refund_status='partially_refunded',
            refund_amount=50.0,
            refund_subtotal=45.0,
            refund_tax=4.0,
            refund_fee=1.0,
            platform_covered=0.0,
        )

        row = conn.execute(
            '''SELECT refund_status, refund_amount, refund_subtotal,
                      refund_tax_amount, refund_processing_fee
               FROM orders WHERE id = ?''',
            (order_id,)
        ).fetchone()

        assert row['refund_status'] == 'partially_refunded'
        assert float(row['refund_amount']) == pytest.approx(50.0, abs=0.01)
        assert float(row['refund_subtotal']) == pytest.approx(45.0, abs=0.01)
        assert float(row['refund_tax_amount']) == pytest.approx(4.0, abs=0.01)
        assert float(row['refund_processing_fee']) == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# Tests: Template rendering via HTTP (Flask test client)
# ---------------------------------------------------------------------------

class TestDetailPageRendering:
    """HTTP-level tests that verify the rendered HTML contains expected sections."""

    def _get_page(self, client, order_id):
        """Fetch the detail page and return (status_code, html_text)."""
        resp = client.get(f'/admin/ledger/order/{order_id}',
                          follow_redirects=True)
        return resp.status_code, resp.data.decode('utf-8', errors='replace')

    def test_refunded_order_shows_status_panel(self, app_client):
        """Fully refunded order shows 'Refund Method & Recovery Status' section."""
        client, detail_db = app_client
        order_id = _seed_refunded_order(detail_db)

        status, html = self._get_page(client, order_id)
        assert status == 200
        assert 'Refund Method' in html
        assert 'Recovery Status' in html

    def test_refunded_order_shows_buyer_refund_row(self, app_client):
        """Buyer Refund row (A.) is present for refunded orders."""
        client, detail_db = app_client
        order_id = _seed_refunded_order(detail_db)

        _, html = self._get_page(client, order_id)
        assert 'A. Buyer Refund' in html
        assert 'Succeeded' in html

    def test_refunded_order_shows_seller_recovery_row(self, app_client):
        """Seller Recovery row (B.) is present."""
        client, detail_db = app_client
        order_id = _seed_refunded_order(detail_db)

        _, html = self._get_page(client, order_id)
        assert 'B. Seller Recovery' in html

    def test_refunded_order_shows_platform_coverage_row(self, app_client):
        """Platform Coverage row (C.) is present."""
        client, detail_db = app_client
        order_id = _seed_refunded_order(detail_db)

        _, html = self._get_page(client, order_id)
        assert 'C. Platform Coverage' in html

    def test_platform_coverage_not_used_when_zero(self, app_client):
        """When platform_covered_amount = 0, shows 'Not Used'."""
        client, detail_db = app_client
        order_id = _seed_refunded_order(detail_db, platform_covered=0.0)

        _, html = self._get_page(client, order_id)
        assert 'Not Used' in html
        # The server-rendered platform coverage alert must NOT appear
        assert 'platform-covered-alert' not in html

    def test_platform_coverage_shown_when_nonzero(self, app_client):
        """When platform_covered_amount > 0, shows coverage amount and alert."""
        client, detail_db = app_client
        order_id = _seed_refunded_order(detail_db, platform_covered=93.0)

        _, html = self._get_page(client, order_id)
        # The server-rendered platform coverage alert must appear
        assert 'platform-covered-alert' in html
        assert '93.00' in html

    def test_financial_breakdown_present(self, app_client):
        """Financial breakdown section shows subtotal, tax, fee, total refunded."""
        client, detail_db = app_client
        order_id = _seed_refunded_order(
            detail_db, refund_subtotal=90.0, refund_tax=8.0,
            refund_fee=2.0, refund_amount=100.0
        )

        _, html = self._get_page(client, order_id)
        assert 'Refund Breakdown' in html
        assert 'Subtotal refunded' in html
        assert 'Total refunded' in html

    def test_partially_refunded_shows_amber_banner(self, app_client):
        """Partially refunded order shows the amber 'Partially Refunded' banner."""
        client, detail_db = app_client
        order_id = _seed_refunded_order(
            detail_db,
            refund_status='partially_refunded',
            refund_amount=50.0,
            refund_subtotal=45.0,
            refund_tax=4.0,
            refund_fee=1.0,
        )

        _, html = self._get_page(client, order_id)
        assert 'Partially Refunded' in html
        # Full refund banner should NOT appear
        assert 'Fully Refunded' not in html

    def test_not_refunded_shows_refund_button(self, app_client):
        """Paid but not-yet-refunded order shows the Issue Refund button."""
        client, detail_db = app_client
        conn, db_path = detail_db

        # Seed a paid but not-refunded order
        conn.execute(
            """INSERT INTO orders
               (buyer_id, total_price, tax_amount, buyer_card_fee, payment_status,
                refund_status, stripe_payment_intent_id)
               VALUES (1, 100.0, 8.0, 2.0, 'paid', 'not_refunded', 'pi_notref')"""
        )
        order_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        conn.execute(
            "INSERT INTO orders_ledger (order_id, buyer_id, gross_amount) VALUES (?, 1, 90.0)",
            (order_id,)
        )
        conn.commit()

        _, html = self._get_page(client, order_id)
        assert 'btn-refund-buyer' in html or 'Issue Refund' in html

    def test_stripe_refund_id_shown(self, app_client):
        """Stripe refund ID is visible on the detail page."""
        client, detail_db = app_client
        order_id = _seed_refunded_order(detail_db)

        _, html = self._get_page(client, order_id)
        assert 're_test001' in html

    def test_seller_recovery_not_required_when_payout_cancelled(self, app_client):
        """When payout recovery status is 'not_needed', shows 'Not Required'."""
        client, detail_db = app_client
        order_id = _seed_refunded_order(detail_db, payout_recovery='not_needed')

        _, html = self._get_page(client, order_id)
        assert 'Not Required' in html
