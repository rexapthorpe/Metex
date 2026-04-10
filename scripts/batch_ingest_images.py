"""
Batch image ingestion runner for Metex standard buckets.

Usage examples:

  # Ingest images for ALL standard buckets from Wikimedia (3 candidates each)
  python scripts/batch_ingest_images.py --all --source wikimedia

  # Ingest only for buckets with no active cover image
  python scripts/batch_ingest_images.py --missing-only --source wikimedia

  # Ingest for a single specific bucket (by standard_buckets.id)
  python scripts/batch_ingest_images.py --bucket-id 5 --source wikimedia

  # Dry-run: see what would be fetched without writing anything
  python scripts/batch_ingest_images.py --missing-only --source wikimedia --dry-run

  # Re-run ingestion for Wikimedia source on all buckets (will deduplicate)
  python scripts/batch_ingest_images.py --all --source wikimedia

  # Limit candidates per bucket (default: 3)
  python scripts/batch_ingest_images.py --all --source wikimedia --max-per-bucket 5

  # Show per-run stats from ingestion_runs table
  python scripts/batch_ingest_images.py --stats [--limit 20]

How ingestion works:
  1. Load target buckets from standard_buckets (based on --all / --missing-only / --bucket-id).
  2. For each bucket, call the selected adapter to get candidate image URLs.
  3. Pipe each candidate through bucket_image_service.ingest_from_url().
     - SHA-256 deduplication: exact duplicate images are silently skipped.
     - Confidence scoring: additive field-matching against raw_source_title.
     - Auto-activation: ONLY for internal_upload source with no warnings.
       Wikimedia candidates stay 'pending' and require admin review.
  4. Record results in bucket_image_ingestion_runs for audit.
  5. Print a per-bucket summary and a final totals line.

Review queue:
  After batch ingestion, visit Admin → Bucket Images to review pending candidates.
  Use the filter "Pending candidates only" or "Missing cover" to triage quickly.
"""

import argparse
import sys
import os
import time
from datetime import datetime
from typing import List, Optional

# Ensure project root on path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database
import services.bucket_image_service as bis
from services.ingestion_adapters import (
    KnownFilesAdapter,
    WikimediaAdapter,
    UsMintDirectAdapter,
    UsMintAdapter,
    RcmAdapter,
    RoyalMintAdapter,
    PerthMintAdapter,
    RefinerAdapter,
    ApmexAdapter,
    JmBullionAdapter,
)

# ---------------------------------------------------------------------------
# Adapter registry — add new adapters here
# ---------------------------------------------------------------------------
# Keys become valid --source values on the CLI.
# Source type and auto-activation rules are defined per-adapter in
# services/ingestion_adapters/.
# ---------------------------------------------------------------------------

ADAPTERS = {
    'known_files':    KnownFilesAdapter,   # hardcoded curated catalog (highest precision)
    'wikimedia':      WikimediaAdapter,    # generic Wikimedia Commons search
    'us_mint_direct': UsMintDirectAdapter, # US Mint scraped from usmint.gov (public_domain, preferred)
    'us_mint':        UsMintAdapter,       # US Mint via Wikimedia search (public_domain, fallback)
    'rcm':            RcmAdapter,          # Royal Canadian Mint via Wikimedia (licensed, review req'd)
    'royal_mint':     RoyalMintAdapter,    # Royal Mint UK via Wikimedia (licensed, review req'd)
    'perth_mint':     PerthMintAdapter,    # Perth Mint AU via Wikimedia (licensed, review req'd)
    'refiner':        RefinerAdapter,      # Bullion bars: PAMP, Valcambi, Sunshine, etc.
    'apmex':          ApmexAdapter,        # APMEX retailer (candidate-only, always pending)
    'jmbullion':      JmBullionAdapter,    # JM Bullion retailer (candidate-only, always pending)
}


# ---------------------------------------------------------------------------
# Core batch logic
# ---------------------------------------------------------------------------

def _load_buckets(
    conn,
    missing_only: bool,
    no_candidates: bool,
    bucket_id: Optional[int],
) -> List[dict]:
    """Return standard_buckets rows to process."""
    if bucket_id:
        row = conn.execute(
            "SELECT * FROM standard_buckets WHERE id = ? AND active = 1", (bucket_id,)
        ).fetchone()
        return [dict(row)] if row else []

    if no_candidates:
        # Buckets with zero assets (not even pending)
        rows = conn.execute("""
            SELECT sb.*
            FROM standard_buckets sb
            WHERE sb.active = 1
              AND NOT EXISTS (
                  SELECT 1 FROM bucket_image_assets bia
                  WHERE bia.standard_bucket_id = sb.id
              )
            ORDER BY sb.metal, sb.title
        """).fetchall()
    elif missing_only:
        # Buckets with no ACTIVE cover image
        rows = conn.execute("""
            SELECT sb.*
            FROM standard_buckets sb
            WHERE sb.active = 1
              AND NOT EXISTS (
                  SELECT 1 FROM bucket_image_assets bia
                  WHERE bia.standard_bucket_id = sb.id AND bia.status = 'active'
              )
            ORDER BY sb.metal, sb.title
        """).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM standard_buckets WHERE active = 1 ORDER BY metal, title"
        ).fetchall()

    return [dict(r) for r in rows]


