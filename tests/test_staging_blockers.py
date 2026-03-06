"""
Staging-blocker regression tests.

Covers the four hard blockers before public staging:
- BLOCK-1: Cancellation approval race / double inventory restore
- BLOCK-2: Weak / short SECRET_KEY rejected in production mode
- BLOCK-3: Report attachments served via access-controlled route only
- BLOCK-4: Notification settings route rejects unknown keys
"""

import pytest
import sqlite3
import os
import sys
import tempfile
import shutil
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    from app import app as flask_app
    test_dir = tempfile.mkdtemp()
    test_db_path = os.path.join(test_dir, 'test_blockers.db')

    main_db_path = 'data/database.db'
    if os.path.exists(main_db_path):
        shutil.copy(main_db_path, test_db_path)

    flask_app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-staging-blocker-secret-key-32c',
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
        'routes.report_routes',
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


def _make_user(conn, username, email):
    from werkzeug.security import generate_password_hash
    h = generate_password_hash('TestPass123!', method='pbkdf2:sha256')
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, password_hash, email) VALUES (?,?,?,?)",
        (username, h, h, email)
    )
    conn.commit()
    return conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()['id']


def _auth_client(app, uid):
    c = app.test_client()
    with c.session_transaction() as s:
        s['user_id'] = uid
        s['username'] = 'testuser'
    return c


# ---------------------------------------------------------------------------
# BLOCK-1: Cancellation approval race — double inventory restore
# ---------------------------------------------------------------------------

