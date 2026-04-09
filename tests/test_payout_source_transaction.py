"""
Tests for source_transaction fix in release_stripe_transfer.

Verifies that the payout release:
  1. Retrieves the PaymentIntent to get the charge ID
  2. Passes source_transaction to stripe.Transfer.create()
  3. Falls back gracefully when no payment_intent_id exists
  4. Falls back gracefully when Stripe PI retrieval fails
"""
import pytest
import sqlite3
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Inject a fake `stripe` module so tests run without the real SDK installed.
# release_stripe_transfer does `import stripe` locally, so we need it in
# sys.modules before the function executes.
# ---------------------------------------------------------------------------

def _make_stripe_module(charge_id='ch_test_xyz', transfer_id='tr_test_001'):
    """Return a MagicMock that looks like the stripe module to our code."""
    m = MagicMock(name='stripe')
    # PaymentIntent.retrieve → returns object with latest_charge
    mock_pi = MagicMock()
    mock_pi.latest_charge = charge_id
    m.PaymentIntent.retrieve.return_value = mock_pi
    # Transfer.create → returns object with .id
    mock_transfer = MagicMock()
    mock_transfer.id = transfer_id
    m.Transfer.create.return_value = mock_transfer
    # Make StripeError a real exception class so except clauses work
    class _StripeError(Exception):
        pass
    m.error.StripeError = _StripeError
    return m


