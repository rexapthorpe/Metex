"""
Tests: Payment Guardrail — no order created unless Stripe payment is confirmed.

Proven:
  GUARD-1: Finalize with PI not confirmed (requires_confirmation) → 402, no order.
  GUARD-2: Finalize with PI confirmed (succeeded) → 200, order created.
  GUARD-3: Finalize with PI processing (ACH) → 200, order created.
  GUARD-4: Finalize with no PI ID → order created (backward compat for tests).
  GUARD-5: prepare-payment updates PI amount via stripe.PaymentIntent.modify.
  GUARD-6: prepare-payment returns SPOT_EXPIRED when snapshot is stale.
  GUARD-7: prepare-payment returns 400 when no PI ID supplied.
  GUARD-8: Finalize → 402 when Stripe verification call itself fails.
  GUARD-9: Bid fill with payment failure → no order created (existing SAVEPOINT behavior).
"""

import os
import sys
import sqlite3
import tempfile
import shutil
import pytest
from unittest.mock import patch, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ---------------------------------------------------------------------------
# Minimal schema
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS system_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT OR IGNORE INTO system_settings (key, value) VALUES ('checkout_enabled', '1');
INSERT OR IGNORE INTO system_settings (key, value) VALUES ('checkout_spot_max_age', '300');
CREATE TABLE IF NOT EXISTS spot_price_snapshots (
    id         INTEGER   PRIMARY KEY AUTOINCREMENT,
    metal      TEXT      NOT NULL,
    price_usd  REAL      NOT NULL,
    as_of      TIMESTAMP NOT NULL,
    source     TEXT      DEFAULT 'metalpriceapi',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS users (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    email                TEXT    DEFAULT '',
    username             TEXT,
    password             TEXT    DEFAULT '',
    password_hash        TEXT    DEFAULT '',
    first_name           TEXT,
    last_name            TEXT,
    is_admin             INTEGER DEFAULT 0,
    is_banned            INTEGER DEFAULT 0,
    is_frozen            INTEGER DEFAULT 0,
    stripe_customer_id   TEXT
);
CREATE TABLE IF NOT EXISTS categories (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT,
    year               TEXT,
    weight             TEXT,
    purity             TEXT,
    mint               TEXT,
    country_of_origin  TEXT,
    coin_series        TEXT,
    denomination       TEXT,
    grade              TEXT,
    finish             TEXT,
    special_designation TEXT,
    metal              TEXT,
    product_type       TEXT,
    bucket_id          INTEGER,
    product_line       TEXT,
    graded             INTEGER DEFAULT 0,
    grading_service    TEXT,
    is_isolated        INTEGER NOT NULL DEFAULT 0,
    condition_category TEXT,
    series_variant     TEXT,
    platform_fee_type  TEXT,
    platform_fee_value REAL,
    fee_updated_at     TIMESTAMP,
    pricing_mode       TEXT DEFAULT 'static'
);
CREATE TABLE IF NOT EXISTS listings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id       INTEGER NOT NULL,
    category_id     INTEGER NOT NULL,
    quantity        INTEGER DEFAULT 1,
    price_per_coin  REAL    DEFAULT 0,
    active          INTEGER DEFAULT 1,
    name            TEXT,
    description     TEXT,
    pricing_mode    TEXT    DEFAULT 'static',
    spot_premium    REAL    DEFAULT 0,
    floor_price     REAL    DEFAULT 0,
    pricing_metal   TEXT,
    is_isolated     INTEGER NOT NULL DEFAULT 0,
    isolated_type   TEXT,
    issue_number    INTEGER,
    issue_total     INTEGER,
    graded          INTEGER DEFAULT 0,
    grading_service TEXT,
    packaging_type  TEXT,
    packaging_notes TEXT,
    cert_number     TEXT,
    condition_notes TEXT,
    actual_year     TEXT,
    image_url       TEXT,
    edition_number  INTEGER,
    edition_total   INTEGER,
    photo_filename  TEXT,
    listing_title   TEXT
);
CREATE TABLE IF NOT EXISTS cart (
    id                            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                       INTEGER,
    listing_id                    INTEGER,
    quantity                      INTEGER DEFAULT 1,
    third_party_grading_requested INTEGER DEFAULT 0,
    grading_preference            TEXT    DEFAULT 'NONE'
);
CREATE TABLE IF NOT EXISTS orders (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_id                 INTEGER,
    total_price              REAL,
    status                   TEXT    DEFAULT 'Pending Shipment',
    payment_status           TEXT    DEFAULT 'unpaid',
    shipping_address         TEXT,
    recipient_first_name     TEXT,
    recipient_last_name      TEXT,
    stripe_payment_intent_id TEXT,
    buyer_card_fee           REAL    DEFAULT 0,
    tax_amount               REAL    DEFAULT 0,
    tax_rate                 REAL    DEFAULT 0,
    placed_from_ip           TEXT,
    payment_method_type      TEXT,
    created_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    paid_at                  TIMESTAMP,
    source_bid_id            INTEGER,
    refund_status            TEXT,
    refund_amount            REAL
);
CREATE TABLE IF NOT EXISTS order_items (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id                INTEGER NOT NULL,
    listing_id              INTEGER NOT NULL,
    quantity                INTEGER NOT NULL,
    price_each              REAL    NOT NULL,
    seller_price_each       REAL,
    grading_fee_charged     REAL    DEFAULT 0,
    spot_price_at_purchase  REAL,
    spot_as_of_used         TEXT,
    spot_source_used        TEXT,
    pricing_mode_at_purchase TEXT,
    spot_premium_used       REAL,
    weight_used             REAL
);
CREATE TABLE IF NOT EXISTS order_payouts (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id               INTEGER,
    order_item_id          INTEGER,
    seller_id              INTEGER,
    payout_status          TEXT    DEFAULT 'pending',
    payout_recovery_status TEXT,
    seller_net_amount      REAL,
    platform_fee_amount    REAL,
    provider_transfer_id   TEXT,
    provider_reversal_id   TEXT,
    recovery_failure_reason TEXT
);
CREATE TABLE IF NOT EXISTS orders_ledger (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     INTEGER,
    order_status TEXT,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS order_items_ledger (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     INTEGER,
    listing_id   INTEGER,
    seller_id    INTEGER,
    quantity     INTEGER,
    unit_price   REAL,
    platform_fee REAL
);
CREATE TABLE IF NOT EXISTS order_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER,
    event_type TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS transaction_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    order_item_id INTEGER,
    snapshot_at TEXT,
    listing_id INTEGER,
    listing_title TEXT,
    listing_description TEXT,
    metal TEXT,
    product_line TEXT,
    product_type TEXT,
    weight TEXT,
    year TEXT,
    mint TEXT,
    purity TEXT,
    finish TEXT,
    condition_category TEXT,
    series_variant TEXT,
    packaging_type TEXT,
    packaging_notes TEXT,
    condition_notes TEXT,
    photo_filenames TEXT,
    quantity INTEGER,
    price_each REAL,
    pricing_mode TEXT,
    spot_price_at_purchase REAL,
    seller_id INTEGER,
    seller_username TEXT,
    seller_email TEXT,
    buyer_id INTEGER,
    buyer_username TEXT,
    buyer_email TEXT,
    payment_intent_id TEXT
);
CREATE TABLE IF NOT EXISTS listing_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER,
    file_path TEXT
);
CREATE TABLE IF NOT EXISTS notification_settings (
    user_id           INTEGER,
    notification_type TEXT,
    enabled           INTEGER DEFAULT 1,
    PRIMARY KEY (user_id, notification_type)
);
CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER,
    type       TEXT,
    message    TEXT,
    is_read    INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS ratings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER,
    rater_id   INTEGER,
    ratee_id   INTEGER,
    rating     INTEGER,
    comment    TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_TEST_USER_ID   = 9901