class TestCancellationApprovalRace:
    """
    The cancellation approval path must be idempotent and restore inventory
    exactly once, regardless of concurrent approvals.
    """

    def _setup(self, conn, buyer_id, seller1_id, seller2_id):
        """Set up an order and pending cancellation request with two sellers."""
        conn.execute(
            "INSERT OR IGNORE INTO categories "
            "(metal,product_line,product_type,weight,purity,mint,year,finish,grade,bucket_id) "
            "VALUES ('Gold','GL','Coin','1 oz','0.9999','RCM','2024','BU','Ungraded',77771)"
        )
        conn.commit()
        cat_id = conn.execute("SELECT id FROM categories WHERE bucket_id=77771").fetchone()['id']

        # Two listings, one per seller
        conn.execute(
            "INSERT INTO listings (category_id,seller_id,quantity,price_per_coin,pricing_mode,active) "
            "VALUES (?,?,3,100,'static',1)", (cat_id, seller1_id)
        )
        conn.execute(
            "INSERT INTO listings (category_id,seller_id,quantity,price_per_coin,pricing_mode,active) "
            "VALUES (?,?,2,100,'static',1)", (cat_id, seller2_id)
        )
        conn.commit()

        lst1 = conn.execute(
            "SELECT id FROM listings WHERE category_id=? AND seller_id=?", (cat_id, seller1_id)
        ).fetchone()['id']
        lst2 = conn.execute(
            "SELECT id FROM listings WHERE category_id=? AND seller_id=?", (cat_id, seller2_id)
        ).fetchone()['id']

        # Create order with both listings, then reduce listing quantities (simulating purchase)
        conn.execute(
            "INSERT INTO orders (buyer_id,total_price,status) VALUES (?,500,'Pending')", (buyer_id,)
        )
        conn.commit()
        order_id = conn.execute(
            "SELECT id FROM orders WHERE buyer_id=? ORDER BY id DESC LIMIT 1", (buyer_id,)
        ).fetchone()['id']

        conn.execute(
            "INSERT INTO order_items (order_id,listing_id,quantity,price_each) VALUES (?,?,3,100)",
            (order_id, lst1)
        )
        conn.execute(
            "INSERT INTO order_items (order_id,listing_id,quantity,price_each) VALUES (?,?,2,100)",
            (order_id, lst2)
        )
        # Reduce stock to simulate purchase
        conn.execute("UPDATE listings SET quantity=0, active=0 WHERE id=?", (lst1,))
        conn.execute("UPDATE listings SET quantity=0, active=0 WHERE id=?", (lst2,))

        # Create cancellation request
        cur = conn.execute(
            "INSERT INTO cancellation_requests (order_id,buyer_id,reason,additional_details) "
            "VALUES (?,'%d','Changed my mind','')" % buyer_id, (order_id,)
        )
        request_id = cur.lastrowid

        # Create seller response slots
        conn.execute(
            "INSERT INTO cancellation_seller_responses (request_id,seller_id) VALUES (?,?)",
            (request_id, seller1_id)
        )
        conn.execute(
            "INSERT INTO cancellation_seller_responses (request_id,seller_id) VALUES (?,?)",
            (request_id, seller2_id)
        )
        conn.commit()

        return order_id, request_id, lst1, lst2

    def test_single_approval_restores_inventory_once(self, app):
        """Both sellers approve; inventory must be restored exactly to original quantities."""
        import database
        conn = database.get_db_connection()
        try:
            buyer_id = _make_user(conn, 'cancel_buyer', 'cancel_buyer@test.com')
            seller1_id = _make_user(conn, 'cancel_seller1', 'cancel_seller1@test.com')
            seller2_id = _make_user(conn, 'cancel_seller2', 'cancel_seller2@test.com')
            order_id, request_id, lst1, lst2 = self._setup(conn, buyer_id, seller1_id, seller2_id)
        finally:
            conn.close()

        # Seller 1 approves
        c1 = _auth_client(app, seller1_id)
        r1 = c1.post(
            f'/api/orders/{order_id}/cancel/respond',
            json={'response': 'approved'}
        )
        assert r1.status_code == 200

        # Seller 2 approves — this is the last one, triggers the actual cancel
        c2 = _auth_client(app, seller2_id)
        r2 = c2.post(
            f'/api/orders/{order_id}/cancel/respond',
            json={'response': 'approved'}
        )
        assert r2.status_code == 200
        data2 = r2.get_json()
        assert data2.get('final_status') == 'approved'

        # Verify inventory restored exactly once (qty 3 and 2 respectively)
        import database
        conn = database.get_db_connection()
        try:
            q1 = conn.execute("SELECT quantity FROM listings WHERE id=?", (lst1,)).fetchone()['quantity']
            q2 = conn.execute("SELECT quantity FROM listings WHERE id=?", (lst2,)).fetchone()['quantity']
            assert q1 == 3, f"Listing 1 quantity should be 3, got {q1}"
            assert q2 == 2, f"Listing 2 quantity should be 2, got {q2}"
        finally:
            conn.close()

    def test_double_approve_request_is_idempotent(self, app):
        """Seller 2 approving twice must not restore inventory twice."""
        import database
        conn = database.get_db_connection()
        try:
            buyer_id = _make_user(conn, 'cancel_buyer2', 'cancel_buyer2@test.com')
            seller1_id = _make_user(conn, 'cancel_seller3', 'cancel_seller3@test.com')
            seller2_id = _make_user(conn, 'cancel_seller4', 'cancel_seller4@test.com')
            order_id, request_id, lst1, lst2 = self._setup(conn, buyer_id, seller1_id, seller2_id)
        finally:
            conn.close()

        c1 = _auth_client(app, seller1_id)
        c1.post(f'/api/orders/{order_id}/cancel/respond', json={'response': 'approved'})

        c2 = _auth_client(app, seller2_id)
        # First approval — transitions the order
        r_first = c2.post(f'/api/orders/{order_id}/cancel/respond', json={'response': 'approved'})
        assert r_first.status_code == 200

        # Simulate a second concurrent request for the same seller
        # (in reality this is the race: seller's browser sent two requests)
        # The server should reject the second approval attempt gracefully.
        r_second = c2.post(f'/api/orders/{order_id}/cancel/respond', json={'response': 'approved'})
        assert r_second.status_code in (200, 400, 404), \
            "Second approval must not crash or cause inventory to double"

        # Inventory must still be at restored-once levels
        import database
        conn = database.get_db_connection()
        try:
            q1 = conn.execute("SELECT quantity FROM listings WHERE id=?", (lst1,)).fetchone()['quantity']
            q2 = conn.execute("SELECT quantity FROM listings WHERE id=?", (lst2,)).fetchone()['quantity']
            assert q1 == 3, f"After idempotent double-approve, qty1 should be 3, got {q1}"
            assert q2 == 2, f"After idempotent double-approve, qty2 should be 2, got {q2}"
        finally:
            conn.close()

    def test_cancellation_request_status_is_approved_not_pending_after_approval(self, app):
        """After all sellers approve, the request row must be status='approved'."""
        import database
        conn = database.get_db_connection()
        try:
            buyer_id = _make_user(conn, 'cancel_buyer3', 'cancel_buyer3@test.com')
            seller1_id = _make_user(conn, 'cancel_seller5', 'cancel_seller5@test.com')
            seller2_id = _make_user(conn, 'cancel_seller6', 'cancel_seller6@test.com')
            order_id, request_id, lst1, lst2 = self._setup(conn, buyer_id, seller1_id, seller2_id)
        finally:
            conn.close()

        _auth_client(app, seller1_id).post(
            f'/api/orders/{order_id}/cancel/respond', json={'response': 'approved'}
        )
        _auth_client(app, seller2_id).post(
            f'/api/orders/{order_id}/cancel/respond', json={'response': 'approved'}
        )

        import database
        conn = database.get_db_connection()
        try:
            status = conn.execute(
                "SELECT status FROM cancellation_requests WHERE id=?", (request_id,)
            ).fetchone()['status']
            assert status == 'approved', f"Expected 'approved', got '{status}'"

            order_status = conn.execute(
                "SELECT status FROM orders WHERE id=?", (order_id,)
            ).fetchone()['status']
            assert order_status == 'Canceled', f"Expected 'Canceled', got '{order_status}'"
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# BLOCK-2: Weak / short SECRET_KEY rejected in production mode
# ---------------------------------------------------------------------------

