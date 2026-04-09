"""
Tests for Orders Tab Transaction Details feature.

Covers:
- Tile displays total_price (full buyer-paid total) instead of subtotal
- Transaction Details button appears in the quick actions area
- /orders/api/<order_id>/transaction endpoint:
  - Auth guards (401 for anonymous, 403 for non-participants)
  - Correct structure and values for a full order with tax + processing fee
  - Legacy orders (tax=0, fee=0) handled gracefully
  - 404 for non-existent orders
- Subtotal, tax, processing fee, and total shown as distinct line items
"""
import json
import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_seller(conn):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, email, password, password_hash, is_admin, is_banned, is_frozen) "
        "VALUES ('seller_txn', 'seller_txn@example.com', 'pw', 'pw', 0, 0, 0)"
    )
    seller_id = cur.lastrowid
    conn.commit()
    return seller_id


def _create_category(conn):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO categories "
        "(bucket_id, metal, product_type, weight, mint, year, product_line, is_isolated, "
        "platform_fee_type, platform_fee_value) "
        "VALUES (1, 'Gold', 'Coin', '1 oz', 'US Mint', 2024, 'American Eagle', 0, 'percent', 2.5)"
    )
    cat_id = cur.lastrowid
    conn.commit()
    return cat_id


def _create_listing(conn, seller_id, cat_id, price=2500.0):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO listings (seller_id, category_id, price_per_coin, quantity, active, "
        "pricing_mode, spot_premium, floor_price) "
        "VALUES (?, ?, ?, 10, 1, 'static', NULL, NULL)",
        (seller_id, cat_id, price)
    )
    listing_id = cur.lastrowid
    conn.commit()
    return listing_id


def _create_order(conn, buyer_id, total_price, tax_amount=0.0, buyer_card_fee=0.0):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO orders (buyer_id, total_price, status, tax_amount, buyer_card_fee) "
        "VALUES (?, ?, 'Pending', ?, ?)",
        (buyer_id, total_price, tax_amount, buyer_card_fee)
    )
    order_id = cur.lastrowid
    conn.commit()
    return order_id


def _create_order_item(conn, order_id, listing_id, quantity=1, price_each=2500.0, grading_fee=0.0):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO order_items (order_id, listing_id, quantity, price_each, grading_fee_charged) "
        "VALUES (?, ?, ?, ?, ?)",
        (order_id, listing_id, quantity, price_each, grading_fee)
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Fixture: a full order with tax + processing fee
# ---------------------------------------------------------------------------

@pytest.fixture
def order_with_fees(auth_client):
    """
    Creates: buyer (auth_client user), seller, listing, order with 2 items,
    tax=$18.75, processing fee=$75.60.
    Returns (client, buyer_id, order_id).
    """
    import database
    client, buyer_id = auth_client
    conn = database.get_db_connection()

    seller_id  = _create_seller(conn)
    cat_id     = _create_category(conn)
    listing_id = _create_listing(conn, seller_id, cat_id, price=2500.0)

    merchandise_subtotal = 2 * 2500.0          # 5000.00
    tax_amount           = 18.75
    buyer_card_fee       = 75.60
    total_price          = merchandise_subtotal + tax_amount + buyer_card_fee  # 5094.35

    order_id = _create_order(conn, buyer_id, total_price, tax_amount, buyer_card_fee)
    _create_order_item(conn, order_id, listing_id, quantity=2, price_each=2500.0)

    conn.close()
    return client, buyer_id, order_id, total_price


# ---------------------------------------------------------------------------
# Fixture: legacy order (no tax / fee — both default to 0)
# ---------------------------------------------------------------------------

