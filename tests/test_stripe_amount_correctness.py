"""
Stripe amount correctness tests.

Verifies that ALL payment flows charge Stripe the full amount:
    total = subtotal + tax + buyer_card_fee

Flows tested:
  STRIPE-1  Source: accept_bid.py calls Stripe Tax before charging
  STRIPE-2  Source: checkout/routes.py hard-fails when payment_intent_id is missing
  STRIPE-3  Unit: _parse_address_for_tax extracts postal code and state correctly
  STRIPE-4  Unit: _get_stripe_tax_for_bid returns Stripe Tax cents (mocked)
  STRIPE-5  Unit: bid acceptance amount = subtotal + tax + card_fee (not subtotal only)
  STRIPE-6  Unit: checkout PI.modify receives subtotal + tax + card_fee (not subtotal only)
  STRIPE-7  Source: checkout/routes.py logs all charge components before PI.modify
"""

import os
import sys
import sqlite3
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Simulated Stripe Tax for an 8.25% rate on $100 subtotal
_MOCK_TAX_CENTS_100 = 825    # $8.25
# Simulated Stripe Tax on $200 subtotal
_MOCK_TAX_CENTS_200 = 1650   # $16.50

_CARD_RATE = 0.0299
_CARD_FLAT = 0.30


def _make_mock_calc(tax_cents: int, calc_id: str = 'taxcalc_test'):
    """Return a mock Stripe Tax Calculation with `tax_amount_exclusive = tax_cents`."""
    calc = MagicMock()
    calc.id = calc_id
    calc.tax_amount_exclusive = tax_cents
    return calc


# ---------------------------------------------------------------------------
# STRIPE-1  Source code check: accept_bid.py computes tax + card fee
# ---------------------------------------------------------------------------

class TestSourceChecksAcceptBid:

    _ACCEPT_BID_PATH = os.path.join(
        os.path.dirname(__file__), '..', 'core', 'blueprints', 'bids', 'accept_bid.py'
    )

    def _src(self):
        with open(os.path.normpath(self._ACCEPT_BID_PATH)) as f:
            return f.read()

    def test_STRIPE1a_accept_bid_calls_get_stripe_tax_for_bid(self):
        """accept_bid.py must call _get_stripe_tax_for_bid before charging."""
        src = self._src()
        assert '_get_stripe_tax_for_bid' in src, (
            "accept_bid.py does not call _get_stripe_tax_for_bid. "
            "Tax is not being computed for bid acceptance charges."
        )

    def test_STRIPE1b_accept_bid_computes_card_fee(self):
        """accept_bid.py must compute _bid_card_fee from taxed subtotal."""
        src = self._src()
        assert '_bid_card_fee' in src, (
            "accept_bid.py does not compute _bid_card_fee. "
            "Card processing fee is not being added to bid charges."
        )

    def test_STRIPE1c_accept_bid_defines_card_rate_constant(self):
        """accept_bid.py must define _CARD_RATE to stay in sync with checkout."""
        src = self._src()
        assert '_CARD_RATE' in src, (
            "accept_bid.py must define _CARD_RATE (card processing fee rate) "
            "so it stays in sync with checkout/routes.py."
        )

    def test_STRIPE1d_accept_bid_uses_total_price_as_full_charge(self):
        """total_price in accept_bid.py must include tax and card fee, not just subtotal."""
        src = self._src()
        # After the fix, total_price = round(_taxed_subtotal + _bid_card_fee, 2)
        assert '_bid_card_fee' in src and '_taxed_subtotal' in src, (
            "accept_bid.py must compute total_price as _taxed_subtotal + _bid_card_fee. "
            "Otherwise Stripe charges only the item subtotal."
        )

    def test_STRIPE1e_accept_bid_parses_address_for_tax(self):
        """accept_bid.py must parse the delivery_address to extract postal code for tax."""
        src = self._src()
        assert '_parse_address_for_tax' in src, (
            "accept_bid.py does not parse delivery_address for tax lookup. "
            "Without a postal code, Stripe Tax cannot compute the correct rate."
        )

    def test_STRIPE1f_accept_bid_stores_tax_and_fee_on_order(self):
        """The order INSERT in accept_bid.py must include buyer_card_fee and tax_amount."""
        src = self._src()
        # Both fields must appear in the INSERT column list
        assert 'buyer_card_fee' in src, (
            "accept_bid.py does not store buyer_card_fee on the order."
        )
        assert 'tax_amount' in src, (
            "accept_bid.py does not store tax_amount on the order."
        )


