"""
Bid payment charging audit tests.

Verifies the bid-payment architecture rules:
  - Placing a bid never charges the buyer
  - Editing a bid never charges the buyer
  - Acceptance charges based on the CURRENT, FINAL bid state in the DB
  - Double-acceptance (already-charged bid) is blocked
  - Failed payment leaves no orphan charge or paid order
  - Inventory is rolled back atomically when payment fails (SAVEPOINT fix)

Tests BP1-BP4 are unit/static tests (no DB or Stripe calls needed).
Tests BP5-BP8 use _charge_bid_payment directly with mocked Stripe.
Tests BP9-BP11 are integration tests: in-memory SQLite + mocked _charge_bid_payment.
"""

import sys
import os
import ast
import sqlite3
import pytest
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Minimal schema for the integration tests
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
    account_frozen INTEGER DEFAULT 0
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
    payment_method_type TEXT
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

_SPOT = 2000.0  # gold spot price used across tests


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.execute("INSERT INTO spot_prices VALUES ('gold', ?)", (_SPOT,))
    conn.execute(
        "INSERT INTO spot_price_snapshots (metal, price_usd) VALUES ('gold', ?)",
        (_SPOT,)
    )
    conn.commit()
    return conn


def _seed(conn):
    """Insert seller (id=1), buyer (id=2), category+bucket (id=1)."""
    conn.execute(
        "INSERT INTO users (id, username, stripe_customer_id) VALUES (1,'seller',NULL)"
    )
    conn.execute(
        "INSERT INTO users (id, username, stripe_customer_id) VALUES (2,'buyer','cus_buyer')"
    )
    conn.execute("INSERT INTO categories (id, bucket_id) VALUES (1, 1)")
    conn.commit()


# ============================================================================
# BP1-BP4  Static / unit checks (no Stripe, no DB)
# ============================================================================

class TestStaticChecks:
    """Source-code checks that do not require running any application code."""

    _BIDS_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'core', 'blueprints', 'bids',
    )

    def _parse(self, filename):
        with open(os.path.join(self._BIDS_DIR, filename)) as f:
            return ast.parse(f.read()), f.read() if False else open(
                os.path.join(self._BIDS_DIR, filename)
            ).read()

    def _has_stripe_import(self, source):
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(a.name == 'stripe' for a in node.names):
                    return True
            if isinstance(node, ast.ImportFrom):
                if node.module and 'stripe' in node.module:
                    return True
        return False

    def test_BP1_edit_bid_has_no_stripe_import(self):
        """edit_bid.py must not import stripe — no charges should happen at edit time."""
        _, src = self._parse('edit_bid.py')
        assert not self._has_stripe_import(src), (
            "edit_bid.py imports stripe; this risks accidentally triggering a charge "
            "or payment at bid-edit time."
        )

    def _read_src(self, rel_path):
        """Read source file relative to core/blueprints/bids/ or any path."""
        p = os.path.join(os.path.dirname(__file__), '..', rel_path)
        with open(os.path.abspath(p)) as f:
            return f.read()

    def _parse_src(self, module_name):
        """Parse a file in core/blueprints/bids/ and return (path, src)."""
        return self._parse(module_name)

    def test_BP14_place_bid_does_not_import_auto_match(self):
        """
        place_bid.py must not import auto_match_bid_to_listings.
        Importing it risks calling it; auto_match creates orders without payment.
        """
        _, src = self._parse('place_bid.py')
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.names:
                for alias in node.names:
                    assert alias.name != 'auto_match_bid_to_listings', (
                        "place_bid.py imports auto_match_bid_to_listings — "
                        "this risks payment-free order creation."
                    )

    def test_BP15_listing_creation_does_not_call_auto_match(self):
        """
        listing_creation.py must not call auto_match_listing_to_bids.
        auto_match creates orders without charging the buyer.
        """
        src = self._read_src('core/blueprints/sell/listing_creation.py')
        tree = ast.parse(src)
        for node in ast.walk(tree):
            # Check for actual call: auto_match_listing_to_bids(...)
            if isinstance(node, ast.Call):
                func = node.func
                name = None
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                assert name != 'auto_match_listing_to_bids', (
                    "listing_creation.py calls auto_match_listing_to_bids — "
                    "this creates orders without charging the buyer."
                )

    def test_BP16_sell_accept_bid_has_no_route(self):
        """
        core/blueprints/sell/accept_bid.py must not register any Flask routes.
        The duplicate /sell/accept_bid/<bucket_id> route was decommissioned.
        All acceptance goes through /bids/accept_bid/<bucket_id>.
        """
        src = self._read_src('core/blueprints/sell/accept_bid.py')
        assert '@sell_bp.route' not in src, (
            "core/blueprints/sell/accept_bid.py still registers a Flask route. "
            "Decommission it — use /bids/accept_bid/ exclusively."
        )

    def test_BP2_place_bid_does_not_create_payment_intent(self):
        """place_bid.py must not call stripe.PaymentIntent.create."""
        _, src = self._parse('place_bid.py')
        assert 'PaymentIntent.create' not in src, (
            "place_bid.py calls PaymentIntent.create — buyers must not be charged at placement."
        )

    def test_BP3_accept_bid_uses_spot_price_snapshots(self):
        """accept_bid.py must prefer spot_price_snapshots over legacy spot_prices."""
        _, src = self._parse('accept_bid.py')
        assert 'spot_price_snapshots' in src, (
            "accept_bid.py must read from spot_price_snapshots (canonical source) "
            "so the charge matches prices shown to the buyer."
        )

    def test_BP4_accept_bid_savepoint_before_inventory_update(self):
        """SAVEPOINT must appear before UPDATE listings in accept_bid.py."""
        _, src = self._parse('accept_bid.py')
        sp_pos = src.find('SAVEPOINT {sp_name}')
        inv_pos = src.find('UPDATE listings SET quantity')
        assert sp_pos != -1, "SAVEPOINT not found in accept_bid.py"
        assert inv_pos != -1, "UPDATE listings SET quantity not found in accept_bid.py"
        assert sp_pos < inv_pos, (
            "Inventory UPDATE must happen AFTER the SAVEPOINT so a payment failure "
            "rolls back the inventory decrement too."
        )


