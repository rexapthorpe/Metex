"""
Ledger Service Package

This package contains all ledger-related functionality, split by domain for maintainability.

Structure:
- exceptions.py: Custom exception classes
- fee_config.py: Fee configuration methods
- order_creation.py: Order ledger creation and validation
- status_updates.py: Status update methods
- escrow_control.py: Admin escrow control operations
- retrieval.py: Ledger data queries
- init_tables.py: Database table initialization

IMPORTANT: This split preserves ALL original function signatures, return values, and behavior.
The LedgerService class is assembled here by importing methods from sub-modules.
"""

from typing import Dict, List, Optional, Any, Tuple

# Import exceptions
from .exceptions import (
    LedgerInvariantError,
    BucketFeeConfigError,
    EscrowControlError
)

# Import all functions from sub-modules
from .fee_config import (
    get_fee_config,
    get_bucket_fee_config,
    update_bucket_fee,
    calculate_fee
)

from .order_creation import (
    _log_event_internal,
    log_order_event,
    create_order_ledger_from_cart,
    validate_order_invariants,
    prevent_amount_modification
)

from .status_updates import (
    update_order_status,
    update_payout_status
)

from .escrow_control import (
    hold_order,
    approve_order,
    hold_payout,
    release_payout,
    process_refund,
    refund_buyer_stripe,
    attempt_payout_recovery,
    handle_report_auto_hold,
    get_payout_eligibility,
    release_stripe_transfer,
    mark_ach_cleared,
    get_payout_block_reason,
    evaluate_payout_readiness,
    run_auto_payouts,
)

from .retrieval import (
    get_order_ledger,
    get_orders_ledger_list
)

from .init_tables import init_ledger_tables


class LedgerService:
    """
    Service class for managing transaction ledger operations.

    This class assembles all ledger methods as static methods for backward compatibility.
    All methods are imported from the sub-modules above.
    """

    # Fee configuration methods
    get_fee_config = staticmethod(get_fee_config)
    get_bucket_fee_config = staticmethod(get_bucket_fee_config)
    update_bucket_fee = staticmethod(update_bucket_fee)
    calculate_fee = staticmethod(calculate_fee)

    # Order creation and validation
    _log_event_internal = staticmethod(_log_event_internal)
    log_order_event = staticmethod(log_order_event)
    create_order_ledger_from_cart = staticmethod(create_order_ledger_from_cart)
    validate_order_invariants = staticmethod(validate_order_invariants)
    prevent_amount_modification = staticmethod(prevent_amount_modification)

    # Status updates
    update_order_status = staticmethod(update_order_status)
    update_payout_status = staticmethod(update_payout_status)

    # Escrow control (admin actions)
    hold_order = staticmethod(hold_order)
    approve_order = staticmethod(approve_order)
    hold_payout = staticmethod(hold_payout)
    release_payout = staticmethod(release_payout)
    process_refund = staticmethod(process_refund)
    refund_buyer_stripe = staticmethod(refund_buyer_stripe)
    attempt_payout_recovery = staticmethod(attempt_payout_recovery)
    handle_report_auto_hold = staticmethod(handle_report_auto_hold)
    get_payout_eligibility = staticmethod(get_payout_eligibility)
    release_stripe_transfer = staticmethod(release_stripe_transfer)
    mark_ach_cleared = staticmethod(mark_ach_cleared)
    get_payout_block_reason = staticmethod(get_payout_block_reason)
    evaluate_payout_readiness = staticmethod(evaluate_payout_readiness)
    run_auto_payouts = staticmethod(run_auto_payouts)

    # Retrieval
    get_order_ledger = staticmethod(get_order_ledger)
    get_orders_ledger_list = staticmethod(get_orders_ledger_list)


# Re-export everything for backward compatibility
__all__ = [
    # Exceptions
    'LedgerInvariantError',
    'BucketFeeConfigError',
    'EscrowControlError',
    # Main service class
    'LedgerService',
    # Initialization
    'init_ledger_tables',
    # Individual functions (for direct import if needed)
    'get_fee_config',
    'get_bucket_fee_config',
    'update_bucket_fee',
    'calculate_fee',
    'log_order_event',
    'create_order_ledger_from_cart',
    'validate_order_invariants',
    'prevent_amount_modification',
    'update_order_status',
    'update_payout_status',
    'hold_order',
    'approve_order',
    'hold_payout',
    'release_payout',
    'process_refund',
    'refund_buyer_stripe',
    'attempt_payout_recovery',
    'handle_report_auto_hold',
    'get_payout_eligibility',
    'release_stripe_transfer',
    'get_payout_block_reason',
    'evaluate_payout_readiness',
    'run_auto_payouts',
    'get_order_ledger',
    'get_orders_ledger_list',
]
