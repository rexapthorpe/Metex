"""
Preferences and Additional API Routes

Routes for user preferences and additional account APIs.
"""

from flask import session, request, jsonify
from database import get_db_connection

from . import account_bp


@account_bp.route('/account/get_preferences', methods=['GET'])
def get_preferences():
    """Get user notification preferences"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        prefs = conn.execute(
            'SELECT * FROM user_preferences WHERE user_id = ?',
            (user_id,)
        ).fetchone()
        conn.close()

        if not prefs:
            # Return default preferences if not set
            return jsonify({
                'success': True,
                'preferences': {
                    'email_listing_sold': 1,
                    'email_bid_filled': 1,
                    'email_price_alerts': 0,
                    'email_newsletter': 1,
                    'inapp_listing_sold': 1,
                    'inapp_bid_filled': 1,
                    'inapp_messages': 1,
                    'inapp_price_alerts': 0
                }
            })

        return jsonify({
            'success': True,
            'preferences': {
                'email_listing_sold': prefs['email_listing_sold'],
                'email_bid_filled': prefs['email_bid_filled'],
                'email_price_alerts': prefs['email_price_alerts'] if 'email_price_alerts' in prefs.keys() else 0,
                'email_newsletter': prefs['email_newsletter'] if 'email_newsletter' in prefs.keys() else 1,
                'inapp_listing_sold': prefs['inapp_listing_sold'],
                'inapp_bid_filled': prefs['inapp_bid_filled'],
                'inapp_messages': prefs['inapp_messages'] if 'inapp_messages' in prefs.keys() else 1,
                'inapp_price_alerts': prefs['inapp_price_alerts'] if 'inapp_price_alerts' in prefs.keys() else 0
            }
        })
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@account_bp.route('/account/update_preferences', methods=['POST'])
def update_preferences():
    """Update user notification preferences"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_id = session['user_id']
    data = request.get_json()

    if not data:
        return jsonify({'success': False, 'message': 'No data provided'}), 400

    conn = get_db_connection()

    try:
        # Extract all preferences from request
        email_listing_sold = 1 if data.get('email_listing_sold') else 0
        email_bid_filled = 1 if data.get('email_bid_filled') else 0
        email_price_alerts = 1 if data.get('email_price_alerts') else 0
        email_newsletter = 1 if data.get('email_newsletter') else 0
        inapp_listing_sold = 1 if data.get('inapp_listing_sold') else 0
        inapp_bid_filled = 1 if data.get('inapp_bid_filled') else 0
        inapp_messages = 1 if data.get('inapp_messages') else 0
        inapp_price_alerts = 1 if data.get('inapp_price_alerts') else 0

        conn.execute('''
            INSERT INTO user_preferences
            (user_id, email_listing_sold, email_bid_filled, email_price_alerts, email_newsletter,
             inapp_listing_sold, inapp_bid_filled, inapp_messages, inapp_price_alerts, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id) DO UPDATE SET
                email_listing_sold = EXCLUDED.email_listing_sold,
                email_bid_filled = EXCLUDED.email_bid_filled,
                email_price_alerts = EXCLUDED.email_price_alerts,
                email_newsletter = EXCLUDED.email_newsletter,
                inapp_listing_sold = EXCLUDED.inapp_listing_sold,
                inapp_bid_filled = EXCLUDED.inapp_bid_filled,
                inapp_messages = EXCLUDED.inapp_messages,
                inapp_price_alerts = EXCLUDED.inapp_price_alerts,
                updated_at = EXCLUDED.updated_at
        ''', (user_id, email_listing_sold, email_bid_filled, email_price_alerts, email_newsletter,
              inapp_listing_sold, inapp_bid_filled, inapp_messages, inapp_price_alerts))

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Preferences updated successfully'
        })
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


# API: Get saved addresses
@account_bp.route('/account/api/addresses', methods=['GET'])
def get_saved_addresses():
    """Get all saved addresses for the current user"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        addresses = conn.execute(
            "SELECT * FROM addresses WHERE user_id = ? ORDER BY id",
            (user_id,)
        ).fetchall()

        addresses_list = [dict(row) for row in addresses]
        conn.close()

        return jsonify({
            'success': True,
            'addresses': addresses_list
        })
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


# API: Include order in portfolio
@account_bp.route('/account/api/orders/<int:order_id>/portfolio/include', methods=['POST'])
def include_order_in_portfolio(order_id):
    """Remove all portfolio exclusions for order items in this order"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        # Verify order belongs to user
        order = conn.execute(
            "SELECT id FROM orders WHERE id = ? AND buyer_id = ?",
            (order_id, user_id)
        ).fetchone()

        if not order:
            conn.close()
            return jsonify({'success': False, 'error': 'Order not found'}), 404

        # Get all order_items for this order
        order_items = conn.execute(
            "SELECT id FROM order_items WHERE order_id = ?",
            (order_id,)
        ).fetchall()

        # Remove portfolio exclusions for all order items
        for item in order_items:
            conn.execute(
                "DELETE FROM portfolio_exclusions WHERE user_id = ? AND order_item_id = ?",
                (user_id, item['id'])
            )

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Order included in portfolio'
        })
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


# REMOVED: Delivery address update route
# The delivery address feature has been removed from the Orders tab
"""
@account_bp.route('/account/api/orders/<int:order_id>/delivery-address', methods=['PUT'])
def update_order_delivery_address(order_id):
    # Update the delivery address for an order
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        # Verify order belongs to user
        order = conn.execute(
            "SELECT id FROM orders WHERE id = ? AND buyer_id = ?",
            (order_id, user_id)
        ).fetchone()

        if not order:
            conn.close()
            return jsonify({'success': False, 'error': 'Order not found'}), 404

        # Get address_id from request
        data = request.get_json()
        address_id = data.get('address_id')

        if not address_id:
            conn.close()
            return jsonify({'success': False, 'error': 'Address ID required'}), 400

        # Get address details
        address = conn.execute(
            "SELECT * FROM addresses WHERE id = ? AND user_id = ?",
            (address_id, user_id)
        ).fetchone()

        if not address:
            conn.close()
            return jsonify({'success': False, 'error': 'Address not found'}), 404

        # Format address as JSON string for storage
        import json
        address_data = {
            'name': address['name'],
            'street': address['street'],
            'street_line2': address['street_line2'] if address['street_line2'] else '',
            'city': address['city'],
            'state': address['state'],
            'zip_code': address['zip_code'],
            'country': address['country'] if address['country'] else 'USA'
        }

        # Update order delivery_address
        conn.execute(
            "UPDATE orders SET delivery_address = ? WHERE id = ?",
            (json.dumps(address_data), order_id)
        )

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Delivery address updated successfully',
            'updated_address': address_data
        })
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500
"""