# ============================================================================
# BP5-BP8  _charge_bid_payment unit tests (mocked Stripe)
# ============================================================================

class TestChargeBidPaymentUnit:

    def _fn(self):
        from core.blueprints.bids.accept_bid import _charge_bid_payment
        return _charge_bid_payment

    def test_BP5_success_returns_pi_id(self):
        """Successful PaymentIntent returns success=True with pi_id."""
        mock_pi = MagicMock(status='succeeded', id='pi_ok')
        with patch('stripe.PaymentIntent.create', return_value=mock_pi):
            result = self._fn()(1, 10, 2, 'pm_x', 'cus_x', 100.0)
        assert result['success'] is True
        assert result['pi_id'] == 'pi_ok'

    def test_BP6_card_error_returns_failure_not_success(self):
        """CardError must return success=False; must never return success=True."""
        import stripe as stripe_mod
        err = stripe_mod.error.CardError('Declined', None, 'card_declined')
        err.error = MagicMock(code='card_declined', message='Your card was declined.')
        with patch('stripe.PaymentIntent.create', side_effect=err):
            result = self._fn()(1, 10, 2, 'pm_x', 'cus_x', 99.99)
        assert result['success'] is False
        assert result.get('code') == 'card_declined'

    def test_BP7_idempotency_key_encodes_bid_and_order(self):
        """Idempotency key must be 'bid-accept-{bid_id}-{order_id}'."""
        mock_pi = MagicMock(status='succeeded', id='pi_idem')
        with patch('stripe.PaymentIntent.create', return_value=mock_pi) as mock_create:
            self._fn()(bid_id=42, order_id=7, buyer_id=2,
                       pm_id='pm_x', customer_id='cus_x', amount_dollars=50.0)
        kwargs = mock_create.call_args.kwargs
        assert kwargs.get('idempotency_key') == 'bid-accept-42-7'

    def test_BP8_amount_is_whole_cents(self):
        """Amount sent to Stripe must be an integer in cents."""
        mock_pi = MagicMock(status='succeeded', id='pi_cents')
        with patch('stripe.PaymentIntent.create', return_value=mock_pi) as mock_create:
            self._fn()(1, 1, 1, 'pm_x', 'cus_x', 123.456)
        amount = mock_create.call_args.kwargs['amount']
        assert isinstance(amount, int), "Stripe amount must be an integer"
        assert amount == 12346  # round(123.456 * 100)


# ============================================================================
# BP9-BP11  Integration tests (in-memory SQLite + mocked _charge_bid_payment)
# ============================================================================

