"""
Coverage report generator.

Reads all manifests in data/manifests/ and produces:
  - Per-bucket candidate counts and coverage status
  - Empty buckets (no candidates)
  - By-metal breakdown
  - By-family breakdown
  - By-source breakdown
  - Confidence distribution
  - Duplicate rate

Usage:
    python -m reports.coverage_report
    python -m reports.coverage_report --metal gold
    python -m reports.coverage_report --json
    python -m reports.coverage_report --out reports/coverage_2024.txt
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from config.settings import MANIFESTS_DIR, REPORTS_DIR
from pipeline.manifest import all_manifests
from pipeline.bucket_loader import load_buckets


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def build_report(
    metal_filter: Optional[str] = None,
    family_filter: Optional[str] = None,
) -> Dict:
    """
    Build a comprehensive coverage report dict.
    """
    manifests = all_manifests()
    all_buckets = load_buckets(use_db=False, use_cache=True)

    # Index manifests by slug
    mf_by_slug: Dict[str, dict] = {m["bucket_slug"]: m for m in manifests}

    if metal_filter:
        all_buckets = [b for b in all_buckets if b.get("metal", "").lower() == metal_filter.lower()]
    if family_filter:
        all_buckets = [b for b in all_buckets
                       if family_filter.lower() in (b.get("product_family") or "").lower()]

    total_buckets = len(all_buckets)
    covered_buckets = 0
    empty_buckets: List[str] = []

    by_metal: Dict[str, Dict] = defaultdict(lambda: {"total": 0, "covered": 0, "candidates": 0})
    by_family: Dict[str, Dict] = defaultdict(lambda: {"total": 0, "covered": 0, "candidates": 0})
    by_source: Counter = Counter()
    by_status: Counter = Counter()
    confidence_values: List[float] = []
    duplicate_checksums: List[str] = []
    seen_checksums: set = set()

    bucket_rows: List[Dict] = []

    for bucket in all_buckets:
        slug   = bucket.get("slug", "")
        metal  = bucket.get("metal", "other")
        family = bucket.get("product_family") or bucket.get("form", "other")

        mf = mf_by_slug.get(slug)
        candidates = mf.get("candidates", []) if mf else []
        n_cands = len(candidates)

        by_metal[metal]["total"] += 1
        by_family[family]["total"] += 1

        if n_cands > 0:
            covered_buckets += 1
            by_metal[metal]["covered"] += 1
            by_family[family]["covered"] += 1
            by_metal[metal]["candidates"] += n_cands
            by_family[family]["candidates"] += n_cands

            for c in candidates:
                src = c.get("source", "unknown")
                by_source[src] += 1
                by_status[c.get("status", "unknown")] += 1
                conf = c.get("confidence_score")
                if conf is not None:
                    confidence_values.append(float(conf))
                cs = c.get("checksum", "")
                if cs:
                    if cs in seen_checksums:
                        duplicate_checksums.append(cs)
                    else:
                        seen_checksums.add(cs)
        else:
            empty_buckets.append(slug)

        bucket_rows.append({
            "slug": slug,
            "title": bucket.get("title", slug),
            "metal": metal,
            "family": family,
            "candidates": n_cands,
            "covered": n_cands > 0,
            "top_confidence": max(
                (c.get("confidence_score", 0) for c in candidates), default=0
            ),
        })

    # Confidence histogram
    conf_dist = {"<0.3": 0, "0.3-0.5": 0, "0.5-0.7": 0, "0.7-0.85": 0, ">=0.85": 0}
    for v in confidence_values:
        if v < 0.3:       conf_dist["<0.3"] += 1
        elif v < 0.5:     conf_dist["0.3-0.5"] += 1
        elif v < 0.7:     conf_dist["0.5-0.7"] += 1
        elif v < 0.85:    conf_dist["0.7-0.85"] += 1
        else:             conf_dist[">=0.85"] += 1

    total_candidates = sum(by_source.values())
    dup_rate = len(duplicate_checksums) / max(len(seen_checksums) + len(duplicate_checksums), 1)

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "filters": {"metal": metal_filter, "family": family_filter},
        "summary": {
            "total_buckets": total_buckets,
            "covered_buckets": covered_buckets,
            "empty_buckets": len(empty_buckets),
            "coverage_pct": round(100 * covered_buckets / max(total_buckets, 1), 1),
            "total_candidates": total_candidates,
            "unique_images": len(seen_checksums),
            "duplicate_count": len(duplicate_checksums),
            "duplicate_rate_pct": round(100 * dup_rate, 1),
        },
        "empty_buckets": sorted(empty_buckets),
        "by_metal": {
            k: {
                "total": v["total"],
                "covered": v["covered"],
                "coverage_pct": round(100 * v["covered"] / max(v["total"], 1), 1),
                "candidates": v["candidates"],
            }
            for k, v in sorted(by_metal.items())
        },
        "by_family": {
            k: {
                "total": v["total"],
                "covered": v["covered"],
                "coverage_pct": round(100 * v["covered"] / max(v["total"], 1), 1),
                "candidates": v["candidates"],
            }
            for k, v in sorted(by_family.items())
        },
        "by_source": dict(by_source.most_common()),
        "by_status": dict(by_status.most_common()),
        "confidence_distribution": conf_dist,
        "bucket_detail": sorted(bucket_rows, key=lambda r: (r["metal"], r["family"], r["slug"])),
    }


def print_report(report: Dict, out=None) -> None:
    """Pretty-print coverage report to stdout or file."""
    out = out or sys.stdout
    s = report["summary"]
    f = report["filters"]

    def w(line=""):
        print(line, file=out)

    w("=" * 72)
    w(f"  METEX BUCKET IMAGE ACQUISITION — COVERAGE REPORT")
    w(f"  Generated: {report['generated_at']}")
    if f["metal"] or f["family"]:
        w(f"  Filters: metal={f['metal']!r}  family={f['family']!r}")
    w("=" * 72)
    w()
    w(f"  Total buckets  : {s['total_buckets']}")
    w(f"  Covered        : {s['covered_buckets']} ({s['coverage_pct']}%)")
    w(f"  Empty          : {s['empty_buckets']}")
    w(f"  Total candidates: {s['total_candidates']}")
    w(f"  Unique images  : {s['unique_images']}")
    w(f"  Duplicate rate : {s['duplicate_rate_pct']}%")
    w()
    w("── BY METAL " + "─" * 60)
    for metal, mv in report["by_metal"].items():
        w(f"  {metal:<12} {mv['covered']:>3}/{mv['total']:<3} ({mv['coverage_pct']:5.1f}%)  "
          f"  {mv['candidates']} candidates")
    w()
    w("── BY FAMILY " + "─" * 58)
    for fam, fv in report["by_family"].items():
        w(f"  {fam:<28} {fv['covered']:>3}/{fv['total']:<3} ({fv['coverage_pct']:5.1f}%)  "
          f"  {fv['candidates']} candidates")
    w()
    w("── BY SOURCE " + "─" * 58)
    for src, cnt in report["by_source"].items():
        w(f"  {src:<36} {cnt:>5}")
    w()
    w("── CONFIDENCE DISTRIBUTION " + "─" * 44)
    for band, cnt in report["confidence_distribution"].items():
        bar = "█" * min(cnt, 40)
        w(f"  {band:<10} {cnt:>5}  {bar}")
    w()
    if report["empty_buckets"]:
        w("── EMPTY BUCKETS " + "─" * 53)
        for slug in report["empty_buckets"]:
            w(f"  {slug}")
    w()
    w("=" * 72)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse():
    p = argparse.ArgumentParser(description="Coverage report for bucket image acquisition")
    p.add_argument("--metal",   help="Filter by metal")
    p.add_argument("--family",  help="Filter by product family")
    p.add_argument("--json",    dest="as_json", action="store_true", help="Output as JSON")
    p.add_argument("--out",     dest="out_file", help="Write to file instead of stdout")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse()
    report = build_report(metal_filter=args.metal, family_filter=args.family)

    if args.as_json:
        output = json.dumps(report, indent=2)
        if args.out_file:
            Path(args.out_file).write_text(output)
            print(f"Report written to {args.out_file}")
        else:
            print(output)
    else:
        if args.out_file:
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            with open(args.out_file, "w") as f:
                print_report(report, out=f)
            print(f"Report written to {args.out_file}")
        else:
            print_report(report)
