"""
Tests: Admin Financial Reconciliation endpoints

RECON-1.  compute_recon_status → MATCHED for fully-reconciled card order
RECON-2.  compute_recon_status → MATCHED for fully-reconciled ACH order (no card fee)
RECON-3.  compute_recon_status → UNPAID when payment_status != 'paid'
RECON-4.  compute_recon_status → MISSING_STRIPE_REF when paid but no PI
RECON-5.  compute_recon_status → AMOUNT_MISMATCH when total_price != gross + card_fee
RECON-6.  compute_recon_status → MISSING_CARD_FEE for card order with no card fee
RECON-7.  compute_recon_status → MISSING_TRANSFER for PAID_OUT without transfer ID
RECON-8.  compute_recon_status → AWAITING_TRANSFER for PAYOUT_READY
RECON-9.  compute_recon_status → PENDING_PAYOUT for paid+refs+not-ready payout
RECON-10. GET /admin/api/reconciliation/stats → requires admin auth
RECON-11. GET /admin/api/reconciliation/stats → correct counts with seeded data
RECON-12. GET /admin/api/reconciliation/rows  → returns rows with recon_status field
RECON-13. GET /admin/api/reconciliation/rows  → filter by recon_status=MATCHED
RECON-14. GET /admin/api/reconciliation/rows  → filter by payment_status=unpaid
RECON-15. GET /admin/api/reconciliation/order/<id> → money-flow breakdown
RECON-16. GET /admin/api/reconciliation/order/9999 → 404 for unknown order
RECON-17. Non-admin access to stats → redirect (401/302)
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

# ── Minimal schema ─────────────────────────────────────────────────────────────

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
    created_at                TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS orders_ledger (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id              INTEGER UNIQUE,
    buyer_id              INTEGER,
    order_status          TEXT DEFAULT 'PAID_IN_ESCROW',
    payment_method        TEXT DEFAULT 'card',
    gross_amount          REAL DEFAULT 0,
    platform_fee_amount   REAL DEFAULT 0,
    spread_capture_amount REAL NOT NULL DEFAULT 0.0,
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS order_payouts (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    order_ledger_id       INTEGER,
    order_id              INTEGER,
    seller_id             INTEGER,
    payout_status         TEXT DEFAULT 'PAYOUT_NOT_READY',
    seller_gross_amount   REAL DEFAULT 0,
    fee_amount            REAL DEFAULT 0,
    seller_net_amount     REAL DEFAULT 0,
    spread_capture_amount REAL NOT NULL DEFAULT 0.0,
    scheduled_for         TIMESTAMP,
    provider_transfer_id  TEXT,
    provider_payout_id    TEXT,
    provider_reversal_id  TEXT,
    payout_recovery_status TEXT DEFAULT 'not_needed',
    recovery_attempted_at TIMESTAMP,
    recovery_completed_at TIMESTAMP,
    recovery_attempted_by_admin_id INTEGER,
    recovery_failure_reason TEXT,
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(order_ledger_id, seller_id)
);
CREATE TABLE IF NOT EXISTS order_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id        INTEGER NOT NULL,
    listing_id      INTEGER,
    quantity        INTEGER DEFAULT 1,
    price_each      REAL DEFAULT 0,
    seller_price_each REAL
);
"""

# ── Fixture IDs ────────────────────────────────────────────────────────────────
ADMIN_UID   = 7001
BUYER_UID   = 7002
SELLER1_UID = 7003
SELLER2_UID = 7004

