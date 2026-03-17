"""
Comprehensive autofill bid tests.

Covers all 4 pricing-mode combinations (Fixed/Variable ask × Fixed/Variable bid),
Random Year eligibility, partial fills, and spot-price sensitivity.

Tests call auto_match_bid_to_listings() and auto_match_listing_to_bids() directly
via an in-memory SQLite database — no Flask app required.

spot = 100 per oz for all tests unless noted otherwise (D3, which varies spot).
"""

import sys
import os
import sqlite3
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.blueprints.bids.auto_match import (
    auto_match_bid_to_listings,
    auto_match_listing_to_bids,
)


# ── Minimal in-memory schema ────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE spot_prices (
    metal TEXT PRIMARY KEY,
    price_usd_per_oz REAL NOT NULL
);

CREATE TABLE categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    metal       TEXT,
    product_line TEXT,
    product_type TEXT,
    weight      TEXT,
    year        TEXT,
    purity      TEXT,
    mint        TEXT,
    finish      TEXT,
    bucket_id   INTEGER DEFAULT 1,
    name        TEXT
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
    graded          INTEGER DEFAULT 0,
    grading_service TEXT
);

CREATE TABLE bids (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id         INTEGER NOT NULL,
    buyer_id            INTEGER NOT NULL,
    quantity_requested  INTEGER NOT NULL,
    price_per_coin      REAL    NOT NULL,
    remaining_quantity  INTEGER NOT NULL,
    active              INTEGER DEFAULT 1,
    requires_grading    INTEGER DEFAULT 0,
    preferred_grader    TEXT,
    delivery_address    TEXT    DEFAULT 'Test Address',
    status              TEXT    DEFAULT 'Open',
    pricing_mode        TEXT    DEFAULT 'static',
    spot_premium        REAL,
    ceiling_price       REAL,
    pricing_metal       TEXT,
    recipient_first_name TEXT   DEFAULT 'Test',
    recipient_last_name  TEXT   DEFAULT 'User',
    random_year         INTEGER DEFAULT 0,
    created_at          TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE orders (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_id            INTEGER,
    total_price         REAL,
    shipping_address    TEXT,
    status              TEXT,
    created_at          TEXT,
    recipient_first_name TEXT,
    recipient_last_name  TEXT,
    source_bid_id       INTEGER
);

CREATE TABLE order_items (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id         INTEGER,
    listing_id       INTEGER,
    quantity         INTEGER,
    price_each       REAL,
    seller_price_each REAL
);
"""


def make_db(spot=100.0):
    """Return a fresh in-memory SQLite connection with schema and spot prices."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    conn.execute(
        "INSERT INTO spot_prices (metal, price_usd_per_oz) VALUES (?, ?)",
        ("gold", spot),
    )
    conn.execute(
        "INSERT INTO spot_prices (metal, price_usd_per_oz) VALUES (?, ?)",
        ("silver", spot),
    )
    conn.commit()
    return conn


def add_category(conn, metal="Gold", product_line="American Eagle",
                 product_type="Coin", weight="1 oz", year="2023",
                 purity=".9999", mint="US Mint", finish="Bullion"):
    cur = conn.execute(
        "INSERT INTO categories (metal, product_line, product_type, weight, year,"
        " purity, mint, finish) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (metal, product_line, product_type, weight, year, purity, mint, finish),
    )
    conn.commit()
    return cur.lastrowid


def add_listing(conn, seller_id, category_id, price_per_coin, quantity=1,
                pricing_mode="static", spot_premium=0.0, floor_price=0.0,
                pricing_metal=None):
    cur = conn.execute(
        "INSERT INTO listings (seller_id, category_id, price_per_coin, quantity,"
        " active, pricing_mode, spot_premium, floor_price, pricing_metal)"
        " VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)",
        (seller_id, category_id, price_per_coin, quantity,
         pricing_mode, spot_premium, floor_price, pricing_metal),
    )
    conn.commit()
    return cur.lastrowid


