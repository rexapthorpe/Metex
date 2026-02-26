"""
Cart-related routes for the buy blueprint.

Routes:
- /add_to_cart/<int:listing_id> (POST) - Add item to cart
- /view_cart - View cart contents
- /order_success - Order success page
- /readd_seller_to_cart/<int:category_id>/<int:seller_id> (POST) - Re-add seller to cart
"""

from flask import render_template, request, redirect, url_for, session, flash
from database import get_db_connection
from services.pricing_service import get_effective_price
from utils.auth_utils import frozen_check
from config import GRADING_FEE_PER_UNIT

from . import buy_bp


@buy_bp.route('/add_to_cart/<int:listing_id>', methods=['POST'])
@frozen_check
def add_to_cart(listing_id):
    quantity = int(request.form['quantity'])
    third_party_grading = int(request.form.get('third_party_grading', 0))

    user_id = session.get('user_id')

    if user_id:
        # Authenticated: save to database cart
        conn = get_db_connection()
        existing_item = conn.execute(
            'SELECT * FROM cart WHERE user_id = ? AND listing_id = ?', (user_id, listing_id)
        ).fetchone()

        if existing_item:
            new_quantity = existing_item['quantity'] + quantity
            conn.execute(
                'UPDATE cart SET quantity = ?, third_party_grading_requested = ? WHERE user_id = ? AND listing_id = ?',
                (new_quantity, third_party_grading, user_id, listing_id)
            )
        else:
            conn.execute(
                'INSERT INTO cart (user_id, listing_id, quantity, third_party_grading_requested) VALUES (?, ?, ?, ?)',
                (user_id, listing_id, quantity, third_party_grading)
            )

        conn.commit()
        conn.close()

    else:
        # Guest: use session-based cart
        guest_cart = session.get('guest_cart', [])
        for item in guest_cart:
            if item['listing_id'] == listing_id:
                item['quantity'] += quantity
                item['third_party_grading_requested'] = third_party_grading
                break
        else:
            guest_cart.append({
                'listing_id': listing_id,
                'quantity': quantity,
                'third_party_grading_requested': third_party_grading
            })
        session['guest_cart'] = guest_cart

    return redirect(url_for('buy.view_cart'))


