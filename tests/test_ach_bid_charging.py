"""
Tests: ACH bank account charging in _charge_bid_payment
=========================================================
Verifies ACH bid payment behavior:

  ACH-CHARGE-1: payment_method_types=['us_bank_account'] used when pm_type='us_bank_account'.
  ACH-CHARGE-2: off_session NOT passed when pm_type is us_bank_account.
  ACH-CHARGE-3: pi.status='processing' returns success=True (ACH settlement in flight).
  ACH-CHARGE-4: pi.status='succeeded' still returns success=True (cards + instant ACH).
  ACH-CHARGE-5: Card PMs still use payment_method_types=['card'] + off_session.
  ACH-CHARGE-6: Default pm_type='card' works correctly (caller fallback path).
  ACH-CHARGE-7: PM type written into PI metadata for auditability.
  ACH-CHARGE-8: Mandate is passed to PaymentIntent when SetupIntents list returns one.
  ACH-CHARGE-9: No mandate → charge attempted anyway (error surfaced by Stripe).
"""

import sys
import os
import pytest
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_pi(status, pi_id='pi_test'):
    m = MagicMock()
    m.status = status
    m.id = pi_id
    return m


def _make_si(pm_id, mandate_id, status='succeeded'):
    """Return a minimal mock SetupIntent."""
    si = MagicMock()
    si.payment_method = pm_id
    si.mandate = mandate_id
    si.status = status
    si.get = lambda k, default=None: {
        'payment_method': pm_id,
        'mandate': mandate_id,
    }.get(k, default)
    return si


def _empty_si_list():
    """Return an empty SetupIntent list."""
    m = MagicMock()
    m.auto_paging_iter.return_value = iter([])
    return m


def _si_list_with_mandate(pm_id, mandate_id):
    """Return a SetupIntent list with one matching SI."""
    m = MagicMock()
    m.auto_paging_iter.return_value = iter([_make_si(pm_id, mandate_id)])
    return m


@pytest.fixture
def charge_fn():
    from core.blueprints.bids.accept_bid import _charge_bid_payment
    return _charge_bid_payment


