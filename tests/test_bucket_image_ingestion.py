"""
Tests for the bucket image ingestion and catalog system.
(services/bucket_image_service.py)

Tests are organized into:
  BIS-1  compute_match_confidence — pure scoring logic
  BIS-2  standard_bucket CRUD
  BIS-3  ingest_from_upload — full ingestion flow (real PIL, temp filesystem)
  BIS-4  deduplication (same checksum → duplicate=True)
  BIS-5  asset lifecycle (approve / activate / reject)
  BIS-6  active image resolution (get_active_image_url*)
  BIS-7  auto-activation rules (internal_upload gets auto-activated if none exists)
"""

import io
import os
import sqlite3
import sys
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock

# Add project root to path so service imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('FLASK_TESTING', '1')

from services.bucket_image_service import (
    compute_match_confidence,
    create_standard_bucket,
    get_standard_bucket,
    update_standard_bucket,
    list_standard_buckets,
    get_standard_bucket_with_assets,
    activate_asset,
    approve_asset,
    reject_asset,
    delete_asset,
    get_active_image_url,
    get_active_image_url_by_category_bucket_id,
    _ingest_bytes,
    _validate_image_bytes,
    _sha256,
    SOURCE_PRIORITY,
)


# ---------------------------------------------------------------------------
# Minimal valid JPEG bytes (1x1 white pixel, no EXIF)
# ---------------------------------------------------------------------------

def _make_jpeg_bytes() -> bytes:
    """Return valid 1×1 JPEG bytes using PIL."""
    from PIL import Image
    img = Image.new('RGB', (1, 1), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=90)
    return buf.getvalue()


def _make_png_bytes() -> bytes:
    from PIL import Image
    img = Image.new('RGB', (2, 2), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


# ---------------------------------------------------------------------------
# In-memory SQLite DB with the three new tables
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS standard_buckets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    metal TEXT NOT NULL,
    form TEXT NOT NULL DEFAULT 'coin',
    weight TEXT,
    weight_oz REAL,
    denomination TEXT,
    mint TEXT,
    product_family TEXT,
    product_series TEXT,
    year_policy TEXT NOT NULL DEFAULT 'fixed',
    year TEXT,
    purity TEXT,
    finish TEXT,
    variant TEXT,
    category_bucket_id INTEGER,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bucket_image_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    standard_bucket_id INTEGER NOT NULL,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'unknown',
    source_priority INTEGER NOT NULL DEFAULT 99,
    source_page_url TEXT,
    original_image_url TEXT,
    storage_key TEXT UNIQUE,
    local_path TEXT,
    web_path TEXT,
    thumb_path TEXT,
    checksum TEXT,
    width INTEGER,
    height INTEGER,
    mime_type TEXT,
    file_size INTEGER,
    attribution_text TEXT,
    license_type TEXT,
    rights_note TEXT,
    usage_allowed INTEGER NOT NULL DEFAULT 1,
    confidence_score REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'pending',
    is_primary_candidate INTEGER NOT NULL DEFAULT 0,
    ingestion_run_id INTEGER,
    matched_title TEXT,
    matched_weight TEXT,
    matched_mint TEXT,
    matched_year TEXT,
    matched_series TEXT,
    match_warnings TEXT,
    raw_source_title TEXT,
    raw_source_metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP,
    reviewed_by INTEGER,
    FOREIGN KEY (standard_bucket_id) REFERENCES standard_buckets(id)
);

CREATE TABLE IF NOT EXISTS bucket_image_ingestion_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    standard_bucket_id INTEGER,
    source_name TEXT,
    source_url TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    images_found INTEGER NOT NULL DEFAULT 0,
    images_ingested INTEGER NOT NULL DEFAULT 0,
    images_skipped_duplicate INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    triggered_by INTEGER,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);