class TestSecretKeyStrength:
    """SECRET_KEY must be rejected if too short or a known default."""

    @pytest.mark.parametrize('bad_key', [
        '',
        'secret',
        'tooshort',          # not in known-bad list but < 32 chars
        'a' * 31,            # exactly one under the limit
        'your-very-random-fallback-key-here',
    ])
    def test_short_or_default_key_raises_in_production(self, bad_key):
        import config
        from core import create_app

        original = config.SECRET_KEY
        try:
            config.SECRET_KEY = bad_key
            with patch.dict(os.environ, {'FLASK_ENV': 'production'}):
                with pytest.raises(RuntimeError, match='SECURITY ERROR'):
                    create_app()
        finally:
            config.SECRET_KEY = original

    def test_exactly_32_char_key_accepted_in_production(self):
        """A key of exactly 32 chars that is not a known default must be accepted."""
        import config
        from core import create_app

        original = config.SECRET_KEY
        # 32 chars, not in the known-bad set
        good_key = 'x' * 32
        try:
            config.SECRET_KEY = good_key
            with patch.dict(os.environ, {'FLASK_ENV': 'production'}):
                app = create_app(test_config={
                    'TESTING': True,
                    'WTF_CSRF_ENABLED': False,
                    'SECRET_KEY': good_key,
                })
                assert app is not None
        finally:
            config.SECRET_KEY = original

    def test_64_char_random_key_accepted(self):
        """A hex(32) key (64 hex chars) must be accepted without error."""
        import config
        from core import create_app
        import secrets as _sec

        original = config.SECRET_KEY
        good_key = _sec.token_hex(32)  # 64 chars
        try:
            config.SECRET_KEY = good_key
            with patch.dict(os.environ, {'FLASK_ENV': 'production'}):
                app = create_app(test_config={
                    'TESTING': True,
                    'WTF_CSRF_ENABLED': False,
                    'SECRET_KEY': good_key,
                })
                assert app is not None
        finally:
            config.SECRET_KEY = original


# ---------------------------------------------------------------------------
# BLOCK-3: Report attachments — access-controlled serve route
# ---------------------------------------------------------------------------