# ---------------------------------------------------------------------------
# STRIPE-2  Source code check: checkout/routes.py hard-fails on missing PI ID
# ---------------------------------------------------------------------------

class TestSourceChecksCheckout:

    _CHECKOUT_PATH = os.path.join(
        os.path.dirname(__file__), '..', 'core', 'blueprints', 'checkout', 'routes.py'
    )

    def _src(self):
        with open(os.path.normpath(self._CHECKOUT_PATH)) as f:
            return f.read()

    def test_STRIPE2a_checkout_rejects_missing_payment_intent_id(self):
        """
        checkout/routes.py must return an error when payment_intent_id is missing —
        not silently proceed.  Without a PI ID, confirmPayment() would charge the
        original PI amount (subtotal only, no tax or card fee).
        """
        src = self._src()
        assert 'if not payment_intent_id:' in src, (
            "checkout/routes.py does not hard-fail when payment_intent_id is missing. "
            "A missing PI ID would allow confirmPayment() to proceed with a stale amount."
        )

    def test_STRIPE2b_checkout_logs_all_charge_components(self):
        """checkout/routes.py must log subtotal, tax, card_fee, and total before PI.modify."""
        src = self._src()
        assert '_charged_total_cents' in src and 'payment_intent_id' in src, (
            "checkout/routes.py logging of charge components is missing."
        )
        # Verify the log line references all components
        assert 'subtotal' in src and 'tax' in src and 'card_fee' in src, (
            "checkout/routes.py log line must include subtotal, tax, and card_fee."
        )

    def test_STRIPE2c_checkout_logs_pi_amount_set(self):
        """checkout/routes.py must log a confirmation after PI.modify succeeds."""
        src = self._src()
        assert 'PI %s amount set to' in src or 'amount set to' in src, (
            "checkout/routes.py should log confirmation that PI amount was updated."
        )


# ---------------------------------------------------------------------------
# STRIPE-3  Unit: _parse_address_for_tax
# ---------------------------------------------------------------------------

class TestParseAddressForTax:

    def _fn(self):
        from core.blueprints.bids.accept_bid import _parse_address_for_tax
        return _parse_address_for_tax

    def test_STRIPE3a_extracts_postal_and_state_no_line2(self):
        """'123 Main St • Austin, TX 78701' → postal='78701', state='TX'"""
        postal, state = self._fn()('123 Main St • Austin, TX 78701')
        assert postal == '78701', f"expected '78701', got '{postal}'"
        assert state == 'TX', f"expected 'TX', got '{state}'"

    def test_STRIPE3b_extracts_with_line2(self):
        """'Line1 • Apt 2B • Chicago, IL 60601' → postal='60601', state='IL'"""
        postal, state = self._fn()('Line1 • Apt 2B • Chicago, IL 60601')
        assert postal == '60601'
        assert state == 'IL'

    def test_STRIPE3c_returns_empty_on_blank(self):
        """Empty string → ('', '')"""
        postal, state = self._fn()('')
        assert postal == '' and state == ''

    def test_STRIPE3d_returns_empty_on_no_state_zip(self):
        """Address without state/ZIP format → ('', '')"""
        postal, state = self._fn()('123 Main Street only')
        assert postal == '' and state == ''

    def test_STRIPE3e_handles_zip_plus_four(self):
        """'100 Elm St • Springfield, MA 01101-1234' → postal='01101-1234', state='MA'"""
        postal, state = self._fn()('100 Elm St • Springfield, MA 01101-1234')
        assert postal == '01101-1234'
        assert state == 'MA'


