# cart_routes.py

from flask import Blueprint, request, redirect, url_for, session, flash, jsonify, render_template
from database import get_db_connection
from utils.cart_utils import get_cart_items

cart_bp = Blueprint('cart', __name__, url_prefix='/cart')


@cart_bp.route('/remove_seller/<int:bucket_id>/<int:seller_id>', methods=['POST'])
def remove_seller_from_cart(bucket_id, seller_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    # Track this seller as removed in session
    if 'removed_sellers' not in session:
        session['removed_sellers'] = {}
    bucket_key = str(bucket_id)
    if bucket_key not in session['removed_sellers']:
        session['removed_sellers'][bucket_key] = []
    if seller_id not in session['removed_sellers'][bucket_key]:
        session['removed_sellers'][bucket_key].append(seller_id)
    session.modified = True

    # 1) Find how many items we're about to lose
    result = cursor.execute('''
        SELECT SUM(cart.quantity) AS lost_qty
          FROM cart
          JOIN listings ON cart.listing_id = listings.id
         WHERE cart.user_id = ?
           AND listings.category_id = ?
           AND listings.seller_id = ?
    ''', (user_id, bucket_id, seller_id)).fetchone()
    lost_qty = result['lost_qty'] or 0

    # 2) Remove them
    cursor.execute('''
        DELETE FROM cart
         WHERE user_id = ?
           AND listing_id IN (
             SELECT id FROM listings
              WHERE category_id = ?
                AND seller_id = ?
           )
    ''', (user_id, bucket_id, seller_id))
    conn.commit()

    # 3) Refill from cheapest remaining sellers (excluding ALL removed sellers)
    remaining = lost_qty
    removed_seller_ids = session.get('removed_sellers', {}).get(bucket_key, [])

    # Build query to exclude all removed sellers
    if removed_seller_ids:
        placeholders = ','.join(['?'] * len(removed_seller_ids))
        query = f'''
            SELECT id, quantity
              FROM listings
             WHERE category_id = ?
               AND active = 1
               AND seller_id NOT IN ({placeholders})
             ORDER BY price_per_coin ASC
        '''
        params = [bucket_id] + removed_seller_ids
    else:
        query = '''
            SELECT id, quantity
              FROM listings
             WHERE category_id = ?
               AND active = 1
             ORDER BY price_per_coin ASC
        '''
        params = [bucket_id]

    replacements = cursor.execute(query, params).fetchall()

    for listing in replacements:
        if remaining <= 0:
            break

        # Check if already in cart
        existing = cursor.execute(
            'SELECT quantity FROM cart WHERE user_id = ? AND listing_id = ?',
            (user_id, listing['id'])
        ).fetchone()

        # How much we can take from this listing
        in_cart = existing['quantity'] if existing else 0
        available_to_add = listing['quantity'] - in_cart
        take = min(remaining, available_to_add)

        if take > 0:
            if existing:
                cursor.execute(
                    'UPDATE cart SET quantity = ? WHERE user_id = ? AND listing_id = ?',
                    (in_cart + take, user_id, listing['id'])
                )
            else:
                cursor.execute(
                    'INSERT INTO cart (user_id, listing_id, quantity) VALUES (?, ?, ?)',
                    (user_id, listing['id'], take)
                )
            remaining -= take

    conn.commit()

    # 4) Check if this bucket now has zero items in cart - if so, clear from removed_sellers
    cart_count = cursor.execute('''
        SELECT COUNT(*) as cnt
        FROM cart
        JOIN listings ON cart.listing_id = listings.id
        WHERE cart.user_id = ? AND listings.category_id = ?
    ''', (user_id, bucket_id)).fetchone()

    if cart_count['cnt'] == 0:
        # Bucket is now empty, clear the removed sellers list for this bucket
        if bucket_key in session.get('removed_sellers', {}):
            del session['removed_sellers'][bucket_key]
            session.modified = True

    conn.close()

    # 5) Check if AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return '', 204

    # 6) Flash a message for non-AJAX requests
    if lost_qty == 0:
        flash("Nothing to remove from that seller.", "warning")
    elif remaining > 0:
        flash(f"Removed seller. Only {lost_qty - remaining}/{lost_qty} items could be refilled.", "warning")
    else:
        flash("Seller removed and cart refilled with other listings.", "success")

    return redirect(url_for('cart.view_cart'))


@cart_bp.route('/remove_item_confirmation_modal/<int:bucket_id>')
def remove_item_confirmation_modal(bucket_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    return render_template(
        'modals/cart_remove_item_confirmation_modal.html',
        bucket_id=bucket_id
    )


@cart_bp.route('/api/bucket/<int:bucket_id>/cart_sellers')
def get_cart_sellers(bucket_id):
    conn = get_db_connection()
    cart_items = get_cart_items(conn)
    conn.close()

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
                'num_reviews': item['seller_rating_count']
            }
        sellers[seller_id]['quantity'] += item['quantity']

    return jsonify(list(sellers.values()))


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

            # ✅ photo + core specs
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

            # ✅ grading info
            'graded'            : item.get('graded'),
            'grading_service'   : item.get('grading_service'),

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


@cart_bp.route('/remove_item/<int:listing_id>', methods=['POST'])
def remove_item(listing_id):
    """
    Remove exactly one listing from the cart (DB or guest),
    then try to refill the lost quantity with other listings from the same bucket,
    prioritizing lowest priced listings.
    Supports both XHR (204) and normal form (flash + redirect).
    """
    user_id = session.get('user_id')

    # Guest cart
    if not user_id:
        guest_cart = session.get('guest_cart', [])
        updated = [item for item in guest_cart if item['listing_id'] != listing_id]
        session['guest_cart'] = updated
        session.modified = True

        flash("🗑️ Item removed from your cart.", "success")
        return redirect(url_for('buy.view_cart'))

    # Authenticated cart with refill logic
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1) Get info about the listing being removed
    cart_item = cursor.execute('''
        SELECT cart.quantity, listings.category_id, listings.seller_id
        FROM cart
        JOIN listings ON cart.listing_id = listings.id
        WHERE cart.user_id = ? AND cart.listing_id = ?
    ''', (user_id, listing_id)).fetchone()

    if not cart_item:
        conn.close()
        flash("Item not found in cart.", "warning")
        return redirect(url_for('buy.view_cart'))

    lost_qty = cart_item['quantity']
    bucket_id = cart_item['category_id']
    removed_seller_id = cart_item['seller_id']

    # Track this listing as removed in session
    if 'removed_listings' not in session:
        session['removed_listings'] = {}
    bucket_key = str(bucket_id)
    if bucket_key not in session['removed_listings']:
        session['removed_listings'][bucket_key] = []
    if listing_id not in session['removed_listings'][bucket_key]:
        session['removed_listings'][bucket_key].append(listing_id)
    session.modified = True

    # 2) Remove the listing from cart
    cursor.execute(
        'DELETE FROM cart WHERE user_id = ? AND listing_id = ?',
        (user_id, listing_id)
    )
    conn.commit()

    # 3) Try to refill from other listings in the same bucket (excluding ALL removed listings)
    remaining = lost_qty
    removed_listing_ids = session.get('removed_listings', {}).get(bucket_key, [])

    # Build query to exclude all removed listings
    if removed_listing_ids:
        placeholders = ','.join(['?'] * len(removed_listing_ids))
        query = f'''
            SELECT id, quantity, seller_id
            FROM listings
            WHERE category_id = ?
              AND active = 1
              AND id NOT IN ({placeholders})
            ORDER BY price_per_coin ASC
        '''
        params = [bucket_id] + removed_listing_ids
    else:
        query = '''
            SELECT id, quantity, seller_id
            FROM listings
            WHERE category_id = ?
              AND active = 1
            ORDER BY price_per_coin ASC
        '''
        params = [bucket_id]

    replacements = cursor.execute(query, params).fetchall()

    for listing in replacements:
        if remaining <= 0:
            break

        # Check if already in cart
        existing = cursor.execute(
            'SELECT quantity FROM cart WHERE user_id = ? AND listing_id = ?',
            (user_id, listing['id'])
        ).fetchone()

        # How much we can take from this listing
        in_cart = existing['quantity'] if existing else 0
        available_to_add = listing['quantity'] - in_cart
        take = min(remaining, available_to_add)

        if take > 0:
            if existing:
                cursor.execute(
                    'UPDATE cart SET quantity = ? WHERE user_id = ? AND listing_id = ?',
                    (in_cart + take, user_id, listing['id'])
                )
            else:
                cursor.execute(
                    'INSERT INTO cart (user_id, listing_id, quantity) VALUES (?, ?, ?)',
                    (user_id, listing['id'], take)
                )
            remaining -= take

    conn.commit()

    # 4) Check if this bucket now has zero items in cart - if so, clear from removed_listings
    cart_count = cursor.execute('''
        SELECT COUNT(*) as cnt
        FROM cart
        JOIN listings ON cart.listing_id = listings.id
        WHERE cart.user_id = ? AND listings.category_id = ?
    ''', (user_id, bucket_id)).fetchone()

    if cart_count['cnt'] == 0:
        # Bucket is now empty, clear the removed listings list for this bucket
        if bucket_key in session.get('removed_listings', {}):
            del session['removed_listings'][bucket_key]
            session.modified = True

    conn.close()

    # If AJAX call, just return 204
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return '', 204

    # Flash message with refill info
    if remaining > 0:
        flash(f"Item removed. Only {lost_qty - remaining}/{lost_qty} items could be refilled from other listings.", "warning")
    else:
        flash("Item removed and cart refilled with other listings.", "success")

    return redirect(url_for('buy.view_cart'))


