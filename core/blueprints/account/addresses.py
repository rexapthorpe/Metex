"""
Address Management Routes

Routes for adding, editing, deleting, and retrieving addresses.
"""

from flask import session, request, jsonify
from database import get_db_connection

from . import account_bp


@account_bp.route('/account/delete_address/<int:address_id>', methods=['POST'])
def delete_address(address_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        # Verify address belongs to user
        address = conn.execute(
            'SELECT * FROM addresses WHERE id = ? AND user_id = ?',
            (address_id, user_id)
        ).fetchone()

        if not address:
            conn.close()
            return jsonify({'success': False, 'message': 'Address not found'}), 404

        conn.execute('DELETE FROM addresses WHERE id = ?', (address_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@account_bp.route('/account/add_address', methods=['POST'])
def add_address():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        conn.execute('''
            INSERT INTO addresses (user_id, name, street, street_line2, city, state, zip_code, country)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            request.form.get('name'),
            request.form.get('street'),
            request.form.get('street_line2', ''),
            request.form.get('city'),
            request.form.get('state'),
            request.form.get('zip_code'),
            request.form.get('country', 'USA')
        ))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@account_bp.route('/account/edit_address/<int:address_id>', methods=['POST'])
def edit_address(address_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        # Verify address belongs to user
        address = conn.execute(
            'SELECT * FROM addresses WHERE id = ? AND user_id = ?',
            (address_id, user_id)
        ).fetchone()

        if not address:
            conn.close()
            return jsonify({'success': False, 'message': 'Address not found'}), 404

        conn.execute('''
            UPDATE addresses
            SET name = ?, street = ?, street_line2 = ?, city = ?, state = ?, zip_code = ?, country = ?
            WHERE id = ?
        ''', (
            request.form.get('name'),
            request.form.get('street'),
            request.form.get('street_line2', ''),
            request.form.get('city'),
            request.form.get('state'),
            request.form.get('zip_code'),
            request.form.get('country', 'USA'),
            address_id
        ))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@account_bp.route('/account/get_addresses', methods=['GET'])
def get_addresses():
    """Fetch all addresses for the current user (for dropdowns)"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        # Fetch user info for auto-populating recipient name fields
        user_info = conn.execute(
            'SELECT first_name, last_name FROM users WHERE id = ?',
            (user_id,)
        ).fetchone()

        addresses = conn.execute(
            'SELECT * FROM addresses WHERE user_id = ? ORDER BY id',
            (user_id,)
        ).fetchall()
        conn.close()

        # Convert to list of dicts
        addresses_list = []
        for addr in addresses:
            addresses_list.append({
                'id': addr['id'],
                'name': addr['name'],
                'street': addr['street'],
                'street_line2': addr['street_line2'] if 'street_line2' in addr.keys() else '',
                'city': addr['city'],
                'state': addr['state'],
                'zip_code': addr['zip_code'],
                'country': addr['country']
            })

        return jsonify({
            'success': True,
            'addresses': addresses_list,
            'user_info': {
                'first_name': user_info['first_name'] if user_info else '',
                'last_name': user_info['last_name'] if user_info else ''
            }
        })
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@account_bp.route('/account/get_address/<int:address_id>', methods=['GET'])
def get_address(address_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        address = conn.execute(
            'SELECT * FROM addresses WHERE id = ? AND user_id = ?',
            (address_id, user_id)
        ).fetchone()
        conn.close()

        if not address:
            return jsonify({'success': False, 'message': 'Address not found'}), 404

        return jsonify({
            'success': True,
            'address': {
                'id': address['id'],
                'name': address['name'],
                'street': address['street'],
                'street_line2': address['street_line2'] if 'street_line2' in address.keys() else '',
                'city': address['city'],
                'state': address['state'],
                'zip_code': address['zip_code'],
                'country': address['country']
            }
        })
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500
