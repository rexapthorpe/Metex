# services/ledger_service.py
"""
Ledger Service - Re-export Module

This module re-exports all ledger components from the new modular structure at core/services/ledger/.

The ledger service has been split into separate modules for better maintainability:
- core/services/ledger/exceptions.py - Exception classes
- core/services/ledger/fee_config.py - Fee configuration methods
- core/services/ledger/order_creation.py - Order ledger creation and validation
- core/services/ledger/status_updates.py - Status update methods
- core/services/ledger/escrow_control.py - Admin escrow control operations
- core/services/ledger/retrieval.py - Ledger data queries
- core/services/ledger/init_tables.py - Database table initialization

IMPORTANT: This file is kept for backwards compatibility.
All functionality is re-exported from core.services.ledger.
"""

# Re-export everything from the new modular structure
from core.services.ledger import (
    # Exceptions
    LedgerInvariantError,
    BucketFeeConfigError,
    EscrowControlError,
    # Main service class
    LedgerService,
    # Initialization
    init_ledger_tables,
)

# Also import get_db_connection for test fixture patching compatibility
from database import get_db_connection

__all__ = [
    'LedgerInvariantError',
    'BucketFeeConfigError',
    'EscrowControlError',
    'LedgerService',
    'init_ledger_tables',
]