@buy_bp.route('/view_cart')
def view_cart():
    from utils.cart_utils import get_cart_items, validate_and_refill_cart, validate_guest_cart

    conn = get_db_connection()

    # Validate cart and refill from other listings if inventory changed
    user_id = session.get('user_id')
    if user_id:
        refill_log = validate_and_refill_cart(conn, user_id)
        # Optional: flash messages for items that couldn't be refilled
        for bucket_id, log in refill_log.items():
            if log['missing'] > 0:
                flash(f"{log['missing']} item(s) no longer available and couldn't be replaced.", "warning")
    else:
        # Validate guest cart - remove unavailable items from session
        validate_guest_cart(conn)

    raw_items = get_cart_items(conn)  # Replaces all manual logic

    # Organize items into buckets and recalculate effective prices
    buckets = {}
    cart_total = 0
    has_tpg = False

    for item in raw_items:
        # Calculate effective price for this cart item
        item_dict = dict(item)
        effective_price = get_effective_price(item_dict)

        category_id = item['category_id']
        if category_id not in buckets:
            cover_photo_url = None
            if item.get('is_isolated') and item.get('file_path'):
                raw = item['file_path']
                if raw.startswith('/'):
                    cover_photo_url = raw
                elif raw.startswith('static/'):
                    cover_photo_url = '/' + raw
                else:
                    cover_photo_url = '/static/' + raw

            buckets[category_id] = {
                'category': {
                    'metal': item['metal'],
                    'product_type': item['product_type'],
                    'weight': item['weight'],
                    'purity': item.get('purity'),  # Added
                    'mint': item['mint'],
                    'year': item['year'],
                    'finish': item['finish'],
                    'grade': item['grade'],
                    'product_line': item.get('product_line'),  # Added
                    'is_isolated': item.get('is_isolated', 0)  # For one-of-a-kind display
                },
                'listings': [],
                'total_qty': 0,
                'total_price': 0.0,
                'avg_price': 0.0,
                'cover_photo_url': cover_photo_url
            }

            # Attach grading preference if available
            if 'grading_preference' in item and item['grading_preference']:
                buckets[category_id]['grading_preference'] = item['grading_preference']

        # Track TPG preference
        if item.get('third_party_grading_requested'):
            has_tpg = True

        # Use effective price for subtotal
        subtotal = effective_price * item['quantity']
        cart_total += subtotal

        buckets[category_id]['listings'].append({
            'seller_id': item['seller_id'],
            'seller_username': item['seller_username'],
            'quantity': item['quantity'],
            'effective_price': effective_price,  # Use effective price
            'price_each': effective_price,  # Keep for backward compatibility
            'subtotal': subtotal,
            'seller_rating': item['seller_rating'],
            'rating_count': item['seller_rating_count'],
            'listing_id': item['listing_id'],
            'graded': item.get('graded'),  # Added: whether this specific listing is graded
            'grading_service': item.get('grading_service'),  # Added: grading service (PCGS/NGC)
            'photos': [item['file_path']] if item.get('file_path') else []  # Add photos for image display
        })

        buckets[category_id]['total_qty'] += item['quantity']
        buckets[category_id]['total_price'] += subtotal

    # Compute average price and total available quantity per bucket
    for category_id, bucket in buckets.items():
        if bucket['total_qty'] > 0:
            bucket['avg_price'] = round(bucket['total_price'] / bucket['total_qty'], 2)

        # Get total available quantity for this category (excluding user's own listings)
        if user_id:
            result = conn.execute('''
                SELECT SUM(quantity) as total_available
                FROM listings
                WHERE category_id = ? AND active = 1 AND seller_id != ?
            ''', (category_id, user_id)).fetchone()
        else:
            # Guest cart - include all listings
            result = conn.execute('''
                SELECT SUM(quantity) as total_available
                FROM listings
                WHERE category_id = ? AND active = 1
            ''', (category_id,)).fetchone()
        bucket['total_available'] = result['total_available'] if result and result['total_available'] else 0

    # Build suggested items based on metals in cart
    suggested_items = []
    if buckets:
        cart_metals = list(set(
            b['category']['metal'] for b in buckets.values() if b['category'].get('metal')
        ))
        if cart_metals:
            # Get bucket_ids already in cart so we can exclude them
            cat_ids = list(buckets.keys())
            cat_ph = ','.join('?' * len(cat_ids))
            cart_bucket_ids = [
                r['bucket_id'] for r in conn.execute(
                    f'SELECT bucket_id FROM categories WHERE id IN ({cat_ph}) AND bucket_id IS NOT NULL',
                    cat_ids
                ).fetchall()
            ]

            metal_ph = ','.join('?' * len(cart_metals))
            exclude_clause = (
                f'AND c.bucket_id NOT IN ({",".join("?" * len(cart_bucket_ids))})'
                if cart_bucket_ids else ''
            )
            params = cart_metals + (cart_bucket_ids if cart_bucket_ids else [])

            rows = conn.execute(f'''
                SELECT DISTINCT
                    c.bucket_id, c.metal, c.product_type, c.weight,
                    c.mint, c.year, c.product_line, c.coin_series,
                    l.price_per_coin, l.pricing_mode, l.spot_premium,
                    l.floor_price, l.pricing_metal
                FROM categories c
                JOIN listings l ON l.category_id = c.id
                WHERE l.active = 1 AND l.quantity > 0
                  AND c.bucket_id IS NOT NULL
                  AND c.is_isolated = 0
                  AND c.metal IN ({metal_ph})
                  {exclude_clause}
            ''', params).fetchall()

            bucket_map = {}
            for row in rows:
                rd = dict(row)
                # get_effective_price needs metal/weight/product_type on the dict
                ep = get_effective_price(rd)
                bid = rd['bucket_id']
                if bid not in bucket_map:
                    bucket_map[bid] = {
                        'bucket_id': bid,
                        'metal': rd['metal'],
                        'product_type': rd['product_type'],
                        'weight': rd['weight'],
                        'mint': rd['mint'],
                        'year': rd['year'],
                        'product_line': rd['product_line'],
                        'coin_series': rd['coin_series'],
                        'lowest_price': ep
                    }
                else:
                    bucket_map[bid]['lowest_price'] = min(bucket_map[bid]['lowest_price'], ep)

            suggested_items = sorted(
                bucket_map.values(),
                key=lambda x: (x['lowest_price'] is None, x['lowest_price'] or 0)
            )[:8]

    conn.close()

    # Compute total item count and grading fee
    total_item_count = sum(b['total_qty'] for b in buckets.values())
    grading_fee = round(GRADING_FEE_PER_UNIT * total_item_count, 2) if has_tpg else 0.0
    grand_total = round(cart_total + grading_fee, 2)

    return render_template(
        'view_cart.html',
        buckets=buckets,
        cart_total=round(cart_total, 2),
        grading_fee=grading_fee,
        grading_fee_per_unit=GRADING_FEE_PER_UNIT,
        third_party_grading=has_tpg,
        item_count=total_item_count,
        grand_total=grand_total,
        suggested_items=suggested_items,
        session=session
    )


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
