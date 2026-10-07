"""Legacy ledger display helpers remain; its money commands must never dispatch.

Supported financial workflows are covered by test_flow_of_funds_acceptance,
test_launch_safety and PostgreSQL race tests. Removed legacy expectations assumed
immediate refunds, fallback funding without source evidence and mutable ledger
payout authority, all contrary to the canonical launch specification.
"""
from unittest.mock import patch
import pytest
from core.services.ledger import escrow_control as legacy


@pytest.mark.parametrize('command,args',[
    ('release_stripe_transfer',(1,9)),
    ('attempt_payout_recovery',(1,9)),
    ('refund_buyer_stripe',(1,9)),
    ('process_refund',(1,9,'full','SELLER_FAULT')),
    ('mark_ach_cleared',(1,9)),
])
def test_retired_command_cannot_contact_provider(command,args):
    with patch('stripe.Transfer.create',side_effect=AssertionError('Unsafe legacy transfer')),patch('stripe.Refund.create',side_effect=AssertionError('Unsafe legacy refund')):
        with pytest.raises(legacy.EscrowControlError,match='Legacy financial commands are retired'):
            getattr(legacy,command)(*args)
