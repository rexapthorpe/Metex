"""
Sellers API for Buy Blueprint

This module contains the API endpoint for fetching sellers for a bucket.
"""

from flask import jsonify
from datetime import datetime
from database import get_db_connection
from . import buy_bp


@buy_bp.route('/api/bucket/<int:bucket_id>/sellers')
def get_bucket_sellers(bucket_id):
    """
    API endpoint to get all sellers for a bucket with enriched data.
    Used by the seller modal on the bucket page.
    """
    conn = get_db_connection()

    # Get all active sellers for this bucket
    # Join through categories to filter by bucket_id (not category_id)
    # This is important for isolated listings where bucket_id != category_id
    sellers_query = conn.execute('''
        SELECT
            u.id as seller_id,
            u.username,
            MIN(l.price_per_coin) as lowest_price,
            AVG(l.price_per_coin) as avg_price,
            SUM(l.quantity) as total_qty,
            COALESCE(AVG(r.rating), 0) as rating,
            COUNT(DISTINCT r.id) as num_reviews
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        JOIN users u ON l.seller_id = u.id
        LEFT JOIN ratings r ON u.id = r.ratee_id
        WHERE c.bucket_id = ? AND l.active = 1 AND l.quantity > 0
        GROUP BY u.id, u.username
        ORDER BY MIN(l.price_per_coin) ASC
    ''', (bucket_id,)).fetchall()

    enriched_sellers = []
    for row in sellers_query:
        seller_id = row['seller_id']
        seller_data = {
            'seller_id': seller_id,
            'username': row['username'],
            'rating': row['rating'] or 0,
            'num_reviews': row['num_reviews'] or 0,
            'lowest_price': row['lowest_price'],
            'avg_price': row['avg_price'],
            'total_qty': row['total_qty']
        }

        # Get user info (member since, display name)
        user_info = conn.execute('''
            SELECT username, first_name, last_name, created_at
            FROM users WHERE id = ?
        ''', (seller_id,)).fetchone()

        if user_info:
            display_name = f"{user_info['first_name'] or ''} {user_info['last_name'] or ''}".strip()
            if not display_name:
                display_name = user_info['username']
            seller_data['display_name'] = display_name

            if user_info['created_at']:
                seller_data['member_since'] = user_info['created_at'][:4]
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

        # Get ships from location
        address_result = conn.execute('''
            SELECT city, state FROM addresses WHERE user_id = ? LIMIT 1
        ''', (seller_id,)).fetchone()
        if address_result:
            seller_data['ships_from'] = f"{address_result['city']}, {address_result['state']}"
        else:
            seller_data['ships_from'] = None

        # Get top 3 product lines (specializations)
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

        # Calculate median response time
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
                    seller_data['response_time'] = "< 1 hour"
                elif median_hours < 24:
                    seller_data['response_time'] = f"< {int(median_hours) + 1} hours"
                else:
                    days = int(median_hours / 24)
                    seller_data['response_time'] = f"< {days + 1} days"
            else:
                seller_data['response_time'] = None
        else:
            seller_data['response_time'] = None

        seller_data['avg_ship_time'] = None  # Not implemented yet

        enriched_sellers.append(seller_data)

    conn.close()
    return jsonify(enriched_sellers)
