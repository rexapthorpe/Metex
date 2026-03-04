"""
Tests: direct_buy_item spot freshness gate

Proves that /direct_buy/<bucket_id> (the ACTUAL purchase route used by the
"Buy Item" → "Yes, Complete Purchase" modal on the bucket page) correctly:

  A. Returns 409 SPOT_EXPIRED when the snapshot is stale — no order created.
  B. Returns 200 success when the snapshot is fresh — order created.
  C. Static-price listings bypass spot checks entirely — always succeeds.

Root cause fixed: direct_buy_item() was calling get_effective_price() without
spot_prices, which internally called get_current_spot_prices() (5-min cache,
external API) instead of check_spot_map_freshness(), bypassing the modal-first
freshness gate entirely.
"""

import os
import sys
import sqlite3
import tempfile
import shutil
import pytest
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS system_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS spot_price_snapshots (
    id         INTEGER   PRIMARY KEY AUTOINCREMENT,
    metal      TEXT      NOT NULL,
    price_usd  REAL      NOT NULL,
    as_of      TIMESTAMP NOT NULL,
    source     TEXT      DEFAULT 'metalpriceapi',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    DEFAULT '',
    password      TEXT    DEFAULT '',
    is_admin      INTEGER DEFAULT 0,
    username      TEXT,
    password_hash TEXT    DEFAULT '',
    first_name    TEXT,
    last_name     TEXT,
    phone         TEXT,
    bio           TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_banned     INTEGER DEFAULT 0,
    is_frozen     INTEGER DEFAULT 0,
    freeze_reason TEXT    DEFAULT NULL
);
CREATE TABLE IF NOT EXISTS addresses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    name         TEXT,
    street       TEXT    NOT NULL DEFAULT '',
    street_line2 TEXT,
    city         TEXT    NOT NULL DEFAULT '',
    state        TEXT    NOT NULL DEFAULT '',
    zip_code     TEXT    NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS categories (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT,
    year               TEXT,
    weight             TEXT,
    purity             TEXT,
    mint               TEXT,
    country_of_origin  TEXT,
    coin_series        TEXT,
    denomination       TEXT,
    grade              TEXT,
    finish             TEXT,
    special_designation TEXT,
    metal              TEXT,
    product_type       TEXT,
    bucket_id          INTEGER,
    product_line       TEXT,
    graded             INTEGER DEFAULT 0,
    grading_service    TEXT,
    is_isolated        INTEGER NOT NULL DEFAULT 0,
    condition_category TEXT,
    series_variant     TEXT,
    platform_fee_type  TEXT,
    platform_fee_value REAL,
    fee_updated_at     TIMESTAMP
);
CREATE TABLE IF NOT EXISTS listings (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id      INTEGER NOT NULL,
    category_id    INTEGER NOT NULL,
    quantity       INTEGER DEFAULT 1,
    price_per_coin REAL    DEFAULT 0,
    active         INTEGER DEFAULT 1,
    name           TEXT,
    description    TEXT,
    pricing_mode   TEXT    DEFAULT 'static',
    spot_premium   REAL    DEFAULT 0,
    floor_price    REAL    DEFAULT 0,
    pricing_metal  TEXT,
    is_isolated    INTEGER NOT NULL DEFAULT 0,
    isolated_type  TEXT,
    issue_number   INTEGER,
    issue_total    INTEGER,
    graded         INTEGER DEFAULT 0,
    grading_service TEXT,
    packaging_type  TEXT,
    packaging_notes TEXT,
    cert_number     TEXT,
    condition_notes TEXT,
    actual_year     TEXT,
    image_url       TEXT,
    edition_number  INTEGER,
    edition_total   INTEGER,
    photo_filename  TEXT,
    listing_title   TEXT
);
CREATE TABLE IF NOT EXISTS listing_photos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL,
    file_path  TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_id             INTEGER,
    total_price          REAL,
    status               TEXT DEFAULT 'pending',
    shipping_address     TEXT,
    recipient_first_name TEXT,
    recipient_last_name  TEXT,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS order_items (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id                    INTEGER,
    listing_id                  INTEGER,
    quantity                    INTEGER,
    price_each                  REAL,
    price_at_purchase           REAL,
    pricing_mode_at_purchase    TEXT,
    spot_price_at_purchase      REAL,
    seller_price_each           REAL,
    third_party_grading_requested INTEGER DEFAULT 0,
    packaging_type              TEXT,
    cert_number                 TEXT,
    condition_notes             TEXT,
    grading_fee_charged         REAL    DEFAULT 0,
    grading_service             TEXT    DEFAULT 'PCGS',
    grading_status              TEXT    DEFAULT 'not_requested',
    seller_tracking_to_grader   TEXT,
    spot_as_of_used             TEXT,
    spot_source_used            TEXT,
    spot_premium_used           REAL,
    weight_used                 REAL
);
CREATE TABLE IF NOT EXISTS price_locks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id  INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    locked_price REAL   NOT NULL,
    expires_at  TIMESTAMP NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS notification_settings (
    user_id             INTEGER,
    notification_type   TEXT,
    enabled             INTEGER DEFAULT 1,
    PRIMARY KEY (user_id, notification_type)
);
CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER,
    type       TEXT,
    message    TEXT,
    is_read    INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS ledger_entries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS ratings (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id  INTEGER NOT NULL,
    rater_id  INTEGER NOT NULL,
    ratee_id  INTEGER NOT NULL,
    rating    INTEGER NOT NULL,
    comment   TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

BUCKET_ID  = 9901
SELLER_ID  = 9902
BUYER_ID   = 9903
GOLD_PRICE = 3200.0
PREMIUM    = 50.0
FLOOR      = 2500.0
MAX_AGE    = 30   # seconds — set via system_settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def test_db():
    """Module-scoped temp DB wired into all relevant modules."""
    # Import app first so blueprint routes bind to the real get_db_connection
    from app import app as _flask_app  # noqa: F401 — side-effect import

    import database
    import utils.auth_utils as auth_utils_mod
    import services.order_service as order_service_mod
    import core.blueprints.checkout.routes as checkout_routes_mod
    import core.blueprints.buy.direct_purchase as direct_purchase_mod

    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "direct_buy_spot_test.db")

    raw = sqlite3.connect(db_path)
    raw.executescript(SCHEMA)
    raw.commit()
    raw.close()

    orig_db              = database.get_db_connection
    orig_auth            = auth_utils_mod.get_db_connection
    orig_order           = order_service_mod._get_conn
    orig_checkout_routes = checkout_routes_mod.get_db_connection
    orig_direct_purchase = direct_purchase_mod.get_db_connection

    def get_test_conn():
        c = sqlite3.connect(db_path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    database.get_db_connection              = get_test_conn
    auth_utils_mod.get_db_connection        = get_test_conn
    order_service_mod._get_conn             = get_test_conn
    checkout_routes_mod.get_db_connection   = get_test_conn
    direct_purchase_mod.get_db_connection   = get_test_conn

    # Set max_age = 30s in system_settings
    conn = get_test_conn()
    conn.execute(
        "INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
        ("spot_max_age_seconds_checkout", str(MAX_AGE)),
    )
    conn.commit()
    conn.close()

    yield db_path, get_test_conn

    database.get_db_connection              = orig_db
    auth_utils_mod.get_db_connection        = orig_auth
    order_service_mod._get_conn             = orig_order
    checkout_routes_mod.get_db_connection   = orig_checkout_routes
    direct_purchase_mod.get_db_connection   = orig_direct_purchase
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="module")
def flask_client(test_db):
    """Flask test client with seller + buyer users and a saved address."""
    from app import app as flask_app

    _, get_test_conn = test_db
    flask_app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-direct-buy-spot-key",
    })

    conn = get_test_conn()
    for uid, uname in [(SELLER_ID, "dbs_seller"), (BUYER_ID, "dbs_buyer")]:
        if not conn.execute("SELECT id FROM users WHERE id=?", (uid,)).fetchone():
            conn.execute(
                "INSERT INTO users (id, username, email) VALUES (?, ?, ?)",
                (uid, uname, f"{uname}@t.com"),
            )

    # Address for buyer
    if not conn.execute("SELECT id FROM addresses WHERE user_id=?", (BUYER_ID,)).fetchone():
        conn.execute(
            "INSERT INTO addresses (user_id, name, street, city, state, zip_code) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (BUYER_ID, "Home", "123 Main St", "Anytown", "CA", "90210"),
        )
    conn.commit()
    conn.close()

    with flask_app.test_client() as client:
        yield client