def add_bid(conn, buyer_id, category_id, price_per_coin, quantity=1,
            pricing_mode="static", spot_premium=None, ceiling_price=None,
            pricing_metal=None, random_year=0):
    cur = conn.execute(
        "INSERT INTO bids (category_id, buyer_id, quantity_requested, price_per_coin,"
        " remaining_quantity, active, status, pricing_mode, spot_premium, ceiling_price,"
        " pricing_metal, random_year)"
        " VALUES (?, ?, ?, ?, ?, 1, 'Open', ?, ?, ?, ?, ?)",
        (category_id, buyer_id, quantity, price_per_coin, quantity,
         pricing_mode, spot_premium, ceiling_price, pricing_metal, random_year),
    )
    conn.commit()
    return cur.lastrowid


def orders_for(conn, buyer_id):
    return conn.execute(
        "SELECT * FROM orders WHERE buyer_id = ?", (buyer_id,)
    ).fetchall()


def order_items_for_order(conn, order_id):
    return conn.execute(
        "SELECT * FROM order_items WHERE order_id = ?", (order_id,)
    ).fetchall()


def listing_qty(conn, listing_id):
    row = conn.execute(
        "SELECT quantity FROM listings WHERE id = ?", (listing_id,)
    ).fetchone()
    return row["quantity"] if row else 0


def bid_remaining(conn, bid_id):
    row = conn.execute(
        "SELECT remaining_quantity, status FROM bids WHERE id = ?", (bid_id,)
    ).fetchone()
    return row


# ═══════════════════════════════════════════════════════════════════════════════
# A: Fixed Ask vs Fixed Bid
# ═══════════════════════════════════════════════════════════════════════════════

class TestA_FixedVsFixed:
    """A-series: Fixed ask listing matched against fixed bid."""

    # seller=1, buyer=2 throughout
    SELLER = 1
    BUYER = 2

    def test_a1_match(self):
        """A1: ask=105, bid=106 → match (1 order, 1 filled)."""
        conn = make_db()
        cat = add_category(conn)
        add_listing(conn, self.SELLER, cat, price_per_coin=105)
        bid_id = add_bid(conn, self.BUYER, cat, price_per_coin=106)

        result = auto_match_bid_to_listings(bid_id, conn.cursor())
        conn.commit()

        assert result["filled_quantity"] == 1
        assert result["orders_created"] == 1
        ords = orders_for(conn, self.BUYER)
        assert len(ords) == 1
        # buyer pays bid price, seller gets listing price
        items = order_items_for_order(conn, ords[0]["id"])
        assert items[0]["price_each"] == pytest.approx(106.0)
        assert items[0]["seller_price_each"] == pytest.approx(105.0)

    def test_a2_no_match(self):
        """A2: ask=105, bid=104 → no match."""
        conn = make_db()
        cat = add_category(conn)
        add_listing(conn, self.SELLER, cat, price_per_coin=105)
        bid_id = add_bid(conn, self.BUYER, cat, price_per_coin=104)

        result = auto_match_bid_to_listings(bid_id, conn.cursor())
        conn.commit()

        assert result["filled_quantity"] == 0
        assert result["orders_created"] == 0

    def test_a3_boundary_match(self):
        """A3: ask=105, bid=105 → match (bid == ask is a match)."""
        conn = make_db()
        cat = add_category(conn)
        add_listing(conn, self.SELLER, cat, price_per_coin=105)
        bid_id = add_bid(conn, self.BUYER, cat, price_per_coin=105)

        result = auto_match_bid_to_listings(bid_id, conn.cursor())
        conn.commit()

        assert result["filled_quantity"] == 1
        assert result["orders_created"] == 1

    def test_a4_partial_fill(self):
        """A4: listings (ask=101 qty=1), (ask=102 qty=5); bid=102 qty=4
        → fill 1 from L1 then 3 from L2; cheapest-first ordering."""
        conn = make_db()
        cat = add_category(conn)
        l1 = add_listing(conn, self.SELLER, cat, price_per_coin=101, quantity=1)
        l2 = add_listing(conn, self.SELLER, cat, price_per_coin=102, quantity=5)
        bid_id = add_bid(conn, self.BUYER, cat, price_per_coin=102, quantity=4)

        result = auto_match_bid_to_listings(bid_id, conn.cursor())
        conn.commit()

        assert result["filled_quantity"] == 4
        # Seller is the same person for both listings, so 1 consolidated order
        ords = orders_for(conn, self.BUYER)
        assert len(ords) == 1
        items = order_items_for_order(conn, ords[0]["id"])
        # Should have 2 line items: L1 (qty 1) and L2 (qty 3)
        filled_by_listing = {it["listing_id"]: it["quantity"] for it in items}
        assert filled_by_listing[l1] == 1
        assert filled_by_listing[l2] == 3
        # L2 still has 2 units left
        assert listing_qty(conn, l2) == 2
        # Bid fully filled
        bd = bid_remaining(conn, bid_id)
        assert bd["remaining_quantity"] == 0
        assert bd["status"] == "Filled"