def _ingest_bucket(
    conn,
    bucket: dict,
    adapter,
    dry_run: bool,
    max_candidates: int,
    min_confidence: float = 0.0,
    download_delay: float = 2.0,
) -> dict:
    """
    Run ingestion for a single bucket. Returns a summary dict:
      bucket_id, title, candidates_found, ingested, duplicates, errors,
      skipped_license, skipped_confidence
    """
    summary = {
        'bucket_id':           bucket['id'],
        'title':               bucket['title'],
        'candidates_found':    0,
        'ingested':            0,
        'duplicates':          0,
        'errors':              0,
        'skipped_license':     0,
        'skipped_confidence':  0,
    }

    try:
        candidates = adapter.find_candidates(bucket)
    except Exception as exc:
        print(f"    [ERROR] adapter.find_candidates failed: {exc}")
        summary['errors'] += 1
        return summary

    candidates = candidates[:max_candidates]
    summary['candidates_found'] = len(candidates)

    if not candidates:
        return summary

    # Pre-filter by confidence before downloading anything
    if min_confidence > 0:
        pre_filtered = []
        for cand in candidates:
            conf, _ = bis.compute_match_confidence(
                bucket,
                cand.get('raw_source_title', ''),
                cand.get('source_type', 'unknown'),
            )
            if conf >= min_confidence:
                pre_filtered.append(cand)
            else:
                print(f"    [SKIP-CONF] pre-conf={conf:.2f} < {min_confidence}: "
                      f"{cand.get('url', '')[:60]}...")
                summary['skipped_confidence'] += 1
        candidates = pre_filtered

    _last_download = [0.0]

    def _throttle_download():
        wait = download_delay - (time.monotonic() - _last_download[0])
        if wait > 0:
            time.sleep(wait)
        _last_download[0] = time.monotonic()

    for cand in candidates:
        url = cand.get('url', '')
        if not url:
            continue

        if dry_run:
            print(f"    [DRY-RUN] Would ingest: {url[:80]}...")
            summary['ingested'] += 1
            continue

        source_info = {
            'source_name':        cand.get('source_name', adapter.name),
            'source_type':        cand.get('source_type', adapter.source_type),
            'source_page_url':    cand.get('source_page_url'),
            'original_image_url': cand.get('original_image_url') or url,
            'attribution_text':   cand.get('attribution_text'),
            'license_type':       cand.get('license_type'),
            'rights_note':        cand.get('rights_note'),
            'usage_allowed':      True,
            'raw_source_title':   cand.get('raw_source_title', ''),
        }

        _throttle_download()
        try:
            result = bis.ingest_from_url(
                standard_bucket_id=bucket['id'],
                url=url,
                source_info=source_info,
                admin_user_id=None,  # system job
            )
            if result.get('duplicate'):
                summary['duplicates'] += 1
                print(f"    Duplicate (skipped): {url[:70]}...")
            else:
                status = result.get('status', 'pending')
                conf   = result.get('confidence_score', 0)
                warns  = result.get('warnings', [])
                summary['ingested'] += 1
                print(f"    Ingested [{status}] conf={conf:.2f} warns={warns}: {url[:60]}...")
        except ValueError as exc:
            print(f"    [SKIP] {exc}: {url[:60]}...")
            summary['skipped_license'] += 1
        except Exception as exc:
            print(f"    [ERROR] {exc}: {url[:60]}...")
            summary['errors'] += 1

    return summary