class TestReportAttachmentAccess:
    """Report attachment files must not be publicly accessible."""

    def _create_report_with_attachment(self, conn, reporter_id, reported_id, report_id_hint=None):
        """Insert a report and a synthetic attachment row; return (report_id, attachment_id)."""
        # Minimal order
        conn.execute(
            "INSERT OR IGNORE INTO categories "
            "(metal,product_line,product_type,weight,purity,mint,year,finish,grade,bucket_id) "
            "VALUES ('Silver','SL','Coin','1 oz','0.999','RCM','2024','BU','Ungraded',77772)"
        )
        conn.commit()
        cat_id = conn.execute("SELECT id FROM categories WHERE bucket_id=77772").fetchone()['id']
        conn.execute(
            "INSERT INTO listings (category_id,seller_id,quantity,price_per_coin,pricing_mode,active) "
            "VALUES (?,?,1,50,'static',1)", (cat_id, reported_id)
        )
        conn.commit()
        lst_id = conn.execute(
            "SELECT id FROM listings WHERE category_id=? AND seller_id=?", (cat_id, reported_id)
        ).fetchone()['id']

        conn.execute(
            "INSERT INTO orders (buyer_id,total_price,status) VALUES (?,50,'Delivered')", (reporter_id,)
        )
        conn.commit()
        order_id = conn.execute(
            "SELECT id FROM orders WHERE buyer_id=? ORDER BY id DESC LIMIT 1", (reporter_id,)
        ).fetchone()['id']
        conn.execute(
            "INSERT INTO order_items (order_id,listing_id,quantity,price_each) VALUES (?,?,1,50)",
            (order_id, lst_id)
        )

        # Report
        cur = conn.execute(
            "INSERT INTO reports (reporter_user_id,reported_user_id,order_id,reason,comment) "
            "VALUES (?,?,?,'scam_fraud','test')",
            (reporter_id, reported_id, order_id)
        )
        conn.commit()
        report_id = cur.lastrowid

        # Fake attachment row (file doesn't need to exist for auth tests)
        cur2 = conn.execute(
            "INSERT INTO report_attachments (report_id,file_path,original_filename) "
            "VALUES (?,?,'evidence.png')",
            (report_id, 'fakefile_for_test.png')
        )
        conn.commit()
        attachment_id = cur2.lastrowid

        return report_id, attachment_id

    def test_unauthenticated_cannot_access_attachment(self, client, app):
        import database
        conn = database.get_db_connection()
        try:
            rep_id = _make_user(conn, 'attach_reporter', 'attach_rep@test.com')
            rpd_id = _make_user(conn, 'attach_reported', 'attach_rpd@test.com')
            report_id, att_id = self._create_report_with_attachment(conn, rep_id, rpd_id)
        finally:
            conn.close()

        resp = client.get(f'/api/reports/{report_id}/attachments/{att_id}')
        assert resp.status_code == 401

    def test_non_reporter_cannot_access_attachment(self, app):
        """A different authenticated user who is neither reporter nor admin gets 403."""
        import database
        conn = database.get_db_connection()
        try:
            rep_id = _make_user(conn, 'attach_reporter2', 'attach_rep2@test.com')
            rpd_id = _make_user(conn, 'attach_reported2', 'attach_rpd2@test.com')
            stranger_id = _make_user(conn, 'attach_stranger', 'attach_str@test.com')
            report_id, att_id = self._create_report_with_attachment(conn, rep_id, rpd_id)
        finally:
            conn.close()

        c = _auth_client(app, stranger_id)
        resp = c.get(f'/api/reports/{report_id}/attachments/{att_id}')
        assert resp.status_code == 403

    def test_reporter_can_access_own_attachment(self, app, tmp_path):
        """The reporter must be able to retrieve their own attachment."""
        import database
        from routes.report_routes import REPORT_ATTACH_DIR

        conn = database.get_db_connection()
        try:
            rep_id = _make_user(conn, 'attach_reporter3', 'attach_rep3@test.com')
            rpd_id = _make_user(conn, 'attach_reported3', 'attach_rpd3@test.com')
            report_id, att_id = self._create_report_with_attachment(conn, rep_id, rpd_id)

            # Update the DB row to point at a real temporary file
            import os
            os.makedirs(REPORT_ATTACH_DIR, exist_ok=True)
            real_file = os.path.join(REPORT_ATTACH_DIR, 'fakefile_for_test.png')
            with open(real_file, 'wb') as fh:
                # Minimal valid 1×1 PNG
                fh.write(bytes([
                    0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a,
                    0x00,0x00,0x00,0x0d,0x49,0x48,0x44,0x52,
                    0x00,0x00,0x00,0x01,0x00,0x00,0x00,0x01,
                    0x08,0x02,0x00,0x00,0x00,0x90,0x77,0x53,
                    0xde,0x00,0x00,0x00,0x0c,0x49,0x44,0x41,
                    0x54,0x08,0xd7,0x63,0xf8,0xcf,0xc0,0x00,
                    0x00,0x00,0x02,0x00,0x01,0xe2,0x21,0xbc,
                    0x33,0x00,0x00,0x00,0x00,0x49,0x45,0x4e,
                    0x44,0xae,0x42,0x60,0x82
                ]))
        finally:
            conn.close()

        c = _auth_client(app, rep_id)
        resp = c.get(f'/api/reports/{report_id}/attachments/{att_id}')
        assert resp.status_code == 200

    def test_static_path_not_accessible(self, client):
        """
        Direct access to the old static/uploads/reports/ path must return 404
        (directory should not exist or be served by Flask static handler at that sub-path).
        This is a belt-and-suspenders check: files are no longer written there.
        """
        resp = client.get('/static/uploads/reports/anyfile.png')
        # Either 404 (no such file) or 301/302 (redirect) — NOT 200
        assert resp.status_code != 200 or resp.data == b'', \
            "Old static/uploads/reports path must not serve files"


