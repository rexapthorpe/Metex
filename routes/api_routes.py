# routes/api_routes.py

from flask import Blueprint, request, jsonify, session
from database import get_db_connection
from utils.cart_utils import get_cart_items
from services.spot_price_service import get_current_spot_prices, get_spot_price_age, refresh_spot_prices
from services.pricing_service import create_price_lock, get_active_price_lock

# Create the blueprint FIRST
api_bp = Blueprint('api', __name__)

@api_bp.route('/api/product_lines')
def api_product_lines():
    metal = request.args.get('metal')
    product_type = request.args.get('product_type')

    conn = get_db_connection()

    # Build SQL dynamically so we can omit filters when they are blank
    sql = '''
        SELECT DISTINCT product_line
        FROM categories
        WHERE product_line IS NOT NULL
    '''
    params = []

    if metal:
        sql += ' AND metal = ?'
        params.append(metal)

    if product_type:
        sql += ' AND product_type = ?'
        params.append(product_type)

    sql += ' ORDER BY product_line'

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    # Convert to list and filter out generic junk values
    product_lines = [
        row['product_line']
        for row in rows
        if row['product_line'] not in ('Coin', 'Bar', 'Round')
    ]

    return jsonify(product_lines)


@api_bp.route('/api/cart-data')
def api_cart_data():
    """
    Return cart data as JSON for checkout modal
    """
    if 'user_id' not in session:
        return jsonify({
            'success': False,
            'message': 'Please log in to view your cart'
        }), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        # Get cart items
        raw_items = get_cart_items(conn)
        listings_info = [dict(row) for row in raw_items]

        # Group into buckets
        buckets = {}
        cart_total = 0

        for item in listings_info:
            bucket_key = f"{item['metal']}-{item['product_type']}-{item['weight']}-{item['mint']}-{item['year']}-{item['finish']}-{item['grade']}"

            if bucket_key not in buckets:
                buckets[bucket_key] = {
                    'category': {
                        'metal': item['metal'],
                        'product_type': item['product_type'],
                        'weight': item['weight'],
                        'purity': item.get('purity', ''),
                        'mint': item['mint'],
                        'year': item['year'],
                        'finish': item['finish'],
                        'grade': item['grade'],
                        'product_line': item.get('product_line', ''),
                        'graded': item.get('graded', 0),
                        'grading_service': item.get('grading_service', '')
                    },
                    'quantity': 0,
                    'total_qty': 0,
                    'total_price': 0,
                    'avg_price': 0
                }

            subtotal = item['price_per_coin'] * item['quantity']
            buckets[bucket_key]['quantity'] += item['quantity']
            buckets[bucket_key]['total_qty'] += item['quantity']
            buckets[bucket_key]['total_price'] += subtotal
            cart_total += subtotal

        # Calculate average prices
        for bucket in buckets.values():
            if bucket['quantity'] > 0:
                bucket['avg_price'] = round(bucket['total_price'] / bucket['quantity'], 2)

        conn.close()

        return jsonify({
            'success': True,
            'buckets': buckets,
            'cart_total': round(cart_total, 2)
        })

    except Exception as e:
        conn.close()
        return jsonify({
            'success': False,
            'message': f'Error loading cart: {str(e)}'
        }), 500


@api_bp.route('/api/spot-prices')
def api_spot_prices():
    """
    Get current spot prices for all metals
    Returns: {metal: price_per_oz, ...}
    """
    try:
        spot_prices = get_current_spot_prices()
        age_minutes = get_spot_price_age()

        return jsonify({
            'success': True,
            'prices': spot_prices,
            'age_minutes': age_minutes,
            'timestamp': None  # Could add timestamp if needed
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error fetching spot prices: {str(e)}'
        }), 500


@api_bp.route('/api/spot-prices/refresh', methods=['POST'])
def api_refresh_spot_prices():
    """
    Manually refresh spot prices from API
    Requires admin permissions (optional - implement if needed)
    """
    try:
        success = refresh_spot_prices()

        if success:
            spot_prices = get_current_spot_prices()
            return jsonify({
                'success': True,
                'prices': spot_prices,
                'message': 'Spot prices refreshed successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to refresh spot prices from API'
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error refreshing spot prices: {str(e)}'
        }), 500


@api_bp.route('/api/price-lock/create', methods=['POST'])
def api_create_price_lock():
    """
    Create a price lock for a listing during checkout
    Request body: {listing_id: int, duration_seconds: int (optional)}
    """
    if 'user_id' not in session:
        return jsonify({
            'success': False,
            'message': 'Please log in to create a price lock'
        }), 401

    user_id = session['user_id']

    try:
        data = request.get_json()
        listing_id = data.get('listing_id')
        duration_seconds = data.get('duration_seconds', 10)

        if not listing_id:
            return jsonify({
                'success': False,
                'message': 'Listing ID is required'
            }), 400

        # Create price lock
        price_lock = create_price_lock(listing_id, user_id, duration_seconds)

        if price_lock:
            return jsonify({
                'success': True,
                'price_lock': price_lock
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to create price lock'
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error creating price lock: {str(e)}'
        }), 500


@api_bp.route('/api/price-lock/get/<int:listing_id>')
def api_get_price_lock(listing_id):
    """
    Get active price lock for a listing
    """
    if 'user_id' not in session:
        return jsonify({
            'success': False,
            'message': 'Please log in'
        }), 401

    user_id = session['user_id']

    try:
        price_lock = get_active_price_lock(listing_id, user_id)

        if price_lock:
            return jsonify({
                'success': True,
                'price_lock': price_lock,
                'has_lock': True
            })
        else:
            return jsonify({
                'success': True,
                'price_lock': None,
                'has_lock': False
            })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error getting price lock: {str(e)}'
        }), 500
