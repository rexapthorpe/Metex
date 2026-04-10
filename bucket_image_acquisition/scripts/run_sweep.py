#!/usr/bin/env python3
"""
Run a full acquisition sweep across all standard buckets and all sources.

Usage:
    cd Metex/bucket_image_acquisition
    python scripts/run_sweep.py
    python scripts/run_sweep.py --max-per-bucket 3 --min-confidence 0.40
    python scripts/run_sweep.py --dry-run
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.orchestrator import run_sweep
from config.source_registry import SWEEP_ORDER

import argparse

def main():
    p = argparse.ArgumentParser(description="Full acquisition sweep — all buckets, all sources")
    p.add_argument("--max-per-bucket", type=int, default=5)
    p.add_argument("--min-confidence", type=float, default=0.30)
    p.add_argument("--download-delay", type=float, default=2.0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--sources", help="Comma-separated source names (default: all)")
    args = p.parse_args()

    sources = SWEEP_ORDER
    if args.sources:
        sources = [s.strip() for s in args.sources.split(",")]

    run_sweep(
        sources=sources,
        max_per_bucket=args.max_per_bucket,
        min_confidence=args.min_confidence,
        download_delay=args.download_delay,
        dry_run=args.dry_run,
    )

if __name__ == "__main__":
    main()
