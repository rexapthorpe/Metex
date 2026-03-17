"""
Tests for set listing creation with >2 items.

Verifies that all items in a set listing (3+) are correctly saved to
listing_set_items and visible via the bucket page and API endpoints.
"""
import io
import json
import os
import sys
import shutil
import sqlite3
import tempfile
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    from app import app as flask_app

    test_dir = tempfile.mkdtemp()
    test_db_path = os.path.join(test_dir, 'test_set_items.db')
    upload_dir = os.path.join(test_dir, 'uploads')
    os.makedirs(upload_dir, exist_ok=True)

    main_db_path = 'data/database.db'
    if os.path.exists(main_db_path):
        shutil.copy(main_db_path, test_db_path)

    flask_app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-set-listing-secret-key',
    })

    import database
    original_get_db = database.get_db_connection

    def test_db():
        conn = sqlite3.connect(test_db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        return conn

    database.get_db_connection = test_db

    # Patch modules that cache get_db_connection at import time
    _patched = {}
    for mod_path in [
        'utils.auth_utils',
        'core.blueprints.sell.listing_creation',
        'core.blueprints.buy.bucket_view',
        'core.blueprints.api.routes',
    ]:
        try:
            import importlib
            mod = importlib.import_module(mod_path)
            if hasattr(mod, 'get_db_connection'):
                _patched[mod_path] = mod.get_db_connection
                mod.get_db_connection = test_db
        except Exception:
            pass

    yield flask_app, test_db_path, upload_dir

    database.get_db_connection = original_get_db
    for mod_path, orig in _patched.items():
        try:
            import importlib
            mod = importlib.import_module(mod_path)
            mod.get_db_connection = orig
        except Exception:
            pass
    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def client(app):
    flask_app, db_path, upload_dir = app
    return flask_app.test_client(), db_path, upload_dir


@pytest.fixture
def logged_in_client(client):
    """Return (test_client, user_id, db_path, upload_dir) with a logged-in user."""
    tc, db_path, upload_dir = client

    import database
    conn = database.get_db_connection()
    conn.execute("""
        INSERT INTO users (username, email, password, password_hash, is_admin, is_banned, is_frozen,
                           first_name, last_name)
        VALUES ('setuser', 'setuser@test.com', 'pw', 'pw', 0, 0, 0, 'Set', 'User')
    """)
    conn.commit()
    user_id = conn.execute("SELECT id FROM users WHERE username='setuser'").fetchone()['id']
    conn.close()

    with tc.session_transaction() as sess:
        sess['user_id'] = user_id
        sess['username'] = 'setuser'

    return tc, user_id, db_path, upload_dir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_png():
    """Return bytes of a tiny valid 1×1 red PNG image."""
    try:
        from PIL import Image
        buf = io.BytesIO()
        Image.new('RGB', (1, 1), color=(255, 0, 0)).save(buf, format='PNG')
        buf.seek(0)
        return buf.read()
    except Exception:
        # Fallback: raw PNG header bytes that PIL will accept
        import struct, zlib
        def _chunk(tag, data):
            c = struct.pack('>I', len(data)) + tag + data
            return c + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)
        sig = b'\x89PNG\r\n\x1a\n'
        ihdr = _chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
        raw = b'\x00\xff\x00\x00'  # filter=0, R=255, G=0, B=0
        idat = _chunk(b'IDAT', zlib.compress(raw))
        iend = _chunk(b'IEND', b'')
        return sig + ihdr + idat + iend


def _photo_tuple(name='photo.png'):
    """Return (BytesIO, filename, mimetype) for use in multipart form data."""
    return (io.BytesIO(_minimal_png()), name, 'image/png')


def _build_set_form_json(n_items, pricing_mode='static', price='100.00'):
    """
    Build multipart form data using set_items_json (the browser code path).
    Mirrors what sell_listing_modals.js sends when submitting the set form.
    """
    import json
    metals = ['Gold', 'Silver', 'Gold', 'Silver']
    items_meta = []
    data = {
        'is_isolated': '1',
        'is_set': '1',
        'listing_title': f'Test Set Listing {n_items} Items (JSON)',
        'listing_description': 'A test set via JSON.',
        'quantity': '1',
        'pricing_mode': pricing_mode,
        'price_per_coin': price,
        'spot_premium': '',
        'floor_price': '',
        'pricing_metal': 'Gold',
        'packaging_type': '',
        'packaging_notes': '',
        'condition_notes': '',
        'cert_number': '',
        'cover_photo': _photo_tuple('cover.png'),
    }
    for i in range(1, n_items + 1):
        metal = metals[min(i - 1, len(metals) - 1)]
        items_meta.append({
            'item_title': f'Item {i}',
            'metal': metal,
            'product_line': 'American Eagle',
            'product_type': 'Coin',
            'weight': '1 oz',
            'purity': '.999',
            'mint': 'US Mint',
            'year': str(2020 + i),
            'finish': 'Brilliant Uncirculated',
            'grade': '',
            'coin_series': '',
            'quantity': '1',
            'packaging_type': '',
            'packaging_notes': '',
            'condition_notes': '',
            'edition_number': '',
            'edition_total': '',
        })
        data[f'set_item_photo_{i}_1'] = _photo_tuple(f'item{i}_photo1.png')
    data['set_items_json'] = json.dumps(items_meta)
    return data


