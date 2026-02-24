# core/blueprints/cart/api.py
"""
Cart API endpoints.

Routes:
- /api/bucket/<int:bucket_id>/cart_sellers - Get sellers for cart items in a bucket
- /api/bucket/<int:bucket_id>/can_refill/<int:current_seller_id> - Check refill availability
- /api/bucket/<int:bucket_id>/price_breakdown - Get price breakdown for cart items
- /api/bucket/<int:bucket_id>/can_refill_listing/<int:current_listing_id> - Check listing refill

Extracted from routes.py during refactor - NO BEHAVIOR CHANGE.
"""

from flask import session, jsonify
from datetime import datetime
from database import get_db_connection
from utils.cart_utils import get_cart_items

from . import cart_bp


@cart_bp.route('/api/bucket/<int:bucket_id>/cart_sellers')
def get_cart_sellers(bucket_id):
    # SECURITY: Require authentication to view cart sellers
    if 'user_id' not in session:
        return jsonify([])  # Return empty array for unauthenticated users

    conn = get_db_connection()
    cart_items = get_cart_items(conn)

    # Get removed sellers for this bucket from session
    bucket_key = str(bucket_id)
    removed_seller_ids = session.get('removed_sellers', {}).get(bucket_key, [])

    # Filter to this bucket and exclude removed sellers
    filtered = [
        item for item in cart_items
        if item['category_id'] == bucket_id
        and item['seller_id'] not in removed_seller_ids
    ]

    sellers = {}
    for item in filtered:
        seller_id = item['seller_id']
        if seller_id not in sellers:
            sellers[seller_id] = {
                'seller_id': seller_id,
                'username': item['seller_username'],
                'price_per_coin': item['price_per_coin'],
                'quantity': 0,
                'rating': item['seller_rating'],
                'num_reviews': item['seller_rating_count'],
                # Cart-specific metrics
                'total_qty': 0,
                'total_price': 0,
                'price_sum': 0,
                'item_count': 0
            }
        sellers[seller_id]['quantity'] += item['quantity']
        sellers[seller_id]['total_qty'] += item['quantity']
        # Use effective_price if available (handles premium-to-spot), otherwise price_per_coin
        item_price = item.get('effective_price') or item.get('price_per_coin') or 0
        sellers[seller_id]['total_price'] += item['quantity'] * item_price
        sellers[seller_id]['price_sum'] += item_price
        sellers[seller_id]['item_count'] += 1

    # Enrich seller data with additional details
    enriched_sellers = []
    for seller_id, seller_data in sellers.items():
        # Calculate avg_price for cart items from this seller
        if seller_data['item_count'] > 0:
            seller_data['avg_price'] = seller_data['price_sum'] / seller_data['item_count']
        else:
            seller_data['avg_price'] = 0
        # Remove temporary fields
        del seller_data['price_sum']
        del seller_data['item_count']

        # Get user info (member since, display name)
        user_info = conn.execute('''
            SELECT username, first_name, last_name, created_at
            FROM users WHERE id = ?
        ''', (seller_id,)).fetchone()

        if user_info:
            # Display name: use first_name + last_name if available, else username
            display_name = f"{user_info['first_name'] or ''} {user_info['last_name'] or ''}".strip()
            if not display_name:
                display_name = user_info['username']
            seller_data['display_name'] = display_name

            # Member since (formatted as "Mon YYYY")
            raw_date = user_info['created_at']
            if raw_date:
                try:
                    dt = datetime.fromisoformat(str(raw_date).replace('Z', ''))
                    seller_data['member_since'] = dt.strftime('%b %Y')
                except (ValueError, TypeError):
                    seller_data['member_since'] = str(raw_date)[:4]
            else:
                seller_data['member_since'] = None

        # Check verified seller status (rating >= 4.7 and num_reviews > 100)
        rating = seller_data.get('rating') or 0
        num_reviews = seller_data.get('num_reviews') or 0
        seller_data['is_verified'] = rating >= 4.7 and num_reviews > 100

        # Get transaction count: only orders confirmed as delivered
        transaction_result = conn.execute('''
            SELECT COUNT(DISTINCT o.id) as transaction_count
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            JOIN listings l ON oi.listing_id = l.id
            WHERE l.seller_id = ?
              AND o.status IN ('Delivered', 'Complete')
        ''', (seller_id,)).fetchone()
        seller_data['transaction_count'] = transaction_result['transaction_count'] if transaction_result else 0

        # Calculate repeat buyers percentage
        # First get all unique buyers, then count those with 2+ orders
        buyers_result = conn.execute('''
            SELECT o.buyer_id, COUNT(DISTINCT o.id) as order_count
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            JOIN listings l ON oi.listing_id = l.id
            WHERE l.seller_id = ?
            GROUP BY o.buyer_id
        ''', (seller_id,)).fetchall()

        total_buyers = len(buyers_result)
        repeat_buyers = sum(1 for b in buyers_result if b['order_count'] >= 2)
        if total_buyers > 0:
            seller_data['repeat_buyers_pct'] = round((repeat_buyers / total_buyers) * 100)
        else:
            seller_data['repeat_buyers_pct'] = 0

        # Get ships from location (state from seller's first address)
        address_result = conn.execute('''
            SELECT city, state FROM addresses WHERE user_id = ? LIMIT 1
        ''', (seller_id,)).fetchone()
        if address_result:
            seller_data['ships_from'] = f"{address_result['city']}, {address_result['state']}"
        else:
            seller_data['ships_from'] = None

        # Get top 3 product lines (specializations) from sold items
        specializations_result = conn.execute('''
            SELECT c.product_line, COUNT(*) as sale_count
            FROM order_items oi
            JOIN listings l ON oi.listing_id = l.id
            JOIN categories c ON l.category_id = c.id
            WHERE l.seller_id = ? AND c.product_line IS NOT NULL AND c.product_line != ''
            GROUP BY c.product_line
            ORDER BY sale_count DESC
            LIMIT 3
        ''', (seller_id,)).fetchall()
        seller_data['specializations'] = [s['product_line'] for s in specializations_result]

        # Calculate median response time (time between receiving a message and responding)
        # Get all message pairs where seller received then responded
        response_times = conn.execute('''
            SELECT
                m1.timestamp as received_at,
                MIN(m2.timestamp) as responded_at
            FROM messages m1
            JOIN messages m2 ON m1.order_id = m2.order_id
                AND m2.sender_id = m1.receiver_id
                AND m2.timestamp > m1.timestamp
            WHERE m1.receiver_id = ?
            GROUP BY m1.id
        ''', (seller_id,)).fetchall()

        if response_times:
            deltas = []
            for rt in response_times:
                try:
                    received = datetime.fromisoformat(rt['received_at'].replace('Z', '+00:00'))
                    responded = datetime.fromisoformat(rt['responded_at'].replace('Z', '+00:00'))
                    delta_hours = (responded - received).total_seconds() / 3600
                    deltas.append(delta_hours)
                except:
                    pass

            if deltas:
                deltas.sort()
                median_idx = len(deltas) // 2
                median_hours = deltas[median_idx]
                if median_hours < 1:
                    seller_data['response_time'] = f"< 1 hour"
                elif median_hours < 24:
                    seller_data['response_time'] = f"< {int(median_hours) + 1} hours"
                else:
                    days = int(median_hours / 24)
                    seller_data['response_time'] = f"< {days + 1} days"
            else:
                seller_data['response_time'] = None
        else:
            seller_data['response_time'] = None

        # Avg ship time: days from order creation to tracking number entry
        ship_time_result = conn.execute('''
            SELECT AVG(julianday(sot.created_at) - julianday(o.created_at)) AS avg_days
            FROM seller_order_tracking sot
            JOIN orders o ON sot.order_id = o.id
            WHERE sot.seller_id = ?
              AND sot.tracking_number IS NOT NULL
              AND sot.tracking_number != ''
        ''', (seller_id,)).fetchone()
        avg_days = ship_time_result['avg_days'] if ship_time_result and ship_time_result['avg_days'] is not None else None
        if avg_days is not None:
            d = round(avg_days)
            seller_data['avg_ship_time'] = f"{d} day{'s' if d != 1 else ''}"
        else:
            seller_data['avg_ship_time'] = None

        enriched_sellers.append(seller_data)

    conn.close()
    return jsonify(enriched_sellers)