def _login_buyer(client):
    with client.session_transaction() as sess:
        sess["user_id"] = BUYER_ID


def _get_address_id(get_conn):
    conn = get_conn()
    row = conn.execute("SELECT id FROM addresses WHERE user_id=?", (BUYER_ID,)).fetchone()
    conn.close()
    return row["id"] if row else None


def _insert_spot_listing(get_conn, seller_id=SELLER_ID, bucket_id=BUCKET_ID):
    """Insert a premium_to_spot gold listing. Returns (category_id, listing_id)."""
    conn = get_conn()
    conn.execute(
        "INSERT INTO categories (bucket_id, metal, product_type, weight, mint, year, "
        "product_line, purity, finish) VALUES (?,?,?,?,?,?,?,?,?)",
        (bucket_id, "gold", "Coin", "1.0", "US Mint", "2024", "AE", ".9999", "BU"),
    )
    cat_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO listings (seller_id, category_id, quantity, price_per_coin, "
        "pricing_mode, spot_premium, floor_price, pricing_metal) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (seller_id, cat_id, 5, FLOOR, "premium_to_spot", PREMIUM, FLOOR, "gold"),
    )
    lid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return cat_id, lid


def _insert_static_listing(get_conn, seller_id=SELLER_ID, bucket_id=9951):
    """Insert a static-price listing in a different bucket."""
    conn = get_conn()
    conn.execute(
        "INSERT INTO categories (bucket_id, metal, product_type, weight, mint, year, "
        "product_line, purity, finish) VALUES (?,?,?,?,?,?,?,?,?)",
        (bucket_id, "gold", "Bar", "1.0", "PAMP", "2023", "Fortuna", ".9999", "BU"),
    )
    cat_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO listings (seller_id, category_id, quantity, price_per_coin, "
        "pricing_mode) VALUES (?,?,?,?,?)",
        (seller_id, cat_id, 5, 2000.0, "static"),
    )
    lid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return cat_id, lid


