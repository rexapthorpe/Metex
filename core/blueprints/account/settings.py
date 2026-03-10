"""
Account Settings Routes

Routes for updating personal info, password, notifications, and profile.
"""

from flask import session, request, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from database import get_db_connection

from . import account_bp


@account_bp.route('/account/update_personal_info', methods=['POST'])
def update_personal_info():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        conn.execute('''
            UPDATE users
            SET first_name = ?, last_name = ?, phone = ?
            WHERE id = ?
        ''', (
            request.form.get('first_name', ''),
            request.form.get('last_name', ''),
            request.form.get('phone', ''),
            user_id
        ))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@account_bp.route('/account/change_password', methods=['POST'])
def change_password():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_id = session['user_id']
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')

    conn = get_db_connection()

    # Verify current password
    user = conn.execute('SELECT password_hash FROM users WHERE id = ?', (user_id,)).fetchone()

    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'}), 404

    # Use the same password verification as login
    if not check_password_hash(user['password_hash'], current_password):
        conn.close()
        return jsonify({'success': False, 'message': 'Current password is incorrect'}), 400

    try:
        # Hash the new password before storing (using pbkdf2:sha256 for compatibility)
        new_password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
        conn.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_password_hash, user_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@account_bp.route('/account/update_notifications', methods=['POST'])
def update_notifications():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        # Create or update notification preferences
        # You may need to create a notifications table first
        conn.execute('''
            INSERT INTO notification_preferences
            (user_id, email_orders, email_bids, email_messages, email_promotions)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (user_id) DO UPDATE SET
                email_orders = EXCLUDED.email_orders,
                email_bids = EXCLUDED.email_bids,
                email_messages = EXCLUDED.email_messages,
                email_promotions = EXCLUDED.email_promotions
        ''', (
            user_id,
            1 if request.form.get('email_orders') else 0,
            1 if request.form.get('email_bids') else 0,
            1 if request.form.get('email_messages') else 0,
            1 if request.form.get('email_promotions') else 0
        ))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@account_bp.route('/account/update_profile', methods=['POST'])
def update_profile():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        conn.execute('''
            UPDATE users
            SET bio = ?
            WHERE id = ?
        ''', (
            request.form.get('bio', ''),
            user_id
        ))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500
