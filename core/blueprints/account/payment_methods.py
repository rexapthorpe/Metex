"""
Payment Methods Routes

Handles saving, retrieving, and deleting payment methods for users.
Note: This stores only masked card data (last 4 digits) - never full card numbers.
"""

from flask import request, session, jsonify
from database import get_db_connection
from . import account_bp


def detect_card_type(card_number):
    """Detect card type from card number prefix."""
    # Remove spaces and dashes
    card_number = card_number.replace(' ', '').replace('-', '')

    if card_number.startswith('4'):
        return 'visa'
    elif card_number.startswith(('51', '52', '53', '54', '55')) or \
         (len(card_number) >= 4 and 2221 <= int(card_number[:4]) <= 2720):
        return 'mastercard'
    elif card_number.startswith(('34', '37')):
        return 'amex'
    elif card_number.startswith(('6011', '644', '645', '646', '647', '648', '649', '65')):
        return 'discover'
    else:
        return 'unknown'


@account_bp.route('/api/payment-methods', methods=['GET'])
def get_payment_methods():
    """Get all saved payment methods for the current user."""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    methods = conn.execute('''
        SELECT id, card_type, last_four, expiry_month, expiry_year,
               cardholder_name, is_default, created_at
        FROM payment_methods
        WHERE user_id = ?
        ORDER BY is_default DESC, created_at DESC
    ''', (user_id,)).fetchall()

    conn.close()

    return jsonify({
        'success': True,
        'payment_methods': [dict(m) for m in methods]
    })


@account_bp.route('/api/payment-methods', methods=['POST'])
def save_payment_method():
    """Save a new payment method for the current user."""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    user_id = session['user_id']
    data = request.get_json()

    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    card_number = data.get('card_number', '').replace(' ', '').replace('-', '')
    cardholder_name = data.get('cardholder_name', '').strip()
    expiry = data.get('expiry_date', '')  # Format: MM/YY

    # Validate required fields
    if not card_number or len(card_number) < 13:
        return jsonify({'success': False, 'error': 'Invalid card number'}), 400

    if not cardholder_name:
        return jsonify({'success': False, 'error': 'Cardholder name required'}), 400

    if not expiry or '/' not in expiry:
        return jsonify({'success': False, 'error': 'Invalid expiry date'}), 400

    # Parse expiry
    try:
        expiry_parts = expiry.split('/')
        expiry_month = int(expiry_parts[0])
        expiry_year = int('20' + expiry_parts[1]) if len(expiry_parts[1]) == 2 else int(expiry_parts[1])
    except (ValueError, IndexError):
        return jsonify({'success': False, 'error': 'Invalid expiry date format'}), 400

    # Detect card type and get last 4 digits
    card_type = detect_card_type(card_number)
    last_four = card_number[-4:]

    conn = get_db_connection()

    # Check if this card already exists for the user
    existing = conn.execute('''
        SELECT id FROM payment_methods
        WHERE user_id = ? AND last_four = ? AND expiry_month = ? AND expiry_year = ?
    ''', (user_id, last_four, expiry_month, expiry_year)).fetchone()

    if existing:
        conn.close()
        return jsonify({'success': True, 'message': 'Card already saved', 'id': existing['id']})

    # Check if this is the first card (make it default)
    existing_count = conn.execute(
        'SELECT COUNT(*) as count FROM payment_methods WHERE user_id = ?',
        (user_id,)
    ).fetchone()['count']

    is_default = 1 if existing_count == 0 else 0

    # Save the card (only masked data)
    cursor = conn.execute('''
        INSERT INTO payment_methods (user_id, card_type, last_four, expiry_month, expiry_year, cardholder_name, is_default)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, card_type, last_four, expiry_month, expiry_year, cardholder_name, is_default))

    new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'message': 'Card saved successfully',
        'id': new_id,
        'card_type': card_type,
        'last_four': last_four
    })


@account_bp.route('/api/payment-methods/<int:method_id>', methods=['DELETE'])
def delete_payment_method(method_id):
    """Delete a saved payment method."""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    # SECURITY: Explicit authorization check (defense in depth)
    from utils.security import authorize_payment_method_owner, AuthorizationError
    try:
        authorize_payment_method_owner(method_id)
    except AuthorizationError:
        return jsonify({'success': False, 'error': 'Payment method not found'}), 403

    user_id = session['user_id']
    conn = get_db_connection()

    # Double-check ownership with scoped query (belt and suspenders)
    method = conn.execute(
        'SELECT id, is_default FROM payment_methods WHERE id = ? AND user_id = ?',
        (method_id, user_id)
    ).fetchone()

    if not method:
        conn.close()
        return jsonify({'success': False, 'error': 'Payment method not found'}), 403

    # Delete the method
    conn.execute('DELETE FROM payment_methods WHERE id = ?', (method_id,))

    # If this was the default, set another as default
    if method['is_default']:
        other = conn.execute(
            'SELECT id FROM payment_methods WHERE user_id = ? ORDER BY created_at DESC LIMIT 1',
            (user_id,)
        ).fetchone()
        if other:
            conn.execute('UPDATE payment_methods SET is_default = 1 WHERE id = ?', (other['id'],))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Payment method deleted'})


@account_bp.route('/api/payment-methods/<int:method_id>/default', methods=['POST'])
def set_default_payment_method(method_id):
    """Set a payment method as default."""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    # SECURITY: Explicit authorization check (defense in depth)
    from utils.security import authorize_payment_method_owner, AuthorizationError
    try:
        authorize_payment_method_owner(method_id)
    except AuthorizationError:
        return jsonify({'success': False, 'error': 'Payment method not found'}), 403

    user_id = session['user_id']
    conn = get_db_connection()

    # Double-check ownership with scoped query (belt and suspenders)
    method = conn.execute(
        'SELECT id FROM payment_methods WHERE id = ? AND user_id = ?',
        (method_id, user_id)
    ).fetchone()

    if not method:
        conn.close()
        return jsonify({'success': False, 'error': 'Payment method not found'}), 403

    # Clear all defaults for this user
    conn.execute('UPDATE payment_methods SET is_default = 0 WHERE user_id = ?', (user_id,))

    # Set this one as default
    conn.execute('UPDATE payment_methods SET is_default = 1 WHERE id = ?', (method_id,))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Default payment method updated'})
