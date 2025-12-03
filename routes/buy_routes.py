# routes/buy_routes.py

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from routes.auto_fill_bid import auto_fill_bid
from datetime import datetime
from database import get_db_connection
from utils.cart_utils import get_cart_items
from services.notification_service import notify_listing_sold
from services.pricing_service import get_effective_price, get_effective_bid_price, get_listings_with_effective_prices
import sqlite3
import os

buy_bp = Blueprint('buy', __name__)


@buy_bp.route('/buy')
def buy():
    conn = get_db_connection()

    # Read grading filters from GET parameters
    graded_only = request.args.get('graded_only') == '1'
    any_grader = request.args.get('any_grader') == '1'
    pcgs = request.args.get('pcgs') == '1'
    ngc = request.args.get('ngc') == '1'

    # First, get all categories (buckets)
    categories_query = '''
        SELECT DISTINCT
            categories.id AS category_id,
            categories.bucket_id,
            categories.metal,
            categories.product_type,
            categories.weight,
            categories.mint,
            categories.year,
            categories.finish,
            categories.grade,
            categories.coin_series,
            categories.product_line
        FROM categories
    '''
    categories = conn.execute(categories_query).fetchall()

    # Then, get all active listings with pricing fields
    listings_query = '''
        SELECT
            l.id, l.category_id, l.quantity, l.price_per_coin,
            l.pricing_mode, l.spot_premium, l.floor_price, l.pricing_metal,
            l.graded, l.grading_service,
            c.metal, c.weight, c.product_type, c.bucket_id
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.active = 1 AND l.quantity > 0
    '''

    where_clauses = []
    params = []

    if graded_only:
        where_clauses.append('l.graded = 1')
        if not any_grader:
            services = []
            if pcgs:
                services.append("'PCGS'")
            if ngc:
                services.append("'NGC'")
            if services:
                where_clauses.append(f"l.grading_service IN ({', '.join(services)})")
            elif not pcgs and not ngc:
                # No grader selected = no results
                conn.close()
                return render_template('buy.html', buckets=[], graded_only=graded_only)

    if where_clauses:
        listings_query += ' AND ' + ' AND '.join(where_clauses)

    listings = conn.execute(listings_query, params).fetchall()
    conn.close()

    # Calculate effective prices for all listings
    listings_with_prices = []
    for listing in listings:
        listing_dict = dict(listing)
        listing_dict['effective_price'] = get_effective_price(listing_dict)
        listings_with_prices.append(listing_dict)

    # Aggregate by bucket_id
    bucket_data = {}
    for listing in listings_with_prices:
        bucket_id = listing['bucket_id']
        if bucket_id not in bucket_data:
            bucket_data[bucket_id] = {
                'lowest_price': listing['effective_price'],
                'total_available': listing['quantity']
            }
        else:
            bucket_data[bucket_id]['lowest_price'] = min(
                bucket_data[bucket_id]['lowest_price'],
                listing['effective_price']
            )
            bucket_data[bucket_id]['total_available'] += listing['quantity']

    # Merge bucket data with categories
    buckets = []
    for category in categories:
        cat_dict = dict(category)
        bucket_id = cat_dict['bucket_id']

        if bucket_id in bucket_data:
            cat_dict['lowest_price'] = bucket_data[bucket_id]['lowest_price']
            cat_dict['total_available'] = bucket_data[bucket_id]['total_available']
        else:
            cat_dict['lowest_price'] = None
            cat_dict['total_available'] = 0

        buckets.append(cat_dict)

    # Sort: items with no listings last, then by lowest_price
    buckets.sort(key=lambda b: (b['lowest_price'] is None, b['lowest_price'] if b['lowest_price'] is not None else 0))

    return render_template('buy.html', buckets=buckets, graded_only=graded_only)

