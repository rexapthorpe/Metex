"""
Tests: Spot Snapshot Scheduler & System Settings

Proven:
  1. SystemSettings: default interval is 10 when unset
  2. SystemSettings: set_spot_snapshot_interval clamps to [1, 120]
  3. SpotSnapshotService: run_snapshot inserts rows into spot_price_snapshots
  4. SpotSnapshotService: threshold guard prevents duplicate inserts within quiet window
  5. SpotSnapshotService: force insert after MAX_QUIET_MINS (stale last snapshot)
  6. SpotSnapshotService: significant price change triggers insert within quiet window
  7. No external API call during chart rendering (only reads spot_price_snapshots)
  8. AdminAPI GET: admin can read current interval + bounds
  9. AdminAPI POST: admin can update interval; response confirms saved value + server clamps
 10. AdminAPI: non-admin / unauthenticated → 401/403
 11. Integration: spot snapshot changes are reflected in reference_price_history endpoint
"""

import os
import sys
import sqlite3
import tempfile
import shutil
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ---------------------------------------------------------------------------
# Minimal schema
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
    source     TEXT      DEFAULT 'test',
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
    weight             TEXT,
    mint               TEXT,
    year               TEXT,
    product_line       TEXT,
    is_isolated        INTEGER DEFAULT 0,
    purity             TEXT,
    finish             TEXT,
    series_variant     TEXT,
    name               TEXT,
    platform_fee_type  TEXT,
    platform_fee_value REAL
);
CREATE TABLE IF NOT EXISTS listings (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id      INTEGER NOT NULL,
    category_id    INTEGER NOT NULL,
    quantity       INTEGER DEFAULT 1,
    price_per_coin REAL    DEFAULT 0,
    active         INTEGER DEFAULT 1,
    pricing_mode   TEXT    DEFAULT 'static',
    spot_premium   REAL,
    floor_price    REAL,
    pricing_metal  TEXT,
    is_isolated    INTEGER DEFAULT 0,
    name           TEXT,
    listing_title  TEXT
);
CREATE TABLE IF NOT EXISTS bids (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id          INTEGER NOT NULL,
    buyer_id             INTEGER NOT NULL,
    quantity_requested   INTEGER NOT NULL DEFAULT 1,
    price_per_coin       REAL    NOT NULL,
    remaining_quantity   INTEGER NOT NULL DEFAULT 1,
    active               INTEGER DEFAULT 1,
    status               TEXT    DEFAULT 'Open',
    pricing_mode         TEXT    DEFAULT 'static',
    spot_premium         REAL,
    ceiling_price        REAL,
    pricing_metal        TEXT,
    random_year          INTEGER DEFAULT 0,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS orders (
    id          INTEGER   PRIMARY KEY AUTOINCREMENT,
    buyer_id    INTEGER,
    seller_id   INTEGER,
    total_price REAL,
    status      TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS order_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER,
    listing_id INTEGER,
    quantity   INTEGER,
    price_each REAL
);
CREATE TABLE IF NOT EXISTS bucket_price_history (
    id         INTEGER   PRIMARY KEY AUTOINCREMENT,
    bucket_id  INTEGER,
    event_type TEXT,
    price      REAL,
    timestamp  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

FAKE_METAL = "xsstest"
BUCKET_ID  = 888881

NOW = datetime.now()

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def test_db():
    """
    Temp SQLite DB patched into the database module AND all modules that do
    `from database import get_db_connection` at import time (e.g. auth_utils).
    """
    import database
    import utils.auth_utils as auth_utils_mod

    tmpdir  = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "scheduler_test.db")

    raw = sqlite3.connect(db_path)
    raw.executescript(SCHEMA)
    raw.commit()
    raw.close()

    original_get_db        = database.get_db_connection
    original_auth_get_db   = auth_utils_mod.get_db_connection

    def get_test_conn():
        c = sqlite3.connect(db_path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    database.get_db_connection      = get_test_conn
    auth_utils_mod.get_db_connection = get_test_conn

    yield db_path, get_test_conn

    database.get_db_connection       = original_get_db
    auth_utils_mod.get_db_connection = original_auth_get_db
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="module")
def flask_client(test_db):
    """Flask test client with admin/user rows pre-inserted."""
    from app import app as flask_app

    _, get_test_conn = test_db

    flask_app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-scheduler-key",
    })

    conn = get_test_conn()
    # Insert admin user (id=9001)
    existing = conn.execute("SELECT id FROM users WHERE id = 9001").fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO users (id, username, email, is_admin) "
            "VALUES (9001, 'sched_admin', 'sched_admin@t.com', 1)"
        )
    # Insert regular user (id=9002)
    existing = conn.execute("SELECT id FROM users WHERE id = 9002").fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO users (id, username, email, is_admin) "
            "VALUES (9002, 'sched_user', 'sched_user@t.com', 0)"
        )
    conn.commit()
    conn.close()

    with flask_app.test_client() as client:
        yield client