# ---------------------------------------------------------------------------
# BLOCK-4: Notification settings route rejects unknown keys
# ---------------------------------------------------------------------------

class TestNotificationSettingsAllowlist:
    """Unknown notification type keys must be rejected with HTTP 400."""

    def _auth_client_for_test(self, app):
        import database
        conn = database.get_db_connection()
        try:
            uid = _make_user(conn, 'notif_settings_user', 'notif_settings@test.com')
        finally:
            conn.close()
        return _auth_client(app, uid), uid

    def test_unknown_key_rejected(self, app):
        c, _ = self._auth_client_for_test(app)
        resp = c.post(
            '/notifications/settings',
            json={'totally_made_up_type': True}
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'Unknown' in data.get('error', '') or 'unknown' in data.get('error', '')

    def test_multiple_unknown_keys_rejected(self, app):
        c, _ = self._auth_client_for_test(app)
        resp = c.post(
            '/notifications/settings',
            json={'xss_injection': True, 'another_bad_key': False}
        )
        assert resp.status_code == 400

    def test_valid_key_accepted(self, app):
        c, _ = self._auth_client_for_test(app)
        resp = c.post(
            '/notifications/settings',
            json={'new_login': False}
        )
        assert resp.status_code == 200
        assert resp.get_json().get('success') is True

    def test_mix_of_valid_and_invalid_keys_rejected(self, app):
        """If even one key is unknown, the entire batch must be rejected."""
        c, _ = self._auth_client_for_test(app)
        resp = c.post(
            '/notifications/settings',
            json={'new_login': True, 'evil_unknown_key': True}
        )
        assert resp.status_code == 400

    def test_empty_payload_rejected(self, app):
        c, _ = self._auth_client_for_test(app)
        resp = c.post('/notifications/settings', json={})
        assert resp.status_code == 400

    def test_all_known_defaults_accepted(self, app):
        """Every key in NOTIFICATION_DEFAULTS must be accepted."""
        from services.notification_service import NOTIFICATION_DEFAULTS
        c, _ = self._auth_client_for_test(app)
        # Send a batch of all known types
        payload = {k: False for k in NOTIFICATION_DEFAULTS}
        resp = c.post('/notifications/settings', json=payload)
        assert resp.status_code == 200
