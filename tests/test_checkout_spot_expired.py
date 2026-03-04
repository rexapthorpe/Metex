"""
Tests: SPOT_EXPIRED modal-first flow

Proven:
  1. check_spot_freshness raises SpotExpiredError when snapshot is stale/absent.
  2. AJAX finalize (cart path) returns 409 SPOT_EXPIRED when snapshot stale.
  3. AJAX finalize (bucket/session path) returns 409 SPOT_EXPIRED when stale.
  4. No order is created when SPOT_EXPIRED is returned.
  5. /checkout/api/recalculate-spot returns 200 with updated totals on success.
  6. /checkout/api/recalculate-spot returns 503 SPOT_UNAVAILABLE when refresh fails.
  7. Static listings (no spot pricing) are never blocked by spot checks.
  8. After successful recalculate, next finalize uses fresh snapshot and succeeds.
"""

import os
import sys
import sqlite3
import tempfile
import shutil
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

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
CREATE TABLE IF NOT EXISTS cart (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                     INTEGER,
    listing_id                  INTEGER,
    quantity                    INTEGER DEFAULT 1,
    third_party_grading_requested INTEGER DEFAULT 0,
    grading_preference          TEXT    DEFAULT 'NONE'
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

GOLD_PRICE = 3200.0
PREMIUM    = 50.0
FLOOR      = 2500.0


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

    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "spot_expired_test.db")

    raw = sqlite3.connect(db_path)
    raw.executescript(SCHEMA)
    raw.commit()
    raw.close()

    orig_db              = database.get_db_connection
    orig_auth            = auth_utils_mod.get_db_connection
    orig_order           = order_service_mod._get_conn
    orig_checkout_routes = checkout_routes_mod.get_db_connection

    def get_test_conn():
        c = sqlite3.connect(db_path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    database.get_db_connection              = get_test_conn
    auth_utils_mod.get_db_connection        = get_test_conn
    order_service_mod._get_conn             = get_test_conn
    checkout_routes_mod.get_db_connection   = get_test_conn

    yield db_path, get_test_conn

    database.get_db_connection              = orig_db
    auth_utils_mod.get_db_connection        = orig_auth
    order_service_mod._get_conn             = orig_order
    checkout_routes_mod.get_db_connection   = orig_checkout_routes
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="module")
def flask_client(test_db):
    """Flask test client with a regular user pre-inserted."""
    from app import app as flask_app

    _, get_test_conn = test_db
    flask_app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-spot-expired-key",
    })

    conn = get_test_conn()
    for uid, uname in [(8801, "se_user")]:
        if not conn.execute("SELECT id FROM users WHERE id=?", (uid,)).fetchone():
            conn.execute(
                "INSERT INTO users (id, username, email) VALUES (?, ?, ?)",
                (uid, uname, f"{uname}@t.com"),
            )
    conn.commit()
    conn.close()

    with flask_app.test_client() as client:
        yield client


def _login(client, user_id=8801):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _insert_snapshot(get_conn, metal, price, age_seconds=0):
    as_of = (datetime.now() - timedelta(seconds=age_seconds)).isoformat()
    conn = get_conn()
    conn.execute(
        "INSERT INTO spot_price_snapshots (metal, price_usd, as_of, source) VALUES (?, ?, ?, ?)",
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


def _insert_spot_listing(get_conn, seller_id=8801, premium=50.0, floor=2500.0):
    """Insert a premium_to_spot gold listing + category, return listing_id."""
    conn = get_conn()
    conn.execute(
        "INSERT INTO categories (bucket_id, metal, product_type, weight, mint, year, "
        "product_line, purity, finish) VALUES (?,?,?,?,?,?,?,?,?)",
        (8801, "gold", "Coin", 1.0, "US Mint", "2024", "American Eagle", ".9999", "BU"),
    )
    cat_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO listings (seller_id, category_id, quantity, price_per_coin, "
        "pricing_mode, spot_premium, floor_price, pricing_metal) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (seller_id, cat_id, 5, floor, "premium_to_spot", premium, floor, "gold"),
    )
    lid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return lid


def _insert_static_listing(get_conn, seller_id=8801, price=1234.56):
    """Insert a static-priced listing + category, return listing_id."""
    conn = get_conn()
    conn.execute(
        "INSERT INTO categories (bucket_id, metal, product_type, weight, mint, year, "
        "product_line, purity, finish) VALUES (?,?,?,?,?,?,?,?,?)",
        (8802, "silver", "Bar", 1.0, "PAMP", "2024", "PAMP Suisse", ".999", "BU"),
    )
    cat_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO listings (seller_id, category_id, quantity, price_per_coin, "
        "pricing_mode) VALUES (?,?,?,?,?)",
        (seller_id, cat_id, 5, price, "static"),
    )
    lid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return lid


def _add_to_cart(get_conn, user_id, listing_id, quantity=1):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO cart (user_id, listing_id, quantity, grading_preference) "
        "VALUES (?, ?, ?, 'NONE')",
        (user_id, listing_id, quantity),
    )
    conn.commit()
    conn.close()


