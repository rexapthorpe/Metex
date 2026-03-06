"""
Security fix regression tests — added during security audit pass.

Tests specifically for:
- SEC-FIX-1: Insecure SECRET_KEY is rejected at startup
- SEC-FIX-2: [Files:...] injection in message text is neutralised before storage
- SEC-FIX-3: File upload content validation (non-images rejected)
- SEC-FIX-4: Account field length limits enforced
- SEC-FIX-5: Password change minimum length
- SEC-FIX-6: IDOR on cancellation endpoints
"""
import pytest
import sqlite3
import os
import sys
import json
import tempfile
import shutil
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    from app import app as flask_app
    test_dir = tempfile.mkdtemp()
    test_db_path = os.path.join(test_dir, 'test_secfix.db')

    main_db_path = 'data/database.db'
    if os.path.exists(main_db_path):
        shutil.copy(main_db_path, test_db_path)

    flask_app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-security-secret-key',
    })

    import database
    orig = database.get_db_connection

    def test_db():
        c = sqlite3.connect(test_db_path, timeout=30.0)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA journal_mode=WAL')
        return c

    database.get_db_connection = test_db

    # Patch all modules that captured get_db_connection at import time
    _originals = {}
    for mod_path in [
        'utils.auth_utils',
        'utils.security',
        'routes.account_routes',
        'core.blueprints.messages.routes',
        'core.blueprints.checkout.routes',
        'core.blueprints.buy.bucket_view',
        'routes.cancellation_routes',
    ]:
        try:
            import importlib
            mod = importlib.import_module(mod_path)
            if hasattr(mod, 'get_db_connection'):
                _originals[mod_path] = mod.get_db_connection
                mod.get_db_connection = test_db
        except Exception:
            pass

    yield flask_app

    # Restore patched references
    for mod_path, orig in _originals.items():
        try:
            import importlib
            mod = importlib.import_module(mod_path)
            mod.get_db_connection = orig
        except Exception:
            pass

    database.get_db_connection = orig
    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(app):
    c = app.test_client()
    import database
    from werkzeug.security import generate_password_hash
    conn = database.get_db_connection()
    try:
        h = generate_password_hash('TestPass123!', method='pbkdf2:sha256')
        conn.execute(
            "INSERT OR IGNORE INTO users (username, password, password_hash, email) VALUES (?,?,?,?)",
            ('fix_buyer', h, h, 'fix_buyer@test.com')
        )
        conn.commit()
        uid = conn.execute("SELECT id FROM users WHERE username='fix_buyer'").fetchone()['id']
    finally:
        conn.close()

    with c.session_transaction() as s:
        s['user_id'] = uid
        s['username'] = 'fix_buyer'

    yield c, uid


# ---------------------------------------------------------------------------
# SEC-FIX-1: Insecure SECRET_KEY rejection
# ---------------------------------------------------------------------------

class TestSecretKeyRejection:
    """The app must refuse to start when SECRET_KEY is a known-insecure value."""

    @pytest.mark.parametrize('bad_key', [
        'your-very-random-fallback-key-here',
        'your-random-secret-key-here-change-this',
        'secret',
        '',
        'tooshort',           # < 32 chars but not in the defaults list
        'a' * 31,             # exactly one char under the 32-char minimum
    ])
    def test_insecure_key_raises_at_startup(self, bad_key):
        import config
        from core import create_app

        original = config.SECRET_KEY
        try:
            config.SECRET_KEY = bad_key
            with patch.dict(os.environ, {'FLASK_ENV': 'production'}):
                with pytest.raises(RuntimeError, match='SECURITY ERROR'):
                    create_app()  # no test_config → security check runs in production mode
        finally:
            config.SECRET_KEY = original

    def test_test_config_bypasses_key_check(self):
        """test_config suppresses the key check so tests can use any key."""
        import config
        from core import create_app

        original = config.SECRET_KEY
        try:
            config.SECRET_KEY = 'your-very-random-fallback-key-here'
            app = create_app(test_config={
                'TESTING': True,
                'WTF_CSRF_ENABLED': False,
                'SECRET_KEY': 'test-override',
            })
            assert app is not None
        finally:
            config.SECRET_KEY = original


# ---------------------------------------------------------------------------
# SEC-FIX-2: [Files:...] injection neutralised in stored message text
# ---------------------------------------------------------------------------