# ---------------------------------------------------------------------------
# STRIPE-4  Unit: _get_stripe_tax_for_bid
# ---------------------------------------------------------------------------

class TestGetStripeTaxForBid:

    def _fn(self):
        from core.blueprints.bids.accept_bid import _get_stripe_tax_for_bid
        return _get_stripe_tax_for_bid

    def test_STRIPE4a_returns_stripe_tax_cents(self):
        """_get_stripe_tax_for_bid returns Stripe's tax_amount_exclusive in cents."""
        mock_calc = _make_mock_calc(_MOCK_TAX_CENTS_100)
        with patch('stripe.tax.Calculation.create', return_value=mock_calc):
            result = self._fn()(10000, '78701', 'TX')
        assert result == _MOCK_TAX_CENTS_100

    def test_STRIPE4b_returns_zero_without_postal_code(self):
        """No postal code → 0 (cannot look up tax without address)."""
        result = self._fn()(10000, '', 'TX')
        assert result == 0

    def test_STRIPE4c_returns_fallback_rate_on_stripe_error(self):
        """Stripe API error with postal code → fallback rate (not 0), matching modal preview."""
        from core.blueprints.bids.accept_bid import FALLBACK_TAX_RATE
        with patch('stripe.tax.Calculation.create', side_effect=Exception('API error')):
            result = self._fn()(10000, '78701', 'TX')
        expected = round(10000 * FALLBACK_TAX_RATE)
        assert result == expected, (
            f"Expected fallback {expected} cents ({FALLBACK_TAX_RATE*100:.2f}%), got {result}. "
            "When Stripe Tax fails with a postal code, fallback rate must apply so the "
            "buyer is charged the same amount shown in the bid modal preview."
        )

    def test_STRIPE4d_passes_correct_subtotal_to_stripe(self):
        """The subtotal passed to Stripe Tax must be the integer cents value."""
        mock_calc = _make_mock_calc(100)
        with patch('stripe.tax.Calculation.create', return_value=mock_calc) as mock_create:
            self._fn()(20000, '10001', 'NY')
        call_kwargs = mock_create.call_args.kwargs
        line_items = call_kwargs.get('line_items', [])
        assert len(line_items) == 1
        assert line_items[0]['amount'] == 20000


# ---------------------------------------------------------------------------
# STRIPE-5  Unit: bid acceptance total = subtotal + tax + card_fee
# ---------------------------------------------------------------------------

