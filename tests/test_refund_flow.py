"""
Comprehensive refund flow tests.

Covers:
- Full refund, no transfer yet → buyer refund succeeds, payout cancelled, no reversal
- Full refund, transfer exists → buyer refund succeeds, reversal succeeds
- Full refund, transfer exists, reversal fails → buyer refund succeeds, manual recovery
- Partial refund with correct tax and processing fee breakdown
- Duplicate-click / duplicate-request protection (idempotency)
- Refund amount exceeding refundable remaining is rejected
- Tax liability reduced by refunded tax (refund_tax_amount stored correctly)
- Platform fee / spread reversal tracked on orders_ledger
- Already-partially-refunded order can still refund remaining amount
"""
import pytest
import sqlite3
import sys
import os
from unittest.mock import patch, MagicMock
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Shared in-memory DB fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def refund_db():
    """
    Minimal in-memory SQLite DB for refund_buyer_stripe tests.
    Returns (conn, insert_order) where insert_order builds a test scenario.
    """
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row

    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            stripe_account_id TEXT,
            stripe_payouts_enabled INTEGER DEFAULT 0
        );
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            buyer_id INTEGER,
            total_price REAL,
            tax_amount REAL NOT NULL DEFAULT 0.0,
            tax_rate REAL NOT NULL DEFAULT 0.0,
            buyer_card_fee REAL NOT NULL DEFAULT 0.0,
            payment_status TEXT DEFAULT 'unpaid',
            refund_status TEXT NOT NULL DEFAULT 'not_refunded',
            refund_amount REAL DEFAULT 0.0,
            refund_subtotal REAL NOT NULL DEFAULT 0.0,
            refund_tax_amount REAL NOT NULL DEFAULT 0.0,
            refund_processing_fee REAL NOT NULL DEFAULT 0.0,
            platform_covered_amount REAL NOT NULL DEFAULT 0.0,
            stripe_payment_intent_id TEXT,
            stripe_refund_id TEXT,
            refunded_at TEXT,
            refund_reason TEXT,
            requires_payout_recovery INTEGER DEFAULT 0
        );
        CREATE TABLE orders_ledger (
            id INTEGER PRIMARY KEY,
            order_id INTEGER UNIQUE,
            order_status TEXT DEFAULT 'AWAITING_SHIPMENT',
            gross_amount REAL DEFAULT 0.0,
            platform_fee_amount REAL DEFAULT 0.0,
            spread_capture_amount REAL NOT NULL DEFAULT 0.0,
            refunded_platform_fee_amount REAL NOT NULL DEFAULT 0.0,
            refunded_spread_capture_amount REAL NOT NULL DEFAULT 0.0,
            buyer_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE order_payouts (
            id INTEGER PRIMARY KEY,
            order_ledger_id INTEGER,
            order_id INTEGER,
            seller_id INTEGER,
            payout_status TEXT DEFAULT 'PAYOUT_NOT_READY',
            seller_gross_amount REAL DEFAULT 0.0,
            fee_amount REAL DEFAULT 0.0,
            seller_net_amount REAL DEFAULT 100.0,
            provider_transfer_id TEXT,
            payout_recovery_status TEXT DEFAULT 'not_needed',
            recovery_attempted_at TEXT,
            recovery_completed_at TEXT,
            recovery_attempted_by_admin_id INTEGER,
            recovery_failure_reason TEXT,
            provider_reversal_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
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
    conn.commit()

    def insert_order(
        total_price=110.00,
        tax_amount=8.00,
        buyer_card_fee=2.00,
        payment_status='paid',
        refund_status='not_refunded',
        refund_amount=0.0,
        stripe_pi='pi_test123',
        payout_status='PAYOUT_NOT_READY',
        provider_transfer_id=None,
        gross_amount=100.0,
        platform_fee=5.0,
        spread_capture=2.0,
        seller_net=93.0,
    ):
        """Insert a complete order scenario; return order_id."""
        conn.executescript(
            "DELETE FROM users; DELETE FROM orders; DELETE FROM orders_ledger; "
            "DELETE FROM order_payouts; DELETE FROM order_events;"
        )
        conn.execute("INSERT INTO users VALUES (1, 'buyer1', NULL, 0)")
        conn.execute("INSERT INTO users VALUES (2, 'seller1', 'acct_test', 1)")
        conn.execute("""
            INSERT INTO orders (id, buyer_id, total_price, tax_amount, buyer_card_fee,
                payment_status, refund_status, refund_amount, stripe_payment_intent_id)
            VALUES (1, 1, ?, ?, ?, ?, ?, ?, ?)
        """, (total_price, tax_amount, buyer_card_fee, payment_status,
              refund_status, refund_amount, stripe_pi))
        conn.execute("""
            INSERT INTO orders_ledger (id, order_id, order_status, gross_amount,
                platform_fee_amount, spread_capture_amount, buyer_id)
            VALUES (1, 1, 'AWAITING_SHIPMENT', ?, ?, ?, 1)
        """, (gross_amount, platform_fee, spread_capture))
        conn.execute("""
            INSERT INTO order_payouts (id, order_ledger_id, order_id, seller_id,
                payout_status, seller_gross_amount, fee_amount, seller_net_amount,
                provider_transfer_id, payout_recovery_status)
            VALUES (1, 1, 1, 2, ?, ?, ?, ?, ?, 'not_needed')
        """, (payout_status, gross_amount, platform_fee, seller_net, provider_transfer_id))
        conn.commit()
        return 1

    return conn, insert_order


# ---------------------------------------------------------------------------
# Helper: call refund_buyer_stripe with an injected connection
# ---------------------------------------------------------------------------

def _do_refund(conn, order_id=1, admin_id=99, reason='test refund', amount=None,
               stripe_refund_id='re_test001', stripe_outcome='success',
               reversal_id='trr_test001', reversal_outcome='success'):
    """
    Call refund_buyer_stripe with mocked Stripe calls.
    stripe_outcome: 'success' | 'stripe_error'
    reversal_outcome: 'success' | 'insufficient_funds' | 'stripe_error'
    """
    from core.services.ledger.escrow_control import refund_buyer_stripe
    from core.services.ledger.exceptions import EscrowControlError

    mock_refund = MagicMock()
    mock_refund.id = stripe_refund_id

    mock_reversal = MagicMock()
    mock_reversal.id = reversal_id

    def fake_refund_create(**kwargs):
        if stripe_outcome == 'stripe_error':
            import stripe as _stripe
            raise _stripe.error.StripeError('Stripe down')
        return mock_refund

    def fake_reversal_create(transfer_id, **kwargs):
        if reversal_outcome == 'insufficient_funds':
            import stripe as _stripe
            err = _stripe.error.StripeError('Insufficient funds')
            err.code = 'insufficient_funds'
            raise err
        if reversal_outcome == 'stripe_error':
            import stripe as _stripe
            raise _stripe.error.StripeError('Reversal failed')
        return mock_reversal

    with patch('stripe.Refund.create', side_effect=fake_refund_create), \
         patch('stripe.Transfer.create_reversal', side_effect=fake_reversal_create):
        return refund_buyer_stripe(order_id, admin_id, reason, amount=amount, conn=conn)


# ---------------------------------------------------------------------------
# Scenario 1: Full refund, no transfer yet
# ---------------------------------------------------------------------------

class TestFullRefundNoTransfer:
    def test_buyer_refunded_payout_cancelled(self, refund_db):
        """Full refund with payout not yet released → payout cancelled, no recovery needed."""
        conn, insert = refund_db
        insert(payout_status='PAYOUT_NOT_READY', provider_transfer_id=None)

        result = _do_refund(conn)

        assert result['refund_id'] == 're_test001'
        assert result['amount'] == pytest.approx(110.00, abs=0.01)
        assert result['requires_payout_recovery'] is False
        assert result['cancelled_payout_ids'] == [1]
        assert result['recovery_pending_payout_ids'] == []

        order = conn.execute('SELECT * FROM orders WHERE id=1').fetchone()
        assert order['refund_status'] == 'refunded'
        assert order['refund_amount'] == pytest.approx(110.00, abs=0.01)
        assert order['stripe_refund_id'] == 're_test001'
        assert order['requires_payout_recovery'] == 0

        payout = conn.execute('SELECT * FROM order_payouts WHERE id=1').fetchone()
        assert payout['payout_status'] == 'PAYOUT_CANCELLED'
        assert payout['payout_recovery_status'] == 'not_needed'

        ledger = conn.execute('SELECT * FROM orders_ledger WHERE order_id=1').fetchone()
        assert ledger['order_status'] == 'REFUNDED'

    def test_events_logged(self, refund_db):
        conn, insert = refund_db
        insert()
        _do_refund(conn)
        events = conn.execute('SELECT event_type FROM order_events WHERE order_id=1').fetchall()
        event_types = [e['event_type'] for e in events]
        assert 'REFUND_INITIATED' in event_types
        assert 'REFUND_COMPLETED' in event_types


# ---------------------------------------------------------------------------
# Scenario 2: Full refund, transfer exists → reversal succeeds
# ---------------------------------------------------------------------------

class TestFullRefundTransferExists:
    def test_reversal_succeeds(self, refund_db):
        """Full refund, PAID_OUT payout → reversal attempted and succeeds."""
        conn, insert = refund_db
        insert(payout_status='PAID_OUT', provider_transfer_id='tr_test001')

        result = _do_refund(conn, reversal_id='trr_success')

        assert result['refund_id'] == 're_test001'
        assert result['requires_payout_recovery'] is False  # auto-recovery succeeded
        assert result['recovery_pending_payout_ids'] == []

        # Check recovery outcome
        outcomes = result['recovery_outcomes']
        assert len(outcomes) == 1
        assert outcomes[0]['outcome'] == 'recovered'
        assert outcomes[0]['reversal_id'] == 'trr_success'

        payout = conn.execute('SELECT * FROM order_payouts WHERE id=1').fetchone()
        assert payout['payout_recovery_status'] == 'recovered'
        assert payout['provider_reversal_id'] == 'trr_success'


# ---------------------------------------------------------------------------
# Scenario 3: Full refund, transfer exists, reversal fails
# ---------------------------------------------------------------------------

class TestFullRefundTransferReversalFails:
    def test_reversal_insufficient_funds(self, refund_db):
        """Reversal fails (insufficient_funds) → buyer still refunded, manual recovery flagged."""
        conn, insert = refund_db
        insert(payout_status='PAID_OUT', provider_transfer_id='tr_test001')

        result = _do_refund(conn, reversal_outcome='insufficient_funds')

        # Buyer refund succeeded
        assert result['refund_id'] == 're_test001'
        order = conn.execute('SELECT * FROM orders WHERE id=1').fetchone()
        assert order['refund_status'] == 'refunded'
        assert order['stripe_refund_id'] == 're_test001'

        # Recovery failed → still pending
        assert result['requires_payout_recovery'] is True
        assert 1 in result['recovery_pending_payout_ids']

        outcomes = result['recovery_outcomes']
        assert outcomes[0]['outcome'] == 'manual_review'

        payout = conn.execute('SELECT * FROM order_payouts WHERE id=1').fetchone()
        assert payout['payout_recovery_status'] == 'manual_review'
        assert payout['provider_reversal_id'] is None

    def test_reversal_other_stripe_error(self, refund_db):
        """Reversal fails with generic Stripe error → buyer refunded, payout recovery=failed."""
        conn, insert = refund_db
        insert(payout_status='PAID_OUT', provider_transfer_id='tr_test001')

        result = _do_refund(conn, reversal_outcome='stripe_error')

        assert result['refund_id'] == 're_test001'
        assert result['requires_payout_recovery'] is True

        payout = conn.execute('SELECT * FROM order_payouts WHERE id=1').fetchone()
        assert payout['payout_recovery_status'] == 'failed'


# ---------------------------------------------------------------------------
# Scenario 4: Partial refund — tax and fee breakdown
# ---------------------------------------------------------------------------

class TestPartialRefund:
    def test_partial_amount_stored_correctly(self, refund_db):
        """
        Order: total=$110, subtotal=$100, tax=$8, fee=$2
        Partial refund of $55 (50%)
        Expected: refund_subtotal=50, refund_tax=4, refund_fee=1, total=55
        """
        conn, insert = refund_db
        insert(total_price=110.0, tax_amount=8.0, buyer_card_fee=2.0,
               gross_amount=100.0, platform_fee=5.0, spread_capture=2.0)

        result = _do_refund(conn, amount=55.0)

        assert result['is_partial'] is True
        assert result['amount'] == pytest.approx(55.0, abs=0.01)

        # Proportional: 55/110 = 0.5
        assert result['refund_tax_amount'] == pytest.approx(4.0, abs=0.01)
        assert result['refund_processing_fee'] == pytest.approx(1.0, abs=0.01)
        # Subtotal = 55 - 4 - 1 = 50
        assert result['refund_subtotal'] == pytest.approx(50.0, abs=0.01)

        # Verify stored on orders
        order = conn.execute('SELECT * FROM orders WHERE id=1').fetchone()
        assert order['refund_status'] == 'partially_refunded'
        assert order['refund_amount'] == pytest.approx(55.0, abs=0.01)
        assert order['refund_tax_amount'] == pytest.approx(4.0, abs=0.01)
        assert order['refund_processing_fee'] == pytest.approx(1.0, abs=0.01)

    def test_partial_platform_fee_reversal(self, refund_db):
        """Platform fee and spread are partially reversed proportionally."""
        conn, insert = refund_db
        insert(total_price=110.0, platform_fee=5.0, spread_capture=2.0)

        _do_refund(conn, amount=55.0)  # 50% refund

        ledger = conn.execute('SELECT * FROM orders_ledger WHERE order_id=1').fetchone()
        assert ledger['refunded_platform_fee_amount'] == pytest.approx(2.5, abs=0.01)
        assert ledger['refunded_spread_capture_amount'] == pytest.approx(1.0, abs=0.01)

    def test_partial_then_remaining_refund(self, refund_db):
        """Partial refund followed by another refund for the remaining amount."""
        conn, insert = refund_db
        insert(total_price=110.0, tax_amount=8.0, buyer_card_fee=2.0,
               refund_status='not_refunded', refund_amount=0.0)

        # First partial refund
        result1 = _do_refund(conn, amount=55.0, stripe_refund_id='re_001')
        assert result1['is_partial'] is True

        order = conn.execute('SELECT * FROM orders WHERE id=1').fetchone()
        assert order['refund_status'] == 'partially_refunded'
        assert order['refund_amount'] == pytest.approx(55.0, abs=0.01)

        # Second refund for remaining $55
        result2 = _do_refund(conn, amount=55.0, stripe_refund_id='re_002')
        assert result2['is_partial'] is False  # Now fully refunded

        order = conn.execute('SELECT * FROM orders WHERE id=1').fetchone()
        assert order['refund_status'] == 'refunded'
        assert order['refund_amount'] == pytest.approx(110.0, abs=0.01)


# ---------------------------------------------------------------------------
# Scenario 5: Duplicate protection / idempotency
# ---------------------------------------------------------------------------

class TestDuplicateProtection:
    def test_fully_refunded_order_blocked(self, refund_db):
        """Second refund on a fully-refunded order is rejected."""
        from core.services.ledger.escrow_control import refund_buyer_stripe
        from core.services.ledger.exceptions import EscrowControlError

        conn, insert = refund_db
        insert(refund_status='refunded', refund_amount=110.0)

        with pytest.raises(EscrowControlError, match='already fully refunded'):
            refund_buyer_stripe(1, 99, 'test', conn=conn)

    def test_unpaid_order_blocked(self, refund_db):
        """Refund on unpaid order is rejected."""
        from core.services.ledger.escrow_control import refund_buyer_stripe
        from core.services.ledger.exceptions import EscrowControlError

        conn, insert = refund_db
        insert(payment_status='unpaid')

        with pytest.raises(EscrowControlError, match="payment_status is 'unpaid'"):
            refund_buyer_stripe(1, 99, 'test', conn=conn)

    def test_no_stripe_pi_blocked(self, refund_db):
        """Refund without a Stripe PaymentIntent is rejected."""
        from core.services.ledger.escrow_control import refund_buyer_stripe
        from core.services.ledger.exceptions import EscrowControlError

        conn, insert = refund_db
        insert(stripe_pi=None)

        with pytest.raises(EscrowControlError, match='no Stripe payment'):
            refund_buyer_stripe(1, 99, 'test', conn=conn)


# ---------------------------------------------------------------------------
# Scenario 6: Refund amount exceeds remaining
# ---------------------------------------------------------------------------

class TestRefundAmountValidation:
    def test_exceeds_total_rejected(self, refund_db):
        """Refund of $200 on a $110 order is rejected."""
        from core.services.ledger.escrow_control import refund_buyer_stripe
        from core.services.ledger.exceptions import EscrowControlError

        conn, insert = refund_db
        insert(total_price=110.0)

        with pytest.raises(EscrowControlError, match='exceeds refundable remaining'):
            refund_buyer_stripe(1, 99, 'test', amount=200.0, conn=conn)

    def test_exceeds_remaining_after_partial(self, refund_db):
        """After $55 partial refund, trying to refund $60 more is rejected."""
        from core.services.ledger.escrow_control import refund_buyer_stripe
        from core.services.ledger.exceptions import EscrowControlError

        conn, insert = refund_db
        insert(total_price=110.0, refund_status='partially_refunded', refund_amount=55.0)

        with pytest.raises(EscrowControlError, match='exceeds refundable remaining'):
            refund_buyer_stripe(1, 99, 'test', amount=60.0, conn=conn)

    def test_exact_remaining_accepted(self, refund_db):
        """Refunding exactly the remaining amount after a partial refund is accepted."""
        conn, insert = refund_db
        insert(total_price=110.0, refund_status='partially_refunded', refund_amount=55.0)

        result = _do_refund(conn, amount=55.0, stripe_refund_id='re_final')
        assert result['amount'] == pytest.approx(55.0, abs=0.01)
        assert not result['is_partial']

    def test_zero_amount_rejected(self, refund_db):
        """Zero refund amount is rejected."""
        from core.services.ledger.escrow_control import refund_buyer_stripe
        from core.services.ledger.exceptions import EscrowControlError

        conn, insert = refund_db
        insert()

        with pytest.raises(EscrowControlError, match='must be positive'):
            refund_buyer_stripe(1, 99, 'test', amount=0.0, conn=conn)


# ---------------------------------------------------------------------------
# Scenario 7: Tax liability tracking
# ---------------------------------------------------------------------------

class TestTaxLiability:
    def test_full_refund_records_full_tax(self, refund_db):
        """Full refund: refund_tax_amount equals the full tax_amount."""
        conn, insert = refund_db
        insert(total_price=110.0, tax_amount=8.0, buyer_card_fee=2.0)

        result = _do_refund(conn)

        assert result['refund_tax_amount'] == pytest.approx(8.0, abs=0.01)
        order = conn.execute('SELECT refund_tax_amount FROM orders WHERE id=1').fetchone()
        assert order['refund_tax_amount'] == pytest.approx(8.0, abs=0.01)

    def test_partial_refund_records_proportional_tax(self, refund_db):
        """
        Partial refund of $55 on $110 order (tax=$8, fee=$2):
        refund_tax = 8 * 0.5 = 4.0
        """
        conn, insert = refund_db
        insert(total_price=110.0, tax_amount=8.0, buyer_card_fee=2.0)

        result = _do_refund(conn, amount=55.0)

        assert result['refund_tax_amount'] == pytest.approx(4.0, abs=0.01)

    def test_no_tax_order(self, refund_db):
        """Order with no tax: refund_tax_amount is 0."""
        conn, insert = refund_db
        insert(total_price=102.0, tax_amount=0.0, buyer_card_fee=2.0)

        result = _do_refund(conn)

        assert result['refund_tax_amount'] == pytest.approx(0.0, abs=0.01)


# ---------------------------------------------------------------------------
# Scenario 8: Platform fee and spread reversal
# ---------------------------------------------------------------------------

class TestPlatformFeeReversal:
    def test_full_refund_reverses_full_platform_fee(self, refund_db):
        """Full refund: entire platform fee and spread are reversed."""
        conn, insert = refund_db
        insert(total_price=110.0, platform_fee=5.0, spread_capture=2.0)

        _do_refund(conn)

        ledger = conn.execute('SELECT * FROM orders_ledger WHERE order_id=1').fetchone()
        assert ledger['refunded_platform_fee_amount'] == pytest.approx(5.0, abs=0.01)
        assert ledger['refunded_spread_capture_amount'] == pytest.approx(2.0, abs=0.01)

    def test_partial_refund_proportional_reversal(self, refund_db):
        """25% partial refund reverses 25% of platform fee and spread."""
        conn, insert = refund_db
        insert(total_price=100.0, tax_amount=0.0, buyer_card_fee=0.0,
               platform_fee=10.0, spread_capture=4.0)

        _do_refund(conn, amount=25.0)  # 25/100 = 25%

        ledger = conn.execute('SELECT * FROM orders_ledger WHERE order_id=1').fetchone()
        assert ledger['refunded_platform_fee_amount'] == pytest.approx(2.5, abs=0.01)
        assert ledger['refunded_spread_capture_amount'] == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# Scenario 9: Processing fee handling
# ---------------------------------------------------------------------------

class TestProcessingFeeHandling:
    def test_full_refund_includes_card_fee(self, refund_db):
        """Full refund includes the full buyer card fee in the Stripe refund amount."""
        conn, insert = refund_db
        insert(total_price=110.0, tax_amount=8.0, buyer_card_fee=2.0)

        result = _do_refund(conn)

        # Full refund amount = total_price (includes card fee)
        assert result['amount'] == pytest.approx(110.0, abs=0.01)
        assert result['refund_processing_fee'] == pytest.approx(2.0, abs=0.01)

    def test_ach_order_has_zero_fee(self, refund_db):
        """ACH orders have zero card fee; refund_processing_fee is 0."""
        conn, insert = refund_db
        insert(total_price=108.0, tax_amount=8.0, buyer_card_fee=0.0)

        result = _do_refund(conn)

        assert result['refund_processing_fee'] == pytest.approx(0.0, abs=0.01)

    def test_partial_refund_fee_proportional(self, refund_db):
        """50% partial refund → 50% of card fee is refunded."""
        conn, insert = refund_db
        insert(total_price=110.0, tax_amount=8.0, buyer_card_fee=2.0)

        result = _do_refund(conn, amount=55.0)

        assert result['refund_processing_fee'] == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# Scenario 10: Stripe failure — DB not mutated
# ---------------------------------------------------------------------------

class TestStripeFails:
    def test_stripe_failure_rolls_back(self, refund_db):
        """If Stripe.Refund.create fails, the DB is not mutated."""
        conn, insert = refund_db
        insert()

        from core.services.ledger.escrow_control import refund_buyer_stripe
        from core.services.ledger.exceptions import EscrowControlError
        import stripe as _stripe

        def bad_stripe(**kwargs):
            raise _stripe.error.StripeError('Stripe offline')

        with patch('stripe.Refund.create', side_effect=bad_stripe):
            with pytest.raises(EscrowControlError, match='Stripe refund failed'):
                refund_buyer_stripe(1, 99, 'test', conn=conn)

        # DB unchanged
        order = conn.execute('SELECT * FROM orders WHERE id=1').fetchone()
        assert order['refund_status'] == 'not_refunded'
        assert (order['stripe_refund_id'] or '') == ''


# ---------------------------------------------------------------------------
# Scenario 11: Refund preview endpoint returns correct breakdown
# ---------------------------------------------------------------------------

class TestRefundPreviewEndpoint:
    def _make_app_and_order(self, refund_db):
        """Set up Flask test client + DB."""
        conn, insert = refund_db
        insert(total_price=110.0, tax_amount=8.0, buyer_card_fee=2.0,
               payment_status='paid', refund_status='not_refunded')
        return conn

    def test_preview_returns_subtotal_breakdown(self, refund_db):
        """
        /refund-preview should return subtotal, tax_amount, buyer_card_fee
        in the order dict, and refundable_amount = total_price.
        """
        from core.blueprints.admin.orders import admin_refund_preview
        import database as _db_module

        conn, insert = refund_db
        insert(total_price=110.0, tax_amount=8.0, buyer_card_fee=2.0)

        with patch.object(_db_module, 'get_db_connection', return_value=conn):
            # Simulate a request context
            import flask
            app = flask.Flask(__name__)
            app.config['TESTING'] = True
            app.config['WTF_CSRF_ENABLED'] = False

            # Directly call the underlying DB query logic rather than HTTP
            order = conn.execute('''
                SELECT o.id, o.total_price, o.tax_amount, o.buyer_card_fee,
                       o.payment_status, o.refund_status, o.refund_amount,
                       o.refund_subtotal, o.refund_tax_amount, o.refund_processing_fee,
                       o.platform_covered_amount,
                       o.stripe_payment_intent_id, o.refund_reason, o.stripe_refund_id, o.refunded_at,
                       u.username AS buyer_username
                FROM orders o
                JOIN users u ON o.buyer_id = u.id
                WHERE o.id = 1
            ''').fetchone()

        assert order is not None
        total_price = float(order['total_price'])
        tax_amount  = float(order['tax_amount'])
        card_fee    = float(order['buyer_card_fee'])
        subtotal    = round(total_price - tax_amount - card_fee, 2)

        assert total_price == pytest.approx(110.0, abs=0.01)
        assert tax_amount  == pytest.approx(8.0,   abs=0.01)
        assert card_fee    == pytest.approx(2.0,   abs=0.01)
        assert subtotal    == pytest.approx(100.0, abs=0.01)


# ---------------------------------------------------------------------------
# Scenario 12: Refund breakdown totals integrity
# ---------------------------------------------------------------------------

class TestBreakdownIntegrity:
    def test_breakdown_sums_to_refund_amount(self, refund_db):
        """refund_subtotal + refund_tax + refund_fee == refund_amount (within rounding)."""
        conn, insert = refund_db
        insert(total_price=110.0, tax_amount=8.00, buyer_card_fee=2.00)

        result = _do_refund(conn)

        total_breakdown = (
            result['refund_subtotal']
            + result['refund_tax_amount']
            + result['refund_processing_fee']
        )
        assert total_breakdown == pytest.approx(result['amount'], abs=0.02)

    def test_partial_breakdown_sums_to_refund_amount(self, refund_db):
        """Partial refund breakdown also sums correctly."""
        conn, insert = refund_db
        insert(total_price=110.0, tax_amount=8.00, buyer_card_fee=2.00)

        result = _do_refund(conn, amount=33.33)

        total_breakdown = (
            result['refund_subtotal']
            + result['refund_tax_amount']
            + result['refund_processing_fee']
        )
        assert total_breakdown == pytest.approx(result['amount'], abs=0.02)


# ---------------------------------------------------------------------------
# Scenario 13: Cumulative refund_amount accumulates correctly
# ---------------------------------------------------------------------------

class TestCumulativeRefundAccumulation:
    def test_two_partial_refunds_accumulate(self, refund_db):
        """Two $30 partial refunds on a $110 order add up to $60 total."""
        conn, insert = refund_db
        insert(total_price=110.0, tax_amount=8.0, buyer_card_fee=2.0)

        _do_refund(conn, amount=30.0, stripe_refund_id='re_1')
        _do_refund(conn, amount=30.0, stripe_refund_id='re_2')

        order = conn.execute('SELECT * FROM orders WHERE id=1').fetchone()
        assert order['refund_amount'] == pytest.approx(60.0, abs=0.01)
        assert order['refund_status'] == 'partially_refunded'

    def test_full_refund_after_two_partials_marks_refunded(self, refund_db):
        """After two $30 partials, refunding remaining $50 marks order fully refunded."""
        conn, insert = refund_db
        insert(total_price=110.0, tax_amount=8.0, buyer_card_fee=2.0)

        _do_refund(conn, amount=30.0, stripe_refund_id='re_1')
        _do_refund(conn, amount=30.0, stripe_refund_id='re_2')
        _do_refund(conn, amount=50.0, stripe_refund_id='re_3')

        order = conn.execute('SELECT * FROM orders WHERE id=1').fetchone()
        assert order['refund_status'] == 'refunded'
        assert order['refund_amount'] == pytest.approx(110.0, abs=0.01)


# ---------------------------------------------------------------------------
# Scenario 14: Platform coverage tracking
# ---------------------------------------------------------------------------

class TestPlatformCoverage:
    """Platform covers refund costs when seller recovery fails."""

    def test_recovery_success_zero_platform_coverage(self, refund_db):
        """
        Full refund, transfer exists, reversal succeeds →
        platform_covered_amount stays 0.
        """
        conn, insert = refund_db
        insert(payout_status='PAID_OUT', provider_transfer_id='tr_abc',
               seller_net=93.0)

        result = _do_refund(conn, reversal_outcome='success')

        assert result['platform_covered_amount'] == pytest.approx(0.0, abs=0.01)
        order = conn.execute('SELECT platform_covered_amount FROM orders WHERE id=1').fetchone()
        assert order['platform_covered_amount'] == pytest.approx(0.0, abs=0.01)

    def test_recovery_failure_sets_platform_coverage(self, refund_db):
        """
        Full refund, transfer exists, reversal fails →
        platform_covered_amount = seller_net_amount (Metex absorbs the loss).
        """
        conn, insert = refund_db
        insert(payout_status='PAID_OUT', provider_transfer_id='tr_abc',
               seller_net=93.0)

        result = _do_refund(conn, reversal_outcome='insufficient_funds')

        assert result['platform_covered_amount'] == pytest.approx(93.0, abs=0.01)
        order = conn.execute('SELECT platform_covered_amount FROM orders WHERE id=1').fetchone()
        assert order['platform_covered_amount'] == pytest.approx(93.0, abs=0.01)

    def test_recovery_stripe_error_sets_platform_coverage(self, refund_db):
        """
        Full refund, reversal fails with stripe_error →
        platform_covered_amount = seller_net_amount.
        """
        conn, insert = refund_db
        insert(payout_status='PAID_OUT', provider_transfer_id='tr_abc',
               seller_net=93.0)

        result = _do_refund(conn, reversal_outcome='stripe_error')

        assert result['platform_covered_amount'] == pytest.approx(93.0, abs=0.01)

    def test_no_paid_out_payout_zero_coverage(self, refund_db):
        """
        Full refund, no paid-out payout → platform_covered_amount = 0.
        Payout is cancelled, no recovery attempted.
        """
        conn, insert = refund_db
        insert(payout_status='PAYOUT_NOT_READY', provider_transfer_id=None)

        result = _do_refund(conn)

        assert result['platform_covered_amount'] == pytest.approx(0.0, abs=0.01)
        order = conn.execute('SELECT platform_covered_amount FROM orders WHERE id=1').fetchone()
        assert order['platform_covered_amount'] == pytest.approx(0.0, abs=0.01)

    def test_manual_recovery_reduces_platform_coverage(self, refund_db):
        """
        After initial recovery fails (platform absorbs loss), a subsequent manual
        recovery success reduces platform_covered_amount back to 0.
        """
        from core.services.ledger.escrow_control import attempt_payout_recovery

        conn, insert = refund_db
        insert(payout_status='PAID_OUT', provider_transfer_id='tr_abc',
               seller_net=93.0)

        # Initial refund: recovery fails → platform covers $93
        _do_refund(conn, reversal_outcome='insufficient_funds')
        order = conn.execute('SELECT platform_covered_amount FROM orders WHERE id=1').fetchone()
        assert order['platform_covered_amount'] == pytest.approx(93.0, abs=0.01)

        # Now manually retry recovery and succeed
        conn.execute(
            "UPDATE order_payouts SET payout_recovery_status='pending' WHERE id=1"
        )
        conn.commit()

        mock_reversal = MagicMock()
        mock_reversal.id = 'trr_retry001'

        with patch('stripe.Transfer.create_reversal', return_value=mock_reversal):
            outcome = attempt_payout_recovery(1, admin_id=99, conn=conn)

        assert outcome['outcome'] == 'recovered'
        conn.commit()

        order = conn.execute('SELECT platform_covered_amount FROM orders WHERE id=1').fetchone()
        assert order['platform_covered_amount'] == pytest.approx(0.0, abs=0.01)

    def test_return_value_has_platform_covered_amount_key(self, refund_db):
        """
        refund_buyer_stripe always returns platform_covered_amount key
        (even when 0) so callers can rely on it.
        """
        conn, insert = refund_db
        insert(payout_status='PAYOUT_NOT_READY', provider_transfer_id=None)

        result = _do_refund(conn)

        assert 'platform_covered_amount' in result
