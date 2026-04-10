#!/usr/bin/env python3
"""
Rebuild / repair manifests from the files already on disk in catalog/.

Use this if manifests were deleted or become out of sync with what's
actually downloaded. Scans catalog/ for image files, re-computes checksums,
and writes fresh manifests.

Usage:
    cd Metex/bucket_image_acquisition
    python scripts/rebuild_manifests.py
    python scripts/rebuild_manifests.py --metal gold
    python scripts/rebuild_manifests.py --slug gold-american-eagle-1oz
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import CATALOG_DIR, MANIFESTS_DIR, SLUG_TO_CATALOG, catalog_dir_for_slug
from pipeline.bucket_loader import load_buckets
from pipeline.manifest import load_manifest, save_manifest


def checksum_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rebuild_manifest_for_slug(slug: str, bucket: dict) -> dict:
    """Scan catalog dir for this slug and rebuild the manifest."""
    catalog_dir = catalog_dir_for_slug(slug)
    manifest = load_manifest(slug)
    manifest["bucket_id"] = bucket.get("id")

    # Index existing candidate checksums
    existing = {c["checksum"]: c for c in manifest.get("candidates", []) if c.get("checksum")}

    # Find image files in catalog dir (not in thumbs/)
    images = [
        f for f in catalog_dir.glob(f"{slug}_*.jpg")
        if "thumb" not in f.name and f.is_file()
    ]

    added = 0
    for img_path in images:
        cs = checksum_file(img_path)
        if cs in existing:
            continue  # Already in manifest

        thumb_path = catalog_dir / "thumbs" / img_path.name.replace(".jpg", "_thumb.jpg")
        raw_path = catalog_dir  # best guess

        # Parse source from filename: {slug}_{source}_{key8}.jpg
        parts = img_path.stem.split("_")
        source_short = parts[1] if len(parts) > 1 else "unknown"

        record = {
            "id": cs[:16],
            "source": source_short,
            "source_type": "unknown",
            "source_page_url": "",
            "original_image_url": "",
            "raw_source_title": img_path.stem,
            "license_type": "unknown",
            "attribution_text": "",
            "rights_note": "",
            "usage_allowed": True,
            "extra_metadata": {},
            "confidence_score": 0.0,
            "warnings": ["rebuilt_from_disk"],
            "status": "candidate",
            "acquired_at": "unknown",
            "checksum": cs,
            "width": 0, "height": 0,
            "mime_type": "image/jpeg",
            "file_size": img_path.stat().st_size,
            "local_web_path": str(img_path),
            "local_thumb_path": str(thumb_path) if thumb_path.exists() else "",
            "local_raw_path": "",
        }
        manifest["candidates"].append(record)
        added += 1

    save_manifest(manifest)
    return {"slug": slug, "added": added, "total": len(manifest["candidates"])}


def main():
    p = argparse.ArgumentParser(description="Rebuild manifests from disk")
    p.add_argument("--metal", help="Filter by metal")
    p.add_argument("--slug",  help="Single bucket slug")
    args = p.parse_args()

    buckets = load_buckets(use_db=False, use_cache=True)

    if args.slug:
        buckets = [b for b in buckets if b.get("slug") == args.slug]
    if args.metal:
        buckets = [b for b in buckets if b.get("metal", "").lower() == args.metal.lower()]

    total_added = 0
    for bucket in buckets:
        result = rebuild_manifest_for_slug(bucket["slug"], bucket)
        if result["added"] > 0:
            print(f"  {result['slug']}: added {result['added']} files (total: {result['total']})")
        total_added += result["added"]

    print(f"\nRebuild complete. Added {total_added} records across {len(buckets)} buckets.")


if __name__ == "__main__":
    main()