class TestACHChargeBidPayment:

    # ── pm_type='us_bank_account' path ────────────────────────────────────────

    def test_ACH_CHARGE_1_bank_account_uses_us_bank_account_pm_type(self, charge_fn):
        """payment_method_types=['us_bank_account'] when pm_type='us_bank_account'."""
        with patch('stripe.SetupIntent.list', return_value=_empty_si_list()):
            with patch('stripe.PaymentIntent.create',
                       return_value=_make_pi('processing')) as mock_create:
                charge_fn(1, 1, 1, 'pm_bank_1', 'cus_x', 50.0, pm_type='us_bank_account')

        kwargs = mock_create.call_args.kwargs
        assert kwargs.get('payment_method_types') == ['us_bank_account'], (
            f"Expected ['us_bank_account'], got {kwargs.get('payment_method_types')}"
        )

    def test_ACH_CHARGE_2_off_session_not_sent_for_bank_account(self, charge_fn):
        """off_session must NOT be passed for ACH — ACH uses the stored mandate."""
        with patch('stripe.SetupIntent.list', return_value=_empty_si_list()):
            with patch('stripe.PaymentIntent.create',
                       return_value=_make_pi('processing')) as mock_create:
                charge_fn(1, 1, 1, 'pm_bank_2', 'cus_x', 30.0, pm_type='us_bank_account')

        kwargs = mock_create.call_args.kwargs
        assert 'off_session' not in kwargs, (
            "off_session must not be passed for ACH payments"
        )

    # ── 'processing' / 'succeeded' handling ──────────────────────────────────

    def test_ACH_CHARGE_3_processing_status_is_success(self, charge_fn):
        """pi.status='processing' must return success=True for ACH payments."""
        with patch('stripe.SetupIntent.list', return_value=_empty_si_list()):
            with patch('stripe.PaymentIntent.create', return_value=_make_pi('processing', 'pi_ach_ok')):
                result = charge_fn(2, 2, 2, 'pm_bank_3', 'cus_x', 75.0, pm_type='us_bank_account')

        assert result['success'] is True, (
            f"processing status should be success=True, got: {result}"
        )
        assert result['pi_id'] == 'pi_ach_ok'

    def test_ACH_CHARGE_4_succeeded_status_still_works(self, charge_fn):
        """pi.status='succeeded' still returns success=True (cards + instant ACH)."""
        with patch('stripe.SetupIntent.list', return_value=_empty_si_list()):
            with patch('stripe.PaymentIntent.create', return_value=_make_pi('succeeded', 'pi_ach_s')):
                result = charge_fn(3, 3, 3, 'pm_bank_4', 'cus_x', 40.0, pm_type='us_bank_account')

        assert result['success'] is True
        assert result['pi_id'] == 'pi_ach_s'

    # ── Card path unchanged ───────────────────────────────────────────────────

    def test_ACH_CHARGE_5_card_pm_uses_card_type_and_off_session(self, charge_fn):
        """Card PMs continue to use payment_method_types=['card'] and off_session=True."""
        with patch('stripe.PaymentIntent.create',
                   return_value=_make_pi('succeeded')) as mock_create:
            result = charge_fn(4, 4, 4, 'pm_card_1', 'cus_x', 100.0, pm_type='card')

        kwargs = mock_create.call_args.kwargs
        assert kwargs.get('payment_method_types') == ['card']
        assert kwargs.get('off_session') is True
        assert result['success'] is True

    # ── Default pm_type='card' (caller fallback) ─────────────────────────────

    def test_ACH_CHARGE_6_default_pm_type_is_card(self, charge_fn):
        """When pm_type is omitted (default='card'), card path is used."""
        with patch('stripe.PaymentIntent.create',
                   return_value=_make_pi('succeeded')) as mock_create:
            result = charge_fn(5, 5, 5, 'pm_unknown', 'cus_x', 20.0)

        kwargs = mock_create.call_args.kwargs
        assert kwargs.get('payment_method_types') == ['card']
        assert result['success'] is True

    # ── Metadata ─────────────────────────────────────────────────────────────

    def test_ACH_CHARGE_7_pm_type_in_metadata(self, charge_fn):
        """pm_type is written to PI metadata for auditability."""
        with patch('stripe.SetupIntent.list', return_value=_empty_si_list()):
            with patch('stripe.PaymentIntent.create',
                       return_value=_make_pi('processing')) as mock_create:
                charge_fn(6, 6, 6, 'pm_bank_5', 'cus_x', 60.0, pm_type='us_bank_account')

        metadata = mock_create.call_args.kwargs.get('metadata', {})
        assert metadata.get('pm_type') == 'us_bank_account'

    # ── Mandate lookup ────────────────────────────────────────────────────────

    def test_ACH_CHARGE_8_mandate_passed_when_found(self, charge_fn):
        """When a matching SetupIntent with a mandate exists, it's passed to PI."""
        si_list = _si_list_with_mandate('pm_bank_6', 'mandate_abc123')
        with patch('stripe.SetupIntent.list', return_value=si_list):
            with patch('stripe.PaymentIntent.create',
                       return_value=_make_pi('processing')) as mock_create:
                charge_fn(7, 7, 7, 'pm_bank_6', 'cus_x', 55.0, pm_type='us_bank_account')

        kwargs = mock_create.call_args.kwargs
        assert kwargs.get('mandate') == 'mandate_abc123', (
            f"Expected mandate='mandate_abc123', got {kwargs.get('mandate')}"
        )

    def test_ACH_CHARGE_9_no_mandate_charge_attempted_anyway(self, charge_fn):
        """When no mandate is found, PI creation is still attempted (Stripe surfaces the error)."""
        with patch('stripe.SetupIntent.list', return_value=_empty_si_list()):
            with patch('stripe.PaymentIntent.create',
                       return_value=_make_pi('processing')) as mock_create:
                result = charge_fn(8, 8, 8, 'pm_bank_7', 'cus_x', 30.0, pm_type='us_bank_account')

        # PI.create IS called even without a mandate (Stripe will reject if needed)
        assert mock_create.called
        # No 'mandate' key in kwargs
        kwargs = mock_create.call_args.kwargs
        assert 'mandate' not in kwargs