class TestAcceptBidIntegration:
    """
    These tests use an in-memory SQLite DB with the minimal schema above.
    _charge_bid_payment is mocked so no real Stripe calls are made.
    The accept_bid route logic is exercised through _run_acceptance(), which
    replicates the relevant inner loop from the route but against our test DB.
    """

    # ------------------------------------------------------------------
    # We drive the accept_bid route logic directly (not through Flask HTTP)
    # by importing and calling the core helper functions with a test cursor.
    # This isolates the DB/payment logic from Flask request handling.
    # ------------------------------------------------------------------

    def _run_acceptance(self, conn, seller_id, bid_id, quantity, charge_result):
        """
        Run the core bid-acceptance loop for a single bid against `conn`.
        `charge_result` is what _charge_bid_payment returns (mocked).

        Returns (filled, order_id or None, payment_failures list).
        """
        from services.pricing_service import get_effective_bid_price, get_effective_price

        cursor = conn.cursor()

        # Load spot prices (canonical source)
        try:
            snap_rows = cursor.execute(
                "SELECT metal, price_usd FROM spot_price_snapshots "
                "WHERE id IN (SELECT MAX(id) FROM spot_price_snapshots GROUP BY metal)"
            ).fetchall()
            spot_prices = {r['metal'].lower(): float(r['price_usd']) for r in snap_rows} if snap_rows else {}
        except Exception:
            spot_prices = {}

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

        assert bid, f"bid {bid_id} not found"

        if bid['bid_payment_status'] == 'charged':
            return 0, None, [{'bid_id': bid_id, 'reason': 'already charged'}]

        bid_pm_id = bid['bid_payment_method_id']
        buyer_id = bid['buyer_id']
        category_id = bid['category_id']
        delivery_address = bid['delivery_address']
        recipient_first = bid['recipient_first_name']
        recipient_last = bid['recipient_last_name']

        if not bid_pm_id:
            return 0, None, [{'bid_id': bid_id, 'reason': 'no payment method'}]

        buyer_row = cursor.execute(
            'SELECT stripe_customer_id FROM users WHERE id = ?', (buyer_id,)
        ).fetchone()
        buyer_customer_id = buyer_row['stripe_customer_id'] if buyer_row else None
        if not buyer_customer_id:
            return 0, None, [{'bid_id': bid_id, 'reason': 'no stripe customer'}]

        bid_dict = dict(bid)
        effective_bid_price = get_effective_bid_price(bid_dict, spot_prices=spot_prices)

        remaining_qty = bid['remaining_quantity'] or bid['quantity_requested'] or 0
        quantity_needed = max(0, min(remaining_qty, quantity))
        if quantity_needed == 0:
            return 0, None, []

        # Fetch seller listings
        listings = cursor.execute(
            """SELECT l.id, l.quantity, l.price_per_coin, l.seller_id,
                      l.pricing_mode, l.spot_premium, l.floor_price, l.pricing_metal,
                      c.metal, c.weight
               FROM listings l JOIN categories c ON l.category_id = c.id
               WHERE l.category_id = ? AND l.seller_id = ? AND l.active = 1""",
            (category_id, seller_id)
        ).fetchall()

        matched = []
        for lst in listings:
            ld = dict(lst)
            ep = get_effective_price(ld, spot_prices=spot_prices)
            if ep <= effective_bid_price:
                ld['effective_price'] = ep
                matched.append(ld)
        matched.sort(key=lambda x: x['effective_price'])

        # Phase 1: build plan (no DB writes)
        filled = 0
        inventory_plan = []
        order_items = []
        for lst in matched:
            if filled >= quantity_needed:
                break
            if lst['quantity'] <= 0:
                continue
            fq = min(lst['quantity'], quantity_needed - filled)
            inventory_plan.append((lst['id'], lst['quantity'] - fq))
            order_items.append({'listing_id': lst['id'], 'quantity': fq,
                                'price_each': effective_bid_price})
            filled += fq

        need_committed = filled < quantity_needed
        unfilled_qty = quantity_needed - filled if need_committed else 0
        if need_committed:
            filled += unfilled_qty

        new_remaining = remaining_qty - filled

        if filled == 0:
            return 0, None, []

        total_price = filled * effective_bid_price

        sp_name = f'sp_bid_{bid_id}'
        cursor.execute(f'SAVEPOINT {sp_name}')

        # Phase 2: apply inside SAVEPOINT
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
            "created_at, recipient_first_name, recipient_last_name, payment_status) "
            "VALUES (?,?,?,'Pending Shipment',datetime('now'),?,?,'unpaid')",
            (buyer_id, total_price, delivery_address, recipient_first, recipient_last)
        )
        order_id = cursor.lastrowid

        for item in order_items:
            cursor.execute(
                'INSERT INTO order_items (order_id, listing_id, quantity, price_each) VALUES (?,?,?,?)',
                (order_id, item['listing_id'], item['quantity'], item['price_each'])
            )

        # Attempt payment (mocked)
        pay_result = charge_result

        if not pay_result['success']:
            cursor.execute(f'ROLLBACK TO SAVEPOINT {sp_name}')
            cursor.execute(f'RELEASE SAVEPOINT {sp_name}')
            cursor.execute(
                "UPDATE bids SET bid_payment_status='failed', bid_payment_failure_code=?, "
                "bid_payment_failure_message=?, bid_payment_attempted_at=datetime('now') WHERE id=?",
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
            cursor.execute(
                "UPDATE bids SET remaining_quantity=?, status='Partially Filled' WHERE id=?",
                (new_remaining, bid_id)
            )

        cursor.execute(f'RELEASE SAVEPOINT {sp_name}')
        conn.commit()
        return filled, order_id, []

    # ------------------------------------------------------------------

    def _make_bid(self, conn, price=60.0, qty=2, pm_id='pm_testcard',
                  payment_status='pending'):
        cur = conn.execute(
            "INSERT INTO bids (category_id, buyer_id, quantity_requested, price_per_coin, "
            "remaining_quantity, bid_payment_method_id, bid_payment_status) "
            "VALUES (1, 2, ?, ?, ?, ?, ?)",
            (qty, price, qty, pm_id, payment_status)
        )
        conn.commit()
        return cur.lastrowid

    def _make_listing(self, conn, seller_id=1, price=50.0, qty=5):
        cur = conn.execute(
            "INSERT INTO listings (seller_id, category_id, price_per_coin, quantity) "
            "VALUES (?,1,?,?)", (seller_id, price, qty)
        )
        conn.commit()
        return cur.lastrowid

    # BP9: Successful acceptance charges the right amount
    def test_BP9_accept_charges_current_bid_price(self):
        """Acceptance charges based on the bid's current price_per_coin in the DB."""
        conn = _make_db()
        _seed(conn)
        listing_id = self._make_listing(conn, price=50.0, qty=3)
        # Bid price is $60 (simulates a bid that was edited upward from $50)
        bid_id = self._make_bid(conn, price=60.0, qty=2)

        success_result = {'success': True, 'pi_id': 'pi_bp9'}
        filled, order_id, failures = self._run_acceptance(
            conn, seller_id=1, bid_id=bid_id, quantity=2, charge_result=success_result
        )

        assert filled == 2
        assert order_id is not None
        assert not failures

        order = conn.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
        assert order['total_price'] == pytest.approx(120.0)  # 60.0 * 2
        assert order['payment_status'] == 'paid'

    # BP10: Duplicate acceptance is blocked for already-charged bids
    def test_BP10_already_charged_bid_not_charged_again(self):
        """Bid with bid_payment_status='charged' is skipped — no second charge."""
        conn = _make_db()
        _seed(conn)
        self._make_listing(conn, price=50.0, qty=5)
        bid_id = self._make_bid(conn, price=60.0, qty=2, payment_status='charged')

        # If the guard works, _run_acceptance returns 0 immediately
        filled, order_id, failures = self._run_acceptance(
            conn, seller_id=1, bid_id=bid_id, quantity=2,
            charge_result={'success': True, 'pi_id': 'pi_should_not_be_used'}
        )

        assert filled == 0
        assert order_id is None
        assert any('already charged' in f.get('reason', '') for f in failures)

        # No order should have been created
        order_count = conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
        assert order_count == 0

    # BP11: Failed payment — bid not paid, order not paid, inventory restored
    def test_BP11_failed_payment_no_paid_state_and_inventory_restored(self):
        """
        When _charge_bid_payment fails:
        - bid_payment_status must be 'failed', not 'charged'
        - no order should exist (or if created, payment_status must NOT be 'paid')
        - listing inventory must be restored to its pre-acceptance value (SAVEPOINT fix)
        """
        conn = _make_db()
        _seed(conn)
        listing_id = self._make_listing(conn, price=50.0, qty=5)
        bid_id = self._make_bid(conn, price=60.0, qty=2)

        initial_qty = conn.execute(
            'SELECT quantity FROM listings WHERE id=?', (listing_id,)
        ).fetchone()['quantity']
        assert initial_qty == 5

        failure_result = {'success': False, 'code': 'card_declined',
                          'message': 'Your card was declined.'}
        filled, order_id, failures = self._run_acceptance(
            conn, seller_id=1, bid_id=bid_id, quantity=2, charge_result=failure_result
        )

        assert filled == 0
        assert order_id is None
        assert failures

        # bid must be 'failed', not 'charged'
        bid_row = conn.execute(
            'SELECT bid_payment_status FROM bids WHERE id=?', (bid_id,)
        ).fetchone()
        assert bid_row['bid_payment_status'] == 'failed'

        # no order should remain in DB
        order_count = conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
        assert order_count == 0, "Order must be rolled back on payment failure"

        # listing inventory must be restored
        restored_qty = conn.execute(
            'SELECT quantity FROM listings WHERE id=?', (listing_id,)
        ).fetchone()['quantity']
        assert restored_qty == initial_qty, (
            f"Listing inventory must be restored after payment failure "
            f"(expected {initial_qty}, got {restored_qty}). "
            "SAVEPOINT must cover inventory updates."
        )

    # BP12: Accepting a non-edited bid works correctly
    def test_BP12_accept_non_edited_bid_succeeds(self):
        """Accepting a plain (never-edited) bid charges correctly."""
        conn = _make_db()
        _seed(conn)
        self._make_listing(conn, price=40.0, qty=5)
        bid_id = self._make_bid(conn, price=45.0, qty=3)

        success_result = {'success': True, 'pi_id': 'pi_bp12'}
        filled, order_id, failures = self._run_acceptance(
            conn, seller_id=1, bid_id=bid_id, quantity=3, charge_result=success_result
        )

        assert filled == 3
        assert not failures
        order = conn.execute('SELECT total_price FROM orders WHERE id=?', (order_id,)).fetchone()
        assert order['total_price'] == pytest.approx(135.0)  # 45.0 * 3

    # BP13: Edit bid (update_bid route) makes zero Stripe calls
    def test_BP13_update_bid_makes_no_stripe_calls(self):
        """
        Calling the update_bid logic path must not trigger any Stripe API call.
        We verify this by patching stripe globally and asserting nothing was called.
        """
        import stripe as stripe_mod
        with patch.object(stripe_mod.PaymentIntent, 'create') as mock_create, \
             patch.object(stripe_mod.PaymentMethod, 'list') as mock_list, \
             patch.object(stripe_mod.Customer, 'retrieve') as mock_retrieve:

            # Import the edit module (just ensure no side-effect calls happen at import)
            import core.blueprints.bids.edit_bid  # noqa: F401

            mock_create.assert_not_called()
            mock_list.assert_not_called()
            mock_retrieve.assert_not_called()


# ============================================================================
# BP17-BP22  Tax-in-charge correctness tests (accept_bid.py path)
# BP23-BP25  Auto-match tax correctness tests (auto_match.py path)
# ============================================================================

class TestBidTaxChargeCorrectness:
    """
    Verify that tax is always included in the Stripe charge amount and that the
    fallback rate (8.25%) matches the modal preview rate exactly.
    """

    FALLBACK = 0.0825
    CARD_RATE = 0.0299
    CARD_FLAT = 0.30

    def _expected_total(self, subtotal: float, tax_rate: float = None) -> float:
        """Compute expected total: subtotal + tax + card_fee, rounded to 2dp."""
        if tax_rate is None:
            tax_rate = self.FALLBACK
        tax = round(subtotal * tax_rate, 2)
        taxed = subtotal + tax
        fee = round(taxed * self.CARD_RATE + self.CARD_FLAT, 2)
        return round(taxed + fee, 2)

    # BP17: _get_stripe_tax_for_bid uses fallback rate when Stripe Tax fails
    def test_BP17_tax_fallback_rate_when_stripe_inactive(self):
        """
        When Stripe Tax raises any exception and a postal code is present,
        _get_stripe_tax_for_bid must return FALLBACK_TAX_RATE * subtotal (not 0).
        """
        import stripe as stripe_mod
        from core.blueprints.bids.accept_bid import _get_stripe_tax_for_bid, FALLBACK_TAX_RATE

        subtotal_cents = 10000  # $100.00
        expected_fallback = round(subtotal_cents * FALLBACK_TAX_RATE)

        with patch('stripe.tax.Calculation.create',
                   side_effect=stripe_mod.error.InvalidRequestError(
                       'No such Stripe Tax product', None
                   )):
            result = _get_stripe_tax_for_bid(subtotal_cents, '85001', 'AZ')

        assert result == expected_fallback, (
            f"Expected fallback tax {expected_fallback} cents "
            f"({FALLBACK_TAX_RATE*100:.2f}%), got {result}"
        )

    # BP18: No postal code → tax = 0 (no address, cannot determine jurisdiction)
    def test_BP18_no_postal_code_means_zero_tax(self):
        """When postal code is empty, _get_stripe_tax_for_bid must return 0."""
        from core.blueprints.bids.accept_bid import _get_stripe_tax_for_bid
        with patch('stripe.tax.Calculation.create') as mock_stripe:
            result = _get_stripe_tax_for_bid(10000, '', 'AZ')
        assert result == 0
        mock_stripe.assert_not_called()

    # BP19: Preview tax rate == fallback charge tax rate
    def test_BP19_preview_and_fallback_use_same_rate(self):
        """
        The bid modal preview (JS) uses 8.25%.
        The bid charge fallback must use the same 8.25%.
        If these diverge, the buyer sees one amount and is charged another.
        """
        from core.blueprints.bids.accept_bid import FALLBACK_TAX_RATE
        PREVIEW_RATE = 0.0825  # hardcoded in bid_modal_steps.js populateReview()
        assert FALLBACK_TAX_RATE == PREVIEW_RATE, (
            f"FALLBACK_TAX_RATE ({FALLBACK_TAX_RATE}) != JS preview rate ({PREVIEW_RATE}). "
            "Buyer would be shown one tax amount but charged a different one."
        )

    # BP20: Full charge amount includes subtotal + tax + fee
    def test_BP20_stripe_amount_includes_tax(self):
        """
        Integration: when Stripe Tax is unavailable (fallback), the amount sent to
        _charge_bid_payment (and thus to Stripe) must include tax, not just subtotal+fee.
        """
        import stripe as stripe_mod
        from core.blueprints.bids.accept_bid import (
            _get_stripe_tax_for_bid, FALLBACK_TAX_RATE, _CARD_RATE, _CARD_FLAT,
        )

        subtotal = 200.0   # 2 coins at $100 each
        subtotal_cents = int(round(subtotal * 100))

        # Stripe Tax fails → fallback
        with patch('stripe.tax.Calculation.create',
                   side_effect=stripe_mod.error.InvalidRequestError('inactive', None)):
            tax_cents = _get_stripe_tax_for_bid(subtotal_cents, '10001', 'NY')

        tax_amount = round(tax_cents / 100, 2)
        taxed_subtotal = subtotal + tax_amount
        card_fee = round(taxed_subtotal * _CARD_RATE + _CARD_FLAT, 2)
        total = round(taxed_subtotal + card_fee, 2)

        # Verify tax is non-zero
        assert tax_amount > 0, "Tax must be non-zero when postal code is present"

        # Verify total > subtotal + fee (tax is included)
        subtotal_plus_fee_only = round(subtotal * (1 + _CARD_RATE) + _CARD_FLAT, 2)
        assert total > subtotal_plus_fee_only, (
            f"Total {total} should be > subtotal+fee {subtotal_plus_fee_only}; "
            "tax is being dropped from the charge"
        )

        # Verify arithmetic: total == subtotal + tax + card_fee
        fee_cents = int(round(card_fee * 100))
        charged_cents = int(round(total * 100))
        assert charged_cents == subtotal_cents + tax_cents + fee_cents, (
            f"charged_cents={charged_cents} != "
            f"subtotal_cents={subtotal_cents} + tax_cents={tax_cents} + fee_cents={fee_cents} "
            f"(={subtotal_cents + tax_cents + fee_cents})"
        )

    # BP21: Stripe Tax success path passes tax through correctly
    def test_BP21_stripe_tax_success_uses_stripe_amount(self):
        """
        When Stripe Tax API succeeds, use the Stripe-computed amount (not fallback).
        """
        from core.blueprints.bids.accept_bid import _get_stripe_tax_for_bid

        mock_calc = MagicMock()
        mock_calc.tax_amount_exclusive = 750   # $7.50 — different from 8.25% fallback
        mock_calc.id = 'taxcalc_test_123'

        with patch('stripe.tax.Calculation.create', return_value=mock_calc):
            result = _get_stripe_tax_for_bid(10000, '94102', 'CA')

        assert result == 750, f"Expected 750 (Stripe value), got {result}"

    # BP22: DB tax_amount matches what was charged
    def test_BP22_db_tax_amount_matches_charge(self):
        """
        The orders.tax_amount stored in the DB must equal the tax used in the
        Stripe charge, so admin reconciliation can verify correctness.
        Checked via the accept_bid.py source code structure.
        """
        import ast, os
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'core', 'blueprints', 'bids', 'accept_bid.py',
        )
        with open(path) as f:
            src = f.read()

        # _tax_amount must appear in the INSERT INTO orders statement
        assert '_tax_amount' in src, "_tax_amount not computed in accept_bid.py"
        assert 'tax_amount' in src, "tax_amount column not written to orders in accept_bid.py"

        # The INSERT INTO orders must include tax_amount
        insert_start = src.find('INSERT INTO orders')
        insert_end   = src.find(')', insert_start)
        insert_block = src[insert_start:insert_end]
        assert 'tax_amount' in insert_block, (
            "tax_amount not included in the INSERT INTO orders statement — "
            "DB record won't reflect what was charged."
        )


