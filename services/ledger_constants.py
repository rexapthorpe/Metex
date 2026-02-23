"""
Ledger Constants - Authoritative enums and constants for the transaction ledger system

These enums define the state machine for orders and payouts.
"""
from enum import Enum


class OrderStatus(str, Enum):
    """
    Order lifecycle states.

    State Machine Flow:
    CHECKOUT_INITIATED -> PAYMENT_PENDING -> PAID_IN_ESCROW -> AWAITING_SHIPMENT
    -> (PARTIALLY_SHIPPED ->) SHIPPED -> COMPLETED

    Alternative paths:
    - Any state -> UNDER_REVIEW (admin intervention)
    - Any state -> CANCELLED (cancellation)
    - PAID_IN_ESCROW+ -> REFUNDED (refund processed)
    """
    CHECKOUT_INITIATED = 'CHECKOUT_INITIATED'  # Order created, awaiting payment
    PAYMENT_PENDING = 'PAYMENT_PENDING'        # Payment initiated but not confirmed
    PAID_IN_ESCROW = 'PAID_IN_ESCROW'          # Payment received, funds held in escrow
    UNDER_REVIEW = 'UNDER_REVIEW'              # Order flagged for admin review
    AWAITING_SHIPMENT = 'AWAITING_SHIPMENT'    # Ready for seller to ship
    PARTIALLY_SHIPPED = 'PARTIALLY_SHIPPED'    # Some items shipped (multi-seller)
    SHIPPED = 'SHIPPED'                        # All items shipped
    COMPLETED = 'COMPLETED'                    # Order fulfilled, funds released
    CANCELLED = 'CANCELLED'                    # Order cancelled before completion
    REFUNDED = 'REFUNDED'                      # Funds returned to buyer
    PARTIALLY_REFUNDED = 'PARTIALLY_REFUNDED'  # Partial refund processed

    @classmethod
    def all_values(cls):
        return [status.value for status in cls]

    @classmethod
    def is_valid(cls, value):
        return value in cls.all_values()

    @classmethod
    def can_transition_to(cls, from_status, to_status):
        """Define valid state transitions"""
        valid_transitions = {
            cls.CHECKOUT_INITIATED: [cls.PAYMENT_PENDING, cls.UNDER_REVIEW, cls.CANCELLED],
            cls.PAYMENT_PENDING: [cls.PAID_IN_ESCROW, cls.UNDER_REVIEW, cls.CANCELLED],
            cls.PAID_IN_ESCROW: [cls.AWAITING_SHIPMENT, cls.UNDER_REVIEW, cls.CANCELLED, cls.REFUNDED, cls.PARTIALLY_REFUNDED],
            cls.UNDER_REVIEW: [cls.PAID_IN_ESCROW, cls.AWAITING_SHIPMENT, cls.CANCELLED, cls.REFUNDED, cls.PARTIALLY_REFUNDED],
            cls.AWAITING_SHIPMENT: [cls.PARTIALLY_SHIPPED, cls.SHIPPED, cls.UNDER_REVIEW, cls.CANCELLED, cls.REFUNDED, cls.PARTIALLY_REFUNDED],
            cls.PARTIALLY_SHIPPED: [cls.SHIPPED, cls.UNDER_REVIEW, cls.CANCELLED, cls.REFUNDED, cls.PARTIALLY_REFUNDED],
            cls.SHIPPED: [cls.COMPLETED, cls.UNDER_REVIEW, cls.REFUNDED, cls.PARTIALLY_REFUNDED],
            cls.COMPLETED: [],  # Terminal state
            cls.CANCELLED: [],  # Terminal state
            cls.REFUNDED: [],   # Terminal state
            cls.PARTIALLY_REFUNDED: [cls.AWAITING_SHIPMENT, cls.SHIPPED, cls.COMPLETED, cls.UNDER_REVIEW],  # Can continue after partial refund
        }
        allowed = valid_transitions.get(from_status, [])
        return to_status in allowed


class PayoutStatus(str, Enum):
    """
    Payout lifecycle states for seller payments.

    State Machine Flow:
    PAYOUT_NOT_READY -> PAYOUT_READY -> PAYOUT_SCHEDULED -> PAYOUT_IN_PROGRESS -> PAID_OUT

    Alternative paths:
    - PAYOUT_READY -> PAYOUT_ON_HOLD (dispute/review)
    - PAYOUT_ON_HOLD -> PAYOUT_READY (resolved)
    - Any non-terminal state -> PAYOUT_CANCELLED
    """
    PAYOUT_NOT_READY = 'PAYOUT_NOT_READY'      # Order not in payable state
    PAYOUT_READY = 'PAYOUT_READY'              # Ready for payout processing
    PAYOUT_ON_HOLD = 'PAYOUT_ON_HOLD'          # Held due to dispute or review
    PAYOUT_SCHEDULED = 'PAYOUT_SCHEDULED'      # Scheduled for specific date
    PAYOUT_IN_PROGRESS = 'PAYOUT_IN_PROGRESS'  # Transfer initiated
    PAID_OUT = 'PAID_OUT'                      # Successfully paid to seller
    PAYOUT_CANCELLED = 'PAYOUT_CANCELLED'      # Payout cancelled (e.g., refund)

    @classmethod
    def all_values(cls):
        return [status.value for status in cls]

    @classmethod
    def is_valid(cls, value):
        return value in cls.all_values()

    @classmethod
    def can_transition_to(cls, from_status, to_status):
        """Define valid state transitions"""
        valid_transitions = {
            cls.PAYOUT_NOT_READY: [cls.PAYOUT_READY, cls.PAYOUT_ON_HOLD, cls.PAYOUT_CANCELLED],
            cls.PAYOUT_READY: [cls.PAYOUT_SCHEDULED, cls.PAYOUT_IN_PROGRESS, cls.PAYOUT_ON_HOLD, cls.PAYOUT_CANCELLED],
            cls.PAYOUT_ON_HOLD: [cls.PAYOUT_READY, cls.PAYOUT_CANCELLED],
            cls.PAYOUT_SCHEDULED: [cls.PAYOUT_IN_PROGRESS, cls.PAYOUT_ON_HOLD, cls.PAYOUT_CANCELLED],
            cls.PAYOUT_IN_PROGRESS: [cls.PAID_OUT, cls.PAYOUT_ON_HOLD, cls.PAYOUT_CANCELLED],
            cls.PAID_OUT: [],          # Terminal state
            cls.PAYOUT_CANCELLED: [],  # Terminal state
        }
        allowed = valid_transitions.get(from_status, [])
        return to_status in allowed