# ═══════════════════════════════════════════════════════════════════════════════
# B: Fixed Ask vs Variable Bid (ceiling required)
# spot = 100 → effective_bid = min(spot + premium, ceiling)
# ═══════════════════════════════════════════════════════════════════════════════

class TestB_FixedAskVariableBid:
    SELLER = 1
    BUYER = 2

    def test_b1_match(self):
        """B1: ask=106, bid premium=+8 ceiling=120 → effective_bid=min(108,120)=108 ≥ 106 → match."""
        conn = make_db()
        cat = add_category(conn)
        add_listing(conn, self.SELLER, cat, price_per_coin=106)
        bid_id = add_bid(conn, self.BUYER, cat, price_per_coin=120,
                         pricing_mode="premium_to_spot",
                         spot_premium=8.0, ceiling_price=120.0,
                         pricing_metal="gold")

        result = auto_match_bid_to_listings(bid_id, conn.cursor())
        conn.commit()

        assert result["filled_quantity"] == 1
        ords = orders_for(conn, self.BUYER)
        items = order_items_for_order(conn, ords[0]["id"])
        assert items[0]["price_each"] == pytest.approx(108.0)   # buyer pays effective bid
        assert items[0]["seller_price_each"] == pytest.approx(106.0)  # seller gets listing price

    def test_b2_no_match_ceiling_binds(self):
        """B2: ask=111, bid premium=+20 ceiling=110 → effective_bid=min(120,110)=110 < 111 → no match."""
        conn = make_db()
        cat = add_category(conn)
        add_listing(conn, self.SELLER, cat, price_per_coin=111)
        bid_id = add_bid(conn, self.BUYER, cat, price_per_coin=110,
                         pricing_mode="premium_to_spot",
                         spot_premium=20.0, ceiling_price=110.0,
                         pricing_metal="gold")

        result = auto_match_bid_to_listings(bid_id, conn.cursor())
        conn.commit()

        assert result["filled_quantity"] == 0

    def test_b3_boundary_via_ceiling(self):
        """B3: ask=110, bid premium=+50 ceiling=110 → effective_bid=min(150,110)=110 = 110 → match."""
        conn = make_db()
        cat = add_category(conn)
        add_listing(conn, self.SELLER, cat, price_per_coin=110)
        bid_id = add_bid(conn, self.BUYER, cat, price_per_coin=110,
                         pricing_mode="premium_to_spot",
                         spot_premium=50.0, ceiling_price=110.0,
                         pricing_metal="gold")

        result = auto_match_bid_to_listings(bid_id, conn.cursor())
        conn.commit()

        assert result["filled_quantity"] == 1
        ords = orders_for(conn, self.BUYER)
        items = order_items_for_order(conn, ords[0]["id"])
        assert items[0]["price_each"] == pytest.approx(110.0)


# ═══════════════════════════════════════════════════════════════════════════════
# C: Variable Ask vs Fixed Bid (seller floor required)
# effective_ask = max(spot + premium, floor_price)
# ═══════════════════════════════════════════════════════════════════════════════