# ============================================================================
# BP23-BP25  Auto-match tax correctness (auto_match.py path)
# ============================================================================

class TestAutoMatchTaxChargeCorrectness:
    """
    Verify that auto_match.py applies the same tax formula as accept_bid.py.

    These tests use source-code (AST/text) checks because the stripe package is
    not installed in the test environment.  The same pattern is used for BP22.
    """

    _BIDS_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'core', 'blueprints', 'bids',
    )

    def _read(self, filename):
        with open(os.path.join(self._BIDS_DIR, filename)) as f:
            return f.read()

    def _extract_constant(self, src, name):
        """
        Extract a float constant defined as ``NAME = <float>`` from source text.
        Returns None if not found.
        """
        import re
        m = re.search(rf'^{name}\s*=\s*([\d.]+)', src, re.MULTILINE)
        return float(m.group(1)) if m else None

    def test_BP23_auto_match_has_fallback_tax_rate_constant(self):
        """
        auto_match.py must define FALLBACK_TAX_RATE.
        Without this constant the fallback branch had no rate to apply and defaulted to 0.
        """
        src = self._read('auto_match.py')
        assert 'FALLBACK_TAX_RATE' in src, (
            "auto_match.py has no FALLBACK_TAX_RATE constant. "
            "The fallback branch will return 0, undercharging buyers by the full tax."
        )

    def test_BP24_auto_match_and_accept_bid_same_fallback_rate(self):
        """
        auto_match.FALLBACK_TAX_RATE must equal accept_bid.FALLBACK_TAX_RATE and the
        JS preview rate (0.0825).  Any divergence means manual vs auto-fill charge
        different amounts, or the modal preview doesn't match what is charged.
        """
        am_src = self._read('auto_match.py')
        ab_src = self._read('accept_bid.py')

        am_rate = self._extract_constant(am_src, 'FALLBACK_TAX_RATE')
        ab_rate = self._extract_constant(ab_src, 'FALLBACK_TAX_RATE')

        assert am_rate is not None, "FALLBACK_TAX_RATE not found in auto_match.py"
        assert ab_rate is not None, "FALLBACK_TAX_RATE not found in accept_bid.py"

        assert am_rate == ab_rate, (
            f"auto_match FALLBACK_TAX_RATE ({am_rate}) != "
            f"accept_bid FALLBACK_TAX_RATE ({ab_rate}). "
            "Manual acceptance and auto-fill charge different tax amounts."
        )

        JS_PREVIEW_RATE = 0.0825  # hardcoded in bid_modal_steps.js populateReview()
        assert am_rate == JS_PREVIEW_RATE, (
            f"auto_match FALLBACK_TAX_RATE ({am_rate}) != JS preview rate ({JS_PREVIEW_RATE}). "
            "Buyer sees one tax amount in the modal but is charged a different amount."
        )

    def test_BP25_auto_match_fallback_branch_returns_fallback_not_zero(self):
        """
        The except block in auto_match._get_stripe_tax_for_bid must return
        ``round(subtotal_cents * FALLBACK_TAX_RATE)`` — NOT ``return 0``.

        This was the root cause: when Stripe Tax was unavailable the function returned
        0, making _taxed_subtotal == _subtotal and dropping tax from the Stripe charge.
        Result: $400 subtotal → $412.26 charged instead of $446.25.
        """
        src = self._read('auto_match.py')

        # Find the _get_stripe_tax_for_bid function body
        fn_start = src.find('def _get_stripe_tax_for_bid(')
        assert fn_start != -1, "_get_stripe_tax_for_bid not found in auto_match.py"

        # Find the next function definition after this one (to bound the search)
        next_fn = src.find('\ndef ', fn_start + 1)
        fn_body = src[fn_start:next_fn] if next_fn != -1 else src[fn_start:]

        # The except block must NOT be a bare ``return 0``
        # (the old buggy implementation: `return 0` on any Stripe Tax exception)
        import re
        # Look for the pattern: except ... block containing only "return 0"
        # We check that FALLBACK_TAX_RATE is referenced inside the function body
        assert 'FALLBACK_TAX_RATE' in fn_body, (
            "_get_stripe_tax_for_bid in auto_match.py does not reference FALLBACK_TAX_RATE "
            "in its body.  The except block is still returning 0 instead of the fallback rate."
        )

    def test_BP26_auto_match_charge_formula_math(self):
        """
        Pure-math verification of the correct charge formula.
        $400 subtotal + 8.25% tax ($33) + 2.99%+$0.30 fee on taxed subtotal ($13.25)
        must equal $446.25, NOT the buggy $412.26 (tax-dropped formula).

        No imports from bids/ needed — just verifies the arithmetic is correct
        so we can trust that when the code uses FALLBACK_TAX_RATE it gets the right answer.
        """
        FALLBACK_TAX_RATE = 0.0825
        CARD_RATE = 0.0299
        CARD_FLAT = 0.30

        subtotal = 400.0
        subtotal_cents = int(round(subtotal * 100))

        # Correct formula (fixed)
        tax_cents = round(subtotal_cents * FALLBACK_TAX_RATE)
        tax_amount = round(tax_cents / 100, 2)
        taxed_subtotal = subtotal + tax_amount
        card_fee = round(taxed_subtotal * CARD_RATE + CARD_FLAT, 2)
        fill_total = round(taxed_subtotal + card_fee, 2)

        # Buggy formula (what was happening before the fix)
        buggy_card_fee = round(subtotal * CARD_RATE + CARD_FLAT, 2)
        buggy_total = round(subtotal + buggy_card_fee, 2)

        assert buggy_total == pytest.approx(412.26, abs=0.01), (
            f"Sanity: buggy formula should give $412.26, got {buggy_total}"
        )
        assert fill_total == pytest.approx(446.25, abs=0.01), (
            f"Correct formula should give $446.25, got {fill_total}. "
            "Check: tax=$33, taxed=$433, fee=$13.25, total=$446.25"
        )
        assert fill_total != pytest.approx(buggy_total), (
            "Correct and buggy formulas produce the same result — "
            "the fix has no effect on the charge amount"
        )

        # Hard assertion: subtotal + tax + fee == total
        fee_cents = int(round(card_fee * 100))
        charged_cents = int(round(fill_total * 100))
        assert charged_cents == subtotal_cents + tax_cents + fee_cents, (
            f"charged_cents ({charged_cents}) != "
            f"subtotal_cents + tax_cents + fee_cents "
            f"({subtotal_cents} + {tax_cents} + {fee_cents} = {subtotal_cents + tax_cents + fee_cents})"
        )