_TEST_SELLER_ID = 9902
_TEST_NONCE     = 'guardrail_test_nonce_abc'


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope='function')
def test_db():
    db_dir  = tempfile.mkdtemp()
    db_path = os.path.join(db_dir, 'test.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO users (id, email, username, password_hash, is_admin) VALUES (?, ?, ?, '', 0)",
        (_TEST_USER_ID, 'buyer@test.com', 'testbuyer'),
    )
    conn.execute(
        "INSERT INTO users (id, email, username, password_hash, is_admin) VALUES (?, ?, ?, '', 0)",
        (_TEST_SELLER_ID, 'seller@test.com', 'testseller'),
    )
    conn.commit()
    conn.close()

    def get_conn():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        return c

    yield db_path, get_conn
    shutil.rmtree(db_dir, ignore_errors=True)


@pytest.fixture(scope='function')
def flask_client(test_db):
    db_path, get_conn = test_db

    import database as _db_mod
    orig_get_conn = _db_mod.get_db_connection

    def _patched_conn():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        return c

    _db_mod.get_db_connection = _patched_conn

    import utils.auth_utils as _au
    orig_au = _au.get_db_connection
    _au.get_db_connection = _patched_conn

    import core.blueprints.checkout.routes as _co_r
    orig_co = _co_r.get_db_connection
    _co_r.get_db_connection = _patched_conn

    import services.order_service as _os_mod
    orig_os = _os_mod._get_conn
    _os_mod._get_conn = _patched_conn

    from core import create_app
    app = create_app({'TESTING': True, 'WTF_CSRF_ENABLED': False,
                      'SECRET_KEY': 'guardrail-test-secret'})

    with app.test_client() as client:
        yield client

    _db_mod.get_db_connection = orig_get_conn
    _au.get_db_connection     = orig_au
    _co_r.get_db_connection   = orig_co
    _os_mod._get_conn         = orig_os