# order IDs (each corresponds to one orders_ledger + one+ order_payouts row)
ORD_CARD_MATCHED    = 2001  # card, paid, PAID_OUT with transfer — MATCHED
ORD_ACH_MATCHED     = 2002  # ach, paid, PAID_OUT with transfer — MATCHED (no card fee)
ORD_UNPAID          = 2003  # payment_status=unpaid
ORD_MISSING_PI      = 2004  # paid, no stripe_payment_intent_id
ORD_AMT_MISMATCH    = 2005  # total_price != gross + card_fee
ORD_MISSING_FEE     = 2006  # card, paid, buyer_card_fee=0 but total_price==gross
ORD_MISSING_XFER    = 2007  # PAID_OUT but no provider_transfer_id
ORD_AWAITING_XFER   = 2008  # PAYOUT_READY (eligible but not yet transferred)
ORD_PENDING_PAYOUT  = 2009  # paid, refs present, PAYOUT_NOT_READY


def _seed_order(raw, oid, buyer_id, total_price, payment_status, payment_method_type,
                stripe_pi, buyer_card_fee, gross_amount, platform_fee,
                payout_status, transfer_id, seller_id,
                ledger_id=None):
    """Insert one complete order + ledger + payout row."""
    if ledger_id is None:
        ledger_id = oid  # use order_id as ledger_id for simplicity in tests

    raw.execute(
        '''INSERT INTO orders (id, buyer_id, total_price, payment_status,
               payment_method_type, stripe_payment_intent_id,
               buyer_card_fee, created_at)
           VALUES (?,?,?,?,?,?,?, CURRENT_TIMESTAMP)''',
        (oid, buyer_id, total_price, payment_status,
         payment_method_type, stripe_pi, buyer_card_fee)
    )
    raw.execute(
        '''INSERT INTO orders_ledger (id, order_id, buyer_id, gross_amount,
               platform_fee_amount, payment_method)
           VALUES (?,?,?,?,?,?)''',
        (ledger_id, oid, buyer_id, gross_amount, platform_fee, payment_method_type)
    )
    seller_net = gross_amount - platform_fee
    raw.execute(
        '''INSERT INTO order_payouts (order_ledger_id, order_id, seller_id,
               payout_status, seller_gross_amount, fee_amount,
               seller_net_amount, provider_transfer_id)
           VALUES (?,?,?,?,?,?,?,?)''',
        (ledger_id, oid, seller_id, payout_status,
         gross_amount, platform_fee, seller_net, transfer_id)
    )


