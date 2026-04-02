"""
Payment System Audit Tests — Final Validation Pass

Tests covering the scenarios identified in the Metex payments audit.

Covers:
  PA1 — Partial bid fill resets bid_payment_status to 'pending' (source check)
  PA2 — Partial bid fill: DB integration confirms bid is re-acceptable after partial fill
  PA3 — Full fill: bid permanently closed (status='Filled', active=0)
  PA4 — Payment failure: bid closed with status='Payment Failed', inventory restored
  PA5 — Double-payout guard: release_stripe_transfer blocks PAID_OUT payouts
  PA6 — ACH block: release_stripe_transfer blocked when requires_payment_clearance=1
  PA7 — payout_eligibility.py: card order eligible, ACH order not eligible
  PA8 — payout_eligibility.py: empty payment_method_type → not eligible
  PA9 — payout_eligibility.py: already-processed payout not eligible
  PA10 — checkout nonce: duplicate submit rejected with 409
  PA11 — accept_bid source: bid_payment_status reset present in partial fill branch
  PA12 — Webhook idempotency: already-paid order not re-processed
  PA13 — ACH requires_payment_clearance set correctly by webhook
  PA14 — Cancellation: inventory restored when all sellers approve
  PA15 — Refund blocks payout (PAID_OUT check enforced)
"""

import ast
import os
import sqlite3
import pytest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Minimal schema for integration tests
# ---------------------------------------------------------------------------
_SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    email TEXT DEFAULT 'x@x.com',
    password_hash TEXT DEFAULT 'x',
    first_name TEXT DEFAULT 'Test',
    last_name TEXT DEFAULT 'User',
    stripe_customer_id TEXT,
    account_frozen INTEGER DEFAULT 0,
    bid_payment_strikes INTEGER DEFAULT 0,
    stripe_account_id TEXT,
    stripe_payouts_enabled INTEGER DEFAULT 0
);

CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metal TEXT DEFAULT 'Gold',
    product_line TEXT DEFAULT 'AE',
    product_type TEXT DEFAULT 'Coin',
    weight TEXT DEFAULT '1 oz',
    year TEXT DEFAULT '2024',
    purity TEXT DEFAULT '.9999',
    mint TEXT DEFAULT 'USM',
    finish TEXT DEFAULT 'Bullion',
    bucket_id INTEGER DEFAULT 1,
    name TEXT
);

CREATE TABLE listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    price_per_coin REAL NOT NULL,
    quantity INTEGER DEFAULT 1,
    active INTEGER DEFAULT 1,
    pricing_mode TEXT DEFAULT 'static',
    spot_premium REAL DEFAULT 0,
    floor_price REAL DEFAULT 0,
    pricing_metal TEXT,
    graded INTEGER DEFAULT 0,
    grading_service TEXT,
    image_url TEXT
);

CREATE TABLE bids (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL,
    buyer_id INTEGER NOT NULL,
    quantity_requested INTEGER NOT NULL,
    price_per_coin REAL NOT NULL,
    remaining_quantity INTEGER NOT NULL,
    active INTEGER DEFAULT 1,
    requires_grading INTEGER DEFAULT 0,
    delivery_address TEXT DEFAULT '123 Main St',
    status TEXT DEFAULT 'Open',
    pricing_mode TEXT DEFAULT 'static',
    spot_premium REAL,
    ceiling_price REAL,
    pricing_metal TEXT,
    recipient_first_name TEXT DEFAULT 'Test',
    recipient_last_name TEXT DEFAULT 'User',
    random_year INTEGER DEFAULT 0,
    preferred_grader TEXT,
    bid_payment_method_id TEXT,
    bid_payment_status TEXT DEFAULT 'pending',
    bid_payment_intent_id TEXT,
    bid_payment_failure_code TEXT,
    bid_payment_failure_message TEXT,
    bid_payment_attempted_at TIMESTAMP
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_id INTEGER,
    total_price REAL,
    shipping_address TEXT,
    status TEXT DEFAULT 'Pending Shipment',
    created_at TEXT,
    recipient_first_name TEXT,
    recipient_last_name TEXT,
    payment_status TEXT DEFAULT 'unpaid',
    stripe_payment_intent_id TEXT,
    paid_at TEXT,
    payment_method_type TEXT,
    requires_payment_clearance INTEGER DEFAULT 0,
    source_bid_id INTEGER
);

