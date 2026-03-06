"""
Second-pass adversarial security regression tests.

Covers vulnerabilities found in the second-pass review:
- SEC2-1: XSS guard in listings_tab specItem (escHtml present)
- SEC2-2: /bucket/<id>/update-price requires auth
- SEC2-3: mark_notification_read ownership check
- SEC2-4: Rating value must be 1–5
- SEC2-5: Message participant must be a counterparty
- SEC2-6: Report uploads use content validation
- SEC2-7: Cancellation stats restricted to owner/admin
- SEC2-8: Admin message reply length capped at 4000 chars
"""

import pytest
import sqlite3
import os
import sys
import tempfile
import shutil
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    from app import app as flask_app
    test_dir = tempfile.mkdtemp()
    test_db_path = os.path.join(test_dir, 'test_pass2.db')

    main_db_path = 'data/database.db'
    if os.path.exists(main_db_path):
        shutil.copy(main_db_path, test_db_path)

    flask_app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-pass2-secret',
    })

    import database
    orig = database.get_db_connection

    def test_db():
        c = sqlite3.connect(test_db_path, timeout=30.0)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA journal_mode=WAL')
        return c

    database.get_db_connection = test_db

    _originals = {}
    for mod_path in [
        'utils.auth_utils',
        'utils.security',
        'routes.account_routes',
        'core.blueprints.messages.routes',
        'core.blueprints.checkout.routes',
        'core.blueprints.buy.bucket_view',
        'routes.cancellation_routes',
        'routes.notification_routes',
        'routes.ratings_routes',
        'routes.bucket_routes',
        'services.notification_service',
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

    for mod_path, o in _originals.items():
        try:
            import importlib
            mod = importlib.import_module(mod_path)
            mod.get_db_connection = o
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
            ('pass2_user', h, h, 'pass2_user@test.com')
        )
        conn.commit()
        uid = conn.execute("SELECT id FROM users WHERE username='pass2_user'").fetchone()['id']
    finally:
        conn.close()

    with c.session_transaction() as s:
        s['user_id'] = uid
        s['username'] = 'pass2_user'

    yield c, uid


# ---------------------------------------------------------------------------
# SEC2-1: XSS — escHtml present in listings_tab
# ---------------------------------------------------------------------------

class TestXSSEscapingInListingsTab:
    """escHtml helper must exist in listings_tab.html."""

    def test_eschtml_defined_in_listings_tab(self):
        """listings_tab.html must define an escHtml() JavaScript function."""
        with open('templates/tabs/listings_tab.html', 'r') as f:
            content = f.read()
        assert 'function escHtml' in content, \
            "escHtml() must be defined in listings_tab.html to prevent XSS"

    def test_specitem_uses_eschtml(self):
        """specItem must use escHtml() for the value field."""
        with open('templates/tabs/listings_tab.html', 'r') as f:
            content = f.read()
        # Check that escHtml wraps the value in specItem
        assert 'escHtml(value)' in content, \
            "specItem() must use escHtml(value) to prevent stored XSS"

    def test_title_uses_eschtml_in_innerhtml(self):
        """title must be escaped before injection into innerHTML."""
        with open('templates/tabs/listings_tab.html', 'r') as f:
            content = f.read()
        assert 'escHtml(title)' in content, \
            "title must be wrapped with escHtml() when used in innerHTML"


# ---------------------------------------------------------------------------
# SEC2-2: /bucket/<id>/update-price requires authentication
# ---------------------------------------------------------------------------

class TestBucketUpdatePriceAuth:
    """Unauthenticated requests to update-price must be rejected."""

    def test_unauthenticated_update_price_rejected(self, client):
        resp = client.post('/bucket/99999/update-price')
        assert resp.status_code == 401, \
            "/bucket/<id>/update-price must require authentication"


# ---------------------------------------------------------------------------
# SEC2-3: mark_notification_read ownership check
# ---------------------------------------------------------------------------

class TestNotificationReadOwnership:
    """A user must not be able to mark another user's notification as read."""

    def _create_notification_for_user(self, conn, user_id, msg='test notification'):
        """Insert a raw notification for user_id and return its id."""
        cur = conn.execute(
            "INSERT INTO notifications (user_id, type, title, message) "
            "VALUES (?, 'system', 'Test', ?)",
            (user_id, msg)
        )
        conn.commit()
        return cur.lastrowid

    def _create_other_user(self, conn):
        from werkzeug.security import generate_password_hash
        h = generate_password_hash('pw', method='pbkdf2:sha256')
        conn.execute(
            "INSERT OR IGNORE INTO users (username, password, password_hash, email) VALUES (?,?,?,?)",
            ('notif_victim', h, h, 'notif_victim@test.com')
        )
        conn.commit()
        return conn.execute("SELECT id FROM users WHERE username='notif_victim'").fetchone()['id']

    def test_cannot_mark_other_users_notification_read(self, auth_client):
        client, uid = auth_client
        import database
        conn = database.get_db_connection()
        try:
            victim_id = self._create_other_user(conn)
            notif_id = self._create_notification_for_user(conn, victim_id)
        finally:
            conn.close()

        # Try to mark victim's notification as read
        resp = client.post(f'/notifications/{notif_id}/read')
        assert resp.status_code in (404, 403), \
            "Should not be able to mark another user's notification as read"

        # Verify notification is still unread in DB
        import database
        conn = database.get_db_connection()
        try:
            row = conn.execute(
                "SELECT is_read FROM notifications WHERE id=?", (notif_id,)
            ).fetchone()
            assert row is None or row['is_read'] == 0, \
                "Other user's notification must not be marked read"
        finally:
            conn.close()

    def test_can_mark_own_notification_read(self, auth_client):
        client, uid = auth_client
        import database
        conn = database.get_db_connection()
        try:
            notif_id = self._create_notification_for_user(conn, uid)
        finally:
            conn.close()

        resp = client.post(f'/notifications/{notif_id}/read')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True