@pytest.fixture(scope='module')
def test_db():
    from app import app as _flask_app  # noqa: F401 — ensures blueprints registered

    import database
    import utils.auth_utils as auth_mod

    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, 'recon_test.db')

    raw = sqlite3.connect(db_path)
    raw.row_factory = sqlite3.Row
    raw.executescript(SCHEMA)

    # Users
    raw.execute("INSERT INTO users (id,username,email,is_admin) VALUES (?,?,?,?)",
                (ADMIN_UID, 'recon_admin', 'ra@t.com', 1))
    raw.execute("INSERT INTO users (id,username,email,is_admin) VALUES (?,?,?,?)",
                (BUYER_UID,  'recon_buyer', 'rb@t.com', 0))
    raw.execute("INSERT INTO users (id,username,email,is_admin) VALUES (?,?,?,?)",
                (SELLER1_UID, 'recon_s1', 'rs1@t.com', 0))
    raw.execute("INSERT INTO users (id,username,email,is_admin) VALUES (?,?,?,?)",
                (SELLER2_UID, 'recon_s2', 'rs2@t.com', 0))

    # Card matched — total_price = 100.00 + 3.29 card fee = 103.29
    _seed_order(raw, ORD_CARD_MATCHED, BUYER_UID,
                total_price=103.29, payment_status='paid',
                payment_method_type='card', stripe_pi='pi_card_ok',
                buyer_card_fee=3.29, gross_amount=100.00,
                platform_fee=2.50,
                payout_status='PAID_OUT', transfer_id='tr_card_ok',
                seller_id=SELLER1_UID)

    # ACH matched — no card fee, total_price == gross_amount
    _seed_order(raw, ORD_ACH_MATCHED, BUYER_UID,
                total_price=200.00, payment_status='paid',
                payment_method_type='us_bank_account', stripe_pi='pi_ach_ok',
                buyer_card_fee=0, gross_amount=200.00,
                platform_fee=5.00,
                payout_status='PAID_OUT', transfer_id='tr_ach_ok',
                seller_id=SELLER1_UID)

    # Unpaid
    _seed_order(raw, ORD_UNPAID, BUYER_UID,
                total_price=50.00, payment_status='unpaid',
                payment_method_type='card', stripe_pi=None,
                buyer_card_fee=0, gross_amount=50.00,
                platform_fee=1.25,
                payout_status='PAYOUT_NOT_READY', transfer_id=None,
                seller_id=SELLER1_UID)

    # Missing Stripe PI (paid but no PI)
    _seed_order(raw, ORD_MISSING_PI, BUYER_UID,
                total_price=75.00, payment_status='paid',
                payment_method_type='card', stripe_pi=None,
                buyer_card_fee=2.54, gross_amount=72.46,
                platform_fee=1.81,
                payout_status='PAYOUT_NOT_READY', transfer_id=None,
                seller_id=SELLER1_UID)

    # Amount mismatch — total_price doesn't match gross + card_fee
    _seed_order(raw, ORD_AMT_MISMATCH, BUYER_UID,
                total_price=150.00,   # wrong — should be 145.00 + 4.63 = 149.63
                payment_status='paid',
                payment_method_type='card', stripe_pi='pi_mismatch',
                buyer_card_fee=4.63, gross_amount=145.00,
                platform_fee=3.63,
                payout_status='PAYOUT_NOT_READY', transfer_id=None,
                seller_id=SELLER2_UID)

    # Missing card fee — card payment but buyer_card_fee=0 and total_price==gross
    _seed_order(raw, ORD_MISSING_FEE, BUYER_UID,
                total_price=80.00, payment_status='paid',
                payment_method_type='card', stripe_pi='pi_no_fee',
                buyer_card_fee=0, gross_amount=80.00,
                platform_fee=2.00,
                payout_status='PAYOUT_NOT_READY', transfer_id=None,
                seller_id=SELLER2_UID)

    # Missing transfer — PAID_OUT but no transfer_id
    _seed_order(raw, ORD_MISSING_XFER, BUYER_UID,
                total_price=103.29, payment_status='paid',
                payment_method_type='card', stripe_pi='pi_no_xfer',
                buyer_card_fee=3.29, gross_amount=100.00,
                platform_fee=2.50,
                payout_status='PAID_OUT', transfer_id=None,
                seller_id=SELLER2_UID)

    # Awaiting transfer — PAYOUT_READY
    _seed_order(raw, ORD_AWAITING_XFER, BUYER_UID,
                total_price=103.29, payment_status='paid',
                payment_method_type='card', stripe_pi='pi_awaiting',
                buyer_card_fee=3.29, gross_amount=100.00,
                platform_fee=2.50,
                payout_status='PAYOUT_READY', transfer_id=None,
                seller_id=SELLER2_UID)

    # Pending payout — paid, refs present, payout not ready yet
    _seed_order(raw, ORD_PENDING_PAYOUT, BUYER_UID,
                total_price=103.29, payment_status='paid',
                payment_method_type='card', stripe_pi='pi_pending',
                buyer_card_fee=3.29, gross_amount=100.00,
                platform_fee=2.50,
                payout_status='PAYOUT_NOT_READY', transfer_id=None,
                seller_id=SELLER1_UID)

    raw.commit()
    raw.close()

    def get_test_conn():
        c = sqlite3.connect(db_path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    orig_db   = database.get_db_connection
    orig_auth = auth_mod.get_db_connection

    database.get_db_connection     = get_test_conn
    auth_mod.get_db_connection = get_test_conn

    yield db_path, get_test_conn

    database.get_db_connection     = orig_db
    auth_mod.get_db_connection = orig_auth
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope='module')
def admin_client(test_db):
    from app import app as flask_app
    flask_app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-recon-key',
    })
    with flask_app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id']  = ADMIN_UID
            sess['username'] = 'recon_admin'
            sess['is_admin'] = True
        yield client