def _login_admin(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 9001


def _login_user(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 9002


def _logout(client):
    with client.session_transaction() as sess:
        sess.clear()


# ---------------------------------------------------------------------------
# Group 1: SystemSettings read/write
# ---------------------------------------------------------------------------

class TestSystemSettings:

    def test_default_interval_when_unset(self, test_db):
        """Default is 10 when key is not in DB."""
        import services.system_settings_service as sss
        _, get_conn = test_db
        conn = get_conn()
        conn.execute("DELETE FROM system_settings WHERE key = ?", (sss.SPOT_SNAPSHOT_INTERVAL_KEY,))
        conn.commit()
        conn.close()

        assert sss.get_spot_snapshot_interval() == 10

    def test_set_and_read_back(self, test_db):
        """Can set an interval and read it back."""
        import services.system_settings_service as sss
        saved = sss.set_spot_snapshot_interval(30)
        assert saved == 30
        assert sss.get_spot_snapshot_interval() == 30

    def test_clamp_below_min(self, test_db):
        """Values below MIN are clamped to MIN=1."""
        import services.system_settings_service as sss
        saved = sss.set_spot_snapshot_interval(0)
        assert saved == sss.SPOT_SNAPSHOT_INTERVAL_MIN
        assert sss.get_spot_snapshot_interval() == sss.SPOT_SNAPSHOT_INTERVAL_MIN

    def test_clamp_above_max(self, test_db):
        """Values above MAX are clamped to MAX=120."""
        import services.system_settings_service as sss
        saved = sss.set_spot_snapshot_interval(9999)
        assert saved == sss.SPOT_SNAPSHOT_INTERVAL_MAX
        assert sss.get_spot_snapshot_interval() == sss.SPOT_SNAPSHOT_INTERVAL_MAX

    def test_non_integer_falls_back_to_default(self, test_db):
        """Non-integer string falls back to default."""
        import services.system_settings_service as sss
        saved = sss.set_spot_snapshot_interval("not-a-number")
        assert saved == sss.SPOT_SNAPSHOT_INTERVAL_DEFAULT


# ---------------------------------------------------------------------------
# Group 2: SpotSnapshotService (patched spot API)
# ---------------------------------------------------------------------------

class TestSpotSnapshotService:

    def _clear_snapshots(self, get_conn):
        conn = get_conn()
        conn.execute("DELETE FROM spot_price_snapshots WHERE metal = ?", (FAKE_METAL,))
        conn.commit()
        conn.close()

    def test_run_snapshot_inserts_rows(self, test_db):
        """run_snapshot inserts a row when no prior snapshot exists."""
        _, get_conn = test_db
        self._clear_snapshots(get_conn)

        fake_prices = {FAKE_METAL: 2050.00}
        with patch("services.spot_price_service.get_current_spot_prices", return_value=fake_prices):
            from services.spot_snapshot_service import run_snapshot
            result = run_snapshot(use_lock=False, verbose=False)

        assert result["inserted"] == 1
        assert result["skipped"] == 0
        assert result["error"] is None

        conn = get_conn()
        row = conn.execute(
            "SELECT price_usd FROM spot_price_snapshots WHERE metal = ? ORDER BY as_of DESC LIMIT 1",
            (FAKE_METAL,)
        ).fetchone()
        conn.close()
        assert row is not None
        assert abs(row["price_usd"] - 2050.00) < 0.001

    def test_threshold_prevents_duplicate_recent_price(self, test_db):
        """
        Cron mode (force=False): same price within quiet window → second call is skipped.
        This tests the deduplication behaviour used by scripts/update_spot_prices.py.
        """
        _, get_conn = test_db
        self._clear_snapshots(get_conn)

        fake_prices = {FAKE_METAL: 2050.00}
        with patch("services.spot_price_service.get_current_spot_prices", return_value=fake_prices):
            from services.spot_snapshot_service import run_snapshot
            r1 = run_snapshot(use_lock=False, verbose=False, force=False)
            r2 = run_snapshot(use_lock=False, verbose=False, force=False)

        assert r1["inserted"] == 1
        assert r2["inserted"] == 0
        assert r2["skipped"] == 1

    def test_force_insert_after_quiet_period(self, test_db):
        """Last snapshot > MAX_QUIET_MINS old → always insert even if price unchanged."""
        _, get_conn = test_db
        self._clear_snapshots(get_conn)

        stale_time = (NOW - timedelta(minutes=25)).isoformat()
        conn = get_conn()
        conn.execute(
            "INSERT INTO spot_price_snapshots (metal, price_usd, as_of, source) VALUES (?, ?, ?, 'test')",
            (FAKE_METAL, 2050.00, stale_time)
        )
        conn.commit()
        conn.close()

        fake_prices = {FAKE_METAL: 2050.00}
        with patch("services.spot_price_service.get_current_spot_prices", return_value=fake_prices):
            from services.spot_snapshot_service import run_snapshot
            result = run_snapshot(use_lock=False, verbose=False)

        assert result["inserted"] == 1

    def test_significant_price_change_triggers_insert(self, test_db):
        """Price change > 0.05% within quiet window → new snapshot inserted."""
        _, get_conn = test_db
        self._clear_snapshots(get_conn)

        recent_time = (NOW - timedelta(minutes=5)).isoformat()
        conn = get_conn()
        conn.execute(
            "INSERT INTO spot_price_snapshots (metal, price_usd, as_of, source) VALUES (?, ?, ?, 'test')",
            (FAKE_METAL, 2000.00, recent_time)
        )
        conn.commit()
        conn.close()

        # 2.5% change → must insert
        fake_prices = {FAKE_METAL: 2050.00}
        with patch("services.spot_price_service.get_current_spot_prices", return_value=fake_prices):
            from services.spot_snapshot_service import run_snapshot
            result = run_snapshot(use_lock=False, verbose=False)

        assert result["inserted"] == 1

    def test_no_external_api_call_during_chart_rendering(self, test_db):
        """
        Chart rendering (reference_price_service) must NOT call get_current_spot_prices.
        Only reads from spot_price_snapshots.
        """
        _, get_conn = test_db
        CHART_BUCKET = 888883
        CHART_METAL  = "xsschart"

        conn = get_conn()
        conn.execute("DELETE FROM spot_price_snapshots WHERE metal = ?", (CHART_METAL,))
        conn.execute("DELETE FROM categories WHERE bucket_id = ?", (CHART_BUCKET,))

        # Check if user 9003 exists
        existing = conn.execute("SELECT id FROM users WHERE id = 9003").fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO users (id, username, email) VALUES (9003, 'chart_seller', 'chart@t.com')"
            )

        conn.execute(
            "INSERT INTO categories (bucket_id, metal, product_type, weight, is_isolated) "
            "VALUES (?, ?, 'Coin', '1 oz', 0)",
            (CHART_BUCKET, CHART_METAL)
        )
        cat_row = conn.execute(
            "SELECT id FROM categories WHERE bucket_id = ?", (CHART_BUCKET,)
        ).fetchone()
        conn.execute(
            "INSERT INTO listings (seller_id, category_id, quantity, active, "
            "pricing_mode, spot_premium, floor_price, pricing_metal) "
            "VALUES (9003, ?, 5, 1, 'premium_to_spot', 50.0, 100.0, ?)",
            (cat_row["id"], CHART_METAL)
        )
        conn.execute(
            "INSERT INTO spot_price_snapshots (metal, price_usd, as_of, source) VALUES (?, 2000.0, ?, 'test')",
            (CHART_METAL, (NOW - timedelta(hours=2)).isoformat())
        )
        conn.execute(
            "INSERT INTO spot_price_snapshots (metal, price_usd, as_of, source) VALUES (?, 2100.0, ?, 'test')",
            (CHART_METAL, (NOW - timedelta(hours=1)).isoformat())
        )
        conn.commit()
        conn.close()

        with patch("services.spot_price_service.get_current_spot_prices") as mock_api:
            from services.reference_price_service import get_reference_price_history
            result = get_reference_price_history(CHART_BUCKET, days=1)

        mock_api.assert_not_called()
        assert result is not None


# ---------------------------------------------------------------------------
# Group 3: Scheduler force=True mode
# ---------------------------------------------------------------------------

class TestSchedulerForceMode:
    """
    Tests proving that run_snapshot(force=True) — the scheduler mode — always
    inserts a row on every call so that latest_spot_as_of advances at the
    admin-configured cadence even when spot prices are unchanged.
    """

    TICK_METAL  = "xsstick"
    TICK_BUCKET = 888884

    def _clear_tick_snapshots(self, get_conn):
        conn = get_conn()
        conn.execute("DELETE FROM spot_price_snapshots WHERE metal = ?", (self.TICK_METAL,))
        conn.commit()
        conn.close()

    def test_force_always_inserts_same_price(self, test_db):
        """
        force=True inserts a row on every call regardless of price change or quiet
        window.  Three consecutive calls at the same price must each produce one row.
        """
        _, get_conn = test_db
        self._clear_tick_snapshots(get_conn)

        fake_prices = {self.TICK_METAL: 3000.00}
        from services.spot_snapshot_service import run_snapshot

        with patch("services.spot_price_service.get_current_spot_prices", return_value=fake_prices):
            r1 = run_snapshot(use_lock=False, verbose=False, force=True)
            r2 = run_snapshot(use_lock=False, verbose=False, force=True)
            r3 = run_snapshot(use_lock=False, verbose=False, force=True)

        assert r1["inserted"] == 1, f"r1: {r1}"
        assert r2["inserted"] == 1, f"r2: {r2}"
        assert r3["inserted"] == 1, f"r3: {r3}"

        conn = get_conn()
        rows = conn.execute(
            "SELECT as_of FROM spot_price_snapshots WHERE metal = ? ORDER BY as_of ASC",
            (self.TICK_METAL,)
        ).fetchall()
        conn.close()

        assert len(rows) == 3, f"Expected 3 rows, got {len(rows)}"

        as_ofs = [row["as_of"] for row in rows]
        assert as_ofs == sorted(as_ofs), f"Timestamps not in order: {as_ofs}"

    def test_cron_mode_still_deduplicates(self, test_db):
        """
        Regression: force=False (cron mode) still deduplicates within the quiet window.
        The scheduler fix must not break cron behaviour.
        """
        _, get_conn = test_db
        self._clear_tick_snapshots(get_conn)

        fake_prices = {self.TICK_METAL: 3000.00}
        from services.spot_snapshot_service import run_snapshot

        with patch("services.spot_price_service.get_current_spot_prices", return_value=fake_prices):
            r1 = run_snapshot(use_lock=False, verbose=False, force=False)
            r2 = run_snapshot(use_lock=False, verbose=False, force=False)

        assert r1["inserted"] == 1
        assert r2["inserted"] == 0
        assert r2["skipped"] == 1

    def test_multiple_ticks_advance_latest_spot_as_of_in_chart(
        self, flask_client, test_db
    ):
        """
        Integration: three simulated scheduler ticks (run_snapshot force=True) for a
        premium_to_spot bucket.

        Asserts:
          - spot_price_snapshots gains >= 3 rows with increasing as_of timestamps
          - /api/buckets/<id>/reference_price_history?range=1d:
              * latest_spot_as_of == newest snapshot as_of (within 1 second)
              * primary_series contains >= 3 points
          - External spot API is NOT called during chart rendering
        """
        from datetime import datetime as _dt

        _, get_conn = test_db
        self._clear_tick_snapshots(get_conn)

        # Bucket + premium_to_spot listing
        conn = get_conn()
        conn.execute(
            "DELETE FROM listings WHERE category_id IN "
            "(SELECT id FROM categories WHERE bucket_id = ?)", (self.TICK_BUCKET,)
        )
        conn.execute("DELETE FROM categories WHERE bucket_id = ?", (self.TICK_BUCKET,))

        existing = conn.execute("SELECT id FROM users WHERE id = 9005").fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO users (id, username, email) VALUES (9005, 'tick_seller', 'tick@t.com')"
            )

        conn.execute(
            "INSERT INTO categories (bucket_id, metal, product_type, weight, is_isolated) "
            "VALUES (?, ?, 'Coin', '1 oz', 0)",
            (self.TICK_BUCKET, self.TICK_METAL)
        )
        cat_row = conn.execute(
            "SELECT id FROM categories WHERE bucket_id = ?", (self.TICK_BUCKET,)
        ).fetchone()
        conn.execute(
            "INSERT INTO listings (seller_id, category_id, quantity, active, "
            "pricing_mode, spot_premium, floor_price, pricing_metal) "
            "VALUES (9005, ?, 5, 1, 'premium_to_spot', 75.0, 200.0, ?)",
            (cat_row["id"], self.TICK_METAL)
        )
        conn.commit()
        conn.close()

        # Simulate 3 scheduler ticks — same price, force=True each time
        fake_prices = {self.TICK_METAL: 5000.00}
        from services.spot_snapshot_service import run_snapshot

        with patch("services.spot_price_service.get_current_spot_prices", return_value=fake_prices):
            for i in range(3):
                r = run_snapshot(use_lock=False, verbose=False, force=True)
                assert r["inserted"] == 1, f"Tick {i+1} failed to insert: {r}"

        # Verify DB has >= 3 rows with monotonically increasing timestamps
        conn = get_conn()
        snap_rows = conn.execute(
            "SELECT as_of FROM spot_price_snapshots WHERE metal = ? ORDER BY as_of ASC",
            (self.TICK_METAL,)
        ).fetchall()
        newest_as_of = conn.execute(
            "SELECT MAX(as_of) AS latest FROM spot_price_snapshots WHERE metal = ?",
            (self.TICK_METAL,)
        ).fetchone()["latest"]
        conn.close()

        assert len(snap_rows) >= 3, f"Expected >= 3 snapshot rows, got {len(snap_rows)}"
        as_ofs = [r["as_of"] for r in snap_rows]
        assert as_ofs == sorted(as_ofs), f"Timestamps not sorted: {as_ofs}"

        # Hit chart endpoint — external API must NOT be called
        _login_admin(flask_client)
        with patch("services.spot_price_service.get_current_spot_prices") as mock_api:
            resp = flask_client.get(
                f"/api/buckets/{self.TICK_BUCKET}/reference_price_history?range=1d"
            )
        mock_api.assert_not_called()
        assert resp.status_code == 200

        data = resp.get_json()
        assert data["success"] is True

        # latest_spot_as_of must match the newest snapshot (within 1 second)
        reported = data["latest_spot_as_of"]
        assert reported is not None, "latest_spot_as_of must not be None"

        def _parse(ts):
            ts = str(ts).replace("T", " ")
            for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
                try:
                    return _dt.strptime(ts, fmt)
                except ValueError:
                    continue
            raise ValueError(f"Cannot parse: {ts!r}")

        delta_secs = abs((_parse(reported) - _parse(str(newest_as_of))).total_seconds())
        assert delta_secs < 1.0, (
            f"latest_spot_as_of mismatch: chart={reported!r}  db={newest_as_of!r} "
            f"({delta_secs:.3f}s apart)"
        )

        # primary_series must have >= 3 points (one per distinct snapshot timestamp)
        series = data["primary_series"]
        assert len(series) >= 3, (
            f"Expected >= 3 series points (one per tick), got {len(series)}: {series}"
        )