# ---------------------------------------------------------------------------
# Minimal DB fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def payout_db():
    """
    In-memory SQLite DB with a ready-to-pay payout row.
    Returns (conn, payout_id).
    """
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row

    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            stripe_account_id TEXT,
            stripe_charges_enabled INTEGER DEFAULT 1,
            stripe_payouts_enabled INTEGER DEFAULT 1,
            stripe_onboarding_complete INTEGER DEFAULT 1
        );
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            buyer_id INTEGER,
            status TEXT DEFAULT 'paid',
            payment_status TEXT DEFAULT 'paid',
            payment_method_type TEXT DEFAULT 'card',
            requires_payment_clearance INTEGER DEFAULT 0,
            stripe_payment_intent_id TEXT,
            refund_status TEXT DEFAULT 'not_refunded',
            requires_payout_recovery INTEGER DEFAULT 0
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
            payout_status TEXT DEFAULT 'PAYOUT_READY',
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
            delivered_at TEXT,
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
    """)

    # Seller with Stripe account
    conn.execute(
        "INSERT INTO users VALUES (1, 'seller1', 'acct_test123', 1, 1, 1)"
    )
    # Order with a PaymentIntent ID
    conn.execute(
        "INSERT INTO orders VALUES (1, 2, 'paid', 'paid', 'card', 0, 'pi_test_abc', 'not_refunded', 0)"
    )
    # Ledger row in a payable status
    conn.execute(
        "INSERT INTO orders_ledger (id, order_id, order_status, gross_amount, platform_fee_amount, buyer_id, created_at) VALUES (1, 1, 'AWAITING_SHIPMENT', 200.0, 10.0, 2, datetime('now'))"
    )
    # Payout row ready to release
    conn.execute(
        "INSERT INTO order_payouts (id, order_ledger_id, order_id, seller_id, payout_status, seller_gross_amount, fee_amount, seller_net_amount, provider_transfer_id, payout_recovery_status, created_at, updated_at) VALUES (1, 1, 1, 1, 'PAYOUT_READY', 110.0, 10.0, 100.0, NULL, 'not_needed', datetime('now'), datetime('now'))"
    )
    # Tracking with delivered_at set
    delivered = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S')
    conn.execute(
        "INSERT INTO seller_order_tracking VALUES (1, 1, 1, 'TRACK123', 'USPS', ?, datetime('now'), datetime('now'))",
        (delivered,)
    )
    conn.commit()

    return conn, 1  # payout_id = 1




# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSourceTransactionPassthrough:

    def _call_release(self, payout_db, mock_stripe):
        conn, payout_id = payout_db
        with patch('core.services.ledger.escrow_control.get_db_connection', return_value=conn), \
             patch.dict(sys.modules, {'stripe': mock_stripe}):
            from core.services.ledger.escrow_control import release_stripe_transfer
            return release_stripe_transfer(payout_id, admin_id=99)

    def test_retrieves_payment_intent(self, payout_db):
        """release_stripe_transfer should call PaymentIntent.retrieve with the PI id."""
        mock_stripe = _make_stripe_module()
        self._call_release(payout_db, mock_stripe)
        mock_stripe.PaymentIntent.retrieve.assert_called_once_with('pi_test_abc')

    def test_passes_source_transaction_to_transfer(self, payout_db):
        """stripe.Transfer.create must include source_transaction=charge_id."""
        mock_stripe = _make_stripe_module(charge_id='ch_test_xyz')
        self._call_release(payout_db, mock_stripe)

        _, kwargs = mock_stripe.Transfer.create.call_args
        assert kwargs.get('source_transaction') == 'ch_test_xyz', (
            f"Expected source_transaction='ch_test_xyz', got: {mock_stripe.Transfer.create.call_args}"
        )

    def test_transfer_amount_correct(self, payout_db):
        """Transfer amount should be seller_net_amount in cents (100.0 → 10000)."""
        mock_stripe = _make_stripe_module()
        self._call_release(payout_db, mock_stripe)

        _, kwargs = mock_stripe.Transfer.create.call_args
        assert kwargs['amount'] == 10000

    def test_transfer_destination_correct(self, payout_db):
        """Transfer destination should be the seller's connected account ID."""
        mock_stripe = _make_stripe_module()
        self._call_release(payout_db, mock_stripe)

        _, kwargs = mock_stripe.Transfer.create.call_args
        assert kwargs['destination'] == 'acct_test123'

    def test_returns_transfer_id(self, payout_db):
        """release_stripe_transfer should return the Stripe transfer ID."""
        mock_stripe = _make_stripe_module(transfer_id='tr_test_001')
        result = self._call_release(payout_db, mock_stripe)
        assert result['transfer_id'] == 'tr_test_001'

    def test_payout_marked_paid_out_in_db(self):
        """After release, payout_status should be PAID_OUT in the DB."""
        # Use a shared-cache named in-memory DB so a second connection can
        # verify state after release_stripe_transfer closes the first connection.
        db_uri = "file:payout_test_db?mode=memory&cache=shared"
        conn = sqlite3.connect(db_uri, uri=True)
        conn.row_factory = sqlite3.Row
        # Build schema and data inline (same as payout_db fixture)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY, username TEXT, stripe_account_id TEXT,
                stripe_charges_enabled INTEGER DEFAULT 1,
                stripe_payouts_enabled INTEGER DEFAULT 1,
                stripe_onboarding_complete INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY, buyer_id INTEGER, status TEXT DEFAULT 'paid',
                payment_status TEXT DEFAULT 'paid', payment_method_type TEXT DEFAULT 'card',
                requires_payment_clearance INTEGER DEFAULT 0,
                stripe_payment_intent_id TEXT, refund_status TEXT DEFAULT 'not_refunded',
                requires_payout_recovery INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS orders_ledger (
                id INTEGER PRIMARY KEY, order_id INTEGER UNIQUE,
                order_status TEXT DEFAULT 'AWAITING_SHIPMENT',
                gross_amount REAL DEFAULT 200.0, platform_fee_amount REAL DEFAULT 10.0,
 spread_capture_amount REAL NOT NULL DEFAULT 0.0,
                buyer_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS order_payouts (
                id INTEGER PRIMARY KEY, order_ledger_id INTEGER, order_id INTEGER,
                seller_id INTEGER, payout_status TEXT DEFAULT 'PAYOUT_READY',
                seller_gross_amount REAL DEFAULT 110.0, fee_amount REAL DEFAULT 10.0,
                seller_net_amount REAL DEFAULT 100.0, provider_transfer_id TEXT,
                payout_recovery_status TEXT DEFAULT 'not_needed',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS seller_order_tracking (
                id INTEGER PRIMARY KEY, order_id INTEGER, seller_id INTEGER,
                tracking_number TEXT, carrier TEXT, delivered_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(order_id, seller_id)
            );
            CREATE TABLE IF NOT EXISTS order_events (
                id INTEGER PRIMARY KEY, order_id INTEGER, event_type TEXT,
                actor_type TEXT DEFAULT 'system', actor_id INTEGER,
                payload_json TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("INSERT INTO users VALUES (1,'seller1','acct_test123',1,1,1)")
        conn.execute("INSERT INTO orders VALUES (1,2,'paid','paid','card',0,'pi_test_abc','not_refunded',0)")
        conn.execute("INSERT INTO orders_ledger (id, order_id, order_status, gross_amount, platform_fee_amount, buyer_id, created_at) VALUES (1,1,'AWAITING_SHIPMENT',200.0,10.0,2,datetime('now'))")
        conn.execute("INSERT INTO order_payouts (id, order_ledger_id, order_id, seller_id, payout_status, seller_gross_amount, fee_amount, seller_net_amount, provider_transfer_id, payout_recovery_status, created_at, updated_at) VALUES (1,1,1,1,'PAYOUT_READY',110.0,10.0,100.0,NULL,'not_needed',datetime('now'),datetime('now'))")
        delivered = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S')
        conn.execute("INSERT INTO seller_order_tracking VALUES (1,1,1,'TRACK123','USPS',?,datetime('now'),datetime('now'))", (delivered,))
        conn.commit()

        # Open the reader BEFORE releasing so the shared-cache DB stays alive
        # even after release_stripe_transfer closes its connection.
        reader = sqlite3.connect(db_uri, uri=True)
        reader.row_factory = sqlite3.Row

        mock_stripe = _make_stripe_module()
        with patch('core.services.ledger.escrow_control.get_db_connection', return_value=conn), \
             patch.dict(sys.modules, {'stripe': mock_stripe}):
            from core.services.ledger.escrow_control import release_stripe_transfer
            release_stripe_transfer(1, admin_id=99)

        row = reader.execute(
            "SELECT payout_status, provider_transfer_id FROM order_payouts WHERE id = 1"
        ).fetchone()
        reader.close()

        assert row['payout_status'] == 'PAID_OUT'
        assert row['provider_transfer_id'] == 'tr_test_001'


class TestSourceTransactionFallbacks:
    """Graceful degradation when PI retrieval fails or PI ID is missing."""

    def _make_db_without_pi(self, payout_db):
        """Remove the stripe_payment_intent_id from the order."""
        conn, payout_id = payout_db
        conn.execute("UPDATE orders SET stripe_payment_intent_id = NULL WHERE id = 1")
        conn.commit()
        return conn, payout_id

    def test_no_source_transaction_when_no_pi_id(self, payout_db):
        """If order has no PI id, transfer proceeds without source_transaction."""
        conn, payout_id = self._make_db_without_pi(payout_db)
        mock_stripe = _make_stripe_module()

        with patch('core.services.ledger.escrow_control.get_db_connection', return_value=conn), \
             patch.dict(sys.modules, {'stripe': mock_stripe}):
            from core.services.ledger.escrow_control import release_stripe_transfer
            result = release_stripe_transfer(payout_id, admin_id=99)

        mock_stripe.PaymentIntent.retrieve.assert_not_called()
        _, kwargs = mock_stripe.Transfer.create.call_args
        assert 'source_transaction' not in kwargs
        assert result['transfer_id'] == 'tr_test_001'

    def test_no_source_transaction_when_pi_retrieval_fails(self, payout_db):
        """If Stripe PI retrieval throws, transfer proceeds without source_transaction."""
        conn, payout_id = payout_db
        mock_stripe = _make_stripe_module()
        mock_stripe.PaymentIntent.retrieve.side_effect = mock_stripe.error.StripeError("Stripe API error")

        with patch('core.services.ledger.escrow_control.get_db_connection', return_value=conn), \
             patch.dict(sys.modules, {'stripe': mock_stripe}):
            from core.services.ledger.escrow_control import release_stripe_transfer
            result = release_stripe_transfer(payout_id, admin_id=99)

        _, kwargs = mock_stripe.Transfer.create.call_args
        assert 'source_transaction' not in kwargs
        assert result['transfer_id'] == 'tr_test_001'
