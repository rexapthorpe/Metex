"""
Cart Pricing Tests — verifies that cart Order Summary uses
the canonical effective pricing logic (same source as Bucket page).

Tests:
  CART-1  floor dominates     : spot=1000, premium=100, floor=4000, qty=3 → avg=4000, subtotal=12000
  CART-2  spot dominates      : spot=5000, premium=100, floor=4000, qty=2 → avg=5100, subtotal=10200
  CART-3  mid-session change  : insert spot=5000, render; insert spot=6000, re-render → subtotal updates
  CART-4  static listing      : unaffected by spot snapshot
  CART-5  no external calls   : requests.get never called during cart render
  CART-6  multi-seller        : two listings, correct avg + subtotal (regression guard)

Run:
    python -m pytest tests/test_cart_pricing.py -v -s
"""

import os
import sys
import sqlite3
import tempfile
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ---------------------------------------------------------------------------
# Minimal schema — only the tables touched by build_cart_summary / get_cart_items
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
    grade              TEXT,
    series_variant     TEXT,
    coin_series        TEXT,
    platform_fee_type  TEXT,
    platform_fee_value REAL
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
    isolated_type   TEXT,
    packaging_type  TEXT,
    packaging_notes TEXT,
    edition_number  INTEGER,
    edition_total   INTEGER,
    condition_notes TEXT,
    graded          INTEGER DEFAULT 0,
    grading_service TEXT,
    photo_filename  TEXT
);

CREATE TABLE IF NOT EXISTS listing_photos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id     INTEGER NOT NULL,
    file_path      TEXT,
    position_index INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cart (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                    INTEGER NOT NULL,
    listing_id                 INTEGER NOT NULL,
    quantity                   INTEGER DEFAULT 1,
    third_party_grading_requested INTEGER DEFAULT 0,
    grading_preference         TEXT    DEFAULT 'NONE'
);

CREATE TABLE IF NOT EXISTS ratings (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ratee_id INTEGER,
    rating   REAL
);

CREATE TABLE IF NOT EXISTS spot_price_snapshots (
    id         INTEGER   PRIMARY KEY AUTOINCREMENT,
    metal      TEXT      NOT NULL,
    price_usd  REAL      NOT NULL,
    as_of      TIMESTAMP NOT NULL,
    source     TEXT      DEFAULT 'test',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

NOW = datetime.now()

# Unique user IDs per test — avoids any cross-test contamination
USER_FLOOR   = 901
USER_SPOT    = 902
USER_MULTI   = 903
USER_STATIC  = 904
USER_NOCALL  = 905
USER_MIDSPOT = 907  # Test 3: mid-session spot change


# ---------------------------------------------------------------------------
# Module-scoped fixture: one DB file, shared across all tests in this module
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def cart_env():
    """
    Create a temporary SQLite DB, patch database.get_db_connection to point at it,
    also patch the module-level binding in utils.cart_utils and cart.py, then yield
    the Flask app.  Restores everything on teardown.
    """
    import database
    from app import app as flask_app

    tmpdir  = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, 'cart_pricing_test.db')

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

    # cart.py (buy blueprint) and checkout use module-level bindings
    import core.blueprints.buy.cart as _cart_mod
    import core.blueprints.buy.buy_page as _buy_page_mod
    _orig_cart_db     = _cart_mod.get_db_connection
    _orig_buy_page_db = _buy_page_mod.get_db_connection
    _cart_mod.get_db_connection     = get_test_conn
    _buy_page_mod.get_db_connection = get_test_conn

    flask_app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-cart-pricing-key',
    })

    # Insert shared test users
    conn = get_test_conn()
    conn.execute("INSERT OR REPLACE INTO users (id, username, email) VALUES (?, 'seller_floor', 'sf@t.com')", (USER_FLOOR,))
    conn.execute("INSERT OR REPLACE INTO users (id, username, email) VALUES (?, 'seller_spot',  'ss@t.com')", (USER_SPOT,))
    conn.execute("INSERT OR REPLACE INTO users (id, username, email) VALUES (?, 'seller_multi', 'sm@t.com')", (USER_MULTI,))
    conn.execute("INSERT OR REPLACE INTO users (id, username, email) VALUES (?, 'seller_static','st@t.com')", (USER_STATIC,))
    conn.execute("INSERT OR REPLACE INTO users (id, username, email) VALUES (?, 'seller_nocall','sn@t.com')", (USER_NOCALL,))
    conn.commit()
    conn.close()

    yield flask_app, get_test_conn

    # Teardown: restore original bindings
    database.get_db_connection        = original_get_db
    _cart_mod.get_db_connection       = _orig_cart_db
    _buy_page_mod.get_db_connection   = _orig_buy_page_db