# ---------------------------------------------------------------------------
# Group 4: Stale-primary / secondary source fallback
# ---------------------------------------------------------------------------

class TestSecondarySpotSource:
    """
    Tests for stale-primary detection and metals.live secondary source fallback.

    Root cause of flat chart: metalpriceapi.com free tier returns end-of-day
    data (provider timestamp age = 18+ hours). Every scheduler tick fetches
    the same price → all snapshot rows have identical price_usd.

    Fix: when metalpriceapi has returned the same price for >= PRIMARY_STALE_MINS
    minutes, run_snapshot() tries api.metals.live (free, no key) instead.
    The `source` column records which source provided each row.
    """

    def _insert_stale_primary_rows(self, get_conn, metal, price=3000.0, count=None):
        """
        Pre-populate spot_price_snapshots with metalpriceapi rows spanning
        PRIMARY_STALE_MINS+1 minutes, all at the same price.
        """
        from services.spot_snapshot_service import PRIMARY_STALE_MINS
        n = count if count is not None else PRIMARY_STALE_MINS + 1
        conn = get_conn()
        conn.execute("DELETE FROM spot_price_snapshots WHERE metal=?", (metal,))
        now = datetime.now()
        for i in range(n):
            t = (now - timedelta(minutes=n - i)).isoformat()
            conn.execute(
                "INSERT INTO spot_price_snapshots (metal, price_usd, as_of, source) "
                "VALUES (?, ?, ?, 'metalpriceapi')",
                (metal, price, t)
            )
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------ #

    def test_stale_primary_triggers_secondary_call(self, test_db):
        """
        When primary has returned the same price for >= PRIMARY_STALE_MINS min,
        run_snapshot calls _fetch_secondary_prices() exactly once.
        The snapshot row uses the secondary price and source='metals_live'.
        """
        _, get_conn = test_db
        metal = "xsssec1"
        self._insert_stale_primary_rows(get_conn, metal, price=3000.0)

        primary = {metal: 3000.0}      # same stale price
        secondary = {metal: 3050.0}    # secondary sees price has moved

        from services.spot_snapshot_service import run_snapshot
        with patch("services.spot_price_service.get_current_spot_prices", return_value=primary):
            with patch("services.spot_snapshot_service._fetch_secondary_prices",
                       return_value=secondary) as mock_sec:
                result = run_snapshot(use_lock=False, verbose=False, force=False)

        mock_sec.assert_called_once()
        assert result["inserted"] == 1, f"Expected 1 insert, got: {result}"

        conn = get_conn()
        row = conn.execute(
            "SELECT price_usd, source FROM spot_price_snapshots "
            "WHERE metal=? ORDER BY as_of DESC LIMIT 1", (metal,)
        ).fetchone()
        conn.close()
        assert abs(row["price_usd"] - 3050.0) < 0.01, f"Expected 3050, got {row['price_usd']}"
        assert row["source"] == "metals_live"

    def test_fresh_primary_does_not_call_secondary(self, test_db):
        """
        When primary is fresh (no prior rows → not enough history to be stale),
        secondary is NOT called even in force=True mode.
        """
        _, get_conn = test_db
        metal = "xsssec2"
        conn = get_conn()
        conn.execute("DELETE FROM spot_price_snapshots WHERE metal=?", (metal,))
        conn.commit()
        conn.close()

        primary = {metal: 3000.0}

        from services.spot_snapshot_service import run_snapshot
        with patch("services.spot_price_service.get_current_spot_prices", return_value=primary):
            with patch("services.spot_snapshot_service._fetch_secondary_prices") as mock_sec:
                run_snapshot(use_lock=False, verbose=False, force=True)

        mock_sec.assert_not_called()

    def test_secondary_unavailable_falls_back_to_primary(self, test_db):
        """
        When primary is stale but secondary returns None (network failure),
        run_snapshot still inserts using the primary price with source='metalpriceapi'.
        """
        _, get_conn = test_db
        metal = "xsssec3"
        self._insert_stale_primary_rows(get_conn, metal, price=3000.0)

        primary = {metal: 3000.0}

        from services.spot_snapshot_service import run_snapshot
        with patch("services.spot_price_service.get_current_spot_prices", return_value=primary):
            with patch("services.spot_snapshot_service._fetch_secondary_prices",
                       return_value=None) as mock_sec:
                result = run_snapshot(use_lock=False, verbose=False, force=True)

        mock_sec.assert_called_once()  # secondary WAS attempted
        assert result["inserted"] == 1

        conn = get_conn()
        row = conn.execute(
            "SELECT source FROM spot_price_snapshots "
            "WHERE metal=? ORDER BY as_of DESC LIMIT 1", (metal,)
        ).fetchone()
        conn.close()
        assert row["source"] == "metalpriceapi"

    def test_stale_detection_resets_when_primary_changes(self, test_db):
        """
        If the primary provider finally returns a NEW price, _primary_is_stale
        returns False → primary is used directly, secondary is NOT called.
        This verifies that when the free-tier provider does update, we resume
        using it immediately.
        """
        _, get_conn = test_db
        metal = "xsssec4"
        self._insert_stale_primary_rows(get_conn, metal, price=3000.0)

        # Provider updated! Returns a different price.
        primary = {metal: 3100.0}

        from services.spot_snapshot_service import run_snapshot
        with patch("services.spot_price_service.get_current_spot_prices", return_value=primary):
            with patch("services.spot_snapshot_service._fetch_secondary_prices") as mock_sec:
                result = run_snapshot(use_lock=False, verbose=False, force=True)

        mock_sec.assert_not_called()  # secondary NOT called (primary is fresh again)
        assert result["inserted"] == 1

        conn = get_conn()
        row = conn.execute(
            "SELECT price_usd, source FROM spot_price_snapshots "
            "WHERE metal=? ORDER BY as_of DESC LIMIT 1", (metal,)
        ).fetchone()
        conn.close()
        assert abs(row["price_usd"] - 3100.0) < 0.01
        assert row["source"] == "metalpriceapi"

    def test_chart_rendering_never_calls_external_apis(self, test_db):
        """
        Chart rendering (reference_price_service.get_reference_price_history) must
        call neither get_current_spot_prices NOR _fetch_secondary_prices.
        Only spot_price_snapshots is read.
        """
        _, get_conn = test_db
        CHART_BUCKET2 = 888885
        CHART_METAL2  = "xsschart2"

        conn = get_conn()
        conn.execute("DELETE FROM spot_price_snapshots WHERE metal=?", (CHART_METAL2,))
        conn.execute("DELETE FROM categories WHERE bucket_id=?", (CHART_BUCKET2,))

        existing = conn.execute("SELECT id FROM users WHERE id=9006").fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO users (id, username, email) VALUES (9006, 'c2_seller', 'c2@t.com')"
            )
        conn.execute(
            "INSERT INTO categories (bucket_id, metal, product_type, weight, is_isolated) "
            "VALUES (?, ?, 'Coin', '1 oz', 0)",
            (CHART_BUCKET2, CHART_METAL2)
        )
        cat_row = conn.execute(
            "SELECT id FROM categories WHERE bucket_id=?", (CHART_BUCKET2,)
        ).fetchone()
        conn.execute(
            "INSERT INTO listings (seller_id, category_id, quantity, active, "
            "pricing_mode, spot_premium, floor_price, pricing_metal) "
            "VALUES (9006, ?, 5, 1, 'premium_to_spot', 50.0, 100.0, ?)",
            (cat_row["id"], CHART_METAL2)
        )
        # Insert two snapshots (including a stale-primary-labelled one and a secondary one)
        t1 = (NOW - timedelta(hours=2)).isoformat()
        t2 = (NOW - timedelta(hours=1)).isoformat()
        conn.execute(
            "INSERT INTO spot_price_snapshots (metal, price_usd, as_of, source) "
            "VALUES (?, 2000.0, ?, 'metalpriceapi')", (CHART_METAL2, t1)
        )
        conn.execute(
            "INSERT INTO spot_price_snapshots (metal, price_usd, as_of, source) "
            "VALUES (?, 2100.0, ?, 'metals_live')", (CHART_METAL2, t2)
        )
        conn.commit()
        conn.close()

        with patch("services.spot_price_service.get_current_spot_prices") as mock_primary:
            with patch("services.spot_snapshot_service._fetch_secondary_prices") as mock_sec:
                from services.reference_price_service import get_reference_price_history
                result = get_reference_price_history(CHART_BUCKET2, days=1)

        mock_primary.assert_not_called()
        mock_sec.assert_not_called()
        assert result is not None
        series = result.get("primary_series", [])
        assert len(series) >= 2, f"Expected >= 2 series points, got: {series}"


