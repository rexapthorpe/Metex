"""
Ledger Order Creation

Methods for creating order ledger records and validating invariants.
"""

import json
from typing import Dict, List, Optional, Any
import database
from services.ledger_constants import (
    OrderStatus, PayoutStatus, ActorType, EventType, PAYABLE_ORDER_STATUSES
)
from .exceptions import LedgerInvariantError
from .fee_config import get_fee_config, get_bucket_fee_config, calculate_fee


def get_db_connection():
    """Get database connection - wrapper for late binding in tests"""
    return database.get_db_connection()


def _log_event_internal(
    conn,
    order_id: int,
    event_type: str,
    actor_type: str,
    actor_id: Optional[int],
    payload: Optional[Dict[str, Any]]
):
    """Internal event logging with an existing connection (no commit)"""
    payload_json = json.dumps(payload) if payload else None
    conn.execute('''
        INSERT INTO order_events (order_id, event_type, actor_type, actor_id, payload_json)
        VALUES (?, ?, ?, ?, ?)
    ''', (order_id, event_type, actor_type, actor_id, payload_json))


def log_order_event(
    order_id: int,
    event_type: str,
    actor_type: str,
    actor_id: Optional[int],
    payload: Optional[Dict[str, Any]] = None
):
    """
    Log an event in the order lifecycle.

    Args:
        order_id: The order ID
        event_type: Type of event (from EventType enum)
        actor_type: Type of actor (from ActorType enum)
        actor_id: Optional ID of the actor (user_id, admin_id, etc.)
        payload: Optional dictionary of event-specific data
    """
    conn = get_db_connection()
    try:
        payload_json = json.dumps(payload) if payload else None
        conn.execute('''
            INSERT INTO order_events (order_id, event_type, actor_type, actor_id, payload_json)
            VALUES (?, ?, ?, ?, ?)
        ''', (order_id, event_type, actor_type, actor_id, payload_json))
        conn.commit()
    finally:
        conn.close()