@pytest.fixture
def legacy_order(auth_client):
    """
    Creates an order with tax_amount=0 and buyer_card_fee=0 (legacy record).
    Returns (client, buyer_id, order_id).
    """
    import database
    client, buyer_id = auth_client
    conn = database.get_db_connection()

    seller_id  = _create_seller(conn)
    cat_id     = _create_category(conn)
    listing_id = _create_listing(conn, seller_id, cat_id, price=1800.0)

    total_price = 1800.0  # no tax / fee on legacy record

    order_id = _create_order(conn, buyer_id, total_price, tax_amount=0.0, buyer_card_fee=0.0)
    _create_order_item(conn, order_id, listing_id, quantity=1, price_each=1800.0)

    conn.close()
    return client, buyer_id, order_id, total_price


# ---------------------------------------------------------------------------
# Auth guard tests
# ---------------------------------------------------------------------------

class TestTransactionAuthGuards:
    def test_anonymous_gets_401(self, client, order_with_fees):
        """Unauthenticated request returns 401 — log out then hit the endpoint."""
        _, __, order_id, _total = order_with_fees
        # Clear the session so we're anonymous
        with client.session_transaction() as sess:
            sess.clear()
        resp = client.get(f'/orders/api/{order_id}/transaction')
        assert resp.status_code == 401
        data = json.loads(resp.data)
        assert 'error' in data

    def test_non_participant_gets_403(self, order_with_fees):
        """User who is not buyer/seller of an order gets 403."""
        import database
        from flask import Flask
        buyer_client, _, order_id, _total = order_with_fees

        # Create a separate stranger client from scratch
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, email, password, password_hash, is_admin, is_banned, is_frozen) "
            "VALUES ('stranger_txn2', 'stranger_txn2@example.com', 'pw', 'pw', 0, 0, 0)"
        )
        stranger_id = cur.lastrowid
        conn.commit()
        conn.close()

        # Reuse the same test client but set a different session user
        with buyer_client.session_transaction() as sess:
            sess['user_id'] = stranger_id
            sess['username'] = 'stranger_txn2'

        resp = buyer_client.get(f'/orders/api/{order_id}/transaction')
        assert resp.status_code == 403

    def test_nonexistent_order_returns_404_or_403(self, auth_client):
        """Non-existent order returns 403 (access check fails) or 404."""
        client, _ = auth_client
        resp = client.get('/orders/api/999999/transaction')
        assert resp.status_code in (403, 404)


# ---------------------------------------------------------------------------
# Response structure tests — full order with tax + fee
# ---------------------------------------------------------------------------

class TestTransactionResponseStructure:
    def test_response_has_required_top_level_keys(self, order_with_fees):
        client, _, order_id, _ = order_with_fees
        resp = client.get(f'/orders/api/{order_id}/transaction')
        assert resp.status_code == 200
        data = json.loads(resp.data)

        required_keys = {'items', 'merchandise_subtotal', 'tax_amount',
                         'buyer_card_fee', 'total_price'}
        assert required_keys.issubset(data.keys()), (
            f"Missing keys: {required_keys - set(data.keys())}"
        )

    def test_items_list_structure(self, order_with_fees):
        client, _, order_id, _ = order_with_fees
        resp = client.get(f'/orders/api/{order_id}/transaction')
        data = json.loads(resp.data)

        assert isinstance(data['items'], list)
        assert len(data['items']) >= 1

        item = data['items'][0]
        for field in ('label', 'quantity', 'price_each', 'line_total', 'seller_username'):
            assert field in item, f"Item missing field: {field}"

    def test_correct_financial_values(self, order_with_fees):
        client, _, order_id, total_price = order_with_fees
        resp = client.get(f'/orders/api/{order_id}/transaction')
        data = json.loads(resp.data)

        assert data['merchandise_subtotal'] == pytest.approx(5000.00, abs=0.01)
        assert data['tax_amount']           == pytest.approx(18.75, abs=0.01)
        assert data['buyer_card_fee']       == pytest.approx(75.60, abs=0.01)
        assert data['total_price']          == pytest.approx(total_price, abs=0.01)

    def test_item_line_total_matches_qty_times_price(self, order_with_fees):
        client, _, order_id, _ = order_with_fees
        resp = client.get(f'/orders/api/{order_id}/transaction')
        data = json.loads(resp.data)

        for item in data['items']:
            expected = round(item['quantity'] * item['price_each'], 2)
            assert item['line_total'] == pytest.approx(expected, abs=0.01)

    def test_tax_is_separate_from_subtotal(self, order_with_fees):
        """Tax must appear as its own distinct value, not folded into subtotal."""
        client, _, order_id, _ = order_with_fees
        resp = client.get(f'/orders/api/{order_id}/transaction')
        data = json.loads(resp.data)

        # Subtotal is merchandise only
        assert data['merchandise_subtotal'] != data['total_price']
        # Tax shown separately
        assert data['tax_amount'] > 0

    def test_processing_fee_separate(self, order_with_fees):
        """Processing fee must appear as its own distinct value."""
        client, _, order_id, _ = order_with_fees
        resp = client.get(f'/orders/api/{order_id}/transaction')
        data = json.loads(resp.data)

        assert data['buyer_card_fee'] > 0
        # Fee not hidden inside subtotal
        assert data['merchandise_subtotal'] < data['total_price']