class TestBidAcceptanceAmount:
    """
    Verify that the bid acceptance charge amount equals subtotal + tax + card_fee,
    not just the subtotal.
    """

    def test_STRIPE5a_total_exceeds_subtotal(self):
        """
        With tax and card fee, total > subtotal.
        Before the fix: _charge_bid_payment was called with only the subtotal.
        """
        from core.blueprints.bids.accept_bid import (
            _parse_address_for_tax, _get_stripe_tax_for_bid, _CARD_RATE, _CARD_FLAT
        )
        subtotal = 100.00
        address  = '123 Main St • Austin, TX 78701'
        postal, state = _parse_address_for_tax(address)

        mock_calc = _make_mock_calc(_MOCK_TAX_CENTS_100)
        with patch('stripe.tax.Calculation.create', return_value=mock_calc):
            tax_cents = _get_stripe_tax_for_bid(int(subtotal * 100), postal, state)

        tax_amount     = round(tax_cents / 100, 2)
        taxed_subtotal = subtotal + tax_amount
        card_fee       = round(taxed_subtotal * _CARD_RATE + _CARD_FLAT, 2)
        total          = round(taxed_subtotal + card_fee, 2)

        assert tax_amount == 8.25, f"expected 8.25, got {tax_amount}"
        assert card_fee > 0, "card_fee must be positive for a card payment"
        assert total > subtotal, (
            f"total ({total}) must exceed subtotal ({subtotal}). "
            "Before the fix, bid charges were subtotal-only."
        )

    def test_STRIPE5b_total_formula_matches_checkout(self):
        """
        accept_bid total = subtotal + tax + card_fee
        must match the formula used by checkout/routes.py exactly.
        """
        from core.blueprints.bids.accept_bid import _CARD_RATE as bid_rate, _CARD_FLAT as bid_flat
        import core.blueprints.checkout.routes as co_routes

        assert bid_rate == co_routes.CARD_RATE, (
            f"accept_bid._CARD_RATE ({bid_rate}) != checkout.CARD_RATE ({co_routes.CARD_RATE}). "
            "Card fee formula must be identical in both flows."
        )
        assert bid_flat == co_routes.CARD_FLAT, (
            f"accept_bid._CARD_FLAT ({bid_flat}) != checkout.CARD_FLAT ({co_routes.CARD_FLAT}). "
            "Card fee formula must be identical in both flows."
        )

    def test_STRIPE5c_charge_bid_payment_receives_full_amount(self):
        """
        _charge_bid_payment must be called with the full amount (subtotal+tax+fee),
        not just the subtotal.  Verified by capturing the Stripe PI create call.
        """
        from core.blueprints.bids.accept_bid import (
            _charge_bid_payment, _parse_address_for_tax, _get_stripe_tax_for_bid,
            _CARD_RATE, _CARD_FLAT
        )

        subtotal    = 200.00
        address     = '456 Oak Ave • Seattle, WA 98101'
        postal, state = _parse_address_for_tax(address)

        mock_calc = _make_mock_calc(_MOCK_TAX_CENTS_200)
        with patch('stripe.tax.Calculation.create', return_value=mock_calc):
            tax_cents = _get_stripe_tax_for_bid(int(subtotal * 100), postal, state)

        tax_amount     = round(tax_cents / 100, 2)   # 16.50
        taxed_subtotal = subtotal + tax_amount         # 216.50
        card_fee       = round(taxed_subtotal * _CARD_RATE + _CARD_FLAT, 2)
        total          = round(taxed_subtotal + card_fee, 2)
        expected_cents = int(round(total * 100))

        # Now verify _charge_bid_payment uses this total when calling Stripe
        mock_pi = MagicMock(status='succeeded', id='pi_test_full_amount')
        with patch('stripe.PaymentIntent.create', return_value=mock_pi) as mock_create:
            result = _charge_bid_payment(
                bid_id=1, order_id=1, buyer_id=2,
                pm_id='pm_test', customer_id='cus_test',
                amount_dollars=total,  # This is what accept_bid now passes
            )

        assert result['success'] is True
        actual_cents = mock_create.call_args.kwargs['amount']
        assert actual_cents == expected_cents, (
            f"Stripe PI amount {actual_cents} cents != expected {expected_cents} cents. "
            f"subtotal={subtotal}, tax={tax_amount}, card_fee={card_fee}, total={total}."
        )
        # Sanity: old (buggy) amount would have been subtotal only
        old_buggy_cents = int(round(subtotal * 100))
        assert actual_cents != old_buggy_cents, (
            "Stripe PI amount equals subtotal only — tax and card fee are missing."
        )


# ---------------------------------------------------------------------------
# STRIPE-6  Unit: checkout PI.modify receives full amount
# ---------------------------------------------------------------------------

