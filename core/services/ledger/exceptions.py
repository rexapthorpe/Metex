"""
Ledger Service Exceptions

Custom exception classes for ledger operations.
"""


class LedgerInvariantError(Exception):
    """Raised when a ledger invariant is violated"""
    pass


class BucketFeeConfigError(Exception):
    """Raised when bucket fee configuration is missing or invalid"""
    pass


class EscrowControlError(Exception):
    """Raised when an escrow control operation fails due to precondition or state violation"""
    pass
