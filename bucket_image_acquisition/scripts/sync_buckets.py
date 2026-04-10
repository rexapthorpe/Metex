#!/usr/bin/env python3
"""
Sync bucket definitions from the live Metex database into data/buckets.json.

This allows the acquisition system to run offline using the latest bucket
catalog without requiring a live DB connection every time.

Usage:
    cd Metex/bucket_image_acquisition
    DATABASE_URL=postgresql://... python scripts/sync_buckets.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.bucket_loader import load_from_db, save_cache


def main():
    print("Syncing bucket definitions from Metex database...")
    buckets = load_from_db()
    if not buckets:
        print("ERROR: Could not load buckets from database.")
        print("Make sure DATABASE_URL is set and the DB is accessible.")
        sys.exit(1)

    save_cache(buckets)
    print(f"Saved {len(buckets)} buckets to data/buckets.json")

    metals = {}
    for b in buckets:
        m = b.get("metal", "other")
        metals[m] = metals.get(m, 0) + 1
    print("\nBy metal:")
    for metal, count in sorted(metals.items()):
        print(f"  {metal:<12} {count}")


if __name__ == "__main__":
    main()
