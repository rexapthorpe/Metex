"""
API Routes

General API routes: cart data, spot prices, price locks, search, listing details.
"""

from flask import request, jsonify, session
from database import get_db_connection
from utils.cart_utils import get_cart_items
from services.spot_price_service import get_current_spot_prices, get_spot_price_age, refresh_spot_prices
from services.pricing_service import create_price_lock, get_active_price_lock, get_effective_price

from . import api_bp


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
    Returns: {
        success: bool,
        prices: {metal: price_per_oz},
        has_api_key: bool,
        is_stale: bool,
        age_minutes: float,
        source: str
    }
    """
    try:
        spot_data = get_current_spot_prices()

        # Handle both old format (plain dict of prices) and new format (enriched dict)
        if isinstance(spot_data, dict) and 'prices' in spot_data:
            # New enriched format
            prices = spot_data['prices']
            has_api_key = spot_data.get('has_api_key', True)
            is_stale = spot_data.get('is_stale', False)
            age_minutes = spot_data.get('age_minutes')
            source = spot_data.get('source', 'unknown')
        else:
            # Old format: simple dict of {metal: price}
            prices = spot_data
            has_api_key = True
            is_stale = False
            age_minutes = None
            source = 'cache'

        return jsonify({
            'success': True,
            'prices': prices,
            'has_api_key': has_api_key,
            'is_stale': is_stale,
            'age_minutes': age_minutes,
            'source': source
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error fetching spot prices: {str(e)}',
            'prices': {},
            'has_api_key': False,
            'is_stale': True,
            'age_minutes': None,
            'source': 'error'
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
            spot_data = get_current_spot_prices()
            return jsonify({
                'success': True,
                'prices': spot_data['prices'],
                'has_api_key': spot_data['has_api_key'],
                'is_stale': spot_data['is_stale'],
                'age_minutes': spot_data['age_minutes'],
                'source': spot_data['source'],
                'message': 'Spot prices refreshed successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to refresh spot prices from API (API key may not be configured)',
                'has_api_key': False,
                'is_stale': True
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


@api_bp.route('/api/search/autocomplete')
def api_search_autocomplete():
    """
    Autocomplete search suggestions for header search bar
    Returns product lines, listing titles, and common item names
    """
    query = request.args.get('q', '').strip()

    if not query or len(query) < 2:
        return jsonify({
            'success': True,
            'suggestions': []
        })

    conn = get_db_connection()

    try:
        # Search in multiple sources
        suggestions = []
        seen_texts = set()  # Avoid duplicates

        # 1. Search product lines (e.g., "Silver Eagle", "Gold Buffalo")
        product_lines = conn.execute("""
            SELECT DISTINCT product_line, bucket_id
            FROM categories
            WHERE product_line LIKE ?
            AND product_line IS NOT NULL
            AND product_line != ''
            ORDER BY product_line
            LIMIT 5
        """, (f'%{query}%',)).fetchall()

        for row in product_lines:
            text = row['product_line']
            if text and text.lower() not in seen_texts:
                seen_texts.add(text.lower())
                suggestions.append({
                    'text': text,
                    'type': 'bucket',
                    'id': row['bucket_id']
                })

        # 2. Search listing names (for isolated/set listings)
        listing_names = conn.execute("""
            SELECT DISTINCT l.id, l.name
            FROM listings l
            WHERE l.name LIKE ?
            AND l.name IS NOT NULL
            AND l.name != ''
            AND l.active = 1
            ORDER BY l.id DESC
            LIMIT 5
        """, (f'%{query}%',)).fetchall()

        for row in listing_names:
            text = row['name']
            if text and text.lower() not in seen_texts:
                seen_texts.add(text.lower())
                suggestions.append({
                    'text': text,
                    'type': 'listing',
                    'id': row['id']
                })

        # 3. Search common combinations (metal + product_type)
        metal_products = conn.execute("""
            SELECT DISTINCT c.metal, c.product_type, c.bucket_id
            FROM categories c
            WHERE (c.metal LIKE ? OR c.product_type LIKE ?)
            AND c.metal IS NOT NULL
            AND c.product_type IS NOT NULL
            ORDER BY c.metal, c.product_type
            LIMIT 5
        """, (f'%{query}%', f'%{query}%')).fetchall()

        for row in metal_products:
            # Create combined text like "Silver Bar" or "Gold Coin"
            text = f"{row['metal']} {row['product_type']}"
            if text.lower() not in seen_texts:
                seen_texts.add(text.lower())
                suggestions.append({
                    'text': text,
                    'type': 'bucket',
                    'id': row['bucket_id']
                })

        conn.close()

        # Limit total suggestions to 6-8
        suggestions = suggestions[:8]

        return jsonify({
            'success': True,
            'suggestions': suggestions
        })

    except Exception as e:
        conn.close()
        return jsonify({
            'success': False,
            'message': f'Search error: {str(e)}',
            'suggestions': []
        }), 500


@api_bp.route('/api/fee-preview')
def fee_preview():
    """Preview fee calculation for sell listing confirmation modal."""
    try:
        gross_price = float(request.args.get('gross_price', 0))
        quantity = int(request.args.get('quantity', 1))

        total_gross = gross_price * quantity
        fee_rate = 0.05  # 5% marketplace fee
        fee_amount = round(total_gross * fee_rate, 2)
        net_amount = round(total_gross - fee_amount, 2)

        return jsonify({
            'success': True,
            'gross_price': gross_price,
            'quantity': quantity,
            'total_gross': round(total_gross, 2),
            'fee_rate': fee_rate,
            'fee_amount': fee_amount,
            'net_amount': net_amount
        })
    except (ValueError, TypeError) as e:
        return jsonify({
            'success': False,
            'message': f'Invalid input: {str(e)}'
        }), 400


@api_bp.route('/api/listings/<int:listing_id>/details')
def get_listing_details(listing_id):
    """Get detailed information about a specific listing for the items modal."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        # Fetch listing details with category info
        listing = conn.execute('''
            SELECT
                l.id AS listing_id,
                l.quantity,
                l.price_per_coin,
                l.pricing_mode,
                l.spot_premium,
                l.floor_price,
                l.pricing_metal,
                l.graded,
                l.grading_service,
                l.is_isolated,
                l.isolated_type,
                l.packaging_type,
                l.packaging_notes,
                l.edition_number,
                l.edition_total,
                l.condition_notes,
                lp.file_path AS photo_path,
                c.metal,
                c.product_line,
                c.product_type,
                c.weight,
                c.mint,
                c.year,
                c.finish,
                c.grade,
                c.purity,
                c.series_variant,
                c.coin_series,
                c.is_isolated AS category_is_isolated
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            LEFT JOIN listing_photos lp ON lp.listing_id = l.id
            WHERE l.id = ?
        ''', (listing_id,)).fetchone()

        if not listing:
            conn.close()
            return jsonify({'error': 'Listing not found or unauthorized'}), 404

        # Calculate effective price using pricing service (handles weight multiplication correctly)
        effective_price = get_effective_price(dict(listing))

        result = {
            'listing_id': listing['listing_id'],
            'quantity': listing['quantity'],
            'price_per_coin': listing['price_per_coin'],
            'effective_price': effective_price,
            'pricing_mode': listing['pricing_mode'],
            'spot_premium': listing['spot_premium'],
            'floor_price': listing['floor_price'],
            'graded': listing['graded'],
            'grading_service': listing['grading_service'],
            'is_isolated': listing['is_isolated'] or listing['category_is_isolated'],
            'isolated_type': listing['isolated_type'],
            'packaging_type': listing['packaging_type'],
            'packaging_notes': listing['packaging_notes'],
            'edition_number': listing['edition_number'],
            'edition_total': listing['edition_total'],
            'condition_notes': listing['condition_notes'],
            'photo_path': listing['photo_path'],
            'metal': listing['metal'],
            'product_line': listing['product_line'],
            'product_type': listing['product_type'],
            'weight': listing['weight'],
            'mint': listing['mint'],
            'year': listing['year'],
            'finish': listing['finish'],
            'grade': listing['grade'],
            'purity': listing['purity'],
            'series_variant': listing['series_variant'],
            'coin_series': listing['coin_series']
        }

        # If this is a set listing, fetch the set items with their photos
        if listing['isolated_type'] == 'set':
            set_items = conn.execute('''
                SELECT
                    lsi.id,
                    lsi.position_index,
                    lsi.metal,
                    lsi.product_line,
                    lsi.product_type,
                    lsi.weight,
                    lsi.purity,
                    lsi.mint,
                    lsi.year,
                    lsi.finish,
                    lsi.grade,
                    lsi.coin_series,
                    lsi.special_designation,
                    lsi.graded,
                    lsi.grading_service,
                    lsi.edition_number,
                    lsi.edition_total,
                    lsi.quantity,
                    lsi.packaging_type,
                    lsi.packaging_notes,
                    lsi.item_title,
                    lsi.condition_notes,
                    lsip.file_path AS photo_path
                FROM listing_set_items lsi
                LEFT JOIN listing_set_item_photos lsip
                    ON lsip.set_item_id = lsi.id AND lsip.position_index = 1
                WHERE lsi.listing_id = ?
                ORDER BY lsi.position_index ASC
            ''', (listing_id,)).fetchall()

            result['set_items'] = [dict(item) for item in set_items]

        conn.close()
        return jsonify(result)

    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500
