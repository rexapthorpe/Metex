"""
Bucket Image Coverage Report

Prints a formatted summary of image coverage across all standard buckets.

Usage:
    python scripts/bucket_image_coverage_report.py

    # Include product-family breakdown (bars, sovereign coins, historic US, etc.)
    python scripts/bucket_image_coverage_report.py --by-family

    # Show recent ingestion runs too
    python scripts/bucket_image_coverage_report.py --runs [--limit 20]

    # Full detail: families + runs
    python scripts/bucket_image_coverage_report.py --by-family --runs

Output:
  - Overall coverage percentage and counts
  - Per-metal breakdown
  - Product-family breakdown (with --by-family): bars, US Mint, sovereign,
    historic US, fractional, private mint, rounds, copper
  - Active image source distribution
  - Optional: recent ingestion runs table
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database
import services.bucket_image_service as bis


def _bar(pct: float, width: int = 20) -> str:
    filled = int(pct / 100 * width)
    empty  = width - filled
    return '█' * filled + '░' * empty


def main():
    parser = argparse.ArgumentParser(description='Print bucket image coverage report.')
    parser.add_argument('--by-family', action='store_true',
                        help='Show per-product-family breakdown')
    parser.add_argument('--runs', action='store_true',
                        help='Also show recent ingestion runs')
    parser.add_argument('--limit', type=int, default=20,
                        help='Limit for --runs output (default: 20)')
    args = parser.parse_args()

    conn = database.get_db_connection()
    try:
        report = bis.get_coverage_report(conn=conn)

        total    = report['total']
        active   = report['with_active']
        pending  = report['pending_only']
        no_cand  = report['no_candidates']
        pct      = report['coverage_pct']

        print()
        print('╔══════════════════════════════════════════════════════╗')
        print('║         Bucket Image Coverage Report                 ║')
        print('╚══════════════════════════════════════════════════════╝')
        print()
        print(f'  Overall Coverage:  {_bar(pct)}  {pct:.1f}%')
        print()
        print(f'  Total buckets      {total:>5}')
        print(f'  With active cover  {active:>5}   ✓')
        print(f'  Pending only       {pending:>5}   ⏳')
        print(f'  No candidates      {no_cand:>5}   ✗')
        print()

        # Per-metal
        print('  ─── By Metal ───────────────────────────────────────')
        by_metal = report.get('by_metal', {})
        for metal, s in sorted(by_metal.items()):
            bar = _bar(s['coverage_pct'], 14)
            print(f'  {metal:<14} {bar}  {s["coverage_pct"]:>5.1f}%  '
                  f'({s["with_active"]}/{s["total"]})')
        print()

        # Product-family breakdown
        if args.by_family:
            print('  ─── By Product Family ───────────────────────────────')
            by_fam = report.get('by_product_group', {})
            if not by_fam:
                print('  (no data)')
            else:
                # Header
                print(f'  {"Group":<32} {"Bar":>3}  {"✓":>4} {"⏳":>4} {"✗":>4}  {"Cov%":>5}')
                print('  ' + '─' * 58)
                for group, g in sorted(by_fam.items()):
                    bar = _bar(g['coverage_pct'], 10)
                    print(
                        f'  {group:<32} {bar}  '
                        f'{g["with_active"]:>4} {g["pending_only"]:>4} '
                        f'{g["no_candidates"]:>4}  {g["coverage_pct"]:>5.1f}%'
                    )
            print()

        # Source breakdown
        by_source = report.get('by_source', {})
        if by_source:
            print('  ─── Active Images by Source ────────────────────────')
            for src, cnt in sorted(by_source.items(), key=lambda x: -x[1]):
                print(f'  {src:<40} {cnt:>4} image{"s" if cnt != 1 else ""}')
            print()

        # Ingestion runs
        if args.runs:
            rows = conn.execute("""
                SELECT bir.*, sb.title AS bucket_title
                FROM bucket_image_ingestion_runs bir
                LEFT JOIN standard_buckets sb ON sb.id = bir.standard_bucket_id
                ORDER BY bir.started_at DESC
                LIMIT ?
            """, (args.limit,)).fetchall()

            print(f'  ─── Recent Ingestion Runs (last {args.limit}) ──────────────────')
            if not rows:
                print('  No runs found.')
            else:
                print(f'  {"ID":<5} {"Bucket":<38} {"Source":<18} {"Status":<10} '
                      f'{"In":>4} {"Started":<20}')
                print('  ' + '─' * 100)
                for r in rows:
                    r = dict(r)
                    print(
                        f'  {r["id"]:<5} '
                        f'{(r.get("bucket_title") or "?")[:36]:<38} '
                        f'{(r.get("source_name") or "")[:16]:<18} '
                        f'{(r.get("status") or ""):<10} '
                        f'{(r.get("images_ingested") or 0):>4} '
                        f'{str(r.get("started_at") or "")[:19]:<20}'
                    )
            print()

    finally:
        conn.close()


if __name__ == '__main__':
    main()
