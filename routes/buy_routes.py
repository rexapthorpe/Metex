# routes/buy_routes.py

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from routes.auto_fill_bid import auto_fill_bid
from datetime import datetime
from database import get_db_connection
from utils.cart_utils import get_cart_items
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

    query = '''
        SELECT 
            categories.id AS category_id,
            categories.metal,
            categories.product_type,
            categories.weight,
            categories.mint,
            categories.year,
            categories.finish,
            categories.grade,
            categories.coin_series,
            MIN(listings.price_per_coin) AS lowest_price,
            SUM(listings.quantity) AS total_available
        FROM listings
        JOIN categories ON listings.category_id = categories.id
        WHERE listings.active = 1 AND listings.quantity > 0
    '''
    params = []

    if graded_only:
        query += ' AND listings.graded = 1'

        if not any_grader:
            services = []
            if pcgs:
                services.append("'PCGS'")
            if ngc:
                services.append("'NGC'")
            if services:
                query += f" AND listings.grading_service IN ({', '.join(services)})"
            elif not pcgs and not ngc:
                # No grader selected = no results
                conn.close()
                return render_template('buy.html', buckets=[], graded_only=graded_only)

    query += '''
        GROUP BY categories.id
        ORDER BY lowest_price ASC
    '''

    buckets = conn.execute(query, params).fetchall()
    conn.close()

    return render_template('buy.html', buckets=buckets, graded_only=graded_only)