class TestC_VariableAskFixedBid:
    SELLER = 1
    BUYER = 2

    def test_c1_match_floor_not_binding(self):
        """C1: ask premium=+6 floor=103 → effective_ask=max(106,103)=106; bid=107 → 107≥106 → match."""
        conn = make_db()
        cat = add_category(conn)
        add_listing(conn, self.SELLER, cat, price_per_coin=0,
                    pricing_mode="premium_to_spot",
                    spot_premium=6.0, floor_price=103.0,
                    pricing_metal="gold")
        bid_id = add_bid(conn, self.BUYER, cat, price_per_coin=107)

        result = auto_match_bid_to_listings(bid_id, conn.cursor())
        conn.commit()

        assert result["filled_quantity"] == 1
        ords = orders_for(conn, self.BUYER)
        items = order_items_for_order(conn, ords[0]["id"])
        assert items[0]["price_each"] == pytest.approx(107.0)        # buyer pays fixed bid
        assert items[0]["seller_price_each"] == pytest.approx(106.0) # seller gets effective ask

    def test_c2_no_match_floor_binds_upward(self):
        """C2: ask premium=-20 floor=105 → effective_ask=max(80,105)=105; bid=104 → 104<105 → no match."""
        conn = make_db()
        cat = add_category(conn)
        add_listing(conn, self.SELLER, cat, price_per_coin=0,
                    pricing_mode="premium_to_spot",
                    spot_premium=-20.0, floor_price=105.0,
                    pricing_metal="gold")
        bid_id = add_bid(conn, self.BUYER, cat, price_per_coin=104)

        result = auto_match_bid_to_listings(bid_id, conn.cursor())
        conn.commit()

        assert result["filled_quantity"] == 0

    def test_c3_boundary_at_floor(self):
        """C3: ask premium=-50 floor=95 → effective_ask=max(50,95)=95; bid=95 → 95≥95 → match."""
        conn = make_db()
        cat = add_category(conn)
        add_listing(conn, self.SELLER, cat, price_per_coin=0,
                    pricing_mode="premium_to_spot",
                    spot_premium=-50.0, floor_price=95.0,
                    pricing_metal="gold")
        bid_id = add_bid(conn, self.BUYER, cat, price_per_coin=95)

        result = auto_match_bid_to_listings(bid_id, conn.cursor())
        conn.commit()

        assert result["filled_quantity"] == 1
        ords = orders_for(conn, self.BUYER)
        items = order_items_for_order(conn, ords[0]["id"])
        assert items[0]["seller_price_each"] == pytest.approx(95.0)


# ═══════════════════════════════════════════════════════════════════════════════
# D: Variable Ask vs Variable Bid (floor + ceiling)
# ═══════════════════════════════════════════════════════════════════════════════

