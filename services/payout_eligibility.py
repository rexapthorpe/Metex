"""
Payout Eligibility Service

Determines whether an order is eligible for seller payout release.

Rules (v1 — no payouts yet, readiness evaluation only):
  card payments  → eligible when payment_status='paid' and
                   requires_payment_clearance=0 (always the case for cards)
                   and payout_status='not_ready_for_payout' (not already processed)
  ACH payments   → NOT automatically eligible; ACH carries chargeback risk
                   during the clearance window, so these require a future
                   explicit admin release step.

This module never calls stripe.Transfer.create or moves any money.
It is a read-only evaluation used by admin dashboards and future
payout orchestration logic.
"""

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_order_payout_eligible(order) -> bool:
    """
    Return True if an order is ready for payout release, False otherwise.

    `order` can be any dict-like object with at minimum these keys:
        payment_status             str  — 'paid' | 'unpaid'
        payment_method_type        str  — 'card' | 'us_bank_account' | ...
        requires_payment_clearance int  — 1 = ACH/bank, 0 = card
        payout_status              str  — 'not_ready_for_payout' | ...

    Returns False (not eligible) if:
        - payment_status is not 'paid'
        - payout_status is already past 'not_ready_for_payout'
          (already handled or on hold)
        - payment method is ACH ('us_bank_account') or requires clearance

    Returns True (eligible) only for:
        - Fully paid card orders not yet processed for payout
    """
    # Must be paid
    if (order.get('payment_status') or '') != 'paid':
        return False

    # Must not already be in a payout workflow
    payout_status = order.get('payout_status') or 'not_ready_for_payout'
    if payout_status != 'not_ready_for_payout':
        return False

    # ACH / bank transfers require explicit clearance — never auto-eligible
    if order.get('requires_payment_clearance'):
        return False

    payment_method = (order.get('payment_method_type') or '').lower()
    if payment_method in ('us_bank_account', 'ach', ''):
        # Empty string means method unknown — treat as not eligible
        if payment_method != 'card':
            return False

    return True


def get_payout_block_reason(order) -> str:
    """
    Return a human-readable string explaining why an order is not eligible,
    or an empty string if it is eligible.

    Useful for admin display and logging.
    """
    if (order.get('payment_status') or '') != 'paid':
        return 'Payment not confirmed'

    payout_status = order.get('payout_status') or 'not_ready_for_payout'
    if payout_status != 'not_ready_for_payout':
        return f'Payout already in state: {payout_status}'

    if order.get('requires_payment_clearance'):
        return 'ACH payment — awaiting bank clearance'

    payment_method = (order.get('payment_method_type') or '').lower()
    if payment_method == 'us_bank_account':
        return 'ACH payment — awaiting bank clearance'

    if not payment_method:
        return 'Payment method unknown'

    return ''  # eligible
