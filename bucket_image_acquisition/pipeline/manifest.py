"""
Manifest management — read/write per-bucket JSON manifests.

Each manifest file lives at:
    data/manifests/<slug>.json

Format:
{
  "bucket_slug": "gold-american-eagle-1oz",
  "bucket_id": 1,              # from Metex DB (if known)
  "metal": "gold",
  "family": "gold/eagles",
  "last_updated": "2024-01-01T12:00:00Z",
  "candidates": [ <Candidate record>, ... ]
}

Candidate record fields:
  id (str), source, source_type, source_priority,
  source_page_url, original_image_url,
  local_web_path, local_thumb_path, local_raw_path,
  checksum, width, height, mime_type, file_size,
  raw_source_title, license_type, attribution_text, rights_note,
  usage_allowed, extra_metadata,
  confidence_score, warnings, status, acquired_at
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from config.settings import MANIFESTS_DIR, catalog_dir_for_slug


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def manifest_path(slug: str) -> Path:
    # Sanitize slug to be safe as a filename (replace / with -)
    safe_slug = slug.replace("/", "-")
    return MANIFESTS_DIR / f"{safe_slug}.json"


def load_manifest(slug: str) -> dict:
    """Load manifest for slug. Returns empty manifest if not found."""
    path = manifest_path(slug)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {
        "bucket_slug": slug,
        "bucket_id": None,
        "metal": slug.split("-")[0] if "-" in slug else "",
        "family": str(catalog_dir_for_slug(slug).relative_to(
            catalog_dir_for_slug(slug).parent.parent
        )),
        "last_updated": _now_iso(),
        "candidates": [],
    }


def save_manifest(manifest: dict) -> None:
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
    manifest["last_updated"] = _now_iso()
    path = manifest_path(manifest["bucket_slug"])
    path.write_text(json.dumps(manifest, indent=2))


def add_candidate(
    manifest: dict,
    candidate: dict,       # from adapter.find_candidates()
    image_info: Optional[dict],  # from processor.process_image()
    confidence_score: float,
    warnings: List[str],
    status: str = "candidate",
) -> dict:
    """
    Build and append a candidate record to the manifest.

    Returns the candidate record dict.
    """
    record = {
        "id": str(uuid.uuid4()),
        "source": candidate.get("source_name", "unknown"),
        "source_type": candidate.get("source_type", "unknown"),
        "source_page_url": candidate.get("source_page_url", ""),
        "original_image_url": candidate.get("original_image_url") or candidate.get("url", ""),
        "raw_source_title": candidate.get("raw_source_title", ""),
        "license_type": candidate.get("license_type", "unknown"),
        "attribution_text": candidate.get("attribution_text", ""),
        "rights_note": candidate.get("rights_note", ""),
        "usage_allowed": candidate.get("usage_allowed", True),
        "extra_metadata": candidate.get("extra_metadata", {}),
        "confidence_score": round(confidence_score, 4),
        "warnings": warnings,
        "status": status,
        "acquired_at": _now_iso(),
    }

    if image_info:
        record.update({
            "checksum": "",    # set by caller after download
            "width": image_info.get("width", 0),
            "height": image_info.get("height", 0),
            "mime_type": image_info.get("mime_type", ""),
            "file_size": image_info.get("file_size", 0),
            "local_web_path": image_info.get("web_path", ""),
            "local_thumb_path": image_info.get("thumb_path", ""),
            "local_raw_path": image_info.get("raw_path", ""),
        })
    else:
        record.update({
            "checksum": "",
            "width": 0, "height": 0,
            "mime_type": "", "file_size": 0,
            "local_web_path": "", "local_thumb_path": "", "local_raw_path": "",
        })

    manifest["candidates"].append(record)
    return record


def get_existing_checksums(slug: str) -> set:
    """Return set of checksums already in the manifest for this slug."""
    manifest = load_manifest(slug)
    return {c.get("checksum", "") for c in manifest.get("candidates", []) if c.get("checksum")}


def all_manifests() -> List[dict]:
    """Load and return all manifests in MANIFESTS_DIR."""
    results = []
    for path in sorted(MANIFESTS_DIR.glob("*.json")):
        try:
            results.append(json.loads(path.read_text()))
        except Exception:
            continue
    return results