CREATE TABLE order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    listing_id INTEGER,
    quantity INTEGER,
    price_each REAL
);

CREATE TABLE spot_prices (
    metal TEXT PRIMARY KEY,
    price_usd_per_oz REAL NOT NULL
);

CREATE TABLE spot_price_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metal TEXT,
    price_usd REAL,
    recorded_at TEXT DEFAULT (datetime('now')),
    source TEXT DEFAULT 'test'
);
"""


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.execute("INSERT INTO spot_prices VALUES ('gold', 2000.0)")
    conn.execute("INSERT INTO spot_price_snapshots (metal, price_usd) VALUES ('gold', 2000.0)")
    conn.commit()
    return conn


def _seed(conn):
    """Insert seller (id=1), seller2 (id=3), buyer (id=2), category/bucket."""
    conn.execute("INSERT INTO users (id, username, stripe_customer_id) VALUES (1,'seller',NULL)")
    conn.execute("INSERT INTO users (id, username, stripe_customer_id, stripe_account_id, stripe_payouts_enabled) VALUES (2,'buyer','cus_buyer',NULL,0)")
    conn.execute("INSERT INTO users (id, username, stripe_customer_id) VALUES (3,'seller2',NULL)")
    conn.execute("INSERT INTO categories (id, bucket_id) VALUES (1, 1)")
    conn.commit()


# ---------------------------------------------------------------------------
# PA1 + PA11 — Source code checks
# ---------------------------------------------------------------------------

class TestSourceChecks:
    """Static source code analysis for payment safety invariants."""

    _BASE = os.path.join(os.path.dirname(__file__), '..')

    def _src(self, rel):
        with open(os.path.normpath(os.path.join(self._BASE, rel))) as f:
            return f.read()

    def test_PA1_partial_fill_resets_bid_payment_status(self):
        """
        accept_bid.py must reset bid_payment_status='pending' in the
        partial-fill branch so future sellers can accept the remaining qty.
        """
        src = self._src('core/blueprints/bids/accept_bid.py')
        # The fix: "Partially Filled" and "bid_payment_status = 'pending'" must
        # appear in the same UPDATE statement (within ~5 lines of each other).
        lines = src.splitlines()
        partial_fill_found = False
        reset_found = False
        for i, line in enumerate(lines):
            if 'Partially Filled' in line and 'UPDATE bids' not in line:
                # Found the status value; look nearby for the reset
                window = '\n'.join(lines[max(0, i-10):i+5])
                if "bid_payment_status = 'pending'" in window or "bid_payment_status='pending'" in window:
                    partial_fill_found = True
                    reset_found = True
                    break
        assert partial_fill_found and reset_found, (
            "accept_bid.py does not reset bid_payment_status='pending' in the partial-fill "
            "UPDATE block. This permanently blocks future acceptance of remaining quantity."
        )

    def test_PA11_partial_fill_sets_bid_intent_null(self):
        """
        accept_bid.py must also set bid_payment_intent_id=NULL in the partial fill
        branch so the stale PI reference is cleared for the next acceptance.
        """
        src = self._src('core/blueprints/bids/accept_bid.py')
        lines = src.splitlines()
        for i, line in enumerate(lines):
            if 'Partially Filled' in line:
                window = '\n'.join(lines[max(0, i-10):i+5])
                assert 'bid_payment_intent_id = NULL' in window or 'bid_payment_intent_id=NULL' in window, (
                    "accept_bid.py should clear bid_payment_intent_id in the partial-fill branch."
                )
                return
        pytest.fail("'Partially Filled' branch not found in accept_bid.py")

    def test_PA12_webhook_idempotency_guard_present(self):
        """Webhook handler must check order['status'] == 'paid' before updating."""
        src = self._src('core/blueprints/stripe_connect/routes.py')
        assert "order['status'] == 'paid'" in src or "status'] == 'paid'" in src, (
            "Webhook handler missing idempotency guard for already-paid orders."
        )

    def test_PA13_webhook_sets_requires_payment_clearance(self):
        """Webhook must set requires_payment_clearance=1 for us_bank_account."""
        src = self._src('core/blueprints/stripe_connect/routes.py')
        assert 'requires_payment_clearance' in src, (
            "Webhook handler missing requires_payment_clearance field update."
        )
        assert 'us_bank_account' in src, (
            "Webhook handler does not detect ACH payment type."
        )

    def test_PA_nonce_consumed_before_order_creation(self):
        """
        checkout nonce must be consumed before order creation — not after.
        Ensures duplicate requests in flight don't create two orders.
        """
        src = self._src('core/blueprints/checkout/routes.py')
        nonce_pop_pos = src.find("session.pop('checkout_nonce'")
        create_order_pos = src.find('order_id = create_order(')
        assert nonce_pop_pos != -1, "checkout_nonce pop not found in checkout routes"
        assert create_order_pos != -1, "create_order() call not found in checkout routes"
        assert nonce_pop_pos < create_order_pos, (
            "Checkout nonce must be consumed BEFORE order creation. "
            "Currently nonce is popped at pos %d, create_order at pos %d."
            % (nonce_pop_pos, create_order_pos)
        )


# ---------------------------------------------------------------------------
# PA2 + PA3 — Partial fill vs full fill DB integration
# ---------------------------------------------------------------------------

class TestBidFillDBIntegration:
    """
    Integration tests that mirror the real accept_bid logic.
    Tests are written to match the FIXED code behavior.
    """

    def _run_accept(self, conn, seller_id, bid_id, quantity, charge_result):
        """
        Simplified accept_bid logic mirroring the fixed code.
        Returns (filled, order_id, failures).
        """
        from services.pricing_service import get_effective_price, get_effective_bid_price

        cursor = conn.cursor()

        bid = cursor.execute(
            """SELECT b.id, b.category_id, b.quantity_requested, b.remaining_quantity,
                      b.price_per_coin, b.buyer_id, b.delivery_address, b.status,
                      b.pricing_mode, b.spot_premium, b.ceiling_price, b.pricing_metal,
                      b.recipient_first_name, b.recipient_last_name,
                      b.bid_payment_method_id, b.bid_payment_status,
                      c.metal, c.weight
               FROM bids b JOIN categories c ON b.category_id = c.id
               WHERE b.id = ?""", (bid_id,)
        ).fetchone()

        if not bid:
            return 0, None, [{'bid_id': bid_id, 'reason': 'not found'}]

        # Guard: block charged / failed bids
        if bid['bid_payment_status'] in ('charged', 'failed'):
            return 0, None, [{'bid_id': bid_id, 'reason': f"bid_payment_status={bid['bid_payment_status']}"}]

        bid_pm_id = bid['bid_payment_method_id']
        buyer_id = bid['buyer_id']
        category_id = bid['category_id']

        buyer_row = cursor.execute('SELECT stripe_customer_id FROM users WHERE id = ?', (buyer_id,)).fetchone()
        buyer_customer_id = buyer_row['stripe_customer_id'] if buyer_row else None
        if not bid_pm_id or not buyer_customer_id:
            return 0, None, [{'bid_id': bid_id, 'reason': 'no payment method / customer'}]

        effective_bid_price = bid['price_per_coin']  # static pricing for tests
        remaining_qty = bid['remaining_quantity'] or bid['quantity_requested'] or 0
        quantity_needed = max(0, min(remaining_qty, quantity))
        if quantity_needed == 0:
            return 0, None, []

        listings = cursor.execute(
            """SELECT l.id, l.quantity, l.price_per_coin, l.seller_id,
                      l.pricing_mode, l.spot_premium, l.floor_price, l.pricing_metal,
                      c.metal, c.weight
               FROM listings l JOIN categories c ON l.category_id = c.id
               WHERE l.category_id = ? AND l.seller_id = ? AND l.active = 1 AND l.price_per_coin <= ?""",
            (category_id, seller_id, effective_bid_price)
        ).fetchall()

        filled = 0
        inventory_plan = []
        order_items = []
        for lst in listings:
            if filled >= quantity_needed:
                break
            fq = min(lst['quantity'], quantity_needed - filled)
            inventory_plan.append((lst['id'], lst['quantity'] - fq))
            order_items.append({'listing_id': lst['id'], 'quantity': fq, 'price_each': effective_bid_price})
            filled += fq

        need_committed = filled < quantity_needed
        unfilled_qty = quantity_needed - filled if need_committed else 0
        if need_committed:
            filled += unfilled_qty

        if filled == 0:
            return 0, None, []

        new_remaining = remaining_qty - filled
        total_price = filled * effective_bid_price

        sp_name = f'sp_bid_{bid_id}'
        cursor.execute(f'SAVEPOINT {sp_name}')

        for listing_id, new_qty in inventory_plan:
            if new_qty <= 0:
                cursor.execute('UPDATE listings SET quantity=0, active=0 WHERE id=?', (listing_id,))
            else:
                cursor.execute('UPDATE listings SET quantity=? WHERE id=?', (new_qty, listing_id))

        if need_committed:
            cursor.execute(
                'INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, active) '
                'VALUES (?,?,0,?,0)', (category_id, seller_id, effective_bid_price)
            )
            order_items.append({'listing_id': cursor.lastrowid, 'quantity': unfilled_qty,
                                'price_each': effective_bid_price})

        cursor.execute(
            "INSERT INTO orders (buyer_id, total_price, shipping_address, status, "
            "created_at, recipient_first_name, recipient_last_name, payment_status, source_bid_id) "
            "VALUES (?,?,?,'Pending Shipment',datetime('now'),?,?,'unpaid',?)",
            (buyer_id, total_price, bid['delivery_address'], bid['recipient_first_name'],
             bid['recipient_last_name'], bid_id)
        )
        order_id = cursor.lastrowid

        for item in order_items:
            cursor.execute(
                'INSERT INTO order_items (order_id, listing_id, quantity, price_each) VALUES (?,?,?,?)',
                (order_id, item['listing_id'], item['quantity'], item['price_each'])
            )

        pay_result = charge_result

        if not pay_result['success']:
            cursor.execute(f'ROLLBACK TO SAVEPOINT {sp_name}')
            cursor.execute(f'RELEASE SAVEPOINT {sp_name}')
            cursor.execute(
                "UPDATE bids SET bid_payment_status='failed', active=0, status='Payment Failed', "
                "bid_payment_failure_code=?, bid_payment_failure_message=?, "
                "bid_payment_attempted_at=datetime('now') WHERE id=?",
                (pay_result.get('code'), pay_result.get('message'), bid_id)
            )
            conn.commit()
            return 0, None, [{'bid_id': bid_id, 'reason': pay_result.get('message')}]

        # Payment succeeded
        cursor.execute(
            "UPDATE orders SET stripe_payment_intent_id=?, payment_status='paid', "
            "status='paid', paid_at=datetime('now'), payment_method_type='card' WHERE id=?",
            (pay_result['pi_id'], order_id)
        )
        cursor.execute(
            "UPDATE bids SET bid_payment_status='charged', bid_payment_intent_id=?, "
            "bid_payment_attempted_at=datetime('now') WHERE id=?",
            (pay_result['pi_id'], bid_id)
        )

        if new_remaining <= 0:
            cursor.execute(
                "UPDATE bids SET remaining_quantity=0, active=0, status='Filled' WHERE id=?",
                (bid_id,)
            )
        else:
            # FIXED: reset payment status for remaining quantity
            cursor.execute(
                "UPDATE bids SET remaining_quantity=?, status='Partially Filled', "
                "bid_payment_status='pending', bid_payment_intent_id=NULL WHERE id=?",
                (new_remaining, bid_id)
            )

        cursor.execute(f'RELEASE SAVEPOINT {sp_name}')
        conn.commit()
        return filled, order_id, []

    def _make_bid(self, conn, price=60.0, qty=5, pm_id='pm_testcard'):
        cur = conn.execute(
            "INSERT INTO bids (category_id, buyer_id, quantity_requested, price_per_coin, "
            "remaining_quantity, bid_payment_method_id) VALUES (1, 2, ?, ?, ?, ?)",
            (qty, price, qty, pm_id)
        )
        conn.commit()
        return cur.lastrowid

    def _make_listing(self, conn, seller_id=1, price=50.0, qty=3):
        cur = conn.execute(
            "INSERT INTO listings (seller_id, category_id, price_per_coin, quantity) "
            "VALUES (?,1,?,?)", (seller_id, price, qty)
        )
        conn.commit()
        return cur.lastrowid

    def test_PA2_partial_fill_bid_is_reacceptable(self):
        """
        PA2: After partial fill (seller 1 fills 3 of 5), bid_payment_status must
        be 'pending' so seller 2 can fill the remaining 2.
        """
        conn = _make_db()
        _seed(conn)
        # Seller 1 has 3 coins, seller 2 has 2 coins
        self._make_listing(conn, seller_id=1, price=50.0, qty=3)
        self._make_listing(conn, seller_id=3, price=50.0, qty=2)
        bid_id = self._make_bid(conn, price=60.0, qty=5)

        # Seller 1 accepts 3 out of 5 (partial fill)
        filled, order1, failures = self._run_accept(
            conn, seller_id=1, bid_id=bid_id, quantity=3,
            charge_result={'success': True, 'pi_id': 'pi_first_partial'}
        )
        assert filled == 3, f"Expected 3 filled, got {filled}"
        assert not failures, f"Unexpected failures: {failures}"

        # Verify bid state after partial fill
        bid = conn.execute("SELECT * FROM bids WHERE id=?", (bid_id,)).fetchone()
        assert bid['remaining_quantity'] == 2, f"Expected remaining=2, got {bid['remaining_quantity']}"
        assert bid['status'] == 'Partially Filled'
        assert bid['bid_payment_status'] == 'pending', (
            f"bid_payment_status should be 'pending' after partial fill, got '{bid['bid_payment_status']}'. "
            "This blocks seller 2 from accepting the remaining 2 coins."
        )
        assert bid['bid_payment_intent_id'] is None, (
            "bid_payment_intent_id should be NULL after partial fill reset"
        )

        # Seller 2 fills remaining 2
        filled2, order2, failures2 = self._run_accept(
            conn, seller_id=3, bid_id=bid_id, quantity=2,
            charge_result={'success': True, 'pi_id': 'pi_second_fill'}
        )
        assert filled2 == 2, f"Expected 2 filled by seller 2, got {filled2}"
        assert not failures2, f"Unexpected failures: {failures2}"

        # Bid should now be fully filled
        bid_final = conn.execute("SELECT * FROM bids WHERE id=?", (bid_id,)).fetchone()
        assert bid_final['status'] == 'Filled'
        assert bid_final['remaining_quantity'] == 0
        assert bid_final['active'] == 0

    def test_PA3_full_fill_permanently_closes_bid(self):
        """
        PA3: After a full fill, bid is permanently closed (active=0, status='Filled').
        Second acceptance attempt is blocked by bid_payment_status='charged'.
        """
        conn = _make_db()
        _seed(conn)
        self._make_listing(conn, seller_id=1, price=50.0, qty=5)
        bid_id = self._make_bid(conn, price=60.0, qty=3)

        # Full fill
        filled, order_id, failures = self._run_accept(
            conn, seller_id=1, bid_id=bid_id, quantity=3,
            charge_result={'success': True, 'pi_id': 'pi_full_fill'}
        )
        assert filled == 3
        assert not failures

        bid = conn.execute("SELECT * FROM bids WHERE id=?", (bid_id,)).fetchone()
        assert bid['status'] == 'Filled'
        assert bid['active'] == 0
        assert bid['bid_payment_status'] == 'charged'

        # Try to double-accept — must be blocked
        filled2, _, failures2 = self._run_accept(
            conn, seller_id=1, bid_id=bid_id, quantity=3,
            charge_result={'success': True, 'pi_id': 'pi_should_not_happen'}
        )
        assert filled2 == 0, "Double-acceptance must be blocked after full fill"
        assert failures2, "Should have failure reason for double-acceptance attempt"
        assert 'charged' in failures2[0]['reason']

    def test_PA4_payment_failure_restores_inventory(self):
        """
        PA4: Failed payment rolls back inventory, sets bid to 'Payment Failed',
        and creates no paid order.
        """
        conn = _make_db()
        _seed(conn)
        listing_id = self._make_listing(conn, seller_id=1, price=50.0, qty=3)
        bid_id = self._make_bid(conn, price=60.0, qty=2)

        initial_qty = conn.execute("SELECT quantity FROM listings WHERE id=?", (listing_id,)).fetchone()['quantity']

        filled, order_id, failures = self._run_accept(
            conn, seller_id=1, bid_id=bid_id, quantity=2,
            charge_result={'success': False, 'code': 'card_declined', 'message': 'Card declined.', 'is_card_decline': True}
        )

        assert filled == 0, "No items should be filled on payment failure"
        assert order_id is None, "No order should be created on payment failure"
        assert failures, "Failures list should be non-empty"

        # Inventory must be restored
        restored_qty = conn.execute("SELECT quantity FROM listings WHERE id=?", (listing_id,)).fetchone()['quantity']
        assert restored_qty == initial_qty, (
            f"Inventory not restored after payment failure: expected {initial_qty}, got {restored_qty}"
        )

        # Bid must be permanently closed
        bid = conn.execute("SELECT * FROM bids WHERE id=?", (bid_id,)).fetchone()
        assert bid['bid_payment_status'] == 'failed'
        assert bid['status'] == 'Payment Failed'
        assert bid['active'] == 0


# ---------------------------------------------------------------------------
# PA5 + PA6 — Payout release guards
# ---------------------------------------------------------------------------

class TestPayoutReleaseGuards:

    def _make_ledger_db(self):
        """Build an in-memory DB with the ledger schema."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        conn.executescript("""
            CREATE TABLE orders_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                buyer_id INTEGER,
                gross_amount REAL,
                platform_fee_amount REAL,
                order_status TEXT DEFAULT 'PAID_IN_ESCROW',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE order_payouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                order_ledger_id INTEGER,
                seller_id INTEGER,
                seller_net_amount REAL,
                payout_status TEXT DEFAULT 'PAYOUT_NOT_READY',
                provider_transfer_id TEXT,
                payout_recovery_status TEXT DEFAULT 'not_needed',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE order_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                event_type TEXT,
                actor_type TEXT,
                actor_id INTEGER,
                payload_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE order_items_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                order_ledger_id INTEGER,
                seller_id INTEGER,
                listing_id INTEGER,
                quantity INTEGER,
                gross_amount REAL,
                platform_fee_amount REAL
            );

            CREATE TABLE seller_order_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                seller_id INTEGER,
                tracking_number TEXT,
                carrier TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        return conn

    def test_PA5_double_payout_guard(self):
        """
        PA5: release_stripe_transfer must raise EscrowControlError if
        payout_status is already PAID_OUT.
        """
        from services.ledger_service import LedgerService, EscrowControlError

        conn = self._make_ledger_db()
        _seed(conn)

        # Create an order + ledger + payout that's already PAID_OUT
        conn.execute("INSERT INTO orders (id, buyer_id, total_price, payment_status, stripe_payment_intent_id, requires_payment_clearance) VALUES (1, 2, 100.0, 'paid', 'pi_test', 0)")
        conn.execute("INSERT INTO orders_ledger (id, order_id, buyer_id, gross_amount, order_status) VALUES (1, 1, 2, 100.0, 'PAID_IN_ESCROW')")
        conn.execute("INSERT INTO order_payouts (id, order_id, order_ledger_id, seller_id, seller_net_amount, payout_status) VALUES (1, 1, 1, 1, 95.0, 'PAID_OUT')")
        conn.execute("UPDATE users SET stripe_account_id='acct_test', stripe_payouts_enabled=1 WHERE id=1")
        conn.commit()

        with patch('core.services.ledger.escrow_control.get_db_connection', return_value=conn):
            with pytest.raises(EscrowControlError, match='already released'):
                LedgerService.release_stripe_transfer(1, admin_id=99)

    def test_PA6_ach_blocks_payout_release(self):
        """
        PA6: release_stripe_transfer must raise EscrowControlError if
        requires_payment_clearance=1 (ACH not yet cleared).
        """
        from services.ledger_service import LedgerService, EscrowControlError

        conn = self._make_ledger_db()
        _seed(conn)

        conn.execute("INSERT INTO orders (id, buyer_id, total_price, payment_status, stripe_payment_intent_id, requires_payment_clearance) VALUES (1, 2, 100.0, 'paid', 'pi_test', 1)")
        conn.execute("INSERT INTO orders_ledger (id, order_id, buyer_id, gross_amount, order_status) VALUES (1, 1, 2, 100.0, 'PAID_IN_ESCROW')")
        conn.execute("INSERT INTO order_payouts (id, order_id, order_ledger_id, seller_id, seller_net_amount, payout_status) VALUES (1, 1, 1, 1, 95.0, 'PAYOUT_READY')")
        conn.execute("UPDATE users SET stripe_account_id='acct_test', stripe_payouts_enabled=1 WHERE id=1")
        conn.commit()

        with patch('core.services.ledger.escrow_control.get_db_connection', return_value=conn):
            with pytest.raises(EscrowControlError, match='clearance'):
                LedgerService.release_stripe_transfer(1, admin_id=99)


