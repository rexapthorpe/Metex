#!/usr/bin/env python3
"""
Export acquired candidates from local manifests into the Metex
bucket_image_assets table.

Requires:
  - DATABASE_URL environment variable (Metex PostgreSQL)
  - Metex project root on PYTHONPATH (handled automatically if run from
    the Metex directory tree)

Usage:
    cd Metex/bucket_image_acquisition
    python scripts/export_to_metex.py --all
    python scripts/export_to_metex.py --metal gold
    python scripts/export_to_metex.py --slug gold-american-eagle-1oz
    python scripts/export_to_metex.py --all --mode url
    python scripts/export_to_metex.py --all --dry-run
    python scripts/export_to_metex.py --all --min-confidence 0.60
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.exporter import export_all_manifests


def main():
    p = argparse.ArgumentParser(description="Export acquired images to Metex bucket_image_assets")
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--all",   dest="run_all", action="store_true", help="Export all manifests")
    grp.add_argument("--metal", dest="metal",   help="Filter by metal")
    grp.add_argument("--slug",  dest="slug",    help="Single bucket slug")

    p.add_argument("--mode",           choices=["upload", "url"], default="upload",
                   help="upload=use local file (fast); url=re-download (always fresh)")
    p.add_argument("--min-confidence", type=float, default=0.30,
                   help="Skip candidates below this confidence (default 0.30)")
    p.add_argument("--dry-run",        action="store_true",
                   help="Print plan without writing to Metex DB")

    args = p.parse_args()

    stats_list = export_all_manifests(
        mode=args.mode,
        min_confidence=args.min_confidence,
        slug_filter=args.slug,
        metal_filter=args.metal,
        dry_run=args.dry_run,
    )

    total_exported = sum(s["exported"] for s in stats_list)
    total_errors   = sum(s["errors"] for s in stats_list)

    print(f"\nExport summary:")
    print(f"  Manifests processed : {len(stats_list)}")
    print(f"  Candidates exported : {total_exported}")
    print(f"  Errors              : {total_errors}")

    if args.dry_run:
        print("\n[DRY RUN] No data written to Metex.")


if __name__ == "__main__":
    main()
