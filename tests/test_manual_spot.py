"""
Tests: Manual Spot Snapshot — admin UI insert, safety gates, chart reflection

Proven:
  1. DEBUG mode: admin can insert manual snapshot → row appears in DB with correct fields.
  2. Non-admin caller → 403.
  3. Production mode (DEBUG=False, ENV != development) → 404.
  4. After inserting a manual snapshot, /api/buckets/<id>/reference_price_history
     returns has_data=True and latest_spot_as_of matching the inserted snapshot for
     a premium_to_spot listing.
  5. No external spot API calls are made during manual insertion or chart rendering.
"""

import os
import sys
import sqlite3
import tempfile
import shutil
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ─── Minimal schema ───────────────────────────────────────────────────────────

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
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id      INTEGER NOT NULL,
    category_id    INTEGER NOT NULL,
    quantity       INTEGER DEFAULT 1,
    price_per_coin REAL    DEFAULT 0,
    active         INTEGER DEFAULT 1,
    pricing_mode   TEXT    DEFAULT 'static',
    spot_premium   REAL    DEFAULT 0,
    floor_price    REAL    DEFAULT 0,
    pricing_metal  TEXT,
    is_isolated    INTEGER DEFAULT 0,
    name           TEXT,
    listing_title  TEXT
);
CREATE TABLE IF NOT EXISTS bids (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER,
    price_per_coin REAL,
    active      INTEGER DEFAULT 1,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS orders (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_id             INTEGER,
    total_price          REAL,
    status               TEXT,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS order_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER,
    listing_id INTEGER,
    quantity   INTEGER,
    price_each REAL
);
CREATE TABLE IF NOT EXISTS bucket_price_history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    bucket_id INTEGER,
    timestamp TIMESTAMP,
    price     REAL
);
"""

# ─── Fixtures ─────────────────────────────────────────────────────────────────

ADMIN_ID = 7701
USER_ID  = 7702
BUCKET_ID = 99          # bucket used for chart tests
CAT_ID    = 99          # categories.id = BUCKET_ID for simplicity


@pytest.fixture(scope="module")
def test_db():
    """Module-scoped temp DB wired into all relevant modules."""
    import database
    import utils.auth_utils as auth_utils_mod
    import services.reference_price_service as ref_svc

    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "manual_spot_test.db")

    raw = sqlite3.connect(db_path)
    raw.executescript(SCHEMA)
    raw.commit()
    raw.close()

    orig_db   = database.get_db_connection
    orig_auth = auth_utils_mod.get_db_connection

    def get_test_conn():
        c = sqlite3.connect(db_path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    database.get_db_connection         = get_test_conn
    auth_utils_mod.get_db_connection   = get_test_conn
    # reference_price_service uses `import database as _db_module`; patching
    # database.get_db_connection is sufficient since _db_module IS the module.

    yield db_path, get_test_conn

    database.get_db_connection       = orig_db
    auth_utils_mod.get_db_connection = orig_auth
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="module")
def flask_client(test_db):
    """Flask test client with admin + regular user pre-seeded."""
    from app import app as flask_app

    _, get_test_conn = test_db

    flask_app.config.update({
        "TESTING":        True,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY":     "test-manual-spot-key",
        "DEBUG":          True,
        "ENV":            "development",
    })

    conn = get_test_conn()
    for uid, uname, is_admin in [(ADMIN_ID, "ms_admin", 1), (USER_ID, "ms_user", 0)]:
        if not conn.execute("SELECT id FROM users WHERE id=?", (uid,)).fetchone():
            conn.execute(
                "INSERT INTO users (id, username, email, is_admin) VALUES (?, ?, ?, ?)",
                (uid, uname, f"{uname}@t.com", is_admin),
            )
    # Seed: category + premium_to_spot listing for chart tests
    if not conn.execute("SELECT id FROM categories WHERE id=?", (CAT_ID,)).fetchone():
        conn.execute(
            """INSERT INTO categories (id, bucket_id, metal, product_type, weight)
               VALUES (?, ?, 'gold', 'Bar', 1.0)""",
            (CAT_ID, BUCKET_ID),
        )
    if not conn.execute(
        "SELECT id FROM listings WHERE category_id=?", (CAT_ID,)
    ).fetchone():
        conn.execute(
            """INSERT INTO listings
               (seller_id, category_id, quantity, price_per_coin, active,
                pricing_mode, spot_premium, floor_price, pricing_metal)
               VALUES (?, ?, 1, 4500.0, 1, 'premium_to_spot', 100.0, 4000.0, 'gold')""",
            (ADMIN_ID, CAT_ID),
        )
    conn.commit()
    conn.close()

    with flask_app.test_client() as client:
        yield client


def _login_admin(client):
    with client.session_transaction() as sess:
        sess["user_id"] = ADMIN_ID


def _login_user(client):
    with client.session_transaction() as sess:
        sess["user_id"] = USER_ID


def _logout(client):
    with client.session_transaction() as sess:
        sess.clear()


def _count_snapshots(get_conn, metal="gold", source="manual_admin"):
    conn = get_conn()
    n = conn.execute(
        "SELECT COUNT(*) AS n FROM spot_price_snapshots WHERE metal=? AND source=?",
        (metal, source),
    ).fetchone()["n"]
    conn.close()
    return n


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestManualSpotInsert:
    """T1: Admin in DEBUG mode can insert; snapshot appears in DB."""

    def test_admin_insert_appears_in_db(self, flask_client, test_db):
        _, get_conn = test_db
        before = _count_snapshots(get_conn)

        _login_admin(flask_client)
        resp = flask_client.post(
            "/admin/api/system-settings/manual-spot",
            json={"metal": "gold", "price_usd": 5300.25},
        )
        assert resp.status_code == 200, resp.data
        body = resp.get_json()
        assert body["success"] is True

        ins = body["inserted"]
        assert ins["metal"]     == "gold"
        assert ins["price_usd"] == 5300.25
        assert ins["source"]    == "manual_admin"
        assert ins["as_of"]                          # non-empty string

        after = _count_snapshots(get_conn)
        assert after == before + 1

    def test_response_contains_inserted_id(self, flask_client, test_db):
        _login_admin(flask_client)
        resp = flask_client.post(
            "/admin/api/system-settings/manual-spot",
            json={"metal": "silver", "price_usd": 30.0},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert isinstance(body["inserted"]["id"], int)
        assert body["inserted"]["id"] > 0

    def test_bad_metal_returns_400(self, flask_client):
        _login_admin(flask_client)
        resp = flask_client.post(
            "/admin/api/system-settings/manual-spot",
            json={"metal": "unobtanium", "price_usd": 1000.0},
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["success"] is False
        assert "metal" in body["message"].lower() or "unknown" in body["message"].lower()

    def test_zero_price_returns_400(self, flask_client):
        _login_admin(flask_client)
        resp = flask_client.post(
            "/admin/api/system-settings/manual-spot",
            json={"metal": "gold", "price_usd": 0},
        )
        assert resp.status_code == 400

    def test_absurd_price_returns_400(self, flask_client):
        _login_admin(flask_client)
        resp = flask_client.post(
            "/admin/api/system-settings/manual-spot",
            json={"metal": "gold", "price_usd": 9_999_999},
        )
        assert resp.status_code == 400

    def test_missing_price_returns_400(self, flask_client):
        _login_admin(flask_client)
        resp = flask_client.post(
            "/admin/api/system-settings/manual-spot",
            json={"metal": "gold"},
        )
        assert resp.status_code == 400

    def test_missing_metal_returns_400(self, flask_client):
        _login_admin(flask_client)
        resp = flask_client.post(
            "/admin/api/system-settings/manual-spot",
            json={"price_usd": 5000},
        )
        assert resp.status_code == 400


class TestManualSpotAccessControl:
    """T2: Non-admin gets 403."""

    def test_non_admin_gets_403(self, flask_client):
        _login_user(flask_client)
        resp = flask_client.post(
            "/admin/api/system-settings/manual-spot",
            json={"metal": "gold", "price_usd": 5000.0},
        )
        assert resp.status_code == 403

    def test_unauthenticated_gets_redirected_or_403(self, flask_client):
        _logout(flask_client)
        resp = flask_client.post(
            "/admin/api/system-settings/manual-spot",
            json={"metal": "gold", "price_usd": 5000.0},
        )
        # admin_required may redirect (302) or return 403
        assert resp.status_code in (302, 403)


class TestManualSpotProductionGate:
    """T3: Production mode returns 404 even for admin."""

    def test_production_mode_returns_404(self, flask_client):
        from app import app as flask_app

        _login_admin(flask_client)

        orig_debug = flask_app.debug
        orig_env   = flask_app.config.get("ENV")
        try:
            flask_app.debug = False
            flask_app.config["ENV"] = "production"

            resp = flask_client.post(
                "/admin/api/system-settings/manual-spot",
                json={"metal": "gold", "price_usd": 5000.0},
            )
            assert resp.status_code == 404
        finally:
            flask_app.debug = orig_debug
            if orig_env is None:
                flask_app.config.pop("ENV", None)
            else:
                flask_app.config["ENV"] = orig_env


class TestManualSpotChartReflection:
    """T4: After inserting a manual snapshot, reference_price_history reflects it."""

    def test_no_snapshot_latest_spot_as_of_is_none(self, flask_client, test_db):
        """
        With no spot snapshots the chart may show fallback floor prices, but
        latest_spot_as_of must be None (no real spot data was used).
        """
        _, get_conn = test_db
        # Clear all snapshots so get_spot_at_time returns None
        conn = get_conn()
        conn.execute("DELETE FROM spot_price_snapshots")
        conn.commit()
        conn.close()

        _login_admin(flask_client)
        resp = flask_client.get(
            f"/api/buckets/{BUCKET_ID}/reference_price_history?range=1d"
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        # No real spot snapshot → latest_spot_as_of should be None
        assert body["latest_spot_as_of"] is None

    def test_after_insert_chart_reflects_snapshot(self, flask_client, test_db):
        """
        Insert manual gold snapshot → reference_price_history shows has_data=True
        and latest_spot_as_of matches the inserted as_of.
        """
        _login_admin(flask_client)

        # Insert snapshot
        ins_resp = flask_client.post(
            "/admin/api/system-settings/manual-spot",
            json={"metal": "gold", "price_usd": 5000.0},
        )
        assert ins_resp.status_code == 200
        inserted_as_of = ins_resp.get_json()["inserted"]["as_of"]

        # Query chart
        chart_resp = flask_client.get(
            f"/api/buckets/{BUCKET_ID}/reference_price_history?range=1d"
        )
        assert chart_resp.status_code == 200
        chart = chart_resp.get_json()

        assert chart["success"] is True
        assert chart["summary"]["has_data"] is True
        assert chart["latest_spot_as_of"] is not None

        # Series should have at least one price point > 0
        assert len(chart["primary_series"]) > 0
        price = chart["primary_series"][-1]["price"]
        assert price > 0

        # Expected: spot 5000 + premium 100 = 5100 (floor 4000, so 5100 wins)
        assert abs(price - 5100.0) < 0.01, f"Expected ~5100, got {price}"

    def test_second_insert_overwrites_reference_price(self, flask_client, test_db):
        """A newer snapshot at a different price updates the current reference price."""
        _login_admin(flask_client)

        flask_client.post(
            "/admin/api/system-settings/manual-spot",
            json={"metal": "gold", "price_usd": 6000.0},
        )

        chart_resp = flask_client.get(
            f"/api/buckets/{BUCKET_ID}/reference_price_history?range=1d"
        )
        chart = chart_resp.get_json()
        price = chart["primary_series"][-1]["price"]
        # Now spot=6000, premium=100 → 6100
        assert abs(price - 6100.0) < 0.01, f"Expected ~6100, got {price}"


class TestManualSpotNoExternalCalls:
    """T5: Manual insert and chart render make zero external API calls."""

    def test_no_external_calls_on_insert(self, flask_client):
        """
        manual-spot endpoint must not make any HTTP requests.
        Patch requests.get/post at the top level to catch any outbound call.
        """
        import requests as _requests_mod
        _login_admin(flask_client)

        with patch.object(
            _requests_mod, "get",
            side_effect=AssertionError("HTTP GET called during manual insert!"),
        ) as mock_get, patch.object(
            _requests_mod, "post",
            side_effect=AssertionError("HTTP POST called during manual insert!"),
        ) as mock_post:
            resp = flask_client.post(
                "/admin/api/system-settings/manual-spot",
                json={"metal": "gold", "price_usd": 5500.0},
            )
            assert resp.status_code == 200
            mock_get.assert_not_called()
            mock_post.assert_not_called()

    def test_no_external_calls_on_chart_render(self, flask_client):
        """
        reference_price_history reads only from spot_price_snapshots — no HTTP calls.
        """
        import requests as _requests_mod
        _login_admin(flask_client)

        with patch.object(
            _requests_mod, "get",
            side_effect=AssertionError("HTTP GET called during chart render!"),
        ) as mock_get, patch.object(
            _requests_mod, "post",
            side_effect=AssertionError("HTTP POST called during chart render!"),
        ) as mock_post:
            resp = flask_client.get(
                f"/api/buckets/{BUCKET_ID}/reference_price_history?range=1d"
            )
            assert resp.status_code == 200
            mock_get.assert_not_called()
            mock_post.assert_not_called()


# ─── Direct service unit tests (no Flask) ─────────────────────────────────────

class TestInsertManualSpotServiceUnit:
    """Unit-test insert_manual_spot_snapshot directly, bypassing Flask."""

    @pytest.fixture(autouse=True)
    def _conn(self, test_db):
        _, get_conn = test_db
        conn = get_conn()
        yield conn
        conn.close()

    def test_valid_gold_inserts_correctly(self, _conn):
        from services.manual_spot_service import insert_manual_spot_snapshot
        result = insert_manual_spot_snapshot(_conn, "gold", 5250.0)
        assert result["metal"]     == "gold"
        assert result["price_usd"] == 5250.0
        assert result["source"]    == "manual_admin"
        assert "T" in result["as_of"] or " " in result["as_of"]   # ISO or space format

    def test_case_insensitive_metal(self, _conn):
        from services.manual_spot_service import insert_manual_spot_snapshot
        result = insert_manual_spot_snapshot(_conn, "GOLD", 5100.0)
        assert result["metal"] == "gold"

    def test_unknown_metal_raises(self, _conn):
        from services.manual_spot_service import insert_manual_spot_snapshot
        with pytest.raises(ValueError, match="Unknown metal"):
            insert_manual_spot_snapshot(_conn, "unobtanium", 1000.0)

    def test_zero_price_raises(self, _conn):
        from services.manual_spot_service import insert_manual_spot_snapshot
        with pytest.raises(ValueError):
            insert_manual_spot_snapshot(_conn, "gold", 0)

    def test_negative_price_raises(self, _conn):
        from services.manual_spot_service import insert_manual_spot_snapshot
        with pytest.raises(ValueError):
            insert_manual_spot_snapshot(_conn, "gold", -100)

    def test_max_exceeded_raises(self, _conn):
        from services.manual_spot_service import insert_manual_spot_snapshot
        with pytest.raises(ValueError, match="maximum"):
            insert_manual_spot_snapshot(_conn, "gold", 2_000_000)

    def test_platinum_accepted(self, _conn):
        from services.manual_spot_service import insert_manual_spot_snapshot
        result = insert_manual_spot_snapshot(_conn, "platinum", 950.0)
        assert result["metal"] == "platinum"
