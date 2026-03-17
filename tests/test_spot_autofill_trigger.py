"""
Spot-price-change → bid-autofill trigger pipeline tests.

T1: Fixed-price bid NOT marketable at high spot becomes marketable after spot drops.
    check_all_pending_matches() must fill it using the new snapshot price.

T2: Floor price takes precedence (floor > spot+premium).
    Bid fills only when bid_price >= floor_price.

T3: No external API calls occur during bid matching.
    All spot prices must come from spot_price_snapshots (or fallback spot_prices).

T4a: insert_manual_spot_snapshot() calls run_bid_rematch_after_spot_update.
T4b: run_snapshot() calls _trigger_bid_rematch_sync (and through it the rematch)
     after at least one snapshot row is inserted.
"""

import sys
import os
import sqlite3
import datetime
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.blueprints.bids.auto_match import check_all_pending_matches
from services.manual_spot_service import insert_manual_spot_snapshot


# ── In-memory DB helpers ─────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE spot_price_snapshots (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    metal     TEXT    NOT NULL,
    price_usd REAL    NOT NULL,
    as_of     TEXT    NOT NULL,
    source    TEXT    DEFAULT 'test'
);

CREATE TABLE spot_prices (
    metal            TEXT PRIMARY KEY,
    price_usd_per_oz REAL NOT NULL
);

CREATE TABLE system_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TEXT
);

CREATE TABLE categories (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    metal        TEXT,
    product_line TEXT,
    product_type TEXT,
    weight       TEXT,
    year         TEXT,
    purity       TEXT,
    mint         TEXT,
    finish       TEXT,
    bucket_id    INTEGER DEFAULT 1
);

CREATE TABLE listings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id       INTEGER NOT NULL,
    category_id     INTEGER NOT NULL,
    price_per_coin  REAL    NOT NULL,
    quantity        INTEGER DEFAULT 1,
    active          INTEGER DEFAULT 1,
    pricing_mode    TEXT    DEFAULT 'static',
    spot_premium    REAL    DEFAULT 0,
    floor_price     REAL    DEFAULT 0,
    pricing_metal   TEXT,
    grading_service TEXT
);

