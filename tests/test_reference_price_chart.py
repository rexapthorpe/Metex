"""
Smoke test: Bucket Reference Price Chart Logic

One-command run:
    python -m pytest tests/test_reference_price_chart.py -v -s

Goals proven:
    1. Variable-spot bucket: new spot snapshot changes the reference price line
    2. External spot API is NOT called during the endpoint request
    3. Endpoint returns correct primary_series data (structure + latest_spot_as_of)
    4. System behaves correctly when only ask side exists (ref = BestAsk)
    5. System behaves correctly when only bid side exists  (ref = BestBid)
    6. Midpoint logic: both sides present → ref = (ask + bid) / 2
"""

import os
import sys
import sqlite3
import shutil
import tempfile
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ---------------------------------------------------------------------------
# Minimal schema — only tables touched by reference_price_service.py
# ---------------------------------------------------------------------------
SCHEMA = """
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
    platform_fee_value REAL,
    grade              TEXT,
    coin_series        TEXT
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
    isolated_type   TEXT,
    issue_number    INTEGER,
    issue_total     INTEGER,
    graded          INTEGER DEFAULT 0,
    grading_service TEXT,
    photo_filename  TEXT
);

CREATE TABLE IF NOT EXISTS listing_photos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL,
    file_path  TEXT,
    position_index INTEGER DEFAULT 0
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
    delivery_address     TEXT    DEFAULT '',
    recipient_first_name TEXT    DEFAULT '',
    recipient_last_name  TEXT    DEFAULT '',
    pricing_mode         TEXT    DEFAULT 'static',
    spot_premium         REAL,
    ceiling_price        REAL,
    pricing_metal        TEXT,
    random_year          INTEGER DEFAULT 0,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS spot_price_snapshots (
    id         INTEGER   PRIMARY KEY AUTOINCREMENT,
    metal      TEXT      NOT NULL,
    price_usd  REAL      NOT NULL,
    as_of      TIMESTAMP NOT NULL,
    source     TEXT      DEFAULT 'test',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bucket_price_history (
    id         INTEGER   PRIMARY KEY AUTOINCREMENT,
    bucket_id  INTEGER,
    event_type TEXT,
    price      REAL,
    timestamp  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
"""

# ---------------------------------------------------------------------------
# Unique bucket IDs — high values to avoid collision with production data
# if the test DB is ever a copy of the real one (it won't be here, but safe)
# ---------------------------------------------------------------------------
BUCKET_SPOT = 999991   # variable-spot listing
BUCKET_ASK  = 999992   # ask-only  (static listing, no bids)
BUCKET_BID  = 999993   # bid-only  (no listings)
BUCKET_MID  = 999994   # midpoint  (static ask + bid)

FAKE_METAL = 'xautest'   # deliberately fake: no production snapshots for this metal

NOW    = datetime.now()
T1_ISO = (NOW - timedelta(hours=3)).isoformat()   # older, lower spot
T2_ISO = (NOW - timedelta(hours=1)).isoformat()   # newer, higher spot

SPOT_T1 = 2000.0
SPOT_T2 = 2200.0
PREMIUM = 50.0   # spot_premium for variable-spot listing
FLOOR   = 100.0  # floor_price  for variable-spot listing

ASK_ONLY  = 35.00   # static ask  for ask-only bucket
BID_ONLY  = 28.00   # static bid  for bid-only bucket
ASK_MID   = 40.00   # static ask  for midpoint bucket
BID_MID   = 30.00   # static bid  for midpoint bucket

# ---------------------------------------------------------------------------
# Floor-test bucket constants
# ---------------------------------------------------------------------------
BUCKET_FLOOR  = 999995   # premium_to_spot with floor dominating
FLOOR_METAL   = 'xautest_f'
FLOOR_AMT     = 4000.0   # floor_price
FLOOR_PREMIUM = 100.0    # spot_premium
SPOT_MANUAL   = 1000.0   # manual override — gives spot+premium=1100 < 4000 floor

# ---------------------------------------------------------------------------
# Platinum (and other non-gold metals) bucket constants
# ---------------------------------------------------------------------------
BUCKET_PLAT   = 999997   # platinum premium_to_spot
PLAT_METAL    = 'platinum'   # canonical lowercase, matches _TRACKED_METALS
PLAT_FLOOR    = 5000.0    # floor_price (spot+premium will be below this)
PLAT_PREMIUM  = 200.0
PLAT_SPOT     = 1500.0    # gives 1700 < 5000 floor → effective = 5000