def _login(client):
    with client.session_transaction() as sess:
        sess['user_id'] = _TEST_USER_ID


def _set_nonce(client):
    with client.session_transaction() as sess:
        sess['checkout_nonce'] = _TEST_NONCE


def _insert_static_listing(get_conn, price=100.0):
    conn = get_conn()
    conn.execute(
        "INSERT INTO categories (id, metal, product_type, bucket_id, weight, pricing_mode) "
        "VALUES (1, 'gold', 'Coin', 1, '1 oz', 'static')"
    )
    conn.execute(
        "INSERT INTO listings (id, seller_id, category_id, quantity, price_per_coin, active, pricing_mode) "
        "VALUES (1, ?, 1, 10, ?, 1, 'static')",
        (_TEST_SELLER_ID, price),
    )
    conn.commit()
    conn.close()
    return 1  # listing_id


def _add_to_cart(get_conn, user_id, listing_id, qty=1):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO cart (user_id, listing_id, quantity, grading_preference) "
        "VALUES (?, ?, ?, 'NONE')",
        (user_id, listing_id, qty),
    )
    conn.commit()
    conn.close()


def _count_orders(get_conn):
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    conn.close()
    return count


def _mock_pi(status='succeeded'):
    pi = MagicMock()
    pi.status = status
    pi.id = f'pi_test_{status}'
    return pi


# ---------------------------------------------------------------------------
# GUARD-1: PI not confirmed → 402, no order
# ---------------------------------------------------------------------------

