"""
Stripe Connect routes for seller payout onboarding AND payment webhooks.

stripe.api_key is set once globally in config.py at import time — do NOT
re-initialize it here.

Onboarding flow:
  1. Seller clicks "Set up payouts" → GET /stripe/create-account
     Creates a Stripe Express account, saves stripe_account_id, redirects to step 2.
  2. GET /stripe/create-account-link
     Generates a fresh onboarding link and redirects to Stripe.
  3. Stripe redirects back to GET /stripe/return
     Fetches account status, updates DB, redirects to /account.
  4. If the link expires, Stripe calls GET /stripe/refresh
     Regenerates the link and redirects to Stripe again.

Webhook flow:
  POST /stripe/webhook
    Stripe posts signed events here.  We verify the signature and handle:
      payment_intent.succeeded — marks the corresponding order as paid.
    This is the source of truth for order payment; /order-success only renders
    a status page and must not be relied on to finalize orders.
"""

import logging

import stripe
from flask import current_app, flash, jsonify, redirect, request, session, url_for

from database import get_db_connection
from utils.csrf import csrf_exempt

from . import stripe_bp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_login():
    """Return a redirect to login if the user is not authenticated, else None."""
    if 'user_id' not in session:
        flash('Please log in to access this page.', 'error')
        return redirect(url_for('auth.login'))
    return None


def is_stripe_ready(user) -> bool:
    """
    Return True if the seller's Stripe account is fully enabled for both
    charges and payouts.  Safe to call with None or a row missing stripe cols.
    """
    if not user:
        return False
    try:
        return bool(user['stripe_charges_enabled']) and bool(user['stripe_payouts_enabled'])
    except (KeyError, TypeError, IndexError):
        return False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@stripe_bp.route('/create-account')