class FeeType(str, Enum):
    """Types of fees that can be applied"""
    PERCENT = 'percent'  # Percentage of gross amount
    FLAT = 'flat'        # Fixed dollar amount


class ActorType(str, Enum):
    """Types of actors that can trigger events"""
    SYSTEM = 'system'
    ADMIN = 'admin'
    BUYER = 'buyer'
    SELLER = 'seller'
    PAYMENT_PROVIDER = 'payment_provider'


class EventType(str, Enum):
    """Types of events in the order lifecycle"""
    # Order lifecycle events
    ORDER_CREATED = 'ORDER_CREATED'
    LEDGER_CREATED = 'LEDGER_CREATED'
    PAYMENT_INITIATED = 'PAYMENT_INITIATED'
    PAYMENT_CONFIRMED = 'PAYMENT_CONFIRMED'
    PAYMENT_FAILED = 'PAYMENT_FAILED'
    STATUS_CHANGED = 'STATUS_CHANGED'

    # Shipping events
    ITEM_SHIPPED = 'ITEM_SHIPPED'
    ALL_ITEMS_SHIPPED = 'ALL_ITEMS_SHIPPED'
    TRACKING_ADDED = 'TRACKING_ADDED'

    # Review/dispute events
    ORDER_FLAGGED = 'ORDER_FLAGGED'
    ORDER_UNFLAGGED = 'ORDER_UNFLAGGED'
    DISPUTE_OPENED = 'DISPUTE_OPENED'
    DISPUTE_RESOLVED = 'DISPUTE_RESOLVED'

    # Completion events
    ORDER_COMPLETED = 'ORDER_COMPLETED'
    ORDER_CANCELLED = 'ORDER_CANCELLED'

    # Payout events
    PAYOUT_STATUS_CHANGED = 'PAYOUT_STATUS_CHANGED'
    PAYOUT_SCHEDULED = 'PAYOUT_SCHEDULED'
    PAYOUT_INITIATED = 'PAYOUT_INITIATED'
    PAYOUT_COMPLETED = 'PAYOUT_COMPLETED'
    PAYOUT_FAILED = 'PAYOUT_FAILED'

    # Refund events
    REFUND_INITIATED = 'REFUND_INITIATED'
    REFUND_COMPLETED = 'REFUND_COMPLETED'
    REFUND_FAILED = 'REFUND_FAILED'

    # Admin escrow control events (Phase 2)
    ORDER_HELD = 'ORDER_HELD'                # Admin placed order under review
    ORDER_APPROVED = 'ORDER_APPROVED'        # Admin released order from review
    PAYOUT_HELD = 'PAYOUT_HELD'              # Admin held specific payout
    PAYOUT_RELEASED = 'PAYOUT_RELEASED'      # Admin released held payout
    REPORT_CREATED = 'REPORT_CREATED'        # User report filed against order
    AUTO_HOLD_FAILED = 'AUTO_HOLD_FAILED'    # Auto-hold on report creation failed

    # Bucket fee events (admin configuration changes)
    BUCKET_FEE_UPDATED = 'BUCKET_FEE_UPDATED'


# Default fee configuration
DEFAULT_PLATFORM_FEE_TYPE = FeeType.PERCENT
DEFAULT_PLATFORM_FEE_VALUE = 2.5  # 2.5%


# Order statuses that allow payout
PAYABLE_ORDER_STATUSES = [
    OrderStatus.PAID_IN_ESCROW,
    OrderStatus.AWAITING_SHIPMENT,
    OrderStatus.PARTIALLY_SHIPPED,
    OrderStatus.SHIPPED,
    OrderStatus.COMPLETED,
]

# Terminal order statuses (no further state changes allowed)
TERMINAL_ORDER_STATUSES = [
    OrderStatus.COMPLETED,
    OrderStatus.CANCELLED,
    OrderStatus.REFUNDED,
]

# Terminal payout statuses (payout is finalized)
TERMINAL_PAYOUT_STATUSES = [
    PayoutStatus.PAID_OUT,
    PayoutStatus.PAYOUT_CANCELLED,
]

# Statuses that block order hold action
ORDER_HOLD_BLOCKED_STATUSES = [
    OrderStatus.CANCELLED,
    OrderStatus.REFUNDED,
    OrderStatus.COMPLETED,
]

# Statuses that block payout hold action
PAYOUT_HOLD_BLOCKED_STATUSES = [
    PayoutStatus.PAID_OUT,
    PayoutStatus.PAYOUT_CANCELLED,
]