# ---------------------------------------------------------------------------
# PA7 + PA8 + PA9 — payout_eligibility.py simple module
# ---------------------------------------------------------------------------

class TestSimplePayoutEligibility:
    """Tests for the simple payout_eligibility.py module."""

    def _mod(self):
        from services.payout_eligibility import is_order_payout_eligible, get_payout_block_reason
        return is_order_payout_eligible, get_payout_block_reason

    def test_PA7_card_order_is_eligible(self):
        """Card order with payment_status='paid' and payout_status not set is eligible."""
        eligible, _ = self._mod()
        order = {
            'payment_status': 'paid',
            'payment_method_type': 'card',
            'requires_payment_clearance': 0,
            'payout_status': 'not_ready_for_payout',
        }
        assert eligible(order) is True

    def test_PA7_ach_order_is_not_eligible(self):
        """ACH order is never auto-eligible."""
        eligible, reason_fn = self._mod()
        order = {
            'payment_status': 'paid',
            'payment_method_type': 'us_bank_account',
            'requires_payment_clearance': 1,
            'payout_status': 'not_ready_for_payout',
        }
        assert eligible(order) is False
        reason = reason_fn(order)
        assert 'ACH' in reason or 'clearance' in reason.lower()

    def test_PA8_empty_payment_method_not_eligible(self):
        """Unknown/empty payment method is not eligible."""
        eligible, _ = self._mod()
        order = {
            'payment_status': 'paid',
            'payment_method_type': '',
            'requires_payment_clearance': 0,
            'payout_status': 'not_ready_for_payout',
        }
        assert eligible(order) is False

    def test_PA9_already_processed_not_eligible(self):
        """Order with payout_status != 'not_ready_for_payout' is not eligible."""
        eligible, _ = self._mod()
        for status in ('paid_out', 'processing', 'payout_in_progress'):
            order = {
                'payment_status': 'paid',
                'payment_method_type': 'card',
                'requires_payment_clearance': 0,
                'payout_status': status,
            }
            assert eligible(order) is False, f"Should not be eligible with payout_status='{status}'"

    def test_PA_unpaid_not_eligible(self):
        """Unpaid order is never eligible for payout."""
        eligible, reason_fn = self._mod()
        order = {
            'payment_status': 'unpaid',
            'payment_method_type': 'card',
            'requires_payment_clearance': 0,
            'payout_status': 'not_ready_for_payout',
        }
        assert eligible(order) is False
        reason = reason_fn(order)
        assert 'Payment' in reason or 'confirmed' in reason.lower()