@pytest.fixture
def non_admin_client(test_db):
    from app import app as flask_app
    flask_app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-recon-key',
    })
    with flask_app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id']  = BUYER_UID
            sess['username'] = 'recon_buyer'
            sess['is_admin'] = False
        yield client


# ── Unit tests for compute_recon_status (no HTTP) ─────────────────────────────

def _row(**kwargs):
    """Build a minimal row dict for compute_recon_status."""
    defaults = {
        'payment_status': 'paid',
        'payout_status': 'PAID_OUT',
        'stripe_payment_intent_id': 'pi_test',
        'provider_transfer_id': 'tr_test',
        'total_price': 103.29,
        'gross_amount': 100.00,
        'spread_capture_amount': 0,
        'tax_amount': 0,
        'buyer_card_fee': 3.29,
        'payment_method_type': 'card',
    }
    defaults.update(kwargs)
    return defaults


def test_recon1_matched_card():
    """RECON-1: Card order fully reconciled → MATCHED."""
    from core.blueprints.admin.reconciliation import compute_recon_status
    assert compute_recon_status(_row()) == 'MATCHED'


def test_recon2_matched_ach():
    """RECON-2: ACH order with no card fee, PAID_OUT+transfer → MATCHED."""
    from core.blueprints.admin.reconciliation import compute_recon_status
    r = _row(
        payment_method_type='us_bank_account',
        buyer_card_fee=0,
        gross_amount=200.00,
        total_price=200.00,
    )
    assert compute_recon_status(r) == 'MATCHED'


def test_recon3_unpaid():
    """RECON-3: payment_status=unpaid → UNPAID regardless of other fields."""
    from core.blueprints.admin.reconciliation import compute_recon_status
    assert compute_recon_status(_row(payment_status='unpaid')) == 'UNPAID'


def test_recon4_missing_stripe_ref():
    """RECON-4: paid but no stripe_payment_intent_id → MISSING_STRIPE_REF."""
    from core.blueprints.admin.reconciliation import compute_recon_status
    assert compute_recon_status(_row(stripe_payment_intent_id=None)) == 'MISSING_STRIPE_REF'


def test_recon5_amount_mismatch():
    """RECON-5: total_price doesn't match gross_amount + buyer_card_fee → AMOUNT_MISMATCH."""
    from core.blueprints.admin.reconciliation import compute_recon_status
    r = _row(total_price=150.00, gross_amount=145.00, buyer_card_fee=4.63)
    assert compute_recon_status(r) == 'AMOUNT_MISMATCH'


def test_recon6_missing_card_fee():
    """RECON-6: card payment with buyer_card_fee=0 and total_price==gross → MISSING_CARD_FEE."""
    from core.blueprints.admin.reconciliation import compute_recon_status
    r = _row(buyer_card_fee=0, gross_amount=80.00, total_price=80.00,
             payment_method_type='card')
    assert compute_recon_status(r) == 'MISSING_CARD_FEE'


def test_recon7_missing_transfer():
    """RECON-7: PAID_OUT but no provider_transfer_id → MISSING_TRANSFER."""
    from core.blueprints.admin.reconciliation import compute_recon_status
    assert compute_recon_status(_row(provider_transfer_id=None)) == 'MISSING_TRANSFER'


def test_recon8_awaiting_transfer():
    """RECON-8: PAYOUT_READY with no transfer yet → AWAITING_TRANSFER."""
    from core.blueprints.admin.reconciliation import compute_recon_status
    r = _row(payout_status='PAYOUT_READY', provider_transfer_id=None)
    assert compute_recon_status(r) == 'AWAITING_TRANSFER'


def test_recon9_pending_payout():
    """RECON-9: paid, refs present, payout not ready → PENDING_PAYOUT."""
    from core.blueprints.admin.reconciliation import compute_recon_status
    r = _row(payout_status='PAYOUT_NOT_READY', provider_transfer_id=None)
    assert compute_recon_status(r) == 'PENDING_PAYOUT'


