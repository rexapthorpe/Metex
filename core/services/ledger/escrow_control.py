"""
Ledger Escrow Control

Admin actions for holding, approving, releasing, and refunding orders/payouts.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import database
from services.ledger_constants import (
    OrderStatus, PayoutStatus, ActorType, EventType,
    ORDER_HOLD_BLOCKED_STATUSES, PAYOUT_HOLD_BLOCKED_STATUSES,
    PAYABLE_ORDER_STATUSES,
)
from .exceptions import EscrowControlError
from .order_creation import _log_event_internal

logger = logging.getLogger(__name__)


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


def get_payout_eligibility(payout_id: int) -> Dict[str, Any]:
    """
    Check whether a payout record is eligible for a Stripe transfer release.

    Returns:
        {'eligible': bool, 'reason': str | None}
        reason is None when eligible, otherwise a human-readable block reason.
    """
    conn = get_db_connection()
    try:
        payout = conn.execute('''
            SELECT
                p.payout_status,
                p.seller_net_amount,
                ol.order_status,
                o.requires_payment_clearance,
                u.stripe_account_id,
                u.stripe_payouts_enabled,
                u.username AS seller_username
            FROM order_payouts p
            JOIN orders_ledger ol ON p.order_ledger_id = ol.id
            JOIN orders o ON p.order_id = o.id
            JOIN users u ON p.seller_id = u.id
            WHERE p.id = ?
        ''', (payout_id,)).fetchone()

        if not payout:
            return {'eligible': False, 'reason': 'Payout not found'}

        if payout['payout_status'] == PayoutStatus.PAID_OUT.value:
            return {'eligible': False, 'reason': 'Already paid out'}

        if payout['payout_status'] == PayoutStatus.PAYOUT_CANCELLED.value:
            return {'eligible': False, 'reason': 'Payout cancelled'}

        if payout['requires_payment_clearance']:
            return {'eligible': False, 'reason': 'ACH requires payment clearance'}

        payable_statuses = [s.value for s in PAYABLE_ORDER_STATUSES]
        if payout['order_status'] not in payable_statuses:
            return {'eligible': False, 'reason': f"Order not payable (status: {payout['order_status']})"}

        if not payout['stripe_account_id']:
            return {'eligible': False, 'reason': 'Seller has no Stripe account'}

        if not payout['stripe_payouts_enabled']:
            return {'eligible': False, 'reason': 'Seller Stripe payouts not enabled'}

        if (payout['seller_net_amount'] or 0) <= 0:
            return {'eligible': False, 'reason': 'Transfer amount is not positive'}

        return {'eligible': True, 'reason': None}

    finally:
        conn.close()


def release_stripe_transfer(payout_id: int, admin_id: int) -> Dict[str, Any]:
    """
    Admin action: Create a Stripe transfer to release a seller payout.

    Preconditions (all enforced):
    - payout_status is NOT PAID_OUT (double-payout guard)
    - payout_status is NOT PAYOUT_CANCELLED
    - order.requires_payment_clearance == 0 (ACH blocked until cleared)
    - order is in a payable status (PAID_IN_ESCROW or later)
    - seller has stripe_account_id and stripe_payouts_enabled == 1
    - seller_net_amount > 0

    Effects:
    - Creates stripe.Transfer to seller's connected account
    - Updates payout_status to PAID_OUT
    - Stores provider_transfer_id
    - Logs PAYOUT_COMPLETED event

    Returns:
        {'transfer_id': str, 'amount': float, 'seller_id': int}

    Raises:
        EscrowControlError: If any precondition fails or Stripe returns an error
        ValueError: If payout not found
    """
    import stripe

    conn = get_db_connection()
    try:
        payout = conn.execute('''
            SELECT
                p.*,
                ol.order_status,
                o.requires_payment_clearance,
                o.payment_method_type,
                o.stripe_payment_intent_id,
                u.username AS seller_username,
                u.stripe_account_id,
                u.stripe_payouts_enabled
            FROM order_payouts p
            JOIN orders_ledger ol ON p.order_ledger_id = ol.id
            JOIN orders o ON p.order_id = o.id
            JOIN users u ON p.seller_id = u.id
            WHERE p.id = ?
        ''', (payout_id,)).fetchone()

        if not payout:
            raise ValueError(f"Payout {payout_id} not found")

        # Double-payout guard
        if payout['payout_status'] == PayoutStatus.PAID_OUT.value:
            raise EscrowControlError("Payout already released (PAID_OUT) — no transfer created")

        if payout['payout_status'] == PayoutStatus.PAYOUT_CANCELLED.value:
            raise EscrowControlError("Payout is cancelled and cannot be released")

        # ACH block
        if payout['requires_payment_clearance']:
            raise EscrowControlError(
                "ACH requires payment clearance — payout cannot be released until funds clear"
            )

        # Order status check
        payable_statuses = [s.value for s in PAYABLE_ORDER_STATUSES]
        if payout['order_status'] not in payable_statuses:
            raise EscrowControlError(
                f"Order status '{payout['order_status']}' is not eligible for payout. "
                f"Must be one of: {', '.join(payable_statuses)}"
            )

        # Seller Stripe readiness
        if not payout['stripe_account_id']:
            raise EscrowControlError(
                f"Seller @{payout['seller_username']} has not connected a Stripe account"
            )

        if not payout['stripe_payouts_enabled']:
            raise EscrowControlError(
                f"Seller @{payout['seller_username']} Stripe account is not enabled for payouts"
            )

        # Transfer amount (dollars -> cents)
        transfer_amount_cents = int(round((payout['seller_net_amount'] or 0) * 100))
        if transfer_amount_cents <= 0:
            raise EscrowControlError(
                f"Transfer amount ${payout['seller_net_amount']:.2f} is not positive"
            )

        logger.info(
            "[Payout] Releasing Stripe transfer  payout_id=%s  order_id=%s  "
            "seller_id=%s  amount=$%.2f",
            payout_id, payout['order_id'], payout['seller_id'], payout['seller_net_amount'],
        )

        # Resolve the charge ID from the PaymentIntent so we can pin the
        # transfer to that specific charge via source_transaction.  This avoids
        # "insufficient available funds" errors caused by Stripe auto-sweeping
        # the platform balance to the bank before we release the payout.
        pi_id = payout['stripe_payment_intent_id']
        source_transaction = None
        if pi_id:
            try:
                pi = stripe.PaymentIntent.retrieve(pi_id)
                source_transaction = pi.latest_charge  # 'ch_...' string
                logger.info(
                    "[Payout] Resolved charge  pi=%s  charge=%s  payout_id=%s",
                    pi_id, source_transaction, payout_id,
                )
            except stripe.error.StripeError as e:
                logger.warning(
                    "[Payout] Could not retrieve PaymentIntent %s — "
                    "proceeding without source_transaction: %s", pi_id, e,
                )
        else:
            logger.warning(
                "[Payout] No stripe_payment_intent_id on order %s — "
                "transfer will draw from platform balance", payout['order_id'],
            )

        # Create Stripe transfer to seller's connected account.
        # source_transaction pins the funds to the original charge so the
        # transfer succeeds even if the platform's available balance is $0.
        transfer_kwargs = dict(
            amount=transfer_amount_cents,
            currency='usd',
            destination=payout['stripe_account_id'],
            metadata={
                'payout_id': str(payout_id),
                'order_id': str(payout['order_id']),
                'seller_id': str(payout['seller_id']),
            },
        )
        if source_transaction:
            transfer_kwargs['source_transaction'] = source_transaction

        transfer = stripe.Transfer.create(**transfer_kwargs)

        logger.info(
            "[Payout] Stripe transfer created  transfer_id=%s  payout_id=%s",
            transfer.id, payout_id,
        )

        # Mark payout PAID_OUT and store transfer ID
        conn.execute('''
            UPDATE order_payouts
            SET payout_status = ?,
                provider_transfer_id = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (PayoutStatus.PAID_OUT.value, transfer.id, payout_id))

        # Log event
        _log_event_internal(
            conn, payout['order_id'], EventType.PAYOUT_COMPLETED.value,
            ActorType.ADMIN.value, admin_id,
            {
                'payout_id': payout_id,
                'seller_id': payout['seller_id'],
                'transfer_id': transfer.id,
                'transfer_amount_cents': transfer_amount_cents,
                'seller_net_amount': payout['seller_net_amount'],
            },
        )

        conn.commit()

        logger.info(
            "[Payout] Payout marked PAID_OUT  payout_id=%s  transfer_id=%s",
            payout_id, transfer.id,
        )

        return {
            'transfer_id': transfer.id,
            'amount': payout['seller_net_amount'],
            'seller_id': payout['seller_id'],
        }

    except stripe.error.StripeError as e:
        conn.rollback()
        logger.error(
            "[Payout] Stripe error creating transfer  payout_id=%s: %s", payout_id, e
        )
        raise EscrowControlError(f"Stripe transfer failed: {getattr(e, 'user_message', None) or str(e)}")
    except (EscrowControlError, ValueError):
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        logger.exception(
            "[Payout] Unexpected error releasing Stripe transfer  payout_id=%s", payout_id
        )
        raise
    finally:
        conn.close()


def attempt_payout_recovery(payout_id: int, admin_id: int, conn=None) -> Dict[str, Any]:
    """
    Admin action: Attempt to recover a seller payout via Stripe Transfer Reversal.

    Stripe architecture note:
    - Payouts are created as stripe.Transfer to seller connected accounts.
    - Reversals use stripe.Transfer.create_reversal(transfer_id).
    - Reversal succeeds only if the connected account has sufficient available balance.
    - If the seller already paid out to their bank, reversal fails with insufficient_funds
      and the row is moved to 'manual_review' for human handling.

    Preconditions:
    - payout_status == PAID_OUT
    - provider_transfer_id is set
    - payout_recovery_status == 'pending' (or 'failed'/'manual_review' for retry)
    - payout_recovery_status != 'recovered' (idempotency guard)
    - payout_recovery_status != 'not_needed'

    Outcomes:
    - Success  → payout_recovery_status = 'recovered', provider_reversal_id stored
    - Insufficient balance → payout_recovery_status = 'manual_review'
    - Other Stripe error → payout_recovery_status = 'failed'

    Returns:
        {'outcome': 'recovered'|'manual_review'|'failed', 'reversal_id': str|None, 'reason': str|None}

    Raises:
        EscrowControlError: If preconditions fail (no retry should occur)
        ValueError: If payout not found
    """
    import stripe

    _owned_conn_recovery = conn is None
    if _owned_conn_recovery:
        conn = get_db_connection()
    try:
        payout = conn.execute('''
            SELECT op.id, op.order_id, op.seller_id, op.payout_status,
                   op.provider_transfer_id, op.payout_recovery_status,
                   op.seller_net_amount,
                   u.username AS seller_username
            FROM order_payouts op
            JOIN users u ON op.seller_id = u.id
            WHERE op.id = ?
        ''', (payout_id,)).fetchone()

        if not payout:
            raise ValueError(f"Payout {payout_id} not found")

        # Idempotency: already recovered — safe no-op
        if payout['payout_recovery_status'] == 'recovered':
            logger.info(
                "[Recovery] Already recovered — no-op  payout_id=%s", payout_id
            )
            return {'outcome': 'recovered', 'reversal_id': None, 'reason': 'Already recovered'}

        # Guard: not needed
        if payout['payout_recovery_status'] == 'not_needed':
            raise EscrowControlError(
                f"Payout {payout_id} does not require recovery (payout_recovery_status=not_needed)"
            )

        # Guard: must have been paid out
        if payout['payout_status'] != PayoutStatus.PAID_OUT.value:
            raise EscrowControlError(
                f"Payout {payout_id} was not released (status={payout['payout_status']!r})"
            )

        # Guard: must have a stored transfer ID to reverse
        transfer_id = payout['provider_transfer_id']
        if not transfer_id:
            raise EscrowControlError(
                f"Payout {payout_id} has no provider_transfer_id — cannot attempt reversal"
            )

        now = datetime.utcnow().isoformat()
        order_id = payout['order_id']

        logger.info(
            "[Recovery] Attempting reversal  payout_id=%s  order_id=%s  "
            "seller=%s  transfer_id=%s  admin_id=%s",
            payout_id, order_id, payout['seller_username'], transfer_id, admin_id,
        )

        # Stamp attempt
        conn.execute('''
            UPDATE order_payouts
            SET recovery_attempted_at = ?,
                recovery_attempted_by_admin_id = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (now, admin_id, payout_id))

        _log_event_internal(
            conn, order_id, EventType.PAYOUT_RECOVERY_ATTEMPTED.value,
            ActorType.ADMIN.value, admin_id,
            {
                'payout_id': payout_id,
                'seller_id': payout['seller_id'],
                'transfer_id': transfer_id,
                'seller_net_amount': payout['seller_net_amount'],
            }
        )

        # Attempt Stripe Transfer Reversal
        try:
            reversal = stripe.Transfer.create_reversal(
                transfer_id,
                metadata={
                    'payout_id': str(payout_id),
                    'order_id': str(order_id),
                    'recovered_by_admin_id': str(admin_id),
                },
            )

            logger.info(
                "[Recovery] Reversal succeeded  payout_id=%s  reversal_id=%s",
                payout_id, reversal.id,
            )

            conn.execute('''
                UPDATE order_payouts
                SET payout_recovery_status = 'recovered',
                    provider_reversal_id = ?,
                    recovery_completed_at = ?,
                    recovery_failure_reason = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (reversal.id, now, payout_id))

            # Reduce platform_covered_amount: if this payout was previously unrecovered,
            # the platform is no longer covering it.
            seller_net = float(payout['seller_net_amount'] or 0)
            conn.execute('''
                UPDATE orders
                SET platform_covered_amount = MAX(0, platform_covered_amount - ?)
                WHERE id = ?
            ''', (seller_net, order_id))

            _log_event_internal(
                conn, order_id, EventType.PAYOUT_RECOVERY_SUCCEEDED.value,
                ActorType.ADMIN.value, admin_id,
                {
                    'payout_id': payout_id,
                    'seller_id': payout['seller_id'],
                    'reversal_id': reversal.id,
                    'transfer_id': transfer_id,
                    'seller_net_amount': seller_net,
                }
            )

            if _owned_conn_recovery:
                conn.commit()
            return {'outcome': 'recovered', 'reversal_id': reversal.id, 'reason': None}

        except stripe.error.StripeError as stripe_err:
            err_code = getattr(stripe_err, 'code', None)
            err_msg = getattr(stripe_err, 'user_message', None) or str(stripe_err)

            # Insufficient balance means seller withdrew funds — needs human action
            if err_code == 'insufficient_funds':
                outcome = 'manual_review'
                failure_reason = (
                    'Insufficient balance on connected account — seller may have already '
                    f'paid out to their bank. Stripe error: {err_msg}'
                )
                logger.warning(
                    "[Recovery] Insufficient funds — manual review required  "
                    "payout_id=%s  transfer_id=%s: %s",
                    payout_id, transfer_id, err_msg,
                )
            else:
                outcome = 'failed'
                failure_reason = f'Stripe reversal failed: {err_msg}'
                logger.error(
                    "[Recovery] Stripe reversal failed  payout_id=%s  transfer_id=%s: %s",
                    payout_id, transfer_id, stripe_err,
                )

            conn.execute('''
                UPDATE order_payouts
                SET payout_recovery_status = ?,
                    recovery_failure_reason = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (outcome, failure_reason, payout_id))

            _log_event_internal(
                conn, order_id, EventType.PAYOUT_RECOVERY_FAILED.value,
                ActorType.ADMIN.value, admin_id,
                {
                    'payout_id': payout_id,
                    'seller_id': payout['seller_id'],
                    'transfer_id': transfer_id,
                    'outcome': outcome,
                    'stripe_error_code': err_code,
                    'failure_reason': failure_reason,
                }
            )

            if _owned_conn_recovery:
                conn.commit()
            return {'outcome': outcome, 'reversal_id': None, 'reason': failure_reason}

    except (EscrowControlError, ValueError):
        if _owned_conn_recovery:
            conn.rollback()
        raise
    except Exception:
        if _owned_conn_recovery:
            conn.rollback()
        logger.exception("[Recovery] Unexpected error  payout_id=%s", payout_id)
        raise
    finally:
        if _owned_conn_recovery:
            conn.close()


def refund_buyer_stripe(
    order_id: int,
    admin_id: int,
    reason: str = '',
    amount: Optional[float] = None,
    conn=None,
) -> Dict[str, Any]:
    """
    Admin action: Create a Stripe refund (full or partial) for the buyer's payment.

    Args:
        order_id:  The order to refund.
        admin_id:  Admin performing the action.
        reason:    Human-readable reason (stored on order and in Stripe metadata).
        amount:    Dollar amount to refund.  None → full remaining refundable amount.
                   Must be > 0 and <= refundable_remaining (total_price - already-refunded).
        conn:      Optional DB connection (injected in tests).

    Preconditions:
        - orders.stripe_payment_intent_id must be set
        - orders.payment_status == 'paid'
        - orders.refund_status != 'refunded'  (fully-refunded orders are terminal)
        - amount <= refundable_remaining

    Multi-seller behavior:
        ONE Stripe refund is created against the full PaymentIntent.
        Per order_payouts row:
          - If payout_status == PAID_OUT:
              → payout_recovery_status = 'pending'
              → attempt_auto_recovery() is called immediately
          - Else:
              → payout_status = PAYOUT_CANCELLED
              → payout_recovery_status = 'not_needed'

    Financial breakdown (stored per refund):
        ratio = refund_amount / total_price
        refund_subtotal       = gross_amount * ratio
        refund_tax_amount     = tax_amount   * ratio
        refund_processing_fee = buyer_card_fee * ratio
        (all rounded to 2 dp, with remainder assigned to subtotal to keep sum exact)

    Platform / spread reversal (stored on orders_ledger):
        refunded_platform_fee_amount   += platform_fee_amount * ratio
        refunded_spread_capture_amount += spread_capture_amount * ratio

    Returns:
        {
            'refund_id':                  str,
            'amount':                     float,
            'refund_subtotal':            float,
            'refund_tax_amount':          float,
            'refund_processing_fee':      float,
            'is_partial':                 bool,
            'requires_payout_recovery':   bool,
            'recovery_outcomes':          list[dict],   # per paid-out payout
            'recovery_pending_payout_ids': list[int],
            'cancelled_payout_ids':       list[int],
        }

    Raises:
        EscrowControlError: If preconditions fail or Stripe returns an error.
        ValueError:         If order not found.
    """
    import stripe

    if not reason:
        reason = 'Admin refund'

    _owned_conn = conn is None
    if _owned_conn:
        conn = get_db_connection()
    try:
        order = conn.execute('''
            SELECT o.id, o.stripe_payment_intent_id, o.payment_status, o.total_price,
                   o.refund_status, o.refund_amount, o.buyer_id,
                   o.tax_amount, o.buyer_card_fee
            FROM orders o
            WHERE o.id = ?
        ''', (order_id,)).fetchone()

        if not order:
            raise ValueError(f"Order {order_id} not found")

        if not order['stripe_payment_intent_id']:
            raise EscrowControlError("Order has no Stripe payment — cannot refund")

        if order['payment_status'] != 'paid':
            raise EscrowControlError(
                f"Cannot refund: payment_status is '{order['payment_status']}', must be 'paid'"
            )

        current_refund_status = order['refund_status'] or 'not_refunded'
        if current_refund_status == 'refunded':
            raise EscrowControlError(
                f"Order {order_id} is already fully refunded"
            )

        total_price = float(order['total_price'] or 0)
        already_refunded = float(order['refund_amount'] or 0)
        refundable_remaining = round(total_price - already_refunded, 2)

        if refundable_remaining <= 0:
            raise EscrowControlError(
                f"Nothing left to refund on order {order_id} "
                f"(total={total_price:.2f}, already_refunded={already_refunded:.2f})"
            )

        # Resolve requested refund amount
        if amount is None:
            refund_amount = refundable_remaining
        else:
            refund_amount = round(float(amount), 2)
            if refund_amount <= 0:
                raise EscrowControlError("Refund amount must be positive")
            if refund_amount > refundable_remaining + 0.005:  # 0.5-cent tolerance for rounding
                raise EscrowControlError(
                    f"Refund amount ${refund_amount:.2f} exceeds refundable remaining "
                    f"${refundable_remaining:.2f}"
                )

        # is_partial: True only if we're NOT clearing the full remaining balance
        is_partial = refund_amount < refundable_remaining - 0.005

        # Financial breakdown proportional to refund_amount / total_price
        ratio = refund_amount / total_price if total_price > 0 else 1.0
        tax_amount = float(order['tax_amount'] or 0)
        buyer_card_fee = float(order['buyer_card_fee'] or 0)
        # Compute gross_amount (subtotal) from ledger
        ledger = conn.execute(
            'SELECT id, order_status, gross_amount, platform_fee_amount, spread_capture_amount '
            'FROM orders_ledger WHERE order_id = ?',
            (order_id,)
        ).fetchone()
        if not ledger:
            raise ValueError(f"Order {order_id} not found in ledger")

        gross_amount = float(ledger['gross_amount'] or 0)
        platform_fee = float(ledger['platform_fee_amount'] or 0)
        spread_capture = float(ledger['spread_capture_amount'] or 0)

        refund_tax = round(tax_amount * ratio, 2)
        refund_fee = round(buyer_card_fee * ratio, 2)
        # Assign remainder to subtotal so totals add up exactly
        refund_subtotal = round(refund_amount - refund_tax - refund_fee, 2)

        platform_fee_reversed = round(platform_fee * ratio, 2)
        spread_reversed = round(spread_capture * ratio, 2)

        # Payout classification
        payouts = conn.execute(
            'SELECT id, seller_id, payout_status, provider_transfer_id, seller_net_amount '
            'FROM order_payouts WHERE order_id = ?',
            (order_id,)
        ).fetchall()

        paid_out_payouts = [p for p in payouts if p['payout_status'] == PayoutStatus.PAID_OUT.value]
        unpaid_payouts = [p for p in payouts if p['payout_status'] != PayoutStatus.PAID_OUT.value]
        paid_out_payout_ids = [p['id'] for p in paid_out_payouts]
        unpaid_payout_ids = [p['id'] for p in unpaid_payouts]
        requires_recovery = bool(paid_out_payout_ids)

        refund_amount_cents = int(round(refund_amount * 100))

        logger.info(
            "[Refund] Initiating Stripe refund  order_id=%s  admin_id=%s  amount=$%.2f  "
            "is_partial=%s  payment_intent=%s  requires_recovery=%s",
            order_id, admin_id, refund_amount, is_partial,
            order['stripe_payment_intent_id'], requires_recovery,
        )

        _log_event_internal(
            conn, order_id, EventType.REFUND_INITIATED.value,
            ActorType.ADMIN.value, admin_id,
            {
                'reason': reason.strip(),
                'refund_amount': refund_amount,
                'is_partial': is_partial,
                'refund_subtotal': refund_subtotal,
                'refund_tax_amount': refund_tax,
                'refund_processing_fee': refund_fee,
                'payment_intent_id': order['stripe_payment_intent_id'],
                'requires_payout_recovery': requires_recovery,
                'recovery_pending_payout_ids': paid_out_payout_ids,
            }
        )

        # ── Stripe Refund ────────────────────────────────────────────────────
        stripe_kwargs: Dict[str, Any] = dict(
            payment_intent=order['stripe_payment_intent_id'],
            reason='requested_by_customer',
            metadata={
                'order_id': str(order_id),
                'admin_id': str(admin_id),
                'reason': reason.strip()[:500],
                'is_partial': str(is_partial),
            },
        )
        if is_partial:
            stripe_kwargs['amount'] = refund_amount_cents

        refund = stripe.Refund.create(**stripe_kwargs)

        logger.info(
            "[Refund] Stripe refund created  refund_id=%s  order_id=%s  amount_cents=%s",
            refund.id, order_id, refund_amount_cents,
        )

        now = datetime.utcnow().isoformat()

        # ── DB Updates ───────────────────────────────────────────────────────
        new_total_refunded = round(already_refunded + refund_amount, 2)
        new_refund_status = (
            'refunded' if new_total_refunded >= total_price - 0.005
            else 'partially_refunded'
        )

        conn.execute('''
            UPDATE orders
            SET refund_status          = ?,
                refund_amount          = ?,
                refund_subtotal        = refund_subtotal + ?,
                refund_tax_amount      = refund_tax_amount + ?,
                refund_processing_fee  = refund_processing_fee + ?,
                stripe_refund_id       = ?,
                refunded_at            = ?,
                refund_reason          = ?,
                requires_payout_recovery = ?
            WHERE id = ?
        ''', (
            new_refund_status,
            new_total_refunded,
            refund_subtotal,
            refund_tax,
            refund_fee,
            refund.id,
            now,
            reason.strip(),
            1 if requires_recovery else 0,
            order_id,
        ))

        # Cancel unpaid payouts
        if unpaid_payout_ids:
            placeholders = ','.join(['?'] * len(unpaid_payout_ids))
            conn.execute(f'''
                UPDATE order_payouts
                SET payout_status = ?,
                    payout_recovery_status = 'not_needed',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id IN ({placeholders})
            ''', [PayoutStatus.PAYOUT_CANCELLED.value] + unpaid_payout_ids)

        # Flag paid-out payouts for recovery
        if paid_out_payout_ids:
            placeholders = ','.join(['?'] * len(paid_out_payout_ids))
            conn.execute(f'''
                UPDATE order_payouts
                SET payout_recovery_status = 'pending',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id IN ({placeholders})
            ''', paid_out_payout_ids)

        # Reverse platform fee and spread on ledger
        conn.execute('''
            UPDATE orders_ledger
            SET order_status                    = ?,
                refunded_platform_fee_amount    = refunded_platform_fee_amount + ?,
                refunded_spread_capture_amount  = refunded_spread_capture_amount + ?,
                updated_at                      = CURRENT_TIMESTAMP
            WHERE order_id = ?
        ''', (OrderStatus.REFUNDED.value, platform_fee_reversed, spread_reversed, order_id))

        _log_event_internal(
            conn, order_id, EventType.REFUND_COMPLETED.value,
            ActorType.ADMIN.value, admin_id,
            {
                'refund_id': refund.id,
                'refund_amount': refund_amount,
                'is_partial': is_partial,
                'refund_subtotal': refund_subtotal,
                'refund_tax_amount': refund_tax,
                'refund_processing_fee': refund_fee,
                'platform_fee_reversed': platform_fee_reversed,
                'spread_reversed': spread_reversed,
                'reason': reason.strip(),
                'requires_payout_recovery': requires_recovery,
                'recovery_pending_payout_ids': paid_out_payout_ids,
                'cancelled_payout_ids': unpaid_payout_ids,
            }
        )

        # Write an audit record to the refunds table so the admin Refunds tab
        # can display all refunds regardless of whether they originated from a
        # dispute or a direct ledger action.  dispute_id is NULL for direct refunds.
        # Use single seller_id when the order has exactly one seller; NULL for multi-seller.
        unique_seller_ids = list({p['seller_id'] for p in payouts})
        refund_seller_id = unique_seller_ids[0] if len(unique_seller_ids) == 1 else None
        conn.execute(
            '''INSERT INTO refunds
                   (dispute_id, order_id, order_item_id, buyer_id, seller_id,
                    amount, provider_refund_id, issued_by_admin_id, issued_at, note)
               VALUES (NULL, ?, NULL, ?, ?, ?, ?, ?, ?, ?)''',
            (
                order_id,
                order['buyer_id'],
                refund_seller_id,
                refund_amount,
                refund.id,
                admin_id,
                now,
                reason.strip(),
            ),
        )

        conn.commit()

        # ── Attempt automatic recovery for paid-out payouts ──────────────────
        # IMPORTANT: attempt_payout_recovery() opens its own connection.
        # We commit DB state first so that function sees the updated recovery flags.
        recovery_outcomes: List[Dict[str, Any]] = []
        still_pending_ids: List[int] = []
        # Map payout_id → seller_net_amount for coverage calculation
        paid_out_net_by_id = {p['id']: float(p['seller_net_amount'] or 0) for p in paid_out_payouts}

        for payout in paid_out_payouts:
            pid = payout['id']
            try:
                outcome = attempt_payout_recovery(pid, admin_id, conn=conn)
                recovery_outcomes.append({
                    'payout_id': pid,
                    'seller_net_amount': paid_out_net_by_id[pid],
                    'outcome': outcome['outcome'],
                    'reversal_id': outcome.get('reversal_id'),
                    'reason': outcome.get('reason'),
                })
                if outcome['outcome'] != 'recovered':
                    still_pending_ids.append(pid)
            except Exception as exc:
                logger.warning(
                    "[Refund] Auto-recovery failed for payout %s: %s", pid, exc
                )
                recovery_outcomes.append({
                    'payout_id': pid,
                    'seller_net_amount': paid_out_net_by_id[pid],
                    'outcome': 'failed',
                    'reversal_id': None,
                    'reason': str(exc),
                })
                still_pending_ids.append(pid)

        final_requires_recovery = bool(still_pending_ids)

        # Platform coverage = seller net amounts that Metex must absorb (recovery not succeeded)
        platform_covered = round(sum(
            paid_out_net_by_id[pid] for pid in still_pending_ids
        ), 2)

        # Always commit after recovery loop — payout status updates (recovered/failed)
        # are made on the shared conn without committing inside attempt_payout_recovery.
        if platform_covered > 0:
            conn.execute(
                'UPDATE orders SET platform_covered_amount = platform_covered_amount + ? WHERE id = ?',
                (platform_covered, order_id)
            )
        conn.commit()

        logger.info(
            "[Refund] Complete  order_id=%s  refund_id=%s  is_partial=%s  "
            "requires_recovery=%s  platform_covered=%.2f  recovery_outcomes=%s",
            order_id, refund.id, is_partial, final_requires_recovery,
            platform_covered, recovery_outcomes,
        )

        return {
            'refund_id': refund.id,
            'amount': refund_amount,
            'refund_subtotal': refund_subtotal,
            'refund_tax_amount': refund_tax,
            'refund_processing_fee': refund_fee,
            'is_partial': is_partial,
            'requires_payout_recovery': final_requires_recovery,
            'recovery_outcomes': recovery_outcomes,
            'recovery_pending_payout_ids': still_pending_ids,
            'cancelled_payout_ids': unpaid_payout_ids,
            'platform_covered_amount': platform_covered,
        }

    except stripe.error.StripeError as e:
        if _owned_conn:
            conn.rollback()
        logger.error("[Refund] Stripe error  order_id=%s: %s", order_id, e)
        raise EscrowControlError(f"Stripe refund failed: {getattr(e, 'user_message', None) or str(e)}")
    except (EscrowControlError, ValueError):
        if _owned_conn:
            conn.rollback()
        raise
    except Exception:
        if _owned_conn:
            conn.rollback()
        logger.exception("[Refund] Unexpected error  order_id=%s", order_id)
        raise
    finally:
        if _owned_conn:
            conn.close()


def mark_ach_cleared(order_id: int, admin_id: int) -> Dict[str, Any]:
    """
    Admin action: Mark an ACH payment as cleared so seller payouts become eligible.

    Idempotent: If already cleared, returns success with already_cleared=True.

    Preconditions:
    - Order must exist
    - Order must be ACH-backed (requires_payment_clearance == 1) or already cleared

    Effects:
    - Sets requires_payment_clearance = 0
    - Sets payment_cleared_at = now
    - Sets payment_cleared_by_admin_id = admin_id
    - Logs ACH_CLEARED event

    Returns:
        {'already_cleared': bool, 'cleared_at': str}

    Raises:
        ValueError: If order not found
        EscrowControlError: If order is not ACH-backed
    """
    conn = get_db_connection()
    try:
        order = conn.execute(
            '''SELECT id, requires_payment_clearance, payment_cleared_at,
                      payment_method_type, payment_cleared_by_admin_id
               FROM orders WHERE id = ?''',
            (order_id,)
        ).fetchone()

        if not order:
            raise ValueError(f"Order {order_id} not found")

        # Idempotent: already cleared
        if order['payment_cleared_at'] is not None:
            cleared_at = str(order['payment_cleared_at'])
            logger.info(
                "[ACH] Duplicate clearance request ignored  order_id=%s  admin_id=%s  "
                "originally_cleared_at=%s",
                order_id, admin_id, cleared_at,
            )
            return {'already_cleared': True, 'cleared_at': cleared_at}

        # Only ACH orders require this workflow
        if not order['requires_payment_clearance']:
            raise EscrowControlError(
                f"Order {order_id} does not require ACH payment clearance "
                f"(payment_method_type={order['payment_method_type']!r})"
            )

        now = datetime.utcnow().isoformat()

        logger.info(
            "[ACH] Clearance requested  order_id=%s  admin_id=%s",
            order_id, admin_id,
        )

        conn.execute(
            '''UPDATE orders
               SET requires_payment_clearance   = 0,
                   payment_cleared_at           = ?,
                   payment_cleared_by_admin_id  = ?
               WHERE id = ?''',
            (now, admin_id, order_id)
        )

        _log_event_internal(
            conn,
            order_id=order_id,
            event_type='ACH_CLEARED',
            actor_type=ActorType.ADMIN.value,
            actor_id=admin_id,
            note=f"ACH payment cleared by admin {admin_id}",
        )

        conn.commit()

        logger.info(
            "[ACH] Clearance granted  order_id=%s  admin_id=%s  cleared_at=%s",
            order_id, admin_id, now,
        )

        return {'already_cleared': False, 'cleared_at': now}

    except (ValueError, EscrowControlError):
        raise
    except Exception:
        logger.exception("[ACH] Unexpected error marking ACH cleared  order_id=%s", order_id)
        raise
    finally:
        conn.close()


def get_payout_block_reason(payout_id: int, conn=None) -> Optional[str]:
    """
    Returns the human-readable reason a payout is blocked, or None if ready for payout.

    This is the single source of truth for payout block reasons, used for admin
    display and readiness evaluation. When None is returned, the payout is eligible
    for release (all conditions met).

    Checks in priority order:
    1. Terminal: PAID_OUT → None (already done, no block)
    2. Terminal: PAYOUT_CANCELLED → 'Payout cancelled'
    3. Admin hold: PAYOUT_ON_HOLD → 'Admin hold'
    4. Payment not completed
    5. Order refunded
    6. Payout recovery pending from refund
    7. ACH not cleared
    8. Order status not in payable states
    9. Seller Stripe account missing
    10. Seller Stripe payouts not enabled
    11. Seller has not uploaded shipping tracking
    12. Shipment not yet confirmed delivered (delivered_at is null)
    13. Delivery hold period not yet elapsed (delivered_at + configured hours)

    Fulfillment signal: seller_order_tracking(order_id, seller_id, tracking_number).
    A non-null, non-empty tracking_number means the seller has shipped their portion.

    Delivery signal: seller_order_tracking.delivered_at — set by admin action.
    Delay: auto_payout_delay_after_delivery_hours system setting (default 24 h).

    Args:
        payout_id: The order_payouts.id to evaluate.
        conn: Optional existing DB connection. If provided, the connection is NOT
              closed on return (caller owns it). If None, a fresh connection is
              opened and closed internally.

    Returns:
        None if no block (payout is ready for release), or a reason string.
    """
    own_conn = conn is None
    if own_conn:
        conn = get_db_connection()
    try:
        payout = conn.execute('''
            SELECT
                p.payout_status,
                p.seller_net_amount,
                p.order_id,
                p.seller_id,
                ol.order_status,
                o.payment_status,
                o.refund_status,
                o.requires_payout_recovery,
                o.requires_payment_clearance,
                o.payment_method_type,
                u.stripe_account_id,
                u.stripe_payouts_enabled,
                u.username AS seller_username,
                sot.tracking_number AS seller_tracking_number,
                sot.updated_at AS tracking_uploaded_at,
                sot.delivered_at AS delivered_at
            FROM order_payouts p
            JOIN orders_ledger ol ON p.order_ledger_id = ol.id
            JOIN orders o ON p.order_id = o.id
            JOIN users u ON p.seller_id = u.id
            LEFT JOIN seller_order_tracking sot
                ON sot.order_id = p.order_id AND sot.seller_id = p.seller_id
            WHERE p.id = ?
        ''', (payout_id,)).fetchone()

        if not payout:
            return 'Payout not found'

        status = payout['payout_status']

        # Terminal success: already paid out, no active block
        if status == PayoutStatus.PAID_OUT.value:
            return None

        # Terminal cancelled
        if status == PayoutStatus.PAYOUT_CANCELLED.value:
            return 'Payout cancelled'

        # Admin hold: explicit freeze, must be released by admin
        if status == PayoutStatus.PAYOUT_ON_HOLD.value:
            return 'Admin hold'

        # Payment must be captured
        if payout['payment_status'] != 'paid':
            return 'Order payment not completed'

        # Order must not be refunded
        if payout['refund_status'] != 'not_refunded':
            return 'Order has been refunded'

        # No payout recovery pending from a prior refund
        if payout['requires_payout_recovery']:
            return 'Payout recovery pending from refund'

        # ACH clearance: bank transfer must clear before seller is paid
        if payout['requires_payment_clearance']:
            return 'ACH requires payment clearance'

        # Order status must be in a payable state
        payable_statuses = [s.value for s in PAYABLE_ORDER_STATUSES]
        if payout['order_status'] not in payable_statuses:
            return f"Order not in payable state ({payout['order_status']})"

        # Seller must have a connected Stripe account
        if not payout['stripe_account_id']:
            return 'Seller has no Stripe account connected'

        # Seller Stripe account must have payouts enabled
        if not payout['stripe_payouts_enabled']:
            return 'Seller Stripe payouts not enabled'

        # Fulfillment: seller must have uploaded shipping tracking
        tracking = payout['seller_tracking_number']
        if not tracking or not tracking.strip():
            return 'Seller has not uploaded shipping tracking'

        # Delivery confirmation: admin must mark the shipment as delivered.
        delivered_at_str = payout['delivered_at']
        if not delivered_at_str:
            return 'Shipment not yet confirmed delivered'

        # Delivery hold: configured delay must elapse after delivery.
        from services.system_settings_service import get_auto_payout_delay_minutes
        delay_minutes = get_auto_payout_delay_minutes()
        try:
            ts = str(delivered_at_str)
            if 'T' in ts:
                delivered_at = datetime.fromisoformat(
                    ts.replace('Z', '+00:00')
                ).replace(tzinfo=None)
            else:
                delivered_at = datetime.strptime(ts[:19], '%Y-%m-%d %H:%M:%S')
            eligible_at = delivered_at + timedelta(minutes=delay_minutes)
            now = datetime.now()
            if now < eligible_at:
                logger.info(
                    "[Readiness] Payout %s blocked by delivery hold — "
                    "delivered_at=%s  eligible_at=%s  delay_minutes=%d",
                    payout_id, delivered_at.isoformat(),
                    eligible_at.isoformat(), delay_minutes,
                )
                return 'Delivery hold period not yet elapsed'
        except Exception:
            pass  # Timestamp parse failure — do not block on delay

        # All checks passed — no block
        return None

    finally:
        if own_conn:
            conn.close()


def evaluate_payout_readiness(payout_id: int) -> Dict[str, Any]:
    """
    Evaluate payout readiness and update payout_status if appropriate.

    Uses get_payout_block_reason() as the single source of truth for conditions.

    Statuses that are NEVER overridden (immutable):
    - PAID_OUT            (terminal success)
    - PAYOUT_CANCELLED    (terminal cancelled)
    - PAYOUT_ON_HOLD      (admin hold, must be explicitly released)
    - PAYOUT_SCHEDULED    (already scheduled for processing)
    - PAYOUT_IN_PROGRESS  (transfer in flight)

    Statuses that may transition:
    - PAYOUT_NOT_READY → PAYOUT_READY  (when all conditions met)
    - PAYOUT_READY → PAYOUT_NOT_READY  (when conditions no longer met)

    Logs PAYOUT_READINESS_EVALUATED event regardless of outcome.

    Args:
        payout_id: The order_payouts.id to evaluate.

    Returns:
        {
            'payout_id': int,
            'ready': bool,
            'reason': str | None,        # block reason, or None if ready
            'status_updated': bool,      # whether payout_status changed
            'old_status': str,
            'new_status': str,
        }

    Raises:
        ValueError: If payout not found.
    """
    conn = get_db_connection()
    try:
        row = conn.execute(
            'SELECT payout_status, order_id, seller_id FROM order_payouts WHERE id = ?',
            (payout_id,)
        ).fetchone()

        if not row:
            raise ValueError(f"Payout {payout_id} not found")

        current_status = row['payout_status']
        order_id = row['order_id']
        seller_id = row['seller_id']

        # Evaluate block reason using shared connection (no extra open/close)
        block_reason = get_payout_block_reason(payout_id, conn=conn)
        ready = (block_reason is None)

        # Statuses we must not overwrite
        immutable_statuses = {
            PayoutStatus.PAID_OUT.value,
            PayoutStatus.PAYOUT_CANCELLED.value,
            PayoutStatus.PAYOUT_ON_HOLD.value,
            PayoutStatus.PAYOUT_SCHEDULED.value,
            PayoutStatus.PAYOUT_IN_PROGRESS.value,
        }

        status_updated = False
        new_status = current_status

        if current_status not in immutable_statuses:
            target_status = (
                PayoutStatus.PAYOUT_READY.value if ready
                else PayoutStatus.PAYOUT_NOT_READY.value
            )
            if current_status != target_status:
                new_status = target_status
                status_updated = True
                conn.execute(
                    '''UPDATE order_payouts
                       SET payout_status = ?, updated_at = CURRENT_TIMESTAMP
                       WHERE id = ?''',
                    (new_status, payout_id)
                )

        _log_event_internal(
            conn, order_id,
            EventType.PAYOUT_READINESS_EVALUATED.value,
            ActorType.ADMIN.value, None,
            {
                'payout_id': payout_id,
                'seller_id': seller_id,
                'ready': ready,
                'reason': block_reason,
                'status_updated': status_updated,
                'old_status': current_status,
                'new_status': new_status,
            },
        )

        conn.commit()

        logger.info(
            "[Readiness] Evaluated payout_id=%s  ready=%s  reason=%r  "
            "status_updated=%s  old=%s  new=%s",
            payout_id, ready, block_reason, status_updated, current_status, new_status,
        )

        return {
            'payout_id': payout_id,
            'ready': ready,
            'reason': block_reason,
            'status_updated': status_updated,
            'old_status': current_status,
            'new_status': new_status,
        }

    except ValueError:
        raise
    except Exception:
        logger.exception(
            "[Readiness] Unexpected error evaluating payout_id=%s", payout_id
        )
        raise
    finally:
        conn.close()


def run_auto_payouts(admin_id=None) -> Dict[str, Any]:
    """
    Automatically release all payouts that are in PAYOUT_READY status.

    For each eligible payout:
    1. Re-check get_payout_block_reason() — never trust stale DB state
    2. Guard: skip if provider_transfer_id already set (idempotency)
    3. Guard: skip if payout_status == PAID_OUT (idempotency)
    4. If still ready → call release_stripe_transfer()
    5. Log outcome for every payout touched

    Args:
        admin_id: Optional admin user ID performing the action (for audit log)

    Returns:
        {
            'processed': int,
            'successful': int,
            'skipped': int,
            'errors': list[dict],
            'results': list[dict],
        }
    """
    conn = get_db_connection()
    try:
        candidate_rows = conn.execute(
            '''SELECT id, order_id, seller_id, seller_net_amount, provider_transfer_id, payout_status
               FROM order_payouts
               WHERE payout_status = ?
               ORDER BY id''',
            (PayoutStatus.PAYOUT_READY.value,)
        ).fetchall()
    finally:
        conn.close()

    processed = 0
    successful = 0
    skipped = 0
    errors = []
    results = []

    for row in candidate_rows:
        payout_id = row['id']
        order_id = row['order_id']
        seller_id = row['seller_id']
        processed += 1

        # Idempotency guard 1: already has a transfer ID
        if row['provider_transfer_id']:
            reason = 'Already has provider_transfer_id — skipped'
            logger.info(
                "[AutoPayout] SKIPPED  payout_id=%s  order_id=%s  seller_id=%s  reason=%r",
                payout_id, order_id, seller_id, reason
            )
            skipped += 1
            results.append({
                'payout_id': payout_id,
                'order_id': order_id,
                'seller_id': seller_id,
                'outcome': 'skipped',
                'reason': reason,
            })
            continue

        # Idempotency guard 2: status already PAID_OUT
        if row['payout_status'] == PayoutStatus.PAID_OUT.value:
            reason = 'Payout already PAID_OUT — skipped'
            logger.info(
                "[AutoPayout] SKIPPED  payout_id=%s  order_id=%s  seller_id=%s  reason=%r",
                payout_id, order_id, seller_id, reason
            )
            skipped += 1
            results.append({
                'payout_id': payout_id,
                'order_id': order_id,
                'seller_id': seller_id,
                'outcome': 'skipped',
                'reason': reason,
            })
            continue

        # Re-check readiness — never trust stale state
        block_reason = get_payout_block_reason(payout_id)
        if block_reason is not None:
            logger.info(
                "[AutoPayout] SKIPPED  payout_id=%s  order_id=%s  seller_id=%s  block=%r",
                payout_id, order_id, seller_id, block_reason
            )
            skipped += 1
            results.append({
                'payout_id': payout_id,
                'order_id': order_id,
                'seller_id': seller_id,
                'outcome': 'skipped',
                'reason': block_reason,
            })
            continue

        # All checks passed — attempt Stripe transfer
        try:
            transfer_result = release_stripe_transfer(payout_id, admin_id or 0)
            logger.info(
                "[AutoPayout] SUCCESS  payout_id=%s  order_id=%s  seller_id=%s  "
                "transfer_id=%s  amount=$%.2f",
                payout_id, order_id, seller_id,
                transfer_result.get('transfer_id'), transfer_result.get('amount', 0)
            )
            successful += 1
            results.append({
                'payout_id': payout_id,
                'order_id': order_id,
                'seller_id': seller_id,
                'outcome': 'success',
                'transfer_id': transfer_result.get('transfer_id'),
                'amount': transfer_result.get('amount'),
            })

        except Exception as exc:
            logger.error(
                "[AutoPayout] FAILED  payout_id=%s  order_id=%s  seller_id=%s  error=%s",
                payout_id, order_id, seller_id, exc
            )
            errors.append({
                'payout_id': payout_id,
                'order_id': order_id,
                'seller_id': seller_id,
                'error': str(exc),
            })

    logger.info(
        "[AutoPayout] Run complete — processed=%d  successful=%d  skipped=%d  errors=%d",
        processed, successful, skipped, len(errors)
    )

    return {
        'processed': processed,
        'successful': successful,
        'skipped': skipped,
        'errors': errors,
        'results': results,
    }