# ---------------------------------------------------------------------------
# Legacy order tests (tax=0, fee=0)
# ---------------------------------------------------------------------------

class TestLegacyOrderGracefulHandling:
    def test_legacy_order_returns_200(self, legacy_order):
        client, _, order_id, _ = legacy_order
        resp = client.get(f'/orders/api/{order_id}/transaction')
        assert resp.status_code == 200

    def test_legacy_order_zero_tax_and_fee(self, legacy_order):
        client, _, order_id, _ = legacy_order
        resp = client.get(f'/orders/api/{order_id}/transaction')
        data = json.loads(resp.data)

        assert data['tax_amount']     == 0.0
        assert data['buyer_card_fee'] == 0.0

    def test_legacy_order_total_matches_stored(self, legacy_order):
        client, _, order_id, total_price = legacy_order
        resp = client.get(f'/orders/api/{order_id}/transaction')
        data = json.loads(resp.data)

        assert data['total_price'] == pytest.approx(total_price, abs=0.01)

    def test_legacy_order_has_items(self, legacy_order):
        client, _, order_id, _ = legacy_order
        resp = client.get(f'/orders/api/{order_id}/transaction')
        data = json.loads(resp.data)

        assert isinstance(data['items'], list)
        assert len(data['items']) >= 1


# ---------------------------------------------------------------------------
# Tile price field — verify query now exposes total_price
# ---------------------------------------------------------------------------

class TestTilePriceSource:
    """
    The account_page query must include total_price, tax_amount, buyer_card_fee,
    and merchandise_subtotal so the template can show the full total paid.
    We test this indirectly by verifying the /orders/api/<id>/transaction
    endpoint returns these fields, and directly by checking the account page
    renders without error for a buyer with orders.
    """

    def test_account_page_loads_with_orders(self, order_with_fees):
        """Account page renders (200) when the buyer has orders."""
        client, _, _, _ = order_with_fees
        resp = client.get('/account')
        assert resp.status_code == 200

    def test_account_page_loads_with_legacy_orders(self, legacy_order):
        """Account page renders (200) with legacy orders (no tax/fee)."""
        client, _, _, _ = legacy_order
        resp = client.get('/account')
        assert resp.status_code == 200

    def test_transaction_details_button_in_template(self, order_with_fees):
        """The rendered account page HTML contains 'Transaction Details'."""
        client, _, _, _ = order_with_fees
        resp = client.get('/account')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'Transaction Details' in html

    def test_total_paid_label_in_template(self, order_with_fees):
        """The rendered account page HTML contains 'Total Paid' label."""
        client, _, _, _ = order_with_fees
        resp = client.get('/account')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'Total Paid' in html


