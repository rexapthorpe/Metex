#!/usr/bin/env python3
"""
Run acquisition using only a specific source adapter.

Usage:
    cd Metex/bucket_image_acquisition
    python scripts/run_by_source.py wikimedia
    python scripts/run_by_source.py us_mint --metal gold
    python scripts/run_by_source.py known_files --all --dry-run
    python scripts/run_by_source.py --list
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.orchestrator import run_sweep
from config.source_registry import list_sources

def main():
    p = argparse.ArgumentParser(description="Acquisition sweep using one source adapter")
    p.add_argument("source", nargs="?", help="Source adapter name")
    p.add_argument("--all",    dest="run_all", action="store_true")
    p.add_argument("--metal",  help="Filter by metal")
    p.add_argument("--family", help="Filter by product family")
    p.add_argument("--slug",   help="Single bucket slug")
    p.add_argument("--max-per-bucket", type=int, default=5)
    p.add_argument("--min-confidence", type=float, default=0.30)
    p.add_argument("--download-delay", type=float, default=2.0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--list",   dest="list_only", action="store_true", help="List available sources")
    args = p.parse_args()

    if args.list_only:
        print("Available sources:")
        for s in list_sources():
            print(f"  {s}")
        return

    if not args.source:
        p.error("Specify a source name or use --list")

    if args.source not in list_sources():
        print(f"Unknown source: {args.source!r}")
        print(f"Available: {list_sources()}")
        sys.exit(1)

    if not (args.run_all or args.metal or args.family or args.slug):
        print("Specify --all, --metal, --family, or --slug")
        sys.exit(1)

    run_sweep(
        sources=[args.source],
        metal_filter=args.metal,
        family_filter=args.family,
        slug_filter=args.slug,
        max_per_bucket=args.max_per_bucket,
        min_confidence=args.min_confidence,
        download_delay=args.download_delay,
        dry_run=args.dry_run,
    )

if __name__ == "__main__":
    main()