# ---------------------------------------------------------------------------
# Timestamp-normalization bucket constants
# ---------------------------------------------------------------------------
BUCKET_TS     = 999996   # mixed space/T format snapshots
TS_METAL      = 'xautest_ts'
# Two snapshots: older in space-format, newer in T-format
TS_T_OLDER    = (NOW - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S')  # space format
TS_T_NEWER    = (NOW - timedelta(hours=1)).isoformat()                    # T format
TS_SPOT_OLDER = 2000.0
TS_SPOT_NEWER = 2200.0
TS_PREMIUM    = 50.0
TS_FLOOR      = 0.0       # no floor — prices vary so ordering is observable


# ---------------------------------------------------------------------------
# Module-scoped environment: one fresh DB, one test client, all data loaded once
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def test_env():
    """
    Build a temporary SQLite DB with minimal schema, patch database module,
    insert all test data, and yield the Flask app.  Restores original DB on exit.
    """
    import database
    from app import app as flask_app

    tmpdir  = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, 'ref_price_smoke.db')

    # Create fresh schema
    raw = sqlite3.connect(db_path)
    raw.executescript(SCHEMA)
    raw.commit()
    raw.close()

    original_get_db = database.get_db_connection

    def get_test_conn():
        c = sqlite3.connect(db_path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    database.get_db_connection = get_test_conn

    # bucket_view.py and buy_page.py use `from database import get_db_connection`
    # at module level, creating fixed bindings that bypass the database-module patch.
    # Patch them directly so all buy-related routes use the test DB.
    import core.blueprints.buy.bucket_view as _bucket_view_mod
    import core.blueprints.buy.buy_page as _buy_page_mod
    _orig_bucket_view_db = _bucket_view_mod.get_db_connection
    _orig_buy_page_db    = _buy_page_mod.get_db_connection
    _bucket_view_mod.get_db_connection = get_test_conn
    _buy_page_mod.get_db_connection    = get_test_conn

    flask_app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-ref-price-key',
    })

    # ── Insert all test data ────────────────────────────────────────────────
    conn = get_test_conn()
    cur  = conn.cursor()

    cur.execute("INSERT INTO users (username, email) VALUES ('ref_seller', 'rs@t.com')")
    seller_id = cur.lastrowid
    cur.execute("INSERT INTO users (username, email) VALUES ('ref_buyer',  'rb@t.com')")
    buyer_id = cur.lastrowid

    bid_time = (NOW - timedelta(hours=1)).isoformat()   # within 1d range

    # -- BUCKET_SPOT : premium_to_spot listing + two spot snapshots ----------
    cur.execute(
        "INSERT INTO categories (bucket_id, metal, product_type, weight, is_isolated) "
        "VALUES (?, ?, 'Coin', '1 oz', 0)",
        (BUCKET_SPOT, FAKE_METAL),
    )
    spot_cat = cur.lastrowid
    cur.execute(
        "INSERT INTO listings "
        "  (seller_id, category_id, price_per_coin, quantity, active, "
        "   pricing_mode, spot_premium, floor_price, pricing_metal) "
        "VALUES (?, ?, 0, 5, 1, 'premium_to_spot', ?, ?, ?)",
        (seller_id, spot_cat, PREMIUM, FLOOR, FAKE_METAL),
    )
    cur.execute(
        "INSERT INTO spot_price_snapshots (metal, price_usd, as_of) VALUES (?, ?, ?)",
        (FAKE_METAL, SPOT_T1, T1_ISO),
    )
    cur.execute(
        "INSERT INTO spot_price_snapshots (metal, price_usd, as_of) VALUES (?, ?, ?)",
        (FAKE_METAL, SPOT_T2, T2_ISO),
    )

    # -- BUCKET_ASK : static listing, no bids --------------------------------
    cur.execute(
        "INSERT INTO categories (bucket_id, metal, product_type, weight, is_isolated) "
        "VALUES (?, 'silver', 'Coin', '1 oz', 0)",
        (BUCKET_ASK,),
    )
    ask_cat = cur.lastrowid
    cur.execute(
        "INSERT INTO listings "
        "  (seller_id, category_id, price_per_coin, quantity, active, pricing_mode) "
        "VALUES (?, ?, ?, 3, 1, 'static')",
        (seller_id, ask_cat, ASK_ONLY),
    )

    # -- BUCKET_BID : bid only, no listings ----------------------------------
    cur.execute(
        "INSERT INTO categories (bucket_id, metal, product_type, weight, is_isolated) "
        "VALUES (?, 'silver', 'Coin', '1 oz', 0)",
        (BUCKET_BID,),
    )
    bid_cat = cur.lastrowid
    cur.execute(
        "INSERT INTO bids "
        "  (category_id, buyer_id, quantity_requested, price_per_coin, "
        "   remaining_quantity, active, status, created_at) "
        "VALUES (?, ?, 1, ?, 1, 1, 'Open', ?)",
        (bid_cat, buyer_id, BID_ONLY, bid_time),
    )

    # -- BUCKET_MID : static ask + bid → midpoint ----------------------------
    cur.execute(
        "INSERT INTO categories (bucket_id, metal, product_type, weight, is_isolated) "
        "VALUES (?, 'silver', 'Coin', '1 oz', 0)",
        (BUCKET_MID,),
    )
    mid_cat = cur.lastrowid
    cur.execute(
        "INSERT INTO listings "
        "  (seller_id, category_id, price_per_coin, quantity, active, pricing_mode) "
        "VALUES (?, ?, ?, 2, 1, 'static')",
        (seller_id, mid_cat, ASK_MID),
    )
    cur.execute(
        "INSERT INTO bids "
        "  (category_id, buyer_id, quantity_requested, price_per_coin, "
        "   remaining_quantity, active, status, created_at) "
        "VALUES (?, ?, 1, ?, 1, 1, 'Open', ?)",
        (mid_cat, buyer_id, BID_MID, bid_time),
    )

    # -- BUCKET_FLOOR : floor dominates (floor=4000, premium=100, spot=1000) --
    cur.execute(
        "INSERT INTO categories (bucket_id, metal, product_type, weight, is_isolated) "
        "VALUES (?, ?, 'Coin', '1 oz', 0)",
        (BUCKET_FLOOR, FLOOR_METAL),
    )
    floor_cat = cur.lastrowid
    cur.execute(
        "INSERT INTO listings "
        "  (seller_id, category_id, price_per_coin, quantity, active, "
        "   pricing_mode, spot_premium, floor_price, pricing_metal) "
        "VALUES (?, ?, 0, 5, 1, 'premium_to_spot', ?, ?, ?)",
        (seller_id, floor_cat, FLOOR_PREMIUM, FLOOR_AMT, FLOOR_METAL),
    )
    # Single snapshot at SPOT_MANUAL=1000: effective = max(1100, 4000) = 4000
    cur.execute(
        "INSERT INTO spot_price_snapshots (metal, price_usd, as_of, source) VALUES (?, ?, ?, ?)",
        (FLOOR_METAL, SPOT_MANUAL, (NOW - timedelta(minutes=5)).isoformat(), 'manual_admin'),
    )

    # -- BUCKET_PLAT : platinum premium_to_spot, floor=5000, spot=1500 ---------
    cur.execute(
        "INSERT INTO categories (bucket_id, metal, product_type, weight, is_isolated) "
        "VALUES (?, 'Platinum', 'Coin', '1 oz', 0)",
        (BUCKET_PLAT,),
    )
    plat_cat = cur.lastrowid
    cur.execute(
        "INSERT INTO listings "
        "  (seller_id, category_id, price_per_coin, quantity, active, "
        "   pricing_mode, spot_premium, floor_price, pricing_metal) "
        "VALUES (?, ?, 0, 2, 1, 'premium_to_spot', ?, ?, ?)",
        (seller_id, plat_cat, PLAT_PREMIUM, PLAT_FLOOR, PLAT_METAL),
    )
    # Insert platinum snapshot: effective = max(1500+200, 5000) = 5000 (floor wins)
    cur.execute(
        "INSERT INTO spot_price_snapshots (metal, price_usd, as_of, source) VALUES (?, ?, ?, ?)",
        (PLAT_METAL, PLAT_SPOT, (NOW - timedelta(minutes=3)).isoformat(), 'manual_admin'),
    )

    # -- BUCKET_TS : mixed space/T-format snapshots for ordering tests --------
    cur.execute(
        "INSERT INTO categories (bucket_id, metal, product_type, weight, is_isolated) "
        "VALUES (?, ?, 'Coin', '1 oz', 0)",
        (BUCKET_TS, TS_METAL),
    )
    ts_cat = cur.lastrowid
    cur.execute(
        "INSERT INTO listings "
        "  (seller_id, category_id, price_per_coin, quantity, active, "
        "   pricing_mode, spot_premium, floor_price, pricing_metal) "
        "VALUES (?, ?, 0, 3, 1, 'premium_to_spot', ?, ?, ?)",
        (seller_id, ts_cat, TS_PREMIUM, TS_FLOOR, TS_METAL),
    )
    # Older snapshot stored in legacy space format (simulates old scheduler rows)
    cur.execute(
        "INSERT INTO spot_price_snapshots (metal, price_usd, as_of) VALUES (?, ?, ?)",
        (TS_METAL, TS_SPOT_OLDER, TS_T_OLDER),   # space format
    )
    # Newer snapshot in canonical T-format
    cur.execute(
        "INSERT INTO spot_price_snapshots (metal, price_usd, as_of) VALUES (?, ?, ?)",
        (TS_METAL, TS_SPOT_NEWER, TS_T_NEWER),   # T format
    )

    conn.commit()
    conn.close()

    yield flask_app

    database.get_db_connection = original_get_db
    _bucket_view_mod.get_db_connection = _orig_bucket_view_db
    _buy_page_mod.get_db_connection    = _orig_buy_page_db
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope='module')
def tc(test_env):
    """Flask test client for the whole module."""
    return test_env.test_client()


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------

