"""
Tests: Admin Listings Tab — Effective Price Display

Proven:
  1. premium_to_spot listing with floor_price=4000 and a gold spot snapshot at $5,100
     → admin listings shows effective price $5,377.78 (spot + premium), NOT $4,000.00.
  2. Floor/stored price ($4,000.00) still rendered in the stored-price column.
  3. Static listing: both columns show the same price_per_coin value.
  4. No external spot-price API calls occur during admin listings render.
  5. premium_to_spot listing with no spot snapshot → effective_price=None → UI shows "—".
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
# Minimal schema — all tables touched by core/blueprints/admin/dashboard.py
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
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    username             TEXT,
    email                TEXT,
    password             TEXT    DEFAULT '',
    password_hash        TEXT    DEFAULT '',
    is_admin             INTEGER DEFAULT 0,
    is_banned            INTEGER DEFAULT 0,
    is_frozen            INTEGER DEFAULT 0,
    is_metex_guaranteed  INTEGER DEFAULT 0,
    created_at           TIMESTAMP
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
    condition_category TEXT,
    coin_series        TEXT
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
CREATE TABLE IF NOT EXISTS orders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_id    INTEGER,
    total_price REAL,
    status      TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS order_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     INTEGER,
    listing_id   INTEGER,
    quantity     INTEGER,
    price_each   REAL
);
CREATE TABLE IF NOT EXISTS bids (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_id     INTEGER,
    bucket_id    INTEGER,
    quantity     INTEGER DEFAULT 1,
    price_per_coin REAL,
    status       TEXT    DEFAULT 'open'
);
"""

# Test constants
ADMIN_UID = 8001
SELLER_UID = 8002

SPOT_PRICE = 5100.0       # gold spot per oz
SPOT_PREMIUM = 277.78     # listing premium over spot
FLOOR_PRICE = 4000.0      # minimum floor for premium_to_spot listing
# effective = max(5100 + 277.78, 4000) = 5377.78
EXPECTED_EFFECTIVE = 5377.78

STATIC_PRICE = 1234.56    # fixed static listing price

CAT_GOLD_ID = 101
CAT_SILVER_ID = 102
CAT_PLATINUM_ID = 103

LISTING_SPOT_ID = 501     # premium_to_spot gold listing
LISTING_STATIC_ID = 502   # static silver listing


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def test_db():
    """Module-scoped temp DB wired into database and auth_utils modules."""
    # Import the Flask app FIRST so all blueprint route modules execute their
    # top-level `from database import get_db_connection` with the REAL function,
    # before we patch database.get_db_connection below.  Without this, being
    # alphabetically the first test file means we'd be the first to import the
    # app, and the blueprint bindings would capture our test stub instead.
    from app import app as _flask_app  # noqa: F401 — side-effect import only

    import database
    import utils.auth_utils as auth_utils_mod

    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "admin_listings_test.db")

    raw = sqlite3.connect(db_path)
    raw.executescript(SCHEMA)

    # Users
    raw.execute(
        "INSERT INTO users (id, username, email, is_admin) VALUES (?, ?, ?, ?)",
        (ADMIN_UID, "al_admin", "al_admin@t.com", 1),
    )
    raw.execute(
        "INSERT INTO users (id, username, email, is_admin) VALUES (?, ?, ?, ?)",
        (SELLER_UID, "al_seller", "al_seller@t.com", 0),
    )

    # Categories
    raw.execute(
        "INSERT INTO categories (id, bucket_id, metal, product_type, weight, product_line) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (CAT_GOLD_ID, 201, "Gold", "Bar", "1 kilo", "Germania"),
    )
    raw.execute(
        "INSERT INTO categories (id, bucket_id, metal, product_type, weight, product_line) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (CAT_SILVER_ID, 202, "Silver", "Coin", "1 oz", "American Eagle"),
    )

    # premium_to_spot gold listing: floor=4000, premium=277.78
    raw.execute(
        "INSERT INTO listings "
        "(id, seller_id, category_id, quantity, price_per_coin, active, "
        " pricing_mode, spot_premium, floor_price, pricing_metal) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (LISTING_SPOT_ID, SELLER_UID, CAT_GOLD_ID, 3,
         FLOOR_PRICE, 1, "premium_to_spot", SPOT_PREMIUM, FLOOR_PRICE, "gold"),
    )

    # Static silver listing
    raw.execute(
        "INSERT INTO listings "
        "(id, seller_id, category_id, quantity, price_per_coin, active, "
        " pricing_mode, spot_premium, floor_price) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (LISTING_STATIC_ID, SELLER_UID, CAT_SILVER_ID, 5,
         STATIC_PRICE, 1, "static", None, None),
    )

    # Gold spot snapshot — fresh (30 seconds old)
    as_of = (datetime.now() - timedelta(seconds=30)).isoformat()
    raw.execute(
        "INSERT INTO spot_price_snapshots (metal, price_usd, as_of) VALUES (?, ?, ?)",
        ("gold", SPOT_PRICE, as_of),
    )

    raw.commit()
    raw.close()

    orig_db = database.get_db_connection
    orig_auth = auth_utils_mod.get_db_connection

    def get_test_conn():
        c = sqlite3.connect(db_path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    database.get_db_connection = get_test_conn
    auth_utils_mod.get_db_connection = get_test_conn

    yield db_path, get_test_conn

    database.get_db_connection = orig_db
    auth_utils_mod.get_db_connection = orig_auth
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="module")
def flask_client(test_db):
    """Flask test client pre-logged-in as admin."""
    from app import app as flask_app

    flask_app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-admin-listings-key",
    })

    with flask_app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = ADMIN_UID
        yield client