@buy_bp.route('/bucket/<int:bucket_id>')
def view_bucket(bucket_id):
    conn = get_db_connection()

    # Fetch the bucket metadata
    bucket = conn.execute('SELECT * FROM categories WHERE id = ?', (bucket_id,)).fetchone()
    if not bucket:
        conn.close()
        flash("Item not found.", "error")
        return redirect(url_for('buy.buy'))

    # Safely map fields and build specs with `--` fallbacks
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

    # 🔧 No DB image column used—template will render grey placeholder if empty
    images = []

    # Grading filter logic (GET)
    graded_only = request.args.get('graded_only') == '1'
    any_grader  = request.args.get('any_grader') == '1'
    pcgs        = request.args.get('pcgs') == '1'
    ngc         = request.args.get('ngc') == '1'
    grading_filter_applied = graded_only and (any_grader or pcgs or ngc)

    # Listings query (respect filters)
    listings_query = 'SELECT * FROM listings WHERE category_id = ? AND active = 1'
    listings_params = [bucket_id]

    if grading_filter_applied:
        listings_query += ' AND graded = 1'
        if not any_grader:
            services = []
            if pcgs: services.append("'PCGS'")
            if ngc:  services.append("'NGC'")
            if services:
                listings_query += f" AND grading_service IN ({', '.join(services)})"
            else:
                # No specific grader chosen → no results
                listings = []
    if 'listings' not in locals():
        listings = conn.execute(listings_query, listings_params).fetchall()

    # Availability (respect filters)
    availability_query = '''
        SELECT MIN(price_per_coin) AS lowest_price,
               SUM(quantity)       AS total_available
        FROM listings
        WHERE category_id = ? AND active = 1
    '''
    availability_params = [bucket_id]
    if grading_filter_applied:
        availability_query += ' AND graded = 1'
        if not any_grader:
            services = []
            if pcgs: services.append("'PCGS'")
            if ngc:  services.append("'NGC'")
            if services:
                availability_query += f" AND grading_service IN ({', '.join(services)})"
            else:
                availability = {'lowest_price': None, 'total_available': 0}
    if 'availability' not in locals():
        availability = conn.execute(availability_query, availability_params).fetchone()
        if not availability or availability['total_available'] is None:
            availability = {'lowest_price': None, 'total_available': 0}

    # Current user
    user_id = session.get('user_id')

    # Current user's bids
    user_bids = []
    if user_id:
        user_bids = conn.execute('''
            SELECT id, quantity_requested, remaining_quantity, price_per_coin, status, created_at, active
            FROM bids
            WHERE buyer_id = ? AND category_id = ? AND active = 1
            ORDER BY price_per_coin DESC
        ''', (user_id, bucket_id)).fetchall()

    # All other users' bids (or all if not logged in)
    if user_id:
        bids = conn.execute('''
            SELECT bids.*, users.username AS buyer_name
            FROM bids
            JOIN users ON bids.buyer_id = users.id
            WHERE bids.category_id = ? AND bids.active = 1 AND bids.buyer_id != ?
            ORDER BY bids.price_per_coin DESC
        ''', (bucket_id, user_id)).fetchall()
    else:
        bids = conn.execute('''
            SELECT bids.*, users.username AS buyer_name
            FROM bids
            JOIN users ON bids.buyer_id = users.id
            WHERE bids.category_id = ? AND bids.active = 1
            ORDER BY bids.price_per_coin DESC
        ''', (bucket_id,)).fetchall()

    # Best bid (cast Row -> dict so |tojson works)
    best_bid_row = conn.execute('''
        SELECT id, price_per_coin, quantity_requested, remaining_quantity
        FROM bids
        WHERE category_id = ? AND active = 1
        ORDER BY price_per_coin DESC
        LIMIT 1
    ''', (bucket_id,)).fetchone()
    best_bid = dict(best_bid_row) if best_bid_row else None

    # Sellers for modal — aggregate ratings from ratings table
    sellers = conn.execute('''
        SELECT
          u.id                  AS seller_id,
          u.username            AS username,
          rr.rating             AS rating,         -- AVG from ratings
          rr.rating_count       AS rating_count,   -- COUNT from ratings
          MIN(l.price_per_coin) AS lowest_price,
          SUM(l.quantity)       AS total_qty
        FROM listings AS l
        JOIN users AS u ON u.id = l.seller_id
        LEFT JOIN (
            SELECT
              ratee_id,
              AVG(rating) AS rating,
              COUNT(*)    AS rating_count
            FROM ratings
            GROUP BY ratee_id
        ) AS rr ON rr.ratee_id = u.id
        WHERE l.category_id = ? AND l.active = 1 AND l.quantity > 0
        GROUP BY u.id, u.username, rr.rating, rr.rating_count
        ORDER BY (rr.rating IS NULL) ASC, rr.rating DESC, lowest_price ASC
    ''', (bucket_id,)).fetchall()

    user_is_logged_in = 'user_id' in session
    conn.close()

    return render_template(
        'view_bucket.html',
        bucket=bucket,
        specs=specs,
        images=images,                 # empty list → grey placeholder
        listings=listings,
        availability=availability,
        graded_only=graded_only,
        user_bids=user_bids,
        bids=bids,
        best_bid=best_bid,             # dict or None
        sellers=sellers,
        user_is_logged_in=user_is_logged_in
    )

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

    # Build listings query with grading filters
    listings_query = '''
        SELECT id, quantity, price_per_coin, seller_id
        FROM listings
        WHERE category_id = ? AND active = 1
    '''
    params = [bucket_id]

    if user_id:
        listings_query += ' AND seller_id != ?'
        params.append(user_id)

    if graded_only:
        listings_query += ' AND graded = 1'
        if not any_grader:
            services = []
            if pcgs:
                services.append("'PCGS'")
            if ngc:
                services.append("'NGC'")
            if services:
                listings_query += f" AND grading_service IN ({', '.join(services)})"
            elif not pcgs and not ngc:
                listings = []
                total_active = 0
                conn.close()
                flash("No matching graded listings available.", "error")
                return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    listings_query += ' ORDER BY price_per_coin ASC'
    listings = cursor.execute(listings_query, params).fetchall()

    total_active = cursor.execute('''
        SELECT COUNT(*) FROM listings
        WHERE category_id = ? AND active = 1
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
    conn.close()

    # Organize items into buckets
    buckets = {}
    cart_total = 0

    for item in raw_items:
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

        subtotal = item['price_per_coin'] * item['quantity']
        cart_total += subtotal

        buckets[bucket_id]['listings'].append({
            'seller_id': item['seller_id'],
            'username': item['seller_username'],
            'quantity': item['quantity'],
            'price_each': item['price_per_coin'],
            'subtotal': subtotal,
            'rating': item['seller_rating'],
            'rating_count': item['seller_rating_count'],
            'listing_id': item['listing_id']
        })

        buckets[bucket_id]['total_qty'] += item['quantity']
        buckets[bucket_id]['total_price'] += subtotal

    # Compute average price per bucket
    for bucket in buckets.values():
        if bucket['total_qty'] > 0:
            bucket['avg_price'] = round(bucket['total_price'] / bucket['total_qty'], 2)

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