# ── HTTP endpoint tests ───────────────────────────────────────────────────────

def test_recon10_auth_required(non_admin_client):
    """RECON-10: Non-admin gets redirect on /api/reconciliation/stats."""
    resp = non_admin_client.get('/admin/api/reconciliation/stats')
    assert resp.status_code in (302, 401, 403)


def test_recon11_stats(admin_client):
    """RECON-11: /api/reconciliation/stats returns correct problem/awaiting counts."""
    resp = admin_client.get('/admin/api/reconciliation/stats')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['success'] is True
    s = data['stats']
    # We seeded 4 problem rows: missing_pi, amt_mismatch, missing_fee, missing_xfer
    assert s['problems'] >= 4
    # At least 1 awaiting transfer row
    assert s['awaiting'] >= 1
    # Total must cover all seeded rows
    assert s['total_rows'] >= 9


def test_recon12_rows_returned(admin_client):
    """RECON-12: /api/reconciliation/rows returns rows with recon_status field."""
    resp = admin_client.get('/admin/api/reconciliation/rows')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['success'] is True
    assert len(data['rows']) >= 9
    # Every row has recon_status and is_problem
    for r in data['rows']:
        assert 'recon_status' in r
        assert 'is_problem' in r
        assert 'total_charged' in r


def test_recon13_filter_matched(admin_client):
    """RECON-13: filter recon_status=MATCHED returns only matched rows."""
    resp = admin_client.get('/admin/api/reconciliation/rows?recon_status=MATCHED')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['success'] is True
    assert len(data['rows']) >= 2  # card + ACH
    for r in data['rows']:
        assert r['recon_status'] == 'MATCHED'
        assert r['is_problem'] is False


def test_recon14_filter_unpaid(admin_client):
    """RECON-14: filter payment_status=unpaid returns only unpaid rows."""
    resp = admin_client.get('/admin/api/reconciliation/rows?payment_status=unpaid')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['success'] is True
    for r in data['rows']:
        assert r['payment_status'] == 'unpaid'
        assert r['recon_status'] == 'UNPAID'


def test_recon15_order_detail(admin_client):
    """RECON-15: /api/reconciliation/order/<id> returns full money-flow breakdown."""
    resp = admin_client.get(f'/admin/api/reconciliation/order/{ORD_CARD_MATCHED}')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['success'] is True
    assert data['order_id'] == ORD_CARD_MATCHED

    mf = data['money_flow']
    assert abs(mf['subtotal']       - 100.00) < 0.01
    assert abs(mf['buyer_card_fee'] -   3.29) < 0.01
    assert abs(mf['total_charged']  - 103.29) < 0.01
    assert abs(mf['platform_fee']   -   2.50) < 0.01

    pmt = data['payment']
    assert pmt['payment_status'] == 'paid'
    assert pmt['stripe_payment_intent_id'] == 'pi_card_ok'

    assert len(data['payout_rows']) == 1
    pr = data['payout_rows'][0]
    assert pr['recon_status'] == 'MATCHED'
    assert pr['provider_transfer_id'] == 'tr_card_ok'


def test_recon16_order_not_found(admin_client):
    """RECON-16: unknown order_id → 404."""
    resp = admin_client.get('/admin/api/reconciliation/order/99999')
    assert resp.status_code == 404


def test_recon17_non_admin_rows(non_admin_client):
    """RECON-17: Non-admin gets redirect on /api/reconciliation/rows."""
    resp = non_admin_client.get('/admin/api/reconciliation/rows')
    assert resp.status_code in (302, 401, 403)


# ── MATCHED_SPREAD unit tests ─────────────────────────────────────────────────

