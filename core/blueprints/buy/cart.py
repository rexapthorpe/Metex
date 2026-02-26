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

from . import buy_bp


@buy_bp.route('/add_to_cart/<int:listing_id>', methods=['POST'])
@frozen_check
def add_to_cart(listing_id):
    quantity = int(request.form['quantity'])
    third_party_grading = int(request.form.get('third_party_grading', 0))

    user_id = session.get('user_id')
    grading_pref = 'ANY' if third_party_grading else 'NONE'

    if user_id:
        # Authenticated: save to database cart.
        # TPG is part of line-item identity: same listing with different grading = separate rows.
        conn = get_db_connection()
        existing_item = conn.execute(
            'SELECT id, quantity FROM cart WHERE user_id = ? AND listing_id = ? AND third_party_grading_requested = ?',
            (user_id, listing_id, third_party_grading)
        ).fetchone()

        if existing_item:
            new_quantity = existing_item['quantity'] + quantity
            conn.execute(
                'UPDATE cart SET quantity = ? WHERE id = ?',
                (new_quantity, existing_item['id'])
            )
        else:
            conn.execute(
                'INSERT INTO cart (user_id, listing_id, quantity, third_party_grading_requested, grading_preference) '
                'VALUES (?, ?, ?, ?, ?)',
                (user_id, listing_id, quantity, third_party_grading, grading_pref)
            )

        conn.commit()
        conn.close()

    else:
        # Guest: use session-based cart. TPG is part of line-item identity.
        guest_cart = session.get('guest_cart', [])
        for item in guest_cart:
            if (item['listing_id'] == listing_id and
                    int(item.get('third_party_grading_requested', 0)) == third_party_grading):
                item['quantity'] += quantity
                break
        else:
            guest_cart.append({
                'listing_id': listing_id,
                'quantity': quantity,
                'third_party_grading_requested': third_party_grading,
                'grading_preference': grading_pref,
            })
        session['guest_cart'] = guest_cart

    return redirect(url_for('buy.view_cart'))


@buy_bp.route('/view_cart')
def view_cart():
    from utils.cart_utils import build_cart_summary, validate_and_refill_cart, validate_guest_cart

    conn = get_db_connection()

    # Validate cart and refill from other listings if inventory changed
    user_id = session.get('user_id')
    if user_id:
        refill_log = validate_and_refill_cart(conn, user_id)
        for bucket_id, log in refill_log.items():
            if log['missing'] > 0:
                flash(f"{log['missing']} item(s) no longer available and couldn't be replaced.", "warning")
    else:
        validate_guest_cart(conn)

    summary = build_cart_summary(conn, user_id)
    buckets = summary['buckets']

    # Build suggested items based on metals in cart
    suggested_items = []
    if buckets:
        cart_metals = list(set(
            b['category']['metal'] for b in buckets.values() if b['category'].get('metal')
        ))
        if cart_metals:
            # Get unique integer category_ids from bucket values (keys are composite strings).
            cat_ids = list({b['category_id'] for b in buckets.values()})
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

    return render_template(
        'view_cart.html',
        buckets=buckets,
        cart_total=summary['subtotal'],
        grading_fee=summary['grading_fee'],
        grading_fee_per_unit=summary['grading_fee_per_unit'],
        third_party_grading=summary['has_tpg'],
        item_count=summary['item_count'],
        grand_total=summary['grand_total'],
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
