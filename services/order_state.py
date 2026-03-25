"""
Order State Helpers

Derives a unified "Order State" display field from existing DB columns.
Used by admin ledger/transactions views to avoid ambiguous status fields.
Does NOT modify any DB model — display only.
"""

# --- State label map ---
ORDER_STATE_LABELS = {
    'CHECKOUT_INITIATED':  'Checkout Initiated',
    'PAYMENT_PENDING':     'Payment Pending',
    'PAID':                'Paid',
    'FULFILLMENT_PENDING': 'Awaiting Shipment',
    'SHIPPED':             'Shipped',
    'PAYOUT_PENDING':      'Payout Pending',
    'PAYOUT_READY':        'Ready for Payout',
    'PAID_OUT':            'Paid Out',
    'REFUNDED':            'Refunded',
    'RECOVERY_PENDING':    'Recovery Pending',
    'CANCELLED':           'Cancelled',
    'UNDER_REVIEW':        'Under Review',
}

# CSS class suffixes for admin badge styling
ORDER_STATE_CSS = {
    'CHECKOUT_INITIATED':  'order-state-initiate',
    'PAYMENT_PENDING':     'order-state-pending',
    'PAID':                'order-state-paid',
    'FULFILLMENT_PENDING': 'order-state-fulfillment',
    'SHIPPED':             'order-state-shipped',
    'PAYOUT_PENDING':      'order-state-payout-pending',
    'PAYOUT_READY':        'order-state-payout-ready',
    'PAID_OUT':            'order-state-paid-out',
    'REFUNDED':            'order-state-refunded',
    'RECOVERY_PENDING':    'order-state-recovery',
    'CANCELLED':           'order-state-cancelled',
    'UNDER_REVIEW':        'order-state-review',
}


def compute_order_state(order: dict) -> str:
    """
    Derive a unified Order State key from component DB fields.

    Consumes (all optional, defaults to ''):
        order_status, payment_status, payout_status,
        refund_status, requires_payout_recovery

    Returns one of the ORDER_STATE_LABELS keys.
    """
    order_status    = (order.get('order_status')   or '').upper()
    payment_status  = (order.get('payment_status') or '').lower()
    payout_status   = (order.get('payout_status')  or '').upper()
    refund_status   = (order.get('refund_status')  or '').lower()
    recovery_pending = bool(order.get('requires_payout_recovery'))

    # --- Terminal: cancelled ---
    if order_status == 'CANCELLED':
        return 'CANCELLED'

    # --- Refunded path ---
    if refund_status == 'refunded':
        return 'RECOVERY_PENDING' if recovery_pending else 'REFUNDED'

    # --- Pre-payment ---
    if payment_status not in ('paid', 'captured'):
        return 'CHECKOUT_INITIATED' if order_status == 'CHECKOUT_INITIATED' else 'PAYMENT_PENDING'

    # --- Paid: check payout progression ---
    if payout_status == 'PAID_OUT':
        return 'PAID_OUT'
    if payout_status == 'PAYOUT_READY':
        return 'PAYOUT_READY'

    # --- Admin hold ---
    if order_status == 'UNDER_REVIEW':
        return 'UNDER_REVIEW'

    # --- Fulfillment stages ---
    if order_status in ('AWAITING_SHIPMENT', 'PAID_IN_ESCROW'):
        return 'FULFILLMENT_PENDING'
    if order_status in ('PARTIALLY_SHIPPED', 'SHIPPED'):
        return 'SHIPPED'
    if order_status == 'COMPLETED':
        return 'PAYOUT_PENDING'

    return 'PAID'


def get_order_state_label(order: dict) -> str:
    """Return the human-readable label for the derived order state."""
    return ORDER_STATE_LABELS.get(compute_order_state(order), 'Unknown')


def get_order_state_css(order: dict) -> str:
    """Return the CSS class for the derived order state badge."""
    return ORDER_STATE_CSS.get(compute_order_state(order), 'order-state-pending')


def get_block_reason_summary(order: dict):
    """
    Compute a simplified payout block reason from order-level fields only.
    Does NOT query per-payout rows — safe to call in list views (no N+1).

    Returns a short string describing the highest-priority blocker, or None
    if no obvious blocker is detected at the order level.
    """
    payout_status   = (order.get('payout_status')  or '').upper()
    payment_status  = (order.get('payment_status') or '').lower()
    refund_status   = (order.get('refund_status')  or '').lower()
    order_status    = (order.get('order_status')   or '').upper()
    requires_clr    = bool(order.get('requires_payment_clearance'))
    recovery_pending = bool(order.get('requires_payout_recovery'))

    if payout_status == 'PAID_OUT':
        return None  # Terminal — no blocker
    if payout_status == 'PAYOUT_CANCELLED':
        return 'Payout cancelled'
    if refund_status == 'refunded':
        return 'Recovery pending' if recovery_pending else 'Order refunded'
    if payment_status not in ('paid', 'captured'):
        return 'Payment not complete'
    if requires_clr:
        return 'ACH clearance pending'
    if order_status not in (
        'PAID_IN_ESCROW', 'AWAITING_SHIPMENT',
        'PARTIALLY_SHIPPED', 'SHIPPED', 'COMPLETED',
    ):
        label = order_status.replace('_', ' ').title()
        return f'Order status: {label}'
    if payout_status in ('PAYOUT_NOT_READY', ''):
        return 'Waiting for tracking / delay / Stripe'
    return None