# ---------------------------------------------------------------------------
# Helpers for bid-originated orders
# ---------------------------------------------------------------------------

def _create_bid_order(conn, buyer_id, seller_id, cat_id, listing_id,
                      qty=2, price_each=1500.0, tax_amount=12.50, buyer_card_fee=45.30):
    """
    Create an order that mimics what accept_bid.py creates:
    - source_bid_id set (non-NULL)
    - total_price = merchandise subtotal + tax + card fee
    - buyer_card_fee and tax_amount stored separately
    """
    cur = conn.cursor()
    merchandise_subtotal = qty * price_each
    total_price = round(merchandise_subtotal + tax_amount + buyer_card_fee, 2)

    cur.execute(
        "INSERT INTO orders (buyer_id, total_price, status, tax_amount, buyer_card_fee, source_bid_id) "
        "VALUES (?, ?, 'paid', ?, ?, 1)",
        (buyer_id, total_price, tax_amount, buyer_card_fee)
    )
    order_id = cur.lastrowid

    cur.execute(
        "INSERT INTO order_items (order_id, listing_id, quantity, price_each) "
        "VALUES (?, ?, ?, ?)",
        (order_id, listing_id, qty, price_each)
    )
    conn.commit()
    return order_id, total_price


def _create_legacy_bid_order(conn, buyer_id, listing_id, qty=1, price_each=800.0):
    """
    Legacy bid order: source_bid_id set but tax_amount=0, buyer_card_fee=0,
    total_price = merchandise subtotal only (how older auto_match_listing_to_bids stored it).
    """
    cur = conn.cursor()
    total_price = qty * price_each
    cur.execute(
        "INSERT INTO orders (buyer_id, total_price, status, tax_amount, buyer_card_fee, source_bid_id) "
        "VALUES (?, ?, 'paid', 0.0, 0.0, 1)",
        (buyer_id, total_price)
    )
    order_id = cur.lastrowid
    cur.execute(
        "INSERT INTO order_items (order_id, listing_id, quantity, price_each) "
        "VALUES (?, ?, ?, ?)",
        (order_id, listing_id, qty, price_each)
    )
    conn.commit()
    return order_id, total_price


# ---------------------------------------------------------------------------
# Fixtures for bid-originated orders
# ---------------------------------------------------------------------------

@pytest.fixture
def bid_order(auth_client):
    """
    Bid-originated order with full financial breakdown (tax + fee stored).
    Returns (client, buyer_id, order_id, total_price).
    """
    import database
    client, buyer_id = auth_client
    conn = database.get_db_connection()

    seller_id  = _create_seller(conn)
    cat_id     = _create_category(conn)
    listing_id = _create_listing(conn, seller_id, cat_id, price=1500.0)

    order_id, total_price = _create_bid_order(
        conn, buyer_id, seller_id, cat_id, listing_id,
        qty=2, price_each=1500.0, tax_amount=12.50, buyer_card_fee=45.30
    )
    conn.close()
    return client, buyer_id, order_id, total_price


@pytest.fixture
def legacy_bid_order(auth_client):
    """
    Legacy bid order: fee=0, tax=0, total=subtotal (old auto_match_listing_to_bids behaviour).
    Returns (client, buyer_id, order_id, total_price).
    """
    import database
    client, buyer_id = auth_client
    conn = database.get_db_connection()

    seller_id  = _create_seller(conn)
    cat_id     = _create_category(conn)
    listing_id = _create_listing(conn, seller_id, cat_id, price=800.0)

    order_id, total_price = _create_legacy_bid_order(
        conn, buyer_id, listing_id, qty=1, price_each=800.0
    )
    conn.close()
    return client, buyer_id, order_id, total_price


# ---------------------------------------------------------------------------
# Bid-originated order tests
# ---------------------------------------------------------------------------

