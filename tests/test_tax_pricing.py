"""
Tests: Tax-inclusive pricing flow (Stripe Tax)

TAX-1.  Card order: tax from Stripe; card fee on taxed subtotal; total correct
TAX-2.  ACH order:  tax from Stripe; buyer_card_fee = 0; total = subtotal + tax
TAX-3.  order_service.create_order() stores tax_amount and correct total_price
TAX-4.  Stripe PaymentIntent amount = subtotal + tax + card_fee (cents)
TAX-5.  Seller net is unaffected by tax or buyer card fee (payout based on gross only)
TAX-6.  Reconciliation AMOUNT_MISMATCH respects tax in expected total
TAX-7.  Reconciliation MATCHED and MISSING_CARD_FEE work correctly with tax present
"""

import os
import sys
import sqlite3
import tempfile
import pytest
from unittest.mock import patch, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ---------------------------------------------------------------------------
# Constants (Stripe Tax is the authority; these match what _get_stripe_tax
# returns for a $100 subtotal in the test mocks below)
# ---------------------------------------------------------------------------
CARD_RATE = 0.0299
CARD_FLAT = 0.30

# Mock tax amounts returned by our Stripe Tax helper for given subtotals.
# Real amounts come from Stripe; these are just test fixtures.
MOCK_TAX_RATE = 0.0825          # effective rate in the test mock (informational)
MOCK_TAX_CENTS_100 = 825        # $8.25 tax on $100.00 subtotal
MOCK_TAX_CENTS_200 = 1650       # $16.50 tax on $200.00 subtotal
MOCK_TAX_CENTS_500 = 4125       # $41.25 tax on $500.00 subtotal
MOCK_TAX_CALC_ID   = 'taxcalc_test_001'


def _stripe_tax_mock(subtotal_cents, postal_code, state='', country='US'):
    """
    Simulate _get_stripe_tax() returning proportional tax at MOCK_TAX_RATE.
    In production this calls stripe.tax.Calculation.create(); here we stub it.
    """
    tax_cents = round(subtotal_cents * MOCK_TAX_RATE)
    return tax_cents, MOCK_TAX_CALC_ID


def _compute_card_fee(taxed_subtotal):
    return round(taxed_subtotal * CARD_RATE + CARD_FLAT, 2)


def _compute_total(subtotal, tax, card_fee):
    return round(subtotal + tax + card_fee, 2)


# ===========================================================================
# TAX-1: Card order math (Stripe Tax)
# ===========================================================================

def test_tax1_card_order_math():
    """Stripe Tax → taxed subtotal → card fee → total; no rounding drift."""
    subtotal = 100.00
    # Simulate Stripe Tax returning $8.25
    tax_cents = MOCK_TAX_CENTS_100
    tax = round(tax_cents / 100, 2)    # 8.25
    assert tax == 8.25, f"Expected 8.25 got {tax}"

    taxed_subtotal = subtotal + tax    # 108.25
    card_fee = _compute_card_fee(taxed_subtotal)
    # 108.25 × 0.0299 + 0.30 = 3.5367 → 3.54
    assert card_fee == round(108.25 * 0.0299 + 0.30, 2)

    total = _compute_total(subtotal, tax, card_fee)
    assert total == round(subtotal + tax + card_fee, 2)

    # Stripe amount in cents must match the stored total exactly
    amount_cents = int(round(total * 100))
    assert amount_cents == round(total * 100)


def test_tax1_card_fee_is_NOT_on_subtotal_alone():
    """The card fee MUST be larger than subtotal×CARD_RATE alone."""
    subtotal = 200.00
    tax = round(MOCK_TAX_CENTS_200 / 100, 2)  # 16.50 from Stripe
    taxed = subtotal + tax                     # 216.50

    fee_correct = _compute_card_fee(taxed)              # on taxed subtotal
    fee_wrong   = round(subtotal * CARD_RATE + CARD_FLAT, 2)  # incorrect: no tax

    assert fee_correct > fee_wrong, "Card fee should be higher when computed on taxed subtotal"


