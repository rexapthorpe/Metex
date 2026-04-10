"""
Pipeline orchestrator — the main engine that drives a full or filtered sweep.

Usage (from bucket_image_acquisition/ directory):

    python -m pipeline.orchestrator --all
    python -m pipeline.orchestrator --metal gold
    python -m pipeline.orchestrator --family eagles
    python -m pipeline.orchestrator --slug gold-american-eagle-1oz
    python -m pipeline.orchestrator --source wikimedia --metal silver
    python -m pipeline.orchestrator --all --max-per-bucket 3 --min-confidence 0.40
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

# Allow running from project root or from this directory
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from config.settings import (
    MANIFESTS_DIR, MIN_CONFIDENCE_TO_KEEP,
    catalog_dir_for_slug, ensure_dirs,
)
from config.source_registry import (
    SWEEP_ORDER, METAL_SOURCES, FAMILY_SOURCES,
    get_adapter, get_registry,
)
from matchers.spec_matcher import compute_confidence
from matchers.deduper import ExactDeduper
from pipeline.downloader import download_image
from pipeline.processor import process_image
from pipeline.manifest import (
    load_manifest, save_manifest, add_candidate,
)
from pipeline.bucket_loader import load_buckets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("orchestrator")


# ---------------------------------------------------------------------------
# Core run logic
# ---------------------------------------------------------------------------

def run_bucket(
    bucket: Dict,
    sources: List[str],
    max_per_bucket: int = 5,
    min_confidence: float = MIN_CONFIDENCE_TO_KEEP,
    download_delay: float = 2.0,
    deduper: Optional[ExactDeduper] = None,
    dry_run: bool = False,
) -> Dict:
    """
    Run acquisition for a single bucket across the given sources.

    Returns a summary dict with counts.
    """
    slug = bucket.get("slug", "unknown")
    logger.info("Processing bucket: %s", slug)

    if deduper is None:
        deduper = ExactDeduper()

    catalog_dir = catalog_dir_for_slug(slug)
    catalog_dir.mkdir(parents=True, exist_ok=True)
    (catalog_dir / "thumbs").mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(slug)
    manifest["bucket_id"] = bucket.get("id")

    # Pre-load existing checksums to avoid re-downloading
    existing_checksums = {
        c.get("checksum", "") for c in manifest.get("candidates", [])
        if c.get("checksum")
    }
    deduper._seen.update(existing_checksums)

    stats = {
        "slug": slug,
        "found": 0,
        "ingested": 0,
        "skipped_confidence": 0,
        "skipped_duplicate": 0,
        "skipped_download": 0,
        "errors": 0,
    }

    candidates_added = 0

    for source_name in sources:
        if candidates_added >= max_per_bucket:
            break
        try:
            adapter = get_adapter(source_name, max_results=max_per_bucket)
        except ValueError:
            logger.warning("Unknown source %r, skipping", source_name)
            continue

        logger.info("  [%s] searching with adapter %s", slug, adapter.name)

        try:
            candidates = adapter.find_candidates(bucket)
        except Exception as e:
            logger.warning("  [%s] adapter %s failed: %s", slug, source_name, e)
            stats["errors"] += 1
            continue

        stats["found"] += len(candidates)

        for cand in candidates:
            if candidates_added >= max_per_bucket:
                break

            url = cand.get("url", "")
            raw_title = cand.get("raw_source_title", "")
            src_type = cand.get("source_type", "unknown")

            # Score before downloading
            confidence, warnings = compute_confidence(raw_title, bucket, src_type)

            if confidence < min_confidence:
                logger.debug("  [%s] low confidence %.2f, skip: %r", slug, confidence, raw_title)
                stats["skipped_confidence"] += 1
                continue

            if dry_run:
                logger.info("  [DRY RUN] would download: %s (conf=%.2f)", url[:80], confidence)
                candidates_added += 1
                stats["ingested"] += 1
                continue

            # Download
            time.sleep(download_delay)
            image_bytes, checksum = download_image(url)

            if not image_bytes:
                logger.debug("  [%s] download failed: %s", slug, url[:80])
                stats["skipped_download"] += 1
                continue

            # Dedup
            if deduper.is_duplicate(checksum):
                logger.debug("  [%s] duplicate %s…", slug, checksum[:12])
                stats["skipped_duplicate"] += 1
                continue
            deduper.add(checksum)

            # Process
            from config.settings import RAW_DIR
            short_source = source_name[:12]
            storage_key = checksum[:16]
            img_info = process_image(
                data=image_bytes,
                storage_key=storage_key,
                slug=slug,
                source_short=short_source,
                catalog_dir=catalog_dir,
                raw_dir=RAW_DIR,
            )

            if not img_info:
                logger.debug("  [%s] image processing failed: %s", slug, url[:60])
                stats["skipped_download"] += 1
                continue

            # Add to manifest
            record = add_candidate(
                manifest=manifest,
                candidate=cand,
                image_info=img_info,
                confidence_score=confidence,
                warnings=warnings,
                status="candidate",
            )
            record["checksum"] = checksum

            candidates_added += 1
            stats["ingested"] += 1
            logger.info(
                "  [%s] ✓ %s | conf=%.2f | %s",
                slug, source_name, confidence, raw_title[:60],
            )

    if not dry_run:
        save_manifest(manifest)

    return stats


def run_sweep(
    sources: List[str] = SWEEP_ORDER,
    metal_filter: Optional[str] = None,
    family_filter: Optional[str] = None,
    slug_filter: Optional[str] = None,
    max_per_bucket: int = 5,
    min_confidence: float = MIN_CONFIDENCE_TO_KEEP,
    download_delay: float = 2.0,
    dry_run: bool = False,
) -> List[Dict]:
    """
    Full or filtered sweep across all standard buckets.

    Returns list of per-bucket stat dicts.
    """
    ensure_dirs()
    buckets = load_buckets()

    if not buckets:
        logger.error("No buckets loaded. Run scripts/export_buckets.py first.")
        return []

    # Apply filters
    if slug_filter:
        buckets = [b for b in buckets if b.get("slug") == slug_filter]
    if metal_filter:
        buckets = [b for b in buckets if b.get("metal", "").lower() == metal_filter.lower()]
    if family_filter:
        # family_filter matches product_family or catalog sub-path
        buckets = [b for b in buckets
                   if family_filter.lower() in (b.get("product_family") or "").lower()
                   or family_filter.lower() in (b.get("slug") or "").lower()]

    if not buckets:
        logger.warning("No buckets match the given filters.")
        return []

    logger.info("Starting sweep: %d buckets × %d sources", len(buckets), len(sources))

    deduper = ExactDeduper()
    deduper.load_from_manifests(MANIFESTS_DIR)

    all_stats: List[Dict] = []
    for bucket in buckets:
        # Narrow sources per metal if no explicit source list given
        bucket_sources = sources
        if metal_filter:
            bucket_sources = METAL_SOURCES.get(metal_filter.lower(), sources)
        if family_filter:
            bucket_sources = FAMILY_SOURCES.get(family_filter.lower(), sources)

        stats = run_bucket(
            bucket=bucket,
            sources=bucket_sources,
            max_per_bucket=max_per_bucket,
            min_confidence=min_confidence,
            download_delay=download_delay,
            deduper=deduper,
            dry_run=dry_run,
        )
        all_stats.append(stats)

    # Summary
    total_found    = sum(s["found"] for s in all_stats)
    total_ingested = sum(s["ingested"] for s in all_stats)
    total_dups     = sum(s["skipped_duplicate"] for s in all_stats)
    total_low_conf = sum(s["skipped_confidence"] for s in all_stats)
    total_errors   = sum(s["errors"] for s in all_stats)

    logger.info("=" * 60)
    logger.info("Sweep complete.")
    logger.info("  Buckets processed : %d", len(all_stats))
    logger.info("  Candidates found  : %d", total_found)
    logger.info("  Ingested          : %d", total_ingested)
    logger.info("  Skipped (low conf): %d", total_low_conf)
    logger.info("  Skipped (dupe)    : %d", total_dups)
    logger.info("  Errors            : %d", total_errors)
    logger.info("=" * 60)

    return all_stats


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args():
    p = argparse.ArgumentParser(description="Metex bucket image acquisition pipeline")
    p.add_argument("--all",    dest="run_all",    action="store_true", help="Process all buckets")
    p.add_argument("--metal",  dest="metal",      help="Filter by metal (gold|silver|platinum|palladium|copper)")
    p.add_argument("--family", dest="family",     help="Filter by product family (eagles|maples|bars...)")
    p.add_argument("--slug",   dest="slug",       help="Process single bucket slug")
    p.add_argument("--source", dest="source",     help="Comma-separated sources (default: all in sweep order)")
    p.add_argument("--max-per-bucket", dest="max_per_bucket", type=int, default=5)
    p.add_argument("--min-confidence", dest="min_confidence", type=float, default=0.30)
    p.add_argument("--download-delay", dest="download_delay", type=float, default=2.0)
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="Plan but don't download anything")
    p.add_argument("--list-sources", dest="list_sources", action="store_true",
                   help="List available sources and exit")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.list_sources:
        from config.source_registry import list_sources
        print("Available sources:")
        for s in list_sources():
            print(f"  {s}")
        sys.exit(0)

    sources = SWEEP_ORDER
    if args.source:
        sources = [s.strip() for s in args.source.split(",")]

    if not (args.run_all or args.metal or args.family or args.slug):
        print("Specify --all, --metal, --family, or --slug. Use --help for options.")
        sys.exit(1)

    run_sweep(
        sources=sources,
        metal_filter=args.metal,
        family_filter=args.family,
        slug_filter=args.slug,
        max_per_bucket=args.max_per_bucket,
        min_confidence=args.min_confidence,
        download_delay=args.download_delay,
        dry_run=args.dry_run,
    )
