"""
Tests: Saved Card Checkout — PaymentIntent customer attachment + saved card listing

Proven:
  CPI-1: create_payment_intent attaches customer=customer_id when user has stripe_customer_id.
  CPI-2: create_payment_intent works without customer when user has no stripe_customer_id.
  CPI-3: create_payment_intent returns clientSecret and paymentIntentId on success.
  CPI-4: create_payment_intent returns 400 when cart total is zero (session_items empty).
  PM-1:  GET /account/api/payment-methods returns saved cards when customer exists.
  PM-2:  GET /account/api/payment-methods returns empty list when no stripe_customer_id.
  PM-3:  GET /account/api/payment-methods requires authentication (401 when not logged in).
  PM-4:  Stripe Customer is created and stored when none exists (via create_payment_intent).
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
# Minimal schema — only tables touched by these routes
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS system_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
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
CREATE TABLE IF NOT EXISTS cart (
    id                            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                       INTEGER,
    listing_id                    INTEGER,
    quantity                      INTEGER DEFAULT 1,
    third_party_grading_requested INTEGER DEFAULT 0,
    grading_preference            TEXT    DEFAULT 'NONE'
);
CREATE TABLE IF NOT EXISTS categories (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    metal        TEXT,
    product_type TEXT,
    bucket_id    INTEGER,
    weight       TEXT,
    is_isolated  INTEGER DEFAULT 0,
    pricing_mode TEXT    DEFAULT 'static'
);
CREATE TABLE IF NOT EXISTS listings (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id      INTEGER NOT NULL,
    category_id    INTEGER NOT NULL,
    quantity       INTEGER DEFAULT 1,
    price_per_coin REAL    DEFAULT 0,
    active         INTEGER DEFAULT 1,
    pricing_mode   TEXT    DEFAULT 'static',
    spot_premium   REAL,
    floor_price    REAL,
    pricing_metal  TEXT,
    is_isolated    INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER,
    type       TEXT,
    message    TEXT,
    is_read    INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS notification_settings (
    user_id           INTEGER,
    notification_type TEXT,
    enabled           INTEGER DEFAULT 1,
    PRIMARY KEY (user_id, notification_type)
);
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def test_db():
    """Module-scoped temp DB wired into checkout and account routes."""
    from app import app as _flask_app  # noqa: F401 — side-effect import to bind blueprints

    import database
    import utils.auth_utils as auth_utils_mod
    import core.blueprints.checkout.routes as checkout_routes_mod
    import core.blueprints.account.payment_methods as payment_methods_mod
    import routes.account_routes as account_routes_mod  # active monolith for /account/api/*

    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "saved_cards_test.db")

    raw = sqlite3.connect(db_path)
    raw.executescript(SCHEMA)
    raw.commit()
    raw.close()

    orig_db             = database.get_db_connection
    orig_auth           = auth_utils_mod.get_db_connection
    orig_checkout       = checkout_routes_mod.get_db_connection
    orig_pm             = payment_methods_mod.get_db_connection
    orig_account_routes = account_routes_mod.get_db_connection

    def get_test_conn():
        c = sqlite3.connect(db_path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    database.get_db_connection              = get_test_conn
    auth_utils_mod.get_db_connection        = get_test_conn
    checkout_routes_mod.get_db_connection   = get_test_conn
    payment_methods_mod.get_db_connection   = get_test_conn
    account_routes_mod.get_db_connection    = get_test_conn

    yield db_path, get_test_conn

    database.get_db_connection              = orig_db
    auth_utils_mod.get_db_connection        = orig_auth
    checkout_routes_mod.get_db_connection   = orig_checkout
    payment_methods_mod.get_db_connection   = orig_pm
    account_routes_mod.get_db_connection    = orig_account_routes
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="module")
def client(test_db):
    """Flask test client with a user pre-inserted."""
    from app import app as flask_app

    _, get_test_conn = test_db

    conn = get_test_conn()
    conn.execute(
        "INSERT INTO users (id, email, username, password_hash, stripe_customer_id) "
        "VALUES (1, 'buyer@test.com', 'buyer', 'hash', NULL)"
    )
    conn.execute(
        "INSERT INTO users (id, email, username, password_hash, stripe_customer_id) "
        "VALUES (2, 'buyer2@test.com', 'buyer2', 'hash', 'cus_existing123')"
    )
    conn.commit()
    conn.close()

    flask_app.config['TESTING'] = True
    flask_app.config['WTF_CSRF_ENABLED'] = False
    flask_app.config['SECRET_KEY'] = 'test-secret'

    with flask_app.test_client() as c:
        yield c


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess['user_id'] = user_id


def _mock_pi(client_secret='cs_test', pi_id='pi_test123'):
    m = MagicMock()
    m.client_secret = client_secret
    m.id = pi_id
    return m


# ---------------------------------------------------------------------------
# CPI-1: create_payment_intent attaches customer when user has stripe_customer_id
# ---------------------------------------------------------------------------

class TestCreatePaymentIntentCustomerAttachment:
    """CPI-1 through CPI-4: /create-payment-intent endpoint."""

    def test_CPI1_attaches_customer_when_customer_id_exists(self, client):
        """customer= is passed to stripe.PaymentIntent.create when user has stripe_customer_id."""
        _login(client, 2)  # user 2 has stripe_customer_id='cus_existing123'
        with client.session_transaction() as sess:
            sess['checkout_items'] = [{'listing_id': 1, 'quantity': 1, 'price_each': 100.0}]

        pi_mock = _mock_pi('cs_for_user2', 'pi_user2')
        with patch('stripe.PaymentIntent.create', return_value=pi_mock) as mock_create:
            with patch(
                'core.blueprints.account.payment_methods._ensure_stripe_customer',
                return_value='cus_existing123',
            ):
                resp = client.post('/create-payment-intent')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['clientSecret'] == 'cs_for_user2'
        assert data['paymentIntentId'] == 'pi_user2'

        # Verify customer= was in the call kwargs
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs.get('customer') == 'cus_existing123'
        assert call_kwargs.get('setup_future_usage') == 'off_session'

    def test_CPI2_no_customer_param_when_ensure_raises(self, client):
        """customer= is omitted when _ensure_stripe_customer raises — still creates PI."""
        _login(client, 1)  # user 1 has no stripe_customer_id
        with client.session_transaction() as sess:
            sess['checkout_items'] = [{'listing_id': 1, 'quantity': 1, 'price_each': 50.0}]

        pi_mock = _mock_pi('cs_no_customer', 'pi_no_cust')
        with patch('stripe.PaymentIntent.create', return_value=pi_mock) as mock_create:
            with patch(
                'core.blueprints.account.payment_methods._ensure_stripe_customer',
                side_effect=Exception('stripe unavailable'),
            ):
                resp = client.post('/create-payment-intent')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['clientSecret'] == 'cs_no_customer'

        call_kwargs = mock_create.call_args[1]
        assert 'customer' not in call_kwargs  # no customer attached

    def test_CPI3_returns_client_secret_and_intent_id(self, client):
        """Response always contains clientSecret and paymentIntentId."""
        _login(client, 2)
        with client.session_transaction() as sess:
            sess['checkout_items'] = [{'listing_id': 1, 'quantity': 2, 'price_each': 200.0}]

        pi_mock = _mock_pi('cs_keys_test', 'pi_keys_test')
        with patch('stripe.PaymentIntent.create', return_value=pi_mock):
            with patch(
                'core.blueprints.account.payment_methods._ensure_stripe_customer',
                return_value='cus_existing123',
            ):
                resp = client.post('/create-payment-intent')

        assert resp.status_code == 200
        data = resp.get_json()
        assert 'clientSecret' in data
        assert 'paymentIntentId' in data

    def test_CPI4_returns_400_when_cart_total_zero(self, client):
        """400 is returned when session_items sums to zero (empty purchase)."""
        _login(client, 2)
        with client.session_transaction() as sess:
            sess['checkout_items'] = [{'listing_id': 1, 'quantity': 1, 'price_each': 0.0}]

        with patch('stripe.PaymentIntent.create') as mock_create:
            with patch(
                'core.blueprints.account.payment_methods._ensure_stripe_customer',
                return_value='cus_existing123',
            ):
                resp = client.post('/create-payment-intent')

        mock_create.assert_not_called()
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'error' in data

    def test_CPI_requires_authentication(self, client):
        """401 is returned when not logged in."""
        with client.session_transaction() as sess:
            sess.pop('user_id', None)

        resp = client.post('/create-payment-intent')
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PM-1 through PM-4: GET /account/api/payment-methods
# ---------------------------------------------------------------------------

class TestGetPaymentMethods:
    """PM tests: saved card listing endpoint."""

    def test_PM1_returns_saved_cards_when_customer_exists(self, client):
        """Returns card list when user has a stripe_customer_id."""
        _login(client, 2)  # has cus_existing123

        mock_customer = MagicMock()
        mock_customer.get.side_effect = lambda key, *args: (
            {'default_payment_method': 'pm_default'} if key == 'invoice_settings'
            else (args[0] if args else None)
        )

        mock_pm = MagicMock()
        mock_pm.id = 'pm_default'
        mock_pm.get.side_effect = lambda key, *args: (
            {'brand': 'visa', 'last4': '4242', 'exp_month': 12, 'exp_year': 2027, 'funding': 'credit'}
            if key == 'card'
            else (args[0] if args else None)
        )

        def _mock_list(**kwargs):
            t = kwargs.get('type')
            m = MagicMock()
            m.auto_paging_iter.return_value = [mock_pm] if t == 'card' else []
            return m

        with patch('stripe.Customer.retrieve', return_value=mock_customer):
            with patch('stripe.PaymentMethod.list', side_effect=_mock_list):
                resp = client.get('/account/api/payment-methods')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert len(data['payment_methods']) == 1
        pm = data['payment_methods'][0]
        assert pm['id'] == 'pm_default'
        assert pm['brand'] == 'visa'
        assert pm['last4'] == '4242'
        assert pm['is_default'] is True

    def test_PM2_returns_empty_list_when_no_customer(self, client):
        """Returns empty payment_methods list when user has no stripe_customer_id."""
        _login(client, 1)  # user 1 has no stripe_customer_id

        resp = client.get('/account/api/payment-methods')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['payment_methods'] == []

    def test_PM3_requires_authentication(self, client):
        """401 when not logged in."""
        with client.session_transaction() as sess:
            sess.pop('user_id', None)

        resp = client.get('/account/api/payment-methods')
        assert resp.status_code == 401

    def test_PM4_customer_created_and_stored_on_first_payment_intent(self, client, test_db):
        """When user has no stripe_customer_id, create_payment_intent creates one and stores it."""
        _, get_test_conn = test_db
        _login(client, 1)  # user 1 has no stripe_customer_id initially

        with client.session_transaction() as sess:
            sess['checkout_items'] = [{'listing_id': 1, 'quantity': 1, 'price_each': 75.0}]

        new_customer = MagicMock()
        new_customer.id = 'cus_newly_created'

        pi_mock = _mock_pi('cs_new_cust', 'pi_new_cust')

        with patch('stripe.Customer.create', return_value=new_customer) as mock_create_cust:
            with patch('stripe.PaymentIntent.create', return_value=pi_mock) as mock_create_pi:
                resp = client.post('/create-payment-intent')

        # PI was created
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['paymentIntentId'] == 'pi_new_cust'

        # customer= was attached to the PI
        pi_kwargs = mock_create_pi.call_args[1]
        assert pi_kwargs.get('customer') == 'cus_newly_created'

        # stripe_customer_id was persisted on the user
        conn = get_test_conn()
        row = conn.execute(
            'SELECT stripe_customer_id FROM users WHERE id = 1'
        ).fetchone()
        conn.close()
        assert row['stripe_customer_id'] == 'cus_newly_created'
