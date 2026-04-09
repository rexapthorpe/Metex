"""
Tests for delivery-based payout eligibility.

Covers:
1. Payout blocked when tracking exists but delivered_at is null
2. Payout blocked when delivered but delay hours not yet elapsed
3. Payout becomes eligible after delay elapsed
4. ACH clearance still blocks even if delivered
5. Refunded / on-hold payouts remain blocked
6. Admin mark-delivered action sets delivered_at
7. System setting is read and applied correctly
"""
import pytest
import sqlite3 as _sqlite3
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Shared fixture: minimal DB for get_payout_block_reason
# ---------------------------------------------------------------------------

@pytest.fixture
def delivery_db(tmp_path):
    """
    In-memory SQLite DB with seller_order_tracking.delivered_at column.
    Returns (conn, insert_fn) where insert_fn creates one payout scenario.
    """
    conn = _sqlite3.connect(':memory:')
    conn.row_factory = _sqlite3.Row

    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            stripe_account_id TEXT,
            stripe_payouts_enabled INTEGER DEFAULT 1
        );
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            buyer_id INTEGER,
            payment_status TEXT DEFAULT 'paid',
            payment_method_type TEXT DEFAULT 'card',
            requires_payment_clearance INTEGER DEFAULT 0,
            payment_cleared_at TEXT,
            refund_status TEXT DEFAULT 'not_refunded',
            requires_payout_recovery INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Pending'
        );
        CREATE TABLE orders_ledger (
            id INTEGER PRIMARY KEY,
            order_id INTEGER UNIQUE,
            order_status TEXT DEFAULT 'AWAITING_SHIPMENT',
            gross_amount REAL DEFAULT 200.0,
            platform_fee_amount REAL DEFAULT 10.0,
            spread_capture_amount REAL NOT NULL DEFAULT 0.0,
            buyer_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE order_payouts (
            id INTEGER PRIMARY KEY,
            order_ledger_id INTEGER,
            order_id INTEGER,
            seller_id INTEGER,
            payout_status TEXT DEFAULT 'PAYOUT_NOT_READY',
            seller_gross_amount REAL DEFAULT 110.0,
            fee_amount REAL DEFAULT 10.0,
            seller_net_amount REAL DEFAULT 100.0,
            provider_transfer_id TEXT,
            payout_recovery_status TEXT DEFAULT 'not_needed',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE seller_order_tracking (
            id INTEGER PRIMARY KEY,
            order_id INTEGER,
            seller_id INTEGER,
            tracking_number TEXT,
            carrier TEXT,
            delivered_at TEXT DEFAULT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(order_id, seller_id)
        );
        CREATE TABLE order_events (
            id INTEGER PRIMARY KEY,
            order_id INTEGER,
            event_type TEXT,
            actor_type TEXT DEFAULT 'system',
            actor_id INTEGER,
            payload_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE system_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()

    def insert(
        payout_status='PAYOUT_NOT_READY',
        payment_status='paid',
        refund_status='not_refunded',
        requires_clearance=0,
        requires_recovery=0,
        payout_on_hold=False,
        tracking_number='TRACK123',
        delivered_hours_ago=None,   # None = not delivered; float/int = hours ago
        order_status='AWAITING_SHIPMENT',
        delay_hours=None,           # None = use default (24); or set in system_settings
    ):
        conn.executescript(
            "DELETE FROM users; DELETE FROM orders; DELETE FROM orders_ledger; "
            "DELETE FROM order_payouts; DELETE FROM seller_order_tracking; "
            "DELETE FROM order_events; DELETE FROM system_settings;"
        )
        conn.execute(
            "INSERT INTO users VALUES (1, 'seller1', 'acct_test', 1)"
        )
        conn.execute(
            "INSERT INTO orders VALUES (1, 2, ?, 'card', ?, NULL, ?, ?, 'Pending')",
            (payment_status, requires_clearance, refund_status, requires_recovery),
        )
        conn.execute(
            "INSERT INTO orders_ledger (id, order_id, order_status, gross_amount, platform_fee_amount, buyer_id, created_at) VALUES (1, 1, ?, 200.0, 10.0, 2, datetime('now'))",
            (order_status,),
        )
        effective_payout_status = 'PAYOUT_ON_HOLD' if payout_on_hold else payout_status
        conn.execute(
            "INSERT INTO order_payouts (id, order_ledger_id, order_id, seller_id, payout_status, seller_gross_amount, fee_amount, seller_net_amount, provider_transfer_id, payout_recovery_status, created_at, updated_at) VALUES (1, 1, 1, 1, ?, 110.0, 10.0, 100.0, NULL, 'not_needed', datetime('now'), datetime('now'))",
            (effective_payout_status,),
        )
        if tracking_number:
            delivered_ts = None
            if delivered_hours_ago is not None:
                delivered_ts = (
                    datetime.now() - timedelta(hours=delivered_hours_ago)
                ).strftime('%Y-%m-%d %H:%M:%S')
            conn.execute(
                """INSERT INTO seller_order_tracking
                   (id, order_id, seller_id, tracking_number, carrier, delivered_at,
                    created_at, updated_at)
                   VALUES (1, 1, 1, ?, 'USPS', ?, datetime('now'), datetime('now'))""",
                (tracking_number, delivered_ts),
            )
        if delay_hours is not None:
            # Convert hours → minutes to match the service key
            conn.execute(
                "INSERT INTO system_settings VALUES ('auto_payout_delay_after_delivery_minutes', ?, datetime('now'))",
                (str(int(delay_hours * 60)),),
            )
        conn.commit()
        return 1  # payout_id

    return conn, insert


def _block(conn, payout_id):
    from core.services.ledger.escrow_control import get_payout_block_reason
    return get_payout_block_reason(payout_id, conn=conn)


# ---------------------------------------------------------------------------
# Test 1: Blocked when tracking exists but delivered_at is null
# ---------------------------------------------------------------------------

class TestDeliveryNotConfirmed:
    def test_blocked_when_delivered_at_null(self, delivery_db):
        conn, insert = delivery_db
        pid = insert(tracking_number='TRACK1', delivered_hours_ago=None)
        reason = _block(conn, pid)
        assert reason is not None
        assert 'delivered' in reason.lower(), f"Expected delivery block, got: {reason}"

    def test_blocked_when_no_tracking_at_all(self, delivery_db):
        conn, insert = delivery_db
        pid = insert(tracking_number=None, delivered_hours_ago=None)
        reason = _block(conn, pid)
        assert reason is not None
        assert 'tracking' in reason.lower(), f"Expected tracking block, got: {reason}"


# ---------------------------------------------------------------------------
# Test 2: Blocked when delivered but hold period not yet elapsed
# ---------------------------------------------------------------------------

class TestDeliveryHoldPeriod:
    def test_blocked_just_delivered(self, delivery_db):
        """Delivered 1 minute ago; 24-hour delay should still block."""
        from unittest.mock import patch
        import services.system_settings_service as svc
        conn, insert = delivery_db
        pid = insert(delivered_hours_ago=0.017, delay_hours=24)  # ~1 minute ago
        with patch.object(svc, 'get_setting', return_value='1440'):  # 24h in minutes
            reason = _block(conn, pid)
        assert reason is not None
        assert 'hold' in reason.lower() or 'elapsed' in reason.lower(), \
            f"Expected hold block, got: {reason}"

    def test_blocked_delivered_22h_ago_with_24h_delay(self, delivery_db):
        from unittest.mock import patch
        import services.system_settings_service as svc
        conn, insert = delivery_db
        pid = insert(delivered_hours_ago=22, delay_hours=24)
        with patch.object(svc, 'get_setting', return_value='1440'):  # 24h in minutes
            reason = _block(conn, pid)
        assert reason is not None, "Should still be blocked (24h delay, only 22h elapsed)"

    def test_blocked_custom_delay_not_elapsed(self, delivery_db):
        """Custom 2880-min (48h) delay; delivered 30h ago → still blocked."""
        from unittest.mock import patch
        import services.system_settings_service as svc
        conn, insert = delivery_db
        pid = insert(delivered_hours_ago=30)
        with patch.object(svc, 'get_setting', return_value='2880'):  # 48h in minutes
            reason = _block(conn, pid)
        assert reason is not None
        assert 'hold' in reason.lower() or 'elapsed' in reason.lower(), \
            f"Expected hold block, got: {reason}"


# ---------------------------------------------------------------------------
# Test 3: Payout eligible after delay elapsed
# ---------------------------------------------------------------------------

class TestPayoutEligibleAfterDelay:
    def test_eligible_after_24h_delay(self, delivery_db):
        conn, insert = delivery_db
        pid = insert(delivered_hours_ago=25, delay_hours=24)
        reason = _block(conn, pid)
        assert reason is None, f"Expected ready, got: {reason}"

    def test_eligible_with_custom_short_delay(self, delivery_db):
        """60-min (1h) delay, delivered 2 hours ago → eligible."""
        from unittest.mock import patch
        import services.system_settings_service as svc
        conn, insert = delivery_db
        pid = insert(delivered_hours_ago=2)
        with patch.object(svc, 'get_setting', return_value='60'):  # 1h in minutes
            reason = _block(conn, pid)
        assert reason is None, f"Expected ready, got: {reason}"

    def test_eligible_no_setting_uses_default_24h(self, delivery_db):
        """No system_settings row → default 24h applies. Delivered 25h ago → eligible."""
        conn, insert = delivery_db
        pid = insert(delivered_hours_ago=25, delay_hours=None)
        reason = _block(conn, pid)
        assert reason is None, f"Expected ready (default 24h), got: {reason}"

    def test_not_eligible_with_default_when_only_23h(self, delivery_db):
        """No setting → default 24h. Delivered 23h ago → still blocked."""
        from unittest.mock import patch
        import services.system_settings_service as svc
        conn, insert = delivery_db
        pid = insert(delivered_hours_ago=23, delay_hours=None)
        # Simulate "no setting row" by having get_setting return None
        with patch.object(svc, 'get_setting', return_value=None):
            reason = _block(conn, pid)
        assert reason is not None, "Should be blocked (default 24h not elapsed)"


# ---------------------------------------------------------------------------
# Test 4: ACH clearance still blocks even if delivered
# ---------------------------------------------------------------------------

class TestAchStillBlocks:
    def test_ach_clearance_blocks_even_when_delivered(self, delivery_db):
        conn, insert = delivery_db
        pid = insert(delivered_hours_ago=48, delay_hours=24, requires_clearance=1)
        reason = _block(conn, pid)
        assert reason is not None
        assert 'ach' in reason.lower() or 'clearance' in reason.lower(), \
            f"Expected ACH block, got: {reason}"


# ---------------------------------------------------------------------------
# Test 5: Refunded / on-hold payouts remain blocked
# ---------------------------------------------------------------------------

class TestOtherBlocksStillWork:
    def test_refunded_order_blocked(self, delivery_db):
        conn, insert = delivery_db
        pid = insert(delivered_hours_ago=48, delay_hours=24, refund_status='refunded')
        reason = _block(conn, pid)
        assert reason is not None
        assert 'refund' in reason.lower(), f"Expected refund block, got: {reason}"

    def test_payout_on_hold_blocked(self, delivery_db):
        conn, insert = delivery_db
        pid = insert(delivered_hours_ago=48, delay_hours=24, payout_on_hold=True)
        reason = _block(conn, pid)
        assert reason is not None
        assert 'hold' in reason.lower(), f"Expected hold block, got: {reason}"

    def test_unpaid_order_blocked(self, delivery_db):
        conn, insert = delivery_db
        pid = insert(delivered_hours_ago=48, delay_hours=24, payment_status='unpaid')
        reason = _block(conn, pid)
        assert reason is not None
        assert 'payment' in reason.lower(), f"Expected payment block, got: {reason}"


# ---------------------------------------------------------------------------
# Test 6: Admin mark-delivered action
# ---------------------------------------------------------------------------

class TestMarkDeliveredEndpoint:
    @pytest.fixture
    def app_and_db(self, tmp_path):
        """Minimal Flask app wired to a real SQLite test DB."""
        import sqlite3
        from unittest.mock import patch

        db_path = str(tmp_path / 'test_mark_delivered.db')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, is_admin INTEGER DEFAULT 1);
            CREATE TABLE seller_order_tracking (
                id INTEGER PRIMARY KEY,
                order_id INTEGER,
                seller_id INTEGER,
                tracking_number TEXT,
                carrier TEXT,
                delivered_at TEXT DEFAULT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(order_id, seller_id)
            );
        """)
        conn.execute("INSERT INTO users VALUES (1, 'admin_user', 1)")
        conn.execute(
            "INSERT INTO seller_order_tracking (order_id, seller_id, tracking_number, carrier)"
            " VALUES (10, 5, 'TRACK999', 'USPS')"
        )
        conn.commit()
        conn.close()

        # Import after sys.path is set
        import importlib
        import database as _db_mod

        real_get_conn = _db_mod.get_db_connection

        def patched_get_conn():
            c = sqlite3.connect(db_path)
            c.row_factory = sqlite3.Row
            return c

        return db_path, patched_get_conn

    def test_mark_delivered_sets_delivered_at(self, app_and_db):
        import sqlite3
        from unittest.mock import patch
        from flask import Flask

        db_path, patched_conn = app_and_db

        # Build a minimal Flask test client
        import sys
        from core.blueprints.admin import admin_bp
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret'
        app.config['WTF_CSRF_ENABLED'] = False

        import database as _db_mod
        with patch.object(_db_mod, 'get_db_connection', patched_conn):
            with patch('utils.auth_utils.get_db_connection', patched_conn):
                app.register_blueprint(admin_bp, url_prefix='/admin')
                with app.test_client() as client:
                    with client.session_transaction() as sess:
                        sess['user_id'] = 1
                        sess['is_admin'] = True

                    resp = client.post(
                        '/admin/api/orders/10/mark-delivered',
                        json={'seller_id': 5},
                        content_type='application/json',
                    )
                    assert resp.status_code == 200, resp.data
                    data = resp.get_json()
                    assert data['success'] is True
                    assert data['already_delivered'] is False
                    assert data['delivered_at'] is not None

        # Verify DB was actually updated
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            'SELECT delivered_at FROM seller_order_tracking WHERE order_id=10 AND seller_id=5'
        ).fetchone()
        conn.close()
        assert row is not None
        assert row['delivered_at'] is not None

    def test_mark_delivered_idempotent(self, app_and_db):
        import sqlite3
        from unittest.mock import patch
        from flask import Flask

        db_path, patched_conn = app_and_db

        # Pre-set delivered_at
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE seller_order_tracking SET delivered_at='2025-01-01 10:00:00'"
            " WHERE order_id=10 AND seller_id=5"
        )
        conn.commit()
        conn.close()

        import database as _db_mod
        from core.blueprints.admin import admin_bp
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret'
        app.config['WTF_CSRF_ENABLED'] = False

        with patch.object(_db_mod, 'get_db_connection', patched_conn):
            with patch('utils.auth_utils.get_db_connection', patched_conn):
                app.register_blueprint(admin_bp, url_prefix='/admin')
                with app.test_client() as client:
                    with client.session_transaction() as sess:
                        sess['user_id'] = 1
                        sess['is_admin'] = True

                    resp = client.post(
                        '/admin/api/orders/10/mark-delivered',
                        json={'seller_id': 5},
                        content_type='application/json',
                    )
                    assert resp.status_code == 200
                    data = resp.get_json()
                    assert data['success'] is True
                    assert data['already_delivered'] is True
                    assert data['delivered_at'] == '2025-01-01 10:00:00'

    def test_mark_delivered_missing_tracking(self, app_and_db):
        """Returns 404 when no tracking row exists for the order/seller pair."""
        import sqlite3
        from unittest.mock import patch
        from flask import Flask

        db_path, patched_conn = app_and_db

        import database as _db_mod
        from core.blueprints.admin import admin_bp
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret'
        app.config['WTF_CSRF_ENABLED'] = False

        with patch.object(_db_mod, 'get_db_connection', patched_conn):
            with patch('utils.auth_utils.get_db_connection', patched_conn):
                app.register_blueprint(admin_bp, url_prefix='/admin')
                with app.test_client() as client:
                    with client.session_transaction() as sess:
                        sess['user_id'] = 1
                        sess['is_admin'] = True

                    resp = client.post(
                        '/admin/api/orders/10/mark-delivered',
                        json={'seller_id': 99},  # no tracking for seller 99
                        content_type='application/json',
                    )
                    assert resp.status_code == 404
                    data = resp.get_json()
                    assert data['success'] is False


# ---------------------------------------------------------------------------
# Test 7: System setting is read and applied correctly
# ---------------------------------------------------------------------------

class TestSystemSetting:
    def test_get_auto_payout_delay_minutes_default(self):
        from unittest.mock import patch
        import services.system_settings_service as svc

        with patch.object(svc, 'get_setting', return_value=None):
            assert svc.get_auto_payout_delay_minutes() == 1440  # 24h default

    def test_get_auto_payout_delay_minutes_custom(self):
        from unittest.mock import patch
        import services.system_settings_service as svc

        with patch.object(svc, 'get_setting', return_value='90'):
            assert svc.get_auto_payout_delay_minutes() == 90  # 1h 30m

    def test_get_auto_payout_delay_minutes_clamped_min(self):
        from unittest.mock import patch
        import services.system_settings_service as svc

        with patch.object(svc, 'get_setting', return_value='0'):
            assert svc.get_auto_payout_delay_minutes() == 1  # MIN = 1 minute

    def test_get_auto_payout_delay_minutes_clamped_max(self):
        from unittest.mock import patch
        import services.system_settings_service as svc

        with patch.object(svc, 'get_setting', return_value='999999'):
            assert svc.get_auto_payout_delay_minutes() == 43200  # MAX = 30 days

    def test_set_auto_payout_delay_minutes_saves(self):
        from unittest.mock import patch
        import services.system_settings_service as svc

        with patch.object(svc, 'set_setting') as mock_set:
            result = svc.set_auto_payout_delay_minutes(90)
            assert result == 90
            mock_set.assert_called_once_with('auto_payout_delay_after_delivery_minutes', '90')

    def test_payout_block_uses_system_setting(self, delivery_db):
        """Verify get_payout_block_reason reads delay (minutes) from system_settings."""
        conn, insert = delivery_db
        # 5-minute delay; delivered 2 minutes ago → still blocked
        pid = insert(delivered_hours_ago=2/60)  # ~2 minutes ago
        from core.services.ledger.escrow_control import get_payout_block_reason

        from unittest.mock import patch
        import services.system_settings_service as svc
        with patch.object(svc, 'get_setting', return_value='5'):  # 5-minute delay
            reason = get_payout_block_reason(pid, conn=conn)
        assert reason is not None
        assert 'hold' in reason.lower() or 'elapsed' in reason.lower()
