"""
Tests: Admin Sales Tax tab

TAX-1.  GET /admin/api/tax/stats     → requires admin auth (302/401 for non-admin)
TAX-2.  GET /admin/api/tax/stats     → correct totals with seeded paid orders
TAX-3.  Tax Collected counts only paid orders (not unpaid)
TAX-4.  Tax Refunded is computed only for full refunds (not partial)
TAX-5.  Net Tax Liability = Collected − Refunded
TAX-6.  GET /admin/api/tax/rows      → returns only orders with tax_amount > 0
TAX-7.  Date range filter (start_date / end_date) narrows rows
TAX-8.  State filter narrows rows by parsed shipping_address
TAX-9.  Payment status filter works
TAX-10. Refund status filter works
TAX-11. GET /admin/api/tax/export    → returns CSV with correct headers
TAX-12. CSV contains expected data columns
TAX-13. GET /admin/api/tax/jurisdiction-summary → aggregates by state
TAX-14. Jurisdiction summary excludes refunded tax for fully-refunded orders
TAX-15. /admin/api/ledger/stats includes total_tax_collected
TAX-16. Reconciliation money-flow detail includes tax_amount field
TAX-17. _parse_state_zip helper correctly extracts state & postal from address
TAX-18. _is_full_refund: true for refund_amount ≈ total_price, false for partial
"""