# ---------------------------------------------------------------------------
# SEC2-4: Rating must be in 1–5 range
# ---------------------------------------------------------------------------

class TestRatingRangeValidation:
    """Ratings outside 1–5 must be rejected."""

    def _setup_completed_order(self, conn, buyer_id):
        """Create a seller and a completed order for buyer."""
        from werkzeug.security import generate_password_hash
        h = generate_password_hash('pw', method='pbkdf2:sha256')
        conn.execute(
            "INSERT OR IGNORE INTO users (username, password, password_hash, email) VALUES (?,?,?,?)",
            ('rating_seller', h, h, 'rating_seller@test.com')
        )
        conn.commit()
        seller_id = conn.execute("SELECT id FROM users WHERE username='rating_seller'").fetchone()['id']

        conn.execute(
            "INSERT OR IGNORE INTO categories "
            "(metal,product_line,product_type,weight,purity,mint,year,finish,grade,bucket_id) "
            "VALUES ('Gold','GL','Coin','1 oz','0.9999','RCM','2024','BU','Ungraded',99991)"
        )
        conn.commit()
        cat_id = conn.execute("SELECT id FROM categories WHERE bucket_id=99991").fetchone()['id']
        conn.execute(
            "INSERT INTO listings (category_id,seller_id,quantity,price_per_coin,pricing_mode) VALUES (?,?,1,100,'static')",
            (cat_id, seller_id)
        )
        conn.commit()
        lst_id = conn.execute(
            "SELECT id FROM listings WHERE category_id=? AND seller_id=?", (cat_id, seller_id)
        ).fetchone()['id']

        conn.execute(
            "INSERT INTO orders (buyer_id,total_price,status) VALUES (?,100,'Complete')", (buyer_id,)
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
        return order_id

    def test_rating_zero_rejected(self, auth_client):
        client, uid = auth_client
        import database
        conn = database.get_db_connection()
        try:
            order_id = self._setup_completed_order(conn, uid)
        finally:
            conn.close()

        resp = client.post(f'/rate/{order_id}',
                           data={'rating': '0', 'comment': 'bad'},
                           headers={'X-Requested-With': 'XMLHttpRequest'})
        assert resp.status_code == 400
        assert 'error' in (resp.get_json() or {})

    def test_rating_six_rejected(self, auth_client):
        client, uid = auth_client
        import database
        conn = database.get_db_connection()
        try:
            order_id = self._setup_completed_order(conn, uid)
        finally:
            conn.close()

        resp = client.post(f'/rate/{order_id}',
                           data={'rating': '6', 'comment': 'too high'},
                           headers={'X-Requested-With': 'XMLHttpRequest'})
        assert resp.status_code == 400

    def test_negative_rating_rejected(self, auth_client):
        client, uid = auth_client
        import database
        conn = database.get_db_connection()
        try:
            order_id = self._setup_completed_order(conn, uid)
        finally:
            conn.close()

        resp = client.post(f'/rate/{order_id}',
                           data={'rating': '-999', 'comment': 'malicious'},
                           headers={'X-Requested-With': 'XMLHttpRequest'})
        assert resp.status_code == 400

    def test_valid_rating_accepted(self, auth_client):
        client, uid = auth_client
        import database
        conn = database.get_db_connection()
        try:
            order_id = self._setup_completed_order(conn, uid)
        finally:
            conn.close()

        resp = client.post(f'/rate/{order_id}',
                           data={'rating': '5', 'comment': 'great'},
                           headers={'X-Requested-With': 'XMLHttpRequest'})
        assert resp.status_code == 200
        assert resp.get_json().get('success') is True


# ---------------------------------------------------------------------------
# SEC2-5: Message participant_id must be a counterparty
# ---------------------------------------------------------------------------

class TestMessageParticipantIDValidation:
    """Cannot send order messages to arbitrary non-counterparty users."""

    def _setup_order(self, conn, buyer_id):
        from werkzeug.security import generate_password_hash
        h = generate_password_hash('pw', method='pbkdf2:sha256')
        conn.execute(
            "INSERT OR IGNORE INTO users (username, password, password_hash, email) VALUES (?,?,?,?)",
            ('msg_seller', h, h, 'msg_seller@test.com')
        )
        conn.execute(
            "INSERT OR IGNORE INTO users (username, password, password_hash, email) VALUES (?,?,?,?)",
            ('msg_stranger', h, h, 'msg_stranger@test.com')
        )
        conn.commit()
        seller_id = conn.execute("SELECT id FROM users WHERE username='msg_seller'").fetchone()['id']
        stranger_id = conn.execute("SELECT id FROM users WHERE username='msg_stranger'").fetchone()['id']

        conn.execute(
            "INSERT OR IGNORE INTO categories "
            "(metal,product_line,product_type,weight,purity,mint,year,finish,grade,bucket_id) "
            "VALUES ('Gold','GL','Coin','1 oz','0.9999','RCM','2024','BU','Ungraded',99992)"
        )
        conn.commit()
        cat_id = conn.execute("SELECT id FROM categories WHERE bucket_id=99992").fetchone()['id']
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
        return order_id, seller_id, stranger_id

    def test_cannot_message_stranger_via_order(self, auth_client):
        """Buyer cannot use a valid order_id to message an unrelated user."""
        client, uid = auth_client
        import database
        conn = database.get_db_connection()
        try:
            order_id, seller_id, stranger_id = self._setup_order(conn, uid)
        finally:
            conn.close()

        resp = client.post(
            f'/orders/api/{order_id}/messages/{stranger_id}',
            json={'message_text': 'Hi stranger!'}
        )
        assert resp.status_code in (400, 403), \
            "Must reject messages to non-counterparty users"

    def test_can_message_real_seller(self, auth_client):
        """Buyer can message the actual seller for that order."""
        client, uid = auth_client
        import database
        conn = database.get_db_connection()
        try:
            order_id, seller_id, _ = self._setup_order(conn, uid)
        finally:
            conn.close()

        resp = client.post(
            f'/orders/api/{order_id}/messages/{seller_id}',
            json={'message_text': 'Hello seller'}
        )
        assert resp.status_code == 200
        assert resp.get_json().get('status') == 'sent'


# ---------------------------------------------------------------------------
# SEC2-6: Report uploads use content validation
# ---------------------------------------------------------------------------

class TestReportUploadContentValidation:
    """Report photo uploads must reject non-image content."""

    def test_report_upload_routes_use_content_validation(self):
        """report_routes.py must import upload_security validation helpers."""
        with open('routes/report_routes.py', 'r') as f:
            content = f.read()
        # Must use content-based validation (validate_upload or save_secure_upload)
        assert 'utils.upload_security' in content, \
            "report_routes.py must import from utils.upload_security"
        assert 'validate_upload' in content or 'save_secure_upload' in content, \
            "report_routes.py must use validate_upload or save_secure_upload for content validation"
        # Files must be stored outside static/ (access-controlled directory)
        assert 'REPORT_ATTACH_DIR' in content, \
            "report_routes.py must store attachments in REPORT_ATTACH_DIR (outside static/)"


# ---------------------------------------------------------------------------
# SEC2-7: Cancellation stats restricted to owner/admin
# ---------------------------------------------------------------------------

class TestCancellationStatsIDOR:
    """A user must not be able to view another user's cancellation stats."""

    def _create_other_user(self, conn):
        from werkzeug.security import generate_password_hash
        h = generate_password_hash('pw', method='pbkdf2:sha256')
        conn.execute(
            "INSERT OR IGNORE INTO users (username, password, password_hash, email) VALUES (?,?,?,?)",
            ('stats_victim', h, h, 'stats_victim@test.com')
        )
        conn.commit()
        return conn.execute("SELECT id FROM users WHERE username='stats_victim'").fetchone()['id']

    def test_cannot_view_other_users_cancellation_stats(self, auth_client):
        client, uid = auth_client
        import database
        conn = database.get_db_connection()
        try:
            victim_id = self._create_other_user(conn)
        finally:
            conn.close()

        resp = client.get(f'/api/seller/{victim_id}/cancellation-stats')
        assert resp.status_code in (401, 403), \
            "Must not expose another user's cancellation stats"

    def test_can_view_own_cancellation_stats(self, auth_client):
        client, uid = auth_client
        resp = client.get(f'/api/seller/{uid}/cancellation-stats')
        assert resp.status_code == 200
        assert resp.get_json().get('success') is True


# ---------------------------------------------------------------------------
# SEC2-8: Admin message reply length limit
# ---------------------------------------------------------------------------

class TestAdminMessageLengthLimit:
    """Admin message reply text is capped server-side."""

    def test_admin_reply_length_capped(self):
        """Verify the cap is applied in the source code."""
        with open('core/blueprints/messages/routes.py', 'r') as f:
            content = f.read()
        # The truncation [:4000] must be present in the admin reply function
        assert '[:4000]' in content, \
            "Admin message reply must truncate message_text to a safe length"
