"""
Payment Methods Routes — Stripe SetupIntent implementation

Handles saving, retrieving, and removing payment methods for buyers using
Stripe Customers + SetupIntents.  No raw card data ever touches Metex servers.

Routes (all under account_bp, registered at /account prefix):
  POST /api/payment-methods/setup-intent         create SetupIntent → client_secret
  GET  /api/payment-methods                      list saved methods from Stripe
  POST /api/payment-methods/<pm_id>/detach       remove a saved method
  POST /api/payment-methods/<pm_id>/default      set a method as default

Separation of concerns:
  buyers  → stripe_customer_id on users table (this module)
  sellers → stripe_account_id  on users table (stripe_connect blueprint)
"""

import logging
import stripe
from flask import request, session, jsonify
from database import get_db_connection
from . import account_bp

_log = logging.getLogger(__name__)


# ─── Internal helper ─────────────────────────────────────────────────────────

def _ensure_stripe_customer(user_id: int, conn) -> str:
    """
    Return the Stripe Customer ID for user_id, creating one if needed.
    Writes stripe_customer_id back to DB when a new customer is created.
    Caller owns the connection lifecycle (open + close).
    """
    row = conn.execute(
        'SELECT stripe_customer_id, email, first_name, last_name FROM users WHERE id = ?',
        (user_id,)
    ).fetchone()

    if not row:
        raise ValueError(f'User {user_id} not found')

    customer_id = row['stripe_customer_id']
    if customer_id:
        return customer_id

    # Build display name for the Stripe dashboard
    name_parts = [p for p in (row['first_name'], row['last_name']) if p]
    customer = stripe.Customer.create(
        email=row['email'],
        name=' '.join(name_parts) if name_parts else None,
        metadata={'metex_user_id': str(user_id)},
    )

    conn.execute(
        'UPDATE users SET stripe_customer_id = ? WHERE id = ?',
        (customer.id, user_id)
    )
    conn.commit()
    _log.info('[PM] Created Stripe customer %s for user %s', customer.id, user_id)
    return customer.id


# ─── Routes ──────────────────────────────────────────────────────────────────

@account_bp.route('/api/payment-methods/setup-intent', methods=['POST'])
def create_setup_intent():
    """
    Create (or retrieve) a Stripe SetupIntent for the logged-in buyer.
    Returns the client_secret so the frontend can mount a Payment Element.
    """
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()
    try:
        customer_id = _ensure_stripe_customer(user_id, conn)
    except Exception as e:
        _log.exception('[PM] Failed to ensure customer for user %s', user_id)
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

    try:
        setup_intent = stripe.SetupIntent.create(
            customer=customer_id,
            payment_method_types=['card', 'us_bank_account'],
            usage='off_session',  # allows future off-session charges at checkout
        )
        _log.info('[PM] SetupIntent %s created for customer %s', setup_intent.id, customer_id)
    except stripe.error.StripeError as e:
        _log.error('[PM] Stripe error creating SetupIntent: %s', e)
        return jsonify({'success': False, 'error': str(e)}), 500

    return jsonify({
        'success': True,
        'client_secret': setup_intent.client_secret,
    })


