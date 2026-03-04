#!/usr/bin/env python3
"""
Spot Price Snapshot Updater (cron/manual entry point)

This script is the original cron entry point.  The actual logic now lives in
`services/spot_snapshot_service.py` so it can be shared with the in-process
background scheduler.

Designed to be called by cron every 10 minutes, e.g.:
    */10 * * * * cd /path/to/metex && python scripts/update_spot_prices.py

The graph endpoint NEVER calls the external API directly — it only reads
from `spot_price_snapshots`.  This script (and the in-process scheduler) are
the only writers.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.spot_snapshot_service import run_snapshot


def run():
    result = run_snapshot(use_lock=False, verbose=True)
    if result.get("error"):
        print(f"[update_spot_prices] Error: {result['error']}")
        sys.exit(1)


if __name__ == '__main__':
    run()
