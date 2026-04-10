"""
Image processor: validate, resize, save web/thumb copies.

Writes to:
  catalog/<metal>/<family>/<slug>_<source_short>_<key8>.jpg   (web 1200px)
  catalog/<metal>/<family>/thumbs/<slug>_<source_short>_<key8>_thumb.jpg
  data/raw/<key16><ext>   (original bytes)
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False
    logger.warning("Pillow not installed — image processing disabled")

# Limits
WEB_MAX_PX    = 1200
THUMB_MAX_PX  = 400
WEB_QUALITY   = 85
THUMB_QUALITY = 80
MAX_PIXELS    = 25_000_000

MIME_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png":  ".png",
    "image/webp": ".webp",
}


def _detect_mime(data: bytes) -> str:
    """Detect image MIME type from magic bytes."""
    if data[:3] == b'\xff\xd8\xff':
        return "image/jpeg"
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if data[:4] in (b'RIFF',) and data[8:12] == b'WEBP':
        return "image/webp"
    return "unknown"


def validate_image(data: bytes) -> Tuple[bool, str, int, int]:
    """
    Validate image bytes.
    Returns (ok, mime_type, width, height).
    """
    if not _PIL_AVAILABLE:
        mime = _detect_mime(data)
        return (mime != "unknown"), mime, 0, 0

    try:
        buf = io.BytesIO(data)
        img = Image.open(buf)
        img.verify()
        # Re-open after verify (verify closes the stream)
        buf.seek(0)
        img = Image.open(buf)
        w, h = img.size
        if w * h > MAX_PIXELS:
            return False, "image/oversized", w, h
        mime = Image.MIME.get(img.format, "image/unknown")
        return True, mime, w, h
    except Exception as e:
        logger.debug("Image validation failed: %s", e)
        return False, "invalid", 0, 0


def _to_rgb(img):
    """Flatten transparency to white, convert to RGB."""
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
        return bg
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def _resize(img, max_px: int):
    """Resize maintaining aspect ratio, only if larger than max_px."""
    w, h = img.size
    if max(w, h) <= max_px:
        return img
    ratio = max_px / max(w, h)
    return img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)


def _save_jpeg(img, path: Path, quality: int) -> None:
    """Save PIL image as JPEG, strip EXIF."""
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    path.write_bytes(buf.getvalue())


def process_image(
    data: bytes,
    storage_key: str,   # first 16 chars of checksum
    slug: str,
    source_short: str,  # short source label for filename
    catalog_dir: Path,
    raw_dir: Path,
) -> Optional[dict]:
    """
    Validate, save original, create web + thumb copies.

    Returns dict with:
        mime_type, width, height, file_size,
        raw_path, web_path, thumb_path
    (all as str, relative to bucket_image_acquisition root)
    Or None if validation fails.
    """
    ok, mime, width, height = validate_image(data)
    if not ok:
        return None
    if mime not in {"image/jpeg", "image/png", "image/webp"}:
        return None

    ext = MIME_TO_EXT.get(mime, ".jpg")
    key8 = storage_key[:8]
    safe_source = source_short.replace(" ", "_").lower()[:16]
    slug = slug.replace("/", "-")  # sanitize slugs like "gold-bar-1/4oz"

    # Save raw original
    raw_path = raw_dir / f"{storage_key}{ext}"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(data)

    if not _PIL_AVAILABLE:
        return {
            "mime_type": mime,
            "width": width,
            "height": height,
            "file_size": len(data),
            "raw_path": str(raw_path),
            "web_path": str(raw_path),   # no processing available
            "thumb_path": str(raw_path),
        }

    # Process
    img = Image.open(io.BytesIO(data))
    img = _to_rgb(img)
    width, height = img.size

    fname_base = f"{slug}_{safe_source}_{key8}"

    # Web copy
    web_img = _resize(img.copy(), WEB_MAX_PX)
    web_path = catalog_dir / f"{fname_base}.jpg"
    _save_jpeg(web_img, web_path, WEB_QUALITY)

    # Thumb copy
    thumb_img = _resize(img.copy(), THUMB_MAX_PX)
    thumb_path = catalog_dir / "thumbs" / f"{fname_base}_thumb.jpg"
    _save_jpeg(thumb_img, thumb_path, THUMB_QUALITY)

    return {
        "mime_type": mime,
        "width": width,
        "height": height,
        "file_size": len(data),
        "raw_path": str(raw_path),
        "web_path": str(web_path),
        "thumb_path": str(thumb_path),
    }
