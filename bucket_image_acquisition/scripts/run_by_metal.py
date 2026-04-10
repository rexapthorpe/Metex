#!/usr/bin/env python3
"""
Run acquisition sweep for a single metal.

Usage:
    cd Metex/bucket_image_acquisition
    python scripts/run_by_metal.py gold
    python scripts/run_by_metal.py silver --max-per-bucket 3
    python scripts/run_by_metal.py platinum --dry-run
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.orchestrator import run_sweep
from config.source_registry import METAL_SOURCES, SWEEP_ORDER

VALID_METALS = ["gold", "silver", "platinum", "palladium", "copper"]

def main():
    p = argparse.ArgumentParser(description="Acquisition sweep for one metal")
    p.add_argument("metal", choices=VALID_METALS, help="Metal to process")
    p.add_argument("--max-per-bucket", type=int, default=5)
    p.add_argument("--min-confidence", type=float, default=0.30)
    p.add_argument("--download-delay", type=float, default=2.0)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    sources = METAL_SOURCES.get(args.metal, SWEEP_ORDER)
    print(f"Running acquisition for metal: {args.metal}")
    print(f"Sources: {sources}")

    run_sweep(
        sources=sources,
        metal_filter=args.metal,
        max_per_bucket=args.max_per_bucket,
        min_confidence=args.min_confidence,
        download_delay=args.download_delay,
        dry_run=args.dry_run,
    )

if __name__ == "__main__":
    main()
