# utils/cart_utils.py
from flask import session
from collections import defaultdict

def get_cart_items(conn):
    """Flat list of all cart entries — used for legacy or simplified views."""
    user_id = session.get('user_id')

    if user_id:
        rows = conn.execute('''
            SELECT 
                listings.id AS listing_id,
                cart.quantity,
                cart.grading_preference,
                listings.price_per_coin,
                listings.seller_id,
                users.username AS seller_username,
                categories.id AS category_id,
                categories.metal,
                categories.product_type,
                categories.weight,
                categories.mint,
                categories.year,
                categories.finish,
                categories.grade,
                (
                    SELECT ROUND(AVG(rating), 2)
                    FROM ratings
                    WHERE ratee_id = users.id
                ) AS seller_rating,
                (
                    SELECT COUNT(*) FROM ratings
                    WHERE ratee_id = users.id
                ) AS seller_rating_count
            FROM cart
            JOIN listings ON cart.listing_id = listings.id
            JOIN categories ON listings.category_id = categories.id
            JOIN users ON listings.seller_id = users.id
            WHERE cart.user_id = ?
            ORDER BY categories.id, price_per_coin ASC
        ''', (user_id,)).fetchall()

        return [dict(row) for row in rows]

    else:
        guest_cart = session.get('guest_cart', [])
        if not guest_cart:
            return []

        listing_ids = [item['listing_id'] for item in guest_cart]
        placeholders = ','.join(['?'] * len(listing_ids))
        listing_qty = {item['listing_id']: item['quantity'] for item in guest_cart}
        grading_map = {item['listing_id']: item.get('grading_preference') for item in guest_cart}

        rows = conn.execute(f'''
            SELECT 
                listings.id AS listing_id,
                listings.price_per_coin,
                listings.seller_id,
                users.username AS seller_username,
                categories.id AS category_id,
                categories.metal,
                categories.product_type,
                categories.weight,
                categories.mint,
                categories.year,
                categories.finish,
                categories.grade,
                (
                    SELECT ROUND(AVG(rating), 2)
                    FROM ratings
                    WHERE ratee_id = users.id
                ) AS seller_rating,
                (
                    SELECT COUNT(*) FROM ratings
                    WHERE ratee_id = users.id
                ) AS seller_rating_count
            FROM listings
            JOIN categories ON listings.category_id = categories.id
            JOIN users ON listings.seller_id = users.id
            WHERE listings.id IN ({placeholders})
        ''', listing_ids).fetchall()

        unified_items = []
        for row in rows:
            row_dict = dict(row)
            listing_id = row['listing_id']
            row_dict['quantity'] = listing_qty[listing_id]
            row_dict['grading_preference'] = grading_map.get(listing_id)
            unified_items.append(row_dict)

        return unified_items

def get_cart_data(conn):
    """
    Groups cart items by category_id and returns structured bucket data
    including per-listing entries for multi-seller support.
    """
    user_id = session.get('user_id')

    if user_id:
        rows = conn.execute('''
            SELECT 
                listings.id AS listing_id,
                cart.quantity,
                cart.grading_preference,
                listings.price_per_coin,
                listings.seller_id,
                users.username AS seller_username,
                categories.id AS category_id,
                categories.metal,
                categories.product_type,
                categories.weight,
                categories.mint,
                categories.year,
                categories.finish,
                categories.grade,
                (
                    SELECT ROUND(AVG(rating), 2)
                    FROM ratings
                    WHERE ratee_id = users.id
                ) AS seller_rating
            FROM cart
            JOIN listings ON cart.listing_id = listings.id
            JOIN categories ON listings.category_id = categories.id
            JOIN users ON listings.seller_id = users.id
            WHERE cart.user_id = ?
            ORDER BY categories.id, price_per_coin ASC
        ''', (user_id,)).fetchall()
        rows = [dict(row) for row in rows]  # Ensure rows are dicts so .get works

    else:
        guest_cart = session.get('guest_cart', [])
        if not guest_cart:
            return {}, 0.0

        listing_ids = [item['listing_id'] for item in guest_cart]
        placeholders = ','.join(['?'] * len(listing_ids))
        listing_qty = {item['listing_id']: item['quantity'] for item in guest_cart}
        grading_map = {item['listing_id']: item.get('grading_preference') for item in guest_cart}

        rows = conn.execute(f'''
            SELECT 
                listings.id AS listing_id,
                listings.price_per_coin,
                listings.seller_id,
                users.username AS seller_username,
                categories.id AS category_id,
                categories.metal,
                categories.product_type,
                categories.weight,
                categories.mint,
                categories.year,
                categories.finish,
                categories.grade,
                (
                    SELECT ROUND(AVG(rating), 2)
                    FROM ratings
                    WHERE ratee_id = users.id
                ) AS seller_rating
            FROM listings
            JOIN categories ON listings.category_id = categories.id
            JOIN users ON listings.seller_id = users.id
            WHERE listings.id IN ({placeholders})
        ''', listing_ids).fetchall()

        rows = [dict(row) for row in rows]  # Ensure rows are dicts
        for row in rows:
            row['quantity'] = listing_qty[row['listing_id']]
            row['grading_preference'] = grading_map.get(row['listing_id'])

    # Build bucket structure
    buckets = defaultdict(lambda: {
        'category': {},
        'listings': [],
        'total_qty': 0,
        'total_price': 0.0,
        'avg_price': 0.0
    })

    cart_total = 0.0
    for row in rows:
        cat_id = row['category_id']
        qty = row['quantity']
        price = row['price_per_coin']
        line_total = qty * price

        bucket = buckets[cat_id]
        bucket['listings'].append({
            'listing_id': row['listing_id'],
            'price_per_coin': price,
            'quantity': qty,
            'seller_username': row['seller_username'],
            'seller_rating': row['seller_rating'],
            'grading_preference': row.get('grading_preference')
        })

        bucket['total_qty'] += qty
        bucket['total_price'] += line_total
        bucket['category'] = {
            'metal': row['metal'],
            'product_type': row['product_type'],
            'weight': row['weight'],
            'mint': row['mint'],
            'year': row['year'],
            'finish': row['finish'],
            'grade': row['grade']
        }

        cart_total += line_total

    for bucket in buckets.values():
        if bucket['total_qty'] > 0:
            bucket['avg_price'] = bucket['total_price'] / bucket['total_qty']

    return dict(buckets), cart_total