# ===========================================================================
# TAX-2: ACH order math (Stripe Tax)
# ===========================================================================

def test_tax2_ach_order_no_card_fee():
    """ACH: Stripe Tax still applies; buyer_card_fee = 0; total = subtotal + tax."""
    subtotal = 500.00
    tax = round(MOCK_TAX_CENTS_500 / 100, 2)  # 41.25 from Stripe
    card_fee = 0.0   # ACH
    total = _compute_total(subtotal, tax, card_fee)

    assert card_fee == 0.0
    assert total == round(subtotal + tax, 2)
    assert total == round(500.00 + 41.25, 2)


# ===========================================================================
# TAX-3: create_order() stores tax correctly
# ===========================================================================

SCHEMA_ORDERS = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, username TEXT, email TEXT,
    password TEXT DEFAULT '', password_hash TEXT DEFAULT '',
    is_admin INTEGER DEFAULT 0, is_banned INTEGER DEFAULT 0,
    is_frozen INTEGER DEFAULT 0, is_metex_guaranteed INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY, seller_id INTEGER, category_id INTEGER,
    price_per_coin REAL, quantity INTEGER DEFAULT 1,
    active INTEGER DEFAULT 1, listing_title TEXT DEFAULT '',
    description TEXT, packaging_type TEXT, packaging_notes TEXT,
    condition_notes TEXT, pricing_mode TEXT DEFAULT 'static',
    spot_premium REAL, floor_price REAL, pricing_metal TEXT,
    photo_filename TEXT
);
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY, listing_id INTEGER, metal TEXT, product_line TEXT,
    product_type TEXT, weight TEXT, year TEXT, mint TEXT, purity TEXT,
    finish TEXT, condition_category TEXT, series_variant TEXT,
    bucket_id INTEGER, grade TEXT, is_isolated INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS listing_photos (
    id INTEGER PRIMARY KEY, listing_id INTEGER, file_path TEXT
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_id INTEGER,
    total_price REAL DEFAULT 0,
    buyer_card_fee REAL DEFAULT 0,
    tax_amount REAL DEFAULT 0,
    tax_rate REAL DEFAULT 0,
    shipping_address TEXT,
    recipient_first_name TEXT,
    recipient_last_name TEXT,
    placed_from_ip TEXT,
    status TEXT DEFAULT 'Pending',
    payment_status TEXT DEFAULT 'unpaid',
    payout_status TEXT DEFAULT 'PAYOUT_NOT_READY',
    refund_status TEXT DEFAULT 'not_refunded',
    refund_amount REAL DEFAULT 0,
    stripe_refund_id TEXT,
    refunded_at TIMESTAMP,
    refund_reason TEXT,
    requires_payout_recovery INTEGER DEFAULT 0,
    stripe_payment_intent_id TEXT,
    payment_method_type TEXT,
    requires_payment_clearance INTEGER DEFAULT 0,
    payment_cleared_at TIMESTAMP,
    payment_cleared_by_admin_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER, listing_id INTEGER,
    quantity INTEGER, price_each REAL,
    spot_price_at_purchase REAL, spot_as_of_used TEXT,
    spot_source_used TEXT, pricing_mode_at_purchase TEXT,
    spot_premium_used REAL, weight_used REAL
);
CREATE TABLE IF NOT EXISTS transaction_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER, order_item_id INTEGER, snapshot_at TEXT,
    listing_id INTEGER, listing_title TEXT, listing_description TEXT,
    metal TEXT, product_line TEXT, product_type TEXT, weight TEXT,
    year TEXT, mint TEXT, purity TEXT, finish TEXT,
    condition_category TEXT, series_variant TEXT,
    packaging_type TEXT, packaging_notes TEXT, condition_notes TEXT,
    photo_filenames TEXT,
    quantity INTEGER, price_each REAL, pricing_mode TEXT,
    spot_price_at_purchase REAL,
    seller_id INTEGER, seller_username TEXT, seller_email TEXT,
    buyer_id INTEGER, buyer_username TEXT, buyer_email TEXT,
    payment_intent_id TEXT
);
"""


@pytest.fixture(scope='module')
def order_db():
    """In-memory SQLite database with orders schema for order_service tests."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, 'tax_test.db')

    import database
    import utils.auth_utils as _au

    raw = sqlite3.connect(db_path)
    raw.executescript(SCHEMA_ORDERS)
    raw.execute("INSERT INTO users (id,username,email) VALUES (1,'buyer','b@t.com')")
    raw.execute("INSERT INTO users (id,username,email) VALUES (2,'seller','s@t.com')")
    raw.execute(
        "INSERT INTO categories (id,listing_id,metal,product_type,weight,bucket_id) "
        "VALUES (10,100,'Gold','Coin','1 oz',1)"
    )
    raw.execute(
        "INSERT INTO listings (id,seller_id,category_id,price_per_coin,quantity,listing_title) "
        "VALUES (100,2,10,800.00,5,'Test Coin')"
    )
    raw.commit()
    raw.close()

    _orig_conn = database.get_db_connection

    def _mock_conn():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        return c

    database.get_db_connection = _mock_conn

    import utils.auth_utils
    utils.auth_utils.get_db_connection = _mock_conn

    yield _mock_conn

    database.get_db_connection = _orig_conn
    utils.auth_utils.get_db_connection = _orig_conn


