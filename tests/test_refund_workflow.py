"""
tests/test_refund_workflow.py
==============================
Refund workflow tests covering the two-stage refund architecture:
  Stage 1 — Stripe refund on the original PaymentIntent (buyer side)
  Stage 2 — Stripe Transfer Reversal for seller recovery (seller side)

Scenarios tested
----------------
RW-1  Paid order, no seller transfer yet → refund succeeds, payout is CANCELLED
RW-2  Paid order, seller transfer already released → refund succeeds, reversal succeeds
RW-3  Paid order, seller transfer released → refund succeeds, reversal fails (manual_review)
RW-4  Partial refund via process_refund (seller-targeted, ledger-only)
RW-5  Multi-seller full refund — all payout rows cancelled
RW-6  Duplicate-click protection — second refund call blocked (idempotency)
RW-7  Refund blocked when payment_status is not 'paid'
RW-8  refund-preview endpoint returns correct data for eligible order
RW-9  refund-preview blocked when order already refunded
"""

import json
import os
import sys
import sqlite3
import pytest
from unittest.mock import patch, MagicMock

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ──────────────────────────────────────────────────────────────────────────────
# Schema helper
# ──────────────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    email TEXT,
    is_admin INTEGER DEFAULT 0,
    stripe_account_id TEXT,
    stripe_payouts_enabled INTEGER DEFAULT 0
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_id INTEGER,
    total_price REAL DEFAULT 0,
    tax_amount REAL NOT NULL DEFAULT 0.0,
    tax_rate REAL NOT NULL DEFAULT 0.0,
    buyer_card_fee REAL DEFAULT 0,
    status TEXT DEFAULT 'Pending',
    payment_status TEXT DEFAULT 'unpaid',
    payment_method_type TEXT,
    stripe_payment_intent_id TEXT,
    paid_at TEXT,
    requires_payment_clearance INTEGER DEFAULT 0,
    payment_cleared_at TEXT,
    refund_status TEXT DEFAULT 'not_refunded',
    refund_amount REAL DEFAULT 0,
    refund_subtotal REAL NOT NULL DEFAULT 0.0,
    refund_tax_amount REAL NOT NULL DEFAULT 0.0,
    refund_processing_fee REAL NOT NULL DEFAULT 0.0,
    platform_covered_amount REAL NOT NULL DEFAULT 0.0,
    stripe_refund_id TEXT,
    refunded_at TEXT,
    refund_reason TEXT,
    requires_payout_recovery INTEGER DEFAULT 0,
    shipping_address TEXT,
    placed_from_ip TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE orders_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER UNIQUE NOT NULL,
    buyer_id INTEGER NOT NULL,
    order_status TEXT NOT NULL DEFAULT 'CHECKOUT_INITIATED',
    gross_amount REAL NOT NULL DEFAULT 0,
    platform_fee_amount REAL NOT NULL DEFAULT 0,
    spread_capture_amount REAL NOT NULL DEFAULT 0.0,
    refunded_platform_fee_amount REAL NOT NULL DEFAULT 0.0,
    refunded_spread_capture_amount REAL NOT NULL DEFAULT 0.0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE order_items_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_ledger_id INTEGER NOT NULL,
    order_id INTEGER NOT NULL,
    seller_id INTEGER NOT NULL,
    listing_id INTEGER NOT NULL DEFAULT 0,
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_price REAL NOT NULL DEFAULT 0,
    gross_amount REAL NOT NULL DEFAULT 0,
    fee_type TEXT NOT NULL DEFAULT 'percent',
    fee_value REAL NOT NULL DEFAULT 0,
    fee_amount REAL NOT NULL DEFAULT 0,
    seller_net_amount REAL NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE order_payouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_ledger_id INTEGER NOT NULL,
    order_id INTEGER NOT NULL,
    seller_id INTEGER NOT NULL,
    payout_status TEXT NOT NULL DEFAULT 'PAYOUT_NOT_READY',
    seller_gross_amount REAL NOT NULL DEFAULT 0,
    fee_amount REAL NOT NULL DEFAULT 0,
    seller_net_amount REAL NOT NULL DEFAULT 0,
    spread_capture_amount REAL NOT NULL DEFAULT 0.0,
    scheduled_for TEXT,
    provider_transfer_id TEXT,
    provider_payout_id TEXT,
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id INTEGER,
    payload_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE refunds (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    dispute_id          INTEGER,
    order_id            INTEGER NOT NULL,
    order_item_id       INTEGER,
    buyer_id            INTEGER NOT NULL,
    seller_id           INTEGER,
    amount              REAL NOT NULL,
    provider_refund_id  TEXT,
    issued_by_admin_id  INTEGER NOT NULL,
    issued_at           TEXT NOT NULL,
    note                TEXT
);
"""


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def test_db(tmp_path):
    """Create an in-memory-style test SQLite DB with the refund-relevant schema."""
    db_path = tmp_path / "refund_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)

    # Seed users
    conn.execute("INSERT INTO users (id, username, email, is_admin) VALUES (1, 'buyer1', 'buyer1@test.com', 0)")
    conn.execute("INSERT INTO users (id, username, email, is_admin) VALUES (2, 'seller1', 'seller1@test.com', 0)")
    conn.execute("INSERT INTO users (id, username, email, is_admin) VALUES (3, 'seller2', 'seller2@test.com', 0)")
    conn.execute("INSERT INTO users (id, username, email, is_admin) VALUES (4, 'admin1',  'admin@test.com',  1)")
    conn.commit()
    yield conn, str(db_path)
    conn.close()


@pytest.fixture
def mock_db(test_db, monkeypatch):
    """Patch database.get_db_connection to return fresh connections to the test DB.

    Follows the documented pattern: must patch both the module attribute AND every
    module that imported get_db_connection by name at module load time.
    """
    conn, db_path = test_db

    def _factory():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        return c

    import database
    monkeypatch.setattr(database, 'get_db_connection', _factory)

    # Patch modules that imported get_db_connection at module level (not via database.*)
    import utils.auth_utils as _auth_utils
    monkeypatch.setattr(_auth_utils, 'get_db_connection', _factory)

    import core.services.ledger.escrow_control as ec
    monkeypatch.setattr(ec, 'get_db_connection', _factory)

    # Patch the admin orders blueprint's database module reference
    import core.blueprints.admin.orders as _admin_orders
    import core.blueprints.admin.orders as _ao_mod
    # The blueprint uses `import database as _db_module` — patch via the module attribute
    import importlib
    _ao_db = importlib.import_module('database')  # same object as `database`
    # Already patched via monkeypatch.setattr(database, ...)

    return _factory


# ──────────────────────────────────────────────────────────────────────────────
# DB seeding helpers
# ──────────────────────────────────────────────────────────────────────────────

def _seed_paid_order(db_factory, total=200.00, pi_id='pi_test123',
                     payment_method='card', buyer_card_fee=0.0):
    """Insert a paid order and its ledger row. Returns order_id, ledger_id."""
    conn = db_factory()
    cur = conn.execute(
        """INSERT INTO orders
           (buyer_id, total_price, buyer_card_fee, status, payment_status,
            payment_method_type, stripe_payment_intent_id, paid_at,
            refund_status, refund_amount)
           VALUES (1, ?, ?, 'paid', 'paid', ?, ?, CURRENT_TIMESTAMP,
                   'not_refunded', 0)""",
        (total, buyer_card_fee, payment_method, pi_id),
    )
    order_id = cur.lastrowid

    cur2 = conn.execute(
        """INSERT INTO orders_ledger
           (order_id, buyer_id, order_status, gross_amount, platform_fee_amount)
           VALUES (?, 1, 'PAID_IN_ESCROW', ?, 0)""",
        (order_id, total),
    )
    ledger_id = cur2.lastrowid
    conn.commit()
    conn.close()
    return order_id, ledger_id


def _seed_payout(db_factory, order_id, ledger_id, seller_id=2,
                 net=190.00, payout_status='PAYOUT_NOT_READY',
                 transfer_id=None, recovery_status='not_needed'):
    """Insert one order_payouts row. Returns payout_id."""
    conn = db_factory()
    cur = conn.execute(
        """INSERT INTO order_payouts
           (order_ledger_id, order_id, seller_id, payout_status,
            seller_gross_amount, fee_amount, seller_net_amount,
            provider_transfer_id, payout_recovery_status)
           VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)""",
        (ledger_id, order_id, seller_id, payout_status,
         net, net, transfer_id, recovery_status),
    )
    payout_id = cur.lastrowid
    conn.commit()
    conn.close()
    return payout_id


def _seed_item_ledger(db_factory, order_id, ledger_id, seller_id=2,
                      gross=200.00, net=190.00):
    """Insert one order_items_ledger row."""
    conn = db_factory()
    conn.execute(
        """INSERT INTO order_items_ledger
           (order_ledger_id, order_id, seller_id, listing_id, quantity,
            unit_price, gross_amount, fee_type, fee_value, fee_amount, seller_net_amount)
           VALUES (?, ?, ?, 1, 1, ?, ?, 'percent', 5.0, ?, ?)""",
        (ledger_id, order_id, seller_id, gross, gross, gross - net, net),
    )
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# Mock Stripe helpers
# ──────────────────────────────────────────────────────────────────────────────

def _mock_stripe_refund(refund_id='re_test_001'):
    m = MagicMock()
    m.id = refund_id
    return m


def _mock_stripe_reversal(reversal_id='pyr_test_001'):
    m = MagicMock()
    m.id = reversal_id
    return m


# ──────────────────────────────────────────────────────────────────────────────
# RW-1: Paid order, no transfer yet → refund OK, payout cancelled
# ──────────────────────────────────────────────────────────────────────────────

class TestRefundNoTransfer:

    def test_rw1_refund_succeeds_payout_cancelled(self, mock_db):
        """RW-1: Full refund on a paid order with no seller transfer yet."""
        from core.services.ledger.escrow_control import refund_buyer_stripe

        order_id, ledger_id = _seed_paid_order(mock_db, total=200.00)
        payout_id = _seed_payout(mock_db, order_id, ledger_id,
                                  payout_status='PAYOUT_NOT_READY')

        mock_refund = _mock_stripe_refund('re_norec_001')

        with patch('stripe.Refund.create', return_value=mock_refund):
            result = refund_buyer_stripe(order_id, admin_id=4, reason='Test refund')

        assert result['refund_id'] == 're_norec_001'
        assert result['amount'] == 200.00
        assert result['requires_payout_recovery'] is False
        assert payout_id in result['cancelled_payout_ids']
        assert result['recovery_pending_payout_ids'] == []

        # Verify DB state
        conn = mock_db()
        order = conn.execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchone()
        assert order['refund_status'] == 'refunded'
        assert order['stripe_refund_id'] == 're_norec_001'
        assert order['refund_amount'] == 200.00
        assert order['requires_payout_recovery'] == 0

        payout = conn.execute('SELECT * FROM order_payouts WHERE id = ?', (payout_id,)).fetchone()
        assert payout['payout_status'] == 'PAYOUT_CANCELLED'
        assert payout['payout_recovery_status'] == 'not_needed'

        ledger = conn.execute('SELECT * FROM orders_ledger WHERE order_id = ?', (order_id,)).fetchone()
        assert ledger['order_status'] == 'REFUNDED'
        conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# RW-2: Prior transfer exists, reversal succeeds
# ──────────────────────────────────────────────────────────────────────────────

class TestRefundWithSuccessfulReversal:

    def test_rw2_refund_then_recovery_success(self, mock_db):
        """RW-2: Refund succeeds; Stripe Transfer Reversal succeeds immediately via auto-recovery."""
        from core.services.ledger.escrow_control import refund_buyer_stripe, attempt_payout_recovery

        order_id, ledger_id = _seed_paid_order(mock_db, total=200.00)
        payout_id = _seed_payout(
            mock_db, order_id, ledger_id,
            payout_status='PAID_OUT',
            transfer_id='tr_already_sent',
            recovery_status='not_needed',
        )

        # Auto-recovery runs immediately inside refund_buyer_stripe — mock reversal to succeed.
        mock_refund = _mock_stripe_refund('re_with_xfr')
        mock_reversal = _mock_stripe_reversal('pyr_success_001')
        with patch('stripe.Refund.create', return_value=mock_refund), \
             patch('stripe.Transfer.create_reversal', return_value=mock_reversal):
            refund_result = refund_buyer_stripe(order_id, admin_id=4, reason='RW-2 test')

        # Auto-recovery succeeded → no pending payouts remain
        assert refund_result['requires_payout_recovery'] is False
        assert refund_result['recovery_pending_payout_ids'] == []
        assert len(refund_result['recovery_outcomes']) == 1
        assert refund_result['recovery_outcomes'][0]['outcome'] == 'recovered'
        assert refund_result['recovery_outcomes'][0]['reversal_id'] == 'pyr_success_001'
        assert refund_result['platform_covered_amount'] == 0.0

        # DB: payout already recovered
        conn = mock_db()
        payout = conn.execute('SELECT * FROM order_payouts WHERE id = ?', (payout_id,)).fetchone()
        assert payout['payout_recovery_status'] == 'recovered'
        assert payout['provider_reversal_id'] == 'pyr_success_001'
        conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# RW-3: Prior transfer, reversal fails → manual_review
# ──────────────────────────────────────────────────────────────────────────────

class TestRefundWithFailedReversal:

    def test_rw3_refund_ok_reversal_fails_manual_review(self, mock_db):
        """RW-3: Buyer refunded but seller recovery fails (insufficient funds)."""
        import stripe as stripe_module
        from core.services.ledger.escrow_control import refund_buyer_stripe, attempt_payout_recovery

        order_id, ledger_id = _seed_paid_order(mock_db, total=150.00)
        payout_id = _seed_payout(
            mock_db, order_id, ledger_id,
            payout_status='PAID_OUT',
            transfer_id='tr_withdrawn',
            net=140.00,
        )

        # Stage 1: Refund buyer — succeeds
        mock_refund = _mock_stripe_refund('re_fail_xfr')
        with patch('stripe.Refund.create', return_value=mock_refund):
            refund_result = refund_buyer_stripe(order_id, admin_id=4, reason='RW-3 test')

        assert refund_result['requires_payout_recovery'] is True

        # Stage 2: Transfer reversal fails (seller withdrew funds).
        # Must pass code= as keyword arg because StripeError.__init__ sets self.code=code.
        insuff_err = stripe_module.error.StripeError(
            'Insufficient funds', code='insufficient_funds'
        )
        with patch('stripe.Transfer.create_reversal', side_effect=insuff_err):
            recovery_result = attempt_payout_recovery(payout_id, admin_id=4)

        assert recovery_result['outcome'] == 'manual_review'
        assert recovery_result['reversal_id'] is None
        assert 'Insufficient' in (recovery_result['reason'] or '')

        # DB: recovery status = 'manual_review', failure reason stored
        conn = mock_db()
        payout = conn.execute('SELECT * FROM order_payouts WHERE id = ?', (payout_id,)).fetchone()
        assert payout['payout_recovery_status'] == 'manual_review'
        assert payout['recovery_failure_reason'] is not None
        conn.close()

    def test_rw3b_buyer_refund_not_blocked_by_reversal_failure(self, mock_db):
        """RW-3b: The buyer refund is committed before any reversal attempt."""
        import stripe as stripe_module
        from core.services.ledger.escrow_control import refund_buyer_stripe, attempt_payout_recovery

        order_id, ledger_id = _seed_paid_order(mock_db, total=100.00)
        payout_id = _seed_payout(
            mock_db, order_id, ledger_id,
            payout_status='PAID_OUT',
            transfer_id='tr_gone',
        )

        mock_refund = _mock_stripe_refund('re_buyer_ok')
        with patch('stripe.Refund.create', return_value=mock_refund):
            result = refund_buyer_stripe(order_id, admin_id=4)

        # Buyer refund is recorded regardless of recovery
        conn = mock_db()
        order = conn.execute('SELECT refund_status, stripe_refund_id FROM orders WHERE id = ?',
                             (order_id,)).fetchone()
        assert order['refund_status'] == 'refunded'
        assert order['stripe_refund_id'] == 're_buyer_ok'
        conn.close()

        # Recovery attempt fails — does NOT roll back the buyer refund
        generic_err = stripe_module.error.StripeError('Generic stripe error', code='card_declined')
        with patch('stripe.Transfer.create_reversal', side_effect=generic_err):
            recovery_result = attempt_payout_recovery(payout_id, admin_id=4)

        assert recovery_result['outcome'] == 'failed'

        # Buyer refund still stands
        conn = mock_db()
        order = conn.execute('SELECT refund_status FROM orders WHERE id = ?', (order_id,)).fetchone()
        assert order['refund_status'] == 'refunded'
        conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# RW-4: Partial refund via process_refund (ledger-only)
# ──────────────────────────────────────────────────────────────────────────────

class TestPartialRefund:

    def test_rw4_partial_refund_by_seller_id(self, mock_db):
        """RW-4: Partial refund targets one seller, leaves other seller untouched."""
        from core.services.ledger.escrow_control import process_refund

        order_id, ledger_id = _seed_paid_order(mock_db, total=300.00)

        # Two sellers
        payout_s1 = _seed_payout(mock_db, order_id, ledger_id, seller_id=2, net=100.00)
        payout_s2 = _seed_payout(mock_db, order_id, ledger_id, seller_id=3, net=190.00)
        _seed_item_ledger(mock_db, order_id, ledger_id, seller_id=2, gross=110.00, net=100.00)
        _seed_item_ledger(mock_db, order_id, ledger_id, seller_id=3, gross=200.00, net=190.00)

        result = process_refund(
            order_id=order_id, admin_id=4,
            refund_type='partial', reason='Seller 2 item damaged',
            seller_id=2,
        )

        assert result['refund_amount'] == 110.00  # gross of seller 2 items

        conn = mock_db()
        p1 = conn.execute('SELECT payout_status FROM order_payouts WHERE id = ?', (payout_s1,)).fetchone()
        p2 = conn.execute('SELECT payout_status FROM order_payouts WHERE id = ?', (payout_s2,)).fetchone()
        ledger = conn.execute('SELECT order_status FROM orders_ledger WHERE order_id = ?', (order_id,)).fetchone()
        conn.close()

        assert p1['payout_status'] == 'PAYOUT_CANCELLED'   # seller 2 cancelled
        assert p2['payout_status'] == 'PAYOUT_NOT_READY'   # seller 3 untouched
        assert ledger['order_status'] == 'PARTIALLY_REFUNDED'


# ──────────────────────────────────────────────────────────────────────────────
# RW-5: Multi-seller full refund
# ──────────────────────────────────────────────────────────────────────────────

class TestMultiSellerRefund:

    def test_rw5_multi_seller_full_refund(self, mock_db):
        """RW-5: Full refund cancels ALL seller payouts across two sellers."""
        from core.services.ledger.escrow_control import refund_buyer_stripe

        order_id, ledger_id = _seed_paid_order(mock_db, total=300.00)
        payout_s1 = _seed_payout(mock_db, order_id, ledger_id, seller_id=2, net=100.00)
        payout_s2 = _seed_payout(mock_db, order_id, ledger_id, seller_id=3, net=190.00)

        mock_refund = _mock_stripe_refund('re_multi')
        with patch('stripe.Refund.create', return_value=mock_refund):
            result = refund_buyer_stripe(order_id, admin_id=4, reason='RW-5 multi-seller')

        assert result['requires_payout_recovery'] is False
        assert set(result['cancelled_payout_ids']) == {payout_s1, payout_s2}

        conn = mock_db()
        payouts = conn.execute(
            'SELECT payout_status FROM order_payouts WHERE order_id = ?', (order_id,)
        ).fetchall()
        conn.close()

        assert all(p['payout_status'] == 'PAYOUT_CANCELLED' for p in payouts)

    def test_rw5b_multi_seller_with_one_paid_out(self, mock_db):
        """RW-5b: Full refund when one seller already paid out → auto-recovery attempted."""
        import stripe as stripe_module
        from core.services.ledger.escrow_control import refund_buyer_stripe

        order_id, ledger_id = _seed_paid_order(mock_db, total=300.00)
        payout_s1 = _seed_payout(
            mock_db, order_id, ledger_id, seller_id=2, net=100.00,
            payout_status='PAID_OUT', transfer_id='tr_s1_sent',
        )
        payout_s2 = _seed_payout(
            mock_db, order_id, ledger_id, seller_id=3, net=190.00,
            payout_status='PAYOUT_NOT_READY',
        )

        # Auto-recovery runs immediately for the paid-out payout; mock it to fail.
        insuff_err = stripe_module.error.StripeError(
            'Insufficient funds', code='insufficient_funds'
        )
        mock_refund = _mock_stripe_refund('re_multi_partial')
        with patch('stripe.Refund.create', return_value=mock_refund), \
             patch('stripe.Transfer.create_reversal', side_effect=insuff_err):
            result = refund_buyer_stripe(order_id, admin_id=4, reason='RW-5b')

        # Auto-recovery failed → payout_s1 still needs manual recovery
        assert result['requires_payout_recovery'] is True
        assert payout_s1 in result['recovery_pending_payout_ids']
        assert payout_s2 in result['cancelled_payout_ids']
        assert result['platform_covered_amount'] == pytest.approx(100.0, abs=0.01)

        conn = mock_db()
        p1 = conn.execute('SELECT * FROM order_payouts WHERE id = ?', (payout_s1,)).fetchone()
        p2 = conn.execute('SELECT * FROM order_payouts WHERE id = ?', (payout_s2,)).fetchone()
        conn.close()

        assert p1['payout_recovery_status'] == 'manual_review'  # auto-recovery tried, got insufficient_funds
        assert p2['payout_status'] == 'PAYOUT_CANCELLED'         # cancelled (no transfer)
        assert p2['payout_recovery_status'] == 'not_needed'


# ──────────────────────────────────────────────────────────────────────────────
# RW-6: Duplicate-click / idempotency protection
# ──────────────────────────────────────────────────────────────────────────────

class TestDuplicateRefundProtection:

    def test_rw6_second_refund_blocked(self, mock_db):
        """RW-6: Second call to refund_buyer_stripe is blocked (idempotency guard)."""
        from core.services.ledger.escrow_control import refund_buyer_stripe
        from core.services.ledger.exceptions import EscrowControlError

        order_id, ledger_id = _seed_paid_order(mock_db, total=100.00)
        _seed_payout(mock_db, order_id, ledger_id)

        mock_refund = _mock_stripe_refund('re_first')
        with patch('stripe.Refund.create', return_value=mock_refund):
            first = refund_buyer_stripe(order_id, admin_id=4)
        assert first['refund_id'] == 're_first'

        # Second call must raise
        with pytest.raises(EscrowControlError, match='already fully refunded'):
            refund_buyer_stripe(order_id, admin_id=4)

        # Stripe.Refund.create should only have been called once
        conn = mock_db()
        order = conn.execute('SELECT refund_status, stripe_refund_id FROM orders WHERE id = ?',
                             (order_id,)).fetchone()
        conn.close()
        assert order['refund_status'] == 'refunded'
        assert order['stripe_refund_id'] == 're_first'

    def test_rw6b_recovery_already_recovered_is_noop(self, mock_db):
        """RW-6b: Calling attempt_payout_recovery on an already-recovered payout is a no-op."""
        from core.services.ledger.escrow_control import attempt_payout_recovery

        order_id, ledger_id = _seed_paid_order(mock_db, total=100.00)
        payout_id = _seed_payout(
            mock_db, order_id, ledger_id,
            payout_status='PAID_OUT',
            transfer_id='tr_done',
            recovery_status='recovered',
        )

        # Override recovery status directly
        conn = mock_db()
        conn.execute(
            "UPDATE order_payouts SET payout_recovery_status='recovered' WHERE id=?",
            (payout_id,)
        )
        conn.commit()
        conn.close()

        with patch('stripe.Transfer.create_reversal') as mock_rev:
            result = attempt_payout_recovery(payout_id, admin_id=4)

        # No Stripe call should be made
        mock_rev.assert_not_called()
        assert result['outcome'] == 'recovered'


# ──────────────────────────────────────────────────────────────────────────────
# RW-7: Refund blocked when payment_status != 'paid'
# ──────────────────────────────────────────────────────────────────────────────

class TestRefundEligibilityGuards:

    def test_rw7_refund_blocked_when_not_paid(self, mock_db):
        """RW-7: refund_buyer_stripe raises when payment_status is 'unpaid'."""
        from core.services.ledger.escrow_control import refund_buyer_stripe
        from core.services.ledger.exceptions import EscrowControlError

        order_id, ledger_id = _seed_paid_order(mock_db, total=100.00)
        # Revert payment status
        conn = mock_db()
        conn.execute("UPDATE orders SET payment_status='unpaid' WHERE id=?", (order_id,))
        conn.commit()
        conn.close()

        with pytest.raises(EscrowControlError, match="payment_status"):
            refund_buyer_stripe(order_id, admin_id=4)

    def test_rw7b_refund_blocked_when_no_stripe_pi(self, mock_db):
        """RW-7b: refund_buyer_stripe raises when no stripe_payment_intent_id."""
        from core.services.ledger.escrow_control import refund_buyer_stripe
        from core.services.ledger.exceptions import EscrowControlError

        order_id, ledger_id = _seed_paid_order(mock_db, total=100.00, pi_id=None)

        with pytest.raises(EscrowControlError, match="no Stripe payment"):
            refund_buyer_stripe(order_id, admin_id=4)

    def test_rw7c_partial_refund_blocked_when_payout_paid_out(self, mock_db):
        """RW-7c: process_refund raises if affected payout is already PAID_OUT."""
        from core.services.ledger.escrow_control import process_refund
        from core.services.ledger.exceptions import EscrowControlError

        order_id, ledger_id = _seed_paid_order(mock_db, total=200.00)
        _seed_payout(
            mock_db, order_id, ledger_id, seller_id=2, net=190.00,
            payout_status='PAID_OUT', transfer_id='tr_out',
        )
        _seed_item_ledger(mock_db, order_id, ledger_id, seller_id=2)

        with pytest.raises(EscrowControlError, match="PAID_OUT"):
            process_refund(
                order_id=order_id, admin_id=4,
                refund_type='full', reason='Full refund test',
            )


# ──────────────────────────────────────────────────────────────────────────────
# RW-8 / RW-9: refund-preview endpoint
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def app_client(mock_db):
    """Flask test client with session patched for admin access."""
    from core import create_app

    application = create_app({'TESTING': True, 'WTF_CSRF_ENABLED': False,
                               'SECRET_KEY': 'testkey'})
    with application.test_client() as client:
        with application.test_request_context():
            with client.session_transaction() as sess:
                sess['user_id'] = 4       # admin user seeded in test_db
                sess['username'] = 'admin1'
                sess['is_admin'] = True
        yield client


class TestRefundPreviewEndpoint:

    def test_rw8_preview_eligible_order(self, mock_db, app_client):
        """RW-8: refund-preview returns correct data for a paid, unrefunded order."""
        order_id, ledger_id = _seed_paid_order(mock_db, total=200.00,
                                               buyer_card_fee=6.28)
        _seed_payout(mock_db, order_id, ledger_id, seller_id=2, net=190.00)

        with app_client.session_transaction() as sess:
            sess['user_id'] = 4
            sess['is_admin'] = True

        resp = app_client.get(f'/admin/api/orders/{order_id}/refund-preview')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['can_refund'] is True
        assert data['block_reason'] is None
        assert data['refundable_amount'] == 200.00
        assert data['already_refunded'] == 0.0
        assert data['requires_recovery'] is False
        assert data['order']['buyer_username'] == 'buyer1'
        assert len(data['payouts']) == 1
        assert data['payouts'][0]['seller_username'] == 'seller1'

    def test_rw9_preview_already_refunded(self, mock_db, app_client):
        """RW-9: refund-preview returns can_refund=False when already refunded."""
        order_id, ledger_id = _seed_paid_order(mock_db, total=200.00)

        # Mark as already refunded
        conn = mock_db()
        conn.execute(
            "UPDATE orders SET refund_status='refunded', refund_amount=200.0, "
            "stripe_refund_id='re_already' WHERE id=?",
            (order_id,)
        )
        conn.commit()
        conn.close()

        with app_client.session_transaction() as sess:
            sess['user_id'] = 4
            sess['is_admin'] = True

        resp = app_client.get(f'/admin/api/orders/{order_id}/refund-preview')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['can_refund'] is False
        assert 'refunded' in (data['block_reason'] or '')

    def test_rw8b_preview_with_paid_out_payout_shows_recovery_needed(self, mock_db, app_client):
        """RW-8b: Preview correctly flags requires_recovery=True for PAID_OUT payout."""
        order_id, ledger_id = _seed_paid_order(mock_db, total=200.00)
        _seed_payout(
            mock_db, order_id, ledger_id, seller_id=2, net=190.00,
            payout_status='PAID_OUT', transfer_id='tr_out_preview',
        )

        with app_client.session_transaction() as sess:
            sess['user_id'] = 4
            sess['is_admin'] = True

        resp = app_client.get(f'/admin/api/orders/{order_id}/refund-preview')
        data = resp.get_json()
        assert data['success'] is True
        assert data['can_refund'] is True
        assert data['requires_recovery'] is True
        assert data['paid_out_payout_count'] == 1