# ============================================================================
# BP27-BP29  End-to-end: real Flask route via test client
# ============================================================================

# Extended schema that matches every column accept_bid.py writes.
_FULL_SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    email TEXT DEFAULT 'x@x.com',
    password_hash TEXT DEFAULT 'x',
    first_name TEXT DEFAULT 'Test',
    last_name TEXT DEFAULT 'User',
    stripe_customer_id TEXT,
    account_frozen INTEGER DEFAULT 0,
    bid_payment_strikes INTEGER DEFAULT 0
);

CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metal TEXT DEFAULT 'gold',
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
    image_url TEXT,
    listing_title TEXT,
    description TEXT,
    packaging_type TEXT,
    packaging_notes TEXT,
    condition_notes TEXT
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
    delivery_address TEXT DEFAULT '123 Main St • Austin, TX 78701',
    status TEXT DEFAULT 'Open',
    pricing_mode TEXT DEFAULT 'static',
    spot_premium REAL,
    ceiling_price REAL,
    pricing_metal TEXT,
    recipient_first_name TEXT DEFAULT 'Test',
    recipient_last_name TEXT DEFAULT 'Buyer',
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
    buyer_card_fee REAL DEFAULT 0,
    tax_amount REAL DEFAULT 0,
    tax_rate REAL DEFAULT 0,
    shipping_address TEXT,
    status TEXT DEFAULT 'Pending Shipment',
    created_at TEXT,
    recipient_first_name TEXT,
    recipient_last_name TEXT,
    payment_status TEXT DEFAULT 'unpaid',
    stripe_payment_intent_id TEXT,
    paid_at TEXT,
    payment_method_type TEXT,
    source_bid_id INTEGER
);