class TestFilesInjectionNeutralised:

    def _setup_order(self, conn, buyer_id):
        """Create a minimal order between buyer and a seller, return (order_id, seller_id)."""
        from werkzeug.security import generate_password_hash
        h = generate_password_hash('pw', method='pbkdf2:sha256')
        conn.execute(
            "INSERT OR IGNORE INTO users (username, password, password_hash, email) VALUES (?,?,?,?)",
            ('fix_seller', h, h, 'fix_seller@test.com')
        )
        conn.commit()
        seller_id = conn.execute("SELECT id FROM users WHERE username='fix_seller'").fetchone()['id']

        conn.execute(
            "INSERT OR IGNORE INTO categories "
            "(metal,product_line,product_type,weight,purity,mint,year,finish,grade,bucket_id) "
            "VALUES ('Gold','GL','Coin','1 oz','0.9999','RCM','2024','BU','Ungraded',88881)"
        )
        conn.commit()
        cat_id = conn.execute("SELECT id FROM categories WHERE bucket_id=88881").fetchone()['id']
        conn.execute(
            "INSERT INTO listings (category_id,seller_id,quantity,price_per_coin,pricing_mode) VALUES (?,?,1,100,'static')",
            (cat_id, seller_id)
        )
        conn.commit()
        lst_id = conn.execute(
            "SELECT id FROM listings WHERE category_id=? AND seller_id=?", (cat_id, seller_id)
        ).fetchone()['id']

        conn.execute(
            "INSERT INTO orders (buyer_id,total_price,status) VALUES (?,100,'Pending')", (buyer_id,)
        )
        conn.commit()
        order_id = conn.execute(
            "SELECT id FROM orders WHERE buyer_id=? ORDER BY id DESC LIMIT 1", (buyer_id,)
        ).fetchone()['id']
        conn.execute(
            "INSERT INTO order_items (order_id,listing_id,quantity,price_each) VALUES (?,?,1,100)",
            (order_id, lst_id)
        )
        conn.commit()
        return order_id, seller_id

    def test_files_bracket_is_neutralised(self, auth_client):
        """[Files:...] in message_text is lowercased before storage."""
        client, uid = auth_client

        import database
        conn = database.get_db_connection()
        try:
            order_id, seller_id = self._setup_order(conn, uid)
        finally:
            conn.close()

        payload = 'Hi [Files: /x" onerror="alert(1)]'
        resp = client.post(
            f'/orders/api/{order_id}/messages/{seller_id}',
            json={'message_text': payload}
        )
        assert resp.status_code == 200
        assert resp.get_json().get('status') == 'sent'

        import database
        conn = database.get_db_connection()
        try:
            msg = conn.execute(
                "SELECT content FROM messages WHERE order_id=? AND sender_id=? ORDER BY id DESC LIMIT 1",
                (order_id, uid)
            ).fetchone()
            stored = msg['content']
            assert '[Files:' not in stored, f"Injection not neutralised: {stored!r}"
        finally:
            conn.close()

    def test_legitimate_message_stored_intact(self, auth_client):
        """A normal message without [Files:] is stored unchanged."""
        client, uid = auth_client

        import database
        conn = database.get_db_connection()
        try:
            order_id, seller_id = self._setup_order(conn, uid)
        finally:
            conn.close()

        text = 'Thanks for the quick shipping!'
        resp = client.post(
            f'/orders/api/{order_id}/messages/{seller_id}',
            json={'message_text': text}
        )
        assert resp.status_code == 200

        import database
        conn = database.get_db_connection()
        try:
            msg = conn.execute(
                "SELECT content FROM messages WHERE order_id=? AND sender_id=? ORDER BY id DESC LIMIT 1",
                (order_id, uid)
            ).fetchone()
            assert msg['content'] == text
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# SEC-FIX-3: File upload content validation
# ---------------------------------------------------------------------------

class TestFileUploadContentValidation:

    def test_php_disguised_as_png_rejected(self):
        from utils.upload_security import validate_upload

        php_bytes = b'<?php system($_GET["cmd"]); ?>'
        f = MagicMock()
        f.filename = 'shell.png'
        f.content_type = 'image/png'
        f.read.return_value = php_bytes
        f.seek.return_value = None

        result = validate_upload(f, allowed_types=['image/png'])
        assert not result['valid'], "PHP disguised as PNG must be rejected"

    def test_html_xss_file_rejected(self):
        from utils.upload_security import validate_upload

        html_bytes = b'<html><script>alert(document.cookie)</script></html>'
        f = MagicMock()
        f.filename = 'xss.png'
        f.content_type = 'image/png'
        f.read.return_value = html_bytes
        f.seek.return_value = None

        result = validate_upload(f, allowed_types=['image/png'])
        assert not result['valid'], "HTML/script file must be rejected"

    def test_empty_file_rejected(self):
        from utils.upload_security import validate_upload

        f = MagicMock()
        f.filename = 'empty.png'
        f.content_type = 'image/png'
        f.read.return_value = b''
        f.seek.return_value = None

        result = validate_upload(f, allowed_types=['image/png'])
        assert not result['valid']

    def test_oversized_file_rejected(self):
        from utils.upload_security import validate_upload

        # 11MB of data — over the 10MB listing_photo limit
        big_data = b'\x89PNG\r\n\x1a\n' + b'X' * (11 * 1024 * 1024)
        f = MagicMock()
        f.filename = 'huge.png'
        f.content_type = 'image/png'
        f.read.return_value = big_data
        f.seek.return_value = None

        result = validate_upload(f, allowed_types=['image/png'], category='listing_photo')
        assert not result['valid'], "File exceeding size limit must be rejected"