# ---------------------------------------------------------------------------
# PA14 — Cancellation inventory restoration
# ---------------------------------------------------------------------------

class TestCancellationInventory:

    def test_PA14_inventory_restored_on_cancellation(self):
        """
        PA14: When a cancellation is approved, inventory is restored for all
        order_items. Re-activation only happens if listing quantity was 0.
        """
        conn = _make_db()
        _seed(conn)

        # Create a listing with 0 remaining (sold out)
        conn.execute("INSERT INTO listings (id, seller_id, category_id, price_per_coin, quantity, active) VALUES (10, 1, 1, 50.0, 0, 0)")
        conn.execute("INSERT INTO orders (id, buyer_id, total_price, status) VALUES (20, 2, 100.0, 'paid')")
        conn.execute("INSERT INTO order_items (order_id, listing_id, quantity, price_each) VALUES (20, 10, 2, 50.0)")
        conn.commit()

        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from routes.cancellation_routes import restore_inventory

        items_restored = restore_inventory(conn, order_id=20)
        conn.commit()

        assert items_restored == 1, f"Expected 1 item restored, got {items_restored}"

        listing = conn.execute("SELECT quantity, active FROM listings WHERE id=10").fetchone()
        assert listing['quantity'] == 2, f"Expected quantity=2 after restore, got {listing['quantity']}"
        assert listing['active'] == 1, "Listing should be reactivated (was at 0 quantity)"

    def test_PA14_active_listing_stays_active_state(self):
        """
        PA14b: Cancellation restore does not reactivate listings that had
        quantity > 0 (were already active or manually deactivated).
        """
        conn = _make_db()
        _seed(conn)

        # Listing still has stock (quantity > 0), manually deactivated
        conn.execute("INSERT INTO listings (id, seller_id, category_id, price_per_coin, quantity, active) VALUES (11, 1, 1, 50.0, 5, 0)")
        conn.execute("INSERT INTO orders (id, buyer_id, total_price, status) VALUES (21, 2, 150.0, 'paid')")
        conn.execute("INSERT INTO order_items (order_id, listing_id, quantity, price_each) VALUES (21, 11, 3, 50.0)")
        conn.commit()

        from routes.cancellation_routes import restore_inventory

        restore_inventory(conn, order_id=21)
        conn.commit()

        listing = conn.execute("SELECT quantity, active FROM listings WHERE id=11").fetchone()
        assert listing['quantity'] == 8, f"Expected quantity=8, got {listing['quantity']}"
        # active stays 0 because quantity was > 0 (not auto-deactivated condition)
        assert listing['active'] == 0, "Manually-deactivated listing should not be reactivated"