class TestD_VariableAskVariableBid:
    SELLER = 1
    BUYER = 2

    def test_d1_match(self):
        """D1: ask +5 floor=104 → effective_ask=105; bid +7 ceiling=110 → effective_bid=107; 107≥105 → match."""
        conn = make_db()
        cat = add_category(conn)
        add_listing(conn, self.SELLER, cat, price_per_coin=0,
                    pricing_mode="premium_to_spot",
                    spot_premium=5.0, floor_price=104.0, pricing_metal="gold")
        bid_id = add_bid(conn, self.BUYER, cat, price_per_coin=110,
                         pricing_mode="premium_to_spot",
                         spot_premium=7.0, ceiling_price=110.0, pricing_metal="gold")

        result = auto_match_bid_to_listings(bid_id, conn.cursor())
        conn.commit()

        assert result["filled_quantity"] == 1
        ords = orders_for(conn, self.BUYER)
        items = order_items_for_order(conn, ords[0]["id"])
        assert items[0]["price_each"] == pytest.approx(107.0)
        assert items[0]["seller_price_each"] == pytest.approx(105.0)

    def test_d2_no_match_ceiling_blocks(self):
        """D2: ask +15 floor=110 → effective_ask=115; bid +30 ceiling=112 → effective_bid=112; 112<115 → no match."""
        conn = make_db()
        cat = add_category(conn)
        add_listing(conn, self.SELLER, cat, price_per_coin=0,
                    pricing_mode="premium_to_spot",
                    spot_premium=15.0, floor_price=110.0, pricing_metal="gold")
        bid_id = add_bid(conn, self.BUYER, cat, price_per_coin=112,
                         pricing_mode="premium_to_spot",
                         spot_premium=30.0, ceiling_price=112.0, pricing_metal="gold")

        result = auto_match_bid_to_listings(bid_id, conn.cursor())
        conn.commit()

        assert result["filled_quantity"] == 0

    def test_d3_spot_sensitivity(self):
        """D3: same premiums/floor/ceiling, vary spot to confirm match outcome changes.

        Setup (same as D1): ask +5 floor=104, bid +7 ceiling=110, pricing_metal=gold.
          spot=95:  effective_ask=max(100,104)=104, effective_bid=min(102,110)=102 → NO match
          spot=100: effective_ask=max(105,104)=105, effective_bid=min(107,110)=107 → match
          spot=110: effective_ask=max(115,104)=115, effective_bid=min(117,110)=110 → NO match
        """
        ASK_PREMIUM = 5.0
        ASK_FLOOR = 104.0
        BID_PREMIUM = 7.0
        BID_CEILING = 110.0

        for spot, expect_match in [(95, False), (100, True), (110, False)]:
            conn = make_db(spot=float(spot))
            cat = add_category(conn)
            add_listing(conn, self.SELLER, cat, price_per_coin=0,
                        pricing_mode="premium_to_spot",
                        spot_premium=ASK_PREMIUM, floor_price=ASK_FLOOR,
                        pricing_metal="gold")
            bid_id = add_bid(conn, self.BUYER, cat, price_per_coin=BID_CEILING,
                             pricing_mode="premium_to_spot",
                             spot_premium=BID_PREMIUM, ceiling_price=BID_CEILING,
                             pricing_metal="gold")

            result = auto_match_bid_to_listings(bid_id, conn.cursor())
            conn.commit()

            if expect_match:
                assert result["filled_quantity"] == 1, (
                    f"Expected match at spot={spot} but got none"
                )
            else:
                assert result["filled_quantity"] == 0, (
                    f"Expected no match at spot={spot} but got {result['filled_quantity']}"
                )


# ═══════════════════════════════════════════════════════════════════════════════
# E: Random Year eligibility
# Two listings: L1 (year=2019, ask=105), L2 (year=2020, ask=104), same other specs.
# ═══════════════════════════════════════════════════════════════════════════════

