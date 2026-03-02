#!/usr/bin/env python3
"""
Migration: Add spot_price_snapshots table

Creates a time-series table for historical spot price snapshots used by the
bucket reference price chart. Separate from the existing spot_prices UNIQUE
cache; this table stores one row per metal per snapshot timestamp.

Safe to run multiple times (idempotent).
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection


def run():
    conn = get_db_connection()
    cursor = conn.cursor()

    print("Running migration: add spot_price_snapshots table")

    # Create the table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS spot_price_snapshots (
            id        INTEGER   PRIMARY KEY AUTOINCREMENT,
            metal     TEXT      NOT NULL,
            price_usd REAL      NOT NULL,
            as_of     TIMESTAMP NOT NULL,
            source    TEXT      DEFAULT 'metalpriceapi',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("  ✓ Table spot_price_snapshots created (or already existed)")

    # Create index for efficient historical lookups: metal + time range queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_spot_snapshots_metal_as_of
            ON spot_price_snapshots(metal, as_of DESC)
    """)
    print("  ✓ Index idx_spot_snapshots_metal_as_of created (or already existed)")

    conn.commit()
    conn.close()
    print("Migration complete.")


if __name__ == '__main__':
    run()