@buy_bp.route('/bucket/<int:bucket_id>')
def view_bucket(bucket_id):
    conn = get_db_connection()

    # Query by bucket_id, not by category id
    bucket = conn.execute('SELECT * FROM categories WHERE bucket_id = ? LIMIT 1', (bucket_id,)).fetchone()
    if not bucket:
        conn.close()
        flash("Item not found.", "error")
        return redirect(url_for('buy.buy'))

    cols = set(bucket.keys()) if hasattr(bucket, 'keys') else set()

    def take(*names):
        for n in names:
            if n in cols:
                v = bucket[n]
                if v is not None and str(v).strip() != "":
                    return v
        return None

    specs = {
        'Metal'        : take('metal'),
        'Product line' : take('product_line', 'coin_series'),
        'Product type' : take('product_type'),
        'Weight'       : take('weight'),
        'Year'         : take('year'),
        'Mint'         : take('mint'),
        'Purity'       : take('purity'),
        'Finish'       : take('finish'),
        'Grading'      : take('grade'),
    }
    specs = {k: (('--' if (v is None or str(v).strip() == '') else v)) for k, v in specs.items()}

    # Add graded and grading_service fields directly from bucket (preserving original values)
    specs['graded'] = bucket.get('graded', 0) if 'graded' in cols else 0
    specs['grading_service'] = bucket.get('grading_service', '') if 'grading_service' in cols else ''

    images = []

    # --- grading filter flags from query (default: nothing selected) ---
    graded_only = request.args.get('graded_only') == '1'
    any_grader  = request.args.get('any_grader') == '1'
    pcgs        = request.args.get('pcgs') == '1'
    ngc         = request.args.get('ngc') == '1'
    grading_filter_applied = graded_only and (any_grader or pcgs or ngc)

    # Listings query (respect filters) - JOIN with categories to query by bucket_id
    # Include pricing fields for effective price calculation
    listings_query = '''
        SELECT l.*, c.metal, c.weight, c.product_type
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ? AND l.active = 1
    '''
    listings_params = [bucket_id]

    # Exclude current user's own listings if logged in
    user_id = session.get('user_id')
    if user_id:
        listings_query += ' AND l.seller_id != ?'
        listings_params.append(user_id)

    if grading_filter_applied:
        listings_query += ' AND l.graded = 1'
        if not any_grader:
            services = []
            if pcgs: services.append("'PCGS'")
            if ngc:  services.append("'NGC'")
            if services:
                listings_query += f" AND l.grading_service IN ({', '.join(services)})"
            else:
                listings = []
    if 'listings' not in locals():
        listings_raw = conn.execute(listings_query, listings_params).fetchall()
        # Calculate effective prices for all listings
        listings = []
        for listing in listings_raw:
            listing_dict = dict(listing)
            listing_dict['effective_price'] = get_effective_price(listing_dict)
            listings.append(listing_dict)

    # Calculate availability from listings with effective prices
    if listings:
        lowest_price = min(l['effective_price'] for l in listings)
        total_available = sum(l['quantity'] for l in listings)
        availability = {'lowest_price': lowest_price, 'total_available': total_available}
    else:
        availability = {'lowest_price': None, 'total_available': 0}

    user_bids = []
    if user_id:
        user_bids_rows = conn.execute('''
            SELECT b.id, b.quantity_requested, b.remaining_quantity, b.price_per_coin,
                   b.status, b.created_at, b.active, b.requires_grading, b.preferred_grader,
                   b.pricing_mode, b.spot_premium, b.floor_price, b.pricing_metal,
                   c.metal, c.weight, c.product_type
            FROM bids b
            JOIN categories c ON b.category_id = c.id
            WHERE b.buyer_id = ? AND c.bucket_id = ? AND b.active = 1
            ORDER BY b.price_per_coin DESC
        ''', (user_id, bucket_id)).fetchall()
        # Calculate effective prices for user bids
        user_bids = []
        for bid in user_bids_rows:
            bid_dict = dict(bid)
            bid_dict['effective_price'] = get_effective_bid_price(bid_dict)
            user_bids.append(bid_dict)

    if user_id:
        bids_rows = conn.execute('''
            SELECT bids.id, bids.buyer_id, bids.category_id, bids.quantity_requested,
                   bids.remaining_quantity, bids.price_per_coin, bids.delivery_address,
                   bids.status, bids.created_at, bids.active, bids.requires_grading,
                   bids.preferred_grader, bids.pricing_mode, bids.spot_premium,
                   bids.floor_price, bids.ceiling_price, bids.pricing_metal,
                   users.username AS buyer_name,
                   c.metal, c.weight, c.product_type
            FROM bids
            JOIN users ON bids.buyer_id = users.id
            JOIN categories c ON bids.category_id = c.id
            WHERE c.bucket_id = ? AND bids.active = 1 AND bids.buyer_id != ?
            ORDER BY bids.price_per_coin DESC
        ''', (bucket_id, user_id)).fetchall()
    else:
        bids_rows = conn.execute('''
            SELECT bids.id, bids.buyer_id, bids.category_id, bids.quantity_requested,
                   bids.remaining_quantity, bids.price_per_coin, bids.delivery_address,
                   bids.status, bids.created_at, bids.active, bids.requires_grading,
                   bids.preferred_grader, bids.pricing_mode, bids.spot_premium,
                   bids.floor_price, bids.ceiling_price, bids.pricing_metal,
                   users.username AS buyer_name,
                   c.metal, c.weight, c.product_type
            FROM bids
            JOIN users ON bids.buyer_id = users.id
            JOIN categories c ON bids.category_id = c.id
            WHERE c.bucket_id = ? AND bids.active = 1
            ORDER BY bids.price_per_coin DESC
        ''', (bucket_id,)).fetchall()

    # Calculate effective prices for all bids
    bids = []
    for bid in bids_rows:
        bid_dict = dict(bid)
        bid_dict['effective_price'] = get_effective_bid_price(bid_dict)
        bids.append(bid_dict)

    # Get best bid - exclude current user's bids if logged in
    if user_id:
        best_bid_row = conn.execute('''
            SELECT bids.id, bids.price_per_coin, bids.quantity_requested,
                   bids.remaining_quantity, bids.delivery_address,
                   bids.pricing_mode, bids.spot_premium, bids.ceiling_price, bids.pricing_metal,
                   users.username AS buyer_name,
                   c.metal, c.weight, c.product_type
            FROM bids
            JOIN users ON bids.buyer_id = users.id
            JOIN categories c ON bids.category_id = c.id
            WHERE c.bucket_id = ? AND bids.active = 1
              AND bids.buyer_id != ?
            ORDER BY bids.price_per_coin DESC
            LIMIT 1
        ''', (bucket_id, user_id)).fetchone()
    else:
        best_bid_row = conn.execute('''
            SELECT bids.id, bids.price_per_coin, bids.quantity_requested,
                   bids.remaining_quantity, bids.delivery_address,
                   bids.pricing_mode, bids.spot_premium, bids.ceiling_price, bids.pricing_metal,
                   users.username AS buyer_name,
                   c.metal, c.weight, c.product_type
            FROM bids
            JOIN users ON bids.buyer_id = users.id
            JOIN categories c ON bids.category_id = c.id
            WHERE c.bucket_id = ? AND bids.active = 1
            ORDER BY bids.price_per_coin DESC
            LIMIT 1
        ''', (bucket_id,)).fetchone()

    if best_bid_row:
        best_bid = dict(best_bid_row)
        best_bid['effective_price'] = get_effective_bid_price(best_bid)
    else:
        best_bid = None

    # Get sellers with effective prices
    sellers_raw = conn.execute('''
        SELECT
          u.id                  AS seller_id,
          u.username            AS username,
          rr.rating             AS rating,
          rr.rating_count       AS rating_count,
          l.id                  AS listing_id,
          l.price_per_coin,
          l.pricing_mode,
          l.spot_premium,
          l.floor_price,
          l.pricing_metal,
          l.quantity,
          c.metal,
          c.weight,
          c.product_type
        FROM listings AS l
        JOIN categories c ON l.category_id = c.id
        JOIN users AS u ON u.id = l.seller_id
        LEFT JOIN (
            SELECT ratee_id, AVG(rating) AS rating, COUNT(*) AS rating_count
            FROM ratings GROUP BY ratee_id
        ) AS rr ON rr.ratee_id = u.id
        WHERE c.bucket_id = ? AND l.active = 1 AND l.quantity > 0
    ''', (bucket_id,)).fetchall()

    # Aggregate sellers with effective prices
    sellers_data = {}
    for row in sellers_raw:
        seller_id = row['seller_id']
        listing_dict = dict(row)
        effective_price = get_effective_price(listing_dict)

        if seller_id not in sellers_data:
            sellers_data[seller_id] = {
                'seller_id': seller_id,
                'username': row['username'],
                'rating': row['rating'],
                'rating_count': row['rating_count'],
                'lowest_price': effective_price,
                'total_qty': row['quantity']
            }
        else:
            sellers_data[seller_id]['lowest_price'] = min(
                sellers_data[seller_id]['lowest_price'],
                effective_price
            )
            sellers_data[seller_id]['total_qty'] += row['quantity']

    # Convert to list and sort
    sellers = list(sellers_data.values())
    sellers.sort(key=lambda s: (s['rating'] is None, -s['rating'] if s['rating'] else 0, s['lowest_price']))

    user_is_logged_in = 'user_id' in session
    conn.close()

    return render_template(
        'view_bucket.html',
        bucket=bucket,
        specs=specs,
        images=images,
        listings=listings,
        availability=availability,
        graded_only=graded_only,
        any_grader=any_grader,   # <<< added
        pcgs=pcgs,               # <<< added
        ngc=ngc,                 # <<< added
        user_bids=user_bids,
        bids=bids,
        best_bid=best_bid,
        sellers=sellers,
        user_is_logged_in=user_is_logged_in
    )


