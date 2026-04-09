"""
Tests: Checkout Spot Service — bounded staleness, single-flight refresh, auditability

Proven:
  1. Fresh snapshot: checkout reads from DB, makes ZERO external API calls.
  2. Stale snapshot + N=10 concurrent checkouts: run_snapshot called at most once;
     all callers receive a fresh-enough price.
  3. Order audit fields: premium_to_spot order_item rows have spot_price_at_purchase,
     spot_as_of_used, spot_source_used, pricing_mode_at_purchase, spot_premium_used,
     weight_used populated with correct values.
  4. Chart rendering regression: reference_price_history API makes 0 external calls.
  5. System settings: get/set checkout_spot_max_age and checkout_spot_refresh_timeout.
  6. Admin API GET/POST for checkout-spot settings.
"""

import os
import sys
import sqlite3
import tempfile
import shutil
import threading
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ---------------------------------------------------------------------------
# Schema — extends scheduler test schema with order tables + audit columns
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
    username      TEXT,
    email         TEXT,
    password      TEXT    DEFAULT '',
    password_hash TEXT    DEFAULT '',
    is_admin      INTEGER DEFAULT 0,
    is_banned     INTEGER DEFAULT 0,
    is_frozen     INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS categories (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    bucket_id          INTEGER,
    metal              TEXT,
    product_type       TEXT,
    weight             REAL,
    mint               TEXT,
    year               TEXT,
    product_line       TEXT,
    is_isolated        INTEGER DEFAULT 0,
    purity             TEXT,
    finish             TEXT,
    series_variant     TEXT,
    name               TEXT,
    platform_fee_type  TEXT,
    platform_fee_value REAL,
    grade              TEXT,
    condition_category TEXT
);
CREATE TABLE IF NOT EXISTS listings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id       INTEGER NOT NULL,
    category_id     INTEGER NOT NULL,
    quantity        INTEGER DEFAULT 1,
    price_per_coin  REAL    DEFAULT 0,
    active          INTEGER DEFAULT 1,
    pricing_mode    TEXT    DEFAULT 'static',
    spot_premium    REAL,
    floor_price     REAL,
    pricing_metal   TEXT,
    is_isolated     INTEGER DEFAULT 0,
    name            TEXT,
    listing_title   TEXT,
    description     TEXT,
    packaging_type  TEXT,
    packaging_notes TEXT,
    condition_notes TEXT
);
CREATE TABLE IF NOT EXISTS orders (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_id             INTEGER,
    total_price          REAL,
    buyer_card_fee       REAL DEFAULT 0.0,
    tax_amount           REAL DEFAULT 0.0,
    tax_rate             REAL DEFAULT 0.0,
    status               TEXT,
    shipping_address     TEXT,
    recipient_first_name TEXT,
    recipient_last_name  TEXT,
    placed_from_ip       TEXT,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS listing_photos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id  INTEGER NOT NULL,
    file_path   TEXT NOT NULL,
    uploader_id INTEGER,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS transaction_snapshots (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id               INTEGER NOT NULL,
    order_item_id          INTEGER,
    snapshot_at            TEXT NOT NULL,
    listing_id             INTEGER,
    listing_title          TEXT,
    listing_description    TEXT,
    metal                  TEXT,
    product_line           TEXT,
    product_type           TEXT,
    weight                 TEXT,
    year                   TEXT,
    mint                   TEXT,
    purity                 TEXT,
    finish                 TEXT,
    condition_category     TEXT,
    series_variant         TEXT,
    packaging_type         TEXT,
    packaging_notes        TEXT,
    condition_notes        TEXT,
    photo_filenames        TEXT,
    quantity               INTEGER,
    price_each             REAL,
    pricing_mode           TEXT,
    spot_price_at_purchase REAL,
    seller_id              INTEGER,
    seller_username        TEXT,
    seller_email           TEXT,
    buyer_id               INTEGER,
    buyer_username         TEXT,
    buyer_email            TEXT,
    payment_intent_id      TEXT
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
"""

METAL = "gold"
FRESH_PRICE = 3100.0
STALE_PRICE = 2900.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def test_db():
    """Module-scoped temp DB wired into database + auth_utils + checkout routes modules."""
    import database
    import utils.auth_utils as auth_utils_mod
    import services.order_service as order_service_mod
    import core.blueprints.checkout.routes as checkout_routes_mod

    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "checkout_spot_test.db")

    raw = sqlite3.connect(db_path)
    raw.executescript(SCHEMA)
    raw.commit()
    raw.close()

    orig_db = database.get_db_connection
    orig_auth = auth_utils_mod.get_db_connection
    orig_order = order_service_mod._get_conn
    orig_checkout_routes_db = checkout_routes_mod.get_db_connection

    def get_test_conn():
        c = sqlite3.connect(db_path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    database.get_db_connection = get_test_conn
    auth_utils_mod.get_db_connection = get_test_conn
    order_service_mod._get_conn = get_test_conn
    checkout_routes_mod.get_db_connection = get_test_conn

    yield db_path, get_test_conn

    database.get_db_connection = orig_db
    auth_utils_mod.get_db_connection = orig_auth
    order_service_mod._get_conn = orig_order
    checkout_routes_mod.get_db_connection = orig_checkout_routes_db
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="module")
def flask_client(test_db):
    """Flask test client (admin + regular user pre-inserted)."""
    from app import app as flask_app

    _, get_test_conn = test_db

    flask_app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-checkout-spot-key",
    })

    conn = get_test_conn()
    for uid, uname, is_admin in [(9101, "cs_admin", 1), (9102, "cs_user", 0)]:
        if not conn.execute("SELECT id FROM users WHERE id=?", (uid,)).fetchone():
            conn.execute(
                "INSERT INTO users (id, username, email, is_admin) VALUES (?, ?, ?, ?)",
                (uid, uname, f"{uname}@t.com", is_admin),
            )
    conn.commit()
    conn.close()

    with flask_app.test_client() as client:
        yield client


def _login_admin(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 9101


def _logout(client):
    with client.session_transaction() as sess:
        sess.clear()


def _insert_snapshot(get_conn, metal, price, age_seconds=0, source="metalpriceapi"):
    """Insert a snapshot row with a given age."""
    as_of = (datetime.now() - timedelta(seconds=age_seconds)).isoformat()
    conn = get_conn()
    conn.execute(
        "INSERT INTO spot_price_snapshots (metal, price_usd, as_of, source) VALUES (?, ?, ?, ?)",
        (metal, price, as_of, source),
    )
    conn.commit()
    conn.close()


def _clear_snapshots(get_conn, metal=None):
    conn = get_conn()
    if metal:
        conn.execute("DELETE FROM spot_price_snapshots WHERE metal=?", (metal,))
    else:
        conn.execute("DELETE FROM spot_price_snapshots")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Group 1: System settings for checkout spot
# ---------------------------------------------------------------------------

class TestCheckoutSpotSettings:

    def test_default_max_age(self, test_db):
        """Default max age is 120s when key is absent."""
        import services.system_settings_service as sss
        _, get_conn = test_db
        conn = get_conn()
        conn.execute("DELETE FROM system_settings WHERE key=?", (sss.CHECKOUT_SPOT_MAX_AGE_KEY,))
        conn.commit()
        conn.close()
        assert sss.get_checkout_spot_max_age() == 120

    def test_default_refresh_timeout(self, test_db):
        """Default refresh timeout is 10s when key is absent."""
        import services.system_settings_service as sss
        _, get_conn = test_db
        conn = get_conn()
        conn.execute("DELETE FROM system_settings WHERE key=?", (sss.CHECKOUT_SPOT_REFRESH_TIMEOUT_KEY,))
        conn.commit()
        conn.close()
        assert sss.get_checkout_spot_refresh_timeout() == 10

    def test_set_and_read_max_age(self, test_db):
        import services.system_settings_service as sss
        saved = sss.set_checkout_spot_max_age(200)
        assert saved == 200
        assert sss.get_checkout_spot_max_age() == 200
        sss.set_checkout_spot_max_age(120)  # reset

    def test_clamp_max_age_below_min(self, test_db):
        import services.system_settings_service as sss
        saved = sss.set_checkout_spot_max_age(0)
        assert saved == sss.CHECKOUT_SPOT_MAX_AGE_MIN
        sss.set_checkout_spot_max_age(120)  # reset to default

    def test_clamp_max_age_above_max(self, test_db):
        import services.system_settings_service as sss
        saved = sss.set_checkout_spot_max_age(9999)
        assert saved == sss.CHECKOUT_SPOT_MAX_AGE_MAX
        sss.set_checkout_spot_max_age(120)  # reset to default

    def test_set_and_read_refresh_timeout(self, test_db):
        import services.system_settings_service as sss
        saved = sss.set_checkout_spot_refresh_timeout(20)
        assert saved == 20
        assert sss.get_checkout_spot_refresh_timeout() == 20
        sss.set_checkout_spot_refresh_timeout(10)  # reset


# ---------------------------------------------------------------------------
# Group 2: get_spot_for_checkout — fresh / stale / single-flight
# ---------------------------------------------------------------------------

class TestGetSpotForCheckout:

    def test_fresh_snapshot_no_external_call(self, test_db):
        """If snapshot is fresh, no external API call is made."""
        _, get_conn = test_db
        _clear_snapshots(get_conn, METAL)
        # Insert a snapshot that is only 10 seconds old (well within default 120s max)
        _insert_snapshot(get_conn, METAL, FRESH_PRICE, age_seconds=10)

        with patch("services.spot_snapshot_service.run_snapshot") as mock_rs:
            from services.checkout_spot_service import get_spot_for_checkout
            result = get_spot_for_checkout(METAL)

        assert result["price_usd"] == FRESH_PRICE
        assert result["was_refreshed"] is False
        assert result["stale_fallback"] is False
        mock_rs.assert_not_called()

    def test_stale_snapshot_triggers_refresh(self, test_db):
        """Stale snapshot triggers a single run_snapshot call and returns new price."""
        import services.system_settings_service as sss
        import services.checkout_spot_service as css
        _, get_conn = test_db
        _clear_snapshots(get_conn, METAL)
        # Insert a snapshot that is 200 seconds old; set max_age=60 so it's stale
        _insert_snapshot(get_conn, METAL, STALE_PRICE, age_seconds=200)
        sss.set_checkout_spot_max_age(60)

        try:
            def mock_run_snapshot(**kwargs):
                # Simulate the refresh by inserting a fresh row
                _insert_snapshot(get_conn, METAL, FRESH_PRICE, age_seconds=0)
                return {"inserted": 1, "skipped": 0, "locked_out": False, "error": None}

            with patch("services.spot_snapshot_service.run_snapshot", side_effect=mock_run_snapshot) as mock_rs:
                result = css.get_spot_for_checkout(METAL)

            assert result["price_usd"] == FRESH_PRICE
            assert result["was_refreshed"] is True
            assert result["stale_fallback"] is False
            mock_rs.assert_called_once()
        finally:
            sss.set_checkout_spot_max_age(120)  # reset

    def test_no_snapshot_raises_spot_unavailable(self, test_db):
        """No snapshot + failed refresh raises SpotUnavailableError (not generic RuntimeError)."""
        from services.checkout_spot_service import SpotUnavailableError
        _, get_conn = test_db
        _clear_snapshots(get_conn, "unobtainium")

        with patch("services.spot_snapshot_service.run_snapshot", return_value={"inserted": 0, "skipped": 0, "locked_out": False, "error": "api_down"}):
            import services.checkout_spot_service as css
            with pytest.raises(SpotUnavailableError) as exc_info:
                css.get_spot_for_checkout("unobtainium")
        assert exc_info.value.metal == "unobtainium"
        assert "unobtainium" in str(exc_info.value)

    def test_stale_raises_spot_unavailable_when_refresh_fails(self, test_db):
        """
        Stale snapshot + refresh that produces no new row → SpotUnavailableError.
        Policy A: checkout must be BLOCKED; stale_fallback is no longer permitted.
        """
        from services.checkout_spot_service import SpotUnavailableError
        import services.system_settings_service as sss
        import services.checkout_spot_service as css
        _, get_conn = test_db
        _clear_snapshots(get_conn, METAL)
        # Insert a snapshot 300s old; set max_age=60 so it's stale
        _insert_snapshot(get_conn, METAL, STALE_PRICE, age_seconds=300)
        sss.set_checkout_spot_max_age(60)

        try:
            def mock_run_snapshot(**kwargs):
                # Refresh does NOT insert a new row (provider unavailable)
                return {"inserted": 0, "skipped": 1, "locked_out": False, "error": None}

            with patch("services.spot_snapshot_service.run_snapshot", side_effect=mock_run_snapshot):
                with pytest.raises(SpotUnavailableError) as exc_info:
                    css.get_spot_for_checkout(METAL)

            assert exc_info.value.metal == METAL
            assert exc_info.value.latest_as_of is not None
            assert exc_info.value.max_age_seconds == 60
        finally:
            sss.set_checkout_spot_max_age(120)  # reset


# ---------------------------------------------------------------------------
# Group 3: Single-flight concurrency — N threads, at most 1 external refresh
# ---------------------------------------------------------------------------

class TestSingleFlightConcurrency:

    def test_n_concurrent_checkouts_single_refresh(self, test_db):
        """
        Simulate 10 concurrent checkout threads hitting a stale snapshot.
        run_snapshot must be called at most once across all threads.
        All threads must receive a price_usd equal to the refreshed price.
        """
        import services.system_settings_service as sss
        _, get_conn = test_db
        _clear_snapshots(get_conn, METAL)
        # Use max_age=60 so 300s-old snapshot is stale; refresh_timeout=5 for fast test
        sss.set_checkout_spot_max_age(60)
        sss.set_checkout_spot_refresh_timeout(5)
        _insert_snapshot(get_conn, METAL, STALE_PRICE, age_seconds=300)

        call_count = 0
        call_lock = threading.Lock()

        def mock_run_snapshot(**kwargs):
            nonlocal call_count
            with call_lock:
                call_count += 1
            # Insert a fresh snapshot
            _insert_snapshot(get_conn, METAL, FRESH_PRICE, age_seconds=0)
            return {"inserted": 1, "skipped": 0, "locked_out": False, "error": None}

        # Patch _try_acquire_run_lock so exactly one thread wins
        real_lock = threading.Lock()
        first_thread = threading.local()

        def mock_acquire_lock(conn):
            """Only the first thread to call this acquires the lock."""
            return real_lock.acquire(blocking=False)

        def mock_release_lock(conn):
            try:
                real_lock.release()
            except RuntimeError:
                pass

        results = []
        errors = []
        barrier = threading.Barrier(10)

        def checkout_thread():
            barrier.wait()  # all start simultaneously
            try:
                import services.checkout_spot_service as css
                r = css.get_spot_for_checkout(METAL)
                results.append(r)
            except Exception as exc:
                errors.append(exc)

        with patch("services.spot_snapshot_service.run_snapshot", side_effect=mock_run_snapshot), \
             patch("services.spot_snapshot_service._try_acquire_run_lock", side_effect=mock_acquire_lock), \
             patch("services.spot_snapshot_service._release_run_lock", side_effect=mock_release_lock):

            threads = [threading.Thread(target=checkout_thread) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

        assert not errors, f"Thread errors: {errors}"
        assert len(results) == 10, f"Expected 10 results, got {len(results)}"
        assert call_count <= 1, f"run_snapshot called {call_count} times (expected at most 1)"
        # All threads should get the fresh price
        for r in results:
            assert r["price_usd"] == FRESH_PRICE, f"Got stale price {r['price_usd']} from a thread"

        # Reset settings to defaults
        sss.set_checkout_spot_max_age(120)
        sss.set_checkout_spot_refresh_timeout(10)

    def test_n_concurrent_checkouts_all_blocked_on_refresh_failure(self, test_db):
        """
        Policy A — concurrency: N=10 threads hit a stale snapshot; refresh fails to
        produce a fresh row.  All threads must receive SpotUnavailableError (no
        stale-price fallback), run_snapshot is called at most once.
        """
        from services.checkout_spot_service import SpotUnavailableError
        import services.system_settings_service as sss
        _, get_conn = test_db
        _clear_snapshots(get_conn, METAL)
        sss.set_checkout_spot_max_age(60)
        sss.set_checkout_spot_refresh_timeout(5)
        # Stale snapshot — 300s old, beyond max_age=60
        _insert_snapshot(get_conn, METAL, STALE_PRICE, age_seconds=300)

        call_count = 0
        call_lock = threading.Lock()

        def mock_run_snapshot(**kwargs):
            nonlocal call_count
            with call_lock:
                call_count += 1
            # Hold briefly so other threads reach _try_acquire_run_lock while
            # this thread still holds the lock (prevents GIL-sequential execution).
            import time as _time
            _time.sleep(0.15)
            # Refresh fails — no new row inserted
            return {"inserted": 0, "skipped": 1, "locked_out": False, "error": "api_down"}

        real_lock = threading.Lock()

        def mock_acquire_lock(conn):
            return real_lock.acquire(blocking=False)

        def mock_release_lock(conn):
            try:
                real_lock.release()
            except RuntimeError:
                pass

        spot_errors = []
        other_errors = []
        barrier = threading.Barrier(10)

        def checkout_thread():
            barrier.wait()
            try:
                import services.checkout_spot_service as css
                css.get_spot_for_checkout(METAL)
                other_errors.append(AssertionError("Expected SpotUnavailableError but got a result"))
            except SpotUnavailableError as e:
                spot_errors.append(e)
            except Exception as exc:
                other_errors.append(exc)

        with patch("services.spot_snapshot_service.run_snapshot", side_effect=mock_run_snapshot), \
             patch("services.spot_snapshot_service._try_acquire_run_lock", side_effect=mock_acquire_lock), \
             patch("services.spot_snapshot_service._release_run_lock", side_effect=mock_release_lock):

            threads = [threading.Thread(target=checkout_thread) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

        assert not other_errors, f"Unexpected thread errors: {other_errors}"
        assert len(spot_errors) == 10, f"Expected 10 SpotUnavailableErrors, got {len(spot_errors)}"
        assert call_count <= 1, f"run_snapshot called {call_count} times (expected at most 1)"

        sss.set_checkout_spot_max_age(120)
        sss.set_checkout_spot_refresh_timeout(10)


# ---------------------------------------------------------------------------
# Group 4: Order audit fields
# ---------------------------------------------------------------------------

class TestOrderAuditFields:

    def _setup_premium_listing(self, get_conn, seller_id=9102, premium=50.0,
                                metal="gold", weight=1.0, price=FRESH_PRICE + 50.0):
        """Insert a category + premium_to_spot listing; return listing_id."""
        conn = get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO users (id, username, email) VALUES (?, ?, ?)",
            (seller_id, "seller_audit", "seller_audit@t.com"),
        )
        cur = conn.execute(
            "INSERT INTO categories (metal, product_type, weight, mint, year, product_line, purity, finish, grade) "
            "VALUES (?, 'Coin', ?, 'US Mint', '2024', 'American Eagle', '.999', 'BU', 'MS70')",
            (metal, weight),
        )
        cat_id = cur.lastrowid
        cur2 = conn.execute(
            "INSERT INTO listings (seller_id, category_id, quantity, price_per_coin, "
            "pricing_mode, spot_premium, floor_price, pricing_metal) "
            "VALUES (?, ?, 5, ?, 'premium_to_spot', ?, ?, ?)",
            (seller_id, cat_id, price, premium, price, metal),
        )
        listing_id = cur2.lastrowid
        conn.commit()
        conn.close()
        return listing_id, cat_id

    def test_order_item_audit_fields_populated(self, test_db):
        """
        When create_order receives cart_data with spot_info + pricing meta,
        order_items rows must have all audit columns populated correctly.
        """
        _, get_conn = test_db
        _clear_snapshots(get_conn, METAL)
        as_of_str = (datetime.now() - timedelta(seconds=5)).isoformat()
        conn = get_conn()
        conn.execute(
            "INSERT INTO spot_price_snapshots (metal, price_usd, as_of, source) VALUES (?, ?, ?, ?)",
            (METAL, FRESH_PRICE, as_of_str, "metalpriceapi"),
        )
        conn.commit()
        conn.close()

        listing_id, _ = self._setup_premium_listing(get_conn)

        spot_info = {
            "price_usd": FRESH_PRICE,
            "as_of": as_of_str,
            "source": "metalpriceapi",
            "was_refreshed": False,
            "stale_fallback": False,
        }
        cart_data = [{
            "listing_id": listing_id,
            "quantity": 2,
            "price_each": FRESH_PRICE + 50.0,  # spot + premium
            "requires_grading": False,
            "spot_info": spot_info,
            "pricing_mode_used": "premium_to_spot",
            "spot_premium_used": 50.0,
            "weight_used": 1.0,
        }]

        from services.order_service import create_order
        order_id = create_order(
            buyer_id=9102,
            cart_items=cart_data,
            shipping_address="123 Test St",
        )

        conn = get_conn()
        row = conn.execute(
            "SELECT * FROM order_items WHERE order_id=?", (order_id,)
        ).fetchone()
        conn.close()

        assert row is not None
        assert row["spot_price_at_purchase"] == FRESH_PRICE
        assert row["spot_as_of_used"] == as_of_str
        assert row["spot_source_used"] == "metalpriceapi"
        assert row["pricing_mode_at_purchase"] == "premium_to_spot"
        assert row["spot_premium_used"] == 50.0
        assert row["weight_used"] == 1.0
        assert row["price_each"] == FRESH_PRICE + 50.0

    def test_static_listing_audit_fields_null(self, test_db):
        """For static-priced items, spot audit fields remain NULL."""
        _, get_conn = test_db

        conn = get_conn()
        conn.execute("INSERT OR REPLACE INTO users (id, username, email) VALUES (9103, 'stn_seller', 's@t.com')")
        cur = conn.execute(
            "INSERT INTO categories (metal, product_type, weight, mint, year, product_line, purity, finish, grade) "
            "VALUES ('gold', 'Bar', 1.0, 'PAMP', '2024', 'Suisse', '.9999', 'BU', 'Raw')"
        )
        cat_id = cur.lastrowid
        cur2 = conn.execute(
            "INSERT INTO listings (seller_id, category_id, quantity, price_per_coin, pricing_mode) "
            "VALUES (9103, ?, 3, 3200.0, 'static')",
            (cat_id,),
        )
        listing_id = cur2.lastrowid
        conn.commit()
        conn.close()

        cart_data = [{
            "listing_id": listing_id,
            "quantity": 1,
            "price_each": 3200.0,
            "requires_grading": False,
            "spot_info": None,
            "pricing_mode_used": "static",
            "spot_premium_used": None,
            "weight_used": None,
        }]

        from services.order_service import create_order
        order_id = create_order(9102, cart_data, "456 Static Rd")

        conn = get_conn()
        row = conn.execute("SELECT * FROM order_items WHERE order_id=?", (order_id,)).fetchone()
        conn.close()

        assert row["spot_price_at_purchase"] is None
        assert row["spot_as_of_used"] is None
        assert row["spot_source_used"] is None
        assert row["pricing_mode_at_purchase"] == "static"
        assert row["price_each"] == 3200.0


# ---------------------------------------------------------------------------
# Group 5: Admin API for checkout spot settings
# ---------------------------------------------------------------------------

class TestAdminCheckoutSpotAPI:

    def test_get_settings(self, flask_client):
        """Admin can read checkout spot settings."""
        _login_admin(flask_client)
        resp = flask_client.get("/admin/api/system-settings/checkout-spot")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "max_age_seconds" in data
        assert "refresh_timeout_seconds" in data
        assert data["max_age_min"] == 30
        assert data["max_age_max"] == 600

    def test_post_settings(self, flask_client):
        """Admin can update checkout spot settings."""
        _login_admin(flask_client)
        resp = flask_client.post(
            "/admin/api/system-settings/checkout-spot",
            json={"max_age_seconds": 180, "refresh_timeout_seconds": 15},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["max_age_seconds"] == 180
        assert data["refresh_timeout_seconds"] == 15

    def test_post_clamped_values(self, flask_client):
        """Values outside bounds are clamped."""
        _login_admin(flask_client)
        resp = flask_client.post(
            "/admin/api/system-settings/checkout-spot",
            json={"max_age_seconds": 99999, "refresh_timeout_seconds": 0},
            content_type="application/json",
        )
        data = resp.get_json()
        assert data["success"] is True
        assert data["max_age_seconds"] == 600   # clamped to max
        assert data["refresh_timeout_seconds"] == 3  # clamped to min

    def test_unauthenticated_get_redirects(self, flask_client):
        """Unauthenticated requests are redirected to login (302) or refused (401/403)."""
        _logout(flask_client)
        resp = flask_client.get("/admin/api/system-settings/checkout-spot")
        # admin_required decorator redirects unauthenticated users to login page
        assert resp.status_code in (302, 401, 403)


# ---------------------------------------------------------------------------
# Group 6: Route-level blocking (Policy A)
# ---------------------------------------------------------------------------

class TestCheckoutRouteBlocking:
    """
    Verify that AJAX and form-submit checkout paths return the correct Policy A
    error response (not 500) when spot pricing is unavailable.
    """

    def _setup_premium_cart(self, get_conn, user_id=9102):
        """Insert a premium_to_spot listing + cart row for the given user."""
        conn = get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO users (id, username, email) VALUES (9105, 'block_seller', 'bs@t.com')"
        )
        cur = conn.execute(
            "INSERT INTO categories (metal, product_type, weight, mint, year, "
            "product_line, purity, finish, grade) "
            "VALUES ('gold', 'Coin', 1.0, 'US Mint', '2024', 'American Eagle', '.999', 'BU', 'MS70')"
        )
        cat_id = cur.lastrowid
        cur2 = conn.execute(
            "INSERT INTO listings (seller_id, category_id, quantity, price_per_coin, "
            "pricing_mode, spot_premium, floor_price, pricing_metal) "
            "VALUES (9105, ?, 5, 3150.0, 'premium_to_spot', 50.0, 3100.0, 'gold')",
            (cat_id,),
        )
        listing_id = cur2.lastrowid
        conn.execute(
            "INSERT INTO cart (user_id, listing_id, quantity, "
            "third_party_grading_requested, grading_preference) VALUES (?, ?, 1, 0, 'NONE')",
            (user_id, listing_id),
        )
        conn.commit()
        conn.close()
        return listing_id

    def _clear_cart(self, get_conn, user_id=9102):
        conn = get_conn()
        conn.execute("DELETE FROM cart WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()

    def _order_count(self, get_conn, user_id=9102):
        conn = get_conn()
        n = conn.execute("SELECT COUNT(*) FROM orders WHERE buyer_id=?", (user_id,)).fetchone()[0]
        conn.close()
        return n

    def test_ajax_cart_checkout_blocked_on_spot_expired(self, flask_client, test_db):
        """
        AJAX cart checkout returns HTTP 409 with error_code=SPOT_EXPIRED when the
        snapshot is stale (modal-first flow: no auto-refresh on finalize).
        No order is created.
        """
        from services.checkout_spot_service import SpotExpiredError
        from services.system_settings_service import set_checkout_spot_max_age
        _, get_conn = test_db
        self._clear_cart(get_conn)
        self._setup_premium_cart(get_conn)
        set_checkout_spot_max_age(120)

        # Insert a definitively stale snapshot — no refresh will be attempted
        conn = get_conn()
        conn.execute("DELETE FROM spot_price_snapshots WHERE metal='gold'")
        stale_as_of = (datetime.now() - timedelta(seconds=300)).isoformat()
        conn.execute(
            "INSERT INTO spot_price_snapshots (metal, price_usd, as_of) VALUES ('gold', 3000.0, ?)",
            (stale_as_of,),
        )
        conn.commit()
        conn.close()

        with flask_client.session_transaction() as sess:
            sess["user_id"] = 9102
            sess.pop("checkout_items", None)
            sess["checkout_nonce"] = "test_nonce_cs"

        orders_before = self._order_count(get_conn)

        resp = flask_client.post(
            "/checkout",
            json={"shipping_address": "1 Test Lane", "checkout_nonce": "test_nonce_cs"},
            headers={"X-Requested-With": "XMLHttpRequest"},
            content_type="application/json",
        )

        assert resp.status_code == 409, f"Expected 409 SPOT_EXPIRED, got {resp.status_code}"
        data = resp.get_json()
        assert data["success"] is False
        assert data["error_code"] == "SPOT_EXPIRED"
        assert data["message"]
        # No new order must have been created
        assert self._order_count(get_conn) == orders_before, "An order was created despite SPOT_EXPIRED"

        self._clear_cart(get_conn)

    def test_form_submit_checkout_blocked_on_spot_expired(self, flask_client, test_db):
        """
        Form-submit checkout (cart fallback path) flashes an error and redirects
        when snapshot is stale (modal-first: check_spot_map_freshness raises
        SpotExpiredError, no auto-refresh).  No order is created.
        """
        from services.checkout_spot_service import SpotExpiredError
        from services.system_settings_service import set_checkout_spot_max_age
        _, get_conn = test_db
        self._clear_cart(get_conn)
        self._setup_premium_cart(get_conn)
        set_checkout_spot_max_age(120)

        conn = get_conn()
        conn.execute("DELETE FROM spot_price_snapshots WHERE metal='gold'")
        stale_as_of = (datetime.now() - timedelta(seconds=300)).isoformat()
        conn.execute(
            "INSERT INTO spot_price_snapshots (metal, price_usd, as_of) VALUES ('gold', 3000.0, ?)",
            (stale_as_of,),
        )
        conn.commit()
        conn.close()

        with flask_client.session_transaction() as sess:
            sess["user_id"] = 9102
            sess.pop("checkout_items", None)  # ensure cart-fallback path

        orders_before = self._order_count(get_conn)

        resp = flask_client.post(
            "/checkout",
            data={"shipping_address": "2 Test Ave"},
            follow_redirects=False,
        )

        # Must redirect (not 500) — SPOT_EXPIRED form path
        assert resp.status_code == 302, f"Expected redirect 302, got {resp.status_code}"
        # No new order must have been created
        assert self._order_count(get_conn) == orders_before, "An order was created despite SPOT_EXPIRED"

        self._clear_cart(get_conn)


# ---------------------------------------------------------------------------
# Group 7: Deterministic Policy A verification — stale + refresh failure
# ---------------------------------------------------------------------------

class TestPolicyAStaleRefreshFailure:
    """
    Deterministic end-to-end verification of Policy A:
      "If spot is stale AND refresh cannot succeed within the SLA,
       checkout is BLOCKED (SpotUnavailableError raised / HTTP 503 or 302
       returned) and NO orders/order_items are created."

    DB state per test:
      - spot_max_age_seconds_checkout = 30  (fast, deterministic)
      - spot_refresh_timeout_seconds  =  1  (poll loop completes in ~1s)
      - Stale gold snapshot inserted with as_of = now - 90s  (60s past max_age)
      - premium_to_spot listing (gold) in the test user's cart
        → ensures _get_cart_metals_for_spot() returns {'gold'}
        → ensures get_spot_for_checkout() is actually called

    Two internal branches covered at service level AND route level:
      B1 – lock acquired, run_snapshot inserts nothing  → SpotUnavailableError
      B2 – lock not acquired, poll times out            → SpotUnavailableError

    Regression note: removing the `raise SpotUnavailableError` in
    checkout_spot_service.py (reverting to stale_fallback=True) would cause
    tests B1/B2-service to fail because no exception is raised.
    Removing the try/except in checkout/routes.py would cause the route tests
    to return HTTP 500 instead of 503/302, failing the status-code assertions.
    """

    USER_ID = 9102        # cs_user created in flask_client fixture
    SELLER_ID = 9201      # dedicated seller for Policy A tests
    STALE_PRICE = 2800.0
    STALE_AGE_SEC = 90    # older than MAX_AGE + buffer
    MAX_AGE_SEC = 30
    TIMEOUT_SEC = 1       # keeps B2 tests fast (~1s poll)

    # ── Per-test helpers ────────────────────────────────────────────────────

    def _configure_settings(self, get_conn):
        """Write deterministic SLA settings into the test DB."""
        import services.system_settings_service as sss
        sss.set_checkout_spot_max_age(self.MAX_AGE_SEC)
        sss.set_checkout_spot_refresh_timeout(self.TIMEOUT_SEC)

    def _restore_settings(self):
        """Restore production defaults so later tests are unaffected."""
        import services.system_settings_service as sss
        sss.set_checkout_spot_max_age(120)
        sss.set_checkout_spot_refresh_timeout(10)

    def _insert_stale_snapshot(self, get_conn):
        """Replace any gold snapshots with one that is definitively stale."""
        conn = get_conn()
        as_of = (datetime.now() - timedelta(seconds=self.STALE_AGE_SEC)).isoformat()
        conn.execute("DELETE FROM spot_price_snapshots WHERE metal='gold'")
        conn.execute(
            "INSERT INTO spot_price_snapshots (metal, price_usd, as_of, source) "
            "VALUES ('gold', ?, ?, 'metalpriceapi')",
            (self.STALE_PRICE, as_of),
        )
        conn.commit()
        conn.close()
        return as_of

    def _setup_premium_cart(self, get_conn):
        """Create a premium_to_spot gold listing and add it to the test user's cart."""
        conn = get_conn()
        conn.execute("DELETE FROM cart WHERE user_id=?", (self.USER_ID,))
        conn.execute(
            "INSERT OR IGNORE INTO users (id, username, email) VALUES (?, ?, ?)",
            (self.SELLER_ID, "policyA_seller", "pa@t.com"),
        )
        cur = conn.execute(
            "INSERT INTO categories "
            "(metal, product_type, weight, mint, year, product_line, purity, finish, grade) "
            "VALUES ('gold', 'Coin', 1.0, 'US Mint', '2024', 'American Eagle', '.999', 'BU', 'MS70')"
        )
        cat_id = cur.lastrowid
        cur2 = conn.execute(
            "INSERT INTO listings "
            "(seller_id, category_id, quantity, price_per_coin, "
            "pricing_mode, spot_premium, floor_price, pricing_metal) "
            "VALUES (?, ?, 5, 2850.0, 'premium_to_spot', 50.0, 2800.0, 'gold')",
            (self.SELLER_ID, cat_id),
        )
        listing_id = cur2.lastrowid
        conn.execute(
            "INSERT INTO cart "
            "(user_id, listing_id, quantity, third_party_grading_requested, grading_preference) "
            "VALUES (?, ?, 1, 0, 'NONE')",
            (self.USER_ID, listing_id),
        )
        conn.commit()
        conn.close()
        return listing_id

    def _clear_cart(self, get_conn):
        conn = get_conn()
        conn.execute("DELETE FROM cart WHERE user_id=?", (self.USER_ID,))
        conn.commit()
        conn.close()

    def _snapshot_counts(self, get_conn):
        """Return (order_count, item_count) for the test user."""
        conn = get_conn()
        n_orders = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE buyer_id=?", (self.USER_ID,)
        ).fetchone()[0]
        n_items = conn.execute(
            "SELECT COUNT(*) FROM order_items "
            "WHERE order_id IN (SELECT id FROM orders WHERE buyer_id=?)",
            (self.USER_ID,),
        ).fetchone()[0]
        conn.close()
        return n_orders, n_items

    # ── Service-level: Branch 1 — lock acquired, run_snapshot inserts nothing ─

    def test_service_b1_lock_acquired_refresh_inserts_nothing(self, test_db):
        """
        Proves: service raises SpotUnavailableError when lock is acquired but
        run_snapshot inserts 0 rows (provider down, timeout, etc.).

        Assertions:
          - SpotUnavailableError raised with correct metal/max_age attributes
          - run_snapshot called exactly once (single-flight)
          - External spot API (fetch_spot_prices_from_api) not called
        """
        from services.checkout_spot_service import SpotUnavailableError, get_spot_for_checkout
        _, get_conn = test_db
        self._configure_settings(get_conn)
        self._insert_stale_snapshot(get_conn)

        rs_calls = []
        fetch_calls = []

        def mock_run_snapshot(**kwargs):
            rs_calls.append(1)
            return {"inserted": 0, "skipped": 1, "locked_out": False, "error": "api_down"}

        def mock_fetch_api(*args, **kwargs):
            fetch_calls.append(1)
            return {}

        with patch("services.spot_snapshot_service.run_snapshot", side_effect=mock_run_snapshot), \
             patch("services.spot_snapshot_service._try_acquire_run_lock", return_value=True), \
             patch("services.spot_snapshot_service._release_run_lock"), \
             patch("services.spot_price_service.fetch_spot_prices_from_api", side_effect=mock_fetch_api):

            with pytest.raises(SpotUnavailableError) as exc_info:
                get_spot_for_checkout("gold")

        err = exc_info.value
        assert err.metal == "gold", f"Unexpected metal: {err.metal}"
        assert err.max_age_seconds == self.MAX_AGE_SEC
        assert err.latest_as_of is not None, "latest_as_of should carry the stale snapshot timestamp"
        assert SpotUnavailableError.USER_MESSAGE in str(err) or err.reason  # has diagnostic info

        assert len(rs_calls) == 1, f"run_snapshot must be called exactly once; got {len(rs_calls)}"
        assert len(fetch_calls) == 0, "External spot API must not be called"

        self._restore_settings()

    # ── Service-level: Branch 1b — lock acquired, run_snapshot raises ─────────

    def test_service_b1_lock_acquired_refresh_raises_exception(self, test_db):
        """
        Proves: service raises SpotUnavailableError even when run_snapshot itself
        throws (e.g., network error).  The exception is swallowed internally; the
        stale snapshot persists, triggering Policy A block.

        Assertions:
          - SpotUnavailableError raised (not the original ConnectionError)
          - run_snapshot called exactly once
        """
        from services.checkout_spot_service import SpotUnavailableError, get_spot_for_checkout
        _, get_conn = test_db
        self._configure_settings(get_conn)
        self._insert_stale_snapshot(get_conn)

        rs_calls = []

        def mock_run_snapshot(**kwargs):
            rs_calls.append(1)
            raise ConnectionError("Simulated network failure")

        with patch("services.spot_snapshot_service.run_snapshot", side_effect=mock_run_snapshot), \
             patch("services.spot_snapshot_service._try_acquire_run_lock", return_value=True), \
             patch("services.spot_snapshot_service._release_run_lock"):

            with pytest.raises(SpotUnavailableError) as exc_info:
                get_spot_for_checkout("gold")

        assert exc_info.value.metal == "gold"
        assert len(rs_calls) == 1, f"run_snapshot must be called exactly once; got {len(rs_calls)}"

        self._restore_settings()

    # ── Service-level: Branch 2 — lock not acquired, poll timeout ─────────────

    def test_service_b2_lock_not_acquired_poll_timeout(self, test_db):
        """
        Proves: service raises SpotUnavailableError when it cannot acquire the
        run-lock AND no fresh snapshot appears within refresh_timeout_seconds (1s).

        Assertions:
          - SpotUnavailableError raised
          - run_snapshot NOT called (lock was never acquired by this thread)
          - Test completes in ~refresh_timeout (1s) — deterministically fast
        """
        from services.checkout_spot_service import SpotUnavailableError, get_spot_for_checkout
        _, get_conn = test_db
        self._configure_settings(get_conn)
        self._insert_stale_snapshot(get_conn)

        rs_calls = []

        def mock_run_snapshot(**kwargs):
            rs_calls.append(1)

        with patch("services.spot_snapshot_service.run_snapshot", side_effect=mock_run_snapshot), \
             patch("services.spot_snapshot_service._try_acquire_run_lock", return_value=False):

            with pytest.raises(SpotUnavailableError) as exc_info:
                get_spot_for_checkout("gold")

        assert exc_info.value.metal == "gold"
        assert len(rs_calls) == 0, \
            f"run_snapshot must NOT be called when lock is not acquired; got {len(rs_calls)}"

        self._restore_settings()

    # ── Route-level AJAX: Branch 1 — lock acquired, refresh inserts nothing ───

    def test_route_ajax_b1_stale_returns_spot_expired(self, flask_client, test_db):
        """
        Proves (route level, AJAX): when snapshot is stale the finalize path
        returns HTTP 409 with error_code=SPOT_EXPIRED (modal-first: no
        auto-refresh on finalize; run_snapshot is NOT called).
        No order or order_item rows are created.

        Assertions:
          - HTTP 409
          - JSON body: success=False, error_code="SPOT_EXPIRED", message non-empty
          - orders count unchanged, order_items count unchanged
          - run_snapshot NOT called (check_spot_map_freshness doesn't refresh)
          - fetch_spot_prices_from_api not called
        """
        _, get_conn = test_db
        self._configure_settings(get_conn)
        self._insert_stale_snapshot(get_conn)
        self._clear_cart(get_conn)
        self._setup_premium_cart(get_conn)

        with flask_client.session_transaction() as sess:
            sess["user_id"] = self.USER_ID
            sess.pop("checkout_items", None)
            sess["checkout_nonce"] = "test_nonce_b1"

        orders_before, items_before = self._snapshot_counts(get_conn)
        rs_calls = []
        fetch_calls = []

        def mock_run_snapshot(**kwargs):
            rs_calls.append(1)
            return {"inserted": 0, "skipped": 1, "locked_out": False}

        def mock_fetch_api(*args, **kwargs):
            fetch_calls.append(1)
            return {}

        with patch("services.spot_snapshot_service.run_snapshot", side_effect=mock_run_snapshot), \
             patch("services.spot_price_service.fetch_spot_prices_from_api", side_effect=mock_fetch_api):

            resp = flask_client.post(
                "/checkout",
                json={"shipping_address": "1 Policy A Lane", "checkout_nonce": "test_nonce_b1"},
                headers={"X-Requested-With": "XMLHttpRequest"},
                content_type="application/json",
            )

        # ── Status code: SPOT_EXPIRED (modal-first) ───────────────────────────
        assert resp.status_code == 409, (
            f"Expected HTTP 409 SPOT_EXPIRED; got {resp.status_code}. Body: {resp.data!r}"
        )

        # ── Response body ────────────────────────────────────────────────────
        data = resp.get_json()
        assert data["success"] is False, "success must be False"
        assert data["error_code"] == "SPOT_EXPIRED", \
            f"Unexpected error_code: {data.get('error_code')}"
        assert data["message"], "message must be non-empty"

        # ── No persistence ───────────────────────────────────────────────────
        orders_after, items_after = self._snapshot_counts(get_conn)
        assert orders_after == orders_before, \
            f"No orders should be created; before={orders_before} after={orders_after}"
        assert items_after == items_before, \
            f"No order_items should be created; before={items_before} after={items_after}"

        # ── run_snapshot NOT called (check_spot_map_freshness has no refresh) ─
        assert len(rs_calls) == 0, \
            f"run_snapshot must NOT be called by the finalize path; got {len(rs_calls)} call(s)"

        # ── No external API ──────────────────────────────────────────────────
        assert len(fetch_calls) == 0, \
            "fetch_spot_prices_from_api was called — external API must not be hit"

        self._clear_cart(get_conn)
        self._restore_settings()

    # ── Route-level AJAX: Branch 2 — lock not acquired, poll timeout ──────────

    def test_route_ajax_b2_stale_no_refresh_attempted(self, flask_client, test_db):
        """
        Proves (route level, AJAX): modal-first design — finalize path uses
        check_spot_map_freshness which never calls run_snapshot or acquires any
        lock.  Returns 409 SPOT_EXPIRED immediately.

        Assertions:
          - HTTP 409
          - JSON body: success=False, error_code="SPOT_EXPIRED"
          - orders count unchanged, order_items count unchanged
          - run_snapshot call count == 0
        """
        _, get_conn = test_db
        self._configure_settings(get_conn)
        self._insert_stale_snapshot(get_conn)
        self._clear_cart(get_conn)
        self._setup_premium_cart(get_conn)

        with flask_client.session_transaction() as sess:
            sess["user_id"] = self.USER_ID
            sess.pop("checkout_items", None)
            sess["checkout_nonce"] = "test_nonce_b2"

        orders_before, items_before = self._snapshot_counts(get_conn)
        rs_calls = []

        def mock_run_snapshot(**kwargs):
            rs_calls.append(1)

        with patch("services.spot_snapshot_service.run_snapshot", side_effect=mock_run_snapshot):

            resp = flask_client.post(
                "/checkout",
                json={"shipping_address": "2 Policy A Lane", "checkout_nonce": "test_nonce_b2"},
                headers={"X-Requested-With": "XMLHttpRequest"},
                content_type="application/json",
            )

        assert resp.status_code == 409, \
            f"Expected HTTP 409 SPOT_EXPIRED; got {resp.status_code}. Body: {resp.data!r}"

        data = resp.get_json()
        assert data["success"] is False
        assert data["error_code"] == "SPOT_EXPIRED"
        assert data["message"], "message must be non-empty"

        orders_after, items_after = self._snapshot_counts(get_conn)
        assert orders_after == orders_before, "No orders on SPOT_EXPIRED (B2)"
        assert items_after == items_before, "No order_items on SPOT_EXPIRED (B2)"

        assert len(rs_calls) == 0, (
            f"run_snapshot must NOT be called by finalize path; "
            f"got {len(rs_calls)} call(s)"
        )

        self._clear_cart(get_conn)
        self._restore_settings()

    # ── Route-level Form: Branch 1 — flash + redirect, no 500, no order ───────

    def test_route_form_b1_stale_redirects_with_spot_expired_flash(self, flask_client, test_db):
        """
        Proves (route level, form-submit): when snapshot is stale the form-submit
        path returns HTTP 302 (not 500) and flashes SpotExpiredError.USER_MESSAGE.
        No order is created.  run_snapshot is NOT called (modal-first design).

        Assertions:
          - HTTP 302 redirect
          - Flash message contains SpotExpiredError.USER_MESSAGE
          - orders count unchanged, order_items count unchanged
          - run_snapshot NOT called
          - fetch_spot_prices_from_api NOT called
        """
        from services.checkout_spot_service import SpotExpiredError
        _, get_conn = test_db
        self._configure_settings(get_conn)
        self._insert_stale_snapshot(get_conn)
        self._clear_cart(get_conn)
        self._setup_premium_cart(get_conn)

        with flask_client.session_transaction() as sess:
            sess["user_id"] = self.USER_ID
            sess.pop("checkout_items", None)  # ensure cart-fallback path

        orders_before, items_before = self._snapshot_counts(get_conn)
        rs_calls = []
        fetch_calls = []

        def mock_run_snapshot(**kwargs):
            rs_calls.append(1)
            return {"inserted": 0}

        def mock_fetch_api(*args, **kwargs):
            fetch_calls.append(1)
            return {}

        with patch("services.spot_snapshot_service.run_snapshot", side_effect=mock_run_snapshot), \
             patch("services.spot_price_service.fetch_spot_prices_from_api", side_effect=mock_fetch_api):

            resp = flask_client.post(
                "/checkout",
                data={
                    "shipping_address": "3 Policy A Ave",
                    "recipient_first_name": "Test",
                    "recipient_last_name": "User",
                },
                follow_redirects=False,
            )

        # ── Must redirect, not 500 ───────────────────────────────────────────
        assert resp.status_code == 302, (
            f"Expected HTTP 302 redirect; got {resp.status_code}. Body: {resp.data!r}"
        )

        # ── Flash message contains SpotExpiredError.USER_MESSAGE ─────────────
        expected_lower = SpotExpiredError.USER_MESSAGE.lower()
        with flask_client.session_transaction() as sess:
            flashed = [msg for (_cat, msg) in sess.get("_flashes", [])]
        assert any(expected_lower in msg.lower() for msg in flashed), (
            f"Expected flash containing {SpotExpiredError.USER_MESSAGE!r} "
            f"but got: {flashed}"
        )

        # ── No persistence ───────────────────────────────────────────────────
        orders_after, items_after = self._snapshot_counts(get_conn)
        assert orders_after == orders_before, \
            f"No orders should be created; before={orders_before} after={orders_after}"
        assert items_after == items_before, \
            f"No order_items should be created; before={items_before} after={items_after}"

        # ── run_snapshot NOT called (check_spot_map_freshness doesn't refresh) ─
        assert len(rs_calls) == 0, \
            f"run_snapshot must NOT be called by the form finalize path; got {len(rs_calls)}"

        # ── No external API ──────────────────────────────────────────────────
        assert len(fetch_calls) == 0, "fetch_spot_prices_from_api was called"

        self._clear_cart(get_conn)
        self._restore_settings()


# ---------------------------------------------------------------------------
# Group 8: Chart rendering — zero external calls (regression guard)
# ---------------------------------------------------------------------------
class TestChartNoExternalCalls:

    def test_reference_price_history_no_external_call(self, flask_client, test_db):
        """
        The reference_price_history endpoint must never call the external spot
        API or checkout_spot_service.  It reads only from spot_price_snapshots.
        """
        _, get_conn = test_db
        # Ensure at least one snapshot row exists
        _clear_snapshots(get_conn, METAL)
        _insert_snapshot(get_conn, METAL, FRESH_PRICE, age_seconds=30)

        with patch("services.spot_price_service.fetch_spot_prices_from_api") as mock_api, \
             patch("services.checkout_spot_service.get_spot_for_checkout") as mock_cso:

            # Find a bucket with a premium_to_spot listing, or use a known endpoint
            # The chart endpoint reads spot_price_snapshots directly — no spot service call.
            resp = flask_client.get("/api/reference-price-history?metal=gold&range=1d")

        # The endpoint may 404 if no bucket/category is set up; that's OK for this test.
        # The key assertion is that no external API or checkout_spot_service was called.
        assert mock_api.call_count == 0, "fetch_spot_prices_from_api was called during chart rendering"
        assert mock_cso.call_count == 0, "get_spot_for_checkout was called during chart rendering"
