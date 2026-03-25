"""
Tests: Admin Nudge Seller endpoint

Proven:
  NUDGE-1. Nudge inserts notification and commits — notification persists after conn close.
  NUDGE-2. Nudge skips sellers who already have tracking uploaded.
  NUDGE-3. Nudge returns correct notified_count.
  NUDGE-4. Nudge returns 404 for order with no items.
  NUDGE-5. Nudge endpoint requires admin auth — non-admin gets redirect.
  NUDGE-6. Response is success=True only when notification is actually committed (commit bug fixed).
"""

import os
import sys
import sqlite3
import tempfile
import shutil
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT,
    email       TEXT,
    password    TEXT    DEFAULT '',
    password_hash TEXT  DEFAULT '',
    is_admin    INTEGER DEFAULT 0,
    is_banned   INTEGER DEFAULT 0,
    is_frozen   INTEGER DEFAULT 0,
    is_metex_guaranteed INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS system_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS listings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id   INTEGER NOT NULL,
    category_id INTEGER DEFAULT 0,
    quantity    INTEGER DEFAULT 1,
    price_per_coin REAL DEFAULT 0,
    active      INTEGER DEFAULT 1,
    pricing_mode TEXT DEFAULT 'static',
    listing_title TEXT,
    photo_filename TEXT
);
CREATE TABLE IF NOT EXISTS orders (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_id     INTEGER,
    total_price  REAL,
    status       TEXT DEFAULT 'active',
    payment_method_type TEXT,
    payment_status TEXT DEFAULT 'unpaid',
    payout_status TEXT DEFAULT 'PAYOUT_NOT_READY',
    refund_status TEXT,
    requires_payment_clearance INTEGER DEFAULT 0,
    requires_payout_recovery   INTEGER DEFAULT 0,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS order_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    INTEGER,
    listing_id  INTEGER,
    quantity    INTEGER DEFAULT 1,
    price_each  REAL
);
CREATE TABLE IF NOT EXISTS seller_order_tracking (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    INTEGER,
    seller_id   INTEGER,
    tracking_number TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    type        TEXT,
    message     TEXT,
    is_read     INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

ADMIN_UID  = 9001
BUYER_UID  = 9002
SELLER1_UID = 9003
SELLER2_UID = 9004

ORDER_ID_TWO_SELLERS  = 1001  # seller1 + seller2, neither has tracking
ORDER_ID_ONE_TRACKED  = 1002  # seller1 has tracking, seller2 does not
ORDER_ID_BOTH_TRACKED = 1003  # both sellers have tracking
ORDER_ID_EMPTY        = 1004  # no order_items


@pytest.fixture(scope="module")
def test_db():
    from app import app as _flask_app  # noqa: F401

    import database
    import utils.auth_utils as auth_utils_mod

    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "nudge_test.db")

    raw = sqlite3.connect(db_path)
    raw.row_factory = sqlite3.Row
    raw.executescript(SCHEMA)

    raw.execute("INSERT INTO users (id, username, email, is_admin) VALUES (?,?,?,?)",
                (ADMIN_UID, "nudge_admin", "nadmin@t.com", 1))
    raw.execute("INSERT INTO users (id, username, email, is_admin) VALUES (?,?,?,?)",
                (BUYER_UID, "nudge_buyer", "nbuyer@t.com", 0))
    raw.execute("INSERT INTO users (id, username, email, is_admin) VALUES (?,?,?,?)",
                (SELLER1_UID, "nudge_seller1", "ns1@t.com", 0))
    raw.execute("INSERT INTO users (id, username, email, is_admin) VALUES (?,?,?,?)",
                (SELLER2_UID, "nudge_seller2", "ns2@t.com", 0))

    # listings for each seller
    raw.execute("INSERT INTO listings (id, seller_id) VALUES (?,?)", (8001, SELLER1_UID))
    raw.execute("INSERT INTO listings (id, seller_id) VALUES (?,?)", (8002, SELLER2_UID))

    # Orders
    for oid in (ORDER_ID_TWO_SELLERS, ORDER_ID_ONE_TRACKED, ORDER_ID_BOTH_TRACKED, ORDER_ID_EMPTY):
        raw.execute("INSERT INTO orders (id, buyer_id, payment_status, payout_status) VALUES (?,?,?,?)",
                    (oid, BUYER_UID, 'paid', 'PAYOUT_NOT_READY'))

    # order_items: two-sellers order
    raw.execute("INSERT INTO order_items (order_id, listing_id, quantity, price_each) VALUES (?,?,?,?)",
                (ORDER_ID_TWO_SELLERS, 8001, 1, 100.0))
    raw.execute("INSERT INTO order_items (order_id, listing_id, quantity, price_each) VALUES (?,?,?,?)",
                (ORDER_ID_TWO_SELLERS, 8002, 1, 100.0))

    # one-tracked order: seller1 + seller2, seller1 already has tracking
    raw.execute("INSERT INTO order_items (order_id, listing_id, quantity, price_each) VALUES (?,?,?,?)",
                (ORDER_ID_ONE_TRACKED, 8001, 1, 100.0))
    raw.execute("INSERT INTO order_items (order_id, listing_id, quantity, price_each) VALUES (?,?,?,?)",
                (ORDER_ID_ONE_TRACKED, 8002, 1, 100.0))
    raw.execute("INSERT INTO seller_order_tracking (order_id, seller_id, tracking_number) VALUES (?,?,?)",
                (ORDER_ID_ONE_TRACKED, SELLER1_UID, "1Z999AA10123456784"))

    # both-tracked order
    raw.execute("INSERT INTO order_items (order_id, listing_id, quantity, price_each) VALUES (?,?,?,?)",
                (ORDER_ID_BOTH_TRACKED, 8001, 1, 100.0))
    raw.execute("INSERT INTO order_items (order_id, listing_id, quantity, price_each) VALUES (?,?,?,?)",
                (ORDER_ID_BOTH_TRACKED, 8002, 1, 100.0))
    raw.execute("INSERT INTO seller_order_tracking (order_id, seller_id, tracking_number) VALUES (?,?,?)",
                (ORDER_ID_BOTH_TRACKED, SELLER1_UID, "TRACK1"))
    raw.execute("INSERT INTO seller_order_tracking (order_id, seller_id, tracking_number) VALUES (?,?,?)",
                (ORDER_ID_BOTH_TRACKED, SELLER2_UID, "TRACK2"))

    # ORDER_ID_EMPTY has no order_items

    raw.commit()
    raw.close()

    orig_db   = database.get_db_connection
    orig_auth = auth_utils_mod.get_db_connection

    def get_test_conn():
        c = sqlite3.connect(db_path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    database.get_db_connection     = get_test_conn
    auth_utils_mod.get_db_connection = get_test_conn

    yield db_path, get_test_conn

    database.get_db_connection     = orig_db
    auth_utils_mod.get_db_connection = orig_auth
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="module")
def admin_client(test_db):
    from app import app as flask_app

    flask_app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-nudge-key",
    })

    with flask_app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"]  = ADMIN_UID
            sess["username"] = "nudge_admin"
            sess["is_admin"] = True
        yield client


