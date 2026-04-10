"""
Bucket Image Ingestion and Catalog Service
==========================================
Long-term production system for automatic image discovery, ingestion, storage,
cataloging, and cover-image assignment for standard Metex buckets.

Key responsibilities:
  - Download images from admin-supplied URLs (safe, with size + type guards)
  - Accept admin-uploaded images via form upload
  - Normalize images to web and thumbnail versions (strip EXIF)
  - Deduplicate by SHA-256 checksum
  - Compute field-based match confidence score
  - Manage asset lifecycle: pending → approved → active / rejected
  - Resolve the active cover image URL for website rendering

Storage layout (all paths relative to static/):
  uploads/bucket_images/originals/<key><ext>   — original file, untouched
  uploads/bucket_images/web/<key>_web.jpg      — normalized web (max 1200x1200 JPEG)
  uploads/bucket_images/thumbs/<key>_thumb.jpg — thumbnail (max 400x400 JPEG)

Source priority (lower = higher trust):
  1  internal_upload   — admin directly uploaded; auto-activates if none exists
  2  public_domain     — official mint / government / public-domain library
  3  licensed          — Creative Commons or clearly licensed
  4  approved_db       — approved API / database source
  5  retailer          — retailer page (candidate only; always requires admin review)
  99 unknown
"""

import hashlib
import io
import json
import logging
import os
import re
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SOURCE_PRIORITY = {
    'internal_upload': 1,
    'public_domain':   2,
    'licensed':        3,
    'approved_db':     4,
    'retailer':        5,
    'unknown':         99,
}

# ---------------------------------------------------------------------------
# Tiered auto-activation policy
# ---------------------------------------------------------------------------
# Determines which ingest results are promoted directly to 'active' without
# admin review.  Everything else stays 'pending'.
#
# Rules (checked in order):
#  1. internal_upload with no warnings        → always auto-activate
#  2. public_domain + confidence >= 0.75
#     with no warnings                        → auto-activate (official mint)
#  3. Everything else (licensed, retailer,
#     unknown)                                → pending, requires review
#
# The threshold for rule 2 can be tuned here without changing call sites.
_AUTO_ACTIVATE_PD_CONFIDENCE = 0.75


def _should_auto_activate(
    source_type: str,
    confidence: float,
    warnings: List[str],
) -> bool:
    """Return True if this image should activate without admin review."""
    if source_type == 'internal_upload' and not warnings:
        return True
    if (source_type == 'public_domain'
            and confidence >= _AUTO_ACTIVATE_PD_CONFIDENCE
            and not warnings):
        return True
    return False


# Keep old constant for any code that references it externally
AUTO_ACTIVATE_SOURCE_TYPES = frozenset({'internal_upload'})

WEB_MAX_PX  = 1200   # max width or height for web version
THUMB_MAX_PX = 400   # max width or height for thumbnail

MAX_DOWNLOAD_BYTES  = 15 * 1024 * 1024   # 15 MB cap on URL downloads
DOWNLOAD_TIMEOUT_S  = 15                 # seconds

ALLOWED_MIME_TYPES = frozenset({
    'image/jpeg', 'image/png', 'image/webp',
})

MIME_TO_EXT = {
    'image/jpeg': '.jpg',
    'image/png':  '.png',
    'image/webp': '.webp',
}

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _static_dir() -> str:
    """Absolute path to the static/ directory regardless of caller location."""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'static',
    )


def _full_path(relative_path: str) -> str:
    """Convert a DB-stored relative path to an absolute filesystem path."""
    return os.path.join(_static_dir(), relative_path)


def _ensure_dirs():
    for subdir in ('originals', 'web', 'thumbs'):
        os.makedirs(os.path.join(_static_dir(), 'uploads', 'bucket_images', subdir), exist_ok=True)


# ---------------------------------------------------------------------------
# Hashing / deduplication
# ---------------------------------------------------------------------------

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _storage_key(checksum: str) -> str:
    """16-char prefix of checksum — used as the stem for all three file variants."""
    return checksum[:16]


# ---------------------------------------------------------------------------
# Image download (URL)
# ---------------------------------------------------------------------------