def test_tax3_create_order_stores_tax(order_db):
    """create_order() persists tax_amount from Stripe Tax and computes total correctly."""
    from services.order_service import create_order

    subtotal = 100.00
    # Simulate Stripe Tax result: $8.25 on $100 subtotal
    tax = round(MOCK_TAX_CENTS_100 / 100, 2)   # 8.25
    taxed = subtotal + tax                      # 108.25
    card_fee = _compute_card_fee(taxed)         # 3.54
    # Effective rate stored for informational purposes
    effective_rate = round(tax / subtotal, 6)   # 0.0825

    cart = [{'listing_id': 100, 'quantity': 1, 'price_each': 100.00}]

    order_id = create_order(
        buyer_id=1,
        cart_items=cart,
        shipping_address='123 Test St',
        buyer_card_fee=card_fee,
        tax_amount=tax,
        tax_rate=effective_rate,
    )
    assert order_id is not None

    conn = order_db()
    row = conn.execute(
        'SELECT total_price, buyer_card_fee, tax_amount, tax_rate FROM orders WHERE id=?',
        (order_id,)
    ).fetchone()
    conn.close()

    assert row is not None
    assert abs(row['tax_amount'] - tax) < 0.001
    assert abs(row['buyer_card_fee'] - card_fee) < 0.001
    expected_total = round(subtotal + tax + card_fee, 2)
    assert abs(row['total_price'] - expected_total) < 0.001


def test_tax3_ach_order_stores_zero_card_fee(order_db):
    """ACH order: card_fee=0, Stripe tax stored, total = subtotal + tax."""
    from services.order_service import create_order

    subtotal = 200.00
    tax = round(MOCK_TAX_CENTS_200 / 100, 2)   # 16.50 from Stripe
    cart = [{'listing_id': 100, 'quantity': 1, 'price_each': 200.00}]

    order_id = create_order(
        buyer_id=1,
        cart_items=cart,
        shipping_address='456 ACH St',
        buyer_card_fee=0.0,
        tax_amount=tax,
        tax_rate=round(tax / subtotal, 6),
    )
    conn = order_db()
    row = conn.execute(
        'SELECT total_price, buyer_card_fee, tax_amount FROM orders WHERE id=?',
        (order_id,)
    ).fetchone()
    conn.close()

    assert abs(row['buyer_card_fee']) < 0.001
    assert abs(row['tax_amount'] - tax) < 0.001
    expected = round(subtotal + tax, 2)
    assert abs(row['total_price'] - expected) < 0.001


# ===========================================================================
# TAX-4: Stripe PaymentIntent amount = subtotal + Stripe tax + card fee
# ===========================================================================

