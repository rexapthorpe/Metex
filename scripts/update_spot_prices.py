#!/usr/bin/env python3
"""
Spot Price Snapshot Updater

Fetches the current spot price for each metal and writes a new row into
`spot_price_snapshots` if the price has changed materially or enough time
has elapsed since the last snapshot.

Designed to be called by cron every 10 minutes, e.g.:
    */10 * * * * cd /path/to/metex && python scripts/update_spot_prices.py

The graph endpoint NEVER calls the external API directly — it only reads
from `spot_price_snapshots`. This script is the only writer.

Threshold guard:
  - Skip insert if |new - old| / old <= 0.0005 (0.05%) AND
    last snapshot was less than 20 minutes ago.
  This prevents inserting identical rows every 10 minutes while still
  recording slow drifts.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from database import get_db_connection
from services.spot_price_service import get_current_spot_prices

THRESHOLD_PCT  = 0.0005   # 0.05% minimum price change to trigger insert
MAX_QUIET_MINS = 20       # Always insert if no snapshot in this many minutes


def _get_last_snapshot(conn, metal):
    """Return (price_usd, as_of) of the most recent snapshot for a metal, or (None, None)."""
    row = conn.execute(
        "SELECT price_usd, as_of FROM spot_price_snapshots "
        "WHERE metal = ? ORDER BY as_of DESC LIMIT 1",
        (metal,)
    ).fetchone()
    if row is None:
        return None, None
    return row['price_usd'], row['as_of']


def _should_insert(last_price, last_as_of, new_price):
    """
    Return True if a new snapshot row should be inserted.
    """
    if last_price is None:
        return True  # No existing data — always insert

    # Parse last timestamp
    try:
        if isinstance(last_as_of, str):
            last_time = datetime.fromisoformat(last_as_of)
        else:
            last_time = last_as_of
        age_mins = (datetime.now() - last_time).total_seconds() / 60
    except Exception:
        return True  # Can't parse — insert to be safe

    # Always insert if the last snapshot is stale
    if age_mins >= MAX_QUIET_MINS:
        return True

    # Insert if price has moved by more than the threshold
    if last_price > 0:
        change_pct = abs(new_price - last_price) / last_price
        return change_pct > THRESHOLD_PCT

    return True


def run():
    conn = get_db_connection()
    now = datetime.now()

    print(f"[update_spot_prices] Starting at {now.isoformat()}")

    # Fetch current prices via the existing spot price service.
    # force_refresh=True bypasses the 5-minute cache and hits the API.
    spot_prices = get_current_spot_prices(force_refresh=True)

    if not spot_prices:
        print("[update_spot_prices] No spot prices available — aborting.")
        conn.close()
        return

    inserted = 0
    skipped  = 0

    for metal, new_price in spot_prices.items():
        last_price, last_as_of = _get_last_snapshot(conn, metal)

        if _should_insert(last_price, last_as_of, new_price):
            conn.execute(
                "INSERT INTO spot_price_snapshots (metal, price_usd, as_of, source) "
                "VALUES (?, ?, ?, 'metalpriceapi')",
                (metal, new_price, now)
            )
            delta = f" (Δ {new_price - last_price:+.4f})" if last_price else " (first)"
            print(f"  ✓ {metal}: ${new_price:.4f}{delta}")
            inserted += 1
        else:
            print(f"  - {metal}: ${new_price:.4f} — unchanged, skipped")
            skipped += 1

    conn.commit()
    conn.close()
    print(f"[update_spot_prices] Done — {inserted} inserted, {skipped} skipped.")


if __name__ == '__main__':
    run()