@cart_bp.route('/api/bucket/<int:bucket_id>/can_refill/<int:current_seller_id>')
def can_refill_from_other_sellers(bucket_id, current_seller_id):
    """
    Check if there are other sellers available for this bucket
    (excluding the current seller and all removed sellers).
    Returns: {"canRefill": true/false, "availableCount": N}
    """
    if 'user_id' not in session:
        return jsonify({'canRefill': False, 'availableCount': 0})

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get removed sellers for this bucket
    bucket_key = str(bucket_id)
    removed_seller_ids = session.get('removed_sellers', {}).get(bucket_key, [])

    # Build query to count available sellers (excluding current and removed)
    excluded_ids = removed_seller_ids + [current_seller_id]
    placeholders = ','.join(['?'] * len(excluded_ids))

    query = f'''
        SELECT COUNT(DISTINCT seller_id) as available_count
        FROM listings
        WHERE category_id = ?
          AND active = 1
          AND quantity > 0
          AND seller_id NOT IN ({placeholders})
    '''

    result = cursor.execute(query, [bucket_id] + excluded_ids).fetchone()
    conn.close()

    available_count = result['available_count'] if result else 0

    return jsonify({
        'canRefill': available_count > 0,
        'availableCount': available_count
    })


@cart_bp.route('/api/bucket/<int:bucket_id>/price_breakdown')
def get_price_breakdown(bucket_id):
    # SECURITY: Require authentication to view price breakdown
    if 'user_id' not in session:
        return jsonify([])  # Return empty array for unauthenticated users

    conn = get_db_connection()
    all_items = get_cart_items(conn)
    conn.close()

    # Get removed listings for this bucket from session
    bucket_key = str(bucket_id)
    removed_listing_ids = session.get('removed_listings', {}).get(bucket_key, [])

    # Filter items to this bucket/category and exclude removed listings
    bucket_items = [
        item for item in all_items
        if item['category_id'] == bucket_id
        and item['listing_id'] not in removed_listing_ids
    ]

    enriched = []
    for item in bucket_items:
        # item is already a dict thanks to get_cart_items
        raw_path = item.get('file_path')

        # Normalize path to image_url (same logic as account_routes.py)
        image_url = None
        if raw_path:
            raw_path = str(raw_path)
            if raw_path.startswith('/'):
                image_url = raw_path
            elif raw_path.startswith('static/'):
                image_url = '/' + raw_path
            else:
                # stored relative to static, e.g. "uploads/listings/foo.jpg"
                image_url = '/static/' + raw_path

        enriched.append({
            'listing_id'        : item['listing_id'],
            'seller_id'         : item['seller_id'],
            'seller_username'   : item['seller_username'],
            'price_per_coin'    : float(item['price_per_coin']),
            'quantity'          : item['quantity'],

            # photo + core specs
            'photo_filename'    : item.get('photo_filename'),  # Keep for backward compatibility
            'file_path'         : raw_path,                     # New field from listing_photos
            'image_url'         : image_url,                    # Normalized URL
            'metal'             : item.get('metal'),
            'product_line'      : item.get('product_line'),
            'product_type'      : item.get('product_type'),
            'weight'            : item.get('weight'),
            'year'              : item.get('year'),
            'mint'              : item.get('mint'),
            'purity'            : item.get('purity'),
            'finish'            : item.get('finish'),
            'grade'             : item.get('grade'),
            'series_variant'    : item.get('series_variant'),
            'coin_series'       : item.get('coin_series'),

            # grading info
            'graded'            : item.get('graded'),
            'grading_service'   : item.get('grading_service'),

            # isolated/one-of-a-kind listing info
            'is_isolated'       : item.get('is_isolated'),
            'isolated_type'     : item.get('isolated_type'),
            'packaging_type'    : item.get('packaging_type'),
            'packaging_notes'   : item.get('packaging_notes'),
            'edition_number'    : item.get('edition_number'),
            'edition_total'     : item.get('edition_total'),
            'condition_notes'   : item.get('condition_notes'),

            # optional but nice to have
            'seller_rating'     : item.get('seller_rating'),
            'seller_rating_count': item.get('seller_rating_count'),
        })

    return jsonify(enriched)


@cart_bp.route('/api/bucket/<int:bucket_id>/can_refill_listing/<int:current_listing_id>')
def can_refill_from_other_listings(bucket_id, current_listing_id):
    """
    Check if there are other listings available for this bucket
    (excluding the current listing and all removed listings).
    Returns: {"canRefill": true/false, "availableCount": N}
    """
    if 'user_id' not in session:
        return jsonify({'canRefill': False, 'availableCount': 0})

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get removed listings for this bucket
    bucket_key = str(bucket_id)
    removed_listing_ids = session.get('removed_listings', {}).get(bucket_key, [])

    # Build query to count available listings (excluding current and removed)
    excluded_ids = removed_listing_ids + [current_listing_id]
    placeholders = ','.join(['?'] * len(excluded_ids))

    query = f'''
        SELECT COUNT(DISTINCT id) as available_count
        FROM listings
        WHERE category_id = ?
          AND active = 1
          AND quantity > 0
          AND id NOT IN ({placeholders})
    '''

    result = cursor.execute(query, [bucket_id] + excluded_ids).fetchone()
    conn.close()

    available_count = result['available_count'] if result else 0

    return jsonify({
        'canRefill': available_count > 0,
        'availableCount': available_count
    })