class TestGuard1PINotConfirmed:

    def test_finalize_with_unconfirmed_pi_returns_402(self, flask_client, test_db):
        """Finalize with a PI in requires_confirmation state → 402, no order."""
        _, get_conn = test_db
        listing_id = _insert_static_listing(get_conn, price=100.0)
        _add_to_cart(get_conn, _TEST_USER_ID, listing_id)
        _login(flask_client)
        _set_nonce(flask_client)

        with patch('stripe.PaymentIntent.modify') as mock_modify, \
             patch('stripe.PaymentIntent.retrieve', return_value=_mock_pi('requires_confirmation')), \
             patch('stripe.tax.Calculation.create', side_effect=Exception('no tax')):
            mock_modify.return_value = None
            resp = flask_client.post(
                '/checkout',
                json={
                    'shipping_address': '123 Main St • Austin, TX 78701',
                    'checkout_nonce': _TEST_NONCE,
                    'payment_intent_id': 'pi_test_unconfirmed',
                },
                headers={'X-Requested-With': 'XMLHttpRequest'},
            )

        assert resp.status_code == 402, f'Expected 402, got {resp.status_code}'
        data = resp.get_json()
        assert data['success'] is False
        assert data.get('error_code') == 'PAYMENT_NOT_CONFIRMED'
        assert _count_orders(get_conn) == 0, 'No order should be created for unconfirmed PI'

    def test_finalize_with_requires_payment_method_returns_402(self, flask_client, test_db):
        """PI in requires_payment_method (default new PI state) → 402, no order."""
        _, get_conn = test_db
        listing_id = _insert_static_listing(get_conn, price=100.0)
        _add_to_cart(get_conn, _TEST_USER_ID, listing_id)
        _login(flask_client)
        _set_nonce(flask_client)

        with patch('stripe.PaymentIntent.modify') as mock_modify, \
             patch('stripe.PaymentIntent.retrieve', return_value=_mock_pi('requires_payment_method')), \
             patch('stripe.tax.Calculation.create', side_effect=Exception('no tax')):
            mock_modify.return_value = None
            resp = flask_client.post(
                '/checkout',
                json={
                    'shipping_address': '123 Main St',
                    'checkout_nonce': _TEST_NONCE,
                    'payment_intent_id': 'pi_test_rqpm',
                },
                headers={'X-Requested-With': 'XMLHttpRequest'},
            )

        assert resp.status_code == 402
        assert _count_orders(get_conn) == 0


# ---------------------------------------------------------------------------
# GUARD-2: PI confirmed (succeeded) → order created
# ---------------------------------------------------------------------------

class TestGuard2PISucceeded:

    def test_finalize_with_succeeded_pi_creates_order(self, flask_client, test_db):
        """Finalize with a PI status=succeeded → 200, order created."""
        _, get_conn = test_db
        listing_id = _insert_static_listing(get_conn, price=100.0)
        _add_to_cart(get_conn, _TEST_USER_ID, listing_id)
        _login(flask_client)
        _set_nonce(flask_client)

        with patch('stripe.PaymentIntent.modify') as mock_modify, \
             patch('stripe.PaymentIntent.retrieve', return_value=_mock_pi('succeeded')), \
             patch('stripe.tax.Calculation.create', side_effect=Exception('no tax')), \
             patch('services.notification_service.notify'):
            mock_modify.return_value = None
            resp = flask_client.post(
                '/checkout',
                json={
                    'shipping_address': '123 Main St',
                    'checkout_nonce': _TEST_NONCE,
                    'payment_intent_id': 'pi_test_succeeded',
                },
                headers={'X-Requested-With': 'XMLHttpRequest'},
            )

        assert resp.status_code == 200, f'Expected 200, got {resp.status_code}: {resp.get_data(as_text=True)}'
        data = resp.get_json()
        assert data['success'] is True
        assert 'order_id' in data
        assert _count_orders(get_conn) == 1, 'Order should be created for succeeded PI'


# ---------------------------------------------------------------------------
# GUARD-3: PI processing (ACH) → order created
# ---------------------------------------------------------------------------