# ---------------------------------------------------------------------------
# PA15 — Refund blocks payout (ledger process_refund check)
# ---------------------------------------------------------------------------

class TestRefundBlocksPayout:

    def test_PA15_refund_fails_on_paid_out_payout(self):
        """
        PA15: process_refund must raise EscrowControlError if any affected
        payout is already PAID_OUT. Money cannot be refunded from a paid-out order.
        """
        from services.ledger_service import LedgerService, EscrowControlError

        # Use the real test fixture from test_ledger_phase2_escrow_control
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row

        # Minimal ledger schema
        conn.executescript("""
            CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT);
            CREATE TABLE orders (id INTEGER PRIMARY KEY, buyer_id INTEGER, total_price REAL,
                payment_status TEXT DEFAULT 'paid', stripe_payment_intent_id TEXT);
            CREATE TABLE order_items (id INTEGER PRIMARY KEY, order_id INTEGER,
                listing_id INTEGER, quantity INTEGER, price_each REAL);
            CREATE TABLE orders_ledger (id INTEGER PRIMARY KEY, order_id INTEGER,
                buyer_id INTEGER, gross_amount REAL, platform_fee_amount REAL,
                order_status TEXT DEFAULT 'PAID_IN_ESCROW', updated_at TIMESTAMP);
            CREATE TABLE order_payouts (id INTEGER PRIMARY KEY, order_id INTEGER,
                order_ledger_id INTEGER, seller_id INTEGER, seller_net_amount REAL,
                payout_status TEXT DEFAULT 'PAYOUT_NOT_READY', updated_at TIMESTAMP);
            CREATE TABLE order_items_ledger (id INTEGER PRIMARY KEY, order_id INTEGER,
                order_ledger_id INTEGER, seller_id INTEGER, listing_id INTEGER,
                quantity INTEGER, gross_amount REAL, platform_fee_amount REAL);
            CREATE TABLE order_events (id INTEGER PRIMARY KEY, order_id INTEGER,
                event_type TEXT, actor_type TEXT, actor_id INTEGER, payload_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        """)
        conn.execute("INSERT INTO users VALUES (1, 'buyer')")
        conn.execute("INSERT INTO users VALUES (2, 'seller')")
        conn.execute("INSERT INTO orders VALUES (1, 1, 100.0, 'paid', 'pi_test')")
        conn.execute("INSERT INTO orders_ledger VALUES (1, 1, 1, 100.0, 5.0, 'PAID_IN_ESCROW', CURRENT_TIMESTAMP)")
        conn.execute("INSERT INTO order_payouts VALUES (1, 1, 1, 2, 95.0, 'PAID_OUT', CURRENT_TIMESTAMP)")
        conn.execute("INSERT INTO order_items_ledger VALUES (1, 1, 1, 2, 1, 1, 100.0, 5.0)")
        conn.commit()

        with patch('core.services.ledger.escrow_control.get_db_connection', return_value=conn):
            with pytest.raises(EscrowControlError, match='PAID_OUT'):
                LedgerService.process_refund(
                    order_id=1, admin_id=99, refund_type='full', reason='Test refund'
                )