def _insert_snapshot(get_conn, metal, price, age_seconds=0):
    as_of = (datetime.now() - timedelta(seconds=age_seconds)).isoformat()
    conn = get_conn()
    conn.execute(
        "INSERT INTO spot_price_snapshots (metal, price_usd, as_of, source) "
        "VALUES (?, ?, ?, ?)",
        (metal, price, as_of, "metalpriceapi"),
    )
    conn.commit()
    conn.close()


def _clear_snapshots(get_conn):
    conn = get_conn()
    conn.execute("DELETE FROM spot_price_snapshots")
    conn.commit()
    conn.close()


def _count_orders(get_conn):
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    conn.close()
    return n


# ---------------------------------------------------------------------------
# Test A: Stale snapshot → 409 SPOT_EXPIRED, no order created
# ---------------------------------------------------------------------------

class TestDirectBuyBlockedOnStaleSpot:

    def test_a1_stale_snapshot_returns_spot_expired(self, flask_client, test_db):
        """
        premium_to_spot listing + snapshot > MAX_AGE seconds old
        → 409 SPOT_EXPIRED, no order created.
        """
        _, get_conn = test_db
        _clear_snapshots(get_conn)
        cat_id, lid = _insert_spot_listing(get_conn)
        _insert_snapshot(get_conn, "gold", GOLD_PRICE, age_seconds=MAX_AGE + 60)

        addr_id = _get_address_id(get_conn)
        orders_before = _count_orders(get_conn)

        _login_buyer(flask_client)
        resp = flask_client.post(
            f"/direct_buy/{BUCKET_ID}",
            data={"quantity": "1", "address_id": str(addr_id),
                  "third_party_grading": "0"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert resp.status_code == 409, f"Expected 409, got {resp.status_code}"
        data = resp.get_json()
        assert data["success"] is False
        assert data["error_code"] == "SPOT_EXPIRED"
        assert _count_orders(get_conn) == orders_before, "No order should be created"

    def test_a2_no_snapshot_at_all_returns_spot_expired(self, flask_client, test_db):
        """
        premium_to_spot listing + no snapshot at all
        → 409 SPOT_EXPIRED, no order created.
        """
        _, get_conn = test_db
        _clear_snapshots(get_conn)
        # Reuse existing spot listing from test_a1 (same bucket_id)

        addr_id = _get_address_id(get_conn)
        orders_before = _count_orders(get_conn)

        _login_buyer(flask_client)
        resp = flask_client.post(
            f"/direct_buy/{BUCKET_ID}",
            data={"quantity": "1", "address_id": str(addr_id),
                  "third_party_grading": "0"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert resp.status_code == 409
        data = resp.get_json()
        assert data["error_code"] == "SPOT_EXPIRED"
        assert _count_orders(get_conn) == orders_before


# ---------------------------------------------------------------------------
# Test B: Fresh snapshot → 200 success, order created
# ---------------------------------------------------------------------------

class TestDirectBuySucceedsWithFreshSpot:

    def test_b1_fresh_snapshot_creates_order(self, flask_client, test_db):
        """
        premium_to_spot listing + snapshot < MAX_AGE seconds old
        → 200 success, order row created.
        """
        _, get_conn = test_db
        _clear_snapshots(get_conn)
        _insert_snapshot(get_conn, "gold", GOLD_PRICE, age_seconds=5)  # 5s old → fresh

        addr_id = _get_address_id(get_conn)
        orders_before = _count_orders(get_conn)

        _login_buyer(flask_client)
        resp = flask_client.post(
            f"/direct_buy/{BUCKET_ID}",
            data={"quantity": "1", "address_id": str(addr_id),
                  "third_party_grading": "0"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.data}"
        data = resp.get_json()
        assert data["success"] is True
        assert _count_orders(get_conn) == orders_before + 1, "Order should be created"

    def test_b2_fresh_snapshot_price_reflects_spot(self, flask_client, test_db):
        """
        The order price_each should be spot + premium (or floor if higher).
        """
        _, get_conn = test_db
        _clear_snapshots(get_conn)
        # Insert fresh listing again (previous one may have 0 quantity now)
        cat_id, lid = _insert_spot_listing(get_conn)
        _insert_snapshot(get_conn, "gold", GOLD_PRICE, age_seconds=2)

        addr_id = _get_address_id(get_conn)

        _login_buyer(flask_client)
        resp = flask_client.post(
            f"/direct_buy/{BUCKET_ID}",
            data={"quantity": "1", "address_id": str(addr_id),
                  "third_party_grading": "0"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

        # Price should be max(GOLD_PRICE + PREMIUM, FLOOR) = 3250.0
        expected_price = max(GOLD_PRICE + PREMIUM, FLOOR)
        conn = get_conn()
        row = conn.execute(
            "SELECT price_each FROM order_items ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert row is not None
        assert abs(row["price_each"] - expected_price) < 0.01, (
            f"Expected price_each≈{expected_price}, got {row['price_each']}"
        )


# ---------------------------------------------------------------------------
# Test C: Static-price listing → not blocked by spot check
# ---------------------------------------------------------------------------

class TestDirectBuyStaticNotBlocked:

    def test_c1_static_listing_succeeds_with_no_snapshot(self, flask_client, test_db):
        """
        Static-price listing with NO spot snapshots at all
        → 200 success (no spot check performed).
        """
        _, get_conn = test_db
        _clear_snapshots(get_conn)  # no snapshots at all

        static_bucket_id = 9951
        cat_id, lid = _insert_static_listing(get_conn, bucket_id=static_bucket_id)

        addr_id = _get_address_id(get_conn)
        orders_before = _count_orders(get_conn)

        _login_buyer(flask_client)
        resp = flask_client.post(
            f"/direct_buy/{static_bucket_id}",
            data={"quantity": "1", "address_id": str(addr_id),
                  "third_party_grading": "0"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert resp.status_code == 200, f"Static listing should not need spot: {resp.data}"
        data = resp.get_json()
        assert data["success"] is True
        assert _count_orders(get_conn) == orders_before + 1

    def test_c2_static_listing_succeeds_with_stale_snapshot(self, flask_client, test_db):
        """
        Static-price listing + stale snapshot → 200 success (spot irrelevant).
        """
        _, get_conn = test_db
        _clear_snapshots(get_conn)
        _insert_snapshot(get_conn, "gold", GOLD_PRICE, age_seconds=MAX_AGE + 300)

        static_bucket_id = 9951
        cat_id, lid = _insert_static_listing(get_conn, bucket_id=static_bucket_id)

        addr_id = _get_address_id(get_conn)
        orders_before = _count_orders(get_conn)

        _login_buyer(flask_client)
        resp = flask_client.post(
            f"/direct_buy/{static_bucket_id}",
            data={"quantity": "1", "address_id": str(addr_id),
                  "third_party_grading": "0"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert _count_orders(get_conn) == orders_before + 1