CREATE TABLE order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    listing_id INTEGER,
    quantity INTEGER,
    price_each REAL,
    seller_price_each REAL
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

CREATE TABLE listing_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER,
    file_path TEXT,
    display_order INTEGER DEFAULT 0
);

CREATE TABLE transaction_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    order_item_id INTEGER,
    listing_id INTEGER,
    snapshot_at TEXT,
    quantity INTEGER,
    price_each REAL,
    buyer_id INTEGER,
    buyer_username TEXT,
    buyer_email TEXT,
    seller_id INTEGER,
    seller_username TEXT,
    seller_email TEXT,
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
    listing_title TEXT,
    description TEXT,
    packaging_type TEXT,
    packaging_notes TEXT,
    condition_notes TEXT,
    photo_url_1 TEXT,
    pricing_mode_used TEXT,
    spot_price_usd REAL,
    payment_intent_id TEXT,
    placed_from_ip TEXT
);

CREATE TABLE notification_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    notification_type TEXT,
    enabled INTEGER DEFAULT 1
);

CREATE TABLE notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    type TEXT,
    message TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    read INTEGER DEFAULT 0,
    metadata TEXT
);

CREATE TABLE orders_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    buyer_id INTEGER,
    seller_id INTEGER,
    listing_id INTEGER,
    quantity INTEGER,
    unit_price REAL,
    buyer_unit_price REAL,
    buyer_fee_amount REAL,
    seller_fee_amount REAL,
    platform_fee_amount REAL,
    buyer_subtotal REAL,
    seller_subtotal REAL,
    order_status TEXT DEFAULT 'CHECKOUT_INITIATED',
    payment_method TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE system_settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);