class TestBidOriginatedOrders:
    def test_bid_order_tile_shows_total_price_not_subtotal(self, bid_order):
        """
        Tile must display the full buyer-paid total (including tax + fee),
        not just the merchandise subtotal.
        """
        client, _, order_id, total_price = bid_order
        resp = client.get(f'/orders/api/{order_id}/transaction')
        assert resp.status_code == 200
        data = json.loads(resp.data)

        # total_price must be greater than merchandise subtotal (tax+fee were added)
        assert data['total_price'] > data['merchandise_subtotal'], (
            "Bid order total should exceed merchandise subtotal (tax+fee not stored)"
        )
        assert data['total_price'] == pytest.approx(total_price, abs=0.01)

    def test_bid_order_transaction_shows_correct_breakdown(self, bid_order):
        """Transaction Details modal shows subtotal, tax, fee, and total separately."""
        client, _, order_id, total_price = bid_order
        resp = client.get(f'/orders/api/{order_id}/transaction')
        assert resp.status_code == 200
        data = json.loads(resp.data)

        assert data['merchandise_subtotal'] == pytest.approx(3000.00, abs=0.01)  # 2 × $1500
        assert data['tax_amount']           == pytest.approx(12.50,   abs=0.01)
        assert data['buyer_card_fee']       == pytest.approx(45.30,   abs=0.01)
        assert data['total_price']          == pytest.approx(total_price, abs=0.01)

    def test_bid_order_tax_is_distinct_from_subtotal(self, bid_order):
        """Tax appears as its own non-zero line, not folded into the subtotal."""
        client, _, order_id, _ = bid_order
        resp = client.get(f'/orders/api/{order_id}/transaction')
        data = json.loads(resp.data)

        assert data['tax_amount'] > 0
        # Subtotal is merchandise only — must not include tax
        assert data['merchandise_subtotal'] == pytest.approx(
            sum(item['line_total'] for item in data['items']), abs=0.01
        )

    def test_bid_order_processing_fee_is_distinct(self, bid_order):
        """Processing fee appears as its own non-zero line."""
        client, _, order_id, _ = bid_order
        resp = client.get(f'/orders/api/{order_id}/transaction')
        data = json.loads(resp.data)

        assert data['buyer_card_fee'] > 0
        assert data['merchandise_subtotal'] < data['total_price']

    def test_bid_order_items_have_correct_price_each(self, bid_order):
        """Item rows show the bid price (effective_bid_price), not total with fees."""
        client, _, order_id, _ = bid_order
        resp = client.get(f'/orders/api/{order_id}/transaction')
        data = json.loads(resp.data)

        for item in data['items']:
            assert item['price_each'] == pytest.approx(1500.0, abs=0.01)
            assert item['line_total'] == pytest.approx(
                item['quantity'] * item['price_each'], abs=0.01
            )

    def test_legacy_bid_order_degrades_gracefully(self, legacy_bid_order):
        """
        Legacy bid orders (fee=0, tax=0 — old auto_match_listing_to_bids behaviour)
        must render without error and show zero for the missing fields.
        """
        client, _, order_id, total_price = legacy_bid_order
        resp = client.get(f'/orders/api/{order_id}/transaction')
        assert resp.status_code == 200
        data = json.loads(resp.data)

        assert data['tax_amount']     == pytest.approx(0.0, abs=0.01)
        assert data['buyer_card_fee'] == pytest.approx(0.0, abs=0.01)
        # total_price == merchandise_subtotal for legacy (no fee was charged)
        assert data['total_price']    == pytest.approx(total_price, abs=0.01)

    def test_legacy_bid_order_total_equals_subtotal(self, legacy_bid_order):
        """For legacy bid orders with no fee, total == merchandise subtotal."""
        client, _, order_id, total_price = legacy_bid_order
        resp = client.get(f'/orders/api/{order_id}/transaction')
        data = json.loads(resp.data)

        assert data['total_price'] == pytest.approx(data['merchandise_subtotal'], abs=0.01)