# ---------------------------------------------------------------------------
# Unit tests for the pricing logic itself
# ---------------------------------------------------------------------------

class TestEffectivePriceCalculation:
    """Verify get_effective_price() math in isolation (no DB, no HTTP)."""

    def test_premium_to_spot_effective_price(self):
        """spot + premium, clamped at floor, gives expected result."""
        from services.pricing_service import get_effective_price

        listing = {
            "pricing_mode": "premium_to_spot",
            "price_per_coin": FLOOR_PRICE,
            "floor_price": FLOOR_PRICE,
            "spot_premium": SPOT_PREMIUM,
            "pricing_metal": "gold",
            "metal": "gold",
        }
        result = get_effective_price(listing, spot_prices={"gold": SPOT_PRICE})
        assert result == EXPECTED_EFFECTIVE, (
            f"Expected {EXPECTED_EFFECTIVE}, got {result}"
        )

    def test_floor_price_is_respected(self):
        """When spot + premium < floor, floor is returned."""
        from services.pricing_service import get_effective_price

        listing = {
            "pricing_mode": "premium_to_spot",
            "price_per_coin": 4000.0,
            "floor_price": 4000.0,
            "spot_premium": -200.0,   # spot drops below floor
            "pricing_metal": "gold",
            "metal": "gold",
        }
        # spot(100) + premium(-200) = -100 → clamped to floor 4000
        result = get_effective_price(listing, spot_prices={"gold": 100.0})
        assert result == 4000.0

    def test_static_listing_returns_price_per_coin(self):
        """Static listings return price_per_coin unchanged."""
        from services.pricing_service import get_effective_price

        listing = {
            "pricing_mode": "static",
            "price_per_coin": STATIC_PRICE,
        }
        result = get_effective_price(listing, spot_prices={})
        assert result == STATIC_PRICE


# ---------------------------------------------------------------------------
# Integration tests via the admin dashboard HTTP endpoint
# ---------------------------------------------------------------------------

class TestAdminListingsPricingPage:
    """Admin /admin/dashboard listings tab shows effective prices correctly."""

    def test_page_loads_as_admin(self, flask_client):
        """Sanity: admin dashboard returns 200."""
        resp = flask_client.get("/admin/dashboard")
        assert resp.status_code == 200

    def test_effective_price_shown_for_spot_listing(self, flask_client):
        """Effective price (5,377.78) is present in the admin listings HTML."""
        resp = flask_client.get("/admin/dashboard")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "5,377.78" in body, (
            "Expected effective price $5,377.78 in admin listings, "
            "but it was not found. Admin page may still be showing floor_price only."
        )

    def test_floor_price_shown_as_stored(self, flask_client):
        """Floor price (4,000.00) still appears in the stored-price column."""
        resp = flask_client.get("/admin/dashboard")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "4,000.00" in body, (
            "Expected floor_price $4,000.00 in the stored price column."
        )

    def test_static_listing_price_shown(self, flask_client):
        """Static listing price (1,234.56) appears in the admin listings HTML."""
        resp = flask_client.get("/admin/dashboard")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "1,234.56" in body, (
            "Expected static listing price $1,234.56 in admin listings response."
        )

    def test_spot_badge_shown_for_spot_listing(self, flask_client):
        """A 'spot' mode badge is rendered for the premium_to_spot listing."""
        resp = flask_client.get("/admin/dashboard")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "spot" in body, (
            "Expected a 'spot' pricing-mode badge in the admin listings table."
        )

    def test_no_external_api_calls(self, flask_client):
        """Admin listings render must not trigger any external spot price API calls.

        We patch the get_current_spot_prices name in pricing_service's namespace
        (where it was imported-from). Since the admin route always passes
        spot_prices= explicitly, this should never be called.
        """
        with patch("services.pricing_service.get_current_spot_prices") as mock_api:
            resp = flask_client.get("/admin/dashboard")
            assert resp.status_code == 200
            assert mock_api.call_count == 0, (
                f"External spot API was called {mock_api.call_count} time(s) "
                "during admin listings render — this should never happen."
            )

    def test_missing_snapshot_shows_dash(self, test_db, flask_client):
        """premium_to_spot listing with no spot snapshot → effective_price=None → '—' in UI."""
        _, get_test_conn = test_db
        conn = get_test_conn()

        # Platinum category + listing (no platinum snapshot in the DB)
        conn.execute(
            "INSERT OR IGNORE INTO categories (id, bucket_id, metal, product_type, weight) "
            "VALUES (?, ?, ?, ?, ?)",
            (CAT_PLATINUM_ID, 203, "Platinum", "Bar", "1 oz"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO listings "
            "(id, seller_id, category_id, quantity, price_per_coin, active, "
            " pricing_mode, spot_premium, floor_price, pricing_metal) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (503, SELLER_UID, CAT_PLATINUM_ID, 1, 900.0, 1,
             "premium_to_spot", 50.0, 900.0, "platinum"),
        )
        conn.commit()
        conn.close()

        resp = flask_client.get("/admin/dashboard")
        assert resp.status_code == 200
        body = resp.data.decode()
        # The template renders title="No spot snapshot available" on the "—" span
        assert "No spot snapshot available" in body, (
            "Expected '—' with tooltip for a listing whose metal has no spot snapshot."
        )