# ---------------------------------------------------------------------------
# SEC-FIX-4: Account field length limits
# ---------------------------------------------------------------------------

class TestAccountFieldLengths:

    def test_bio_truncated(self, auth_client):
        client, uid = auth_client
        resp = client.post('/account/update_profile', data={'bio': 'Z' * 9999})
        assert resp.status_code == 200
        assert resp.get_json().get('success') is True

        import database
        conn = database.get_db_connection()
        try:
            row = conn.execute("SELECT bio FROM users WHERE id=?", (uid,)).fetchone()
            assert len(row['bio'] or '') <= 1000
        finally:
            conn.close()

    def test_invalid_email_rejected(self, auth_client):
        client, uid = auth_client
        resp = client.post('/account/update_personal_info', data={
            'email': 'totally-not-an-email',
            'first_name': 'A',
            'last_name': 'B',
            'phone': '123',
        })
        assert resp.status_code == 400
        assert resp.get_json().get('success') is False

    def test_first_name_truncated(self, auth_client):
        client, uid = auth_client
        resp = client.post('/account/update_personal_info', data={
            'email': 'fix_buyer@test.com',
            'first_name': 'N' * 999,
            'last_name': 'A',
            'phone': '123',
        })
        assert resp.status_code == 200

        import database
        conn = database.get_db_connection()
        try:
            row = conn.execute("SELECT first_name FROM users WHERE id=?", (uid,)).fetchone()
            assert len(row['first_name'] or '') <= 100
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# SEC-FIX-5: Password change minimum length
# ---------------------------------------------------------------------------

class TestPasswordChangeMinLength:

    def test_short_new_password_rejected(self, auth_client):
        client, uid = auth_client
        resp = client.post('/account/change_password', data={
            'current_password': 'TestPass123!',
            'new_password': 'ab',
        })
        assert resp.status_code == 400
        assert resp.get_json().get('success') is False

    def test_wrong_current_password_rejected(self, auth_client):
        client, uid = auth_client
        resp = client.post('/account/change_password', data={
            'current_password': 'Wrong!',
            'new_password': 'ValidNewPass123',
        })
        assert resp.status_code == 400
        assert resp.get_json().get('success') is False


# ---------------------------------------------------------------------------
# SEC-FIX-6: IDOR on cancellation/order endpoints
# ---------------------------------------------------------------------------

class TestIDORPrevention:

    def _create_other_order(self, conn):
        from werkzeug.security import generate_password_hash
        h = generate_password_hash('pw', method='pbkdf2:sha256')
        conn.execute(
            "INSERT OR IGNORE INTO users (username, password, password_hash, email) VALUES (?,?,?,?)",
            ('idor_owner', h, h, 'idor@test.com')
        )
        conn.commit()
        other_id = conn.execute("SELECT id FROM users WHERE username='idor_owner'").fetchone()['id']
        conn.execute(
            "INSERT INTO orders (buyer_id,total_price,status) VALUES (?,99,'Pending')", (other_id,)
        )
        conn.commit()
        return conn.execute(
            "SELECT id FROM orders WHERE buyer_id=? ORDER BY id DESC LIMIT 1", (other_id,)
        ).fetchone()['id']

    def test_cannot_view_other_users_cancellation_status(self, auth_client):
        client, uid = auth_client
        import database
        conn = database.get_db_connection()
        try:
            other_order_id = self._create_other_order(conn)
        finally:
            conn.close()

        resp = client.get(f'/api/orders/{other_order_id}/cancellation/status')
        assert resp.status_code in (403, 404)
        data = resp.get_json()
        assert data.get('success') is not True

    def test_cannot_cancel_other_users_order(self, auth_client):
        client, uid = auth_client
        import database
        conn = database.get_db_connection()
        try:
            other_order_id = self._create_other_order(conn)
        finally:
            conn.close()

        resp = client.post(
            f'/api/orders/{other_order_id}/cancel',
            json={'reason': 'Changed my mind', 'additional_details': ''}
        )
        assert resp.status_code in (403, 404)
        assert resp.get_json().get('success') is not True

    def test_unauthenticated_cannot_cancel(self, client):
        resp = client.post(
            '/api/orders/999/cancel',
            json={'reason': 'test'}
        )
        assert resp.status_code == 401