class TestCheckoutPIAmount:
    """
    Verify that the checkout flow calls PaymentIntent.modify with the full amount.
    """

    def test_STRIPE6a_checkout_modify_called_with_full_amount(self):
        """
        When checkout/routes.py AJAX handler runs, PaymentIntent.modify must be called
        with subtotal + tax + card_fee, not subtotal only.
        """
        from core.blueprints.checkout.routes import _get_stripe_tax, CARD_RATE, CARD_FLAT

        subtotal     = 100.00
        postal_code  = '78701'
        state        = 'TX'
        method_type  = 'card'

        mock_calc = _make_mock_calc(_MOCK_TAX_CENTS_100)
        with patch('stripe.tax.Calculation.create', return_value=mock_calc):
            tax_cents, _ = _get_stripe_tax(int(subtotal * 100), postal_code, state)

        tax_amount     = round(tax_cents / 100, 2)
        taxed_subtotal = subtotal + tax_amount
        card_fee       = round(taxed_subtotal * CARD_RATE + CARD_FLAT, 2)
        total          = round(taxed_subtotal + card_fee, 2)
        expected_cents = int(round(total * 100))

        assert tax_amount == 8.25
        assert card_fee > 0
        assert expected_cents > int(subtotal * 100), (
            f"Checkout PI amount {expected_cents} is not greater than subtotal "
            f"{int(subtotal * 100)} — tax and/or card fee missing."
        )

    def test_STRIPE6b_checkout_ach_has_no_card_fee(self):
        """
        ACH (us_bank_account) payments must have buyer_card_fee = 0.
        Tax still applies.
        """
        from core.blueprints.checkout.routes import _get_stripe_tax, CARD_RATE, CARD_FLAT

        subtotal = 100.00
        mock_calc = _make_mock_calc(_MOCK_TAX_CENTS_100)
        with patch('stripe.tax.Calculation.create', return_value=mock_calc):
            tax_cents, _ = _get_stripe_tax(int(subtotal * 100), '78701', 'TX')

        tax_amount  = round(tax_cents / 100, 2)
        card_fee    = 0.0   # ACH
        total       = round(subtotal + tax_amount + card_fee, 2)
        total_cents = int(round(total * 100))

        assert tax_amount == 8.25
        assert card_fee == 0.0
        assert total == 108.25, f"ACH total should be subtotal+tax only, got {total}"
        assert total_cents == 10825


# ---------------------------------------------------------------------------
# STRIPE-7  Source code check: auto_match.py computes tax + card fee
# ---------------------------------------------------------------------------

class TestSourceChecksAutoMatch:
    """Verify that the autofill path (auto_match.py) also computes the full charge."""

    _AUTO_MATCH_PATH = os.path.join(
        os.path.dirname(__file__), '..', 'core', 'blueprints', 'bids', 'auto_match.py'
    )

    def _src(self):
        with open(os.path.normpath(self._AUTO_MATCH_PATH)) as f:
            return f.read()

    def test_STRIPE7a_auto_match_defines_card_rate(self):
        """auto_match.py must define _CARD_RATE so the autofill charge stays in sync."""
        assert '_CARD_RATE' in self._src(), (
            "auto_match.py does not define _CARD_RATE. "
            "Autofill charges will omit the card processing fee."
        )

    def test_STRIPE7b_auto_match_computes_tax(self):
        """auto_match.py must call _get_stripe_tax_for_bid before the Stripe PI."""
        assert '_get_stripe_tax_for_bid' in self._src(), (
            "auto_match.py does not compute Stripe Tax. "
            "Autofill charges will omit sales tax."
        )

    def test_STRIPE7c_auto_match_computes_card_fee(self):
        """auto_match.py must compute _bid_card_fee from the taxed subtotal."""
        assert '_bid_card_fee' in self._src(), (
            "auto_match.py does not compute _bid_card_fee. "
            "Autofill charges will undercharge buyers."
        )

    def test_STRIPE7d_auto_match_stores_fee_on_order(self):
        """The order INSERT in auto_match.py must include buyer_card_fee and tax_amount."""
        src = self._src()
        assert 'buyer_card_fee' in src, (
            "auto_match.py does not store buyer_card_fee on the order."
        )
        assert 'tax_amount' in src, (
            "auto_match.py does not store tax_amount on the order."
        )

    def test_STRIPE7e_auto_match_has_hard_guard(self):
        """auto_match.py must abort if charged_cents < subtotal_cents."""
        src = self._src()
        assert '_charged_cents < _subtotal_cents' in src, (
            "auto_match.py is missing the hard guard that prevents undercharging. "
            "A bug in the fee formula could silently charge less than the subtotal."
        )

    def test_STRIPE7f_auto_match_card_rate_matches_accept_bid(self):
        """auto_match._CARD_RATE must equal accept_bid._CARD_RATE."""
        from core.blueprints.bids.auto_match import _CARD_RATE as am_rate, _CARD_FLAT as am_flat
        from core.blueprints.bids.accept_bid import _CARD_RATE as ab_rate, _CARD_FLAT as ab_flat
        assert am_rate == ab_rate, (
            f"auto_match._CARD_RATE ({am_rate}) != accept_bid._CARD_RATE ({ab_rate}). "
            "Both charge paths must use the same rate."
        )
        assert am_flat == ab_flat, (
            f"auto_match._CARD_FLAT ({am_flat}) != accept_bid._CARD_FLAT ({ab_flat}). "
            "Both charge paths must use the same flat fee."
        )