# ---------------------------------------------------------------------------
# Group 5: Admin API endpoint
# ---------------------------------------------------------------------------

class TestAdminAPI:

    def test_get_interval_as_admin(self, flask_client):
        """Admin can GET the current interval and bounds."""
        _login_admin(flask_client)
        resp = flask_client.get("/admin/api/system-settings/spot-interval")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "interval_minutes" in data
        assert "min_minutes" in data
        assert "max_minutes" in data

    def test_post_interval_as_admin(self, flask_client):
        """Admin can POST a new interval and it persists."""
        _login_admin(flask_client)
        resp = flask_client.post(
            "/admin/api/system-settings/spot-interval",
            json={"interval_minutes": 15},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["interval_minutes"] == 15

        import services.system_settings_service as sss
        assert sss.get_spot_snapshot_interval() == 15

    def test_post_interval_clamped_above_max(self, flask_client):
        """Server clamps value > MAX to MAX."""
        _login_admin(flask_client)
        resp = flask_client.post(
            "/admin/api/system-settings/spot-interval",
            json={"interval_minutes": 9999},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        from services.system_settings_service import SPOT_SNAPSHOT_INTERVAL_MAX
        assert data["interval_minutes"] == SPOT_SNAPSHOT_INTERVAL_MAX

    def test_post_interval_clamped_below_min(self, flask_client):
        """Server clamps value < MIN to MIN."""
        _login_admin(flask_client)
        resp = flask_client.post(
            "/admin/api/system-settings/spot-interval",
            json={"interval_minutes": -5},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        from services.system_settings_service import SPOT_SNAPSHOT_INTERVAL_MIN
        assert data["interval_minutes"] == SPOT_SNAPSHOT_INTERVAL_MIN

    def test_non_admin_get_forbidden(self, flask_client):
        """Non-admin gets 401/403 on GET."""
        _login_user(flask_client)
        resp = flask_client.get("/admin/api/system-settings/spot-interval")
        assert resp.status_code in (401, 403)

    def test_non_admin_post_forbidden(self, flask_client):
        """Non-admin gets 401/403 on POST."""
        _login_user(flask_client)
        resp = flask_client.post(
            "/admin/api/system-settings/spot-interval",
            json={"interval_minutes": 5},
            content_type="application/json",
        )
        assert resp.status_code in (401, 403)

    def test_unauthenticated_forbidden(self, flask_client):
        """Unauthenticated request is redirected or rejected (302/401/403)."""
        _logout(flask_client)
        resp = flask_client.post(
            "/admin/api/system-settings/spot-interval",
            json={"interval_minutes": 5},
            content_type="application/json",
        )
        assert resp.status_code in (301, 302, 401, 403)

    def test_missing_field_returns_400(self, flask_client):
        """POST without interval_minutes returns 400."""
        _login_admin(flask_client)
        resp = flask_client.post(
            "/admin/api/system-settings/spot-interval",
            json={},
            content_type="application/json",
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Group 6: Integration — snapshot changes appear in chart endpoint
# ---------------------------------------------------------------------------

class TestChartIntegration:

    def test_spot_snapshot_changes_reflected_in_chart(self, flask_client, test_db):
        """
        Two spot snapshots at different prices for a premium_to_spot bucket.
        The reference_price_history endpoint must return a series where prices differ.
        External spot API must NOT be called.
        """
        _, get_conn = test_db
        INTEG_BUCKET = 888882
        INTEG_METAL  = "xssinteg"

        conn = get_conn()
        # Clean slate for this bucket/metal
        conn.execute("DELETE FROM spot_price_snapshots WHERE metal = ?", (INTEG_METAL,))
        conn.execute("DELETE FROM listings WHERE category_id IN "
                     "(SELECT id FROM categories WHERE bucket_id = ?)", (INTEG_BUCKET,))
        conn.execute("DELETE FROM categories WHERE bucket_id = ?", (INTEG_BUCKET,))

        existing = conn.execute("SELECT id FROM users WHERE id = 9004").fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO users (id, username, email) VALUES (9004, 'integ_seller', 'integ@t.com')"
            )

        conn.execute(
            "INSERT INTO categories (bucket_id, metal, product_type, weight, is_isolated) "
            "VALUES (?, ?, 'Coin', '1 oz', 0)",
            (INTEG_BUCKET, INTEG_METAL)
        )
        cat_row = conn.execute(
            "SELECT id FROM categories WHERE bucket_id = ?", (INTEG_BUCKET,)
        ).fetchone()

        conn.execute(
            "INSERT INTO listings (seller_id, category_id, quantity, active, "
            "pricing_mode, spot_premium, floor_price, pricing_metal) "
            "VALUES (9004, ?, 5, 1, 'premium_to_spot', 50.0, 100.0, ?)",
            (cat_row["id"], INTEG_METAL)
        )

        t1 = (NOW - timedelta(hours=3)).isoformat()
        t2 = (NOW - timedelta(hours=1)).isoformat()
        conn.execute(
            "INSERT INTO spot_price_snapshots (metal, price_usd, as_of, source) VALUES (?, 2000.0, ?, 'test')",
            (INTEG_METAL, t1)
        )
        conn.execute(
            "INSERT INTO spot_price_snapshots (metal, price_usd, as_of, source) VALUES (?, 2200.0, ?, 'test')",
            (INTEG_METAL, t2)
        )
        conn.commit()
        conn.close()

        _login_admin(flask_client)

        with patch("services.spot_price_service.get_current_spot_prices") as mock_api:
            resp = flask_client.get(
                f"/api/buckets/{INTEG_BUCKET}/reference_price_history?range=1d"
            )

        mock_api.assert_not_called()
        assert resp.status_code == 200

        data = resp.get_json()
        assert data["success"] is True

        series = data["primary_series"]
        assert len(series) >= 2, f"Expected >= 2 points, got {len(series)}: {series}"

        prices = [pt["price"] for pt in series if pt.get("price") is not None]
        assert len(prices) >= 2

        # Spot T1=2000→ask=2050; Spot T2=2200→ask=2250; delta=200
        assert min(prices) < max(prices), "Reference price must change across snapshots"
        assert max(prices) - min(prices) >= 100, (
            f"Expected ~200 USD delta, got {max(prices) - min(prices):.2f}"
        )