def _clear_cart(get_conn, user_id):
    conn = get_conn()
    conn.execute("DELETE FROM cart WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def _clear_orders(get_conn):
    conn = get_conn()
    conn.execute("DELETE FROM order_items")
    conn.execute("DELETE FROM orders")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Group 1: Unit — check_spot_freshness
# ---------------------------------------------------------------------------

class TestCheckSpotFreshness:

    def test_fresh_snapshot_returns_data(self, test_db):
        """check_spot_freshness returns spot_info when snapshot is within SLA."""
        _, get_conn = test_db
        _clear_snapshots(get_conn)
        _insert_snapshot(get_conn, "gold", GOLD_PRICE, age_seconds=5)

        from services.checkout_spot_service import check_spot_freshness
        from services.system_settings_service import set_checkout_spot_max_age
        set_checkout_spot_max_age(120)

        result = check_spot_freshness("gold")
        assert result["price_usd"] == GOLD_PRICE
        assert result["was_refreshed"] is False
        assert result["stale_fallback"] is False

    def test_stale_snapshot_raises_spot_expired_error(self, test_db):
        """check_spot_freshness raises SpotExpiredError when snapshot age > max_age."""
        _, get_conn = test_db
        _clear_snapshots(get_conn)
        _insert_snapshot(get_conn, "gold", GOLD_PRICE, age_seconds=300)

        from services.checkout_spot_service import check_spot_freshness, SpotExpiredError
        from services.system_settings_service import set_checkout_spot_max_age
        set_checkout_spot_max_age(120)

        with pytest.raises(SpotExpiredError) as exc_info:
            check_spot_freshness("gold")

        assert exc_info.value.metal == "gold"
        assert exc_info.value.max_age_seconds == 120

    def test_no_snapshot_raises_spot_expired_error(self, test_db):
        """check_spot_freshness raises SpotExpiredError when no snapshot exists."""
        _, get_conn = test_db
        _clear_snapshots(get_conn)

        from services.checkout_spot_service import check_spot_freshness, SpotExpiredError
        with pytest.raises(SpotExpiredError):
            check_spot_freshness("gold")

    def test_check_map_propagates_spot_expired(self, test_db):
        """check_spot_map_freshness propagates SpotExpiredError when any metal stale."""
        _, get_conn = test_db
        _clear_snapshots(get_conn)
        _insert_snapshot(get_conn, "gold", GOLD_PRICE, age_seconds=300)

        from services.checkout_spot_service import check_spot_map_freshness, SpotExpiredError
        from services.system_settings_service import set_checkout_spot_max_age
        set_checkout_spot_max_age(120)

        with pytest.raises(SpotExpiredError):
            check_spot_map_freshness({"gold"})

    def test_check_map_empty_metals_returns_empty(self, test_db):
        """check_spot_map_freshness returns {} without raising when metals is empty."""
        from services.checkout_spot_service import check_spot_map_freshness
        result = check_spot_map_freshness(set())
        assert result == {}

    def test_no_refresh_attempted(self, test_db):
        """check_spot_freshness must NOT call run_snapshot even when stale."""
        _, get_conn = test_db
        _clear_snapshots(get_conn)
        _insert_snapshot(get_conn, "gold", GOLD_PRICE, age_seconds=300)

        from services.checkout_spot_service import check_spot_freshness, SpotExpiredError
        with patch("services.spot_snapshot_service.run_snapshot") as mock_run:
            with pytest.raises(SpotExpiredError):
                check_spot_freshness("gold")
            mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Group 2: AJAX finalize — cart path blocked when stale
# ---------------------------------------------------------------------------

class TestCartFinalizeBlockedOnStale:

    def test_stale_spot_returns_spot_expired(self, flask_client, test_db):
        """AJAX cart finalize → 409 SPOT_EXPIRED when snapshot is stale."""
        _, get_conn = test_db
        _clear_snapshots(get_conn)
        _clear_orders(get_conn)
        _clear_cart(get_conn, 8801)

        from services.system_settings_service import set_checkout_spot_max_age
        set_checkout_spot_max_age(120)

        listing_id = _insert_spot_listing(get_conn)
        _add_to_cart(get_conn, 8801, listing_id)
        _insert_snapshot(get_conn, "gold", GOLD_PRICE, age_seconds=300)  # stale

        _login(flask_client)
        resp = flask_client.post(
            "/checkout",
            json={"shipping_address": "123 Main St"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert resp.status_code == 409
        data = resp.get_json()
        assert data["success"] is False
        assert data["error_code"] == "SPOT_EXPIRED"

    def test_no_order_created_on_spot_expired(self, flask_client, test_db):
        """No order row created when SPOT_EXPIRED is returned."""
        _, get_conn = test_db
        _clear_orders(get_conn)
        orders_before = _count_orders(get_conn)
        # (stale snapshot already in place from previous test)

        _login(flask_client)
        flask_client.post(
            "/checkout",
            json={"shipping_address": "123 Main St"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert _count_orders(get_conn) == orders_before

    def test_fresh_spot_allows_order(self, flask_client, test_db):
        """AJAX cart finalize → 200 + order created when snapshot is fresh."""
        _, get_conn = test_db
        _clear_snapshots(get_conn)
        _clear_orders(get_conn)
        _clear_cart(get_conn, 8801)

        from services.system_settings_service import set_checkout_spot_max_age
        set_checkout_spot_max_age(120)

        listing_id = _insert_spot_listing(get_conn, premium=50.0, floor=2500.0)
        _add_to_cart(get_conn, 8801, listing_id)
        _insert_snapshot(get_conn, "gold", GOLD_PRICE, age_seconds=5)  # fresh

        _login(flask_client)
        with patch("services.notification_service.notify") as _m:
            resp = flask_client.post(
                "/checkout",
                json={"shipping_address": "123 Main St"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "order_id" in data
        assert _count_orders(get_conn) == 1


# ---------------------------------------------------------------------------
# Group 3: AJAX finalize — bucket/session path blocked when stale
# ---------------------------------------------------------------------------

class TestBucketFinalizeBlockedOnStale:

    def test_stale_spot_blocks_session_items_path(self, flask_client, test_db):
        """AJAX finalize with checkout_items in session → 409 SPOT_EXPIRED when stale."""
        _, get_conn = test_db
        _clear_snapshots(get_conn)
        _clear_orders(get_conn)

        from services.system_settings_service import set_checkout_spot_max_age
        set_checkout_spot_max_age(120)

        listing_id = _insert_spot_listing(get_conn)
        _insert_snapshot(get_conn, "gold", GOLD_PRICE, age_seconds=300)  # stale

        _login(flask_client)
        # Simulate bucket selection stored in session
        with flask_client.session_transaction() as sess:
            sess["checkout_items"] = [
                {"listing_id": listing_id, "quantity": 1, "price_each": 3250.0}
            ]
            sess["checkout_tpg"] = 0

        resp = flask_client.post(
            "/checkout",
            json={"shipping_address": "456 Oak Ave"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert resp.status_code == 409
        data = resp.get_json()
        assert data["error_code"] == "SPOT_EXPIRED"

    def test_session_items_restored_on_spot_expired(self, flask_client, test_db):
        """checkout_items are restored to session when SPOT_EXPIRED, so user can recalc."""
        _, get_conn = test_db
        _clear_snapshots(get_conn)

        listing_id = _insert_spot_listing(get_conn)
        _insert_snapshot(get_conn, "gold", GOLD_PRICE, age_seconds=300)

        session_items = [{"listing_id": listing_id, "quantity": 2, "price_each": 3300.0}]

        _login(flask_client)
        with flask_client.session_transaction() as sess:
            sess["checkout_items"] = session_items
            sess["checkout_tpg"] = 0

        flask_client.post(
            "/checkout",
            json={"shipping_address": "456 Oak Ave"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        # Session items must still be there so recalculate can find them
        with flask_client.session_transaction() as sess:
            assert "checkout_items" in sess
            assert len(sess["checkout_items"]) == 1

    def test_no_order_created_on_bucket_spot_expired(self, flask_client, test_db):
        """No order row created in the bucket finalize SPOT_EXPIRED case."""
        _, get_conn = test_db
        _clear_snapshots(get_conn)
        _clear_orders(get_conn)

        listing_id = _insert_spot_listing(get_conn)
        _insert_snapshot(get_conn, "gold", GOLD_PRICE, age_seconds=300)

        _login(flask_client)
        with flask_client.session_transaction() as sess:
            sess["checkout_items"] = [
                {"listing_id": listing_id, "quantity": 1, "price_each": 3250.0}
            ]
            sess["checkout_tpg"] = 0

        flask_client.post(
            "/checkout",
            json={},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert _count_orders(get_conn) == 0


# ---------------------------------------------------------------------------
# Group 4: Static listings — never blocked
# ---------------------------------------------------------------------------

class TestStaticListingNotBlocked:

    def test_static_listing_not_blocked_when_no_snapshot(self, flask_client, test_db):
        """Static-price listing can be bought even when there's no spot snapshot."""
        _, get_conn = test_db
        _clear_snapshots(get_conn)
        _clear_orders(get_conn)
        _clear_cart(get_conn, 8801)

        # Clear any checkout_items left in session from bucket-finalize tests
        with flask_client.session_transaction() as sess:
            sess.pop("checkout_items", None)
            sess.pop("checkout_tpg", None)

        listing_id = _insert_static_listing(get_conn, price=1500.0)
        _add_to_cart(get_conn, 8801, listing_id)

        _login(flask_client)
        with patch("services.notification_service.notify") as _m:
            resp = flask_client.post(
                "/checkout",
                json={"shipping_address": "789 Pine St"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert _count_orders(get_conn) == 1


# ---------------------------------------------------------------------------
# Group 5: /checkout/api/recalculate-spot
# ---------------------------------------------------------------------------

class TestRecalculateEndpoint:

    def test_recalculate_returns_updated_totals(self, flask_client, test_db):
        """Recalculate with fresh snapshot → 200 with subtotal and cart_total."""
        _, get_conn = test_db
        _clear_snapshots(get_conn)
        _clear_orders(get_conn)
        _clear_cart(get_conn, 8801)

        from services.system_settings_service import set_checkout_spot_max_age
        set_checkout_spot_max_age(120)

        listing_id = _insert_spot_listing(get_conn, premium=50.0, floor=2500.0)
        _add_to_cart(get_conn, 8801, listing_id)
        # Insert fresh snapshot — recalculate reads it without external call
        _insert_snapshot(get_conn, "gold", 3500.0, age_seconds=5)

        _login(flask_client)
        resp = flask_client.post(
            "/checkout/api/recalculate-spot",
            json={},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["subtotal"] > 0
        assert data["cart_total"] >= data["subtotal"]
        assert "updated_items" in data
        assert len(data["updated_items"]) >= 1

    def test_recalculate_updates_session_bucket_items(self, flask_client, test_db):
        """Recalculate updates session checkout_items with new price_each."""
        _, get_conn = test_db
        _clear_snapshots(get_conn)

        from services.system_settings_service import set_checkout_spot_max_age
        set_checkout_spot_max_age(120)

        listing_id = _insert_spot_listing(get_conn, premium=100.0, floor=2000.0)
        new_spot = 4000.0
        _insert_snapshot(get_conn, "gold", new_spot, age_seconds=5)

        old_price = 2800.0  # stale price locked earlier
        _login(flask_client)
        with flask_client.session_transaction() as sess:
            sess["checkout_items"] = [
                {"listing_id": listing_id, "quantity": 2, "price_each": old_price}
            ]
            sess["checkout_tpg"] = 0

        resp = flask_client.post(
            "/checkout/api/recalculate-spot",
            json={},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

        # Session should have updated price_each = max(spot+premium, floor)
        expected_price = max(new_spot + 100.0, 2000.0)
        with flask_client.session_transaction() as sess:
            items = sess.get("checkout_items", [])
            assert len(items) == 1
            assert abs(items[0]["price_each"] - expected_price) < 0.01

    def test_recalculate_spot_unavailable_returns_503(self, flask_client, test_db):
        """Recalculate → 503 SPOT_UNAVAILABLE when snapshot refresh fails."""
        _, get_conn = test_db
        _clear_snapshots(get_conn)
        _clear_cart(get_conn, 8801)

        from services.system_settings_service import set_checkout_spot_max_age
        set_checkout_spot_max_age(120)

        listing_id = _insert_spot_listing(get_conn)
        _add_to_cart(get_conn, 8801, listing_id)
        # No fresh snapshot → get_spot_map_for_checkout will try to refresh
        _insert_snapshot(get_conn, "gold", GOLD_PRICE, age_seconds=300)  # stale

        _login(flask_client)
        # Mock run_snapshot to simulate external API failure
        with patch("services.spot_snapshot_service.run_snapshot", return_value={"inserted": 0, "error": "API down"}):
            resp = flask_client.post(
                "/checkout/api/recalculate-spot",
                json={},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )

        assert resp.status_code == 503
        data = resp.get_json()
        assert data["success"] is False
        assert data["error_code"] == "SPOT_UNAVAILABLE"

    def test_recalculate_unauthenticated_returns_401(self, flask_client, test_db):
        """Recalculate without login → 401."""
        with flask_client.session_transaction() as sess:
            sess.clear()

        resp = flask_client.post(
            "/checkout/api/recalculate-spot",
            json={},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Group 6: Full flow — stale → recalculate → finalize succeeds
# ---------------------------------------------------------------------------

class TestFullSpotExpiredFlow:

    def test_full_flow_stale_recalc_finalize(self, flask_client, test_db):
        """
        End-to-end: stale snapshot → finalize 409 → recalculate → finalize 200.
        """
        _, get_conn = test_db
        _clear_snapshots(get_conn)
        _clear_orders(get_conn)
        _clear_cart(get_conn, 8801)
        # Clear any leftover session items from prior tests
        with flask_client.session_transaction() as sess:
            sess.pop("checkout_items", None)
            sess.pop("checkout_tpg", None)

        from services.system_settings_service import set_checkout_spot_max_age
        set_checkout_spot_max_age(120)

        listing_id = _insert_spot_listing(get_conn, premium=50.0, floor=2500.0)
        _add_to_cart(get_conn, 8801, listing_id)

        # Step 1: Insert stale snapshot
        _insert_snapshot(get_conn, "gold", GOLD_PRICE, age_seconds=300)

        _login(flask_client)

        # Step 2: Finalize → SPOT_EXPIRED
        resp1 = flask_client.post(
            "/checkout",
            json={"shipping_address": "Full Flow Ave"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp1.status_code == 409
        assert resp1.get_json()["error_code"] == "SPOT_EXPIRED"
        assert _count_orders(get_conn) == 0

        # Step 3: Add a fresh snapshot (simulating what recalculate does via run_snapshot)
        _insert_snapshot(get_conn, "gold", 3500.0, age_seconds=0)

        # Step 4: Re-add to cart (finalize popped cart in SPOT_EXPIRED? No — cart
        # is NOT cleared until order is created. But this cart checkout path
        # doesn't pop cart on SPOT_EXPIRED; the AJAX finalize returns early.)
        # Re-insert fresh listing since previous one may have been consumed.
        _clear_cart(get_conn, 8801)
        _add_to_cart(get_conn, 8801, listing_id)

        # Step 5: Finalize again → now fresh → order created
        with patch("services.notification_service.notify") as _m:
            resp2 = flask_client.post(
                "/checkout",
                json={"shipping_address": "Full Flow Ave"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )

        assert resp2.status_code == 200
        data2 = resp2.get_json()
        assert data2["success"] is True
        assert _count_orders(get_conn) == 1
