"""
test_update_qty_spot.py

Verifies that POST /cart/update_bucket_quantity/<category_id>
returns effective prices that USE the spot snapshot, not the raw
price_per_coin, when the listing is premium_to_spot.

Also verifies the mid-session scenario: if the spot price changes
between the initial page render and a quantity update, the response
from update_bucket_quantity reflects the NEW spot price (not the
stale one the page was rendered with).

Run:
    source venv/bin/activate && python3 -m pytest tests/test_update_qty_spot.py -v
"""

import os
import sys
import sqlite3
import tempfile
import shutil
import json
import pytest
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ---------------------------------------------------------------------------
# Minimal schema for this test module
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT,
    email         TEXT    DEFAULT '',
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
    product_type       TEXT DEFAULT 'Coin',
    weight             TEXT DEFAULT '1 oz',
    mint               TEXT,
    year               TEXT,
    product_line       TEXT,
    purity             TEXT,
    finish             TEXT,
    is_isolated        INTEGER DEFAULT 0,
    platform_fee_type  TEXT,
    platform_fee_value REAL,
    grade              TEXT,
    coin_series        TEXT,
    series_variant     TEXT
);
CREATE TABLE IF NOT EXISTS listings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id       INTEGER NOT NULL,
    category_id     INTEGER NOT NULL,
    quantity        INTEGER DEFAULT 1,
    price_per_coin  REAL    DEFAULT 0,
    active          INTEGER DEFAULT 1,
    pricing_mode    TEXT    DEFAULT 'static',
    spot_premium    REAL    DEFAULT 0,
    floor_price     REAL    DEFAULT 0,
    pricing_metal   TEXT,
    is_isolated     INTEGER DEFAULT 0,
    graded          INTEGER DEFAULT 0,
    grading_service TEXT,
    photo_filename  TEXT,
    listing_title   TEXT
);
CREATE TABLE IF NOT EXISTS listing_photos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL,
    file_path  TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS cart (
    id                            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                       INTEGER NOT NULL,
    listing_id                    INTEGER NOT NULL,
    quantity                      INTEGER DEFAULT 1,
    third_party_grading_requested INTEGER DEFAULT 0,
    grading_preference            TEXT    DEFAULT 'NONE'
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

BUYER_ID  = 8801
SELLER_ID = 8802
GOLD_SPOT = 3000.0
PREMIUM   = 50.0
FLOOR     = 100.0


# ---------------------------------------------------------------------------
# Module-scoped fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qty_env():
    """
    Temp DB wired into database + cart routes module-level binding.
    Yields (flask_app, get_test_conn).
    """
    from app import app as flask_app  # noqa: F401 side-effect import

    import database
    import utils.auth_utils as auth_mod
    import core.blueprints.cart.routes as cart_routes_mod

    tmpdir  = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "qty_spot_test.db")

    raw = sqlite3.connect(db_path)
    raw.executescript(SCHEMA)
    raw.commit()
    raw.close()

    orig_db    = database.get_db_connection
    orig_auth  = auth_mod.get_db_connection
    orig_cart  = cart_routes_mod.get_db_connection

    def get_test_conn():
        c = sqlite3.connect(db_path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    database.get_db_connection          = get_test_conn
    auth_mod.get_db_connection          = get_test_conn
    cart_routes_mod.get_db_connection   = get_test_conn

    flask_app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-qty-spot-key",
    })

    conn = get_test_conn()
    for uid, uname in [(BUYER_ID, "qty_buyer"), (SELLER_ID, "qty_seller")]:
        conn.execute(
            "INSERT OR REPLACE INTO users (id, username, email) VALUES (?,?,?)",
            (uid, uname, f"{uname}@t.com"),
        )
    conn.commit()
    conn.close()

    with flask_app.test_client() as client:
        yield client, get_test_conn

    database.get_db_connection          = orig_db
    auth_mod.get_db_connection          = orig_auth
    cart_routes_mod.get_db_connection   = orig_cart
    shutil.rmtree(tmpdir, ignore_errors=True)


def _login(client):
    with client.session_transaction() as sess:
        sess["user_id"] = BUYER_ID