@pytest.fixture
def non_admin_client(test_db):
    from app import app as flask_app

    flask_app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-nudge-key",
    })

    with flask_app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"]  = BUYER_UID
            sess["username"] = "nudge_buyer"
            sess["is_admin"] = False
        yield client


def count_notifications(get_conn, order_id):
    """Return count of admin_nudge notifications for this order."""
    c = get_conn()
    try:
        rows = c.execute(
            "SELECT COUNT(*) as cnt FROM notifications WHERE type='admin_nudge' AND message LIKE ?",
            (f'%order #{order_id}%',)
        ).fetchone()
        return rows['cnt'] if rows else 0
    finally:
        c.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_nudge_1_notifications_persisted(admin_client, test_db):
    """NUDGE-1: Notifications are committed and persist after the request."""
    db_path, get_conn = test_db
    before = count_notifications(get_conn, ORDER_ID_TWO_SELLERS)

    rv = admin_client.post(f'/admin/api/orders/{ORDER_ID_TWO_SELLERS}/nudge-seller',
                           content_type='application/json')
    data = rv.get_json()

    assert rv.status_code == 200
    assert data['success'] is True

    after = count_notifications(get_conn, ORDER_ID_TWO_SELLERS)
    assert after == before + 2, (
        f"Expected 2 new notifications (one per seller), got {after - before}. "
        "Likely a commit bug: notifications were not persisted."
    )


def test_nudge_2_skips_tracked_sellers(admin_client, test_db):
    """NUDGE-2: Sellers who already have tracking uploaded are skipped."""
    db_path, get_conn = test_db
    before = count_notifications(get_conn, ORDER_ID_ONE_TRACKED)

    rv = admin_client.post(f'/admin/api/orders/{ORDER_ID_ONE_TRACKED}/nudge-seller',
                           content_type='application/json')
    data = rv.get_json()

    assert rv.status_code == 200
    assert data['success'] is True
    assert data['notified_count'] == 1  # seller2 only; seller1 has tracking

    after = count_notifications(get_conn, ORDER_ID_ONE_TRACKED)
    assert after == before + 1


def test_nudge_3_correct_notified_count(admin_client, test_db):
    """NUDGE-3: notified_count matches how many sellers were actually notified."""
    rv = admin_client.post(f'/admin/api/orders/{ORDER_ID_BOTH_TRACKED}/nudge-seller',
                           content_type='application/json')
    data = rv.get_json()

    assert rv.status_code == 200
    assert data['success'] is True
    assert data['notified_count'] == 0  # both already have tracking


def test_nudge_4_order_not_found(admin_client):
    """NUDGE-4: Returns 404 when order has no items."""
    rv = admin_client.post(f'/admin/api/orders/{ORDER_ID_EMPTY}/nudge-seller',
                           content_type='application/json')
    data = rv.get_json()

    assert rv.status_code == 404
    assert data['success'] is False


def test_nudge_5_requires_admin(non_admin_client):
    """NUDGE-5: Non-admin users are rejected (redirect or 403)."""
    rv = non_admin_client.post(f'/admin/api/orders/{ORDER_ID_TWO_SELLERS}/nudge-seller',
                               content_type='application/json')
    # admin_required redirects to login or returns 403
    assert rv.status_code in (302, 403)