def test_recon_matched_spread_with_spread():
    """RECON-18: Spread order (PAID_OUT + transfer + spread > 0) → MATCHED_SPREAD."""
    from core.blueprints.admin.reconciliation import compute_recon_status
    r = _row(
        total_price=113.00,
        gross_amount=95.00,
        spread_capture_amount=15.00,
        buyer_card_fee=3.00,
        tax_amount=0,
    )
    assert compute_recon_status(r) == 'MATCHED_SPREAD'


def test_recon_matched_spread_is_not_problem():
    """RECON-19: MATCHED_SPREAD must NOT be flagged as a problem."""
    from core.blueprints.admin.reconciliation import compute_recon_status, _is_problem_status
    r = _row(
        total_price=113.00,
        gross_amount=95.00,
        spread_capture_amount=15.00,
        buyer_card_fee=3.00,
        tax_amount=0,
    )
    status = compute_recon_status(r)
    assert status == 'MATCHED_SPREAD'
    assert _is_problem_status(status) is False


def test_recon_spread_mismatch_still_flagged():
    """RECON-20: Spread stored but unexplained delta remains → AMOUNT_MISMATCH."""
    from core.blueprints.admin.reconciliation import compute_recon_status
    # total_price=120, but expected = 95+15+0+3 = 113; delta = 7 → mismatch
    r = _row(
        total_price=120.00,
        gross_amount=95.00,
        spread_capture_amount=15.00,
        buyer_card_fee=3.00,
        tax_amount=0,
    )
    assert compute_recon_status(r) == 'AMOUNT_MISMATCH'


def test_recon_spread_with_tax_matched_spread():
    """RECON-21: Spread + tax + card fee all reconcile → MATCHED_SPREAD."""
    from core.blueprints.admin.reconciliation import compute_recon_status
    # total = 95 + 15 + 9.08 + 3.56 = 122.64
    r = _row(
        total_price=122.64,
        gross_amount=95.00,
        spread_capture_amount=15.00,
        buyer_card_fee=3.56,
        tax_amount=9.08,
    )
    assert compute_recon_status(r) == 'MATCHED_SPREAD'


def test_recon_filter_matched_spread_via_api(admin_client, test_db):
    """RECON-22: Seed a spread order; filter recon_status=MATCHED_SPREAD returns it."""
    _, get_conn = test_db
    conn = get_conn()
    ORD_SPREAD = 3001
    # Seed a spread order directly
    conn.execute(
        '''INSERT INTO orders (id, buyer_id, total_price, payment_status,
               payment_method_type, stripe_payment_intent_id,
               buyer_card_fee, created_at)
           VALUES (?,?,?,?,?,?,?, CURRENT_TIMESTAMP)''',
        (ORD_SPREAD, BUYER_UID, 113.00, 'paid', 'card', 'pi_spread_ok', 3.00)
    )
    conn.execute(
        '''INSERT INTO orders_ledger (id, order_id, buyer_id, gross_amount,
               platform_fee_amount, spread_capture_amount, payment_method)
           VALUES (?,?,?,?,?,?,?)''',
        (ORD_SPREAD, ORD_SPREAD, BUYER_UID, 95.00, 4.75, 15.00, 'card')
    )
    conn.execute(
        '''INSERT INTO order_payouts (order_ledger_id, order_id, seller_id,
               payout_status, seller_gross_amount, fee_amount,
               seller_net_amount, spread_capture_amount, provider_transfer_id)
           VALUES (?,?,?,?,?,?,?,?,?)''',
        (ORD_SPREAD, ORD_SPREAD, SELLER1_UID, 'PAID_OUT',
         95.00, 4.75, 90.25, 15.00, 'tr_spread_ok')
    )
    conn.commit()
    conn.close()

    resp = admin_client.get('/admin/api/reconciliation/rows?recon_status=MATCHED_SPREAD')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['success'] is True
    spread_rows = [r for r in data['rows'] if r['order_id'] == ORD_SPREAD]
    assert len(spread_rows) == 1
    assert spread_rows[0]['recon_status'] == 'MATCHED_SPREAD'
    assert spread_rows[0]['is_problem'] is False