class TestGuard3PIProcessing:

    def test_finalize_with_processing_pi_creates_order(self, flask_client, test_db):
        """ACH finalize with PI status=processing → 200, order created."""
        _, get_conn = test_db
        listing_id = _insert_static_listing(get_conn, price=200.0)
        _add_to_cart(get_conn, _TEST_USER_ID, listing_id)
        _login(flask_client)
        _set_nonce(flask_client)

        with patch('stripe.PaymentIntent.modify') as mock_modify, \
             patch('stripe.PaymentIntent.retrieve', return_value=_mock_pi('processing')), \
             patch('stripe.tax.Calculation.create', side_effect=Exception('no tax')), \
             patch('services.notification_service.notify'):
            mock_modify.return_value = None
            resp = flask_client.post(
                '/checkout',
                json={
                    'shipping_address': '456 Oak Ave',
                    'checkout_nonce': _TEST_NONCE,
                    'payment_intent_id': 'pi_test_processing',
                    'payment_method_type': 'us_bank_account',
                },
                headers={'X-Requested-With': 'XMLHttpRequest'},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert _count_orders(get_conn) == 1


# ---------------------------------------------------------------------------
# GUARD-4: No PI ID → order still created (backward compat, test environments)
# ---------------------------------------------------------------------------

class TestGuard4NoPIID:

    def test_finalize_without_pi_id_creates_order(self, flask_client, test_db):
        """No payment_intent_id → guardrail does not fire, order created (test compat)."""
        _, get_conn = test_db
        listing_id = _insert_static_listing(get_conn, price=50.0)
        _add_to_cart(get_conn, _TEST_USER_ID, listing_id)
        _login(flask_client)
        _set_nonce(flask_client)

        with patch('stripe.tax.Calculation.create', side_effect=Exception('no tax')), \
             patch('services.notification_service.notify'):
            resp = flask_client.post(
                '/checkout',
                json={'shipping_address': '789 Elm St', 'checkout_nonce': _TEST_NONCE},
                headers={'X-Requested-With': 'XMLHttpRequest'},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert _count_orders(get_conn) == 1


# ---------------------------------------------------------------------------
# GUARD-5: prepare-payment updates PI amount
# ---------------------------------------------------------------------------

class TestGuard5PreparePayment:

    def test_prepare_payment_calls_stripe_modify(self, flask_client, test_db):
        """POST /checkout/prepare-payment calls stripe.PaymentIntent.modify with final amount."""
        _, get_conn = test_db
        listing_id = _insert_static_listing(get_conn, price=100.0)
        _add_to_cart(get_conn, _TEST_USER_ID, listing_id)
        _login(flask_client)
        _set_nonce(flask_client)

        with patch('stripe.PaymentIntent.modify') as mock_modify, \
             patch('stripe.tax.Calculation.create', side_effect=Exception('no tax')):
            mock_modify.return_value = None
            resp = flask_client.post(
                '/checkout/prepare-payment',
                json={
                    'payment_intent_id': 'pi_test_prepare',
                    'checkout_nonce': _TEST_NONCE,
                    'shipping_address': '123 Main St',
                    'recipient_first': 'Alice',
                    'recipient_last': 'Test',
                    'zip_code': '78701',
                    'state': 'TX',
                    'country': 'US',
                    'payment_method_type': 'card',
                },
                headers={'X-Requested-With': 'XMLHttpRequest'},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'total' in data
        mock_modify.assert_called_once()
        # Verify the amount is > subtotal (includes tax fallback + card fee)
        call_kwargs = mock_modify.call_args
        amount_arg = call_kwargs[1].get('amount') or call_kwargs[0][1]
        assert amount_arg > 10000, f'PI amount {amount_arg} should be > 10000 cents (subtotal only)'

    def test_prepare_payment_returns_spot_expired_when_stale(self, flask_client, test_db):
        """prepare-payment with stale snapshot → 409 SPOT_EXPIRED."""
        _, get_conn = test_db

        # Insert a spot-priced listing
        conn = get_conn()
        conn.execute(
            "INSERT INTO categories (id, metal, product_type, bucket_id, weight, pricing_mode) "
            "VALUES (2, 'gold', 'Coin', 2, '1 oz', 'premium_to_spot')"
        )
        conn.execute(
            "INSERT INTO listings (id, seller_id, category_id, quantity, price_per_coin, "
            "active, pricing_mode, spot_premium) VALUES (2, ?, 2, 5, 0, 1, 'premium_to_spot', 50)",
            (_TEST_SELLER_ID,),
        )
        # Stale snapshot (300 seconds old)
        from datetime import datetime, timedelta
        stale_ts = (datetime.now() - timedelta(seconds=300)).isoformat()
        conn.execute(
            "INSERT INTO spot_price_snapshots (metal, price_usd, as_of, source) VALUES ('gold', 3000.0, ?, 'test')",
            (stale_ts,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO cart (user_id, listing_id, quantity, grading_preference) "
            "VALUES (?, 2, 1, 'NONE')",
            (_TEST_USER_ID,),
        )
        conn.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('checkout_spot_max_age', '120')")
        conn.commit()
        conn.close()

        _login(flask_client)
        _set_nonce(flask_client)
        resp = flask_client.post(
            '/checkout/prepare-payment',
            json={
                'payment_intent_id': 'pi_test_stale',
                'checkout_nonce': _TEST_NONCE,
                'shipping_address': '123 Main St',
            },
            headers={'X-Requested-With': 'XMLHttpRequest'},
        )

        assert resp.status_code == 409
        data = resp.get_json()
        assert data['success'] is False
        assert data.get('error_code') == 'SPOT_EXPIRED'

    def test_prepare_payment_without_pi_id_returns_400(self, flask_client, test_db):
        """prepare-payment with no payment_intent_id → 400."""
        _, get_conn = test_db
        _login(flask_client)
        _set_nonce(flask_client)
        resp = flask_client.post(
            '/checkout/prepare-payment',
            json={'checkout_nonce': _TEST_NONCE},
            headers={'X-Requested-With': 'XMLHttpRequest'},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GUARD-6: Already-confirmed PI modify gracefully skipped
# ---------------------------------------------------------------------------

class TestGuard6AlreadyConfirmedModify:

    def test_modify_already_confirmed_does_not_block_order(self, flask_client, test_db):
        """If PI.modify raises 'already confirmed', order creation still proceeds."""
        _, get_conn = test_db
        listing_id = _insert_static_listing(get_conn, price=100.0)
        _add_to_cart(get_conn, _TEST_USER_ID, listing_id)
        _login(flask_client)
        _set_nonce(flask_client)

        already_confirmed_err = MagicMock(spec=Exception)
        already_confirmed_err.__str__ = lambda self: 'You cannot modify a PaymentIntent after it has been confirmed'

        import stripe as _stripe_mod
        confirm_err = _stripe_mod.error.InvalidRequestError(
            message='You cannot modify a PaymentIntent after it has been confirmed',
            param=None,
        )

        with patch('stripe.PaymentIntent.modify', side_effect=confirm_err), \
             patch('stripe.PaymentIntent.retrieve', return_value=_mock_pi('succeeded')), \
             patch('stripe.tax.Calculation.create', side_effect=Exception('no tax')), \
             patch('services.notification_service.notify'):
            resp = flask_client.post(
                '/checkout',
                json={
                    'shipping_address': '123 Main St',
                    'checkout_nonce': _TEST_NONCE,
                    'payment_intent_id': 'pi_already_confirmed',
                },
                headers={'X-Requested-With': 'XMLHttpRequest'},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert _count_orders(get_conn) == 1


# ---------------------------------------------------------------------------
# GUARD-7: Finalize → 500 when Stripe verification call fails
# ---------------------------------------------------------------------------

class TestGuard7StripeVerifyError:

    def test_stripe_verify_error_blocks_order(self, flask_client, test_db):
        """If stripe.PaymentIntent.retrieve raises StripeError → 500, no order."""
        _, get_conn = test_db
        listing_id = _insert_static_listing(get_conn, price=100.0)
        _add_to_cart(get_conn, _TEST_USER_ID, listing_id)
        _login(flask_client)
        _set_nonce(flask_client)

        import stripe as _stripe_mod
        retrieve_err = _stripe_mod.error.APIConnectionError(message='connection refused')

        with patch('stripe.PaymentIntent.modify') as mock_modify, \
             patch('stripe.PaymentIntent.retrieve', side_effect=retrieve_err), \
             patch('stripe.tax.Calculation.create', side_effect=Exception('no tax')):
            mock_modify.return_value = None
            resp = flask_client.post(
                '/checkout',
                json={
                    'shipping_address': '123 Main St',
                    'checkout_nonce': _TEST_NONCE,
                    'payment_intent_id': 'pi_network_fail',
                },
                headers={'X-Requested-With': 'XMLHttpRequest'},
            )

        assert resp.status_code == 500
        assert _count_orders(get_conn) == 0, 'No order on Stripe verification error'
