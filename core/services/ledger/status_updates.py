"""
Ledger Status Updates

Methods for updating order and payout status.
"""

from typing import Optional
import database
from services.ledger_constants import (
    OrderStatus, PayoutStatus, EventType, PAYABLE_ORDER_STATUSES
)
from .exceptions import LedgerInvariantError
from .order_creation import _log_event_internal


def get_db_connection():
    """Get database connection - wrapper for late binding in tests"""
    return database.get_db_connection()


def update_order_status(
    order_ledger_id: int,
    new_status: str,
    actor_type: str,
    actor_id: Optional[int] = None
) -> bool:
    """
    Update order status with validation and event logging.

    Args:
        order_ledger_id: The ledger ID
        new_status: New status (from OrderStatus enum)
        actor_type: Type of actor making the change
        actor_id: Optional actor ID

    Returns:
        True if update succeeded

    Raises:
        ValueError: If status transition is invalid
    """
    conn = get_db_connection()
    try:
        # Get current status
        order = conn.execute('''
            SELECT order_id, order_status FROM orders_ledger WHERE id = ?
        ''', (order_ledger_id,)).fetchone()

        if not order:
            raise ValueError(f"Order ledger {order_ledger_id} not found")

        current_status = OrderStatus(order['order_status'])
        new_status_enum = OrderStatus(new_status)

        # Validate transition
        if not OrderStatus.can_transition_to(current_status, new_status_enum):
            raise ValueError(
                f"Invalid status transition from {current_status.value} to {new_status}"
            )

        # Update status
        conn.execute('''
            UPDATE orders_ledger
            SET order_status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (new_status, order_ledger_id))

        # Log event
        _log_event_internal(
            conn, order['order_id'], EventType.STATUS_CHANGED.value,
            actor_type, actor_id,
            {'from_status': current_status.value, 'to_status': new_status}
        )

        conn.commit()
        return True

    finally:
        conn.close()


def update_payout_status(
    payout_id: int,
    new_status: str,
    actor_type: str,
    actor_id: Optional[int] = None,
    scheduled_for: Optional[str] = None,
    provider_transfer_id: Optional[str] = None,
    provider_payout_id: Optional[str] = None
) -> bool:
    """
    Update payout status with validation and event logging.

    Args:
        payout_id: The payout record ID
        new_status: New status (from PayoutStatus enum)
        actor_type: Type of actor making the change
        actor_id: Optional actor ID
        scheduled_for: Optional scheduled date (for PAYOUT_SCHEDULED)
        provider_transfer_id: Optional payment provider transfer ID
        provider_payout_id: Optional payment provider payout ID

    Returns:
        True if update succeeded

    Raises:
        ValueError: If status transition is invalid
        LedgerInvariantError: If PAID_OUT on non-payable order
    """
    conn = get_db_connection()
    try:
        # Get current payout and associated order
        payout = conn.execute('''
            SELECT p.*, ol.order_status
            FROM order_payouts p
            JOIN orders_ledger ol ON p.order_ledger_id = ol.id
            WHERE p.id = ?
        ''', (payout_id,)).fetchone()

        if not payout:
            raise ValueError(f"Payout {payout_id} not found")

        current_status = PayoutStatus(payout['payout_status'])
        new_status_enum = PayoutStatus(new_status)

        # Validate transition
        if not PayoutStatus.can_transition_to(current_status, new_status_enum):
            raise ValueError(
                f"Invalid payout status transition from {current_status.value} to {new_status}"
            )

        # Invariant check: Can't pay out if order isn't in payable status
        if new_status_enum == PayoutStatus.PAID_OUT:
            payable_statuses = [s.value for s in PAYABLE_ORDER_STATUSES]
            if payout['order_status'] not in payable_statuses:
                raise LedgerInvariantError(
                    f"Cannot set payout to PAID_OUT when order status is {payout['order_status']}"
                )

        # Build update query
        update_fields = ['payout_status = ?', 'updated_at = CURRENT_TIMESTAMP']
        params = [new_status]

        if scheduled_for:
            update_fields.append('scheduled_for = ?')
            params.append(scheduled_for)
        if provider_transfer_id:
            update_fields.append('provider_transfer_id = ?')
            params.append(provider_transfer_id)
        if provider_payout_id:
            update_fields.append('provider_payout_id = ?')
            params.append(provider_payout_id)

        params.append(payout_id)

        conn.execute(f'''
            UPDATE order_payouts
            SET {', '.join(update_fields)}
            WHERE id = ?
        ''', params)

        # Log event
        _log_event_internal(
            conn, payout['order_id'], EventType.PAYOUT_STATUS_CHANGED.value,
            actor_type, actor_id,
            {
                'payout_id': payout_id,
                'seller_id': payout['seller_id'],
                'from_status': current_status.value,
                'to_status': new_status
            }
        )

        conn.commit()
        return True

    finally:
        conn.close()
