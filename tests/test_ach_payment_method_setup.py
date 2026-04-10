"""
Tests: ACH / Bank Account Payment Method Setup
================================================
Verifies that the payment method setup flow supports us_bank_account type,
not just cards.  Covers both the core blueprint and the active monolith.

Proven:
  ACH-1: SetupIntent created by core payment_methods blueprint includes
         us_bank_account in payment_method_types.
  ACH-2: SetupIntent created by routes/account_routes (active monolith) includes
         us_bank_account in payment_method_types.
  ACH-3: GET /account/api/payment-methods returns bank accounts (us_bank_account)
         as well as cards.
  ACH-4: Bank accounts are returned with method_type='bank_account' and correct
         brand/last4 fields (no exp_month/exp_year).
  ACH-5: Cards are still returned with method_type='card'.
  ACH-6: Mixed list (card + bank) returns both, default-first sort preserved.
"""

import os
import sys
import sqlite3
import tempfile
import shutil
import pytest
from unittest.mock import patch, MagicMock, call

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

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
    from app import app as _flask_app  # noqa: F401

    import database
    import utils.auth_utils as auth_utils_mod
    import core.blueprints.account.payment_methods as payment_methods_mod
    import routes.account_routes as account_routes_mod

    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "ach_test.db")

    raw = sqlite3.connect(db_path)
    raw.executescript(SCHEMA)
    raw.commit()
    raw.close()

    orig_db             = database.get_db_connection
    orig_auth           = auth_utils_mod.get_db_connection
    orig_pm             = payment_methods_mod.get_db_connection
    orig_account_routes = account_routes_mod.get_db_connection

    def get_test_conn():
        c = sqlite3.connect(db_path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    database.get_db_connection           = get_test_conn
    auth_utils_mod.get_db_connection     = get_test_conn
    payment_methods_mod.get_db_connection = get_test_conn
    account_routes_mod.get_db_connection  = get_test_conn

    yield db_path, get_test_conn

    database.get_db_connection           = orig_db
    auth_utils_mod.get_db_connection     = orig_auth
    payment_methods_mod.get_db_connection = orig_pm
    account_routes_mod.get_db_connection  = orig_account_routes
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="module")
def client(test_db):
    from app import app as flask_app

    _, get_test_conn = test_db

    conn = get_test_conn()
    conn.execute(
        "INSERT INTO users (id, email, username, password_hash, stripe_customer_id) "
        "VALUES (10, 'ach@test.com', 'achuser', 'hash', 'cus_ach123')"
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


# ---------------------------------------------------------------------------
# ACH-1: Core blueprint SetupIntent includes us_bank_account
# ---------------------------------------------------------------------------

class TestSetupIntentIncludesBankAccount:

    def test_ACH1_core_setup_intent_includes_us_bank_account(self, client):
        """Core payment_methods blueprint: SetupIntent must include us_bank_account."""
        _login(client, 10)

        mock_si = MagicMock()
        mock_si.client_secret = 'seti_core_secret'

        with patch(
            'core.blueprints.account.payment_methods._ensure_stripe_customer',
            return_value='cus_ach123',
        ):
            with patch('stripe.SetupIntent.create', return_value=mock_si) as mock_create:
                resp = client.post('/account/api/payment-methods/setup-intent')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['client_secret'] == 'seti_core_secret'

        call_kwargs = mock_create.call_args[1]
        pm_types = call_kwargs.get('payment_method_types', [])
        assert 'us_bank_account' in pm_types, (
            f"us_bank_account missing from payment_method_types: {pm_types}"
        )
        assert 'card' in pm_types

    def test_ACH2_active_monolith_setup_intent_includes_us_bank_account(self, client):
        """routes/account_routes (active monolith) SetupIntent must include us_bank_account."""
        _login(client, 10)

        mock_si = MagicMock()
        mock_si.client_secret = 'seti_monolith_secret'

        with patch(
            'core.blueprints.account.payment_methods._ensure_stripe_customer',
            return_value='cus_ach123',
        ):
            with patch('stripe.SetupIntent.create', return_value=mock_si) as mock_create:
                resp = client.post('/account/api/payment-methods/setup-intent')

        assert resp.status_code == 200
        call_kwargs = mock_create.call_args[1]
        pm_types = call_kwargs.get('payment_method_types', [])
        assert 'us_bank_account' in pm_types, (
            f"us_bank_account missing from payment_method_types: {pm_types}"
        )


# ---------------------------------------------------------------------------
# ACH-3/4/5/6: GET /account/api/payment-methods returns bank accounts
# ---------------------------------------------------------------------------

class TestGetPaymentMethodsIncludesBankAccounts:

    def _mock_customer(self, default_pm_id=None):
        mock_customer = MagicMock()
        mock_customer.get.side_effect = lambda key, *args: (
            {'default_payment_method': default_pm_id} if key == 'invoice_settings'
            else (args[0] if args else None)
        )
        return mock_customer

    def _mock_card_pm(self, pm_id, brand='visa', last4='4242',
                      exp_month=12, exp_year=2027):
        pm = MagicMock()
        pm.id = pm_id
        pm.type = 'card'
        pm.get.side_effect = lambda key, *args: (
            {'brand': brand, 'last4': last4,
             'exp_month': exp_month, 'exp_year': exp_year, 'funding': 'credit'}
            if key == 'card' else (args[0] if args else None)
        )
        return pm

    def _mock_bank_pm(self, pm_id, bank_name='Chase', last4='6789'):
        pm = MagicMock()
        pm.id = pm_id
        pm.type = 'us_bank_account'
        pm.get.side_effect = lambda key, *args: (
            {'bank_name': bank_name, 'last4': last4}
            if key == 'us_bank_account' else (args[0] if args else None)
        )
        return pm

    def _list_side_effect(self, card_pms, bank_pms):
        """Returns a function that routes PaymentMethod.list by type kwarg."""
        def _list(**kwargs):
            t = kwargs.get('type')
            m = MagicMock()
            m.auto_paging_iter.return_value = card_pms if t == 'card' else bank_pms
            return m
        return _list

    def test_ACH3_bank_account_returned_in_payment_methods_list(self, client):
        """GET /account/api/payment-methods includes us_bank_account methods."""
        _login(client, 10)

        mock_bank = self._mock_bank_pm('pm_bank1', 'Chase', '6789')
        mock_customer = self._mock_customer(default_pm_id=None)

        with patch('stripe.Customer.retrieve', return_value=mock_customer):
            with patch('stripe.PaymentMethod.list',
                       side_effect=self._list_side_effect([], [mock_bank])):
                resp = client.get('/account/api/payment-methods')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        methods = data['payment_methods']
        assert len(methods) == 1
        m = methods[0]
        assert m['id'] == 'pm_bank1'
        assert m['method_type'] == 'bank_account'
        assert m['brand'] == 'Chase'
        assert m['last4'] == '6789'
        # Bank accounts should NOT have expiry
        assert m['exp_month'] is None
        assert m['exp_year'] is None

    def test_ACH4_bank_account_not_mislabeled_as_link_or_card(self, client):
        """Bank account method_type is 'bank_account', not 'card' or 'link'."""
        _login(client, 10)

        mock_bank = self._mock_bank_pm('pm_bank2', 'Wells Fargo', '1234')
        mock_customer = self._mock_customer()

        with patch('stripe.Customer.retrieve', return_value=mock_customer):
            with patch('stripe.PaymentMethod.list',
                       side_effect=self._list_side_effect([], [mock_bank])):
                resp = client.get('/account/api/payment-methods')

        data = resp.get_json()
        methods = data['payment_methods']
        assert methods[0]['method_type'] == 'bank_account'
        assert methods[0]['method_type'] != 'card'
        assert methods[0]['method_type'] != 'link'

    def test_ACH5_cards_still_returned_with_card_method_type(self, client):
        """Cards are returned with method_type='card' (regression test)."""
        _login(client, 10)

        mock_card = self._mock_card_pm('pm_visa1')
        mock_customer = self._mock_customer(default_pm_id='pm_visa1')

        with patch('stripe.Customer.retrieve', return_value=mock_customer):
            with patch('stripe.PaymentMethod.list',
                       side_effect=self._list_side_effect([mock_card], [])):
                resp = client.get('/account/api/payment-methods')

        data = resp.get_json()
        methods = data['payment_methods']
        assert len(methods) == 1
        m = methods[0]
        assert m['id'] == 'pm_visa1'
        assert m['method_type'] == 'card'
        assert m['brand'] == 'visa'
        assert m['last4'] == '4242'
        assert m['is_default'] is True

    def test_ACH6_mixed_list_returns_both_card_and_bank_default_first(self, client):
        """Mixed list: card + bank both returned; default comes first."""
        _login(client, 10)

        mock_card = self._mock_card_pm('pm_card_x')
        mock_bank = self._mock_bank_pm('pm_bank_x', 'Bank of America', '9999')
        # bank is default
        mock_customer = self._mock_customer(default_pm_id='pm_bank_x')

        with patch('stripe.Customer.retrieve', return_value=mock_customer):
            with patch('stripe.PaymentMethod.list',
                       side_effect=self._list_side_effect([mock_card], [mock_bank])):
                resp = client.get('/account/api/payment-methods')

        data = resp.get_json()
        methods = data['payment_methods']
        assert len(methods) == 2

        # Default (bank) should be first
        assert methods[0]['id'] == 'pm_bank_x'
        assert methods[0]['method_type'] == 'bank_account'
        assert methods[0]['is_default'] is True

        assert methods[1]['id'] == 'pm_card_x'
        assert methods[1]['method_type'] == 'card'
        assert methods[1]['is_default'] is False