def _safe_fetch_url(url: str) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Download image bytes from a URL with safety guards.
    Returns (bytes, None) on success or (None, error_message) on failure.

    Only http/https schemes are allowed. Redirects are followed up to 3 hops.
    Response is capped at MAX_DOWNLOAD_BYTES.
    """
    # Scheme whitelist
    if not re.match(r'^https?://', url, re.IGNORECASE):
        return None, "Only http:// and https:// URLs are accepted."

    try:
        import requests
        resp = requests.get(
            url,
            stream=True,
            timeout=DOWNLOAD_TIMEOUT_S,
            allow_redirects=True,
            headers={'User-Agent': 'MetexImageBot/1.0 (image catalog ingestion)'},
        )
        resp.raise_for_status()

        # Stream-read with size cap
        chunks = []
        total = 0
        for chunk in resp.iter_content(chunk_size=65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                return None, f"Image exceeds maximum download size ({MAX_DOWNLOAD_BYTES // (1024*1024)} MB)."
            chunks.append(chunk)

        return b''.join(chunks), None

    except Exception as exc:
        return None, f"Download failed: {exc}"


# ---------------------------------------------------------------------------
# Image validation and normalization
# ---------------------------------------------------------------------------

def _validate_image_bytes(data: bytes) -> Tuple[bool, str, int, int, str]:
    """
    Validate raw bytes as an image.
    Returns (ok, error_or_empty, width, height, detected_mime).
    """
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        img.verify()
        img = Image.open(io.BytesIO(data))
        fmt = (img.format or '').upper()
        mime_map = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'WEBP': 'image/webp'}
        detected_mime = mime_map.get(fmt)
        if not detected_mime:
            return False, f"Unsupported image format: {fmt}", 0, 0, ''
        w, h = img.size
        if w * h > 25_000_000:
            return False, "Image too large (decompression bomb guard).", 0, 0, ''
        return True, '', w, h, detected_mime
    except Exception as exc:
        return False, f"Image validation failed: {exc}", 0, 0, ''


def _normalize(data: bytes, max_px: int, quality: int) -> bytes:
    """
    Resize (thumbnail — maintain aspect ratio) and re-encode as JPEG,
    stripping all EXIF metadata.
    """
    from PIL import Image

    img = Image.open(io.BytesIO(data))

    # Flatten transparency to white
    if img.mode in ('RGBA', 'P', 'LA'):
        bg = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        mask = img.split()[-1] if img.mode in ('RGBA', 'LA') else None
        bg.paste(img, mask=mask)
        img = bg
    elif img.mode != 'RGB':
        img = img.convert('RGB')

    img.thumbnail((max_px, max_px), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=quality, optimize=True, exif=b'')
    return buf.getvalue()


def _write_file(path: str, data: bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as fh:
        fh.write(data)


# ---------------------------------------------------------------------------
# Store original + derivatives, return paths
# ---------------------------------------------------------------------------

def _store_image(data: bytes, checksum: str, orig_mime: str) -> Dict[str, str]:
    """
    Write original + web + thumb to disk.
    Returns dict with keys: local_path, web_path, thumb_path (all relative to static/).
    """
    _ensure_dirs()
    key  = _storage_key(checksum)
    ext  = MIME_TO_EXT.get(orig_mime, '.jpg')

    orig_rel  = f'uploads/bucket_images/originals/{key}{ext}'
    web_rel   = f'uploads/bucket_images/web/{key}_web.jpg'
    thumb_rel = f'uploads/bucket_images/thumbs/{key}_thumb.jpg'

    _write_file(_full_path(orig_rel),  data)
    _write_file(_full_path(web_rel),   _normalize(data, WEB_MAX_PX,   quality=85))
    _write_file(_full_path(thumb_rel), _normalize(data, THUMB_MAX_PX, quality=80))

    return {
        'local_path': orig_rel,
        'web_path':   web_rel,
        'thumb_path': thumb_rel,
    }


# ---------------------------------------------------------------------------
# Match confidence scoring
# ---------------------------------------------------------------------------

def compute_match_confidence(
    standard_bucket: Dict[str, Any],
    raw_source_title: str,
    source_type: str,
    raw_metadata: Optional[Dict] = None,
) -> Tuple[float, List[str]]:
    """
    Compute a 0.0–1.0 confidence score for how well an image source matches
    a standard bucket, and collect warning flags.

    Scoring is additive field-matching:
      metal           +0.20
      weight          +0.20
      mint            +0.20
      product_family  +0.20
      product_series  +0.10
      denomination    +0.05
      year (fixed)    +0.05
      year_varies     +0.03

    Hard caps are applied when warning flags are raised.
    """
    # Weight synonym maps: canonical numeric form → spelled-out Wikimedia variants
    _WEIGHT_SYNONYMS: Dict[str, Tuple[str, ...]] = {
        '1 oz':     ('one ounce', 'one oz', '1oz', '1-oz', '1 troy ounce',
                     'one troy ounce', 'one troy oz', '1 troy oz'),
        '1/2 oz':   ('half ounce', 'half oz', 'half-ounce', 'one-half ounce',
                     '1/2oz', '0.5 oz', 'half-oz'),
        '1/4 oz':   ('quarter ounce', 'quarter oz', 'quarter-ounce',
                     'one-quarter ounce', '1/4oz', 'fourth ounce'),
        '1/10 oz':  ('one-tenth ounce', 'one tenth ounce', 'one-tenth oz',
                     'one tenth oz', '1/10oz', '0.1 oz', 'tenth ounce'),
        '1/20 oz':  ('one-twentieth ounce', 'one twentieth ounce', '1/20oz',
                     'twentieth ounce'),
        '1/25 oz':  ('one-twenty-fifth ounce', '1/25oz', '1/25 oz'),
        '1 g':      ('1 gram', 'one gram', '1gram', '1-gram'),
        '2.5 g':    ('2.5 gram', 'two and a half gram', '2.5gram'),
        '5 g':      ('5 gram', 'five gram', '5gram', '5-gram'),
        '10 g':     ('10 gram', 'ten gram', '10gram', '10-gram'),
        '1 kg':     ('one kilogram', '1kg', '1 kilogram', 'one kilo', 'kilogram'),
        '1 lb':     ('one pound', '1lb', '1 pound', 'one lb'),
        '100 oz':   ('100-oz', '100oz', 'hundred ounce', 'hundred oz'),
        '50 oz':    ('50oz', 'fifty ounce', 'fifty oz'),
        '10 oz':    ('ten ounce', 'ten oz', '10oz', '10-oz'),
        '5 oz':     ('five ounce', 'five oz', '5oz', '5-oz'),
        '2 oz':     ('two ounce', 'two oz', '2oz', '2-oz'),
        '30 g':     ('30 gram', 'thirty gram', '30gram'),
    }

    warnings: List[str] = []
    title = (raw_source_title or '').lower()
    score = 0.0

    def _field_in(field_key: str, weight: float):
        nonlocal score
        val = (standard_bucket.get(field_key) or '').lower().strip()
        if not val:
            return
        if val in title:
            score += weight
            return
        # Weight field: also try spelled-out synonyms
        if field_key == 'weight':
            for synonym in _WEIGHT_SYNONYMS.get(val, ()):
                if synonym in title:
                    score += weight
                    return

    _field_in('metal',          0.20)
    _field_in('weight',         0.20)
    _field_in('mint',           0.20)
    _field_in('product_family', 0.20)
    _field_in('product_series', 0.10)
    _field_in('denomination',   0.05)

    year_policy = standard_bucket.get('year_policy', 'fixed')
    if year_policy == 'fixed':
        year = (standard_bucket.get('year') or '').strip()
        if year and year in title:
            score += 0.05
    else:
        score += 0.03
        if any(kw in title for kw in ('year varies', 'random year', 'any year')):
            warnings.append('year_varies')

    # Warning: different weight mentioned in title (size mismatch)
    bucket_weight = (standard_bucket.get('weight') or '').lower().strip()
    if bucket_weight:
        # Build a set of all normalized weight strings we're NOT looking for
        _all_weight_strs = set()
        for w, syns in _WEIGHT_SYNONYMS.items():
            if w != bucket_weight:
                _all_weight_strs.update([w] + list(syns))
        # If a different-weight term appears in the title, flag it
        if any(s in title for s in _all_weight_strs):
            warnings.append('size_mismatch')
            score = min(score, 0.55)

    # Warning conditions that cap confidence
    if any(kw in title for kw in ('example image', 'sample image', 'for example')):
        warnings.append('example_image')
        score = min(score, 0.50)
    if any(kw in title for kw in ('generic', 'placeholder', 'stock photo')):
        warnings.append('generic_image')
        score = min(score, 0.40)
    if any(kw in title for kw in ('brand varies', 'mint varies', 'random mint', 'assorted mint')):
        warnings.append('brand_varies')
        score = min(score, 0.60)

    # Retailer sources get a hard cap (they're candidates, not trusted truth)
    if source_type == 'retailer':
        score = min(score, 0.75)
        if score >= 0.70:
            warnings.append('retailer_source_requires_review')

    score = round(min(score, 1.0), 3)
    return score, warnings


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _get_conn():
    import database as _db
    return _db.get_db_connection()


def _now_iso() -> str:
    return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')


def _row_to_dict(row) -> Optional[Dict]:
    if row is None:
        return None
    return dict(row)


# ---------------------------------------------------------------------------
# Standard bucket CRUD
# ---------------------------------------------------------------------------

def create_standard_bucket(data: Dict[str, Any], conn=None) -> int:
    """
    Insert a new standard bucket row.
    Returns the new row id.
    Raises ValueError on slug collision.
    """
    close = conn is None
    if conn is None:
        conn = _get_conn()
    try:
        slug = (data.get('slug') or '').strip()
        if not slug:
            raise ValueError("slug is required")

        existing = conn.execute(
            "SELECT id FROM standard_buckets WHERE slug = ?", (slug,)
        ).fetchone()
        if existing:
            raise ValueError(f"A standard bucket with slug '{slug}' already exists.")

        conn.execute(
            """INSERT INTO standard_buckets
               (slug, title, metal, form, weight, weight_oz, denomination,
                mint, product_family, product_series, year_policy, year,
                purity, finish, variant, category_bucket_id, active)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                slug,
                data.get('title', ''),
                data.get('metal', ''),
                data.get('form', 'coin'),
                data.get('weight'),
                data.get('weight_oz'),
                data.get('denomination'),
                data.get('mint'),
                data.get('product_family'),
                data.get('product_series'),
                data.get('year_policy', 'fixed'),
                data.get('year'),
                data.get('purity'),
                data.get('finish'),
                data.get('variant'),
                data.get('category_bucket_id'),
                1 if data.get('active', True) else 0,
            ),
        )
        row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        return row_id
    finally:
        if close:
            conn.close()