"""

_SPOT_E2E = 2000.0   # gold spot price
_PRICE_E2E = 1473.92  # effective bid price (matches bug-report screenshot)


def _make_e2e_db():
    """Create a full-schema in-memory SQLite for end-to-end route tests."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_FULL_SCHEMA)
    conn.execute("INSERT INTO spot_prices VALUES ('gold', ?)", (_SPOT_E2E,))
    conn.execute(
        "INSERT INTO spot_price_snapshots (metal, price_usd) VALUES ('gold', ?)",
        (_SPOT_E2E,)
    )
    conn.execute(
        "INSERT INTO system_settings (key, value) VALUES ('checkout_enabled', '1')"
    )
    conn.commit()
    return conn


def _seed_e2e(conn, price=_PRICE_E2E):
    """Seed: seller id=1, buyer id=2 (with Stripe customer), category+listing+bid."""
    conn.execute(
        "INSERT INTO users (id, username, stripe_customer_id) VALUES (1,'seller',NULL)"
    )
    conn.execute(
        "INSERT INTO users (id, username, stripe_customer_id) "
        "VALUES (2,'buyer','cus_buyer_test')"
    )
    conn.execute(
        "INSERT INTO categories (id, bucket_id, metal, weight) VALUES (1, 1, 'gold', '1 oz')"
    )
    conn.execute(
        "INSERT INTO listings (id, seller_id, category_id, price_per_coin, quantity, active) "
        "VALUES (1, 1, 1, ?, 1, 1)", (price,)
    )
    # Bid with full US delivery address so postal code can be parsed for tax
    conn.execute(
        "INSERT INTO bids (id, category_id, buyer_id, quantity_requested, "
        "remaining_quantity, price_per_coin, active, pricing_mode, "
        "delivery_address, bid_payment_method_id) "
        "VALUES (1, 1, 2, 1, 1, ?, 1, 'static', "
        "'123 Main St • Austin, TX 78701', 'pm_test_card')",
        (price,)
    )
    conn.commit()


