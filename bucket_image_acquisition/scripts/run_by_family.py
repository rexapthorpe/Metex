#!/usr/bin/env python3
"""
Run acquisition sweep for a single product family.

Usage:
    cd Metex/bucket_image_acquisition
    python scripts/run_by_family.py eagles
    python scripts/run_by_family.py maples --max-per-bucket 3
    python scripts/run_by_family.py bars --dry-run
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.orchestrator import run_sweep
from config.source_registry import FAMILY_SOURCES, SWEEP_ORDER

def main():
    p = argparse.ArgumentParser(description="Acquisition sweep for one product family")
    p.add_argument("family", help="Family name (eagles, maples, bars, krugerrands, etc.)")
    p.add_argument("--max-per-bucket", type=int, default=5)
    p.add_argument("--min-confidence", type=float, default=0.30)
    p.add_argument("--download-delay", type=float, default=2.0)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    sources = FAMILY_SOURCES.get(args.family.lower(), SWEEP_ORDER)
    print(f"Running acquisition for family: {args.family}")
    print(f"Sources: {sources}")

    run_sweep(
        sources=sources,
        family_filter=args.family,
        max_per_bucket=args.max_per_bucket,
        min_confidence=args.min_confidence,
        download_delay=args.download_delay,
        dry_run=args.dry_run,
    )

if __name__ == "__main__":
    main()