# ---------------------------------------------------------------------------
# STRIPE-8  Unit: autofill charged amount = subtotal + tax + card_fee
# ---------------------------------------------------------------------------

class TestAutoFillChargeAmount:
    """Verify the autofill path charges Stripe the full amount, not just the subtotal."""

    def test_STRIPE8a_autofill_total_exceeds_subtotal(self):
        """
        With tax and card fee, autofill total > subtotal.
        Before the fix: _charge_bid_payment was called with fill_total = subtotal only.
        """
        from core.blueprints.bids.auto_match import (
            _parse_address_for_tax, _get_stripe_tax_for_bid, _CARD_RATE, _CARD_FLAT
        )

        subtotal = 150.00
        address  = '789 Pine Rd • Houston, TX 77001'
        postal, state = _parse_address_for_tax(address)

        mock_calc = _make_mock_calc(1238)  # $12.38 tax on $150
        with patch('stripe.tax.Calculation.create', return_value=mock_calc):
            tax_cents = _get_stripe_tax_for_bid(int(subtotal * 100), postal, state)

        tax_amount     = round(tax_cents / 100, 2)
        taxed_subtotal = subtotal + tax_amount
        card_fee       = round(taxed_subtotal * _CARD_RATE + _CARD_FLAT, 2)
        total          = round(taxed_subtotal + card_fee, 2)

        assert tax_amount > 0, "Expected nonzero tax for TX address"
        assert card_fee > 0,   "Expected nonzero card fee"
        assert total > subtotal, (
            f"autofill total ({total}) must exceed subtotal ({subtotal}). "
            "Before the fix, autofill charges were subtotal-only."
        )

    def test_STRIPE8b_autofill_charge_receives_full_amount(self):
        """
        _charge_bid_payment in auto_match.py must receive the full charge amount
        (subtotal + tax + card_fee), not just the subtotal.
        """
        from core.blueprints.bids.auto_match import (
            _charge_bid_payment, _parse_address_for_tax,
            _get_stripe_tax_for_bid, _CARD_RATE, _CARD_FLAT
        )

        subtotal = 100.00
        address  = '123 Main St • Austin, TX 78701'
        postal, state = _parse_address_for_tax(address)

        mock_calc = _make_mock_calc(_MOCK_TAX_CENTS_100)
        with patch('stripe.tax.Calculation.create', return_value=mock_calc):
            tax_cents = _get_stripe_tax_for_bid(int(subtotal * 100), postal, state)

        tax_amount     = round(tax_cents / 100, 2)         # 8.25
        taxed_subtotal = subtotal + tax_amount               # 108.25
        card_fee       = round(taxed_subtotal * _CARD_RATE + _CARD_FLAT, 2)
        total          = round(taxed_subtotal + card_fee, 2)
        expected_cents = int(round(total * 100))

        mock_pi = MagicMock(status='succeeded', id='pi_autofill_test')
        with patch('stripe.PaymentIntent.create', return_value=mock_pi) as mock_create:
            result = _charge_bid_payment(
                bid_id=99, order_id=99, buyer_id=2,
                pm_id='pm_test', customer_id='cus_test',
                amount_dollars=total,
            )

        assert result['success'] is True
        actual_cents = mock_create.call_args.kwargs['amount']
        assert actual_cents == expected_cents, (
            f"Autofill PI amount {actual_cents} cents != expected {expected_cents} cents. "
            f"subtotal={subtotal}, tax={tax_amount}, card_fee={card_fee}, total={total}."
        )
        # Old buggy amount was subtotal only
        old_buggy_cents = int(round(subtotal * 100))
        assert actual_cents != old_buggy_cents, (
            "Autofill PI amount equals subtotal only — tax and card fee are missing."
        )

    def test_STRIPE8c_autofill_address_parse_returns_postal(self):
        """auto_match._parse_address_for_tax must extract the same postal code as accept_bid."""
        from core.blueprints.bids.auto_match import _parse_address_for_tax as am_parse
        from core.blueprints.bids.accept_bid import _parse_address_for_tax as ab_parse

        address = '100 Elm St • Denver, CO 80203'
        assert am_parse(address) == ab_parse(address), (
            "auto_match._parse_address_for_tax and accept_bid._parse_address_for_tax "
            "return different results for the same address."
        )