@cart_bp.route('/remove_bucket/<int:bucket_id>', methods=['POST'])
def remove_bucket(bucket_id):
    """
    Delete every cart entry in this bucket (category),
    supports both DB and guest session.
    Always returns 204.
    """
    user_id = session.get('user_id')

    if not user_id:
        guest = session.get('guest_cart', [])
        filtered = [i for i in guest if i.get('category_id') != bucket_id]
        session['guest_cart'] = filtered
        session.modified = True
        # Clear removed sellers and listings for this bucket
        bucket_key = str(bucket_id)
        if bucket_key in session.get('removed_sellers', {}):
            del session['removed_sellers'][bucket_key]
            session.modified = True
        if bucket_key in session.get('removed_listings', {}):
            del session['removed_listings'][bucket_key]
            session.modified = True
        return '', 204

    conn = get_db_connection()
    conn.execute('''
        DELETE FROM cart
         WHERE user_id = ?
           AND listing_id IN (
             SELECT id FROM listings WHERE category_id = ?
           )
    ''', (user_id, bucket_id))
    conn.commit()
    conn.close()

    # Clear removed sellers and listings for this bucket
    bucket_key = str(bucket_id)
    if bucket_key in session.get('removed_sellers', {}):
        del session['removed_sellers'][bucket_key]
        session.modified = True
    if bucket_key in session.get('removed_listings', {}):
        del session['removed_listings'][bucket_key]
        session.modified = True

    return '', 204


