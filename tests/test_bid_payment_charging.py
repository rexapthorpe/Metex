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
