# core/blueprints/bids/api.py

from flask import jsonify, session
from database import get_db_connection
from services.pricing_service import get_effective_bid_price
from datetime import datetime
from . import bid_bp


@bid_bp.route('/api/bid/<int:bid_id>/bidder_info')
def get_bidder_info(bid_id):
    """
    API endpoint to fetch bidder information for a specific bid
    Used by the View Bidder modal on the Bucket ID page
    Returns enriched bidder data matching the seller modal format

    SECURITY: Only sellers with listings in the same bucket as the bid can view
    bidder information (since they might accept the bid).
    """
    # SECURITY: Require authentication
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    conn = get_db_connection()

    try:
        # Get bid and bidder information
        bidder = conn.execute("""
            SELECT
                b.id as bid_id,
                b.buyer_id,
                b.quantity_requested,
                b.remaining_quantity,
                b.price_per_coin,
                b.pricing_mode,
                b.spot_premium,
                b.ceiling_price,
                b.pricing_metal,
                u.username,
                COALESCE(AVG(r.rating), 0) as rating,
                COUNT(r.id) as num_reviews
            FROM bids b
            JOIN users u ON b.buyer_id = u.id
            LEFT JOIN ratings r ON u.id = r.ratee_id
            WHERE b.id = ?
            GROUP BY b.id, b.buyer_id, b.quantity_requested, b.remaining_quantity,
                     b.price_per_coin, b.pricing_mode, b.spot_premium, b.ceiling_price,
                     b.pricing_metal, u.username
        """, (bid_id,)).fetchone()

        if not bidder:
            return jsonify({'error': 'Bid not found'}), 404

        buyer_id = bidder['buyer_id']

        # Calculate quantity for this bid
        requested = bidder['quantity_requested'] or 0
        remaining = bidder['remaining_quantity'] if bidder['remaining_quantity'] is not None else requested

        effective_price = get_effective_bid_price(dict(bidder))

        result = {
            'buyer_id': buyer_id,
            'username': bidder['username'],
            'rating': round(bidder['rating'], 1),
            'num_reviews': bidder['num_reviews'],
            'quantity': remaining,
            'bid_price': round(effective_price, 2),
            'pricing_mode': bidder['pricing_mode'],
        }

        # Get user info (member since, display name)
        user_info = conn.execute('''
            SELECT username, first_name, last_name, created_at
            FROM users WHERE id = ?
        ''', (buyer_id,)).fetchone()

        if user_info:
            # Display name: use first_name + last_name if available, else username
            display_name = f"{user_info['first_name'] or ''} {user_info['last_name'] or ''}".strip()
            if not display_name:
                display_name = user_info['username']
            result['display_name'] = display_name

            # Member since (formatted as "Mon YYYY")
            raw_date = user_info['created_at']
            if raw_date:
                try:
                    dt = datetime.fromisoformat(str(raw_date).replace('Z', ''))
                    result['member_since'] = dt.strftime('%b %Y')
                except (ValueError, TypeError):
                    result['member_since'] = str(raw_date)[:4]
            else:
                result['member_since'] = None

        # Check verified buyer status (rating >= 4.7 and num_reviews > 100)
        rating = result.get('rating') or 0
        num_reviews = result.get('num_reviews') or 0
        result['is_verified'] = rating >= 4.7 and num_reviews > 100

        # Get transaction count (orders where this user is the buyer)
        transaction_result = conn.execute('''
            SELECT COUNT(DISTINCT id) as transaction_count
            FROM orders WHERE buyer_id = ?
        ''', (buyer_id,)).fetchone()
        result['transaction_count'] = transaction_result['transaction_count'] if transaction_result else 0

        # Calculate repeat sellers percentage (sellers they've bought from 2+ times)
        sellers_result = conn.execute('''
            SELECT l.seller_id, COUNT(DISTINCT o.id) as order_count
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            JOIN listings l ON oi.listing_id = l.id
            WHERE o.buyer_id = ?
            GROUP BY l.seller_id
        ''', (buyer_id,)).fetchall()

        total_sellers = len(sellers_result)
        repeat_sellers = sum(1 for s in sellers_result if s['order_count'] >= 2)
        if total_sellers > 0:
            result['repeat_sellers_pct'] = round((repeat_sellers / total_sellers) * 100)
        else:
            result['repeat_sellers_pct'] = 0

        # Get ships to location (state from buyer's first address)
        address_result = conn.execute('''
            SELECT city, state FROM addresses WHERE user_id = ? LIMIT 1
        ''', (buyer_id,)).fetchone()
        if address_result:
            result['ships_to'] = f"{address_result['city']}, {address_result['state']}"
        else:
            result['ships_to'] = None

        # Get top 3 product lines (purchase interests) from bought items
        interests_result = conn.execute('''
            SELECT c.product_line, COUNT(*) as purchase_count
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            JOIN listings l ON oi.listing_id = l.id
            JOIN categories c ON l.category_id = c.id
            WHERE o.buyer_id = ? AND c.product_line IS NOT NULL AND c.product_line != ''
            GROUP BY c.product_line
            ORDER BY purchase_count DESC
            LIMIT 3
        ''', (buyer_id,)).fetchall()
        result['purchase_interests'] = [i['product_line'] for i in interests_result]

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
        ''', (buyer_id,)).fetchall()

        if response_times:
            from datetime import datetime
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
                    result['response_time'] = "< 1 hour"
                elif median_hours < 24:
                    result['response_time'] = f"< {int(median_hours) + 1} hours"
                else:
                    days = int(median_hours / 24)
                    result['response_time'] = f"< {days + 1} days"
            else:
                result['response_time'] = None
        else:
            result['response_time'] = None

        return jsonify(result)

    except Exception as e:
        print(f"Error fetching bidder info: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()