@buy_bp.route('/bucket/<int:bucket_id>/availability_json')
def bucket_availability_json(bucket_id):
    conn = get_db_connection()

    graded_only = request.args.get('graded_only') == '1'
    any_grader  = request.args.get('any_grader') == '1'
    pcgs        = request.args.get('pcgs') == '1'
    ngc         = request.args.get('ngc') == '1'

    # Get listings with pricing fields
    query = '''
        SELECT l.*, c.metal, c.weight, c.product_type
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ? AND l.active = 1
    '''
    params = [bucket_id]

    if graded_only:
        query += ' AND l.graded = 1'
        if not any_grader:
            services = []
            if pcgs: services.append("'PCGS'")
            if ngc:  services.append("'NGC'")
            if services:
                query += f" AND l.grading_service IN ({', '.join(services)})"
            else:
                conn.close()
                return {'lowest_price': None, 'total_available': 0}

    listings = conn.execute(query, params).fetchall()
    conn.close()

    # Calculate effective prices and aggregate
    if listings:
        lowest_price = None
        total_available = 0
        for listing in listings:
            listing_dict = dict(listing)
            effective_price = get_effective_price(listing_dict)
            if lowest_price is None or effective_price < lowest_price:
                lowest_price = effective_price
            total_available += listing_dict['quantity']
    else:
        lowest_price = None
        total_available = 0

    return {'lowest_price': lowest_price, 'total_available': total_available}