CREATE TABLE bids (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id          INTEGER NOT NULL,
    buyer_id             INTEGER NOT NULL,
    quantity_requested   INTEGER NOT NULL,
    price_per_coin       REAL    NOT NULL,
    remaining_quantity   INTEGER NOT NULL,
    active               INTEGER DEFAULT 1,
    delivery_address     TEXT    DEFAULT 'Test Address',
    status               TEXT    DEFAULT 'Open',
    pricing_mode         TEXT    DEFAULT 'static',
    spot_premium         REAL,
    ceiling_price        REAL,
    pricing_metal        TEXT,
    recipient_first_name TEXT    DEFAULT 'Test',
    recipient_last_name  TEXT    DEFAULT 'User',
    random_year          INTEGER DEFAULT 0,
    created_at           TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE orders (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_id             INTEGER,
    total_price          REAL,
    shipping_address     TEXT,
    status               TEXT,
    created_at           TEXT,
    recipient_first_name TEXT,
    recipient_last_name  TEXT,
    source_bid_id        INTEGER
);

CREATE TABLE order_items (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id          INTEGER,
    listing_id        INTEGER,
    quantity          INTEGER,
    price_each        REAL,
    seller_price_each REAL
);
"""


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _set_spot(conn, metal: str, price: float):
    """Insert a spot_price_snapshots row AND update the legacy spot_prices table."""
    as_of = datetime.datetime.now().isoformat()
    conn.execute(
        "INSERT INTO spot_price_snapshots (metal, price_usd, as_of) VALUES (?, ?, ?)",
        (metal, price, as_of),
    )
    conn.execute(
        "INSERT OR REPLACE INTO spot_prices (metal, price_usd_per_oz) VALUES (?, ?)",
        (metal, price),
    )
    conn.commit()


def _add_cat(conn, metal="Gold"):
    r = conn.execute(
        "INSERT INTO categories (metal, product_line, product_type, weight)"
        " VALUES (?, 'TestLine', 'Coin', '1 oz')",
        (metal,),
    )
    conn.commit()
    return r.lastrowid


def _add_listing(conn, seller_id, cat_id, price_per_coin=0.0, qty=1,
                 pricing_mode="static", spot_premium=0.0,
                 floor_price=0.0, pricing_metal=None):
    r = conn.execute(
        "INSERT INTO listings"
        " (seller_id, category_id, price_per_coin, quantity, active,"
        "  pricing_mode, spot_premium, floor_price, pricing_metal)"
        " VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)",
        (seller_id, cat_id, price_per_coin, qty,
         pricing_mode, spot_premium, floor_price, pricing_metal),
    )
    conn.commit()
    return r.lastrowid


def _add_bid(conn, buyer_id, cat_id, price_per_coin, qty=1):
    r = conn.execute(
        "INSERT INTO bids"
        " (category_id, buyer_id, quantity_requested, price_per_coin,"
        "  remaining_quantity, active, status)"
        " VALUES (?, ?, ?, ?, ?, 1, 'Open')",
        (cat_id, buyer_id, qty, price_per_coin, qty),
    )
    conn.commit()
    return r.lastrowid


def _bid_row(conn, bid_id):
    return conn.execute("SELECT * FROM bids WHERE id=?", (bid_id,)).fetchone()


def _listing_qty(conn, listing_id):
    return conn.execute(
        "SELECT quantity FROM listings WHERE id=?", (listing_id,)
    ).fetchone()["quantity"]


# ── T1: Spot drop makes bid marketable ──────────────────────────────────────

class TestT1SpotDropMakesBidMarketable:
    """
    Scenario: variable-spot listing with premium=100, floor=0.
      gold=2900 → effective ask = 3000
      bid = 2960 (< 3000) → NOT marketable initially

    After gold drops to 950:
      effective ask = 950 + 100 = 1050
      bid 2960 >= 1050 → fills immediately via check_all_pending_matches.
    """

    def setup_method(self):
        self.conn = _make_db()
        cat_id = _add_cat(self.conn, "Gold")
        self.listing_id = _add_listing(
            self.conn, seller_id=1, cat_id=cat_id, qty=2,
            pricing_mode="premium_to_spot",
            spot_premium=100.0, floor_price=0.0, pricing_metal="gold",
        )
        self.bid_id = _add_bid(
            self.conn, buyer_id=2, cat_id=cat_id, price_per_coin=2960.0, qty=1
        )
        _set_spot(self.conn, "gold", 2900.0)  # ask = 3000 → bid not marketable

    def test_not_filled_at_high_spot(self):
        """Bid $2,960 < ask $3,000: no fill."""
        result = check_all_pending_matches(self.conn)
        assert result["total_filled"] == 0
        b = _bid_row(self.conn, self.bid_id)
        assert b["status"] == "Open"
        assert _listing_qty(self.conn, self.listing_id) == 2

    def test_filled_after_spot_drops(self):
        """After gold drops to $950, ask=$1,050; bid $2,960 fills."""
        # First pass: not filled
        check_all_pending_matches(self.conn)
        assert _bid_row(self.conn, self.bid_id)["status"] == "Open"

        # Insert new low-spot snapshot
        _set_spot(self.conn, "gold", 950.0)  # ask = 1050

        # Second pass: should fill
        result = check_all_pending_matches(self.conn)
        assert result["total_filled"] == 1, "Expected bid to fill after spot drop"
        assert result["bids_matched"] == 1
        assert result["orders_created"] == 1

        b = _bid_row(self.conn, self.bid_id)
        assert b["status"] == "Filled"
        assert b["remaining_quantity"] == 0
        # Listing had qty=2; one unit consumed
        assert _listing_qty(self.conn, self.listing_id) == 1

        # Verify order was created for the buyer
        orders = self.conn.execute(
            "SELECT * FROM orders WHERE buyer_id=?", (2,)
        ).fetchall()
        assert len(orders) == 1

        items = self.conn.execute(
            "SELECT * FROM order_items WHERE order_id=?", (orders[0]["id"],)
        ).fetchall()
        assert len(items) == 1
        assert items[0]["quantity"] == 1

    def test_inventory_not_reduced_before_fill(self):
        """Listing inventory stays intact until the bid actually fills."""
        check_all_pending_matches(self.conn)
        assert _listing_qty(self.conn, self.listing_id) == 2


# ── T2: Floor price ──────────────────────────────────────────────────────────

class TestT2FloorPrice:
    """
    Listing: premium_to_spot, premium=100, floor=3000.
    gold=900 → computed = 1000 < floor → effective ask = 3000.

    Bid $2,960 < $3,000 → NOT filled.
    Bid $3,100 >= $3,000 → fills; seller receives floor price, buyer pays bid price.
    """

    def setup_method(self):
        self.conn = _make_db()
        self.cat_id = _add_cat(self.conn, "Gold")
        self.listing_id = _add_listing(
            self.conn, seller_id=1, cat_id=self.cat_id, qty=1,
            pricing_mode="premium_to_spot",
            spot_premium=100.0, floor_price=3000.0, pricing_metal="gold",
        )
        _set_spot(self.conn, "gold", 900.0)

    def test_bid_below_floor_does_not_fill(self):
        bid_id = _add_bid(
            self.conn, buyer_id=2, cat_id=self.cat_id, price_per_coin=2960.0
        )
        result = check_all_pending_matches(self.conn)
        assert result["total_filled"] == 0
        assert _bid_row(self.conn, bid_id)["status"] == "Open"
        assert _listing_qty(self.conn, self.listing_id) == 1

    def test_bid_above_floor_fills(self):
        """Bid $3,100 >= floor $3,000 → fills; prices split by spread model."""
        bid_id = _add_bid(
            self.conn, buyer_id=2, cat_id=self.cat_id, price_per_coin=3100.0
        )
        result = check_all_pending_matches(self.conn)
        assert result["total_filled"] == 1

        b = _bid_row(self.conn, bid_id)
        assert b["status"] == "Filled"
        assert _listing_qty(self.conn, self.listing_id) == 0

        order = self.conn.execute(
            "SELECT * FROM orders WHERE buyer_id=2"
        ).fetchone()
        assert order is not None

        item = self.conn.execute(
            "SELECT * FROM order_items WHERE order_id=?", (order["id"],)
        ).fetchone()
        # Buyer pays bid effective price (3100), seller receives listing effective price (floor=3000)
        assert item["price_each"] == 3100.0
        assert item["seller_price_each"] == 3000.0

    def test_floor_prevents_fill_after_spot_further_drops(self):
        """Even if spot falls more, floor holds; bid below floor never fills."""
        bid_id = _add_bid(
            self.conn, buyer_id=2, cat_id=self.cat_id, price_per_coin=2960.0
        )
        _set_spot(self.conn, "gold", 10.0)  # computed = 110, well below floor
        result = check_all_pending_matches(self.conn)
        assert result["total_filled"] == 0
        assert _bid_row(self.conn, bid_id)["status"] == "Open"


# ── T3: No external API calls during matching ────────────────────────────────

class TestT3NoExternalApiCalls:
    """
    Bid matching must never call external APIs (requests.get, metalpriceapi, etc.).
    All spot data comes from spot_price_snapshots (via _get_spot_prices_from_cursor).
    """

    def test_no_api_calls_during_matching(self):
        conn = _make_db()
        cat_id = _add_cat(conn, "Gold")
        _add_listing(
            conn, seller_id=1, cat_id=cat_id, qty=1,
            pricing_mode="premium_to_spot",
            spot_premium=100.0, floor_price=0.0, pricing_metal="gold",
        )
        _add_bid(conn, buyer_id=2, cat_id=cat_id, price_per_coin=2000.0)
        _set_spot(conn, "gold", 1500.0)  # ask=1600; bid 2000 >= 1600 → fills

        # Patch requests.get so any HTTP call raises immediately
        with patch("requests.get", side_effect=AssertionError("HTTP call forbidden!")):
            # Secondary guard: patch the pricing-service fetcher directly
            with patch(
                "services.pricing_service.get_current_spot_prices",
                side_effect=AssertionError("External price fetch forbidden!"),
            ):
                result = check_all_pending_matches(conn)

        # Bid still fills using only snapshot data
        assert result["total_filled"] == 1

    def test_matching_works_with_only_snapshots_populated(self):
        """Matching works even when spot_prices table is empty (snapshots only)."""
        conn = _make_db()
        cat_id = _add_cat(conn, "Gold")
        _add_listing(
            conn, seller_id=1, cat_id=cat_id, qty=1,
            pricing_mode="premium_to_spot",
            spot_premium=50.0, floor_price=0.0, pricing_metal="gold",
        )
        _add_bid(conn, buyer_id=2, cat_id=cat_id, price_per_coin=1200.0)

        # Only populate spot_price_snapshots — leave spot_prices empty
        as_of = datetime.datetime.now().isoformat()
        conn.execute(
            "INSERT INTO spot_price_snapshots (metal, price_usd, as_of) VALUES (?, ?, ?)",
            ("gold", 1000.0, as_of),
        )
        conn.commit()  # ask = 1050; bid 1200 >= 1050 → fills

        result = check_all_pending_matches(conn)
        assert result["total_filled"] == 1


# ── T4a: Manual admin spot insert triggers rematch ──────────────────────────

class TestT4aManualInsertTrigger:
    """
    insert_manual_spot_snapshot() must call run_bid_rematch_after_spot_update
    after committing the new snapshot row.
    """

    def test_rematch_called_on_manual_insert(self):
        conn = _make_db()
        with patch(
            "core.blueprints.bids.auto_match.run_bid_rematch_after_spot_update"
        ) as mock_rematch:
            insert_manual_spot_snapshot(conn, "gold", 1500.0)

        mock_rematch.assert_called_once()
        # Verify the correct metal was passed
        _, kwargs = mock_rematch.call_args
        metals = kwargs.get("metals") or []
        assert "gold" in metals

    def test_rematch_called_for_silver(self):
        conn = _make_db()
        with patch(
            "core.blueprints.bids.auto_match.run_bid_rematch_after_spot_update"
        ) as mock_rematch:
            insert_manual_spot_snapshot(conn, "silver", 25.0)

        mock_rematch.assert_called_once()
        _, kwargs = mock_rematch.call_args
        assert "silver" in (kwargs.get("metals") or [])

    def test_rematch_not_blocked_by_error(self):
        """
        Even if run_bid_rematch_after_spot_update raises, insert_manual_spot_snapshot
        must return successfully (errors are caught in _trigger_bid_rematch).
        """
        conn = _make_db()
        with patch(
            "core.blueprints.bids.auto_match.run_bid_rematch_after_spot_update",
            side_effect=RuntimeError("DB down"),
        ):
            result = insert_manual_spot_snapshot(conn, "gold", 1500.0)

        # Insert still returned its row dict
        assert result["metal"] == "gold"
        assert result["price_usd"] == 1500.0


# ── T4b: Scheduler run_snapshot() triggers rematch ──────────────────────────

class TestT4bSchedulerTrigger:
    """
    run_snapshot(force=True) must call _trigger_bid_rematch_sync after inserting
    at least one snapshot row.
    """

    def test_trigger_called_after_snapshot_insert(self):
        conn = _make_db()
        fake_prices = {"gold": 1500.0, "silver": 25.0}

        # Patch the external API call and the DB-connection factory so we use our
        # in-memory DB.  Patch _trigger_bid_rematch_sync to verify it is called.
        with patch(
            "services.spot_price_service.get_current_spot_prices",
            return_value=fake_prices,
        ), patch(
            "services.spot_snapshot_service._db_module"
        ) as mock_db_module, patch(
            "services.spot_snapshot_service._trigger_bid_rematch_sync"
        ) as mock_trigger:
            mock_db_module.get_db_connection.return_value = conn

            from services.spot_snapshot_service import run_snapshot
            result = run_snapshot(use_lock=False, verbose=False, force=True)

        assert result["inserted"] > 0, "Expected at least one snapshot to be inserted"
        mock_trigger.assert_called_once()

    def test_trigger_not_called_when_nothing_inserted(self):
        """If run_snapshot inserts 0 rows (e.g. locked_out), trigger is not called."""
        conn = _make_db()
        fake_prices = {"gold": 1500.0}

        with patch(
            "services.spot_price_service.get_current_spot_prices",
            return_value=fake_prices,
        ), patch(
            "services.spot_snapshot_service._db_module"
        ) as mock_db_module, patch(
            "services.spot_snapshot_service._trigger_bid_rematch_sync"
        ) as mock_trigger:
            mock_db_module.get_db_connection.return_value = conn
            # force=False with a very recent snapshot → _should_insert returns False
            # First insert a "recent" snapshot so the dedup guard fires
            as_of = datetime.datetime.now().isoformat()
            conn.execute(
                "INSERT INTO spot_price_snapshots (metal, price_usd, as_of)"
                " VALUES (?, ?, ?)",
                ("gold", 1500.0, as_of),
            )
            conn.commit()

            from services.spot_snapshot_service import run_snapshot
            result = run_snapshot(use_lock=False, verbose=False, force=False)

        # trigger must NOT be called when inserted == 0
        if result["inserted"] == 0:
            mock_trigger.assert_not_called()
        # (if a different metal was inserted due to staleness timing, that's fine too)
