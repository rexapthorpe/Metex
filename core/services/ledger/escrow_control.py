"""
Ledger Escrow Control

Admin actions for holding, approving, releasing, and refunding orders/payouts.
"""

from typing import Dict, List, Optional, Any
import database
from services.ledger_constants import (
    OrderStatus, PayoutStatus, ActorType, EventType,
    ORDER_HOLD_BLOCKED_STATUSES, PAYOUT_HOLD_BLOCKED_STATUSES
)
from .exceptions import EscrowControlError
from .order_creation import _log_event_internal


def get_db_connection():
    """Get database connection - wrapper for late binding in tests"""
    return database.get_db_connection()


def hold_order(order_id: int, admin_id: int, reason: str) -> bool:
    """
    Admin action: Place an order UNDER_REVIEW and hold ALL related payouts.

    Preconditions:
    - order_status NOT IN (CANCELLED, REFUNDED, COMPLETED)

    Effects:
    - order_status → UNDER_REVIEW
    - ALL related order_payouts: payout_status → PAYOUT_ON_HOLD
    - Log event: ORDER_HELD

    Args:
        order_id: The order ID to hold
        admin_id: The admin user performing the action
        reason: Required reason for the hold

    Returns:
        True if successful

    Raises:
        EscrowControlError: If preconditions are not met
        ValueError: If order not found
    """
    if not reason or not reason.strip():
        raise EscrowControlError("Reason is required for holding an order")

    conn = get_db_connection()
    try:
        # Get order ledger record
        order = conn.execute('''
            SELECT id, order_id, order_status FROM orders_ledger WHERE order_id = ?
        ''', (order_id,)).fetchone()

        if not order:
            raise ValueError(f"Order {order_id} not found in ledger")

        current_status = OrderStatus(order['order_status'])

        # Check preconditions
        blocked_statuses = [s.value for s in ORDER_HOLD_BLOCKED_STATUSES]
        if current_status.value in blocked_statuses:
            raise EscrowControlError(
                f"Cannot hold order in status {current_status.value}. "
                f"Order must not be in {blocked_statuses}"
            )

        # Update order status to UNDER_REVIEW
        conn.execute('''
            UPDATE orders_ledger
            SET order_status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ?
        ''', (OrderStatus.UNDER_REVIEW.value, order_id))

        # Hold ALL related payouts
        conn.execute('''
            UPDATE order_payouts
            SET payout_status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ? AND payout_status NOT IN (?, ?)
        ''', (
            PayoutStatus.PAYOUT_ON_HOLD.value, order_id,
            PayoutStatus.PAID_OUT.value, PayoutStatus.PAYOUT_CANCELLED.value
        ))

        # Log event
        _log_event_internal(
            conn, order_id, EventType.ORDER_HELD.value,
            ActorType.ADMIN.value, admin_id,
            {
                'reason': reason.strip(),
                'previous_status': current_status.value
            }
        )

        conn.commit()
        return True

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def approve_order(order_id: int, admin_id: int) -> bool:
    """
    Admin action: Release an order from UNDER_REVIEW to AWAITING_SHIPMENT.

    Preconditions:
    - order_status == UNDER_REVIEW

    Effects:
    - order_status → AWAITING_SHIPMENT
    - For each payout currently PAYOUT_ON_HOLD: payout_status → PAYOUT_NOT_READY
    - Log event: ORDER_APPROVED

    Args:
        order_id: The order ID to approve
        admin_id: The admin user performing the action

    Returns:
        True if successful

    Raises:
        EscrowControlError: If preconditions are not met
        ValueError: If order not found
    """
    conn = get_db_connection()
    try:
        # Get order ledger record
        order = conn.execute('''
            SELECT id, order_id, order_status FROM orders_ledger WHERE order_id = ?
        ''', (order_id,)).fetchone()

        if not order:
            raise ValueError(f"Order {order_id} not found in ledger")

        current_status = OrderStatus(order['order_status'])

        # Check preconditions
        if current_status != OrderStatus.UNDER_REVIEW:
            raise EscrowControlError(
                f"Cannot approve order in status {current_status.value}. "
                f"Order must be UNDER_REVIEW"
            )

        # Update order status to AWAITING_SHIPMENT
        conn.execute('''
            UPDATE orders_ledger
            SET order_status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ?
        ''', (OrderStatus.AWAITING_SHIPMENT.value, order_id))

        # Release held payouts to PAYOUT_NOT_READY
        conn.execute('''
            UPDATE order_payouts
            SET payout_status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ? AND payout_status = ?
        ''', (
            PayoutStatus.PAYOUT_NOT_READY.value, order_id,
            PayoutStatus.PAYOUT_ON_HOLD.value
        ))

        # Log event
        _log_event_internal(
            conn, order_id, EventType.ORDER_APPROVED.value,
            ActorType.ADMIN.value, admin_id,
            {'previous_status': current_status.value}
        )

        conn.commit()
        return True

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def hold_payout(payout_id: int, admin_id: int, reason: str) -> bool:
    """
    Admin action: Hold a specific seller's payout.

    Preconditions:
    - payout_status NOT IN (PAID_OUT, PAYOUT_CANCELLED)

    Effects:
    - payout_status → PAYOUT_ON_HOLD
    - Log event: PAYOUT_HELD

    Args:
        payout_id: The payout ID to hold
        admin_id: The admin user performing the action
        reason: Required reason for the hold

    Returns:
        True if successful

    Raises:
        EscrowControlError: If preconditions are not met
        ValueError: If payout not found
    """
    if not reason or not reason.strip():
        raise EscrowControlError("Reason is required for holding a payout")

    conn = get_db_connection()
    try:
        # Get payout record
        payout = conn.execute('''
            SELECT p.*, ol.order_status
            FROM order_payouts p
            JOIN orders_ledger ol ON p.order_ledger_id = ol.id
            WHERE p.id = ?
        ''', (payout_id,)).fetchone()

        if not payout:
            raise ValueError(f"Payout {payout_id} not found")

        current_status = PayoutStatus(payout['payout_status'])

        # Check preconditions
        blocked_statuses = [s.value for s in PAYOUT_HOLD_BLOCKED_STATUSES]
        if current_status.value in blocked_statuses:
            raise EscrowControlError(
                f"Cannot hold payout in status {current_status.value}. "
                f"Payout must not be in {blocked_statuses}"
            )

        # Update payout status
        conn.execute('''
            UPDATE order_payouts
            SET payout_status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (PayoutStatus.PAYOUT_ON_HOLD.value, payout_id))

        # Log event
        _log_event_internal(
            conn, payout['order_id'], EventType.PAYOUT_HELD.value,
            ActorType.ADMIN.value, admin_id,
            {
                'payout_id': payout_id,
                'seller_id': payout['seller_id'],
                'reason': reason.strip(),
                'previous_status': current_status.value
            }
        )

        conn.commit()
        return True

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def release_payout(payout_id: int, admin_id: int) -> bool:
    """
    Admin action: Release a held payout to PAYOUT_READY.

    Preconditions:
    - payout_status == PAYOUT_ON_HOLD
    - order_status NOT IN (UNDER_REVIEW, CANCELLED, REFUNDED)

    Effects:
    - payout_status → PAYOUT_READY
    - Log event: PAYOUT_RELEASED

    Args:
        payout_id: The payout ID to release
        admin_id: The admin user performing the action

    Returns:
        True if successful

    Raises:
        EscrowControlError: If preconditions are not met
        ValueError: If payout not found
    """
    conn = get_db_connection()
    try:
        # Get payout record with order status
        payout = conn.execute('''
            SELECT p.*, ol.order_status
            FROM order_payouts p
            JOIN orders_ledger ol ON p.order_ledger_id = ol.id
            WHERE p.id = ?
        ''', (payout_id,)).fetchone()

        if not payout:
            raise ValueError(f"Payout {payout_id} not found")

        current_payout_status = PayoutStatus(payout['payout_status'])
        order_status = OrderStatus(payout['order_status'])

        # Check payout precondition
        if current_payout_status != PayoutStatus.PAYOUT_ON_HOLD:
            raise EscrowControlError(
                f"Cannot release payout in status {current_payout_status.value}. "
                f"Payout must be PAYOUT_ON_HOLD"
            )

        # Check order status precondition
        blocked_order_statuses = [
            OrderStatus.UNDER_REVIEW.value,
            OrderStatus.CANCELLED.value,
            OrderStatus.REFUNDED.value
        ]
        if order_status.value in blocked_order_statuses:
            raise EscrowControlError(
                f"Cannot release payout when order status is {order_status.value}"
            )

        # Update payout status
        conn.execute('''
            UPDATE order_payouts
            SET payout_status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (PayoutStatus.PAYOUT_READY.value, payout_id))

        # Log event
        _log_event_internal(
            conn, payout['order_id'], EventType.PAYOUT_RELEASED.value,
            ActorType.ADMIN.value, admin_id,
            {
                'payout_id': payout_id,
                'seller_id': payout['seller_id'],
                'previous_status': current_payout_status.value
            }
        )

        conn.commit()
        return True

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def process_refund(
    order_id: int,
    admin_id: int,
    refund_type: str,
    reason: str,
    seller_id: Optional[int] = None,
    order_item_ids: Optional[List[int]] = None
) -> Dict[str, Any]:
    """
    Admin action: Process a full or partial refund (ledger-only, no money movement).

    Rules (ENFORCE STRICTLY):
    - Refund NOT allowed if any affected payout_status == PAID_OUT
    - Partial refund allowed ONLY for items not shipped, payouts not paid out
    - Refund amount must NOT exceed captured gross for affected items

    Effects:
    - Update order_status: full → REFUNDED, partial → PARTIALLY_REFUNDED
    - For affected payouts: payout_status → PAYOUT_CANCELLED
    - Log events: REFUND_INITIATED, REFUND_COMPLETED

    Args:
        order_id: The order ID to refund
        admin_id: The admin user performing the action
        refund_type: "full" or "partial"
        reason: Required reason for the refund
        seller_id: For partial refund, target specific seller
        order_item_ids: For partial refund, target specific items

    Returns:
        Dict with refund details: {
            'refund_amount': float,
            'affected_items': int,
            'affected_payouts': List[int]
        }

    Raises:
        EscrowControlError: If rules are violated
        ValueError: If invalid parameters
    """
    if refund_type not in ('full', 'partial'):
        raise ValueError("refund_type must be 'full' or 'partial'")

    if not reason or not reason.strip():
        raise EscrowControlError("Reason is required for refund")

    # HARDENING: Partial refund validation rules
    if refund_type == 'partial':
        # Must provide EXACTLY one of seller_id or order_item_ids
        has_seller_id = seller_id is not None
        has_item_ids = order_item_ids is not None and len(order_item_ids) > 0

        if has_seller_id and has_item_ids:
            raise ValueError(
                "Partial refund must specify seller_id OR order_item_ids, not both"
            )
        if not has_seller_id and not has_item_ids:
            raise ValueError(
                "Partial refund requires either seller_id or order_item_ids"
            )

    conn = get_db_connection()
    try:
        # Get order ledger record
        order = conn.execute('''
            SELECT ol.*, u.username as buyer_username
            FROM orders_ledger ol
            JOIN users u ON ol.buyer_id = u.id
            WHERE ol.order_id = ?
        ''', (order_id,)).fetchone()

        if not order:
            raise ValueError(f"Order {order_id} not found in ledger")

        order_status = OrderStatus(order['order_status'])

        # Check if order is in a terminal state that blocks refund
        if order_status in [OrderStatus.REFUNDED, OrderStatus.CANCELLED]:
            raise EscrowControlError(
                f"Cannot refund order in status {order_status.value}"
            )

        # Get items and payouts based on refund scope
        if refund_type == 'full':
            # Full refund: all items, all payouts
            items = conn.execute('''
                SELECT * FROM order_items_ledger WHERE order_id = ?
            ''', (order_id,)).fetchall()

            payouts = conn.execute('''
                SELECT * FROM order_payouts WHERE order_id = ?
            ''', (order_id,)).fetchall()

        else:
            # Partial refund: targeted items/sellers
            if seller_id:
                items = conn.execute('''
                    SELECT * FROM order_items_ledger
                    WHERE order_id = ? AND seller_id = ?
                ''', (order_id, seller_id)).fetchall()
                payouts = conn.execute('''
                    SELECT * FROM order_payouts
                    WHERE order_id = ? AND seller_id = ?
                ''', (order_id, seller_id)).fetchall()

                # Validate seller has items in this order
                if not items:
                    raise ValueError(
                        f"Seller {seller_id} has no items in order {order_id}"
                    )

            else:  # order_item_ids
                # HARDENING: Validate all order_item_ids belong to this order
                placeholders = ','.join(['?'] * len(order_item_ids))
                items = conn.execute(f'''
                    SELECT * FROM order_items_ledger
                    WHERE order_id = ? AND id IN ({placeholders})
                ''', [order_id] + list(order_item_ids)).fetchall()

                # Check if all requested item IDs were found
                found_ids = set(item['id'] for item in items)
                requested_ids = set(order_item_ids)
                missing_ids = requested_ids - found_ids

                if missing_ids:
                    raise ValueError(
                        f"Item IDs {list(missing_ids)} not found in order {order_id}"
                    )

                # Get unique seller_ids from items
                item_seller_ids = list(set(item['seller_id'] for item in items))
                placeholders = ','.join(['?'] * len(item_seller_ids))
                payouts = conn.execute(f'''
                    SELECT * FROM order_payouts
                    WHERE order_id = ? AND seller_id IN ({placeholders})
                ''', [order_id] + item_seller_ids).fetchall()

        # STRICT CHECK: No affected payout can be PAID_OUT
        for payout in payouts:
            if payout['payout_status'] == PayoutStatus.PAID_OUT.value:
                raise EscrowControlError(
                    f"Cannot refund: Payout {payout['id']} for seller {payout['seller_id']} "
                    f"is already PAID_OUT"
                )

        # Calculate refund amount and collect detailed info for events
        refund_amount = sum(item['gross_amount'] for item in items)
        affected_payout_ids = [p['id'] for p in payouts]
        affected_seller_ids = list(set(p['seller_id'] for p in payouts))
        affected_item_ids = [item['id'] for item in items]

        # Log REFUND_INITIATED with detailed payload
        _log_event_internal(
            conn, order_id, EventType.REFUND_INITIATED.value,
            ActorType.ADMIN.value, admin_id,
            {
                'refund_type': refund_type,
                'reason': reason.strip(),
                'refund_amount': refund_amount,
                'affected_items_count': len(items),
                'affected_item_ids': affected_item_ids,
                'affected_seller_ids': affected_seller_ids,
                'affected_payout_ids': affected_payout_ids,
                'target_seller_id': seller_id if seller_id else None,
                'target_order_item_ids': list(order_item_ids) if order_item_ids else None
            }
        )

        # Cancel affected payouts
        if payouts:
            payout_ids = [p['id'] for p in payouts]
            placeholders = ','.join(['?'] * len(payout_ids))
            conn.execute(f'''
                UPDATE order_payouts
                SET payout_status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id IN ({placeholders})
            ''', [PayoutStatus.PAYOUT_CANCELLED.value] + payout_ids)

        # Update order status
        new_status = (OrderStatus.REFUNDED.value if refund_type == 'full'
                     else OrderStatus.PARTIALLY_REFUNDED.value)

        conn.execute('''
            UPDATE orders_ledger
            SET order_status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ?
        ''', (new_status, order_id))

        # Log REFUND_COMPLETED with detailed payload
        _log_event_internal(
            conn, order_id, EventType.REFUND_COMPLETED.value,
            ActorType.ADMIN.value, admin_id,
            {
                'refund_type': refund_type,
                'refund_amount': refund_amount,
                'new_order_status': new_status,
                'cancelled_payout_ids': affected_payout_ids,
                'affected_seller_ids': affected_seller_ids,
                'affected_item_ids': affected_item_ids
            }
        )

        conn.commit()

        return {
            'refund_amount': refund_amount,
            'affected_items': len(items),
            'affected_item_ids': affected_item_ids,
            'affected_payouts': affected_payout_ids,
            'affected_sellers': affected_seller_ids
        }

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def handle_report_auto_hold(
    report_id: int,
    order_id: int,
    reported_user_id: int,
    reporter_id: int
) -> Dict[str, Any]:
    """
    Automatically hold funds when a report is filed.

    Behavior:
    - If reported_user_id == buyer: hold entire order
    - If reported_user_id == seller: hold ONLY that seller's payout(s)
    - Create REPORT_CREATED event

    Args:
        report_id: The report ID
        order_id: The order ID referenced in the report
        reported_user_id: The user being reported
        reporter_id: The user filing the report

    Returns:
        Dict with hold details

    Raises:
        ValueError: If order not found
    """
    conn = get_db_connection()
    try:
        # Get order ledger record
        order = conn.execute('''
            SELECT ol.*, o.buyer_id
            FROM orders_ledger ol
            JOIN orders o ON ol.order_id = o.id
            WHERE ol.order_id = ?
        ''', (order_id,)).fetchone()

        if not order:
            raise ValueError(f"Order {order_id} not found in ledger")

        order_status = OrderStatus(order['order_status'])

        # Check if order is in a state that allows hold
        blocked_statuses = [s.value for s in ORDER_HOLD_BLOCKED_STATUSES]
        if order_status.value in blocked_statuses:
            # Can't hold, but still log the report event
            _log_event_internal(
                conn, order_id, EventType.REPORT_CREATED.value,
                ActorType.BUYER.value if reporter_id == order['buyer_id'] else ActorType.SELLER.value,
                reporter_id,
                {
                    'report_id': report_id,
                    'reported_user_id': reported_user_id,
                    'auto_hold_applied': False,
                    'reason': f'Order in {order_status.value} status, no hold applied'
                }
            )
            conn.commit()
            return {
                'hold_type': None,
                'reason': f'Order status {order_status.value} does not allow holds'
            }

        is_buyer_reported = reported_user_id == order['buyer_id']

        if is_buyer_reported:
            # Hold entire order
            conn.execute('''
                UPDATE orders_ledger
                SET order_status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE order_id = ?
            ''', (OrderStatus.UNDER_REVIEW.value, order_id))

            # Hold ALL payouts
            conn.execute('''
                UPDATE order_payouts
                SET payout_status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE order_id = ? AND payout_status NOT IN (?, ?)
            ''', (
                PayoutStatus.PAYOUT_ON_HOLD.value, order_id,
                PayoutStatus.PAID_OUT.value, PayoutStatus.PAYOUT_CANCELLED.value
            ))

            hold_type = 'order'
            affected_payouts = conn.execute('''
                SELECT id FROM order_payouts
                WHERE order_id = ? AND payout_status = ?
            ''', (order_id, PayoutStatus.PAYOUT_ON_HOLD.value)).fetchall()
            affected_payout_ids = [p['id'] for p in affected_payouts]

        else:
            # Hold only the reported seller's payout(s)
            conn.execute('''
                UPDATE order_payouts
                SET payout_status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE order_id = ? AND seller_id = ? AND payout_status NOT IN (?, ?)
            ''', (
                PayoutStatus.PAYOUT_ON_HOLD.value, order_id, reported_user_id,
                PayoutStatus.PAID_OUT.value, PayoutStatus.PAYOUT_CANCELLED.value
            ))

            hold_type = 'payout'
            affected_payouts = conn.execute('''
                SELECT id FROM order_payouts
                WHERE order_id = ? AND seller_id = ? AND payout_status = ?
            ''', (order_id, reported_user_id, PayoutStatus.PAYOUT_ON_HOLD.value)).fetchall()
            affected_payout_ids = [p['id'] for p in affected_payouts]

        # Log REPORT_CREATED event
        _log_event_internal(
            conn, order_id, EventType.REPORT_CREATED.value,
            ActorType.BUYER.value if reporter_id == order['buyer_id'] else ActorType.SELLER.value,
            reporter_id,
            {
                'report_id': report_id,
                'reported_user_id': reported_user_id,
                'reported_is_buyer': is_buyer_reported,
                'auto_hold_applied': True,
                'hold_type': hold_type,
                'affected_payout_ids': affected_payout_ids
            }
        )

        conn.commit()

        return {
            'hold_type': hold_type,
            'affected_payout_ids': affected_payout_ids
        }

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