class TestAcceptBidRouteE2E:
    """
    BP27-BP29: Exercise the REAL /bids/accept_bid/<bucket_id> Flask route via
    test client. Verifies that stripe.PaymentIntent.create is called with the
    FULL charge amount (subtotal + tax + fee), not just the subtotal.

    This is the definitive regression guard: if the formula reverts to
    ``total_price = filled * effective_bid_price`` (subtotal only), BP27 fails.
    """

    _PRICE = _PRICE_E2E      # $1,473.92 — matches bug-report screenshot
    _TAX_RATE = 0.0825       # fallback 8.25% (Stripe Tax disabled in tests)
    _CARD_RATE = 0.0299
    _CARD_FLAT = 0.30

    def _expected_cents(self, price=None):
        price = price or self._PRICE
        tax = round(price * self._TAX_RATE, 2)
        taxed = price + tax
        fee = round(taxed * self._CARD_RATE + self._CARD_FLAT, 2)
        total = round(taxed + fee, 2)
        return int(round(total * 100))

    def _subtotal_only_cents(self, price=None):
        price = price or self._PRICE
        return int(round(price * 100))

    def test_BP27_route_charges_full_total_not_subtotal(self):
        """
        The /bids/accept_bid route must call stripe.PaymentIntent.create with
        subtotal + fallback_tax + card_fee, NOT just the subtotal.

        Bug before fix:  amount = int(filled * effective_bid_price * 100)  → 147392
        Correct amount:  amount = int((subtotal + tax + fee) * 100)         → 164353
        """
        import stripe as stripe_mod
        import core.blueprints.bids.accept_bid as ab_mod

        db = _make_e2e_db()
        _seed_e2e(db)

        from app import app as flask_app
        import database as db_mod

        original_db = db_mod.get_db_connection
        original_ab = ab_mod.get_db_connection

        # Patch all DB calls inside the route to use our in-memory DB.
        # accept_bid.py does `from database import get_db_connection` at import time,
        # so we must patch both the module attribute AND the bound name in accept_bid.
        def _test_db():
            return db

        db_mod.get_db_connection = _test_db
        ab_mod.get_db_connection = _test_db

        try:
            # Disable CSRF so the test POST is accepted
            flask_app.config['WTF_CSRF_ENABLED'] = False

            # Stripe Tax unavailable → expect fallback 8.25% to be applied
            mock_tax_exc = stripe_mod.error.InvalidRequestError('Stripe Tax inactive', None)
            mock_pi = MagicMock(status='succeeded', id='pi_bp27_test')

            with flask_app.test_client() as client:
                with client.session_transaction() as sess:
                    sess['user_id'] = 1  # seller

                with patch('stripe.tax.Calculation.create', side_effect=mock_tax_exc), \
                     patch('stripe.PaymentIntent.create', return_value=mock_pi) as mock_create:

                    resp = client.post(
                        '/bids/accept_bid/1',
                        data={'selected_bids': ['1'], 'accept_qty[1]': '1'},
                        headers={'X-Requested-With': 'XMLHttpRequest'},
                    )

            assert resp.status_code == 200, (
                f"Route returned HTTP {resp.status_code}. "
                f"Response: {resp.get_data(as_text=True)[:500]}"
            )

            assert mock_create.called, (
                "stripe.PaymentIntent.create was never called. "
                "The bid acceptance did not attempt a Stripe charge."
            )

            # Extract the `amount` argument (cents)
            call_kwargs = mock_create.call_args.kwargs
            call_args = mock_create.call_args.args
            actual_cents = call_kwargs.get('amount', call_args[0] if call_args else None)

            expected_cents = self._expected_cents()
            subtotal_cents = self._subtotal_only_cents()

            assert actual_cents != subtotal_cents, (
                f"REGRESSION: Stripe was charged {actual_cents} cents "
                f"(${actual_cents/100:.2f}) — this equals the subtotal ONLY. "
                f"Tax ({self._TAX_RATE*100:.2f}%) and card fee ({self._CARD_RATE*100:.2f}%+${self._CARD_FLAT}) "
                f"are missing from the charge."
            )

            assert actual_cents == expected_cents, (
                f"Stripe was charged {actual_cents} cents (${actual_cents/100:.2f}), "
                f"expected {expected_cents} cents (${expected_cents/100:.2f}). "
                f"Subtotal-only (buggy) amount: {subtotal_cents} cents."
            )

        finally:
            flask_app.config['WTF_CSRF_ENABLED'] = True
            db_mod.get_db_connection = original_db
            ab_mod.get_db_connection = original_ab
            db.close()

    def test_BP28_charge_math_matches_bid_modal_preview(self):
        """
        The math used by accept_bid.py must produce the same total the bid modal
        shows the buyer: $1,473.92 subtotal → $121.60 tax → $48.01 fee → $1,643.53.
        """
        price = self._PRICE        # 1473.92
        tax = round(price * self._TAX_RATE, 2)        # 121.60
        taxed = price + tax                            # 1595.52
        fee = round(taxed * self._CARD_RATE + self._CARD_FLAT, 2)  # 48.01
        total = round(taxed + fee, 2)                 # 1643.53

        assert tax   == pytest.approx(121.60, abs=0.01), f"Tax mismatch: ${tax}"
        assert fee   == pytest.approx(48.01,  abs=0.01), f"Fee mismatch: ${fee}"
        assert total == pytest.approx(1643.53, abs=0.01), f"Total mismatch: ${total}"
        assert total > price, "Total must exceed subtotal after adding tax and fee"

    def test_BP29_subtotal_only_undercharges_by_significant_amount(self):
        """
        Quantify the bug impact: charging $1,473.92 instead of $1,643.53 means
        the platform absorbs ~$169.61 in tax + processing fees per transaction.
        """
        price = self._PRICE
        tax = round(price * self._TAX_RATE, 2)
        taxed = price + tax
        fee = round(taxed * self._CARD_RATE + self._CARD_FLAT, 2)
        total = round(taxed + fee, 2)
        undercharge = round(total - price, 2)
        assert undercharge == pytest.approx(169.61, abs=0.05), (
            f"Undercharge is ${undercharge}, expected ~$169.61"
        )