@account_bp.route('/api/payment-methods', methods=['GET'])
def get_payment_methods():
    """
    List saved payment methods for the logged-in buyer, fetched live from Stripe.
    Returns cards only (v1).  ACH bank accounts can be added later with type='us_bank_account'.
    """
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()
    try:
        row = conn.execute(
            'SELECT stripe_customer_id FROM users WHERE id = ?', (user_id,)
        ).fetchone()
        customer_id = row['stripe_customer_id'] if row else None
    finally:
        conn.close()

    if not customer_id:
        return jsonify({'success': True, 'payment_methods': []})

    try:
        # Retrieve customer to find the default PM
        customer = stripe.Customer.retrieve(customer_id)
        default_pm_id = (customer.get('invoice_settings') or {}).get('default_payment_method')

        methods = []

        # Cards
        for pm in stripe.PaymentMethod.list(customer=customer_id, type='card').auto_paging_iter():
            card = pm.get('card') or {}
            methods.append({
                'id': pm.id,
                'method_type': 'card',
                'brand': card.get('brand', 'unknown'),
                'last4': card.get('last4', ''),
                'exp_month': card.get('exp_month'),
                'exp_year': card.get('exp_year'),
                'funding': card.get('funding', ''),  # 'credit', 'debit', 'prepaid'
                'is_default': pm.id == default_pm_id,
            })

        # ACH bank accounts
        for pm in stripe.PaymentMethod.list(customer=customer_id, type='us_bank_account').auto_paging_iter():
            bank = pm.get('us_bank_account') or {}
            methods.append({
                'id': pm.id,
                'method_type': 'bank_account',
                'brand': bank.get('bank_name') or 'Bank',
                'last4': bank.get('last4', ''),
                'exp_month': None,
                'exp_year': None,
                'funding': 'bank',
                'is_default': pm.id == default_pm_id,
            })

        # Default first
        methods.sort(key=lambda m: (not m['is_default'], 0))

    except stripe.error.StripeError as e:
        _log.error('[PM] Stripe error listing methods for customer %s: %s', customer_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500

    return jsonify({'success': True, 'payment_methods': methods})


@account_bp.route('/api/payment-methods/<string:pm_id>/detach', methods=['POST'])
def detach_payment_method(pm_id):
    """
    Detach a saved payment method from the logged-in buyer's Stripe customer.
    Ownership is verified against the stored stripe_customer_id before detach.
    """
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()
    try:
        row = conn.execute(
            'SELECT stripe_customer_id FROM users WHERE id = ?', (user_id,)
        ).fetchone()
        customer_id = row['stripe_customer_id'] if row else None
    finally:
        conn.close()

    if not customer_id:
        return jsonify({'success': False, 'error': 'No payment account found'}), 404

    try:
        # Verify ownership before detaching
        pm = stripe.PaymentMethod.retrieve(pm_id)
        if pm.get('customer') != customer_id:
            return jsonify({'success': False, 'error': 'Payment method not found'}), 403

        stripe.PaymentMethod.detach(pm_id)
        _log.info('[PM] Detached %s from customer %s (user %s)', pm_id, customer_id, user_id)

    except stripe.error.InvalidRequestError:
        return jsonify({'success': False, 'error': 'Payment method not found'}), 404
    except stripe.error.StripeError as e:
        _log.error('[PM] Stripe error detaching %s: %s', pm_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500

    return jsonify({'success': True, 'message': 'Payment method removed'})


@account_bp.route('/api/payment-methods/<string:pm_id>/default', methods=['POST'])
def set_default_payment_method(pm_id):
    """
    Set a payment method as the default for the logged-in buyer.
    Updates Stripe customer.invoice_settings.default_payment_method.
    """
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()
    try:
        row = conn.execute(
            'SELECT stripe_customer_id FROM users WHERE id = ?', (user_id,)
        ).fetchone()
        customer_id = row['stripe_customer_id'] if row else None
    finally:
        conn.close()

    if not customer_id:
        return jsonify({'success': False, 'error': 'No payment account found'}), 404

    try:
        # Verify ownership
        pm = stripe.PaymentMethod.retrieve(pm_id)
        if pm.get('customer') != customer_id:
            return jsonify({'success': False, 'error': 'Payment method not found'}), 403

        stripe.Customer.modify(
            customer_id,
            invoice_settings={'default_payment_method': pm_id},
        )
        _log.info('[PM] Default set to %s for customer %s (user %s)', pm_id, customer_id, user_id)

    except stripe.error.StripeError as e:
        _log.error('[PM] Stripe error setting default %s: %s', pm_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500

    return jsonify({'success': True, 'message': 'Default payment method updated'})