class TestE_RandomYear:
    SELLER = 1
    BUYER = 2

    # Shared category specs (year differs)
    CAT_KWARGS = dict(
        metal="Gold", product_line="Buffalo", product_type="Coin",
        weight="1 oz", purity=".9999", mint="US Mint", finish="Bullion"
    )

    def _setup(self, conn):
        """Insert two categories differing only by year, plus their listings."""
        cat_2019 = add_category(conn, year="2019", **self.CAT_KWARGS)
        cat_2020 = add_category(conn, year="2020", **self.CAT_KWARGS)
        l1 = add_listing(conn, self.SELLER, cat_2019, price_per_coin=105)
        l2 = add_listing(conn, self.SELLER, cat_2020, price_per_coin=104)
        return cat_2019, cat_2020, l1, l2

    def test_e1_random_year_off_only_exact_year(self):
        """E1: random_year=OFF, bid specifies year=2019.
        Only L1 (2019) is eligible; L2 (2020) excluded even though cheaper."""
        conn = make_db()
        cat_2019, cat_2020, l1, l2 = self._setup(conn)

        # Bid placed on 2019 category, random_year=0
        bid_id = add_bid(conn, self.BUYER, cat_2019, price_per_coin=110,
                         random_year=0)

        result = auto_match_bid_to_listings(bid_id, conn.cursor())
        conn.commit()

        assert result["filled_quantity"] == 1
        ords = orders_for(conn, self.BUYER)
        items = order_items_for_order(conn, ords[0]["id"])
        # Must have filled L1, not L2
        assert items[0]["listing_id"] == l1
        # L2 untouched
        assert listing_qty(conn, l2) == 1

    def test_e2_random_year_on_both_eligible_fills_cheapest(self):
        """E2: random_year=ON, bid qty=1.
        Both L1 and L2 eligible; autofill picks L2 first (lower ask=104)."""
        conn = make_db()
        cat_2019, cat_2020, l1, l2 = self._setup(conn)

        # Bid placed on 2019 category but random_year=1 → both years eligible
        bid_id = add_bid(conn, self.BUYER, cat_2019, price_per_coin=110,
                         random_year=1)

        result = auto_match_bid_to_listings(bid_id, conn.cursor())
        conn.commit()

        assert result["filled_quantity"] == 1
        ords = orders_for(conn, self.BUYER)
        items = order_items_for_order(conn, ords[0]["id"])
        # L2 (ask=104) is cheapest → filled first
        assert items[0]["listing_id"] == l2
        assert items[0]["seller_price_each"] == pytest.approx(104.0)
        # L1 untouched
        assert listing_qty(conn, l1) == 1

    def test_e3_random_year_on_partial_fill(self):
        """E3: random_year=ON, L2 qty=1 at 104, L1 qty=5 at 105, bid qty=3.
        Fill: 1 from L2 (cheapest), then 2 from L1."""
        conn = make_db()
        cat_2019, cat_2020, _, _ = self._setup(conn)

        # Override quantities via fresh listings
        conn.execute("DELETE FROM listings")
        l1 = add_listing(conn, self.SELLER, cat_2019, price_per_coin=105, quantity=5)
        l2 = add_listing(conn, self.SELLER, cat_2020, price_per_coin=104, quantity=1)
        conn.commit()

        bid_id = add_bid(conn, self.BUYER, cat_2019, price_per_coin=110,
                         quantity=3, random_year=1)

        result = auto_match_bid_to_listings(bid_id, conn.cursor())
        conn.commit()

        assert result["filled_quantity"] == 3
        ords = orders_for(conn, self.BUYER)
        # Seller is same user → 1 consolidated order
        assert len(ords) == 1
        items = order_items_for_order(conn, ords[0]["id"])
        filled = {it["listing_id"]: it["quantity"] for it in items}
        assert filled[l2] == 1  # cheap one exhausted
        assert filled[l1] == 2  # remainder from expensive one
        # L1 should have 3 remaining (5 - 2)
        assert listing_qty(conn, l1) == 3
        # L2 exhausted
        assert listing_qty(conn, l2) == 0

    def test_e4_random_year_on_other_specs_still_filter(self):
        """E4: random_year=ON but different metal → no match.
        Random Year only relaxes year constraint; other specs still apply."""
        conn = make_db()
        cat_2019, _, _, _ = self._setup(conn)

        # Add a Silver category (different metal) with same non-metal specs
        silver_cat = add_category(conn, metal="Silver", year="2021",
                                  product_line="Buffalo", product_type="Coin",
                                  weight="1 oz", purity=".999",
                                  mint="US Mint", finish="Bullion")
        add_listing(conn, self.SELLER, silver_cat, price_per_coin=90)

        # Bid is for Gold cat, random_year=1 — should NOT match the Silver listing
        bid_id = add_bid(conn, self.BUYER, cat_2019, price_per_coin=110,
                         random_year=1)

        result = auto_match_bid_to_listings(bid_id, conn.cursor())
        conn.commit()

        # Only Gold listings are eligible; the Silver one should not be touched
        silver_qty = listing_qty(conn, conn.execute(
            "SELECT id FROM listings WHERE category_id = ?", (silver_cat,)
        ).fetchone()["id"])
        assert silver_qty == 1  # untouched

    def test_e5_random_year_reverse_match_listing_to_bids(self):
        """E5: Reverse direction — new listing in 2020 category triggers auto_match_listing_to_bids.
        A bid placed on the 2019 category with random_year=ON should fill from the 2020 listing."""
        conn = make_db()
        cat_2019 = add_category(conn, year="2019", **self.CAT_KWARGS)
        cat_2020 = add_category(conn, year="2020", **self.CAT_KWARGS)

        # Place a bid on 2019 category with random_year=1 (no listings exist yet)
        bid_id = add_bid(conn, self.BUYER, cat_2019, price_per_coin=110,
                         random_year=1)

        # New listing added to 2020 category → should trigger reverse match
        l2020 = add_listing(conn, self.SELLER, cat_2020, price_per_coin=104)

        result = auto_match_listing_to_bids(l2020, conn.cursor())
        conn.commit()

        assert result["filled_quantity"] == 1
        bd = bid_remaining(conn, bid_id)
        assert bd["remaining_quantity"] == 0
        assert bd["status"] == "Filled"

    def test_e6_random_year_off_reverse_match_no_cross_year(self):
        """E6: Reverse direction — bid on 2019 with random_year=OFF.
        A new listing in 2020 category must NOT fill it."""
        conn = make_db()
        cat_2019 = add_category(conn, year="2019", **self.CAT_KWARGS)
        cat_2020 = add_category(conn, year="2020", **self.CAT_KWARGS)

        bid_id = add_bid(conn, self.BUYER, cat_2019, price_per_coin=110,
                         random_year=0)

        l2020 = add_listing(conn, self.SELLER, cat_2020, price_per_coin=104)

        result = auto_match_listing_to_bids(l2020, conn.cursor())
        conn.commit()

        assert result["filled_quantity"] == 0
        bd = bid_remaining(conn, bid_id)
        assert bd["remaining_quantity"] == 1  # bid still open