class TestReferencePriceChart:
    """Smoke-tests for /api/buckets/<id>/reference_price_history."""

    def test_1_spot_snapshot_changes_reference_price_line(self, tc):
        """
        GOAL 1 — Variable-spot bucket: inserting a higher spot snapshot
        shifts the reference price upward.

        Listing:  premium_to_spot | spot_premium=$50 | weight=1oz
        T1:  spot=$2000  → ask = $2000*1 + $50 = $2050  → ref = $2050
        T2:  spot=$2200  → ask = $2200*1 + $50 = $2250  → ref = $2250
        Expected delta: $200
        """
        rv   = tc.get(f'/api/buckets/{BUCKET_SPOT}/reference_price_history?range=1d')
        data = rv.get_json()

        assert rv.status_code == 200, f"HTTP {rv.status_code}: {rv.data}"
        assert data['success'] is True

        series  = data['primary_series']
        prices  = [pt['price'] for pt in series]
        first_p = prices[0]
        last_p  = prices[-1]
        delta   = last_p - first_p
        expected_delta = SPOT_T2 - SPOT_T1   # 200

        assert len(series) >= 2,  f"Need ≥2 series points, got {len(series)}: {series}"
        assert last_p > first_p,  f"Price should increase: {first_p:.2f} → {last_p:.2f}"
        assert abs(delta - expected_delta) < 5.0, (
            f"Expected ~${expected_delta:.0f} change, got ${delta:.2f}"
        )

        _report(
            "1 PASS — Spot snapshot change moves reference price line",
            bucket_id        = BUCKET_SPOT,
            snapshot_t1      = f"${SPOT_T1:.2f}  →  ref=${first_p:.2f}",
            snapshot_t2      = f"${SPOT_T2:.2f}  →  ref=${last_p:.2f}",
            price_delta      = f"${delta:.2f}  (expected ≈${expected_delta:.2f})",
            series_points    = len(series),
        )

    def test_2_external_spot_api_not_called(self, tc):
        """
        GOAL 2 — The reference price endpoint must NEVER call the
        external spot-price API (get_current_spot_prices).

        Patches both the service layer and its import in pricing_service to
        make the assertion watertight.
        """
        with patch('services.pricing_service.get_current_spot_prices') as mock_ps, \
             patch('services.spot_price_service.get_current_spot_prices') as mock_ss:
            rv = tc.get(
                f'/api/buckets/{BUCKET_SPOT}/reference_price_history?range=1d'
            )

        assert rv.status_code == 200, f"HTTP {rv.status_code}"
        assert mock_ps.call_count == 0, (
            f"pricing_service.get_current_spot_prices was called "
            f"{mock_ps.call_count} time(s)!"
        )
        assert mock_ss.call_count == 0, (
            f"spot_price_service.get_current_spot_prices was called "
            f"{mock_ss.call_count} time(s)!"
        )

        _report(
            "2 PASS — External spot API was NOT called",
            pricing_service_calls     = mock_ps.call_count,
            spot_price_service_calls  = mock_ss.call_count,
        )

    def test_3_primary_series_structure_and_latest_spot_as_of(self, tc):
        """
        GOAL 3 — Endpoint returns well-formed primary_series and
        latest_spot_as_of == the timestamp of the most recent snapshot (T2).
        """
        rv   = tc.get(f'/api/buckets/{BUCKET_SPOT}/reference_price_history?range=1d')
        data = rv.get_json()

        assert rv.status_code == 200
        assert data['success'] is True
        assert isinstance(data.get('primary_series'), list)
        assert data.get('latest_spot_as_of') is not None, (
            "latest_spot_as_of must be non-null for a variable-spot bucket"
        )

        # latest_spot_as_of must match T2 (the more recent snapshot)
        stored = data['latest_spot_as_of']
        assert T2_ISO[:13] in stored, (
            f"latest_spot_as_of={stored!r} does not match "
            f"T2_ISO prefix={T2_ISO[:13]!r}"
        )

        # Each point must have 't' (ISO string) and 'price' (positive float)
        for pt in data['primary_series']:
            assert 't' in pt and 'price' in pt
            assert isinstance(pt['price'], (int, float)) and pt['price'] > 0

        _report(
            "3 PASS — primary_series structure is correct",
            series_points     = len(data['primary_series']),
            latest_spot_as_of = data['latest_spot_as_of'],
            summary           = data['summary'],
        )

    def test_4_ask_only_bucket(self, tc):
        """
        GOAL 4a — Ask-only bucket (no bids, no trades).
        compute_reference_price(ask, None, None) → ref = BestAsk.
        """
        rv   = tc.get(f'/api/buckets/{BUCKET_ASK}/reference_price_history?range=1d')
        data = rv.get_json()

        assert rv.status_code == 200
        assert data['success'] is True

        series = data['primary_series']
        assert len(series) >= 1, "Expected ≥1 series point for ask-only bucket"

        last_p = series[-1]['price']
        assert abs(last_p - ASK_ONLY) < 0.01, (
            f"Ask-only: expected ref={ASK_ONLY:.2f}, got {last_p:.4f}"
        )

        _report(
            "4 PASS — Ask-only bucket: ref = BestAsk",
            bucket_id = BUCKET_ASK,
            expected  = f"${ASK_ONLY:.2f}",
            got       = f"${last_p:.4f}",
        )

    def test_5_bid_only_bucket(self, tc):
        """
        GOAL 4b — Bid-only bucket (no active listings, no trades).
        compute_reference_price(None, bid, None) → ref = BestBid.
        """
        rv   = tc.get(f'/api/buckets/{BUCKET_BID}/reference_price_history?range=1d')
        data = rv.get_json()

        assert rv.status_code == 200
        assert data['success'] is True

        series = data['primary_series']
        assert len(series) >= 1, "Expected ≥1 series point for bid-only bucket"

        last_p = series[-1]['price']
        assert abs(last_p - BID_ONLY) < 0.01, (
            f"Bid-only: expected ref={BID_ONLY:.2f}, got {last_p:.4f}"
        )

        _report(
            "5 PASS — Bid-only bucket: ref = BestBid",
            bucket_id = BUCKET_BID,
            expected  = f"${BID_ONLY:.2f}",
            got       = f"${last_p:.4f}",
        )

    def test_6_midpoint_logic_both_sides_present(self, tc):
        """
        GOAL 4c + midpoint — Both ask ($40) and bid ($30) are active.
        compute_reference_price(40, 30, None) → (40+30)/2 = $35.
        """
        expected_mid = (ASK_MID + BID_MID) / 2   # 35.00

        rv   = tc.get(f'/api/buckets/{BUCKET_MID}/reference_price_history?range=1d')
        data = rv.get_json()

        assert rv.status_code == 200
        assert data['success'] is True

        series = data['primary_series']
        assert len(series) >= 1, "Expected ≥1 series point for midpoint bucket"

        last_p = series[-1]['price']
        assert abs(last_p - expected_mid) < 0.01, (
            f"Midpoint: expected {expected_mid:.2f} "
            f"(ask={ASK_MID}, bid={BID_MID}), got {last_p:.4f}"
        )

        _report(
            "6 PASS — Midpoint logic triggered: (ask + bid) / 2",
            bucket_id     = BUCKET_MID,
            ask           = f"${ASK_MID:.2f}",
            bid           = f"${BID_MID:.2f}",
            expected_mid  = f"${expected_mid:.2f}",
            got           = f"${last_p:.4f}",
        )