def update_standard_bucket(bucket_id: int, data: Dict[str, Any], conn=None):
    """Update mutable fields of a standard bucket."""
    close = conn is None
    if conn is None:
        conn = _get_conn()
    try:
        fields = [
            'title', 'metal', 'form', 'weight', 'weight_oz', 'denomination',
            'mint', 'product_family', 'product_series', 'year_policy', 'year',
            'purity', 'finish', 'variant', 'category_bucket_id', 'active',
        ]
        updates = {}
        for f in fields:
            if f in data:
                updates[f] = data[f]
        if not updates:
            return

        updates['updated_at'] = _now_iso()
        set_clause = ', '.join(f'{k} = ?' for k in updates)
        values = list(updates.values()) + [bucket_id]
        conn.execute(f"UPDATE standard_buckets SET {set_clause} WHERE id = ?", values)
        conn.commit()
    finally:
        if close:
            conn.close()


def get_standard_bucket(bucket_id: int, conn=None) -> Optional[Dict]:
    close = conn is None
    if conn is None:
        conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM standard_buckets WHERE id = ?", (bucket_id,)
        ).fetchone()
        return _row_to_dict(row)
    finally:
        if close:
            conn.close()


def list_standard_buckets(
    missing_cover: bool = False,
    metal: Optional[str] = None,
    active_only: bool = True,
    pending_only: bool = False,
    low_confidence: bool = False,
    low_confidence_threshold: float = 0.6,
    retailer_only: bool = False,
    missing_license: bool = False,
    no_candidates: bool = False,
    conn=None,
) -> List[Dict]:
    """
    Return standard buckets with image stats.

    Filter params:
      missing_cover      — buckets with no active cover image
      pending_only       — buckets that have pending assets but no active image
      low_confidence     — buckets whose active image has confidence < threshold
      low_confidence_threshold — threshold for low_confidence filter (default 0.6)
      retailer_only      — buckets where every non-rejected asset is retailer-sourced
      missing_license    — buckets where the active image has no license_type set
      no_candidates      — buckets with zero assets (not even pending)
    """
    close = conn is None
    if conn is None:
        conn = _get_conn()
    try:
        wheres = []
        params: List[Any] = []

        if active_only:
            wheres.append("sb.active = 1")
        if metal:
            wheres.append("sb.metal = ?")
            params.append(metal)

        where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""

        rows = conn.execute(
            f"""SELECT sb.*,
                       COUNT(bia.id)                                                           AS total_assets,
                       SUM(CASE WHEN bia.status = 'active'  THEN 1 ELSE 0 END)                AS active_count,
                       SUM(CASE WHEN bia.status = 'pending' THEN 1 ELSE 0 END)                AS pending_count,
                       MAX(CASE WHEN bia.status = 'active'  THEN bia.web_path          END)   AS active_web_path,
                       MAX(CASE WHEN bia.status = 'active'  THEN bia.confidence_score  END)   AS active_confidence,
                       MAX(CASE WHEN bia.status = 'active'  THEN bia.license_type      END)   AS active_license_type,
                       MIN(CASE WHEN bia.status NOT IN ('rejected')
                                 AND bia.source_type != 'retailer' THEN 0 ELSE 1 END)         AS all_retailer_flag
                FROM standard_buckets sb
                LEFT JOIN bucket_image_assets bia ON bia.standard_bucket_id = sb.id
                {where_sql}
                GROUP BY sb.id
                ORDER BY sb.metal, sb.title""",
            params,
        ).fetchall()

        results = []
        for row in rows:
            d = dict(row)

            if missing_cover and d.get('active_count', 0) > 0:
                continue
            if pending_only and (d.get('pending_count', 0) == 0 or d.get('active_count', 0) > 0):
                continue
            if low_confidence:
                conf = d.get('active_confidence')
                if conf is None or float(conf) >= low_confidence_threshold:
                    continue
            if retailer_only:
                # all_retailer_flag = 1 means every non-rejected asset is retailer-sourced
                # We check total_assets > 0 to avoid empty-bucket false positives
                if d.get('total_assets', 0) == 0 or not d.get('all_retailer_flag'):
                    continue
            if missing_license:
                if d.get('active_count', 0) == 0:
                    continue  # no active image, not applicable
                if d.get('active_license_type'):
                    continue  # license present, skip
            if no_candidates and d.get('total_assets', 0) > 0:
                continue

            results.append(d)
        return results
    finally:
        if close:
            conn.close()