# ═══════════════════════════════════════════════════════════════════════════════
# Self-match prevention
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoSelfMatch:
    def test_no_self_match_bid_to_listing(self):
        """A buyer cannot fill their own listing via autofill."""
        conn = make_db()
        cat = add_category(conn)
        same_user = 1
        add_listing(conn, same_user, cat, price_per_coin=100)
        bid_id = add_bid(conn, same_user, cat, price_per_coin=200)

        result = auto_match_bid_to_listings(bid_id, conn.cursor())
        conn.commit()

        assert result["filled_quantity"] == 0

    def test_no_self_match_listing_to_bid(self):
        """A seller cannot fill their own bid via autofill (reverse direction)."""
        conn = make_db()
        cat = add_category(conn)
        same_user = 1
        bid_id = add_bid(conn, same_user, cat, price_per_coin=200)
        listing_id = add_listing(conn, same_user, cat, price_per_coin=100)

        result = auto_match_listing_to_bids(listing_id, conn.cursor())
        conn.commit()

        assert result["filled_quantity"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Grading is NOT a matching constraint
# ═══════════════════════════════════════════════════════════════════════════════

class TestGradingNotAConstraint:
    SELLER = 1
    BUYER = 2

    def test_bid_requiring_grading_matches_ungraded_listing(self):
        """A bid with requires_grading=1 must still match an ungraded listing.
        Grading is handled post-match (e.g., during fulfillment), not as an eligibility filter."""
        conn = make_db()
        cat = add_category(conn)
        # Listing is NOT graded
        conn.execute(
            "INSERT INTO listings (seller_id, category_id, price_per_coin, quantity,"
            " active, graded) VALUES (?, ?, 100, 1, 1, 0)",
            (self.SELLER, cat),
        )
        listing_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()

        bid_id = add_bid(conn, self.BUYER, cat, price_per_coin=110)
        conn.execute(
            "UPDATE bids SET requires_grading = 1 WHERE id = ?", (bid_id,)
        )
        conn.commit()

        result = auto_match_bid_to_listings(bid_id, conn.cursor())
        conn.commit()

        # Grading should NOT block the match
        assert result["filled_quantity"] == 1