"""


def _make_conn():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    return conn


def _sample_bucket_data(**overrides):
    base = {
        'slug':           'test-1oz-gold-eagle',
        'title':          '1 oz American Gold Eagle Coin',
        'metal':          'Gold',
        'form':           'coin',
        'weight':         '1 oz',
        'weight_oz':      1.0,
        'mint':           'United States Mint',
        'product_family': 'American Eagle',
        'product_series': 'Bullion',
        'year_policy':    'fixed',
        'year':           '2024',
        'denomination':   '$50',
        'purity':         '.9167',
    }
    base.update(overrides)
    return base


# ===========================================================================
# BIS-1: compute_match_confidence
# ===========================================================================

class TestComputeMatchConfidence(unittest.TestCase):

    def _bucket(self, **kw):
        return _sample_bucket_data(**kw)

    def test_full_match_returns_high_score(self):
        """All key fields present in title → near-max score."""
        bucket = self._bucket()
        raw_title = '2024 1 oz American Gold Eagle Coin United States Mint $50 Bullion'
        score, warns = compute_match_confidence(bucket, raw_title, 'public_domain')
        self.assertGreaterEqual(score, 0.80)
        self.assertEqual(warns, [])

    def test_empty_title_returns_zero(self):
        score, warns = compute_match_confidence(self._bucket(), '', 'public_domain')
        self.assertEqual(score, 0.0)
        self.assertEqual(warns, [])

    def test_example_image_caps_score(self):
        raw = 'Gold Eagle example image stock photo'
        score, warns = compute_match_confidence(self._bucket(), raw, 'public_domain')
        self.assertLessEqual(score, 0.50)
        self.assertIn('example_image', warns)

    def test_generic_image_caps_score(self):
        raw = 'generic gold coin placeholder'
        score, warns = compute_match_confidence(self._bucket(), raw, 'public_domain')
        self.assertLessEqual(score, 0.40)
        self.assertIn('generic_image', warns)

    def test_brand_varies_caps_score(self):
        raw = '1 oz gold coin random mint brand varies'
        score, warns = compute_match_confidence(self._bucket(), raw, 'public_domain')
        self.assertLessEqual(score, 0.60)
        self.assertIn('brand_varies', warns)

    def test_retailer_source_hard_cap(self):
        """Retailer sources capped at 0.75 even on perfect title match."""
        bucket = self._bucket()
        raw = '2024 1 oz American Gold Eagle Coin United States Mint $50 Bullion'
        score, warns = compute_match_confidence(bucket, raw, 'retailer')
        self.assertLessEqual(score, 0.75)
        self.assertIn('retailer_source_requires_review', warns)

    def test_year_varies_policy(self):
        bucket = self._bucket(year_policy='varies', year=None)
        raw = '1 oz American Gold Eagle Gold Coin random year varies United States Mint'
        score, warns = compute_match_confidence(bucket, raw, 'public_domain')
        self.assertIn('year_varies', warns)
        self.assertGreater(score, 0.0)

    def test_partial_match(self):
        """Only metal matches — should be 0.20."""
        bucket = self._bucket()
        raw = 'Some generic Gold product'
        score, warns = compute_match_confidence(bucket, raw, 'approved_db')
        self.assertAlmostEqual(score, 0.20, places=2)

    def test_score_capped_at_one(self):
        """Score never exceeds 1.0."""
        bucket = self._bucket()
        raw = '2024 1 oz Gold American Eagle Coin United States Mint $50 Bullion coin coin coin'
        score, _ = compute_match_confidence(bucket, raw, 'public_domain')
        self.assertLessEqual(score, 1.0)


# ===========================================================================
# BIS-2: standard_bucket CRUD (using patched connection)
# ===========================================================================

class TestStandardBucketCRUD(unittest.TestCase):

    def _conn(self):
        return _make_conn()

    def test_create_and_get(self):
        conn = self._conn()
        bid = create_standard_bucket(_sample_bucket_data(), conn=conn)
        self.assertIsInstance(bid, int)
        bucket = get_standard_bucket(bid, conn=conn)
        self.assertEqual(bucket['slug'], 'test-1oz-gold-eagle')
        self.assertEqual(bucket['metal'], 'Gold')
        conn.close()

    def test_slug_collision_raises(self):
        conn = self._conn()
        create_standard_bucket(_sample_bucket_data(), conn=conn)
        with self.assertRaises(ValueError):
            create_standard_bucket(_sample_bucket_data(), conn=conn)
        conn.close()

    def test_update(self):
        conn = self._conn()
        bid = create_standard_bucket(_sample_bucket_data(), conn=conn)
        update_standard_bucket(bid, {'title': 'Updated Title', 'year': '2025'}, conn=conn)
        bucket = get_standard_bucket(bid, conn=conn)
        self.assertEqual(bucket['title'], 'Updated Title')
        self.assertEqual(bucket['year'], '2025')
        conn.close()

    def test_list_standard_buckets(self):
        conn = self._conn()
        create_standard_bucket(_sample_bucket_data(), conn=conn)
        create_standard_bucket(_sample_bucket_data(slug='silver-eagle', metal='Silver', title='Silver Eagle'), conn=conn)
        all_buckets = list_standard_buckets(active_only=False, conn=conn)
        self.assertEqual(len(all_buckets), 2)
        gold_only = list_standard_buckets(metal='Gold', active_only=False, conn=conn)
        self.assertEqual(len(gold_only), 1)
        conn.close()

    def test_list_missing_cover_filter(self):
        conn = self._conn()
        bid = create_standard_bucket(_sample_bucket_data(), conn=conn)
        # No assets yet → shows in missing_cover filter
        missing = list_standard_buckets(missing_cover=True, active_only=False, conn=conn)
        self.assertEqual(len(missing), 1)
        conn.close()


# ===========================================================================
# BIS-3: ingest_from_upload / _ingest_bytes (with real PIL, temp filesystem)
# ===========================================================================

class TestIngestBytes(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # Patch _static_dir() so files land in our temp dir
        self._patcher = patch(
            'services.bucket_image_service._static_dir',
            return_value=self.tmp,
        )
        self._patcher.start()
        self.conn = _make_conn()
        self.bucket_id = create_standard_bucket(_sample_bucket_data(), conn=self.conn)

    def tearDown(self):
        self._patcher.stop()
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _source_info(self, source_type='internal_upload'):
        return {
            'source_name':     'Test Source',
            'source_type':     source_type,
            'raw_source_title': '2024 1 oz Gold American Eagle Coin United States Mint',
        }

    def test_ingest_jpeg_creates_asset_record(self):
        data = _make_jpeg_bytes()
        result = _ingest_bytes(data, self.bucket_id, self._source_info(), None, None, self.conn)
        self.assertFalse(result.get('duplicate'))
        self.assertIn('asset_id', result)

        # Verify DB row
        row = self.conn.execute(
            "SELECT * FROM bucket_image_assets WHERE id = ?", (result['asset_id'],)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['standard_bucket_id'], self.bucket_id)
        self.assertEqual(row['mime_type'], 'image/jpeg')

    def test_ingest_png(self):
        data = _make_png_bytes()
        result = _ingest_bytes(data, self.bucket_id, self._source_info(), None, None, self.conn)
        self.assertFalse(result.get('duplicate'))
        row = self.conn.execute(
            "SELECT mime_type FROM bucket_image_assets WHERE id = ?", (result['asset_id'],)
        ).fetchone()
        self.assertEqual(row['mime_type'], 'image/png')

    def test_web_and_thumb_files_created(self):
        data = _make_jpeg_bytes()
        result = _ingest_bytes(data, self.bucket_id, self._source_info(), None, None, self.conn)
        row = self.conn.execute(
            "SELECT web_path, thumb_path FROM bucket_image_assets WHERE id = ?",
            (result['asset_id'],)
        ).fetchone()
        web_full   = os.path.join(self.tmp, row['web_path'])
        thumb_full = os.path.join(self.tmp, row['thumb_path'])
        self.assertTrue(os.path.exists(web_full),   f"web file missing: {web_full}")
        self.assertTrue(os.path.exists(thumb_full), f"thumb file missing: {thumb_full}")

    def test_checksum_stored(self):
        data = _make_jpeg_bytes()
        expected_checksum = _sha256(data)
        result = _ingest_bytes(data, self.bucket_id, self._source_info(), None, None, self.conn)
        row = self.conn.execute(
            "SELECT checksum FROM bucket_image_assets WHERE id = ?", (result['asset_id'],)
        ).fetchone()
        self.assertEqual(row['checksum'], expected_checksum)

    def test_invalid_bytes_raises(self):
        with self.assertRaises(ValueError):
            _ingest_bytes(b'not an image', self.bucket_id, self._source_info(), None, None, self.conn)

    def test_bucket_not_found_raises(self):
        with self.assertRaises(ValueError):
            _ingest_bytes(_make_jpeg_bytes(), 99999, self._source_info(), None, None, self.conn)


# ===========================================================================
# BIS-4: Deduplication
# ===========================================================================

class TestDeduplication(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._patcher = patch('services.bucket_image_service._static_dir', return_value=self.tmp)
        self._patcher.start()
        self.conn = _make_conn()
        self.bucket_id = create_standard_bucket(_sample_bucket_data(), conn=self.conn)

    def tearDown(self):
        self._patcher.stop()
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_duplicate_detected_on_second_ingest(self):
        data   = _make_jpeg_bytes()
        info   = {'source_name': 'Test', 'source_type': 'internal_upload', 'raw_source_title': ''}
        first  = _ingest_bytes(data, self.bucket_id, info, None, None, self.conn)
        self.conn.commit()
        second = _ingest_bytes(data, self.bucket_id, info, None, None, self.conn)
        self.assertFalse(first.get('duplicate'))
        self.assertTrue(second.get('duplicate'))
        self.assertEqual(second['asset_id'], first['asset_id'])

    def test_different_images_not_duplicates(self):
        info = {'source_name': 'Test', 'source_type': 'internal_upload', 'raw_source_title': ''}
        r1 = _ingest_bytes(_make_jpeg_bytes(), self.bucket_id, info, None, None, self.conn)
        self.conn.commit()
        # PNG has different bytes/checksum
        r2 = _ingest_bytes(_make_png_bytes(), self.bucket_id, info, None, None, self.conn)
        self.assertFalse(r2.get('duplicate'))
        self.assertNotEqual(r1['asset_id'], r2['asset_id'])


# ===========================================================================
# BIS-5: Asset lifecycle
# ===========================================================================

class TestAssetLifecycle(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._patcher = patch('services.bucket_image_service._static_dir', return_value=self.tmp)
        self._patcher.start()
        self.conn_factory = _make_conn

    def tearDown(self):
        self._patcher.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _create_asset(self, status='pending'):
        conn = self.conn_factory()
        bid = create_standard_bucket(_sample_bucket_data(), conn=conn)
        data = _make_jpeg_bytes()
        info = {'source_name': 'Test', 'source_type': 'approved_db', 'raw_source_title': ''}
        r = _ingest_bytes(data, bid, info, None, None, conn)
        conn.commit()
        # Force status
        conn.execute("UPDATE bucket_image_assets SET status = ? WHERE id = ?", (status, r['asset_id']))
        conn.commit()
        return conn, bid, r['asset_id']

    def test_approve_asset(self):
        conn, bid, aid = self._create_asset('pending')
        with patch('services.bucket_image_service._get_conn', return_value=conn):
            result = approve_asset(aid, admin_user_id=1)
        self.assertEqual(result['status'], 'approved')
        conn.close()

    def test_reject_asset(self):
        conn, bid, aid = self._create_asset('pending')
        with patch('services.bucket_image_service._get_conn', return_value=conn):
            result = reject_asset(aid, admin_user_id=1)
        self.assertEqual(result['status'], 'rejected')
        conn.close()

    def test_activate_asset_deactivates_previous(self):
        conn = self.conn_factory()
        bid = create_standard_bucket(_sample_bucket_data(), conn=conn)
        info = {'source_name': 'T', 'source_type': 'public_domain', 'raw_source_title': ''}
        r1 = _ingest_bytes(_make_jpeg_bytes(), bid, info, None, None, conn)
        conn.commit()
        r2 = _ingest_bytes(_make_png_bytes(), bid, info, None, None, conn)
        conn.commit()
        # Manually set first as active
        conn.execute("UPDATE bucket_image_assets SET status='active' WHERE id=?", (r1['asset_id'],))
        conn.commit()

        # Use a no-close wrapper so we can read state after the service's finally clause
        class _NoClose:
            def __init__(self, c): self._c = c
            def __getattr__(self, n): return getattr(self._c, n)
            def close(self): pass  # no-op

        with patch('services.bucket_image_service._get_conn', return_value=_NoClose(conn)):
            result = activate_asset(r2['asset_id'], admin_user_id=1)

        row1 = conn.execute("SELECT status FROM bucket_image_assets WHERE id=?", (r1['asset_id'],)).fetchone()
        row2 = conn.execute("SELECT status FROM bucket_image_assets WHERE id=?", (r2['asset_id'],)).fetchone()
        self.assertEqual(row1['status'], 'approved')  # demoted
        self.assertEqual(row2['status'], 'active')
        self.assertEqual(result['status'], 'active')
        conn.close()

    def test_delete_removes_record_and_files(self):
        conn, bid, aid = self._create_asset('pending')
        # Check files exist before delete
        row = conn.execute("SELECT web_path FROM bucket_image_assets WHERE id=?", (aid,)).fetchone()
        web_full = os.path.join(self.tmp, row['web_path'])
        self.assertTrue(os.path.exists(web_full))

        class _NoClose:
            def __init__(self, c): self._c = c
            def __getattr__(self, n): return getattr(self._c, n)
            def close(self): pass

        with patch('services.bucket_image_service._get_conn', return_value=_NoClose(conn)):
            deleted = delete_asset(aid)

        self.assertTrue(deleted)
        # File on disk should be gone
        self.assertFalse(os.path.exists(web_full))
        # DB row should be gone
        row_after = conn.execute("SELECT id FROM bucket_image_assets WHERE id=?", (aid,)).fetchone()
        self.assertIsNone(row_after)
        conn.close()


# ===========================================================================
# BIS-6: Active image resolution
# ===========================================================================

class TestActiveImageResolution(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._patcher = patch('services.bucket_image_service._static_dir', return_value=self.tmp)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_active_image_returns_none(self):
        conn = _make_conn()
        bid = create_standard_bucket(_sample_bucket_data(), conn=conn)
        with patch('services.bucket_image_service._get_conn', return_value=conn):
            result = get_active_image_url(bid)
        self.assertIsNone(result)
        conn.close()

    def test_active_image_returns_web_path(self):
        conn = _make_conn()
        bid = create_standard_bucket(_sample_bucket_data(), conn=conn)
        info = {'source_name': 'T', 'source_type': 'internal_upload', 'raw_source_title': ''}
        r = _ingest_bytes(_make_jpeg_bytes(), bid, info, None, None, conn)
        # Force active
        conn.execute("UPDATE bucket_image_assets SET status='active' WHERE id=?", (r['asset_id'],))
        conn.commit()

        with patch('services.bucket_image_service._get_conn', return_value=conn):
            url = get_active_image_url(bid)

        self.assertIsNotNone(url)
        self.assertIn('web', url)
        conn.close()

    def test_resolve_by_category_bucket_id(self):
        conn = _make_conn()
        bid = create_standard_bucket(_sample_bucket_data(category_bucket_id=42), conn=conn)
        info = {'source_name': 'T', 'source_type': 'internal_upload', 'raw_source_title': ''}
        r = _ingest_bytes(_make_jpeg_bytes(), bid, info, None, None, conn)
        conn.execute("UPDATE bucket_image_assets SET status='active' WHERE id=?", (r['asset_id'],))
        conn.commit()

        with patch('services.bucket_image_service._get_conn', return_value=conn):
            url = get_active_image_url_by_category_bucket_id(42)

        self.assertIsNotNone(url)
        conn.close()

    def test_resolve_unknown_category_bucket_id_returns_none(self):
        conn = _make_conn()
        with patch('services.bucket_image_service._get_conn', return_value=conn):
            url = get_active_image_url_by_category_bucket_id(99999)
        self.assertIsNone(url)
        conn.close()


# ===========================================================================
# BIS-7: Auto-activation rules
# ===========================================================================

class TestAutoActivation(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._patcher = patch('services.bucket_image_service._static_dir', return_value=self.tmp)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_internal_upload_auto_activates_when_none_exists(self):
        """First internal_upload with no warnings → automatically set to 'active'."""
        conn = _make_conn()
        bid = create_standard_bucket(_sample_bucket_data(), conn=conn)
        info = {'source_name': 'Admin', 'source_type': 'internal_upload', 'raw_source_title': ''}
        result = _ingest_bytes(_make_jpeg_bytes(), bid, info, None, None, conn)
        self.assertEqual(result['status'], 'active')
        conn.close()

    def test_internal_upload_becomes_approved_when_active_exists(self):
        """If an active image already exists, new internal_upload becomes 'approved' (not active)."""
        conn = _make_conn()
        bid = create_standard_bucket(_sample_bucket_data(), conn=conn)
        info = {'source_name': 'Admin', 'source_type': 'internal_upload', 'raw_source_title': ''}
        # First upload → active
        _ingest_bytes(_make_jpeg_bytes(), bid, info, None, None, conn)
        conn.commit()
        # Second upload → approved (first is still active)
        result2 = _ingest_bytes(_make_png_bytes(), bid, info, None, None, conn)
        self.assertEqual(result2['status'], 'approved')
        conn.close()

    def test_retailer_source_stays_pending(self):
        """Retailer sources always start as 'pending', never auto-activate."""
        conn = _make_conn()
        bid = create_standard_bucket(_sample_bucket_data(), conn=conn)
        info = {'source_name': 'APMEX', 'source_type': 'retailer', 'raw_source_title': ''}
        result = _ingest_bytes(_make_jpeg_bytes(), bid, info, None, None, conn)
        self.assertEqual(result['status'], 'pending')
        conn.close()

    def test_public_domain_stays_pending(self):
        """public_domain without warnings stays pending (admin review required)."""
        conn = _make_conn()
        bid = create_standard_bucket(_sample_bucket_data(), conn=conn)
        info = {'source_name': 'US Mint', 'source_type': 'public_domain', 'raw_source_title': ''}
        result = _ingest_bytes(_make_jpeg_bytes(), bid, info, None, None, conn)
        self.assertEqual(result['status'], 'pending')
        conn.close()

    def test_source_priority_values(self):
        """Source priority table has expected values."""
        self.assertEqual(SOURCE_PRIORITY['internal_upload'], 1)
        self.assertEqual(SOURCE_PRIORITY['public_domain'],   2)
        self.assertGreater(SOURCE_PRIORITY['retailer'], SOURCE_PRIORITY['approved_db'])
        self.assertEqual(SOURCE_PRIORITY['unknown'], 99)


if __name__ == '__main__':
    unittest.main()
