"""
Bucket Image Coverage Report

Prints a formatted summary of image coverage across all standard buckets.

Usage:
    python scripts/bucket_image_coverage_report.py

    # Include product-family breakdown
    python scripts/bucket_image_coverage_report.py --by-family

    # Per-source breakdown: candidates, activated, pending, rejected
    python scripts/bucket_image_coverage_report.py --by-source

    # List buckets that still have no active cover
    python scripts/bucket_image_coverage_report.py --empty-buckets

    # Show recent ingestion runs too
    python scripts/bucket_image_coverage_report.py --runs [--limit 20]

    # Full detail
    python scripts/bucket_image_coverage_report.py --by-family --by-source --empty-buckets --runs

Output:
  - Overall coverage percentage and counts
  - Per-metal breakdown
  - Product-family breakdown (with --by-family)
  - Per-source breakdown: active / pending / rejected totals (with --by-source)
  - Buckets still empty (no active cover) (with --empty-buckets)
  - Optional: recent ingestion runs table (with --runs)
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
    parser.add_argument('--by-source', action='store_true',
                        help='Show per-source breakdown: active / pending / rejected counts')
    parser.add_argument('--empty-buckets', action='store_true',
                        help='List all buckets with no active cover image')
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

        # Per-source detailed breakdown
        if args.by_source:
            print('  ─── By Source (all candidate statuses) ─────────────')
            by_src = report.get('by_source_detail', {})
            if not by_src:
                print('  (no candidates ingested yet)')
            else:
                print(f'  {"Source":<38}  {"Total":>5}  {"Active":>6}  {"Pending":>7}  '
                      f'{"Approved":>8}  {"Rejected":>8}')
                print('  ' + '─' * 82)
                # Sort: active desc, then total desc
                for sname, s in sorted(by_src.items(),
                                       key=lambda kv: (-kv[1]['active'], -kv[1]['total'])):
                    print(
                        f'  {sname[:36]:<38} '
                        f'{s["total"]:>5}  '
                        f'{s["active"]:>6}  '
                        f'{s["pending"]:>7}  '
                        f'{s["approved"]:>8}  '
                        f'{s["rejected"]:>8}'
                    )
            print()

            # Active-image source summary (compact view)
            by_active = report.get('by_source', {})
            if by_active:
                print('  ─── Active Images by Source ────────────────────────')
                for src, cnt in sorted(by_active.items(), key=lambda x: -x[1]):
                    print(f'  {src:<40} {cnt:>4} image{"s" if cnt != 1 else ""}')
                print()

        elif report.get('by_source'):
            # Default: show active-only source breakdown when --by-source not set
            by_active = report.get('by_source', {})
            print('  ─── Active Images by Source ────────────────────────')
            for src, cnt in sorted(by_active.items(), key=lambda x: -x[1]):
                print(f'  {src:<40} {cnt:>4} image{"s" if cnt != 1 else ""}')
            print()

        # Empty buckets list
        if args.empty_buckets:
            empty = report.get('empty_buckets', [])
            print(f'  ─── Buckets With No Active Cover ({len(empty)} total) ────────────────')
            if not empty:
                print('  All buckets have an active cover image. ✓')
            else:
                print(f'  {"Metal":<10}  {"Title":<44}  {"Pending":>7}  {"Status"}')
                print('  ' + '─' * 76)
                for b in empty:
                    pnd  = b.get('pending_count') or 0
                    tot  = b.get('total_assets') or 0
                    flag = '⏳' if pnd > 0 else '✗'
                    print(
                        f'  {(b["metal"] or "?")[:8]:<10} '
                        f'  {b["title"][:42]:<44} '
                        f'  {pnd:>7} '
                        f'  {flag}'
                    )
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
                print(f'  {"ID":<5} {"Bucket":<38} {"Source":<22} {"Status":<10} '
                      f'{"In":>4} {"Started":<20}')
                print('  ' + '─' * 104)
                for r in rows:
                    r = dict(r)
                    print(
                        f'  {r["id"]:<5} '
                        f'{(r.get("bucket_title") or "?")[:36]:<38} '
                        f'{(r.get("source_name") or "")[:20]:<22} '
                        f'{(r.get("status") or ""):<10} '
                        f'{(r.get("images_ingested") or 0):>4} '
                        f'{str(r.get("started_at") or "")[:19]:<20}'
                    )
            print()

    finally:
        conn.close()


if __name__ == '__main__':
    main()