def _print_stats(conn, limit: int):
    """Print recent ingestion run stats from the audit table."""
    rows = conn.execute("""
        SELECT bir.*, sb.title AS bucket_title, sb.metal
        FROM bucket_image_ingestion_runs bir
        LEFT JOIN standard_buckets sb ON sb.id = bir.standard_bucket_id
        ORDER BY bir.started_at DESC
        LIMIT ?
    """, (limit,)).fetchall()

    if not rows:
        print("No ingestion runs found.")
        return

    print(f"\n{'ID':<6} {'Bucket':<40} {'Source':<20} {'Status':<10} "
          f"{'Found':>5} {'Ingested':>8} {'Dupes':>5} {'Started':<20}")
    print('-' * 115)
    for r in rows:
        r = dict(r)
        print(
            f"{r['id']:<6} "
            f"{(r.get('bucket_title') or '?')[:38]:<40} "
            f"{(r.get('source_name') or '')[:18]:<20} "
            f"{(r.get('status') or ''):<10} "
            f"{(r.get('images_found') or 0):>5} "
            f"{(r.get('images_ingested') or 0):>8} "
            f"{(r.get('images_skipped_duplicate') or 0):>5} "
            f"{str(r.get('started_at') or '')[:19]:<20}"
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Batch-ingest cover images for standard buckets.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument('--all', action='store_true',
                       help='Ingest images for all active standard buckets')
    group.add_argument('--missing-only', action='store_true',
                       help='Ingest only for buckets with no active cover image')
    group.add_argument('--no-candidates', action='store_true',
                       help='Ingest only for buckets with zero candidates (not even pending)')
    group.add_argument('--bucket-id', type=int, metavar='ID',
                       help='Ingest images for a single standard bucket (by id)')
    group.add_argument('--stats', action='store_true',
                       help='Print recent ingestion run stats and exit')

    parser.add_argument('--source', default='wikimedia',
                        choices=list(ADAPTERS.keys()),
                        help='Image source adapter (default: wikimedia)')
    parser.add_argument('--max-per-bucket', type=int, default=3,
                        help='Max candidate images to fetch per bucket (default: 3)')
    parser.add_argument('--min-confidence', type=float, default=0.30,
                        help='Skip candidates whose pre-computed confidence is below this '
                             'threshold before downloading (default: 0.30). '
                             'Use 0 to disable the filter.')
    parser.add_argument('--download-delay', type=float, default=2.0,
                        help='Seconds to wait between image downloads to avoid 429s '
                             '(default: 2.0)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be ingested without writing anything')
    parser.add_argument('--limit', type=int, default=20,
                        help='Limit for --stats (default: 20)')

    args = parser.parse_args()

    conn = database.get_db_connection()
    try:
        if args.stats:
            _print_stats(conn, args.limit)
            return

        no_cand = getattr(args, 'no_candidates', False)
        if not (args.all or args.missing_only or no_cand or args.bucket_id):
            parser.print_help()
            print('\nError: specify --all, --missing-only, --no-candidates, or --bucket-id\n')
            sys.exit(1)

        # Build adapter
        AdapterClass = ADAPTERS[args.source]
        adapter = AdapterClass(max_results=args.max_per_bucket)

        # Load target buckets
        buckets = _load_buckets(
            conn,
            missing_only=args.missing_only,
            no_candidates=no_cand,
            bucket_id=args.bucket_id,
        )

        if not buckets:
            print('No buckets match the given criteria.')
            return

        mode = ('NO-CANDIDATES' if no_cand else
                'MISSING-ONLY'  if args.missing_only else
                f'BUCKET-ID={args.bucket_id}' if args.bucket_id else 'ALL')
        print(f'\n=== Batch ingestion: {len(buckets)} buckets | source={args.source} '
              f'| max={args.max_per_bucket} | mode={mode} '
              f'| min-conf={args.min_confidence} | dl-delay={args.download_delay}s '
              f'{"| DRY-RUN" if args.dry_run else ""} ===\n')

        totals = {'found': 0, 'ingested': 0, 'duplicates': 0,
                  'errors': 0, 'skipped_confidence': 0}
        start_time = time.monotonic()

        for i, bucket in enumerate(buckets, 1):
            print(f'[{i}/{len(buckets)}] {bucket["metal"]} — {bucket["title"]} (id={bucket["id"]})')
            summary = _ingest_bucket(
                conn, bucket, adapter, args.dry_run, args.max_per_bucket,
                min_confidence=args.min_confidence,
                download_delay=args.download_delay,
            )
            totals['found']               += summary['candidates_found']
            totals['ingested']            += summary['ingested']
            totals['duplicates']          += summary['duplicates']
            totals['errors']              += summary['errors']
            totals['skipped_confidence']  += summary.get('skipped_confidence', 0)
            print(f"    → found={summary['candidates_found']} ingested={summary['ingested']} "
                  f"dupes={summary['duplicates']} errors={summary['errors']} "
                  f"skip-conf={summary.get('skipped_confidence', 0)}\n")

        elapsed = time.monotonic() - start_time
        print(f'=== Done in {elapsed:.1f}s — '
              f'found={totals["found"]} ingested={totals["ingested"]} '
              f'dupes={totals["duplicates"]} errors={totals["errors"]} '
              f'skip-conf={totals["skipped_confidence"]} ===')

        if not args.dry_run and totals['ingested'] > 0:
            print('\nNext step: visit Admin → Bucket Images to review pending candidates.')

    finally:
        conn.close()


if __name__ == '__main__':
    main()