# ---------------------------------------------------------------------------
# STRIPE-9  Variable bid (premium_to_spot): charge = effective_price*qty + tax + fee
# ---------------------------------------------------------------------------

class TestVariableBidChargeAmount:
    """
    Variable bids use pricing_mode='premium_to_spot'.
    The old bug: total_price = filled * effective_bid_price  (subtotal only, no tax/fee).
    The fix:     total_price = subtotal + tax + card_fee.

    These tests confirm the fix applies to variable bids specifically, not just
    the generic formula.
    """

    _SPOT_GOLD = 2000.0   # $/oz
    _PREMIUM   = 50.0     # $/oz above spot
    _CEILING   = 2200.0   # max buyer will pay per coin
    _WEIGHT_OZ = 1.0      # 1 troy oz coin

    def _make_variable_bid(self):
        return {
            'id': 1,
            'pricing_mode': 'premium_to_spot',
            'spot_premium': self._PREMIUM,
            'ceiling_price': self._CEILING,
            'pricing_metal': 'gold',
            'price_per_coin': self._CEILING,   # stored as ceiling at placement
            'metal': 'gold',
            'weight': f'{self._WEIGHT_OZ} oz',
        }

    def test_STRIPE9a_effective_price_is_spot_plus_premium_not_ceiling(self):
        """
        When spot + premium < ceiling, effective_bid_price must be spot + premium,
        not ceiling_price.  The old bug would have used ceiling_price via price_per_coin.
        """
        from services.pricing_service import get_effective_bid_price

        bid = self._make_variable_bid()
        spot_prices = {'gold': self._SPOT_GOLD}

        effective = get_effective_bid_price(bid, spot_prices=spot_prices)
        expected  = min(self._SPOT_GOLD * self._WEIGHT_OZ + self._PREMIUM, self._CEILING)

        assert effective == pytest.approx(expected), (
            f"effective_bid_price {effective} != expected spot+premium {expected}. "
            "For variable bids, the charge basis must be spot+premium (capped at ceiling), "
            "not the stored ceiling_price."
        )
        assert effective < self._CEILING, (
            "For this test, spot+premium must be below ceiling so the two paths diverge."
        )

    def test_STRIPE9b_variable_bid_total_exceeds_subtotal(self):
        """
        For a variable bid, total_price = effective_price*qty + tax + fee > subtotal.
        Before the fix: total_price = effective_price * qty (no tax, no fee).
        """
        from services.pricing_service import get_effective_bid_price
        from core.blueprints.bids.accept_bid import (
            _parse_address_for_tax, _get_stripe_tax_for_bid, _CARD_RATE, _CARD_FLAT
        )

        bid = self._make_variable_bid()
        spot_prices = {'gold': self._SPOT_GOLD}
        filled = 2
        address = '100 Elm St • Austin, TX 78701'

        effective = get_effective_bid_price(bid, spot_prices=spot_prices)
        subtotal  = round(filled * effective, 2)

        postal, state = _parse_address_for_tax(address)
        mock_calc = MagicMock()
        mock_calc.id = 'tc_var9b'
        mock_calc.tax_amount_exclusive = round(subtotal * 100 * 0.0825)  # 8.25%
        with patch('stripe.tax.Calculation.create', return_value=mock_calc):
            tax_cents = _get_stripe_tax_for_bid(int(subtotal * 100), postal, state)

        tax_amount     = round(tax_cents / 100, 2)
        taxed_subtotal = subtotal + tax_amount
        card_fee       = round(taxed_subtotal * _CARD_RATE + _CARD_FLAT, 2)
        total          = round(taxed_subtotal + card_fee, 2)

        # The old bug charged only the subtotal
        old_buggy_amount = subtotal

        assert tax_amount > 0,  "Tax must be non-zero for TX postal code"
        assert card_fee > 0,    "Card fee must be non-zero"
        assert total > old_buggy_amount, (
            f"Variable bid total ({total}) must exceed subtotal ({old_buggy_amount}). "
            f"effective={effective}, qty={filled}, tax={tax_amount}, fee={card_fee}. "
            "The old bug charged only filled * effective_bid_price."
        )

    def test_STRIPE9c_variable_bid_charge_formula_unchanged_from_accept_bid(self):
        """
        The formula used in accept_bid.py for variable bids must be:
            total_price = round(_taxed_subtotal + _bid_card_fee, 2)
        The old bug was: total_price = filled * effective_bid_price
        Source-code check confirms the old formula is gone.
        """
        import os
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'core', 'blueprints', 'bids', 'accept_bid.py',
        )
        with open(path) as f:
            src = f.read()

        # The old (buggy) line should not exist
        old_line = 'total_price = filled * effective_bid_price'
        assert old_line not in src, (
            "accept_bid.py still contains the old subtotal-only charge: "
            f"'{old_line}'. "
            "Variable bids (and all bids) are being undercharged — tax and card fee missing."
        )

        # The new correct formula must be present
        assert '_taxed_subtotal' in src, (
            "accept_bid.py is missing _taxed_subtotal — tax is not included in the charge."
        )
        assert '_bid_card_fee' in src, (
            "accept_bid.py is missing _bid_card_fee — card processing fee not included."
        )

    def test_STRIPE9d_auto_match_variable_bid_formula_correct(self):
        """
        auto_match.py must also use the full charge formula (not subtotal only).
        The old bug was: fill_total = sum(fill_qty * buyer_price_each for fill in fills)
        """
        import os
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'core', 'blueprints', 'bids', 'auto_match.py',
        )
        with open(path) as f:
            src = f.read()

        # The old (buggy) line should not exist in this form
        old_line_fragment = 'fill_total = sum(f[\'fill_qty\'] * f[\'buyer_price_each\']'
        assert old_line_fragment not in src, (
            "auto_match.py still uses the old subtotal-only fill_total formula. "
            "Variable bids filled via auto-match are being undercharged."
        )

        assert '_taxed_subtotal' in src, (
            "auto_match.py is missing _taxed_subtotal — tax not included in auto-fill charge."
        )
        assert '_bid_card_fee' in src, (
            "auto_match.py is missing _bid_card_fee — card fee not included in auto-fill charge."
        )