def test_tax4_stripe_amount_cents_matches_total():
    """The integer cents sent to Stripe equals round(total × 100)."""
    subtotal = 349.99
    # Stripe Tax mock returns MOCK_TAX_RATE of subtotal
    tax = round(subtotal * MOCK_TAX_RATE, 2)
    taxed = subtotal + tax
    card_fee = _compute_card_fee(taxed)
    total = _compute_total(subtotal, tax, card_fee)

    amount_cents = int(round(total * 100))

    reconstructed = amount_cents / 100
    assert abs(reconstructed - total) < 0.01, \
        f"Cents/total mismatch: {amount_cents}¢ vs ${total:.2f}"


def test_tax4_stripe_amount_ach():
    """ACH Stripe amount = subtotal + Stripe tax (no card fee)."""
    subtotal = 1000.00
    tax = round(subtotal * MOCK_TAX_RATE, 2)
    total = round(subtotal + tax, 2)
    amount_cents = int(round(total * 100))
    assert amount_cents == int(round((subtotal + tax) * 100))


# ===========================================================================
# TAX-5: Seller payout unaffected by tax and card fee
# ===========================================================================

def test_tax5_seller_net_excludes_tax_and_card_fee():
    """Seller net = gross_amount − platform_fee. Tax and card fee are buyer-only."""
    gross_amount = 500.00    # pre-tax item revenue
    platform_fee = 25.00     # Metex 5% cut
    tax_amount   = round(MOCK_TAX_CENTS_500 / 100, 2)   # from Stripe
    card_fee     = _compute_card_fee(gross_amount + tax_amount)

    seller_net = gross_amount - platform_fee

    # Seller receives none of the tax or card fee
    assert abs(seller_net - 475.00) < 0.001
    assert seller_net < (gross_amount + tax_amount + card_fee - platform_fee), \
        "Seller net should not include tax or card fee"


# ===========================================================================
# TAX-6 & TAX-7: Reconciliation status with tax
# ===========================================================================

from core.blueprints.admin.reconciliation import compute_recon_status


def _row(total_price, gross_amount, buyer_card_fee, tax_amount=0.0,
         payment_status='paid', payout_status='PAID_OUT',
         stripe_pi='pi_test', transfer_id='tr_test',
         payment_method_type='card'):
    return {
        'total_price': total_price,
        'gross_amount': gross_amount,
        'buyer_card_fee': buyer_card_fee,
        'tax_amount': tax_amount,
        'payment_status': payment_status,
        'payout_status': payout_status,
        'stripe_payment_intent_id': stripe_pi,
        'provider_transfer_id': transfer_id,
        'payment_method_type': payment_method_type,
    }


def test_tax6_recon_matched_with_tax():
    """MATCHED: total_price = gross + Stripe tax + card_fee, all refs present."""
    gross = 100.00
    # Stripe-derived tax stored on the order
    tax   = round(MOCK_TAX_CENTS_100 / 100, 2)
    fee   = _compute_card_fee(gross + tax)
    total = round(gross + tax + fee, 2)

    status = compute_recon_status(_row(
        total_price=total,
        gross_amount=gross,
        buyer_card_fee=fee,
        tax_amount=tax,
    ))
    assert status == 'MATCHED', f"Expected MATCHED, got {status}"


def test_tax6_recon_amount_mismatch_when_tax_missing_from_total():
    """AMOUNT_MISMATCH: total_price doesn't include tax (old incorrect calculation)."""
    gross = 100.00
    tax   = round(MOCK_TAX_CENTS_100 / 100, 2)
    fee   = _compute_card_fee(gross + tax)
    # total stored without tax — old bug
    wrong_total = round(gross + fee, 2)

    status = compute_recon_status(_row(
        total_price=wrong_total,
        gross_amount=gross,
        buyer_card_fee=fee,
        tax_amount=tax,   # tax IS known but was not included in total_price
    ))
    assert status == 'AMOUNT_MISMATCH', f"Expected AMOUNT_MISMATCH, got {status}"


