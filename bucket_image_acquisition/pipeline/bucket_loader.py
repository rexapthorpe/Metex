"""
Bucket loader — provides standard_bucket dicts to the pipeline.

Priority order:
  1. Live Metex PostgreSQL database (if DATABASE_URL is set and connectable)
  2. Local cache file: data/buckets.json (seeded by scripts/sync_buckets.py)
  3. Built-in fallback seed (all 64 products hardcoded)

The returned dicts match the standard_buckets table schema.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "buckets.json"

# ---------------------------------------------------------------------------
# Built-in fallback seed
# (matches scripts/seed_standard_buckets.py in the main Metex project)
# ---------------------------------------------------------------------------

_SEED_BUCKETS: List[Dict] = [
    # ── Gold Eagles ─────────────────────────────────────────────────────────
    {"id": 1,  "slug": "gold-american-eagle-1oz",         "title": "1 oz Gold American Eagle",
     "metal": "gold",  "form": "coin",  "weight": "1 oz",  "weight_oz": 1.0,
     "mint": "US Mint",  "product_family": "American Eagle",  "product_series": "American Eagle",
     "year_policy": "varies",  "purity": ".9167",  "denomination": "$50"},

    {"id": 2,  "slug": "gold-american-eagle-half-oz",     "title": "1/2 oz Gold American Eagle",
     "metal": "gold",  "form": "coin",  "weight": "1/2 oz",  "weight_oz": 0.5,
     "mint": "US Mint",  "product_family": "American Eagle",  "year_policy": "varies",
     "purity": ".9167",  "denomination": "$25"},

    {"id": 3,  "slug": "gold-american-eagle-quarter-oz",  "title": "1/4 oz Gold American Eagle",
     "metal": "gold",  "form": "coin",  "weight": "1/4 oz",  "weight_oz": 0.25,
     "mint": "US Mint",  "product_family": "American Eagle",  "year_policy": "varies",
     "purity": ".9167",  "denomination": "$10"},

    {"id": 4,  "slug": "gold-american-eagle-tenth-oz",    "title": "1/10 oz Gold American Eagle",
     "metal": "gold",  "form": "coin",  "weight": "1/10 oz",  "weight_oz": 0.1,
     "mint": "US Mint",  "product_family": "American Eagle",  "year_policy": "varies",
     "purity": ".9167",  "denomination": "$5"},

    {"id": 5,  "slug": "gold-american-buffalo-1oz",       "title": "1 oz Gold American Buffalo",
     "metal": "gold",  "form": "coin",  "weight": "1 oz",  "weight_oz": 1.0,
     "mint": "US Mint",  "product_family": "American Buffalo",  "year_policy": "varies",
     "purity": ".9999",  "denomination": "$50"},

    # ── Gold Maples ──────────────────────────────────────────────────────────
    {"id": 6,  "slug": "gold-canadian-maple-leaf-1oz",    "title": "1 oz Gold Maple Leaf",
     "metal": "gold",  "form": "coin",  "weight": "1 oz",  "weight_oz": 1.0,
     "mint": "Royal Canadian Mint",  "product_family": "Maple Leaf",  "year_policy": "varies",
     "purity": ".9999"},

    {"id": 7,  "slug": "gold-canadian-maple-leaf-half-oz","title": "1/2 oz Gold Maple Leaf",
     "metal": "gold",  "form": "coin",  "weight": "1/2 oz",  "weight_oz": 0.5,
     "mint": "Royal Canadian Mint",  "product_family": "Maple Leaf",  "year_policy": "varies",
     "purity": ".9999"},

    {"id": 8,  "slug": "gold-canadian-maple-leaf-quarter-oz","title": "1/4 oz Gold Maple Leaf",
     "metal": "gold",  "form": "coin",  "weight": "1/4 oz",  "weight_oz": 0.25,
     "mint": "Royal Canadian Mint",  "product_family": "Maple Leaf",  "year_policy": "varies",
     "purity": ".9999"},

    {"id": 9,  "slug": "gold-canadian-maple-leaf-tenth-oz","title": "1/10 oz Gold Maple Leaf",
     "metal": "gold",  "form": "coin",  "weight": "1/10 oz",  "weight_oz": 0.1,
     "mint": "Royal Canadian Mint",  "product_family": "Maple Leaf",  "year_policy": "varies",
     "purity": ".9999"},

    # ── Gold Krugerrands ──────────────────────────────────────────────────────
    {"id": 10, "slug": "gold-krugerrand-1oz",             "title": "1 oz Gold Krugerrand",
     "metal": "gold",  "form": "coin",  "weight": "1 oz",  "weight_oz": 1.0,
     "mint": "South African Mint",  "product_family": "Krugerrand",  "year_policy": "varies",
     "purity": ".9167"},

    {"id": 11, "slug": "gold-krugerrand-half-oz",         "title": "1/2 oz Gold Krugerrand",
     "metal": "gold",  "form": "coin",  "weight": "1/2 oz",  "weight_oz": 0.5,
     "mint": "South African Mint",  "product_family": "Krugerrand",  "year_policy": "varies",
     "purity": ".9167"},

    {"id": 12, "slug": "gold-krugerrand-quarter-oz",      "title": "1/4 oz Gold Krugerrand",
     "metal": "gold",  "form": "coin",  "weight": "1/4 oz",  "weight_oz": 0.25,
     "mint": "South African Mint",  "product_family": "Krugerrand",  "year_policy": "varies",
     "purity": ".9167"},

    {"id": 13, "slug": "gold-krugerrand-tenth-oz",        "title": "1/10 oz Gold Krugerrand",
     "metal": "gold",  "form": "coin",  "weight": "1/10 oz",  "weight_oz": 0.1,
     "mint": "South African Mint",  "product_family": "Krugerrand",  "year_policy": "varies",
     "purity": ".9167"},

    # ── Gold Philharmonics ────────────────────────────────────────────────────
    {"id": 14, "slug": "gold-austrian-philharmonic-1oz",  "title": "1 oz Gold Austrian Philharmonic",
     "metal": "gold",  "form": "coin",  "weight": "1 oz",  "weight_oz": 1.0,
     "mint": "Austrian Mint",  "product_family": "Philharmonic",  "year_policy": "varies",
     "purity": ".9999"},

    # ── Gold Kangaroos ────────────────────────────────────────────────────────
    {"id": 15, "slug": "gold-australian-kangaroo-1oz",    "title": "1 oz Gold Kangaroo",
     "metal": "gold",  "form": "coin",  "weight": "1 oz",  "weight_oz": 1.0,
     "mint": "Perth Mint",  "product_family": "Kangaroo",  "year_policy": "varies",
     "purity": ".9999"},

    {"id": 16, "slug": "gold-australian-kangaroo-half-oz","title": "1/2 oz Gold Kangaroo",
     "metal": "gold",  "form": "coin",  "weight": "1/2 oz",  "weight_oz": 0.5,
     "mint": "Perth Mint",  "product_family": "Kangaroo",  "year_policy": "varies",
     "purity": ".9999"},

    # ── Gold Britannia ────────────────────────────────────────────────────────
    {"id": 17, "slug": "gold-british-britannia-1oz",      "title": "1 oz Gold Britannia",
     "metal": "gold",  "form": "coin",  "weight": "1 oz",  "weight_oz": 1.0,
     "mint": "Royal Mint",  "product_family": "Britannia",  "year_policy": "varies",
     "purity": ".9999"},

    # ── Gold Panda / Libertad ─────────────────────────────────────────────────
    {"id": 18, "slug": "gold-chinese-panda-1oz",          "title": "1 oz Gold Chinese Panda",
     "metal": "gold",  "form": "coin",  "weight": "1 oz",  "weight_oz": 1.0,
     "mint": "China Gold Coin",  "product_family": "Panda",  "year_policy": "varies",
     "purity": ".999"},

    {"id": 19, "slug": "gold-mexican-libertad-1oz",       "title": "1 oz Gold Mexican Libertad",
     "metal": "gold",  "form": "coin",  "weight": "1 oz",  "weight_oz": 1.0,
     "mint": "Mexican Mint",  "product_family": "Libertad",  "year_policy": "varies",
     "purity": ".999"},

    # ── Gold Bars ─────────────────────────────────────────────────────────────
    {"id": 20, "slug": "gold-bar-1g",    "title": "1 g Gold Bar",  "metal": "gold", "form": "bar",
     "weight": "1 g",  "weight_oz": 0.032,  "mint": "Various",  "product_family": "Bar",
     "year_policy": "varies",  "purity": ".9999"},
    {"id": 21, "slug": "gold-bar-2.5g",  "title": "2.5 g Gold Bar", "metal": "gold", "form": "bar",
     "weight": "2.5 g",  "weight_oz": 0.080,  "mint": "Various",  "product_family": "Bar",
     "year_policy": "varies",  "purity": ".9999"},
    {"id": 22, "slug": "gold-bar-5g",   "title": "5 g Gold Bar",   "metal": "gold", "form": "bar",
     "weight": "5 g",   "weight_oz": 0.161,  "mint": "Various",  "product_family": "Bar",
     "year_policy": "varies",  "purity": ".9999"},
    {"id": 23, "slug": "gold-bar-10g",  "title": "10 g Gold Bar",  "metal": "gold", "form": "bar",
     "weight": "10 g",  "weight_oz": 0.321,  "mint": "Various",  "product_family": "Bar",
     "year_policy": "varies",  "purity": ".9999"},
    {"id": 24, "slug": "gold-bar-1/4oz","title": "1/4 oz Gold Bar","metal": "gold", "form": "bar",
     "weight": "1/4 oz","weight_oz": 0.25,   "mint": "Various",  "product_family": "Bar",
     "year_policy": "varies",  "purity": ".9999"},
    {"id": 25, "slug": "gold-bar-1oz",  "title": "1 oz Gold Bar",  "metal": "gold", "form": "bar",
     "weight": "1 oz",  "weight_oz": 1.0,    "mint": "Various",  "product_family": "Bar",
     "year_policy": "varies",  "purity": ".9999"},
    {"id": 26, "slug": "gold-bar-10oz", "title": "10 oz Gold Bar", "metal": "gold", "form": "bar",
     "weight": "10 oz", "weight_oz": 10.0,   "mint": "Various",  "product_family": "Bar",
     "year_policy": "varies",  "purity": ".9999"},
    {"id": 27, "slug": "gold-bar-1kg",  "title": "1 kg Gold Bar",  "metal": "gold", "form": "bar",
     "weight": "1 kg",  "weight_oz": 32.15,  "mint": "Various",  "product_family": "Bar",
     "year_policy": "varies",  "purity": ".9999"},

    # ── Silver Eagles ─────────────────────────────────────────────────────────
    {"id": 28, "slug": "silver-american-eagle-1oz",       "title": "1 oz Silver American Eagle",
     "metal": "silver", "form": "coin",  "weight": "1 oz",  "weight_oz": 1.0,
     "mint": "US Mint",  "product_family": "American Eagle",  "year_policy": "varies",
     "purity": ".999",  "denomination": "$1"},

    # ── Silver Maple ──────────────────────────────────────────────────────────
    {"id": 29, "slug": "silver-canadian-maple-leaf-1oz",  "title": "1 oz Silver Maple Leaf",
     "metal": "silver", "form": "coin",  "weight": "1 oz",  "weight_oz": 1.0,
     "mint": "Royal Canadian Mint",  "product_family": "Maple Leaf",  "year_policy": "varies",
     "purity": ".9999"},

    # ── Silver Philharmonic ───────────────────────────────────────────────────
    {"id": 30, "slug": "silver-austrian-philharmonic-1oz","title": "1 oz Silver Philharmonic",
     "metal": "silver", "form": "coin",  "weight": "1 oz",  "weight_oz": 1.0,
     "mint": "Austrian Mint",  "product_family": "Philharmonic",  "year_policy": "varies",
     "purity": ".999"},

    # ── Silver Kangaroo ───────────────────────────────────────────────────────
    {"id": 31, "slug": "silver-australian-kangaroo-1oz",  "title": "1 oz Silver Kangaroo",
     "metal": "silver", "form": "coin",  "weight": "1 oz",  "weight_oz": 1.0,
     "mint": "Perth Mint",  "product_family": "Kangaroo",  "year_policy": "varies",
     "purity": ".9999"},

    # ── Silver Britannia ──────────────────────────────────────────────────────
    {"id": 32, "slug": "silver-british-britannia-1oz",    "title": "1 oz Silver Britannia",
     "metal": "silver", "form": "coin",  "weight": "1 oz",  "weight_oz": 1.0,
     "mint": "Royal Mint",  "product_family": "Britannia",  "year_policy": "varies",
     "purity": ".999"},

    # ── Silver Krugerrand / Libertad / Panda ──────────────────────────────────
    {"id": 33, "slug": "silver-south-african-krugerrand-1oz","title": "1 oz Silver Krugerrand",
     "metal": "silver", "form": "coin",  "weight": "1 oz",  "weight_oz": 1.0,
     "mint": "South African Mint",  "product_family": "Krugerrand",  "year_policy": "varies",
     "purity": ".999"},

    {"id": 34, "slug": "silver-mexican-libertad-1oz",     "title": "1 oz Silver Libertad",
     "metal": "silver", "form": "coin",  "weight": "1 oz",  "weight_oz": 1.0,
     "mint": "Mexican Mint",  "product_family": "Libertad",  "year_policy": "varies",
     "purity": ".999"},

    {"id": 35, "slug": "silver-chinese-panda-1oz",        "title": "1 oz Silver Chinese Panda",
     "metal": "silver", "form": "coin",  "weight": "1 oz",  "weight_oz": 1.0,
     "mint": "China Gold Coin",  "product_family": "Panda",  "year_policy": "varies",
     "purity": ".999"},

    # ── Silver Generic Round ──────────────────────────────────────────────────
    {"id": 36, "slug": "silver-round-generic-1oz",        "title": "1 oz Silver Round (Generic)",
     "metal": "silver", "form": "round", "weight": "1 oz",  "weight_oz": 1.0,
     "mint": "Various",  "product_family": "Round",  "year_policy": "varies",
     "purity": ".999"},

    # ── Historic US Silver ────────────────────────────────────────────────────
    {"id": 37, "slug": "silver-morgan-dollar",            "title": "Morgan Silver Dollar",
     "metal": "silver", "form": "coin",  "weight": "0.77 oz",  "weight_oz": 0.77,
     "mint": "US Mint",  "product_family": "Morgan Dollar",  "year_policy": "varies",
     "year": "1878-1921",  "purity": ".900",  "denomination": "$1"},

    {"id": 38, "slug": "silver-peace-dollar",             "title": "Peace Silver Dollar",
     "metal": "silver", "form": "coin",  "weight": "0.77 oz",  "weight_oz": 0.77,
     "mint": "US Mint",  "product_family": "Peace Dollar",  "year_policy": "varies",
     "year": "1921-1935",  "purity": ".900",  "denomination": "$1"},

    {"id": 39, "slug": "silver-walking-liberty-half-dollar","title": "Walking Liberty Half Dollar",
     "metal": "silver", "form": "coin",  "weight": "0.36 oz",  "weight_oz": 0.36,
     "mint": "US Mint",  "product_family": "Walking Liberty",  "year_policy": "varies",
     "year": "1916-1947",  "purity": ".900",  "denomination": "$0.50"},

    {"id": 40, "slug": "silver-franklin-half-dollar",     "title": "Franklin Silver Half Dollar",
     "metal": "silver", "form": "coin",  "weight": "0.36 oz",  "weight_oz": 0.36,
     "mint": "US Mint",  "product_family": "Franklin Half",  "year_policy": "varies",
     "year": "1948-1963",  "purity": ".900",  "denomination": "$0.50"},

    {"id": 41, "slug": "silver-mercury-dime",             "title": "Mercury Silver Dime",
     "metal": "silver", "form": "coin",  "weight": "0.072 oz",  "weight_oz": 0.072,
     "mint": "US Mint",  "product_family": "Mercury Dime",  "year_policy": "varies",
     "year": "1916-1945",  "purity": ".900",  "denomination": "$0.10"},

    {"id": 42, "slug": "silver-roosevelt-dime",           "title": "Roosevelt Silver Dime",
     "metal": "silver", "form": "coin",  "weight": "0.072 oz",  "weight_oz": 0.072,
     "mint": "US Mint",  "product_family": "Roosevelt Dime",  "year_policy": "varies",
     "year": "1946-1964",  "purity": ".900",  "denomination": "$0.10"},

    {"id": 43, "slug": "silver-washington-quarter",       "title": "Washington Silver Quarter",
     "metal": "silver", "form": "coin",  "weight": "0.18 oz",  "weight_oz": 0.18,
     "mint": "US Mint",  "product_family": "Washington Quarter",  "year_policy": "varies",
     "year": "1932-1964",  "purity": ".900",  "denomination": "$0.25"},

    # ── Silver Bars ───────────────────────────────────────────────────────────
    {"id": 44, "slug": "silver-bar-1oz",   "title": "1 oz Silver Bar",   "metal": "silver", "form": "bar",
     "weight": "1 oz",   "weight_oz": 1.0,   "mint": "Various", "product_family": "Bar", "year_policy": "varies", "purity": ".999"},
    {"id": 45, "slug": "silver-bar-2oz",   "title": "2 oz Silver Bar",   "metal": "silver", "form": "bar",
     "weight": "2 oz",   "weight_oz": 2.0,   "mint": "Various", "product_family": "Bar", "year_policy": "varies", "purity": ".999"},
    {"id": 46, "slug": "silver-bar-5oz",   "title": "5 oz Silver Bar",   "metal": "silver", "form": "bar",
     "weight": "5 oz",   "weight_oz": 5.0,   "mint": "Various", "product_family": "Bar", "year_policy": "varies", "purity": ".999"},
    {"id": 47, "slug": "silver-bar-10oz",  "title": "10 oz Silver Bar",  "metal": "silver", "form": "bar",
     "weight": "10 oz",  "weight_oz": 10.0,  "mint": "Various", "product_family": "Bar", "year_policy": "varies", "purity": ".999"},
    {"id": 48, "slug": "silver-bar-50oz",  "title": "50 oz Silver Bar",  "metal": "silver", "form": "bar",
     "weight": "50 oz",  "weight_oz": 50.0,  "mint": "Various", "product_family": "Bar", "year_policy": "varies", "purity": ".999"},
    {"id": 49, "slug": "silver-bar-100oz", "title": "100 oz Silver Bar", "metal": "silver", "form": "bar",
     "weight": "100 oz", "weight_oz": 100.0, "mint": "Various", "product_family": "Bar", "year_policy": "varies", "purity": ".999"},
    {"id": 50, "slug": "silver-bar-1kg",   "title": "1 kg Silver Bar",   "metal": "silver", "form": "bar",
     "weight": "1 kg",   "weight_oz": 32.15, "mint": "Various", "product_family": "Bar", "year_policy": "varies", "purity": ".999"},

    # ── Platinum ──────────────────────────────────────────────────────────────
    {"id": 51, "slug": "platinum-american-eagle-1oz",        "title": "1 oz Platinum American Eagle",
     "metal": "platinum", "form": "coin", "weight": "1 oz", "weight_oz": 1.0,
     "mint": "US Mint",  "product_family": "American Eagle",  "year_policy": "varies",
     "purity": ".9995",  "denomination": "$100"},
    {"id": 52, "slug": "platinum-american-eagle-quarter-oz", "title": "1/4 oz Platinum American Eagle",
     "metal": "platinum", "form": "coin", "weight": "1/4 oz", "weight_oz": 0.25,
     "mint": "US Mint",  "product_family": "American Eagle",  "year_policy": "varies",
     "purity": ".9995",  "denomination": "$25"},
    {"id": 53, "slug": "platinum-american-eagle-tenth-oz",   "title": "1/10 oz Platinum American Eagle",
     "metal": "platinum", "form": "coin", "weight": "1/10 oz", "weight_oz": 0.1,
     "mint": "US Mint",  "product_family": "American Eagle",  "year_policy": "varies",
     "purity": ".9995",  "denomination": "$10"},
    {"id": 54, "slug": "platinum-canadian-maple-leaf-1oz",   "title": "1 oz Platinum Maple Leaf",
     "metal": "platinum", "form": "coin", "weight": "1 oz", "weight_oz": 1.0,
     "mint": "Royal Canadian Mint",  "product_family": "Maple Leaf",  "year_policy": "varies",
     "purity": ".9995"},
    {"id": 55, "slug": "platinum-bar-1oz",                   "title": "1 oz Platinum Bar",
     "metal": "platinum", "form": "bar",  "weight": "1 oz", "weight_oz": 1.0,
     "mint": "Various",  "product_family": "Bar",  "year_policy": "varies",  "purity": ".9995"},

    # ── Palladium ─────────────────────────────────────────────────────────────
    {"id": 56, "slug": "palladium-american-eagle-1oz",       "title": "1 oz Palladium American Eagle",
     "metal": "palladium", "form": "coin", "weight": "1 oz", "weight_oz": 1.0,
     "mint": "US Mint",  "product_family": "American Eagle",  "year_policy": "varies",
     "purity": ".9995",  "denomination": "$25"},
    {"id": 57, "slug": "palladium-canadian-maple-leaf-1oz",  "title": "1 oz Palladium Maple Leaf",
     "metal": "palladium", "form": "coin", "weight": "1 oz", "weight_oz": 1.0,
     "mint": "Royal Canadian Mint",  "product_family": "Maple Leaf",  "year_policy": "varies",
     "purity": ".9995"},
    {"id": 58, "slug": "palladium-bar-1oz",                  "title": "1 oz Palladium Bar",
     "metal": "palladium", "form": "bar",  "weight": "1 oz", "weight_oz": 1.0,
     "mint": "Various",  "product_family": "Bar",  "year_policy": "varies",  "purity": ".9995"},

    # ── Copper ────────────────────────────────────────────────────────────────
    {"id": 59, "slug": "copper-round-1oz",  "title": "1 oz Copper Round",
     "metal": "copper", "form": "round", "weight": "1 oz", "weight_oz": 1.0,
     "mint": "Various",  "product_family": "Round",  "year_policy": "varies",  "purity": ".999"},
    {"id": 60, "slug": "copper-bar-1oz",    "title": "1 oz Copper Bar",
     "metal": "copper", "form": "bar",   "weight": "1 oz", "weight_oz": 1.0,
     "mint": "Various",  "product_family": "Bar",  "year_policy": "varies",  "purity": ".999"},
    {"id": 61, "slug": "copper-bar-1lb",    "title": "1 lb Copper Bar",
     "metal": "copper", "form": "bar",   "weight": "1 lb", "weight_oz": 14.58,
     "mint": "Various",  "product_family": "Bar",  "year_policy": "varies",  "purity": ".999"},

    # ── Kookaburra (Perth Mint) ───────────────────────────────────────────────
    {"id": 62, "slug": "silver-australian-kookaburra-1oz",   "title": "1 oz Silver Kookaburra",
     "metal": "silver", "form": "coin", "weight": "1 oz", "weight_oz": 1.0,
     "mint": "Perth Mint",  "product_family": "Kookaburra",  "year_policy": "varies",  "purity": ".999"},
]


def load_from_db() -> Optional[List[Dict]]:
    """Try to load buckets from Metex PostgreSQL DB. Returns None on failure."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return None
    try:
        import sys
        # Add Metex root to path so we can import database module
        metex_root = str(Path(__file__).resolve().parent.parent.parent)
        if metex_root not in sys.path:
            sys.path.insert(0, metex_root)
        import database
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, slug, title, metal, form, weight, weight_oz,
                   denomination, mint, product_family, product_series,
                   year_policy, year, purity, finish, variant,
                   category_bucket_id, active
            FROM standard_buckets
            WHERE active = 1
            ORDER BY metal, product_family, weight_oz
        """)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        conn.close()
        logger.info("Loaded %d buckets from database", len(rows))
        return rows
    except Exception as e:
        logger.debug("DB load failed: %s", e)
        return None


def load_from_cache() -> Optional[List[Dict]]:
    """Load buckets from local JSON cache."""
    if not _CACHE_PATH.exists():
        return None
    try:
        data = json.loads(_CACHE_PATH.read_text())
        logger.info("Loaded %d buckets from cache: %s", len(data), _CACHE_PATH)
        return data
    except Exception as e:
        logger.debug("Cache load failed: %s", e)
        return None


def save_cache(buckets: List[Dict]) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(buckets, indent=2, default=str))
    logger.info("Saved %d buckets to cache: %s", len(buckets), _CACHE_PATH)


def load_buckets(use_cache: bool = True, use_db: bool = True) -> List[Dict]:
    """
    Load standard bucket dicts in priority order:
      1. Live DB (if DATABASE_URL set)
      2. Local cache (data/buckets.json)
      3. Built-in seed
    """
    if use_db:
        buckets = load_from_db()
        if buckets:
            if use_cache:
                save_cache(buckets)
            return buckets

    if use_cache:
        buckets = load_from_cache()
        if buckets:
            return buckets

    logger.info("Using built-in seed (%d buckets)", len(_SEED_BUCKETS))
    return list(_SEED_BUCKETS)