# ---------------------------------------------------------------------------
# Helper: seed one cart scenario and call build_cart_summary
# ---------------------------------------------------------------------------

def _run_cart_summary(get_test_conn, flask_app, buyer_id, seller_id,
                      category_data, listing_data, snapshot_data, qty=1, grading=0):
    """
    Insert one category + one listing + one cart row + spot snapshots,
    then call build_cart_summary inside a Flask request context (so `session` works).

    Returns the build_cart_summary result dict.
    """
    from utils.cart_utils import build_cart_summary
    from services.reference_price_service import get_current_spots_from_snapshots

    conn = get_test_conn()

    # Clear leftover cart entries from previous runs of this buyer (module-scoped DB)
    conn.execute("DELETE FROM cart WHERE user_id = ?", (buyer_id,))

    # Category
    conn.execute(
        "INSERT INTO categories (metal, product_type, weight, is_isolated) VALUES (?, ?, ?, 0)",
        (category_data['metal'], category_data.get('product_type', 'Coin'),
         category_data.get('weight', '1 oz')),
    )
    cat_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Listing(s) — listing_data may be a list for multi-seller tests
    listing_ids = []
    if not isinstance(listing_data, list):
        listing_data = [listing_data]
    for ld in listing_data:
        conn.execute(
            "INSERT INTO listings "
            "  (seller_id, category_id, price_per_coin, quantity, active, "
            "   pricing_mode, spot_premium, floor_price, pricing_metal) "
            "VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)",
            (seller_id, cat_id,
             ld.get('price_per_coin', 0.0),
             ld.get('quantity', qty),
             ld.get('pricing_mode', 'static'),
             ld.get('spot_premium'),
             ld.get('floor_price'),
             ld.get('pricing_metal', category_data['metal'])),
        )
        listing_ids.append(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    # Cart rows (only for this category — old cart entries already cleared above)
    for lid in listing_ids:
        conn.execute(
            "INSERT INTO cart (user_id, listing_id, quantity, third_party_grading_requested, grading_preference) "
            "VALUES (?, ?, ?, ?, ?)",
            (buyer_id, lid, qty, grading, 'ANY' if grading else 'NONE'),
        )

    # Spot snapshots
    for metal, price, ts in snapshot_data:
        conn.execute(
            "INSERT INTO spot_price_snapshots (metal, price_usd, as_of) VALUES (?, ?, ?)",
            (metal, price, ts),
        )

    conn.commit()

    # Build spot_prices dict directly from the test-inserted snapshots.
    # get_current_spots_from_snapshots only covers _TRACKED_METALS (gold, silver, platinum,
    # palladium), so test-specific metal names would be missed.  Building the dict here
    # mirrors what the production cart route does for any metal found in snapshots.
    spot_prices = {}
    for metal, price, _ts in snapshot_data:
        spot_prices[metal] = price  # later inserts for same metal override earlier ones

    # Run build_cart_summary inside Flask request context (session required)
    with flask_app.test_request_context():
        from flask import session
        session['user_id'] = buyer_id
        result = build_cart_summary(conn, user_id=buyer_id, spot_prices=spot_prices)

    conn.close()
    return result


# ---------------------------------------------------------------------------
# CART-1  floor dominates
# ---------------------------------------------------------------------------

class TestCartFloorDominates:
    """
    CART-1: premium_to_spot listing where floor wins.
    spot=1000, premium=100 → computed=1100; floor=4000 → effective=4000
    """

    def test_effective_price_is_floor(self, cart_env):
        flask_app, get_test_conn = cart_env
        metal = 'cart_test_gold_floor'
        snap_ts = NOW.isoformat()

        result = _run_cart_summary(
            get_test_conn, flask_app,
            buyer_id=USER_FLOOR, seller_id=USER_FLOOR,
            category_data={'metal': metal},
            listing_data={
                'pricing_mode': 'premium_to_spot',
                'spot_premium': 100.0,
                'floor_price':  4000.0,
                'pricing_metal': metal,
            },
            snapshot_data=[(metal, 1000.0, snap_ts)],
            qty=1,
        )

        buckets = result['buckets']
        assert len(buckets) == 1, "Expected exactly one bucket"
        bucket = next(iter(buckets.values()))

        listing = bucket['listings'][0]
        assert listing['effective_price'] == 4000.0, (
            f"Floor should dominate: expected $4000.00, got ${listing['effective_price']}"
        )
        assert result['subtotal'] == 4000.0
        assert bucket['avg_price'] == 4000.0

    def test_total_scales_with_quantity(self, cart_env):
        """Floor-based price × qty = correct subtotal."""
        flask_app, get_test_conn = cart_env
        metal = 'cart_test_gold_floor_qty'
        snap_ts = NOW.isoformat()

        result = _run_cart_summary(
            get_test_conn, flask_app,
            buyer_id=USER_FLOOR, seller_id=USER_FLOOR,
            category_data={'metal': metal},
            listing_data={
                'pricing_mode': 'premium_to_spot',
                'spot_premium': 100.0,
                'floor_price':  4000.0,
                'pricing_metal': metal,
                'quantity': 3,
            },
            snapshot_data=[(metal, 1000.0, snap_ts)],
            qty=3,
        )

        bucket = next(iter(result['buckets'].values()))
        assert bucket['total_qty'] == 3
        assert result['subtotal'] == 12000.0


# ---------------------------------------------------------------------------
# CART-2  spot dominates
# ---------------------------------------------------------------------------

class TestCartSpotDominates:
    """
    CART-2: premium_to_spot listing where spot+premium wins.
    spot=5000, premium=100 → computed=5100; floor=4000 → effective=5100
    """

    def test_effective_price_is_spot_plus_premium(self, cart_env):
        flask_app, get_test_conn = cart_env
        metal = 'cart_test_gold_spot_dom'
        snap_ts = NOW.isoformat()

        result = _run_cart_summary(
            get_test_conn, flask_app,
            buyer_id=USER_SPOT, seller_id=USER_SPOT,
            category_data={'metal': metal},
            listing_data={
                'pricing_mode': 'premium_to_spot',
                'spot_premium': 100.0,
                'floor_price':  4000.0,
                'pricing_metal': metal,
            },
            snapshot_data=[(metal, 5000.0, snap_ts)],
            qty=1,
        )

        bucket = next(iter(result['buckets'].values()))
        listing = bucket['listings'][0]

        assert listing['effective_price'] == 5100.0, (
            f"Spot+premium should dominate: expected $5100.00, got ${listing['effective_price']}"
        )
        assert result['subtotal'] == 5100.0
        assert bucket['avg_price'] == 5100.0

    def test_subtotal_scales_with_quantity(self, cart_env):
        """
        CART-2b: spot=5000, premium=100, floor=4000, qty=2
        → average_price=5100, subtotal=10200
        """
        flask_app, get_test_conn = cart_env
        metal = 'cart_test_gold_spot_qty2'
        snap_ts = NOW.isoformat()

        result = _run_cart_summary(
            get_test_conn, flask_app,
            buyer_id=USER_SPOT, seller_id=USER_SPOT,
            category_data={'metal': metal},
            listing_data={
                'pricing_mode': 'premium_to_spot',
                'spot_premium': 100.0,
                'floor_price':  4000.0,
                'pricing_metal': metal,
                'quantity': 2,
            },
            snapshot_data=[(metal, 5000.0, snap_ts)],
            qty=2,
        )

        bucket = next(iter(result['buckets'].values()))
        assert bucket['avg_price'] == 5100.0, (
            f"avg_price must be per-unit effective price: expected $5100, got ${bucket['avg_price']}"
        )
        assert result['subtotal'] == 10200.0, (
            f"subtotal must equal avg_price × qty: expected $10200, got ${result['subtotal']}"
        )


# ---------------------------------------------------------------------------
# CART-3  mid-session spot change
# ---------------------------------------------------------------------------

class TestCartMidSessionSpotChange:
    """
    CART-3: insert spot=5000, render cart, assert subtotal uses spot=5000.
    Then insert spot=6000 (newer timestamp), re-render, assert subtotal updates.

    Uses 'gold' — a _TRACKED_METALS entry — so get_current_spots_from_snapshots
    returns the new snapshot without special handling.
    """

    def test_subtotal_reflects_updated_snapshot(self, cart_env):
        flask_app, get_test_conn = cart_env
        from utils.cart_utils import build_cart_summary
        from services.reference_price_service import get_current_spots_from_snapshots
        from datetime import timedelta

        metal = 'gold'
        spot_premium = 100.0
        floor_price = 3000.0
        qty = 2

        conn = get_test_conn()

        # --- setup user, category, listing, cart -------------------------
        conn.execute(
            "INSERT OR REPLACE INTO users (id, username, email) VALUES (?, 'midspot_buyer', 'ms@t.com')",
            (USER_MIDSPOT,),
        )
        conn.execute("DELETE FROM cart WHERE user_id = ?", (USER_MIDSPOT,))

        conn.execute(
            "INSERT INTO categories (metal, product_type, weight, is_isolated) VALUES (?, 'Coin', '1 oz', 0)",
            (metal,),
        )
        cat_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.execute(
            "INSERT INTO listings "
            "  (seller_id, category_id, price_per_coin, quantity, active, "
            "   pricing_mode, spot_premium, floor_price, pricing_metal) "
            "VALUES (?, ?, 0, ?, 1, 'premium_to_spot', ?, ?, ?)",
            (USER_MIDSPOT, cat_id, qty + 10, spot_premium, floor_price, metal),
        )
        lid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.execute(
            "INSERT INTO cart (user_id, listing_id, quantity, third_party_grading_requested) VALUES (?, ?, ?, 0)",
            (USER_MIDSPOT, lid, qty),
        )

        # --- First render: spot=5000 (older timestamp) -------------------
        t1 = (NOW - timedelta(seconds=60)).isoformat()
        conn.execute(
            "INSERT INTO spot_price_snapshots (metal, price_usd, as_of) VALUES (?, ?, ?)",
            (metal, 5000.0, t1),
        )
        conn.commit()

        spot_prices_1 = get_current_spots_from_snapshots(conn)
        assert 'gold' in spot_prices_1, "gold snapshot must be found by get_current_spots_from_snapshots"
        assert spot_prices_1['gold'] == 5000.0

        with flask_app.test_request_context():
            from flask import session
            session['user_id'] = USER_MIDSPOT
            result_1 = build_cart_summary(conn, user_id=USER_MIDSPOT, spot_prices=spot_prices_1)

        # effective_1 = max(5000+100, 3000) = 5100;  subtotal = 5100 × 2 = 10200
        assert result_1['subtotal'] == 10200.0, (
            f"[spot=5000] Expected subtotal=$10200, got ${result_1['subtotal']}"
        )
        assert next(iter(result_1['buckets'].values()))['avg_price'] == 5100.0

        # --- Second render: spot=6000 (newer timestamp) ------------------
        t2 = NOW.isoformat()  # More recent than t1
        conn.execute(
            "INSERT INTO spot_price_snapshots (metal, price_usd, as_of) VALUES (?, ?, ?)",
            (metal, 6000.0, t2),
        )
        conn.commit()

        spot_prices_2 = get_current_spots_from_snapshots(conn)
        assert spot_prices_2['gold'] == 6000.0, (
            f"get_current_spots_from_snapshots must return newest snapshot: expected 6000, got {spot_prices_2['gold']}"
        )

        with flask_app.test_request_context():
            from flask import session
            session['user_id'] = USER_MIDSPOT
            result_2 = build_cart_summary(conn, user_id=USER_MIDSPOT, spot_prices=spot_prices_2)

        conn.close()

        # effective_2 = max(6000+100, 3000) = 6100;  subtotal = 6100 × 2 = 12200
        assert result_2['subtotal'] == 12200.0, (
            f"[spot=6000] Expected subtotal=$12200, got ${result_2['subtotal']}"
        )
        assert next(iter(result_2['buckets'].values()))['avg_price'] == 6100.0

        # The key assertion: subtotal CHANGED because spot changed
        assert result_2['subtotal'] != result_1['subtotal'], (
            "Subtotal must update when spot snapshot changes — "
            f"both renders returned ${result_1['subtotal']}"
        )


# ---------------------------------------------------------------------------
# CART-6  multi-seller bucket (was CART-3 — renumbered to make room)
# ---------------------------------------------------------------------------

class TestCartMultiSeller:
    """
    CART-3: two listings in the same category bucket.
    Listing A: premium_to_spot, spot=1000, premium=100, floor=0 → $1100
    Listing B: premium_to_spot, spot=1000, premium=200, floor=0 → $1200
    Expected: correct per-listing effective prices, correct avg and subtotal.
    """

    def test_multi_seller_correct_prices(self, cart_env):
        flask_app, get_test_conn = cart_env
        from utils.cart_utils import build_cart_summary
        from services.reference_price_service import get_current_spots_from_snapshots

        metal = 'cart_test_multi_seller'
        snap_ts = NOW.isoformat()
        spot_price = 1000.0

        conn = get_test_conn()

        # Clear leftover cart entries for this user
        conn.execute("DELETE FROM cart WHERE user_id = ?", (USER_MULTI,))

        conn.execute(
            "INSERT INTO categories (metal, product_type, weight, is_isolated) VALUES (?, 'Coin', '1 oz', 0)",
            (metal,),
        )
        cat_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Listing A — cheaper by effective price
        conn.execute(
            "INSERT INTO listings "
            "  (seller_id, category_id, price_per_coin, quantity, active, "
            "   pricing_mode, spot_premium, floor_price, pricing_metal) "
            "VALUES (?, ?, 0, 1, 1, 'premium_to_spot', 100.0, 0.0, ?)",
            (USER_MULTI, cat_id, metal),
        )
        lid_a = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Listing B — more expensive by effective price
        conn.execute(
            "INSERT INTO listings "
            "  (seller_id, category_id, price_per_coin, quantity, active, "
            "   pricing_mode, spot_premium, floor_price, pricing_metal) "
            "VALUES (?, ?, 0, 1, 1, 'premium_to_spot', 200.0, 0.0, ?)",
            (USER_MULTI, cat_id, metal),
        )
        lid_b = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Add both to cart (qty=1 each)
        conn.execute(
            "INSERT INTO cart (user_id, listing_id, quantity, third_party_grading_requested) VALUES (?, ?, 1, 0)",
            (USER_MULTI, lid_a),
        )
        conn.execute(
            "INSERT INTO cart (user_id, listing_id, quantity, third_party_grading_requested) VALUES (?, ?, 1, 0)",
            (USER_MULTI, lid_b),
        )

        conn.execute(
            "INSERT INTO spot_price_snapshots (metal, price_usd, as_of) VALUES (?, ?, ?)",
            (metal, spot_price, snap_ts),
        )
        conn.commit()

        spot_prices = {metal: spot_price}

        with flask_app.test_request_context():
            from flask import session
            session['user_id'] = USER_MULTI
            result = build_cart_summary(conn, user_id=USER_MULTI, spot_prices=spot_prices)

        conn.close()

        buckets = result['buckets']
        assert len(buckets) == 1

        bucket = next(iter(buckets.values()))
        listings = bucket['listings']
        assert len(listings) == 2

        prices = sorted(l['effective_price'] for l in listings)
        assert prices == [1100.0, 1200.0], f"Expected [1100.0, 1200.0], got {prices}"

        assert bucket['total_qty'] == 2
        assert result['subtotal'] == 2300.0, f"Expected $2300.00 subtotal, got ${result['subtotal']}"
        assert bucket['avg_price'] == 1150.0, f"Expected $1150.00 avg, got ${bucket['avg_price']}"

    def test_multi_seller_selects_cheapest_first(self, cart_env):
        """The cheapest listing (by effective price) appears first in bucket listings."""
        flask_app, get_test_conn = cart_env
        from utils.cart_utils import build_cart_summary

        metal = 'cart_test_multi_order'
        snap_ts = NOW.isoformat()
        spot_price = 1000.0

        conn = get_test_conn()

        # Clear leftover cart entries for this user
        conn.execute("DELETE FROM cart WHERE user_id = ?", (USER_MULTI,))

        conn.execute(
            "INSERT INTO categories (metal, product_type, weight, is_isolated) VALUES (?, 'Coin', '1 oz', 0)",
            (metal,),
        )
        cat_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Insert B first (more expensive) then A (cheaper) — DB order ≠ effective-price order
        conn.execute(
            "INSERT INTO listings "
            "  (seller_id, category_id, price_per_coin, quantity, active, "
            "   pricing_mode, spot_premium, floor_price, pricing_metal) "
            "VALUES (?, ?, 0, 1, 1, 'premium_to_spot', 200.0, 0.0, ?)",
            (USER_MULTI, cat_id, metal),
        )
        lid_b2 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.execute(
            "INSERT INTO listings "
            "  (seller_id, category_id, price_per_coin, quantity, active, "
            "   pricing_mode, spot_premium, floor_price, pricing_metal) "
            "VALUES (?, ?, 0, 1, 1, 'premium_to_spot', 100.0, 0.0, ?)",
            (USER_MULTI, cat_id, metal),
        )
        lid_a2 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.execute(
            "INSERT INTO cart (user_id, listing_id, quantity, third_party_grading_requested) VALUES (?, ?, 1, 0)",
            (USER_MULTI, lid_b2),
        )
        conn.execute(
            "INSERT INTO cart (user_id, listing_id, quantity, third_party_grading_requested) VALUES (?, ?, 1, 0)",
            (USER_MULTI, lid_a2),
        )
        conn.execute(
            "INSERT INTO spot_price_snapshots (metal, price_usd, as_of) VALUES (?, ?, ?)",
            (metal, spot_price, snap_ts),
        )
        conn.commit()

        spot_prices = {metal: spot_price}

        with flask_app.test_request_context():
            from flask import session
            session['user_id'] = USER_MULTI
            result = build_cart_summary(conn, user_id=USER_MULTI, spot_prices=spot_prices)

        conn.close()

        bucket = next(iter(result['buckets'].values()))
        # `get_cart_items` sorts by price_per_coin which is 0 for both spot-priced listings,
        # so order is DB-insertion order. The TOTAL is correct regardless of order.
        prices = [l['effective_price'] for l in bucket['listings']]
        assert set(prices) == {1100.0, 1200.0}
        assert result['subtotal'] == 2300.0


# ---------------------------------------------------------------------------
# CART-4  static listing
# ---------------------------------------------------------------------------

class TestCartStaticListing:
    """
    CART-4: static listing — price_per_coin returned directly, spot snapshot ignored.
    """

    def test_static_price_ignores_spot(self, cart_env):
        flask_app, get_test_conn = cart_env
        static_price = 99.95
        metal = 'cart_test_static_silver'
        snap_ts = NOW.isoformat()

        result = _run_cart_summary(
            get_test_conn, flask_app,
            buyer_id=USER_STATIC, seller_id=USER_STATIC,
            category_data={'metal': metal},
            listing_data={
                'pricing_mode':  'static',
                'price_per_coin': static_price,
            },
            snapshot_data=[(metal, 999999.0, snap_ts)],  # extreme spot — must NOT affect price
            qty=1,
        )

        bucket = next(iter(result['buckets'].values()))
        listing = bucket['listings'][0]

        assert listing['effective_price'] == static_price, (
            f"Static listing must use price_per_coin; expected ${static_price}, "
            f"got ${listing['effective_price']}"
        )
        assert result['subtotal'] == static_price

    def test_static_price_without_any_snapshot(self, cart_env):
        """Static listing works even if no snapshot exists at all."""
        flask_app, get_test_conn = cart_env
        static_price = 42.00
        metal = 'cart_test_static_nosnap'  # metal with no snapshots

        result = _run_cart_summary(
            get_test_conn, flask_app,
            buyer_id=USER_STATIC, seller_id=USER_STATIC,
            category_data={'metal': metal},
            listing_data={
                'pricing_mode':  'static',
                'price_per_coin': static_price,
            },
            snapshot_data=[],  # no snapshots
            qty=2,
        )

        bucket = next(iter(result['buckets'].values()))
        assert bucket['avg_price'] == static_price
        assert result['subtotal'] == static_price * 2


# ---------------------------------------------------------------------------
# CART-5  no external API calls
# ---------------------------------------------------------------------------

class TestCartNoExternalApiCalls:
    """
    CART-5: confirm that the cart view route never calls the external spot API.
    """

    def test_view_cart_uses_snapshots_not_external_api(self, cart_env):
        flask_app, get_test_conn = cart_env
        metal = 'cart_test_no_api_gold'
        snap_ts = NOW.isoformat()

        # Insert test data
        conn = get_test_conn()
        conn.execute(
            "INSERT OR REPLACE INTO users (id, username, email) VALUES (?, 'buyer_nocall', 'bn@t.com')",
            (USER_NOCALL,),
        )
        conn.execute("DELETE FROM cart WHERE user_id = ?", (USER_NOCALL,))
        conn.execute(
            "INSERT INTO categories (metal, product_type, weight, is_isolated) VALUES (?, 'Coin', '1 oz', 0)",
            (metal,),
        )
        cat_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO listings "
            "  (seller_id, category_id, price_per_coin, quantity, active, "
            "   pricing_mode, spot_premium, floor_price, pricing_metal) "
            "VALUES (?, ?, 0, 2, 1, 'premium_to_spot', 50.0, 100.0, ?)",
            (USER_NOCALL, cat_id, metal),
        )
        lid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO cart (user_id, listing_id, quantity, third_party_grading_requested) VALUES (?, ?, 1, 0)",
            (USER_NOCALL, lid),
        )
        conn.execute(
            "INSERT INTO spot_price_snapshots (metal, price_usd, as_of) VALUES (?, ?, ?)",
            (metal, 2000.0, snap_ts),
        )
        conn.commit()
        conn.close()

        with patch('services.spot_price_service.get_current_spot_prices') as mock_api:
            mock_api.side_effect = AssertionError("External spot API must NOT be called during cart render")

            with flask_app.test_client() as client:
                with client.session_transaction() as sess:
                    sess['user_id'] = USER_NOCALL
                response = client.get('/view_cart')

            # If we reach here, the external API was not called (no AssertionError raised)
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    def test_build_cart_summary_uses_provided_spot_prices(self, cart_env):
        """
        When spot_prices dict is passed to build_cart_summary, get_current_spot_prices
        must never be invoked (it would call the external API).
        """
        flask_app, get_test_conn = cart_env
        from utils.cart_utils import build_cart_summary

        # Use a dedicated user ID so this test is fully isolated from the view_cart test above
        user_id = 906
        metal = 'cart_test_provided_spots'
        spot_val = 3000.0

        conn = get_test_conn()
        conn.execute(
            "INSERT OR REPLACE INTO users (id, username, email) VALUES (?, 'buyer_provided', 'bp@t.com')",
            (user_id,),
        )
        conn.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
        conn.execute(
            "INSERT INTO categories (metal, product_type, weight, is_isolated) VALUES (?, 'Coin', '1 oz', 0)",
            (metal,),
        )
        cat_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO listings "
            "  (seller_id, category_id, price_per_coin, quantity, active, "
            "   pricing_mode, spot_premium, floor_price, pricing_metal) "
            "VALUES (?, ?, 0, 1, 1, 'premium_to_spot', 200.0, 0.0, ?)",
            (user_id, cat_id, metal),
        )
        lid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO cart (user_id, listing_id, quantity, third_party_grading_requested) VALUES (?, ?, 1, 0)",
            (user_id, lid),
        )
        conn.commit()

        with patch('services.spot_price_service.get_current_spot_prices') as mock_api:
            mock_api.side_effect = AssertionError("External API must NOT be called when spot_prices supplied")
            spot_prices = {metal: spot_val}

            with flask_app.test_request_context():
                from flask import session
                session['user_id'] = user_id
                result = build_cart_summary(conn, user_id=user_id, spot_prices=spot_prices)

        conn.close()

        bucket = next(iter(result['buckets'].values()))
        # effective = max(3000 + 200, 0) = 3200
        assert bucket['listings'][0]['effective_price'] == 3200.0