def _seed(get_test_conn, snapshot_price, qty_in_cart, qty_in_listing=10):
    """
    Insert category + listing (premium_to_spot) + cart row + spot snapshot.
    Returns (category_id, listing_id).
    Clears any existing cart rows for BUYER_ID first.
    """
    now = datetime.now()
    conn = get_test_conn()
    conn.execute("DELETE FROM cart          WHERE user_id   = ?", (BUYER_ID,))
    conn.execute("DELETE FROM spot_price_snapshots WHERE metal = 'gold'")

    conn.execute(
        "INSERT INTO categories (bucket_id, metal, product_type, weight) VALUES (?,?,?,?)",
        (7701, "gold", "Coin", "1 oz"),
    )
    cat_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        "INSERT INTO listings "
        "(seller_id, category_id, quantity, price_per_coin, active, "
        " pricing_mode, spot_premium, floor_price, pricing_metal) "
        "VALUES (?,?,?,?,1,'premium_to_spot',?,?,?)",
        (SELLER_ID, cat_id, qty_in_listing, 0.0, PREMIUM, FLOOR, "gold"),
    )
    lid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        "INSERT INTO cart (user_id, listing_id, quantity, third_party_grading_requested) "
        "VALUES (?,?,?,0)",
        (BUYER_ID, lid, qty_in_cart),
    )

    # Insert spot snapshot
    conn.execute(
        "INSERT INTO spot_price_snapshots (metal, price_usd, as_of) VALUES (?,?,?)",
        ("gold", snapshot_price, now.isoformat()),
    )
    conn.commit()
    conn.close()
    return cat_id, lid


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestUpdateQtySpotPricing:
    """
    QTY-1: Response total_price uses snapshot spot price, not price_per_coin.
    QTY-2: Decreasing quantity uses spot-based effective price.
    QTY-3: Increasing quantity uses spot-based effective price.
    QTY-4: Mid-session spot change — qty update uses CURRENT snapshot.
    """

    def test_qty1_response_uses_spot_not_static(self, qty_env):
        """QTY-1: total_price must equal qty × (spot + premium), not qty × price_per_coin."""
        client, get_test_conn = qty_env
        _login(client)
        cat_id, _ = _seed(get_test_conn, snapshot_price=GOLD_SPOT, qty_in_cart=3)

        # effective = max(3000 + 50, 100) = 3050
        expected_total = 3 * (GOLD_SPOT + PREMIUM)  # $9150 (no floor effect)

        resp = client.post(
            f"/cart/update_bucket_quantity/{cat_id}",
            data=json.dumps({"quantity": 3, "requires_grading": 0}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.data}"
        data = resp.get_json()
        assert data["success"] is True
        assert data["quantity"] == 3
        assert abs(data["total_price"] - expected_total) < 0.01, (
            f"QTY-1: total_price should be {expected_total} (spot-based), "
            f"got {data['total_price']}. "
            f"price_per_coin=0, so if total≈0 the route is using static price."
        )
        assert abs(data["avg_price"] - (GOLD_SPOT + PREMIUM)) < 0.01, (
            f"QTY-1: avg_price should be {GOLD_SPOT + PREMIUM}, got {data['avg_price']}"
        )

    def test_qty2_decrease_uses_spot(self, qty_env):
        """QTY-2: Decrease qty 3→2; total_price must be 2 × effective(spot)."""
        client, get_test_conn = qty_env
        _login(client)
        cat_id, _ = _seed(get_test_conn, snapshot_price=GOLD_SPOT, qty_in_cart=3)

        expected_total = 2 * (GOLD_SPOT + PREMIUM)  # $6100

        resp = client.post(
            f"/cart/update_bucket_quantity/{cat_id}",
            data=json.dumps({"quantity": 2, "requires_grading": 0}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["quantity"] == 2
        assert abs(data["total_price"] - expected_total) < 0.01, (
            f"QTY-2: total after decrease should be {expected_total}, got {data['total_price']}"
        )

    def test_qty3_increase_uses_spot(self, qty_env):
        """QTY-3: Increase qty 2→4; total_price must be 4 × effective(spot)."""
        client, get_test_conn = qty_env
        _login(client)
        cat_id, _ = _seed(get_test_conn, snapshot_price=GOLD_SPOT, qty_in_cart=2)

        expected_total = 4 * (GOLD_SPOT + PREMIUM)  # $12200

        resp = client.post(
            f"/cart/update_bucket_quantity/{cat_id}",
            data=json.dumps({"quantity": 4, "requires_grading": 0}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["quantity"] == 4
        assert abs(data["total_price"] - expected_total) < 0.01, (
            f"QTY-3: total after increase should be {expected_total}, got {data['total_price']}"
        )

    def test_qty4_mid_session_spot_change(self, qty_env):
        """
        QTY-4: Mid-session spot change.

        Scenario:
          1. Page renders with spot=3000 → shows $9150 for qty=3
          2. Spot updates to 4000 (new snapshot inserted)
          3. User changes qty → update_bucket_quantity called
          4. Response must use NEW spot (4000), not the stale 3000

        This is the exact user-reported bug scenario.
        """
        client, get_test_conn = qty_env
        _login(client)
        cat_id, _ = _seed(get_test_conn, snapshot_price=GOLD_SPOT, qty_in_cart=3)

        # Simulate a spot price update AFTER page render but BEFORE qty change
        new_spot = 4000.0
        conn = get_test_conn()
        conn.execute(
            "INSERT INTO spot_price_snapshots (metal, price_usd, as_of) VALUES (?,?,?)",
            ("gold", new_spot, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()

        # Now change quantity — route must pick up the NEW snapshot
        expected_total = 2 * (new_spot + PREMIUM)  # 2 × 4050 = 8100

        resp = client.post(
            f"/cart/update_bucket_quantity/{cat_id}",
            data=json.dumps({"quantity": 2, "requires_grading": 0}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

        # Key assertion: must use NEW spot (4000), not old (3000)
        old_spot_total = 2 * (GOLD_SPOT + PREMIUM)  # 2 × 3050 = 6100
        assert abs(data["total_price"] - expected_total) < 0.01, (
            f"QTY-4: After spot update 3000→4000, qty-change response should use new spot. "
            f"Expected total={expected_total} (new spot), got {data['total_price']}. "
            f"(Old-spot total would be {old_spot_total})"
        )
        assert abs(data["avg_price"] - (new_spot + PREMIUM)) < 0.01, (
            f"QTY-4: avg_price should reflect new spot {new_spot + PREMIUM}, "
            f"got {data['avg_price']}"
        )