import os
import sys
import sqlite3
import tempfile
import shutil
import json
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT,
    email         TEXT,
    password      TEXT    DEFAULT '',
    password_hash TEXT    DEFAULT '',
    is_admin      INTEGER DEFAULT 0,
    is_banned     INTEGER DEFAULT 0,
    is_frozen     INTEGER DEFAULT 0,
    is_metex_guaranteed INTEGER DEFAULT 0,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS system_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS orders (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_id                  INTEGER,
    total_price               REAL DEFAULT 0,
    status                    TEXT DEFAULT 'Pending',
    payment_status            TEXT DEFAULT 'unpaid',
    payout_status             TEXT DEFAULT 'PAYOUT_NOT_READY',
    refund_status             TEXT DEFAULT 'not_refunded',
    refund_amount             REAL DEFAULT 0,
    stripe_refund_id          TEXT,
    refunded_at               TIMESTAMP,
    refund_reason             TEXT,
    requires_payout_recovery  INTEGER DEFAULT 0,
    requires_payment_clearance INTEGER DEFAULT 0,
    payment_cleared_at        TIMESTAMP,
    payment_cleared_by_admin_id INTEGER,
    stripe_payment_intent_id  TEXT,
    payment_method_type       TEXT DEFAULT 'card',
    buyer_card_fee            REAL DEFAULT 0,
    tax_amount                REAL DEFAULT 0,
    tax_rate                  REAL DEFAULT 0,
    shipping_address          TEXT DEFAULT '',
    created_at                TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS orders_ledger (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id             INTEGER UNIQUE,
    buyer_id             INTEGER,
    order_status         TEXT DEFAULT 'PAID_IN_ESCROW',
    gross_amount         REAL DEFAULT 0,
    platform_fee_amount  REAL DEFAULT 0,
    spread_capture_amount REAL NOT NULL DEFAULT 0.0,
    payment_method       TEXT DEFAULT 'card',
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS order_payouts (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    order_ledger_id       INTEGER,
    order_id              INTEGER,
    seller_id             INTEGER,
    payout_status         TEXT DEFAULT 'PAYOUT_NOT_READY',
    payout_recovery_status TEXT DEFAULT 'not_needed',
    seller_gross_amount   REAL DEFAULT 0,
    fee_amount            REAL DEFAULT 0,
    seller_net_amount     REAL DEFAULT 0,
    spread_capture_amount REAL NOT NULL DEFAULT 0.0,
    provider_transfer_id  TEXT,
    provider_payout_id    TEXT,
    provider_reversal_id  TEXT,
    recovery_attempted_at TIMESTAMP,
    recovery_completed_at TIMESTAMP,
    recovery_attempted_by_admin_id INTEGER,
    recovery_failure_reason TEXT,
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS order_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id        INTEGER NOT NULL,
    listing_id      INTEGER,
    quantity        INTEGER DEFAULT 1,
    price_each      REAL DEFAULT 0,
    seller_price_each REAL
);
CREATE TABLE IF NOT EXISTS order_items_ledger (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    order_ledger_id  INTEGER,
    order_id         INTEGER,
    seller_id        INTEGER,
    listing_id       INTEGER,
    quantity         INTEGER DEFAULT 1,
    unit_price       REAL DEFAULT 0,
    gross_amount     REAL DEFAULT 0,
    fee_type         TEXT DEFAULT 'percent',
    fee_value        REAL DEFAULT 0,
    fee_amount       REAL DEFAULT 0,
    seller_net_amount REAL DEFAULT 0,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS order_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER,
    event_type TEXT,
    actor_type TEXT,
    actor_id   INTEGER,
    payload_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER,
    type       TEXT,
    message    TEXT,
    read       INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS notification_settings (
    user_id           INTEGER,
    notification_type TEXT,
    enabled           INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS spot_price_snapshots (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    metal     TEXT,
    price_usd REAL,
    as_of     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS user_risk_profile (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER UNIQUE,
    risk_score INTEGER DEFAULT 0,
    risk_flag  TEXT DEFAULT 'none',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

ADMIN_UID = 8001
BUYER_UID = 8002


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def test_db():
    """Set up test DB, patch database layer, seed data, yield."""
    from app import app as _flask_app  # noqa — ensure blueprints registered

    import database
    import utils.auth_utils as auth_mod

    tmpdir  = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, 'tax_test.db')

    raw = sqlite3.connect(db_path)
    raw.row_factory = sqlite3.Row
    raw.executescript(SCHEMA)

    # Users
    raw.execute("INSERT INTO users (id,username,email,is_admin) VALUES (?,?,?,?)",
                (ADMIN_UID, 'tax_admin', 'ta@t.com', 1))
    raw.execute("INSERT INTO users (id,username,email,is_admin) VALUES (?,?,?,?)",
                (BUYER_UID, 'tax_buyer', 'tb@t.com', 0))

    # Order 101: paid, CA, $10 tax — not refunded
    raw.execute("""
        INSERT INTO orders (id, buyer_id, total_price, payment_status,
            buyer_card_fee, tax_amount, tax_rate, refund_status, refund_amount,
            shipping_address, stripe_payment_intent_id, created_at)
        VALUES (101, ?, 125.79, 'paid',
            3.59, 10.00, 0.0875, 'not_refunded', 0,
            '123 Main St • Los Angeles, CA 90001', 'pi_tax1',
            '2026-03-15 12:00:00')
    """, (BUYER_UID,))

    # Order 102: paid, TX, $6.25 tax — not refunded
    raw.execute("""
        INSERT INTO orders (id, buyer_id, total_price, payment_status,
            buyer_card_fee, tax_amount, tax_rate, refund_status, refund_amount,
            shipping_address, stripe_payment_intent_id, created_at)
        VALUES (102, ?, 109.00, 'paid',
            3.22, 6.25, 0.0625, 'not_refunded', 0,
            '456 Oak Ave • Dallas, TX 75201', 'pi_tax2',
            '2026-03-20 10:00:00')
    """, (BUYER_UID,))

    # Order 103: paid, CA, $8 tax — FULLY refunded
    raw.execute("""
        INSERT INTO orders (id, buyer_id, total_price, payment_status,
            buyer_card_fee, tax_amount, tax_rate, refund_status, refund_amount,
            shipping_address, stripe_payment_intent_id, created_at)
        VALUES (103, ?, 108.00, 'paid',
            3.16, 8.00, 0.08, 'refunded', 108.00,
            '789 Pine Rd • San Francisco, CA 94102', 'pi_tax3',
            '2026-03-22 09:00:00')
    """, (BUYER_UID,))

    # Order 104: UNPAID, $5 tax — should NOT count toward tax_collected
    raw.execute("""
        INSERT INTO orders (id, buyer_id, total_price, payment_status,
            buyer_card_fee, tax_amount, tax_rate, refund_status, refund_amount,
            shipping_address, created_at)
        VALUES (104, ?, 105.00, 'unpaid',
            3.10, 5.00, 0.05, 'not_refunded', 0,
            '100 Elm St • Seattle, WA 98101',
            '2026-03-25 08:00:00')
    """, (BUYER_UID,))

    # Order 105: paid, TX, $6.75 tax — PARTIAL refund ($50 of $109.50) → refunded_tax=0
    raw.execute("""
        INSERT INTO orders (id, buyer_id, total_price, payment_status,
            buyer_card_fee, tax_amount, tax_rate, refund_status, refund_amount,
            shipping_address, stripe_payment_intent_id, created_at)
        VALUES (105, ?, 109.50, 'paid',
            3.23, 6.75, 0.0675, 'partially_refunded', 50.00,
            '200 Maple Dr • Austin, TX 78701', 'pi_tax5',
            '2026-04-01 11:00:00')
    """, (BUYER_UID,))

    # Ledger row for order 101 (needed for ledger stats test + recon detail test)
    raw.execute("""
        INSERT INTO orders_ledger (id, order_id, buyer_id, order_status,
            gross_amount, platform_fee_amount, payment_method)
        VALUES (1, 101, ?, 'PAID_IN_ESCROW', 112.20, 5.61, 'card')
    """, (BUYER_UID,))

    # Payout row for order 101 (needed for recon detail endpoint)
    raw.execute("""
        INSERT INTO order_payouts
            (order_id, order_ledger_id, seller_id, payout_status,
             seller_gross_amount, fee_amount, seller_net_amount, provider_transfer_id)
        VALUES (101, 1, ?, 'PAID_OUT', 112.20, 5.61, 106.59, 'tr_tax1')
    """, (ADMIN_UID,))

    raw.commit()
    raw.close()

    def get_test_conn():
        c = sqlite3.connect(db_path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    orig_db   = database.get_db_connection
    orig_auth = auth_mod.get_db_connection

    database.get_db_connection  = get_test_conn
    auth_mod.get_db_connection  = get_test_conn

    yield db_path, get_test_conn

    database.get_db_connection  = orig_db
    auth_mod.get_db_connection  = orig_auth
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope='module')
def admin_client(test_db):
    from app import app as flask_app
    flask_app.config.update({'TESTING': True, 'WTF_CSRF_ENABLED': False,
                             'SECRET_KEY': 'tax-test-key'})
    with flask_app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id']  = ADMIN_UID
            sess['username'] = 'tax_admin'
            sess['is_admin'] = True
        yield client


@pytest.fixture
def non_admin_client(test_db):
    from app import app as flask_app
    flask_app.config.update({'TESTING': True, 'WTF_CSRF_ENABLED': False,
                             'SECRET_KEY': 'tax-test-key'})
    with flask_app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id']  = BUYER_UID
            sess['username'] = 'tax_buyer'
            sess['is_admin'] = False
        yield client


# ── Unit tests: helper functions ──────────────────────────────────────────────

class TestHelpers:
    """TAX-17 / TAX-18: unit test pure helper functions in tax.py."""

    def test_TAX17_parse_standard(self):
        """TAX-17: Parses state and postal from 'City, ST ZIP'."""
        from core.blueprints.admin.tax import _parse_state_zip
        state, postal = _parse_state_zip('123 Main St • Los Angeles, CA 90001')
        assert state  == 'CA'
        assert postal == '90001'

    def test_TAX17_parse_two_line(self):
        """TAX-17: Parses two-line address (line • line • city, ST ZIP)."""
        from core.blueprints.admin.tax import _parse_state_zip
        state, postal = _parse_state_zip('456 Oak Ave • Apt 2B • Dallas, TX 75201')
        assert state  == 'TX'
        assert postal == '75201'

    def test_TAX17_parse_empty(self):
        """TAX-17: Returns ('', '') for empty/None input."""
        from core.blueprints.admin.tax import _parse_state_zip
        assert _parse_state_zip('')   == ('', '')
        assert _parse_state_zip(None) == ('', '')

    def test_TAX18_full_refund_true(self):
        """TAX-18: _is_full_refund True when refund_amount ≈ total_price."""
        from core.blueprints.admin.tax import _is_full_refund
        assert _is_full_refund({
            'refund_status': 'refunded', 'refund_amount': 108.00, 'total_price': 108.00
        }) is True

    def test_TAX18_partial_refund_false(self):
        """TAX-18: _is_full_refund False for partial refunds."""
        from core.blueprints.admin.tax import _is_full_refund
        assert _is_full_refund({
            'refund_status': 'partially_refunded', 'refund_amount': 50.00, 'total_price': 109.50
        }) is False

    def test_TAX18_not_refunded_false(self):
        """TAX-18: _is_full_refund False when refund_status = not_refunded."""
        from core.blueprints.admin.tax import _is_full_refund
        assert _is_full_refund({
            'refund_status': 'not_refunded', 'refund_amount': 0, 'total_price': 125.79
        }) is False


# ── Integration: stats ────────────────────────────────────────────────────────

class TestTaxStats:

    def test_TAX1_requires_admin(self, non_admin_client):
        """TAX-1: Non-admin is redirected away from stats."""
        r = non_admin_client.get('/admin/api/tax/stats')
        assert r.status_code in (302, 401, 403)

    def test_TAX2_correct_totals(self, admin_client):
        """TAX-2: Stats return correct tax_collected, refunded, net."""
        r = admin_client.get('/admin/api/tax/stats')
        assert r.status_code == 200
        s = json.loads(r.data)['stats']
        # Paid orders: 101($10)+102($6.25)+103($8)+105($6.75) = 31.00
        assert abs(s['total_tax_collected'] - 31.00) < 0.05
        # Only order 103 is fully refunded: $8
        assert abs(s['total_tax_refunded'] - 8.00) < 0.05

    def test_TAX3_unpaid_excluded(self, admin_client):
        """TAX-3: Unpaid order 104 ($5 tax) is excluded from collected."""
        r = admin_client.get('/admin/api/tax/stats')
        s = json.loads(r.data)['stats']
        assert s['total_tax_collected'] < 36.00  # would be 36 if order 104 included

    def test_TAX4_partial_refund_not_counted(self, admin_client):
        """TAX-4: Partial refund (order 105) does NOT add to tax_refunded."""
        r = admin_client.get('/admin/api/tax/stats')
        s = json.loads(r.data)['stats']
        assert abs(s['total_tax_refunded'] - 8.00) < 0.05  # only order 103

    def test_TAX5_net_equals_collected_minus_refunded(self, admin_client):
        """TAX-5: net_tax_liability = collected - refunded."""
        r = admin_client.get('/admin/api/tax/stats')
        s = json.loads(r.data)['stats']
        expected = round(s['total_tax_collected'] - s['total_tax_refunded'], 2)
        assert abs(s['net_tax_liability'] - expected) < 0.01


# ── Integration: rows ─────────────────────────────────────────────────────────

class TestTaxRows:

    def test_TAX6_returns_only_tax_positive(self, admin_client):
        """TAX-6: Rows only include orders where tax_amount > 0."""
        r = admin_client.get('/admin/api/tax/rows')
        data = json.loads(r.data)
        assert data['success']
        ids = [row['order_id'] for row in data['rows']]
        assert 101 in ids
        assert 102 in ids

    def test_TAX7_date_filter(self, admin_client):
        """TAX-7: start_date filter excludes older orders."""
        r = admin_client.get('/admin/api/tax/rows?start_date=2026-04-01')
        ids = [x['order_id'] for x in json.loads(r.data)['rows']]
        assert 105 in ids
        assert 101 not in ids

    def test_TAX8_state_filter(self, admin_client):
        """TAX-8: state=TX returns only Texas orders."""
        r = admin_client.get('/admin/api/tax/rows?state=TX')
        ids = [x['order_id'] for x in json.loads(r.data)['rows']]
        assert 102 in ids   # Dallas TX
        assert 105 in ids   # Austin TX
        assert 101 not in ids  # CA

    def test_TAX9_payment_status_filter(self, admin_client):
        """TAX-9: payment_status=unpaid returns order 104."""
        r = admin_client.get('/admin/api/tax/rows?payment_status=unpaid')
        ids = [x['order_id'] for x in json.loads(r.data)['rows']]
        assert 104 in ids
        assert 101 not in ids

    def test_TAX10_refund_status_filter(self, admin_client):
        """TAX-10: refund_status=refunded returns order 103 only."""
        r = admin_client.get('/admin/api/tax/rows?refund_status=refunded')
        ids = [x['order_id'] for x in json.loads(r.data)['rows']]
        assert 103 in ids
        assert 101 not in ids

    def test_derived_fields_present(self, admin_client):
        """Rows include state, postal, refunded_tax, net_tax, taxable_subtotal."""
        r = admin_client.get('/admin/api/tax/rows')
        rows = json.loads(r.data)['rows']
        row101 = next(x for x in rows if x['order_id'] == 101)
        assert row101['state']  == 'CA'
        assert row101['postal'] == '90001'
        assert row101['refunded_tax'] == 0.0
        assert abs(row101['net_tax'] - 10.0) < 0.01

    def test_full_refund_row_has_refunded_tax(self, admin_client):
        """Order 103 (fully refunded) has refunded_tax = tax_amount = $8."""
        r = admin_client.get('/admin/api/tax/rows')
        rows = json.loads(r.data)['rows']
        row103 = next((x for x in rows if x['order_id'] == 103), None)
        assert row103 is not None
        assert abs(row103['refunded_tax'] - 8.0) < 0.01
        assert abs(row103['net_tax']) < 0.01  # 8 - 8 = 0


# ── Integration: export ───────────────────────────────────────────────────────

class TestTaxExport:

    def test_TAX11_returns_csv_content_type(self, admin_client):
        """TAX-11: Export returns text/csv."""
        r = admin_client.get('/admin/api/tax/export')
        assert r.status_code == 200
        assert 'text/csv' in r.content_type

    def test_TAX12_csv_has_required_columns(self, admin_client):
        """TAX-12: CSV header contains all filing-required columns."""
        r = admin_client.get('/admin/api/tax/export')
        header = r.data.decode('utf-8').splitlines()[0]
        required = [
            'Order ID', 'Order Date', 'Buyer', 'State', 'Postal Code',
            'Tax Amount', 'Tax Rate', 'Payment Status', 'Refund Status',
            'Refunded Tax', 'Net Tax', 'Stripe Payment Intent',
        ]
        for col in required:
            assert col in header, f"Missing column: {col}"

    def test_csv_has_data_rows(self, admin_client):
        """CSV has at least one data row (beyond header)."""
        r = admin_client.get('/admin/api/tax/export')
        lines = [l for l in r.data.decode('utf-8').splitlines() if l.strip()]
        assert len(lines) > 1

    def test_csv_state_filter(self, admin_client):
        """CSV export respects state=TX filter."""
        r = admin_client.get('/admin/api/tax/export?state=TX')
        lines = r.data.decode('utf-8').splitlines()
        for line in lines[1:]:
            if line.strip():
                assert 'TX' in line, f"Non-TX row in TX-filtered export: {line}"


# ── Integration: jurisdiction summary ────────────────────────────────────────

class TestTaxJurisdiction:

    def test_TAX13_aggregates_by_state(self, admin_client):
        """TAX-13: Jurisdiction summary groups paid orders by state."""
        r = admin_client.get('/admin/api/tax/jurisdiction-summary')
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data['success']
        states = {j['state']: j for j in data['jurisdictions']}
        # CA: orders 101 ($10) + 103 ($8) = $18
        assert 'CA' in states
        assert abs(states['CA']['tax_collected'] - 18.00) < 0.05
        # TX: orders 102 ($6.25) + 105 ($6.75) = $13
        assert 'TX' in states
        assert abs(states['TX']['tax_collected'] - 13.00) < 0.05

    def test_TAX14_full_refund_reduces_ca_net(self, admin_client):
        """TAX-14: CA net_tax_liability = 18 - 8 = 10 (order 103 fully refunded)."""
        r = admin_client.get('/admin/api/tax/jurisdiction-summary')
        states = {j['state']: j for j in json.loads(r.data)['jurisdictions']}
        ca = states['CA']
        assert abs(ca['tax_refunded']      - 8.00)  < 0.05
        assert abs(ca['net_tax_liability'] - 10.00) < 0.05

    def test_partial_refund_not_in_tax_refunded(self, admin_client):
        """TX partial refund (order 105) does NOT appear in tax_refunded."""
        r = admin_client.get('/admin/api/tax/jurisdiction-summary')
        states = {j['state']: j for j in json.loads(r.data)['jurisdictions']}
        tx = states.get('TX', {})
        assert abs(tx.get('tax_refunded', 0))          < 0.01
        assert abs(tx.get('net_tax_liability', 0) - 13.00) < 0.05

    def test_sorted_by_tax_collected_desc(self, admin_client):
        """Jurisdiction list is sorted by tax_collected descending."""
        r = admin_client.get('/admin/api/tax/jurisdiction-summary')
        amounts = [j['tax_collected'] for j in json.loads(r.data)['jurisdictions']]
        assert amounts == sorted(amounts, reverse=True)


# ── Integration: ledger stats tax card ───────────────────────────────────────

class TestLedgerTaxStat:

    def test_TAX15_ledger_stats_has_tax_collected(self, admin_client):
        """TAX-15: /admin/api/ledger/stats returns total_tax_collected key."""
        r = admin_client.get('/admin/api/ledger/stats')
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data['success']
        assert 'total_tax_collected' in data['stats']
        # Order 101 is in orders_ledger (paid) → tax_amount = $10
        assert data['stats']['total_tax_collected'] >= 10.0


# ── Integration: reconciliation money-flow includes tax ──────────────────────

class TestReconMoneyFlow:

    def test_TAX16_recon_detail_money_flow_has_tax(self, admin_client):
        """TAX-16: Recon detail for order 101 money_flow includes tax_amount = $10."""
        r = admin_client.get('/admin/api/reconciliation/order/101')
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data['success']
        mf = data['money_flow']
        assert 'tax_amount' in mf
        assert abs(mf['tax_amount'] - 10.00) < 0.05
        # total_charged must include tax: subtotal + tax + card_fee
        expected = round(mf['subtotal'] + mf['tax_amount'] + mf['buyer_card_fee'], 2)
        assert abs(mf['total_charged'] - expected) < 0.05
