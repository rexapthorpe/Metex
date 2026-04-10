"""
Exporter — push acquired candidates from local manifests into the Metex
bucket_image_assets table via BucketImageService.

This is the bridge between the acquisition system and the canonical
Metex serving/review system.

Two export modes:
  1. upload  — copy local file into Metex static/uploads and call
               BucketImageService.ingest_from_upload()
  2. url     — call BucketImageService.ingest_from_url() with the
               original remote URL (re-downloads from source)

Default: upload (uses already-downloaded local files — faster, offline-capable).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Ensure Metex root is importable
_METEX_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_METEX_ROOT) not in sys.path:
    sys.path.insert(0, str(_METEX_ROOT))


def _get_service():
    """Lazy-import BucketImageService from Metex."""
    try:
        from services.bucket_image_service import BucketImageService
        return BucketImageService()
    except ImportError as e:
        raise RuntimeError(
            f"Cannot import BucketImageService — is DATABASE_URL set? ({e})"
        )


def _get_db():
    try:
        import database
        return database.get_db_connection()
    except ImportError as e:
        raise RuntimeError(f"Cannot import database module: {e}")


def _resolve_bucket_id(slug: str, conn) -> Optional[int]:
    """Look up standard_bucket id by slug."""
    cur = conn.cursor()
    cur.execute("SELECT id FROM standard_buckets WHERE slug = %s", (slug,))
    row = cur.fetchone()
    return row[0] if row else None


def export_manifest(
    manifest: dict,
    mode: str = "upload",
    min_confidence: float = 0.30,
    statuses: List[str] = ("candidate",),
    dry_run: bool = False,
) -> Dict:
    """
    Export candidates from a single manifest to Metex.

    Args:
        manifest:       loaded manifest dict
        mode:           "upload" (use local file) or "url" (re-download)
        min_confidence: skip below this threshold
        statuses:       only export candidates with these status values
        dry_run:        print plan without writing to DB

    Returns summary dict with counts.
    """
    slug = manifest.get("bucket_slug", "unknown")
    candidates = manifest.get("candidates", [])

    stats = {
        "slug": slug,
        "total": len(candidates),
        "exported": 0,
        "skipped_confidence": 0,
        "skipped_status": 0,
        "skipped_no_file": 0,
        "errors": 0,
    }

    if not candidates:
        return stats

    try:
        bis = _get_service()
        conn = _get_db()
    except RuntimeError as e:
        logger.error("Export setup failed for %s: %s", slug, e)
        stats["errors"] += len(candidates)
        return stats

    bucket_id = manifest.get("bucket_id") or _resolve_bucket_id(slug, conn)
    if not bucket_id:
        logger.warning("No Metex bucket_id found for slug %r — skipping", slug)
        conn.close()
        return stats

    for cand in candidates:
        confidence = cand.get("confidence_score", 0.0)
        status = cand.get("status", "candidate")

        if confidence < min_confidence:
            stats["skipped_confidence"] += 1
            continue
        if status not in statuses:
            stats["skipped_status"] += 1
            continue

        source_info = {
            "source_name":       cand.get("source", "unknown"),
            "source_type":       cand.get("source_type", "unknown"),
            "source_page_url":   cand.get("source_page_url", ""),
            "attribution_text":  cand.get("attribution_text", ""),
            "license_type":      cand.get("license_type", "unknown"),
            "rights_note":       cand.get("rights_note", ""),
            "usage_allowed":     cand.get("usage_allowed", True),
            "raw_source_title":  cand.get("raw_source_title", ""),
            "raw_source_metadata": cand.get("extra_metadata", {}),
        }

        if dry_run:
            logger.info("[DRY RUN] Would export to Metex: %s / conf=%.2f / %s",
                        slug, confidence, cand.get("raw_source_title", "")[:60])
            stats["exported"] += 1
            continue

        try:
            if mode == "upload":
                local_path = cand.get("local_web_path") or cand.get("local_raw_path", "")
                if not local_path or not Path(local_path).exists():
                    logger.debug("Local file missing for %s: %s", slug, local_path)
                    stats["skipped_no_file"] += 1
                    continue
                with open(local_path, "rb") as f:
                    image_bytes = f.read()
                result = bis.ingest_from_upload(
                    bucket_id=bucket_id,
                    image_bytes=image_bytes,
                    filename=Path(local_path).name,
                    source_info=source_info,
                    admin_user_id=None,
                )
            else:
                url = cand.get("original_image_url") or ""
                if not url:
                    stats["skipped_no_file"] += 1
                    continue
                result = bis.ingest_from_url(
                    bucket_id=bucket_id,
                    url=url,
                    source_info=source_info,
                    admin_user_id=None,
                )

            if result.get("error"):
                logger.warning("Metex rejected %s: %s", slug, result["error"])
                stats["errors"] += 1
            else:
                logger.info("Exported to Metex: %s | asset_id=%s | duplicate=%s",
                            slug, result.get("asset_id"), result.get("duplicate"))
                stats["exported"] += 1

        except Exception as e:
            logger.error("Export error for %s: %s", slug, e)
            stats["errors"] += 1

    try:
        conn.close()
    except Exception:
        pass

    return stats


def export_all_manifests(
    manifests_dir: Optional[Path] = None,
    mode: str = "upload",
    min_confidence: float = 0.30,
    slug_filter: Optional[str] = None,
    metal_filter: Optional[str] = None,
    dry_run: bool = False,
) -> List[Dict]:
    """Export all manifests (or filtered subset) to Metex."""
    from pipeline.manifest import all_manifests
    from config.settings import MANIFESTS_DIR as DEFAULT_MF_DIR

    mf_dir = manifests_dir or DEFAULT_MF_DIR
    manifests = all_manifests() if not manifests_dir else [
        __import__("json").loads(p.read_text())
        for p in sorted(mf_dir.glob("*.json"))
    ]

    if slug_filter:
        manifests = [m for m in manifests if m.get("bucket_slug") == slug_filter]
    if metal_filter:
        manifests = [m for m in manifests if m.get("metal", "").lower() == metal_filter.lower()]

    all_stats: List[Dict] = []
    for manifest in manifests:
        stats = export_manifest(
            manifest=manifest,
            mode=mode,
            min_confidence=min_confidence,
            dry_run=dry_run,
        )
        all_stats.append(stats)

    # Summary
    total_exported = sum(s["exported"] for s in all_stats)
    total_errors   = sum(s["errors"] for s in all_stats)
    logger.info("Export complete: %d exported, %d errors across %d manifests",
                total_exported, total_errors, len(all_stats))

    return all_stats