@cart_bp.route('/update_bucket_quantity/<int:category_id>', methods=['POST'])
def update_bucket_quantity(category_id):
    """
    Update the total quantity for a category/bucket in the cart.
    Adds or removes listings to reach the target quantity,
    prioritizing cheapest listings.
    Validates inventory and refills from other sellers if needed.

    Note: Despite the name, this route uses category_id as the identifier
    for backwards compatibility with existing templates.
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.get_json()
    target_qty = data.get('quantity', 1)

    if not isinstance(target_qty, int) or target_qty < 1:
        return jsonify({'error': 'Invalid quantity'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # First, validate and refill cart to ensure accurate inventory
    from utils.cart_utils import validate_and_refill_cart
    validate_and_refill_cart(conn, user_id)

    # 1) Get current cart items for this category
    current_items = cursor.execute('''
        SELECT cart.listing_id, cart.quantity, listings.price_per_coin
          FROM cart
          JOIN listings ON cart.listing_id = listings.id
         WHERE cart.user_id = ?
           AND listings.category_id = ?
         ORDER BY listings.price_per_coin ASC
    ''', (user_id, category_id)).fetchall()

    current_qty = sum(item['quantity'] for item in current_items)

    # 2) If target equals current, nothing to do
    if target_qty == current_qty:
        conn.close()
        return jsonify({'success': True, 'quantity': target_qty})

    # 3) If we need to add more items
    if target_qty > current_qty:
        needed = target_qty - current_qty

        # Get all available listings for this category (excluding user's own), sorted by price
        available = cursor.execute('''
            SELECT id, quantity, price_per_coin
              FROM listings
             WHERE category_id = ?
               AND active = 1
               AND seller_id != ?
             ORDER BY price_per_coin ASC
        ''', (category_id, user_id)).fetchall()

        for listing in available:
            if needed <= 0:
                break

            # Check if already in cart
            existing = cursor.execute(
                'SELECT quantity FROM cart WHERE user_id = ? AND listing_id = ?',
                (user_id, listing['id'])
            ).fetchone()

            # How much we can take from this listing
            in_cart = existing['quantity'] if existing else 0
            available_to_add = listing['quantity'] - in_cart
            take = min(needed, available_to_add)

            if take > 0:
                if existing:
                    cursor.execute(
                        'UPDATE cart SET quantity = ? WHERE user_id = ? AND listing_id = ?',
                        (in_cart + take, user_id, listing['id'])
                    )
                else:
                    cursor.execute(
                        'INSERT INTO cart (user_id, listing_id, quantity) VALUES (?, ?, ?)',
                        (user_id, listing['id'], take)
                    )
                needed -= take

    # 4) If we need to remove items
    else:
        to_remove = current_qty - target_qty

        # Remove from most expensive first (reverse order)
        for item in reversed(current_items):
            if to_remove <= 0:
                break

            listing_id = item['listing_id']
            in_cart = item['quantity']
            remove_from_this = min(to_remove, in_cart)

            new_qty = in_cart - remove_from_this
            if new_qty <= 0:
                cursor.execute(
                    'DELETE FROM cart WHERE user_id = ? AND listing_id = ?',
                    (user_id, listing_id)
                )
            else:
                cursor.execute(
                    'UPDATE cart SET quantity = ? WHERE user_id = ? AND listing_id = ?',
                    (new_qty, user_id, listing_id)
                )
            to_remove -= remove_from_this

    conn.commit()

    # Get updated category data for frontend display
    from services.pricing_service import get_effective_price

    updated_items = cursor.execute('''
        SELECT
            cart.quantity,
            listings.price_per_coin,
            listings.pricing_mode,
            listings.floor_price,
            listings.spot_premium,
            listings.pricing_metal,
            categories.metal,
            categories.weight,
            categories.product_type
        FROM cart
        JOIN listings ON cart.listing_id = listings.id
        JOIN categories ON listings.category_id = categories.id
        WHERE cart.user_id = ?
          AND categories.id = ?
    ''', (user_id, category_id)).fetchall()

    # Calculate new total quantity and average price
    new_total_qty = 0
    new_total_price = 0.0

    for item in updated_items:
        item_dict = dict(item)
        effective_price = get_effective_price(item_dict)
        qty = item['quantity']
        new_total_qty += qty
        new_total_price += qty * effective_price

    new_avg_price = new_total_price / new_total_qty if new_total_qty > 0 else 0.0

    conn.close()

    return jsonify({
        'success': True,
        'quantity': new_total_qty,
        'avg_price': round(new_avg_price, 2),
        'total_price': round(new_total_price, 2)
    })