def create_order_ledger_from_cart(
    buyer_id: int,
    cart_snapshot: List[Dict[str, Any]],
    payment_method: Optional[str] = None,
    order_id: Optional[int] = None
) -> int:
    """
    Create ledger records from a cart snapshot at order creation time.

    This function:
    a) Creates an orders_ledger record
    b) Creates order_items_ledger rows with per-item fee fields
    c) Creates one order_payout row per seller
    d) Creates order_events for ORDER_CREATED and LEDGER_CREATED

    Fee lookup priority (per item):
    1. Explicit fee_type/fee_value in cart item
    2. Bucket-level fee from categories table
    3. Global default from fee_config table

    Args:
        buyer_id: The ID of the buyer
        cart_snapshot: List of cart items, each containing:
            - seller_id: int
            - listing_id: int
            - quantity: int
            - unit_price: float
            - bucket_id (optional): int - bucket for fee lookup
            - fee_type (optional): 'percent' or 'flat' - explicit override
            - fee_value (optional): float - explicit override
        payment_method: Optional payment method string
        order_id: Optional existing order ID to link to

    Returns:
        The created order_ledger_id

    Raises:
        LedgerInvariantError: If invariants are violated
        BucketFeeConfigError: If no fee config found for a bucket
    """
    conn = get_db_connection()
    try:
        # Calculate totals
        total_gross = 0.0
        total_platform_fee = 0.0
        total_spread = 0.0
        items_to_insert = []
        seller_totals: Dict[int, Dict[str, float]] = {}  # seller_id -> {gross, fee, net, spread}

        for item in cart_snapshot:
            seller_id = item['seller_id']
            listing_id = item['listing_id']
            quantity = item['quantity']
            # unit_price is the SELLER-SIDE price (merchandise value).
            # For direct-checkout orders this equals the buyer price.
            # For bid-fill orders with spread, this is the seller's listing price.
            unit_price = float(item['unit_price'])

            # buyer_unit_price is what the buyer actually paid per unit.
            # When absent (normal checkout, no spread) it defaults to unit_price.
            buyer_unit_price = float(item.get('buyer_unit_price', unit_price))
            # Spread per unit: amount the platform retains as spread revenue (not fee).
            spread_per_unit = round(buyer_unit_price - unit_price, 4)

            # Calculate SELLER-SIDE gross for this item.
            # Fee and seller_net are computed on the seller-side gross so the seller
            # does not receive credit for the buyer premium above their ask.
            item_gross = round(quantity * unit_price, 2)

            # Total spread captured for this item line
            item_spread = round(quantity * spread_per_unit, 2)

            # Get fee config for this item
            # Priority: explicit override > bucket-level > global default
            if 'fee_type' in item and 'fee_value' in item:
                # Explicit override provided in cart snapshot
                fee_type = item['fee_type']
                fee_value = float(item['fee_value'])
            else:
                # Look up fee from bucket or global default
                bucket_id = item.get('bucket_id')

                if bucket_id is None:
                    # Try to get bucket_id from listing's category
                    bucket_result = conn.execute('''
                        SELECT c.bucket_id
                        FROM listings l
                        JOIN categories c ON l.category_id = c.id
                        WHERE l.id = ?
                    ''', (listing_id,)).fetchone()

                    if bucket_result:
                        bucket_id = bucket_result['bucket_id']

                if bucket_id:
                    # Get bucket-level or global default fee
                    fee_type, fee_value = get_bucket_fee_config(bucket_id, conn)
                else:
                    # Fallback to global default (legacy behavior)
                    fee_type, fee_value = get_fee_config()

            # Calculate fee on SELLER-SIDE gross (not buyer gross)
            fee_amount = calculate_fee(item_gross, fee_type, fee_value)
            seller_net = round(item_gross - fee_amount, 2)

            # Track totals
            total_gross += item_gross
            total_platform_fee += fee_amount
            total_spread += item_spread

            # Track per-seller totals
            if seller_id not in seller_totals:
                seller_totals[seller_id] = {'gross': 0, 'fee': 0, 'net': 0, 'spread': 0}
            seller_totals[seller_id]['gross'] += item_gross
            seller_totals[seller_id]['fee'] += fee_amount
            seller_totals[seller_id]['net'] += seller_net
            seller_totals[seller_id]['spread'] += item_spread

            items_to_insert.append({
                'seller_id': seller_id,
                'listing_id': listing_id,
                'quantity': quantity,
                'unit_price': unit_price,
                'buyer_unit_price': buyer_unit_price,
                'spread_per_unit': spread_per_unit,
                'gross_amount': item_gross,
                'fee_type': fee_type,
                'fee_value': fee_value,
                'fee_amount': fee_amount,
                'seller_net_amount': seller_net
            })

        # Round totals
        total_gross = round(total_gross, 2)
        total_platform_fee = round(total_platform_fee, 2)
        total_spread = round(total_spread, 2)

        # If no order_id provided, we need one from the orders table
        # In integration, this will be passed from the checkout flow
        if order_id is None:
            # Create a placeholder - in real integration, order_id is always provided
            cursor = conn.execute('''
                INSERT INTO orders (buyer_id, total_price, status)
                VALUES (?, ?, 'Pending')
            ''', (buyer_id, total_gross))
            order_id = cursor.lastrowid

        # 1. Create orders_ledger record
        cursor = conn.execute('''
            INSERT INTO orders_ledger (
                order_id, buyer_id, order_status, payment_method,
                gross_amount, platform_fee_amount, spread_capture_amount
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            order_id, buyer_id, OrderStatus.CHECKOUT_INITIATED.value,
            payment_method, total_gross, total_platform_fee, total_spread
        ))
        order_ledger_id = cursor.lastrowid

        # 2. Create order_items_ledger rows
        for item in items_to_insert:
            conn.execute('''
                INSERT INTO order_items_ledger (
                    order_ledger_id, order_id, seller_id, listing_id,
                    quantity, unit_price, gross_amount,
                    fee_type, fee_value, fee_amount, seller_net_amount,
                    buyer_unit_price, spread_per_unit
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                order_ledger_id, order_id, item['seller_id'], item['listing_id'],
                item['quantity'], item['unit_price'], item['gross_amount'],
                item['fee_type'], item['fee_value'], item['fee_amount'],
                item['seller_net_amount'],
                item['buyer_unit_price'], item['spread_per_unit']
            ))

        # 3. Create order_payout rows (one per seller)
        for seller_id, totals in seller_totals.items():
            conn.execute('''
                INSERT INTO order_payouts (
                    order_ledger_id, order_id, seller_id, payout_status,
                    seller_gross_amount, fee_amount, seller_net_amount,
                    spread_capture_amount
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                order_ledger_id, order_id, seller_id,
                PayoutStatus.PAYOUT_NOT_READY.value,
                round(totals['gross'], 2),
                round(totals['fee'], 2),
                round(totals['net'], 2),
                round(totals['spread'], 2)
            ))

        # 4. Create order events
        _log_event_internal(
            conn, order_id, EventType.ORDER_CREATED.value,
            ActorType.SYSTEM.value, None,
            {'buyer_id': buyer_id, 'gross_amount': total_gross}
        )
        _log_event_internal(
            conn, order_id, EventType.LEDGER_CREATED.value,
            ActorType.SYSTEM.value, None,
            {
                'order_ledger_id': order_ledger_id,
                'item_count': len(items_to_insert),
                'seller_count': len(seller_totals),
                'total_gross': total_gross,
                'total_platform_fee': total_platform_fee,
                'total_spread': total_spread,
            }
        )

        conn.commit()

        return order_ledger_id

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def validate_order_invariants(order_ledger_id: int):
    """
    Validate ledger invariants for an order.

    Invariants:
    1. sum(order_items.gross_amount) == orders_ledger.gross_amount
    2. For each seller: sum(items.seller_net_amount) == payout.seller_net_amount
    3. order_payouts cannot be PAID_OUT unless order_status is PAID_IN_ESCROW or later
    4. For each item: gross_amount - fee_amount == seller_net_amount

    Raises:
        LedgerInvariantError: If any invariant is violated
    """
    conn = get_db_connection()
    try:
        # Get order ledger
        order = conn.execute('''
            SELECT * FROM orders_ledger WHERE id = ?
        ''', (order_ledger_id,)).fetchone()

        if not order:
            raise LedgerInvariantError(f"Order ledger {order_ledger_id} not found")

        # Invariant 1: Items gross sum matches order gross
        items_sum = conn.execute('''
            SELECT COALESCE(SUM(gross_amount), 0) as total
            FROM order_items_ledger WHERE order_ledger_id = ?
        ''', (order_ledger_id,)).fetchone()['total']

        if abs(items_sum - order['gross_amount']) > 0.01:
            raise LedgerInvariantError(
                f"Invariant violated: sum(items.gross_amount)={items_sum} "
                f"!= orders_ledger.gross_amount={order['gross_amount']}"
            )

        # Invariant 2: Per-seller net amounts match
        # Get all unique sellers for this order
        sellers = conn.execute('''
            SELECT DISTINCT seller_id FROM order_items_ledger WHERE order_ledger_id = ?
        ''', (order_ledger_id,)).fetchall()

        for seller_row in sellers:
            seller_id = seller_row['seller_id']

            # Sum of items for this seller
            items_net = conn.execute('''
                SELECT COALESCE(SUM(seller_net_amount), 0) as total
                FROM order_items_ledger
                WHERE order_ledger_id = ? AND seller_id = ?
            ''', (order_ledger_id, seller_id)).fetchone()['total']

            # Payout record for this seller
            payout = conn.execute('''
                SELECT seller_net_amount FROM order_payouts
                WHERE order_ledger_id = ? AND seller_id = ?
            ''', (order_ledger_id, seller_id)).fetchone()

            if not payout:
                raise LedgerInvariantError(
                    f"Invariant violated: No payout record for seller {seller_id}"
                )

            if abs(items_net - payout['seller_net_amount']) > 0.01:
                raise LedgerInvariantError(
                    f"Invariant violated: sum(items.seller_net) for seller {seller_id}={items_net} "
                    f"!= payout.seller_net_amount={payout['seller_net_amount']}"
                )

        # Invariant 3: Check payout status vs order status
        payouts = conn.execute('''
            SELECT * FROM order_payouts WHERE order_ledger_id = ?
        ''', (order_ledger_id,)).fetchall()

        for payout in payouts:
            if payout['payout_status'] == PayoutStatus.PAID_OUT.value:
                # Order must be in a payable status
                payable_statuses = [s.value for s in PAYABLE_ORDER_STATUSES]
                if order['order_status'] not in payable_statuses:
                    raise LedgerInvariantError(
                        f"Invariant violated: Payout {payout['id']} is PAID_OUT but "
                        f"order status is {order['order_status']}"
                    )

        # Invariant 4: For each item, gross_amount - fee_amount == seller_net_amount
        items = conn.execute('''
            SELECT id, gross_amount, fee_amount, seller_net_amount
            FROM order_items_ledger WHERE order_ledger_id = ?
        ''', (order_ledger_id,)).fetchall()

        for item in items:
            expected_net = round(item['gross_amount'] - item['fee_amount'], 2)
            actual_net = round(item['seller_net_amount'], 2)
            if abs(expected_net - actual_net) > 0.01:
                raise LedgerInvariantError(
                    f"Invariant violated: item {item['id']}: "
                    f"gross({item['gross_amount']}) - fee({item['fee_amount']}) = {expected_net} "
                    f"!= seller_net({actual_net})"
                )

        return True

    finally:
        conn.close()


def prevent_amount_modification(order_ledger_id: int):
    """
    Check that amounts haven't been modified after order creation.

    This is a runtime check - amounts should never be updated after creation.
    In a production system, this would be enforced via triggers or application-level checks.

    Note: This is informational - the actual prevention is done by not having
    UPDATE routes for amount fields.
    """
    # In SQLite we don't have triggers by default, so this is enforced
    # at the application level by not providing any UPDATE endpoints
    # for amount-related fields in orders_ledger, order_items_ledger, or order_payouts
    pass