def _build_set_form(n_items, pricing_mode='static', price='100.00'):
    """
    Build multipart form data dict for a set listing with n_items items.
    Each item gets full specs (metal, product_line, etc.) and one photo.
    """
    data = {
        'is_isolated': '1',
        'is_set': '1',
        'listing_title': f'Test Set Listing {n_items} Items',
        'listing_description': 'A test set.',
        'quantity': '1',
        'pricing_mode': pricing_mode,
        'price_per_coin': price,
        'spot_premium': '',
        'floor_price': '',
        'pricing_metal': 'Gold',
        'packaging_type': '',
        'packaging_notes': '',
        'condition_notes': '',
        'cert_number': '',
        # Cover photo
        'cover_photo': _photo_tuple('cover.png'),
    }

    metals = ['Gold', 'Silver', 'Gold']
    for i in range(1, n_items + 1):
        idx = min(i - 1, len(metals) - 1)
        metal = metals[idx]
        data[f'set_items[{i}][metal]'] = metal
        data[f'set_items[{i}][product_line]'] = 'American Eagle'
        data[f'set_items[{i}][product_type]'] = 'Coin'
        data[f'set_items[{i}][weight]'] = '1 oz'
        data[f'set_items[{i}][purity]'] = '.999'
        data[f'set_items[{i}][mint]'] = 'US Mint'
        data[f'set_items[{i}][year]'] = str(2020 + i)
        data[f'set_items[{i}][finish]'] = 'Brilliant Uncirculated'
        data[f'set_items[{i}][grade]'] = ''
        data[f'set_items[{i}][coin_series]'] = ''
        data[f'set_items[{i}][quantity]'] = '1'
        data[f'set_items[{i}][item_title]'] = f'Item {i}'
        data[f'set_items[{i}][packaging_type]'] = ''
        data[f'set_items[{i}][packaging_notes]'] = ''
        data[f'set_items[{i}][condition_notes]'] = ''
        data[f'set_items[{i}][edition_number]'] = ''
        data[f'set_items[{i}][edition_total]'] = ''
        data[f'set_items[{i}][series_variant]'] = ''
        # Photo for this set item
        data[f'set_item_photo_{i}_1'] = _photo_tuple(f'item{i}_photo1.png')

    return data


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSetListingCreation:
    """Verify that set listings with >2 items save all items correctly."""

    def _mock_save_secure_upload(self, *args, **kwargs):
        """Replace save_secure_upload with one that always succeeds."""
        import tempfile, os
        tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False,
                                          dir=self._upload_dir)
        tmp.write(_minimal_png())
        tmp.close()
        return {'success': True, 'path': tmp.name}

    def test_set_listing_2_items_saves_both(self, logged_in_client):
        """Baseline: 2-item set should save both items."""
        tc, user_id, db_path, upload_dir = logged_in_client
        self._upload_dir = upload_dir

        with patch('utils.upload_security.save_secure_upload',
                   side_effect=self._mock_save_secure_upload):
            resp = tc.post('/sell',
                           data=_build_set_form(2),
                           content_type='multipart/form-data',
                           headers={'X-Requested-With': 'XMLHttpRequest'})

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.data[:300]}"
        body = json.loads(resp.data)
        assert body.get('success') is True, f"Expected success=True: {body}"

        # Verify 2 set items in DB
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        listing_id = body['listing']['id']
        rows = conn.execute(
            'SELECT * FROM listing_set_items WHERE listing_id=? ORDER BY position_index',
            (listing_id,)
        ).fetchall()
        conn.close()

        assert len(rows) == 2, f"Expected 2 set items, got {len(rows)}"
        assert rows[0]['metal'] == 'Gold'
        assert rows[1]['metal'] == 'Silver'

    def test_set_listing_3_items_saves_all_three(self, logged_in_client):
        """Core test: 3-item set must save all three items."""
        tc, user_id, db_path, upload_dir = logged_in_client
        self._upload_dir = upload_dir

        with patch('utils.upload_security.save_secure_upload',
                   side_effect=self._mock_save_secure_upload):
            resp = tc.post('/sell',
                           data=_build_set_form(3),
                           content_type='multipart/form-data',
                           headers={'X-Requested-With': 'XMLHttpRequest'})

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.data[:500]}"
        body = json.loads(resp.data)
        assert body.get('success') is True, f"Expected success=True: {body}"

        listing_id = body['listing']['id']

        # Verify ALL 3 set items are in the DB
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            'SELECT * FROM listing_set_items WHERE listing_id=? ORDER BY position_index',
            (listing_id,)
        ).fetchall()
        conn.close()

        assert len(rows) == 3, (
            f"Expected 3 set items in listing_set_items, got {len(rows)}. "
            f"Items: {[dict(r) for r in rows]}"
        )
        # Verify position_index sequence
        positions = [r['position_index'] for r in rows]
        assert positions == [0, 1, 2], f"Expected positions [0,1,2], got {positions}"
        # Verify item data
        assert rows[0]['metal'] == 'Gold'
        assert rows[1]['metal'] == 'Silver'
        assert rows[2]['metal'] == 'Gold'

    def test_set_listing_4_items_saves_all_four(self, logged_in_client):
        """Unlimited items: 4-item set must save all four items."""
        tc, user_id, db_path, upload_dir = logged_in_client
        self._upload_dir = upload_dir

        with patch('utils.upload_security.save_secure_upload',
                   side_effect=self._mock_save_secure_upload):
            resp = tc.post('/sell',
                           data=_build_set_form(4),
                           content_type='multipart/form-data',
                           headers={'X-Requested-With': 'XMLHttpRequest'})

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.data[:500]}"
        body = json.loads(resp.data)
        assert body.get('success') is True, f"Expected success=True: {body}"

        listing_id = body['listing']['id']

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            'SELECT * FROM listing_set_items WHERE listing_id=? ORDER BY position_index',
            (listing_id,)
        ).fetchall()
        conn.close()

        assert len(rows) == 4, (
            f"Expected 4 set items, got {len(rows)}: {[dict(r) for r in rows]}"
        )

    def test_set_listing_3_items_visible_on_bucket_page(self, logged_in_client):
        """3-item set should display all 3 items on the bucket page."""
        tc, user_id, db_path, upload_dir = logged_in_client
        self._upload_dir = upload_dir

        # Create a 3-item set listing
        with patch('utils.upload_security.save_secure_upload',
                   side_effect=self._mock_save_secure_upload):
            resp = tc.post('/sell',
                           data=_build_set_form(3),
                           content_type='multipart/form-data',
                           headers={'X-Requested-With': 'XMLHttpRequest'})

        assert resp.status_code == 200
        body = json.loads(resp.data)
        assert body.get('success') is True

        listing_id = body['listing']['id']

        # Get the bucket_id for this listing
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            'SELECT c.bucket_id FROM listings l JOIN categories c ON l.category_id=c.id WHERE l.id=?',
            (listing_id,)
        ).fetchone()
        conn.close()
        bucket_id = row['bucket_id']

        # Visit the bucket page — all 3 set items should be visible in HTML
        resp = tc.get(f'/bucket/{bucket_id}')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')

        # Should say "3 items" in the set description
        assert '3 item' in html, "Bucket page should show '3 items' for a 3-item set"
        # Should render all three item cards
        assert 'Item #1' in html
        assert 'Item #2' in html
        assert 'Item #3' in html

    def test_set_listing_3_items_via_api(self, logged_in_client):
        """3-item set should return all 3 items via the listing details API."""
        tc, user_id, db_path, upload_dir = logged_in_client
        self._upload_dir = upload_dir

        with patch('utils.upload_security.save_secure_upload',
                   side_effect=self._mock_save_secure_upload):
            resp = tc.post('/sell',
                           data=_build_set_form(3),
                           content_type='multipart/form-data',
                           headers={'X-Requested-With': 'XMLHttpRequest'})

        assert resp.status_code == 200
        body = json.loads(resp.data)
        listing_id = body['listing']['id']

        # Fetch via API
        resp = tc.get(f'/api/listings/{listing_id}/details')
        assert resp.status_code == 200
        data = json.loads(resp.data)

        assert 'set_items' in data, "API should return set_items for a set listing"
        assert len(data['set_items']) == 3, (
            f"API should return 3 set items, got {len(data['set_items'])}: {data['set_items']}"
        )

    def test_set_listing_3_items_via_json_blob(self, logged_in_client):
        """
        Core path test: verify that set_items_json (the browser code path) saves all 3 items.
        This mirrors what sell_listing_modals.js sends when window.setItems has 3 items.
        """
        tc, user_id, db_path, upload_dir = logged_in_client
        self._upload_dir = upload_dir

        with patch('utils.upload_security.save_secure_upload',
                   side_effect=self._mock_save_secure_upload):
            resp = tc.post('/sell',
                           data=_build_set_form_json(3),
                           content_type='multipart/form-data',
                           headers={'X-Requested-With': 'XMLHttpRequest'})

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.data[:500]}"
        body = json.loads(resp.data)
        assert body.get('success') is True, f"Expected success=True: {body}"

        listing_id = body['listing']['id']

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            'SELECT * FROM listing_set_items WHERE listing_id=? ORDER BY position_index',
            (listing_id,)
        ).fetchall()
        conn.close()

        assert len(rows) == 3, (
            f"Expected 3 set items via JSON path, got {len(rows)}: {[dict(r) for r in rows]}"
        )
        assert rows[0]['metal'] == 'Gold'
        assert rows[1]['metal'] == 'Silver'
        assert rows[2]['metal'] == 'Gold'