class TestFloorAndTimestampNormalization:
    """
    Integration tests for Policy B: canonical pricing + chart stability.

    Bucket setup (BUCKET_FLOOR):
        pricing_mode  = premium_to_spot
        spot_premium  = 100
        floor_price   = 4000
        spot snapshot = 1000   → effective = max(1100, 4000) = 4000  (floor wins)

    Bucket setup (BUCKET_TS):
        pricing_mode  = premium_to_spot
        spot_premium  = 50 / floor = 0
        Snapshots:
            TS_T_OLDER (space-format, 2h ago) price=2000 → effective=2050
            TS_T_NEWER (T-format,    1h ago)  price=2200 → effective=2250
    """

    def test_floor_dominates_chart_primary_series(self, tc):
        """Chart's last (most recent) point must equal floor_price when floor > spot+premium."""
        rv   = tc.get(f'/api/buckets/{BUCKET_FLOOR}/reference_price_history?range=1d')
        data = rv.get_json()

        assert rv.status_code == 200, f"HTTP {rv.status_code}: {rv.data}"
        assert data['success'] is True

        series = data['primary_series']
        assert len(series) >= 1, f"Expected ≥1 series point, got {series}"

        last_p = series[-1]['price']
        assert abs(last_p - FLOOR_AMT) < 0.01, (
            f"Expected floor {FLOOR_AMT:.2f} as last chart price, got {last_p:.4f}"
        )

        # summary.current_price must also reflect floor
        current = data['summary']['current_price']
        assert current is not None
        assert abs(current - FLOOR_AMT) < 0.01, (
            f"summary.current_price={current:.4f}, expected {FLOOR_AMT:.2f}"
        )

        _report(
            "FLOOR-1 PASS — chart last point equals floor when spot+premium < floor",
            floor        = f"${FLOOR_AMT:.2f}",
            spot_premium = f"${FLOOR_PREMIUM:.2f}",
            spot         = f"${SPOT_MANUAL:.2f}",
            effective    = f"${last_p:.4f}",
        )

    def test_floor_dominates_availability_json(self, tc):
        """availability_json.lowest_price must equal floor when floor > spot+premium."""
        rv   = tc.get(f'/bucket/{BUCKET_FLOOR}/availability_json')
        data = rv.get_json()

        assert rv.status_code == 200, f"HTTP {rv.status_code}: {rv.data}"
        assert data.get('lowest_price') is not None

        lp = data['lowest_price']
        assert abs(lp - FLOOR_AMT) < 0.01, (
            f"availability_json.lowest_price={lp:.4f}, expected {FLOOR_AMT:.2f} (floor)"
        )

        _report(
            "FLOOR-2 PASS — availability_json lowest_price equals floor",
            expected     = f"${FLOOR_AMT:.2f}",
            got          = f"${lp:.4f}",
        )

    def test_best_ask_matches_chart_current_price(self, tc):
        """Best Ask (availability_json) and chart summary.current_price must be identical."""
        avail_rv = tc.get(f'/bucket/{BUCKET_FLOOR}/availability_json')
        chart_rv = tc.get(f'/api/buckets/{BUCKET_FLOOR}/reference_price_history?range=1d')

        assert avail_rv.status_code == 200
        assert chart_rv.status_code == 200

        avail_data = avail_rv.get_json()
        chart_data = chart_rv.get_json()

        best_ask      = avail_data['lowest_price']
        chart_current = chart_data['summary']['current_price']

        assert best_ask is not None and chart_current is not None
        assert abs(best_ask - chart_current) < 0.01, (
            f"Best Ask={best_ask:.4f} != chart current={chart_current:.4f}"
        )

        _report(
            "FLOOR-3 PASS — Best Ask matches chart current price",
            best_ask      = f"${best_ask:.4f}",
            chart_current = f"${chart_current:.4f}",
        )

    def test_no_external_api_calls_on_availability_json(self, tc):
        """availability_json must NOT call get_current_spot_prices (external API)."""
        with patch('services.pricing_service.get_current_spot_prices') as mock_ps, \
             patch('services.spot_price_service.get_current_spot_prices') as mock_ss:
            rv = tc.get(f'/bucket/{BUCKET_FLOOR}/availability_json')

        assert rv.status_code == 200
        assert mock_ps.call_count == 0, (
            f"pricing_service.get_current_spot_prices called {mock_ps.call_count}x"
        )
        assert mock_ss.call_count == 0, (
            f"spot_price_service.get_current_spot_prices called {mock_ss.call_count}x"
        )

        _report(
            "FLOOR-4 PASS — availability_json made 0 external API calls",
            pricing_service_calls    = mock_ps.call_count,
            spot_price_service_calls = mock_ss.call_count,
        )

    def test_mixed_format_timestamps_series_strictly_sorted(self, tc):
        """
        Chart series must be strictly time-sorted even when spot_price_snapshots
        contains a mix of space-format ("YYYY-MM-DD HH:MM:SS") and T-format
        ("YYYY-MM-DDTHH:MM:SS") timestamps.

        Bucket has:
            snapshot at TS_T_OLDER (space, 2h ago) price=2000 → effective=2050
            snapshot at TS_T_NEWER (T,     1h ago) price=2200 → effective=2250
        Series must be ascending with last price ≥ first price (2050 → 2250).
        """
        rv   = tc.get(f'/api/buckets/{BUCKET_TS}/reference_price_history?range=1d')
        data = rv.get_json()

        assert rv.status_code == 200, f"HTTP {rv.status_code}: {rv.data}"
        assert data['success'] is True

        series = data['primary_series']
        assert len(series) >= 2, f"Expected ≥2 points for 2 snapshots, got {series}"

        # All timestamps must be strictly ascending (or at worst equal — no going backward)
        timestamps = [pt['t'] for pt in series]
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1], (
                f"Series not sorted: [{i-1}]={timestamps[i-1]!r} > [{i}]={timestamps[i]!r}"
            )

        # Last price must reflect the newer snapshot (2200 → effective=2250), not the older
        expected_last = round(TS_SPOT_NEWER + TS_PREMIUM, 4)
        last_p = series[-1]['price']
        assert abs(last_p - expected_last) < 0.5, (
            f"Last price={last_p:.4f}, expected ~{expected_last:.4f} "
            f"(from newer snapshot {TS_SPOT_NEWER}+{TS_PREMIUM})"
        )

        _report(
            "TS-1 PASS — series strictly ascending with mixed-format snapshots",
            older_snapshot = f"space-format, spot={TS_SPOT_OLDER}",
            newer_snapshot = f"T-format,     spot={TS_SPOT_NEWER}",
            series_points  = len(series),
            first_price    = f"${series[0]['price']:.4f}",
            last_price     = f"${last_p:.4f}",
        )

    def test_mixed_format_no_duplicate_timestamps_in_output(self, tc):
        """
        The chart must not emit two series points with the same 't' value.
        Duplicate x-values cause vertical spikes in Chart.js.
        """
        rv   = tc.get(f'/api/buckets/{BUCKET_TS}/reference_price_history?range=1d')
        data = rv.get_json()

        assert rv.status_code == 200
        series = data['primary_series']
        timestamps = [pt['t'] for pt in series]

        assert len(timestamps) == len(set(timestamps)), (
            f"Duplicate timestamps found in primary_series: {timestamps}"
        )

        _report(
            "TS-2 PASS — no duplicate timestamps in primary_series",
            series_points   = len(series),
            unique_ts_count = len(set(timestamps)),
        )

    # ------------------------------------------------------------------
    # Platinum (non-gold metal) consistency tests
    # ------------------------------------------------------------------

    def test_platinum_floor_dominates_chart(self, tc):
        """
        Fix must apply to ALL metals — platinum chart last point = floor_price
        when spot+premium < floor.

        Bucket:  premium_to_spot | metal='Platinum' | pricing_metal='platinum'
        Snapshot: PLAT_SPOT=1500 → effective = max(1500+200, 5000) = 5000
        """
        rv   = tc.get(f'/api/buckets/{BUCKET_PLAT}/reference_price_history?range=1d')
        data = rv.get_json()

        assert rv.status_code == 200, f"HTTP {rv.status_code}: {rv.data}"
        assert data['success'] is True

        series = data['primary_series']
        assert len(series) >= 1, f"Expected ≥1 series point, got {series}"

        last_p = series[-1]['price']
        assert abs(last_p - PLAT_FLOOR) < 0.01, (
            f"Platinum chart last price={last_p:.4f}, expected floor={PLAT_FLOOR:.2f}"
        )

        _report(
            "PLAT-1 PASS — platinum chart last point equals floor",
            metal        = PLAT_METAL,
            spot         = f"${PLAT_SPOT:.2f}",
            premium      = f"${PLAT_PREMIUM:.2f}",
            floor        = f"${PLAT_FLOOR:.2f}",
            chart_last   = f"${last_p:.4f}",
        )

    def test_platinum_floor_dominates_availability_json(self, tc):
        """
        availability_json Best Ask for a platinum bucket must equal floor_price
        when spot+premium < floor.  Verifies get_current_spots_from_snapshots()
        correctly returns the platinum snapshot price.
        """
        rv   = tc.get(f'/bucket/{BUCKET_PLAT}/availability_json')
        data = rv.get_json()

        assert rv.status_code == 200, f"HTTP {rv.status_code}: {rv.data}"
        lp = data.get('lowest_price')
        assert lp is not None, f"No lowest_price in response: {data}"

        assert abs(lp - PLAT_FLOOR) < 0.01, (
            f"Platinum Best Ask={lp:.4f}, expected floor={PLAT_FLOOR:.2f}"
        )

        _report(
            "PLAT-2 PASS — platinum availability_json lowest_price equals floor",
            expected = f"${PLAT_FLOOR:.2f}",
            got      = f"${lp:.4f}",
        )

    def test_platinum_best_ask_matches_chart(self, tc):
        """
        Best Ask (availability_json) and chart current_price must be identical
        for a platinum bucket — confirms both code paths use the same snapshot.
        """
        avail_rv = tc.get(f'/bucket/{BUCKET_PLAT}/availability_json')
        chart_rv = tc.get(f'/api/buckets/{BUCKET_PLAT}/reference_price_history?range=1d')

        assert avail_rv.status_code == 200
        assert chart_rv.status_code == 200

        best_ask      = avail_rv.get_json()['lowest_price']
        chart_current = chart_rv.get_json()['summary']['current_price']

        assert best_ask is not None and chart_current is not None
        assert abs(best_ask - chart_current) < 0.01, (
            f"Platinum Best Ask={best_ask:.4f} != chart current={chart_current:.4f}"
        )

        _report(
            "PLAT-3 PASS — platinum Best Ask matches chart current_price",
            best_ask      = f"${best_ask:.4f}",
            chart_current = f"${chart_current:.4f}",
        )

    def test_platinum_no_external_api_calls(self, tc):
        """
        Platinum bucket page and chart must make zero external API calls.
        """
        with patch('services.pricing_service.get_current_spot_prices') as mock_ps, \
             patch('services.spot_price_service.get_current_spot_prices') as mock_ss:
            avail_rv = tc.get(f'/bucket/{BUCKET_PLAT}/availability_json')
            chart_rv = tc.get(
                f'/api/buckets/{BUCKET_PLAT}/reference_price_history?range=1d'
            )

        assert avail_rv.status_code == 200
        assert chart_rv.status_code == 200
        assert mock_ps.call_count == 0, (
            f"pricing_service.get_current_spot_prices called {mock_ps.call_count}x"
        )
        assert mock_ss.call_count == 0, (
            f"spot_price_service.get_current_spot_prices called {mock_ss.call_count}x"
        )

        _report(
            "PLAT-4 PASS — platinum: 0 external API calls on availability_json + chart",
            pricing_service_calls    = mock_ps.call_count,
            spot_price_service_calls = mock_ss.call_count,
        )

    # ------------------------------------------------------------------
    # Buy-page tile price consistency tests
    # ------------------------------------------------------------------

    def test_buy_page_tile_price_matches_best_ask(self, tc):
        """
        The price shown on the /buy tile for a bucket must equal the Best Ask
        (availability_json.lowest_price) — both must use the same DB snapshot.

        Floor bucket: floor=4000, spot=1000, premium=100 → effective=4000.
        The /buy HTML must contain "4,000" for this bucket's tile.
        """
        avail_rv = tc.get(f'/bucket/{BUCKET_FLOOR}/availability_json')
        buy_rv   = tc.get('/buy')

        assert avail_rv.status_code == 200
        assert buy_rv.status_code == 200

        best_ask = avail_rv.get_json()['lowest_price']
        assert best_ask is not None

        # The buy page renders the price as "$X,XXX" — check for the integer part
        expected_str = f'{int(best_ask):,}'  # "4,000"
        html = buy_rv.data.decode()
        assert expected_str in html, (
            f"Buy page tile price '{expected_str}' not found in /buy HTML "
            f"(best_ask={best_ask}). Tile price and Best Ask are out of sync."
        )

        _report(
            "BUY-1 PASS — /buy tile price matches availability_json Best Ask",
            best_ask          = f"${best_ask:.2f}",
            expected_in_html  = f"${expected_str}",
        )

    def test_buy_page_tile_platinum_price_matches_best_ask(self, tc):
        """
        Same consistency check for a platinum bucket:
        floor=5000, spot=1500, premium=200 → effective=5000.
        """
        avail_rv = tc.get(f'/bucket/{BUCKET_PLAT}/availability_json')
        buy_rv   = tc.get('/buy')

        assert avail_rv.status_code == 200
        assert buy_rv.status_code == 200

        best_ask = avail_rv.get_json()['lowest_price']
        assert best_ask is not None

        expected_str = f'{int(best_ask):,}'  # "5,000"
        html = buy_rv.data.decode()
        assert expected_str in html, (
            f"Buy page tile platinum price '{expected_str}' not found in /buy HTML "
            f"(best_ask={best_ask}). Tile price and Best Ask are out of sync."
        )

        _report(
            "BUY-2 PASS — /buy platinum tile price matches availability_json Best Ask",
            metal    = 'platinum',
            best_ask = f"${best_ask:.2f}",
            html_key = f"${expected_str}",
        )

    def test_buy_page_no_external_api_calls(self, tc):
        """
        /buy page must never call the external spot-price API.
        All pricing must come from spot_price_snapshots.
        """
        with patch('services.pricing_service.get_current_spot_prices') as mock_ps, \
             patch('services.spot_price_service.get_current_spot_prices') as mock_ss:
            rv = tc.get('/buy')

        assert rv.status_code == 200
        assert mock_ps.call_count == 0, (
            f"pricing_service.get_current_spot_prices called {mock_ps.call_count}x on /buy"
        )
        assert mock_ss.call_count == 0, (
            f"spot_price_service.get_current_spot_prices called {mock_ss.call_count}x on /buy"
        )

        _report(
            "BUY-3 PASS — /buy made 0 external API calls",
            pricing_service_calls    = mock_ps.call_count,
            spot_price_service_calls = mock_ss.call_count,
        )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _report(title: str, **details):
    """Print structured test result to stdout (visible with pytest -s)."""
    print(f"\n  ✓ {title}")
    for key, val in details.items():
        print(f"      {key:<30}: {val}")