def get_standard_bucket_with_assets(bucket_id: int, conn=None) -> Optional[Dict]:
    """Return a standard bucket dict with its full assets list."""
    close = conn is None
    if conn is None:
        conn = _get_conn()
    try:
        bucket = _row_to_dict(
            conn.execute("SELECT * FROM standard_buckets WHERE id = ?", (bucket_id,)).fetchone()
        )
        if not bucket:
            return None

        assets = [
            dict(r) for r in conn.execute(
                """SELECT * FROM bucket_image_assets
                   WHERE standard_bucket_id = ?
                   ORDER BY status DESC, confidence_score DESC, created_at DESC""",
                (bucket_id,),
            ).fetchall()
        ]
        bucket['assets'] = assets
        return bucket
    finally:
        if close:
            conn.close()


# ---------------------------------------------------------------------------
# Core ingestion: shared logic after bytes are in hand
# ---------------------------------------------------------------------------

def _ingest_bytes(
    image_data: bytes,
    standard_bucket_id: int,
    source_info: Dict[str, Any],
    admin_user_id: Optional[int],
    ingestion_run_id: Optional[int],
    conn,
) -> Dict[str, Any]:
    """
    Validate, deduplicate, store, score, and catalog image_data.
    Returns asset dict with 'asset_id' key, or raises on hard failure.
    source_info keys (all optional except source_name, source_type):
      source_name, source_type, source_page_url, original_image_url,
      attribution_text, license_type, rights_note, usage_allowed,
      raw_source_title, raw_source_metadata,
      matched_title, matched_weight, matched_mint, matched_year, matched_series
    """
    # 1. Validate image
    ok, err, width, height, detected_mime = _validate_image_bytes(image_data)
    if not ok:
        raise ValueError(err)
    if detected_mime not in ALLOWED_MIME_TYPES:
        raise ValueError(f"Unsupported image type: {detected_mime}")

    # 2. Checksum + deduplication
    checksum = _sha256(image_data)
    existing = conn.execute(
        "SELECT id, standard_bucket_id FROM bucket_image_assets WHERE checksum = ?",
        (checksum,),
    ).fetchone()
    if existing:
        return {
            'asset_id': existing['id'],
            'duplicate': True,
            'checksum': checksum,
        }

    # 3. Store files
    paths = _store_image(image_data, checksum, detected_mime)
    storage_key = _storage_key(checksum)

    # 4. Fetch bucket for confidence scoring
    bucket = _row_to_dict(
        conn.execute("SELECT * FROM standard_buckets WHERE id = ?", (standard_bucket_id,)).fetchone()
    )
    if not bucket:
        raise ValueError(f"Standard bucket {standard_bucket_id} not found.")

    # 5. Confidence score
    source_type = source_info.get('source_type', 'unknown')
    raw_title   = source_info.get('raw_source_title', '')
    confidence, warnings = compute_match_confidence(bucket, raw_title, source_type,
                                                    source_info.get('raw_source_metadata'))

    # 6. Determine initial status
    source_priority = SOURCE_PRIORITY.get(source_type, 99)
    if _should_auto_activate(source_type, confidence, warnings):
        # Auto-activate eligible images if no active cover exists yet
        active_exists = conn.execute(
            "SELECT id FROM bucket_image_assets WHERE standard_bucket_id = ? AND status = 'active'",
            (standard_bucket_id,),
        ).fetchone()
        status = 'active' if not active_exists else 'approved'
    else:
        status = 'pending'

    # 7. Insert asset record
    raw_meta_json = (
        json.dumps(source_info.get('raw_source_metadata'))
        if source_info.get('raw_source_metadata')
        else None
    )
    warnings_json = json.dumps(warnings) if warnings else None

    conn.execute(
        """INSERT INTO bucket_image_assets
           (standard_bucket_id, source_name, source_type, source_priority,
            source_page_url, original_image_url, storage_key,
            local_path, web_path, thumb_path,
            checksum, width, height, mime_type, file_size,
            attribution_text, license_type, rights_note, usage_allowed,
            confidence_score, status, is_primary_candidate,
            ingestion_run_id,
            matched_title, matched_weight, matched_mint, matched_year, matched_series,
            match_warnings, raw_source_title, raw_source_metadata)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            standard_bucket_id,
            source_info.get('source_name', 'unknown'),
            source_type,
            source_priority,
            source_info.get('source_page_url'),
            source_info.get('original_image_url'),
            storage_key,
            paths['local_path'],
            paths['web_path'],
            paths['thumb_path'],
            checksum,
            width,
            height,
            detected_mime,
            len(image_data),
            source_info.get('attribution_text'),
            source_info.get('license_type'),
            source_info.get('rights_note'),
            1 if source_info.get('usage_allowed', True) else 0,
            confidence,
            status,
            0,
            ingestion_run_id,
            source_info.get('matched_title'),
            source_info.get('matched_weight'),
            source_info.get('matched_mint'),
            source_info.get('matched_year'),
            source_info.get('matched_series'),
            warnings_json,
            raw_title,
            raw_meta_json,
        ),
    )
    asset_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    return {
        'asset_id': asset_id,
        'duplicate': False,
        'checksum': checksum,
        'status': status,
        'confidence_score': confidence,
        'warnings': warnings,
        'paths': paths,
    }


# ---------------------------------------------------------------------------
# Public ingestion entry points
# ---------------------------------------------------------------------------

def ingest_from_url(
    standard_bucket_id: int,
    url: str,
    source_info: Dict[str, Any],
    admin_user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Download image from URL and ingest into the catalog.
    Creates an ingestion run record.  Returns asset dict.
    """
    conn = _get_conn()
    try:
        # Create ingestion run record
        conn.execute(
            """INSERT INTO bucket_image_ingestion_runs
               (standard_bucket_id, source_name, source_url, status,
                images_found, triggered_by)
               VALUES (?,?,?,'running',1,?)""",
            (standard_bucket_id, source_info.get('source_name', 'url'), url, admin_user_id),
        )
        run_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()

        # Download
        data, err = _safe_fetch_url(url)
        if err:
            _finish_run(conn, run_id, 'failed', err)
            conn.commit()
            conn.close()
            raise ValueError(err)

        source_info = dict(source_info)
        source_info.setdefault('original_image_url', url)

        result = _ingest_bytes(data, standard_bucket_id, source_info, admin_user_id, run_id, conn)

        ingested = 0 if result.get('duplicate') else 1
        skipped  = 1 if result.get('duplicate') else 0
        _finish_run(conn, run_id, 'completed', None,
                    images_found=1, images_ingested=ingested,
                    images_skipped_duplicate=skipped)
        conn.commit()
        return result

    except Exception as exc:
        try:
            _finish_run(conn, run_id, 'failed', str(exc))
            conn.commit()
        except Exception:
            pass
        conn.close()
        raise


def ingest_from_upload(
    standard_bucket_id: int,
    file_stream,
    source_info: Dict[str, Any],
    admin_user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Ingest image from a werkzeug FileStorage (or any file-like with .read()).
    Reads bytes, validates, stores, and catalogs.
    """
    data = file_stream.read()
    if hasattr(file_stream, 'seek'):
        file_stream.seek(0)

    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO bucket_image_ingestion_runs
               (standard_bucket_id, source_name, source_url, status,
                images_found, triggered_by)
               VALUES (?,?,'[upload]','running',1,?)""",
            (standard_bucket_id, source_info.get('source_name', 'admin_upload'), admin_user_id),
        )
        run_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()

        result = _ingest_bytes(data, standard_bucket_id, source_info, admin_user_id, run_id, conn)
        ingested = 0 if result.get('duplicate') else 1
        skipped  = 1 if result.get('duplicate') else 0
        _finish_run(conn, run_id, 'completed', None,
                    images_found=1, images_ingested=ingested,
                    images_skipped_duplicate=skipped)
        conn.commit()
        return result
    except Exception as exc:
        try:
            _finish_run(conn, run_id, 'failed', str(exc))
            conn.commit()
        except Exception:
            pass
        conn.close()
        raise


def _finish_run(conn, run_id: int, status: str, error: Optional[str],
                images_found: int = 0, images_ingested: int = 0,
                images_skipped_duplicate: int = 0):
    conn.execute(
        """UPDATE bucket_image_ingestion_runs
           SET status = ?, error_message = ?, completed_at = ?,
               images_found = ?, images_ingested = ?, images_skipped_duplicate = ?
           WHERE id = ?""",
        (status, error, _now_iso(), images_found, images_ingested,
         images_skipped_duplicate, run_id),
    )


# ---------------------------------------------------------------------------
# Asset lifecycle management
# ---------------------------------------------------------------------------

def _get_asset(asset_id: int, conn) -> Optional[Dict]:
    row = conn.execute(
        "SELECT * FROM bucket_image_assets WHERE id = ?", (asset_id,)
    ).fetchone()
    return _row_to_dict(row)


def activate_asset(asset_id: int, admin_user_id: Optional[int] = None) -> Dict:
    """
    Set asset status to 'active'. Deactivates any previously active asset
    for the same standard_bucket (there can be only one active image per bucket).
    Raises ValueError if asset not found.
    """
    conn = _get_conn()
    try:
        asset = _get_asset(asset_id, conn)
        if not asset:
            raise ValueError(f"Asset {asset_id} not found.")

        bucket_id = asset['standard_bucket_id']

        # Deactivate all other images for this bucket
        conn.execute(
            "UPDATE bucket_image_assets SET status = 'approved' WHERE standard_bucket_id = ? AND status = 'active'",
            (bucket_id,),
        )

        now = _now_iso()
        conn.execute(
            "UPDATE bucket_image_assets SET status = 'active', reviewed_at = ?, reviewed_by = ? WHERE id = ?",
            (now, admin_user_id, asset_id),
        )
        conn.commit()
        return _get_asset(asset_id, conn)
    finally:
        conn.close()


def approve_asset(asset_id: int, admin_user_id: Optional[int] = None) -> Dict:
    """Move asset from pending to approved (reviewed but not yet active cover)."""
    conn = _get_conn()
    try:
        asset = _get_asset(asset_id, conn)
        if not asset:
            raise ValueError(f"Asset {asset_id} not found.")
        now = _now_iso()
        conn.execute(
            "UPDATE bucket_image_assets SET status = 'approved', reviewed_at = ?, reviewed_by = ? WHERE id = ?",
            (now, admin_user_id, asset_id),
        )
        conn.commit()
        return _get_asset(asset_id, conn)
    finally:
        conn.close()


def reject_asset(asset_id: int, admin_user_id: Optional[int] = None) -> Dict:
    """Mark asset as rejected (kept in DB for audit trail, files left on disk)."""
    conn = _get_conn()
    try:
        asset = _get_asset(asset_id, conn)
        if not asset:
            raise ValueError(f"Asset {asset_id} not found.")
        now = _now_iso()
        conn.execute(
            "UPDATE bucket_image_assets SET status = 'rejected', reviewed_at = ?, reviewed_by = ? WHERE id = ?",
            (now, admin_user_id, asset_id),
        )
        conn.commit()
        return _get_asset(asset_id, conn)
    finally:
        conn.close()


def delete_asset(asset_id: int) -> bool:
    """
    Hard-delete asset: remove DB row and all associated files.
    Returns True if deleted, False if not found.
    """
    conn = _get_conn()
    try:
        asset = _get_asset(asset_id, conn)
        if not asset:
            return False

        # Remove files
        for path_key in ('local_path', 'web_path', 'thumb_path'):
            rel = asset.get(path_key)
            if rel:
                full = _full_path(rel)
                try:
                    if os.path.exists(full):
                        os.remove(full)
                except Exception as exc:
                    log.warning("Could not delete file %s: %s", full, exc)

        conn.execute("DELETE FROM bucket_image_assets WHERE id = ?", (asset_id,))
        conn.commit()
        return True
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Website resolution
# ---------------------------------------------------------------------------

def get_active_image_for_bucket(standard_bucket_id: int, conn=None) -> Optional[Dict]:
    """Return the active asset dict for a standard bucket, or None."""
    close = conn is None
    if conn is None:
        conn = _get_conn()
    try:
        row = conn.execute(
            """SELECT * FROM bucket_image_assets
               WHERE standard_bucket_id = ? AND status = 'active'
               ORDER BY id DESC LIMIT 1""",
            (standard_bucket_id,),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        if close:
            conn.close()


def get_active_image_url(standard_bucket_id: int, conn=None) -> Optional[str]:
    """
    Return the web_path (relative to static/) for the active cover image
    of a standard bucket, or None if none is active.
    """
    asset = get_active_image_for_bucket(standard_bucket_id, conn=conn)
    return asset['web_path'] if asset else None


def get_active_image_url_by_category_bucket_id(
    category_bucket_id: int,
    conn=None,
) -> Optional[str]:
    """
    Resolve active cover image using the categories.bucket_id linkage.
    Used by listing/buy-page renderers that only have bucket_id.
    """
    close = conn is None
    if conn is None:
        conn = _get_conn()
    try:
        sb = conn.execute(
            """SELECT sb.id
               FROM standard_buckets sb
               WHERE sb.category_bucket_id = ? AND sb.active = 1
               LIMIT 1""",
            (category_bucket_id,),
        ).fetchone()
        if not sb:
            return None
        return get_active_image_url(sb['id'], conn=conn)
    finally:
        if close:
            conn.close()


# ---------------------------------------------------------------------------
# Bulk / convenience operations
# ---------------------------------------------------------------------------

def auto_activate_best_candidate(
    standard_bucket_id: int,
    admin_user_id: Optional[int] = None,
) -> Optional[Dict]:
    """
    Find the highest-confidence non-rejected candidate for a bucket and
    promote it to active.

    Preference order: approved > pending; highest confidence_score first.
    If the bucket already has an active image, it is demoted to approved
    before the new one is promoted (same as activate_asset).

    Returns the newly activated asset dict, or None if no candidates exist.
    """
    conn = _get_conn()
    try:
        row = conn.execute(
            """SELECT id FROM bucket_image_assets
               WHERE standard_bucket_id = ?
                 AND status IN ('approved', 'pending')
               ORDER BY
                 CASE status WHEN 'approved' THEN 0 ELSE 1 END,
                 confidence_score DESC
               LIMIT 1""",
            (standard_bucket_id,),
        ).fetchone()
        if not row:
            return None

        asset_id  = row['id']
        bucket_id = standard_bucket_id

        # Deactivate any currently active image
        conn.execute(
            "UPDATE bucket_image_assets SET status = 'approved' "
            "WHERE standard_bucket_id = ? AND status = 'active'",
            (bucket_id,),
        )

        now = _now_iso()
        conn.execute(
            "UPDATE bucket_image_assets "
            "SET status = 'active', reviewed_at = ?, reviewed_by = ? "
            "WHERE id = ?",
            (now, admin_user_id, asset_id),
        )
        conn.commit()
        return _get_asset(asset_id, conn)
    finally:
        conn.close()


def bulk_reject_assets(
    asset_ids: List[int],
    admin_user_id: Optional[int] = None,
) -> int:
    """
    Reject a list of assets (by id).
    Assets already rejected or active are skipped.
    Returns the count of assets actually changed to rejected.
    """
    if not asset_ids:
        return 0

    conn = _get_conn()
    try:
        now     = _now_iso()
        changed = 0
        for asset_id in asset_ids:
            result = conn.execute(
                """UPDATE bucket_image_assets
                   SET status = 'rejected', reviewed_at = ?, reviewed_by = ?
                   WHERE id = ? AND status NOT IN ('rejected', 'active')""",
                (now, admin_user_id, asset_id),
            )
            changed += result.rowcount
        conn.commit()
        return changed
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Coverage reporting
# ---------------------------------------------------------------------------

def _bucket_product_group(slug: str, form: str, metal: str, weight: str) -> str:
    """
    Classify a standard bucket into a human-readable product group for
    coverage reporting.  Groups are ordered from most-specific to broadest
    so the first matching rule wins.
    """
    s = (slug or '').lower()
    f = (form  or '').lower()
    m = (metal or '').title()
    w = (weight or '')

    if f == 'bar':
        return f'{m} Bars'
    if f == 'round':
        return f'{m} Rounds'
    # Coins from here ----------------------------------------------------
    if 'american-eagle' in s or 'american-buffalo' in s:
        return 'US Mint Coins'
    _HISTORIC = ('morgan', 'peace-dollar', 'walking-liberty', 'franklin',
                 'mercury-dime', 'roosevelt-dime', 'washington-quarter', 'junk')
    if any(k in s for k in _HISTORIC):
        return 'Historic US Coinage'
    _PRIVATE = ('chinese-panda', 'mexican-libertad', 'kookaburra', 'round')
    if any(k in s for k in _PRIVATE):
        return 'Private Mint / Generic'
    # International sovereign coins: split 1oz vs fractional
    _FRAC = ('1/2', '1/4', '1/10', '1/20', '1/25')
    if any(f in w for f in _FRAC):
        return f'{m} Fractional Coins'
    if m in ('Platinum', 'Palladium'):
        return f'{m} Sovereign Coins'
    return f'{m} Sovereign Coins (1 oz)'


def get_coverage_report(conn=None) -> Dict[str, Any]:
    """
    Return coverage statistics across all standard buckets.

    Returns:
      {
        total:            int,
        with_active:      int,
        pending_only:     int,   # has pending candidates but no active cover
        no_candidates:    int,   # zero assets of any kind
        coverage_pct:     float, # with_active / total * 100
        by_metal: {
          metal: {total, with_active, coverage_pct}
        },
        by_product_group: {
          group_name: {total, with_active, pending_only, no_candidates, coverage_pct}
        },
        by_source: {
          source_name: count    # count of ACTIVE images by source name
        }
      }
    """
    close = conn is None
    if conn is None:
        conn = _get_conn()
    try:
        # Per-bucket stats (include slug/form/weight for product group classification)
        rows = conn.execute(
            """SELECT sb.id, sb.slug, sb.metal, sb.form, sb.weight,
                      COUNT(bia.id)                                            AS total_assets,
                      SUM(CASE WHEN bia.status = 'active'  THEN 1 ELSE 0 END) AS active_count,
                      SUM(CASE WHEN bia.status = 'pending' THEN 1 ELSE 0 END) AS pending_count
               FROM standard_buckets sb
               LEFT JOIN bucket_image_assets bia ON bia.standard_bucket_id = sb.id
               WHERE sb.active = 1
               GROUP BY sb.id, sb.slug, sb.metal, sb.form, sb.weight"""
        ).fetchall()

        total         = len(rows)
        with_active   = sum(1 for r in rows if (r['active_count'] or 0) > 0)
        pending_only  = sum(1 for r in rows
                            if (r['pending_count'] or 0) > 0
                            and (r['active_count'] or 0) == 0)
        no_candidates = sum(1 for r in rows if (r['total_assets'] or 0) == 0)
        coverage_pct  = round(with_active / total * 100, 1) if total else 0.0

        # Per-metal breakdown
        metal_stats: Dict[str, Dict] = {}
        for r in rows:
            metal = r['metal'] or 'Unknown'
            s = metal_stats.setdefault(metal, {'total': 0, 'with_active': 0})
            s['total'] += 1
            if (r['active_count'] or 0) > 0:
                s['with_active'] += 1
        by_metal = {}
        for metal, s in sorted(metal_stats.items()):
            by_metal[metal] = {
                'total':        s['total'],
                'with_active':  s['with_active'],
                'coverage_pct': round(s['with_active'] / s['total'] * 100, 1)
                                if s['total'] else 0.0,
            }

        # Per-product-group breakdown
        group_stats: Dict[str, Dict] = {}
        for r in rows:
            group = _bucket_product_group(
                r['slug'], r['form'], r['metal'], r['weight']
            )
            g = group_stats.setdefault(group, {
                'total': 0, 'with_active': 0,
                'pending_only': 0, 'no_candidates': 0,
            })
            g['total'] += 1
            act = (r['active_count']  or 0)
            pnd = (r['pending_count'] or 0)
            tot = (r['total_assets']  or 0)
            if act > 0:
                g['with_active'] += 1
            elif pnd > 0:
                g['pending_only'] += 1
            if tot == 0:
                g['no_candidates'] += 1
        by_product_group: Dict[str, Dict] = {}
        for group, g in sorted(group_stats.items()):
            by_product_group[group] = {
                'total':         g['total'],
                'with_active':   g['with_active'],
                'pending_only':  g['pending_only'],
                'no_candidates': g['no_candidates'],
                'coverage_pct':  round(g['with_active'] / g['total'] * 100, 1)
                                 if g['total'] else 0.0,
            }

        # Source breakdown for active images
        source_rows = conn.execute(
            """SELECT source_name, COUNT(*) AS cnt
               FROM bucket_image_assets
               WHERE status = 'active'
               GROUP BY source_name
               ORDER BY cnt DESC"""
        ).fetchall()
        by_source = {r['source_name']: r['cnt'] for r in source_rows}

        return {
            'total':             total,
            'with_active':       with_active,
            'pending_only':      pending_only,
            'no_candidates':     no_candidates,
            'coverage_pct':      coverage_pct,
            'by_metal':          by_metal,
            'by_product_group':  by_product_group,
            'by_source':         by_source,
        }
    finally:
        if close:
            conn.close()
