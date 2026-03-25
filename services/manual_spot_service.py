"""
Manual Spot Snapshot Service (Dev / Debug Only)

Provides an admin-controlled way to insert spot price snapshots directly into
the DB for testing variable-spot bucket pricing without waiting for external
API calls.

Safety requirements:
- NEVER calls any external API.  All it does is INSERT into spot_price_snapshots.
- The calling route is responsible for checking DEBUG / ENV before invoking this.
- source is always 'manual_admin' so snapshots can be filtered or identified easily.
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

ALLOWED_METALS = {"gold", "silver", "platinum", "palladium", "copper"}

# Absolute maximum — reject obviously absurd inputs
PRICE_MAX = 1_000_000.0   # USD / troy oz

# Per-metal minimum guard against typos (e.g. entering 5 instead of 5000 for gold)
PRICE_MIN_BY_METAL = {
    "gold":      100.0,
    "silver":      0.5,
    "platinum":   10.0,
    "palladium":  10.0,
    "copper":      0.01,
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _trigger_bid_rematch(metal: str) -> None:
    """Re-evaluate open bids after a manual spot price update."""
    try:
        from core.blueprints.bids.auto_match import run_bid_rematch_after_spot_update
        run_bid_rematch_after_spot_update(metals=[metal])
    except Exception as e:
        logger.warning("[manual_spot] Bid rematch failed for %s: %s", metal, e)


# ─── Service function ─────────────────────────────────────────────────────────

def insert_manual_spot_snapshot(conn, metal: str, price_usd: float) -> dict:
    """
    Insert a manual spot price snapshot into spot_price_snapshots.

    Does NOT call any external API.  Source column is always 'manual_admin'.

    Args:
        conn:      Open DB connection with row_factory already configured.
        metal:     Canonical metal name ('gold', 'silver', 'platinum', …).
                   Case-insensitive — normalised to lower-case internally.
        price_usd: Price in USD per troy oz.  Must satisfy:
                     PRICE_MIN_BY_METAL[metal] <= price_usd <= PRICE_MAX

    Returns:
        dict: {id, metal, price_usd, as_of, source}

    Raises:
        ValueError: on invalid metal or price.
    """
    # --- normalise & validate metal -----------------------------------------
    metal = metal.strip().lower()
    if metal not in ALLOWED_METALS:
        raise ValueError(
            f"Unknown metal '{metal}'. Allowed: {sorted(ALLOWED_METALS)}"
        )

    # --- validate price ------------------------------------------------------
    try:
        price_usd = float(price_usd)
    except (TypeError, ValueError):
        raise ValueError("price_usd must be a number")

    if price_usd <= 0:
        raise ValueError("price_usd must be greater than 0")

    if price_usd > PRICE_MAX:
        raise ValueError(
            f"price_usd {price_usd:,.2f} exceeds maximum {PRICE_MAX:,.0f}"
        )

    min_price = PRICE_MIN_BY_METAL.get(metal, 0.01)
    if price_usd < min_price:
        raise ValueError(
            f"price_usd {price_usd} is below the minimum {min_price} for {metal}"
        )

    # --- insert --------------------------------------------------------------
    as_of = datetime.now().isoformat()

    cur = conn.execute(
        """
        INSERT INTO spot_price_snapshots (metal, price_usd, as_of, source)
        VALUES (?, ?, ?, 'manual_admin')
        """,
        (metal, price_usd, as_of),
    )
    conn.commit()

    # After committing the new snapshot, re-evaluate open bids that may now
    # be marketable at the updated spot price.
    _trigger_bid_rematch(metal)

    return {
        "id":        cur.lastrowid,
        "metal":     metal,
        "price_usd": price_usd,
        "as_of":     as_of,
        "source":    "manual_admin",
    }
