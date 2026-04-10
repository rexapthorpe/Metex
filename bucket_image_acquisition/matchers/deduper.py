"""
Deduplication helpers.

Two strategies:
  1. Exact: SHA-256 hash match (byte-identical images)
  2. Perceptual: phash (requires imagehash library; gracefully skipped if absent)

The deduper operates on the local manifest/catalog only — it does NOT
query the Metex database. That dedup layer happens at export time.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, Optional, Set


# ---------------------------------------------------------------------------
# Exact deduplication
# ---------------------------------------------------------------------------

class ExactDeduper:
    """Track SHA-256 hashes seen during an acquisition run."""

    def __init__(self) -> None:
        self._seen: Set[str] = set()

    def add(self, checksum: str) -> None:
        self._seen.add(checksum)

    def is_duplicate(self, checksum: str) -> bool:
        return checksum in self._seen

    def load_from_manifests(self, manifests_dir: Path) -> None:
        """Pre-populate from all existing manifest JSON files."""
        for mf in manifests_dir.glob("*.json"):
            try:
                data = json.loads(mf.read_text())
                for c in data.get("candidates", []):
                    cs = c.get("checksum") or ""
                    if cs:
                        self._seen.add(cs)
            except Exception:
                pass

    @staticmethod
    def hash_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Perceptual deduplication (optional)
# ---------------------------------------------------------------------------

try:
    import imagehash
    from PIL import Image
    import io
    _PHASH_AVAILABLE = True
except ImportError:
    _PHASH_AVAILABLE = False


class PerceptualDeduper:
    """
    Detect visually similar images using perceptual hashing.

    Requires: pip install imagehash Pillow
    Falls back to no-op if not installed.
    """

    def __init__(self, threshold: int = 8) -> None:
        """threshold: max hamming distance to consider as duplicate (0=identical)."""
        self.threshold = threshold
        self._hashes: Dict[str, str] = {}  # checksum → phash_str

    def available(self) -> bool:
        return _PHASH_AVAILABLE

    def compute_phash(self, image_bytes: bytes) -> Optional[str]:
        if not _PHASH_AVAILABLE:
            return None
        try:
            img = Image.open(io.BytesIO(image_bytes))
            return str(imagehash.phash(img))
        except Exception:
            return None

    def is_perceptual_duplicate(self, phash_str: str) -> bool:
        if not _PHASH_AVAILABLE or not phash_str:
            return False
        try:
            new_hash = imagehash.hex_to_hash(phash_str)
            for existing_str in self._hashes.values():
                existing = imagehash.hex_to_hash(existing_str)
                if abs(new_hash - existing) <= self.threshold:
                    return True
        except Exception:
            pass
        return False

    def add(self, checksum: str, phash_str: str) -> None:
        if phash_str:
            self._hashes[checksum] = phash_str