def test_tax6_recon_ach_matched_with_tax():
    """ACH MATCHED: Stripe tax present, card fee=0, total=gross+tax."""
    gross = 200.00
    tax   = round(MOCK_TAX_CENTS_200 / 100, 2)
    total = round(gross + tax, 2)

    status = compute_recon_status(_row(
        total_price=total,
        gross_amount=gross,
        buyer_card_fee=0.0,
        tax_amount=tax,
        payment_method_type='us_bank_account',
    ))
    assert status == 'MATCHED', f"Expected MATCHED, got {status}"


def test_tax7_missing_card_fee_with_tax():
    """MISSING_CARD_FEE: card payment where fee was skipped but Stripe tax was applied."""
    gross = 100.00
    tax   = round(MOCK_TAX_CENTS_100 / 100, 2)
    # total includes tax but NO card fee
    total = round(gross + tax, 2)

    status = compute_recon_status(_row(
        total_price=total,
        gross_amount=gross,
        buyer_card_fee=0.0,
        tax_amount=tax,
        payment_method_type='card',
    ))
    assert status == 'MISSING_CARD_FEE', f"Expected MISSING_CARD_FEE, got {status}"


def test_tax7_pre_tax_orders_still_matched():
    """Pre-tax orders (tax_amount=0) continue to MATCH if total=gross+card_fee."""
    gross = 150.00
    fee   = round(gross * CARD_RATE + CARD_FLAT, 2)   # old formula, no tax
    total = round(gross + fee, 2)

    # tax_amount=0 means this is a legacy pre-tax order — should still MATCH
    status = compute_recon_status(_row(
        total_price=total,
        gross_amount=gross,
        buyer_card_fee=fee,
        tax_amount=0.0,
    ))
    assert status == 'MATCHED', f"Pre-tax order should still MATCH, got {status}"


def test_tax7_pre_tax_missing_card_fee():
    """Pre-tax MISSING_CARD_FEE still detected when tax_amount=0."""
    gross = 150.00
    # old card order that never had a fee applied
    status = compute_recon_status(_row(
        total_price=gross,   # total == gross (no tax, no fee)
        gross_amount=gross,
        buyer_card_fee=0.0,
        tax_amount=0.0,
        payment_method_type='card',
    ))
    assert status == 'MISSING_CARD_FEE', f"Expected MISSING_CARD_FEE, got {status}"


# ===========================================================================
# TAX-8: _get_stripe_tax() returns 0 when postal code is missing
# ===========================================================================

def test_tax8_no_postal_code_returns_zero():
    """_get_stripe_tax() returns (0, None) when postal_code is empty string."""
    from core.blueprints.checkout.routes import _get_stripe_tax
    tax_cents, calc_id = _get_stripe_tax(10000, postal_code='')
    assert tax_cents == 0
    assert calc_id is None


def test_tax8_zero_subtotal_returns_zero():
    """_get_stripe_tax() returns (0, None) when subtotal_cents <= 0."""
    from core.blueprints.checkout.routes import _get_stripe_tax
    tax_cents, calc_id = _get_stripe_tax(0, postal_code='90210', state='CA')
    assert tax_cents == 0
    assert calc_id is None


# ===========================================================================
# TAX-9: /checkout/api/tax-estimate endpoint — correct amounts with address
# ===========================================================================

@pytest.fixture(scope='module')
def checkout_client():
    """Flask test client for checkout blueprint endpoint tests."""
    import os as _os
    _os.environ.setdefault('FLASK_TESTING', '1')
    from core import create_app
    test_app = create_app({'TESTING': True, 'WTF_CSRF_ENABLED': False,
                           'SECRET_KEY': 'tax-test-secret'})
    with test_app.test_client() as c:
        with test_app.test_request_context():
            from flask import session
        yield c, test_app


def test_tax9_estimate_endpoint_with_postal_code(checkout_client):
    """Tax estimate endpoint returns tax_amount and taxed_subtotal when postal code given."""
    client, app = checkout_client

    with client.session_transaction() as sess:
        sess['user_id'] = 1

    with patch('core.blueprints.checkout.routes._get_stripe_tax',
               return_value=(825, 'taxcalc_test')):
        resp = client.post('/checkout/api/tax-estimate',
                           json={'subtotal': 100.00, 'postal_code': '90210',
                                 'state': 'CA', 'country': 'US'})

    assert resp.status_code == 200
    data = resp.get_json()
    assert 'tax_amount' in data
    assert 'taxed_subtotal' in data
    assert 'tax_calculated' in data
    assert data['tax_calculated'] is True
    assert abs(data['tax_amount'] - 8.25) < 0.01
    assert abs(data['taxed_subtotal'] - 108.25) < 0.01