@buy_bp.route('/purchase_from_bucket/<int:bucket_id>', methods=['POST'])
def auto_fill_bucket_purchase(bucket_id):
    quantity_to_buy = int(request.form['quantity_to_buy'])
    user_id = session.get('user_id')  # May be None for guests

    conn = get_db_connection()
    cursor = conn.cursor()

    graded_only = request.form.get('graded_only') == '1'
    any_grader = request.form.get('any_grader') == '1'
    pcgs = request.form.get('pcgs') == '1'
    ngc = request.form.get('ngc') == '1'

    # 🆕 Determine grading preference string
    if any_grader:
        grading_preference = 'Any Grader'
    elif pcgs:
        grading_preference = 'PCGS'
    elif ngc:
        grading_preference = 'NGC'
    else:
        grading_preference = None

    session['grading_preference'] = grading_preference  # optional: still store for display

    # Build listings query with grading filters - JOIN with categories to query by bucket_id
    # Include pricing fields for effective price calculation
    listings_query = '''
        SELECT l.*, c.metal, c.weight, c.product_type
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ? AND l.active = 1
    '''
    params = [bucket_id]

    if user_id:
        listings_query += ' AND l.seller_id != ?'
        params.append(user_id)

    if graded_only:
        listings_query += ' AND l.graded = 1'
        if not any_grader:
            services = []
            if pcgs:
                services.append("'PCGS'")
            if ngc:
                services.append("'NGC'")
            if services:
                listings_query += f" AND l.grading_service IN ({', '.join(services)})"
            elif not pcgs and not ngc:
                listings = []
                total_active = 0
                conn.close()
                flash("No matching graded listings available.", "error")
                return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    listings_raw = cursor.execute(listings_query, params).fetchall()

    # Calculate effective prices and sort by them
    listings_with_prices = []
    for listing in listings_raw:
        listing_dict = dict(listing)
        listing_dict['effective_price'] = get_effective_price(listing_dict)
        listings_with_prices.append(listing_dict)

    # Sort by effective price (cheapest first)
    listings = sorted(listings_with_prices, key=lambda x: x['effective_price'])

    total_active = cursor.execute('''
        SELECT COUNT(*)
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ? AND l.active = 1
    ''', (bucket_id,)).fetchone()[0]

    if not listings:
        if total_active > 0:
            flash("You cannot add your own listings to your cart.", "error")
        else:
            flash("No listings available to fulfill your request.", "error")
        conn.close()
        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    total_filled = 0
    guest_cart = session.get('guest_cart', [])

    for listing in listings:
        if user_id and listing['seller_id'] == user_id:
            continue  # skip own listings
        if total_filled >= quantity_to_buy:
            break

        available = listing['quantity']
        to_add = min(available, quantity_to_buy - total_filled)

        if user_id:
            # Authenticated user: update DB cart
            existing = cursor.execute('''
                SELECT quantity FROM cart
                WHERE user_id = ? AND listing_id = ?
            ''', (user_id, listing['id'])).fetchone()

            if existing:
                new_qty = existing['quantity'] + to_add
                cursor.execute('''
                    UPDATE cart SET quantity = ?, grading_preference = ?
                    WHERE user_id = ? AND listing_id = ?
                ''', (new_qty, grading_preference, user_id, listing['id']))
            else:
                cursor.execute('''
                    INSERT INTO cart (user_id, listing_id, quantity, grading_preference)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, listing['id'], to_add, grading_preference))
        else:
            # Guest user: use session cart
            for item in guest_cart:
                if item['listing_id'] == listing['id']:
                    item['quantity'] += to_add
                    break
            else:
                guest_cart.append({
                    'listing_id': listing['id'],
                    'quantity': to_add,
                    'grading_preference': grading_preference  # 🆕 include grading filter
                })

        total_filled += to_add

    if not user_id:
        session['guest_cart'] = guest_cart

    conn.commit()
    conn.close()

    if total_filled == 0:
        flash("No listings available to fulfill your request.", "error")
        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    if total_filled < quantity_to_buy:
        flash(f"Only {total_filled} units could be added to your cart due to limited stock.", "warning")

    return redirect(url_for('buy.view_cart'))  # ✅ Sends user directly to cart


@buy_bp.route('/add_to_cart/<int:listing_id>', methods=['POST'])
def add_to_cart(listing_id):
    quantity = int(request.form['quantity'])

    user_id = session.get('user_id')
    grading_preference = session.get('grading_preference')  # 🆕 Pull from session

    if user_id:
        # Authenticated: save to database cart
        conn = get_db_connection()
        existing_item = conn.execute(
            'SELECT * FROM cart WHERE user_id = ? AND listing_id = ?', (user_id, listing_id)
        ).fetchone()

        if existing_item:
            new_quantity = existing_item['quantity'] + quantity
            conn.execute(
                'UPDATE cart SET quantity = ?, grading_preference = ? WHERE user_id = ? AND listing_id = ?',
                (new_quantity, grading_preference, user_id, listing_id)
            )
        else:
            conn.execute(
                'INSERT INTO cart (user_id, listing_id, quantity, grading_preference) VALUES (?, ?, ?, ?)',
                (user_id, listing_id, quantity, grading_preference)
            )

        conn.commit()
        conn.close()

    else:
        # Guest: use session-based cart
        guest_cart = session.get('guest_cart', [])
        for item in guest_cart:
            if item['listing_id'] == listing_id:
                item['quantity'] += quantity
                break
        else:
            guest_cart.append({'listing_id': listing_id, 'quantity': quantity, 'grading_preference': grading_preference})
        session['guest_cart'] = guest_cart

    return redirect(url_for('buy.item_added_to_cart'))


@buy_bp.route('/view_cart')
def view_cart():
    from utils.cart_utils import get_cart_items  # ✅ Make sure this import is present

    conn = get_db_connection()
    raw_items = get_cart_items(conn)  # ✅ Replaces all manual logic

    # Organize items into buckets and recalculate effective prices
    buckets = {}
    cart_total = 0

    for item in raw_items:
        # Calculate effective price for this cart item
        item_dict = dict(item)
        effective_price = get_effective_price(item_dict)

        bucket_id = item['category_id']
        if bucket_id not in buckets:
            buckets[bucket_id] = {
                'category': {
                    'metal': item['metal'],
                    'product_type': item['product_type'],
                    'weight': item['weight'],
                    'mint': item['mint'],
                    'year': item['year'],
                    'finish': item['finish'],
                    'grade': item['grade']
                },
                'listings': [],
                'total_qty': 0,
                'total_price': 0.0,
                'avg_price': 0.0
            }

            # Attach grading preference if available
            if 'grading_preference' in item and item['grading_preference']:
                buckets[bucket_id]['grading_preference'] = item['grading_preference']

        # Use effective price for subtotal
        subtotal = effective_price * item['quantity']
        cart_total += subtotal

        buckets[bucket_id]['listings'].append({
            'seller_id': item['seller_id'],
            'username': item['seller_username'],
            'quantity': item['quantity'],
            'price_each': effective_price,  # Use effective price
            'subtotal': subtotal,
            'rating': item['seller_rating'],
            'rating_count': item['seller_rating_count'],
            'listing_id': item['listing_id']
        })

        buckets[bucket_id]['total_qty'] += item['quantity']
        buckets[bucket_id]['total_price'] += subtotal

    # Compute average price and total available quantity per bucket
    for bucket_id, bucket in buckets.items():
        if bucket['total_qty'] > 0:
            bucket['avg_price'] = round(bucket['total_price'] / bucket['total_qty'], 2)

        # Get total available quantity for this bucket
        result = conn.execute('''
            SELECT SUM(l.quantity) as total_available
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE c.bucket_id = ? AND l.active = 1
        ''', (bucket_id,)).fetchone()
        bucket['total_available'] = result['total_available'] if result and result['total_available'] else 0

    conn.close()

    return render_template('view_cart.html', buckets=buckets, cart_total=round(cart_total, 2), session=session)


@buy_bp.route('/order_success')
def order_success():
    return render_template('order_success.html')


@buy_bp.route('/readd_seller_to_cart/<int:category_id>/<int:seller_id>', methods=['POST'])
def readd_seller_to_cart(category_id, seller_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    # Find listings from that seller in the bucket
    listings = cursor.execute('''
        SELECT id, quantity
        FROM listings
        WHERE category_id = ? AND seller_id = ? AND active = 1
    ''', (category_id, seller_id)).fetchall()

    for listing in listings:
        existing = cursor.execute('''
            SELECT quantity FROM cart
            WHERE user_id = ? AND listing_id = ?
        ''', (user_id, listing['id'])).fetchone()

        if existing:
            continue  # skip already-added listings

        cursor.execute('''
            INSERT INTO cart (user_id, listing_id, quantity)
            VALUES (?, ?, ?)
        ''', (user_id, listing['id'], listing['quantity']))

    conn.commit()
    conn.close()
    flash("Seller re-added to cart.", "success")
    return redirect(url_for('buy.view_cart'))


@buy_bp.route('/preview_buy/<int:bucket_id>', methods=['POST'])
def preview_buy(bucket_id):
    """
    Preview purchase breakdown without creating orders.
    Returns the actual total and item breakdown for confirmation modal.
    For premium-to-spot listings, creates price locks.
    """
    from services.pricing_service import create_price_lock
    user_id = session.get('user_id')

    try:
        # Get form data
        quantity = int(request.form.get('quantity', 1))
        graded_only = request.form.get('graded_only') == '1'
        any_grader = request.form.get('any_grader') == '1'
        pcgs = request.form.get('pcgs') == '1'
        ngc = request.form.get('ngc') == '1'

        conn = get_db_connection()
        cursor = conn.cursor()

        # Build listings query (include pricing fields for effective price calculation)
        listings_query = '''
            SELECT l.*, c.metal, c.weight, c.product_type
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE c.bucket_id = ? AND l.active = 1 AND l.quantity > 0
        '''
        params = [bucket_id]

        # Exclude user's own listings
        if user_id:
            listings_query += ' AND l.seller_id != ?'
            params.append(user_id)

        if graded_only:
            listings_query += ' AND l.graded = 1'
            if not any_grader:
                services = []
                if pcgs:
                    services.append("'PCGS'")
                if ngc:
                    services.append("'NGC'")
                if services:
                    listings_query += f" AND l.grading_service IN ({', '.join(services)})"

        listings_raw = cursor.execute(listings_query, params).fetchall()

        if not listings_raw:
            conn.close()
            return jsonify(success=False, message='No matching listings available.'), 400

        # Calculate effective prices and sort
        listings_with_prices = []
        has_premium_to_spot = False
        for listing in listings_raw:
            listing_dict = dict(listing)
            listing_dict['effective_price'] = get_effective_price(listing_dict)
            listings_with_prices.append(listing_dict)

            # Check if any listing is premium-to-spot
            if listing_dict.get('pricing_mode') == 'premium_to_spot':
                has_premium_to_spot = True

        # Sort by effective price
        listings = sorted(listings_with_prices, key=lambda x: (x['effective_price'], x['id']))

        # Calculate what would be filled (without modifying database)
        breakdown = []
        total_filled = 0
        total_cost = 0
        price_locks = []
        listings_to_lock = []

        for listing in listings:
            if total_filled >= quantity:
                break

            available = listing['quantity']
            fill_qty = min(available, quantity - total_filled)

            cost = fill_qty * listing['effective_price']
            total_cost += cost

            breakdown.append({
                'quantity': fill_qty,
                'price_each': listing['effective_price'],
                'subtotal': cost
            })

            # Track listing for price lock creation
            if has_premium_to_spot and user_id:
                listings_to_lock.append({
                    'listing_id': listing['id'],
                    'effective_price': listing['effective_price'],
                    'quantity': fill_qty
                })

            total_filled += fill_qty

        # Create price locks for premium-to-spot listings (30-second duration)
        lock_expires_at = None
        if has_premium_to_spot and user_id and listings_to_lock:
            for item in listings_to_lock:
                lock = create_price_lock(item['listing_id'], user_id, lock_duration_seconds=30)
                if lock:
                    price_locks.append({
                        'lock_id': lock['id'],
                        'listing_id': lock['listing_id'],
                        'locked_price': lock['locked_price']
                    })
                    # All locks expire at same time (use first lock's expiry)
                    if not lock_expires_at:
                        lock_expires_at = lock['expires_at']

        conn.close()

        if total_filled == 0:
            return jsonify(success=False, message='No items could be filled.'), 400

        # Return preview data with price lock info
        response_data = {
            'success': True,
            'total_quantity': total_filled,
            'total_cost': total_cost,
            'average_price': total_cost / total_filled if total_filled > 0 else 0,
            'breakdown': breakdown,
            'can_fill_completely': total_filled >= quantity,
            'has_price_lock': has_premium_to_spot and len(price_locks) > 0,
            'price_locks': price_locks,
            'lock_expires_at': lock_expires_at
        }

        return jsonify(response_data)

    except Exception as e:
        print(f"Preview buy error: {e}")
        return jsonify(success=False, message=str(e)), 500


@buy_bp.route('/refresh_price_lock/<int:bucket_id>', methods=['POST'])
def refresh_price_lock(bucket_id):
    """
    Refresh price locks when timer expires.
    Creates new price locks and returns updated prices.
    """
    from services.pricing_service import create_price_lock
    user_id = session.get('user_id')

    if not user_id:
        return jsonify(success=False, message='You must be logged in.'), 401

    try:
        # Get form data (same as preview_buy)
        quantity = int(request.form.get('quantity', 1))
        graded_only = request.form.get('graded_only') == '1'
        any_grader = request.form.get('any_grader') == '1'
        pcgs = request.form.get('pcgs') == '1'
        ngc = request.form.get('ngc') == '1'

        conn = get_db_connection()
        cursor = conn.cursor()

        # Build listings query (same as preview_buy)
        listings_query = '''
            SELECT l.*, c.metal, c.weight, c.product_type
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE c.bucket_id = ? AND l.active = 1 AND l.quantity > 0
        '''
        params = [bucket_id]

        # Exclude user's own listings
        if user_id:
            listings_query += ' AND l.seller_id != ?'
            params.append(user_id)

        if graded_only:
            listings_query += ' AND l.graded = 1'
            if not any_grader:
                services = []
                if pcgs:
                    services.append("'PCGS'")
                if ngc:
                    services.append("'NGC'")
                if services:
                    listings_query += f" AND l.grading_service IN ({', '.join(services)})"

        listings_raw = cursor.execute(listings_query, params).fetchall()

        if not listings_raw:
            conn.close()
            return jsonify(success=False, message='No matching listings available.'), 400

        # Calculate effective prices (potentially updated spot prices)
        listings_with_prices = []
        has_premium_to_spot = False
        for listing in listings_raw:
            listing_dict = dict(listing)
            listing_dict['effective_price'] = get_effective_price(listing_dict)
            listings_with_prices.append(listing_dict)

            if listing_dict.get('pricing_mode') == 'premium_to_spot':
                has_premium_to_spot = True

        # Sort by effective price
        listings = sorted(listings_with_prices, key=lambda x: (x['effective_price'], x['id']))

        # Calculate fill quantities and create new price locks
        total_filled = 0
        total_cost = 0
        price_locks = []
        lock_expires_at = None

        for listing in listings:
            if total_filled >= quantity:
                break

            available = listing['quantity']
            fill_qty = min(available, quantity - total_filled)

            cost = fill_qty * listing['effective_price']
            total_cost += cost

            # Create new price lock (30-second duration)
            if has_premium_to_spot:
                lock = create_price_lock(listing['id'], user_id, lock_duration_seconds=30)
                if lock:
                    price_locks.append({
                        'lock_id': lock['id'],
                        'listing_id': lock['listing_id'],
                        'locked_price': lock['locked_price']
                    })
                    if not lock_expires_at:
                        lock_expires_at = lock['expires_at']

            total_filled += fill_qty

        conn.close()

        # Return refreshed price data
        return jsonify(
            success=True,
            total_quantity=total_filled,
            total_cost=total_cost,
            average_price=total_cost / total_filled if total_filled > 0 else 0,
            has_price_lock=has_premium_to_spot and len(price_locks) > 0,
            price_locks=price_locks,
            lock_expires_at=lock_expires_at,
            price_updated=True
        )

    except Exception as e:
        print(f"Refresh price lock error: {e}")
        return jsonify(success=False, message=str(e)), 500


@buy_bp.route('/direct_buy/<int:bucket_id>', methods=['POST'])
def direct_buy_item(bucket_id):
    """
    Directly create an order from bucket purchase (bypasses checkout).
    Returns JSON for AJAX handling with success modal.
    """
    if 'user_id' not in session:
        return jsonify(success=False, message='You must be logged in to purchase items.'), 401

    user_id = session['user_id']

    try:
        # Get form data
        quantity = int(request.form.get('quantity', 1))
        graded_only = request.form.get('graded_only') == '1'
        any_grader = request.form.get('any_grader') == '1'
        pcgs = request.form.get('pcgs') == '1'
        ngc = request.form.get('ngc') == '1'

        # Get price lock IDs (comma-separated string from frontend)
        price_lock_ids_str = request.form.get('price_lock_ids', '')
        price_lock_ids = [int(id.strip()) for id in price_lock_ids_str.split(',') if id.strip().isdigit()]

        # Get user's default shipping address
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get first address for user (or could require address selection in modal)
        address_row = cursor.execute(
            'SELECT street, street_line2, city, state, zip_code FROM addresses WHERE user_id = ? LIMIT 1',
            (user_id,)
        ).fetchone()

        if not address_row:
            conn.close()
            return jsonify(success=False, message='Please add a shipping address to your account first.'), 400

        # Format shipping address with all components, using bullet as separator for Line 2
        street_line2 = address_row['street_line2'] or ''
        if street_line2.strip():
            shipping_address = f"{address_row['street']} • {street_line2} • {address_row['city']}, {address_row['state']} {address_row['zip_code']}"
        else:
            shipping_address = f"{address_row['street']} • {address_row['city']}, {address_row['state']} {address_row['zip_code']}"

        # Load price locks if provided
        price_lock_map = {}  # listing_id -> locked_price
        if price_lock_ids:
            from datetime import datetime
            placeholders = ','.join(['?' for _ in price_lock_ids])
            locks_query = f'''
                SELECT listing_id, locked_price, expires_at
                FROM price_locks
                WHERE id IN ({placeholders})
                  AND user_id = ?
            '''
            locks_params = price_lock_ids + [user_id]
            locks = cursor.execute(locks_query, locks_params).fetchall()

            now = datetime.now()
            for lock in locks:
                expires_at = datetime.fromisoformat(lock['expires_at'])
                # Validate lock hasn't expired
                if expires_at > now:
                    price_lock_map[lock['listing_id']] = lock['locked_price']
                else:
                    # Lock expired - will use current effective price
                    print(f"[WARNING] Price lock for listing {lock['listing_id']} has expired")

        # Build listings query with grading filters (include pricing fields)
        listings_query = '''
            SELECT l.*, c.metal, c.weight, c.product_type
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE c.bucket_id = ? AND l.active = 1 AND l.quantity > 0
        '''
        params = [bucket_id]

        # Exclude user's own listings
        if user_id:
            listings_query += ' AND l.seller_id != ?'
            params.append(user_id)

        if graded_only:
            listings_query += ' AND l.graded = 1'
            if not any_grader:
                services = []
                if pcgs:
                    services.append("'PCGS'")
                if ngc:
                    services.append("'NGC'")
                if services:
                    listings_query += f" AND l.grading_service IN ({', '.join(services)})"

        listings_raw = cursor.execute(listings_query, params).fetchall()

        if not listings_raw:
            conn.close()
            return jsonify(success=False, message='No matching listings available for purchase.'), 400

        # Calculate effective prices and sort
        # Use locked prices when available, otherwise calculate current effective price
        listings_with_prices = []
        for listing in listings_raw:
            listing_dict = dict(listing)
            listing_id = listing_dict['id']

            # Use locked price if available, otherwise calculate effective price
            if listing_id in price_lock_map:
                listing_dict['effective_price'] = price_lock_map[listing_id]
                listing_dict['price_was_locked'] = True
            else:
                listing_dict['effective_price'] = get_effective_price(listing_dict)
                listing_dict['price_was_locked'] = False

            listings_with_prices.append(listing_dict)

        # Sort by effective price
        listings = sorted(listings_with_prices, key=lambda x: (x['effective_price'], x['id']))

        # Fill order from listings (group by seller)
        seller_fills = {}  # seller_id -> list of {listing_id, quantity, price_each}
        total_filled = 0

        for listing in listings:
            if total_filled >= quantity:
                break

            seller_id = listing['seller_id']
            available = listing['quantity']
            fill_qty = min(available, quantity - total_filled)

            # Update listing quantity
            new_qty = available - fill_qty
            if new_qty <= 0:
                cursor.execute('UPDATE listings SET quantity = 0, active = 0 WHERE id = ?', (listing['id'],))
            else:
                cursor.execute('UPDATE listings SET quantity = ? WHERE id = ?', (new_qty, listing['id']))

            # Track fill for this seller (using effective price)
            if seller_id not in seller_fills:
                seller_fills[seller_id] = []

            seller_fills[seller_id].append({
                'listing_id': listing['id'],
                'quantity': fill_qty,
                'price_each': listing['effective_price'],  # Use effective price
                'grading_service': listing.get('grading_service')
            })

            total_filled += fill_qty

        if total_filled == 0:
            conn.close()
            return jsonify(success=False, message='No items could be filled from available listings.'), 400

        # Get category/bucket info for notifications
        bucket_row = cursor.execute('SELECT * FROM categories WHERE bucket_id = ? LIMIT 1', (bucket_id,)).fetchone()
        bucket_dict = dict(bucket_row) if bucket_row else {}

        # Collect notification data (will send after commit to avoid database locking)
        notifications_to_send = []

        # Create one order per seller
        orders_created = []
        for seller_id, items in seller_fills.items():
            total_price = sum(item['quantity'] * item['price_each'] for item in items)

            # Create order
            cursor.execute('''
                INSERT INTO orders (buyer_id, total_price, shipping_address, status, created_at)
                VALUES (?, ?, ?, 'Pending Shipment', datetime('now'))
            ''', (user_id, total_price, shipping_address))

            order_id = cursor.lastrowid

            # Create order_items and notify seller for each listing
            for item in items:
                cursor.execute('''
                    INSERT INTO order_items (order_id, listing_id, quantity, price_each)
                    VALUES (?, ?, ?, ?)
                ''', (order_id, item['listing_id'], item['quantity'], item['price_each']))

                # Build item description for notification
                item_desc_parts = []
                if bucket_dict.get('metal'):
                    item_desc_parts.append(bucket_dict['metal'])
                if bucket_dict.get('product_line'):
                    item_desc_parts.append(bucket_dict['product_line'])
                if bucket_dict.get('weight'):
                    item_desc_parts.append(bucket_dict['weight'])
                if bucket_dict.get('year'):
                    item_desc_parts.append(bucket_dict['year'])
                item_description = ' '.join(item_desc_parts) if item_desc_parts else 'Item'

                # Check if this was a partial sale (listing still has quantity remaining)
                listing_info = cursor.execute(
                    'SELECT quantity FROM listings WHERE id = ?',
                    (item['listing_id'],)
                ).fetchone()
                is_partial = listing_info and listing_info['quantity'] > 0
                remaining_quantity = listing_info['quantity'] if is_partial else 0

                # Collect notification data (will send after commit)
                notifications_to_send.append({
                    'seller_id': seller_id,
                    'order_id': order_id,
                    'listing_id': item['listing_id'],
                    'item_description': item_description,
                    'quantity_sold': item['quantity'],
                    'price_per_unit': item['price_each'],
                    'total_amount': item['quantity'] * item['price_each'],
                    'shipping_address': shipping_address,
                    'is_partial': is_partial,
                    'remaining_quantity': remaining_quantity
                })

            orders_created.append({
                'order_id': order_id,
                'total_price': total_price,
                'quantity': sum(i['quantity'] for i in items),
                'price_each': items[0]['price_each']  # First item price for display
            })

        conn.commit()
        conn.close()

        # Send notifications AFTER commit (avoids database locking)
        for notif_data in notifications_to_send:
            try:
                notify_listing_sold(**notif_data)
            except Exception as notify_error:
                print(f"[ERROR] Failed to notify seller {notif_data['seller_id']}: {notify_error}")

        # Build success response with order details
        return jsonify(
            success=True,
            message=f'Order created successfully! {total_filled} items purchased.',
            orders=orders_created,
            total_quantity=total_filled,
            bucket=bucket_dict,
            shipping_address=shipping_address
        )

    except ValueError as e:
        return jsonify(success=False, message=f'Invalid input: {str(e)}'), 400
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return jsonify(success=False, message=f'Error creating order: {str(e)}'), 500