def create_account():
    """
    Create a Stripe Express account for the logged-in user (if they don't
    already have one), save stripe_account_id, then redirect to onboarding.
    """
    guard = _require_login()
    if guard:
        return guard

    user_id = session['user_id']

    try:
        conn = get_db_connection()
        user = conn.execute(
            "SELECT id, stripe_account_id FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()

        if not user:
            conn.close()
            flash('User not found.', 'error')
            return redirect(url_for('account.account'))

        # If user has an old account, clear it so a fresh one is created with correct config.
        if user['stripe_account_id']:
            logger.info(
                "[Stripe] Clearing old account %s for user %s to force re-onboarding.",
                user['stripe_account_id'], user_id,
            )
            conn.execute(
                """UPDATE users
                      SET stripe_account_id          = NULL,
                          stripe_onboarding_complete = 0,
                          stripe_charges_enabled     = 0,
                          stripe_payouts_enabled     = 0
                    WHERE id = ?""",
                (user_id,),
            )
            conn.commit()

        account = stripe.Account.create(
            type='express',
            country='US',
            business_type='individual',
            business_profile={
                'product_description': 'Selling coins and precious metals via Metex marketplace',
            },
            capabilities={
                'transfers': {'requested': True},
            },
            metadata={'user_id': str(user_id)},
        )

        logger.info("[Stripe] Created new account %s for user %s.", account.id, user_id)
        conn.execute(
            "UPDATE users SET stripe_account_id = ? WHERE id = ?",
            (account.id, user_id),
        )
        conn.commit()
        conn.close()

    except stripe.error.StripeError as e:
        logger.error("[Stripe] create_account failed for user %s: %s", user_id, e)
        flash('Could not connect to Stripe. Please try again.', 'error')
        return redirect(url_for('account.account'))
    except Exception:
        logger.exception("[Stripe] Unexpected error in create_account for user %s", user_id)
        flash('An unexpected error occurred. Please try again.', 'error')
        return redirect(url_for('account.account'))

    return redirect(url_for('stripe_connect.create_account_link'))


@stripe_bp.route('/create-account-link')
def create_account_link():
    """
    Generate a fresh Stripe onboarding link for the current user's Express
    account and redirect them to it.
    """
    guard = _require_login()
    if guard:
        return guard

    user_id = session['user_id']

    try:
        conn = get_db_connection()
        user = conn.execute(
            "SELECT stripe_account_id FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        conn.close()

        if not user or not user['stripe_account_id']:
            return redirect(url_for('stripe_connect.create_account'))

        account_link = stripe.AccountLink.create(
            account=user['stripe_account_id'],
            refresh_url=url_for('stripe_connect.refresh', _external=True),
            return_url=url_for('stripe_connect.stripe_return', _external=True),
            type='account_onboarding',
        )

    except stripe.error.StripeError as e:
        logger.error("[Stripe] create_account_link failed for user %s: %s", user_id, e)
        flash('Could not start Stripe onboarding. Please try again.', 'error')
        return redirect(url_for('account.account'))
    except Exception:
        logger.exception("[Stripe] Unexpected error in create_account_link for user %s", user_id)
        flash('An unexpected error occurred. Please try again.', 'error')
        return redirect(url_for('account.account'))

    return redirect(account_link.url)


@stripe_bp.route('/return')
def stripe_return():
    """
    Called by Stripe after the seller completes (or exits) onboarding.
    Fetches the latest account status from Stripe and persists it to the DB.
    """
    guard = _require_login()
    if guard:
        return guard

    user_id = session['user_id']

    try:
        conn = get_db_connection()
        user = conn.execute(
            "SELECT stripe_account_id FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()

        if user and user['stripe_account_id']:
            account = stripe.Account.retrieve(user['stripe_account_id'])
            conn.execute(
                """UPDATE users
                      SET stripe_onboarding_complete = ?,
                          stripe_charges_enabled     = ?,
                          stripe_payouts_enabled     = ?
                    WHERE id = ?""",
                (
                    1 if account.details_submitted else 0,
                    1 if account.charges_enabled else 0,
                    1 if account.payouts_enabled else 0,
                    user_id,
                ),
            )
            conn.commit()

        conn.close()

    except stripe.error.StripeError as e:
        logger.error("[Stripe] stripe_return failed for user %s: %s", user_id, e)
        flash('Could not verify your Stripe account status. Please try again.', 'error')
        return redirect(url_for('account.account'))
    except Exception:
        logger.exception("[Stripe] Unexpected error in stripe_return for user %s", user_id)
        flash('An unexpected error occurred. Please try again.', 'error')
        return redirect(url_for('account.account'))

    flash('Payout account updated. Check your status below.', 'success')
    return redirect(url_for('account.account'))


@stripe_bp.route('/refresh')
def refresh():
    """
    Called by Stripe when an onboarding link expires before the seller
    finishes.  Simply regenerates a fresh link and redirects.
    """
    guard = _require_login()
    if guard:
        return guard

    return redirect(url_for('stripe_connect.create_account_link'))


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

@stripe_bp.route('/webhook', methods=['POST'])
@csrf_exempt
def stripe_webhook():
    """
    Receive and verify Stripe webhook events.

    This endpoint is the source of truth for payment finalization.
    Stripe calls it directly — it does not go through the browser, so it is
    immune to tab closes, browser crashes, or failed redirects.

    Idempotent: receiving the same event more than once is safe.

    Currently handled events:
        payment_intent.succeeded  →  marks the linked order as paid
    """
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    webhook_secret = current_app.config.get('STRIPE_WEBHOOK_SECRET', '')

    logger.info("[Stripe webhook] received request")

    if not webhook_secret:
        logger.error(
            "[Stripe webhook] STRIPE_WEBHOOK_SECRET is not configured. "
            "Set it in .env to the whsec_... value from `stripe listen` or "
            "the Stripe Dashboard."
        )
        return jsonify({'error': 'Webhook secret not configured'}), 500

    # Verify the event signature.  construct_event raises on any failure.
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError:
        logger.warning("[Stripe webhook] invalid payload (not valid JSON)")
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError:
        logger.warning("[Stripe webhook] signature verification failed")
        return jsonify({'error': 'Invalid signature'}), 400

    logger.info("[Stripe webhook] verified event type=%s id=%s", event['type'], event['id'])

    # Dispatch to the appropriate handler.
    if event['type'] == 'payment_intent.succeeded':
        _handle_payment_intent_succeeded(event['data']['object'])

    # Acknowledge all events we don't explicitly handle — Stripe will retry
    # on non-2xx, so always return 200 for unhandled types.
    return jsonify({'received': True}), 200


def _extract_payment_method_type(payment_intent):
    """
    Extract the actual payment method type used from a PaymentIntent object.

    Prefers charge-level detail (payment_method_details.type) so we get the
    exact rail ('card', 'us_bank_account', etc.).  Falls back to the first
    entry in payment_method_types if charges aren't expanded in the payload.
    """
    charges = payment_intent.get('charges', {})
    charge_list = charges.get('data', [])
    if charge_list:
        pm_details = charge_list[0].get('payment_method_details', {})
        pm_type = pm_details.get('type')
        if pm_type:
            return pm_type

    # Fallback: use the allowed types list (we only allow one at a time)
    pm_types = payment_intent.get('payment_method_types', [])
    return pm_types[0] if pm_types else 'unknown'


def _handle_payment_intent_succeeded(payment_intent):
    """
    Mark the order linked to this PaymentIntent as paid and record payment details.

    Persists:
      - status → 'paid'
      - stripe_payment_intent_id
      - paid_at (UTC timestamp)
      - payment_method_type ('card' or 'us_bank_account')
      - requires_payment_clearance (1 for ACH/bank, 0 for card)

    Called only after Stripe signature verification, so payment_intent data
    can be trusted.  This function is idempotent: re-processing an already-paid
    order is a no-op.
    """
    from datetime import datetime

    pi_id = payment_intent.get('id', '<unknown>')
    logger.info("[Stripe webhook] payment_intent.succeeded  pi=%s", pi_id)

    order_id = payment_intent.get('metadata', {}).get('order_id')
    if not order_id:
        # Metadata lookup failed — try finding the order by stripe_payment_intent_id.
        # This handles the case where the PI ID was stored on the order during checkout
        # Phase 1 but metadata was never stamped.
        conn = get_db_connection()
        try:
            row = conn.execute(
                "SELECT id FROM orders WHERE stripe_payment_intent_id = ?",
                (pi_id,)
            ).fetchone()
        finally:
            conn.close()
        if row:
            order_id = row['id']
            logger.info(
                "[Stripe webhook] found order via stripe_payment_intent_id fallback  order_id=%s  pi=%s",
                order_id, pi_id,
            )
        else:
            # Truly unlinked PI (e.g., abandoned checkout before order was created).
            logger.warning(
                "[Stripe webhook] payment_intent.succeeded has no order_id in metadata and no DB match  pi=%s",
                pi_id,
            )
            return

    payment_method_type = _extract_payment_method_type(payment_intent)
    requires_clearance = 1 if payment_method_type == 'us_bank_account' else 0
    paid_at = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

    logger.info(
        "[Stripe webhook] payment_method_type=%s requires_clearance=%s  pi=%s",
        payment_method_type, requires_clearance, pi_id,
    )

    conn = get_db_connection()
    try:
        order = conn.execute(
            "SELECT id, status FROM orders WHERE id = ?",
            (order_id,)
        ).fetchone()

        if not order:
            logger.warning(
                "[Stripe webhook] order not found  order_id=%s  pi=%s",
                order_id, pi_id,
            )
            return

        if order['status'] == 'paid':
            # Already finalized — idempotent, nothing to do.
            logger.info(
                "[Stripe webhook] order already paid, skipping  order_id=%s  pi=%s",
                order_id, pi_id,
            )
            return

        conn.execute(
            """UPDATE orders
                  SET status                     = 'paid',
                      payment_status             = 'paid',
                      stripe_payment_intent_id   = ?,
                      paid_at                    = ?,
                      payment_method_type        = ?,
                      requires_payment_clearance = ?
                WHERE id = ?""",
            (pi_id, paid_at, payment_method_type, requires_clearance, order_id),
        )
        conn.commit()
        logger.info(
            "[Stripe webhook] order marked paid  order_id=%s  pi=%s  method=%s",
            order_id, pi_id, payment_method_type,
        )

    except Exception:
        logger.exception(
            "[Stripe webhook] unexpected error handling payment_intent.succeeded  "
            "order_id=%s  pi=%s", order_id, pi_id,
        )
    finally:
        conn.close()