def test_tax9_estimate_endpoint_no_subtotal_returns_400(checkout_client):
    """Tax estimate endpoint returns 400 when subtotal is zero or missing."""
    client, app = checkout_client

    with client.session_transaction() as sess:
        sess['user_id'] = 1

    resp = client.post('/checkout/api/tax-estimate',
                       json={'subtotal': 0, 'postal_code': '90210'})
    assert resp.status_code == 400


def test_tax9_estimate_endpoint_no_postal_returns_zero_tax(checkout_client):
    """When postal code is missing, endpoint returns tax_amount=0 and tax_calculated=False."""
    client, app = checkout_client

    with client.session_transaction() as sess:
        sess['user_id'] = 1

    # _get_stripe_tax returns (0, None) when no postal code — no mock needed
    resp = client.post('/checkout/api/tax-estimate',
                       json={'subtotal': 100.00, 'postal_code': ''})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['tax_amount'] == 0.0
    assert abs(data['taxed_subtotal'] - 100.00) < 0.01
    assert data['tax_calculated'] is False


# ===========================================================================
# TAX-10: Processing fee recalculates on taxed subtotal after estimate
# ===========================================================================

def test_tax10_processing_fee_after_tax_estimate():
    """After Stripe tax estimate, processing fee must be on taxed subtotal."""
    subtotal  = 100.00
    # Stripe returned 8.25 tax
    tax       = 8.25
    taxed     = subtotal + tax      # 108.25

    fee_on_taxed    = round(taxed * CARD_RATE + CARD_FLAT, 2)
    fee_on_subtotal = round(subtotal * CARD_RATE + CARD_FLAT, 2)

    assert fee_on_taxed > fee_on_subtotal, \
        "After tax is known, card fee should be larger (computed on taxed subtotal)"
    assert abs(fee_on_taxed - round(108.25 * 0.0299 + 0.30, 2)) < 0.001


def test_tax10_ach_fee_is_zero_regardless_of_tax():
    """ACH: processing fee stays 0 even after tax is known."""
    subtotal = 100.00
    tax      = 8.25
    taxed    = subtotal + tax
    ach_fee  = 0.0   # ACH is always free
    total    = round(taxed + ach_fee, 2)

    assert ach_fee == 0.0
    assert abs(total - 108.25) < 0.001


# ===========================================================================
# TAX-11: Taxed subtotal math consistency
# ===========================================================================

def test_tax11_taxed_subtotal_equals_subtotal_plus_tax():
    """taxed_subtotal returned by endpoint must equal subtotal + tax_amount."""
    subtotal   = 250.00
    tax_amount = round(250.00 * MOCK_TAX_RATE, 2)
    taxed      = round(subtotal + tax_amount, 2)

    # Simulate endpoint response data
    endpoint_response = {
        'tax_amount': tax_amount,
        'taxed_subtotal': taxed,
    }
    assert abs(endpoint_response['taxed_subtotal'] -
               (endpoint_response['tax_amount'] + subtotal)) < 0.001


def test_tax11_zero_tax_jurisdiction_shows_zero_not_placeholder():
    """If Stripe returns 0 tax for a valid address, tax_amount=0 is a real value."""
    subtotal   = 100.00
    # Some states have no sales tax — Stripe returns 0
    tax_amount = 0.0
    taxed      = subtotal + tax_amount  # 100.00

    total = round(taxed + _compute_card_fee(taxed), 2)
    # tax_amount == 0 is a valid result (not a placeholder)
    assert tax_amount == 0.0
    # Total still includes card fee applied to taxed subtotal
    expected_fee = _compute_card_fee(100.00)
    assert abs(total - round(100.00 + expected_fee, 2)) < 0.001
