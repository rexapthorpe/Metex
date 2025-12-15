# utils/cart_utils.py
from flask import session
from collections import defaultdict

def validate_and_refill_cart(conn, user_id):
    """
    Validate cart inventory and refill from other listings when items are consumed.
    This ensures cart quantities reflect actual available inventory.
    Returns: dict of {bucket_id: quantity_refilled} for logging/flash messages
    """
    if not user_id:
        return {}  # Guest carts handled separately

    cursor = conn.cursor()
    refill_log = {}

    # Get all cart entries with current listing availability
    cart_entries = cursor.execute('''
        SELECT
            cart.id as cart_id,
            cart.listing_id,
            cart.quantity as cart_qty,
            listings.quantity as listing_available_qty,
            listings.active,
            listings.seller_id,
            categories.id as category_id,
            categories.bucket_id,
            listings.price_per_coin
        FROM cart
        JOIN listings ON cart.listing_id = listings.id
        JOIN categories ON listings.category_id = categories.id
        WHERE cart.user_id = ?
        ORDER BY categories.bucket_id, listings.price_per_coin ASC
    ''', (user_id,)).fetchall()

    # Group by bucket to handle refilling
    buckets_to_refill = defaultdict(list)

    for entry in cart_entries:
        bucket_id = entry['bucket_id']
        cart_qty = entry['cart_qty']
        available_qty = entry['listing_available_qty']
        active = entry['active']

        # Check if listing is out of stock or partially consumed
        if not active or available_qty == 0:
            # Listing is completely gone - remove from cart and track for refill
            cursor.execute('DELETE FROM cart WHERE id = ?', (entry['cart_id'],))
            buckets_to_refill[bucket_id].append({
                'lost_qty': cart_qty,
                'old_listing_id': entry['listing_id'],
                'seller_id': entry['seller_id']
            })
        elif available_qty < cart_qty:
            # Listing partially consumed - reduce cart qty and refill difference
            cursor.execute('UPDATE cart SET quantity = ? WHERE id = ?', (available_qty, entry['cart_id']))
            buckets_to_refill[bucket_id].append({
                'lost_qty': cart_qty - available_qty,
                'old_listing_id': entry['listing_id'],
                'seller_id': entry['seller_id']
            })

    # Now refill from other listings in each affected bucket
    for bucket_id, items_to_refill in buckets_to_refill.items():
        total_lost = sum(item['lost_qty'] for item in items_to_refill)
        total_refilled = 0

        # Get available listings in this bucket (excluding user's own and already-processed listings)
        excluded_listing_ids = [item['old_listing_id'] for item in items_to_refill]
        placeholders = ','.join(['?'] * len(excluded_listing_ids))

        query = f'''
            SELECT l.id, l.quantity, l.seller_id, l.price_per_coin
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE c.bucket_id = ?
              AND l.active = 1
              AND l.quantity > 0
              AND l.seller_id != ?
              AND l.id NOT IN ({placeholders})
            ORDER BY l.price_per_coin ASC
        '''

        params = [bucket_id, user_id] + excluded_listing_ids
        available_listings = cursor.execute(query, params).fetchall()

        # Refill from cheapest available listings
        remaining_to_fill = total_lost

        for listing in available_listings:
            if remaining_to_fill <= 0:
                break

            # Check if this listing is already in cart
            existing = cursor.execute(
                'SELECT quantity FROM cart WHERE user_id = ? AND listing_id = ?',
                (user_id, listing['id'])
            ).fetchone()

            in_cart = existing['quantity'] if existing else 0
            available_to_add = listing['quantity'] - in_cart
            take = min(remaining_to_fill, available_to_add)

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
                remaining_to_fill -= take
                total_refilled += take

        refill_log[bucket_id] = {
            'lost': total_lost,
            'refilled': total_refilled,
            'missing': total_lost - total_refilled
        }

    conn.commit()
    return refill_log

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
                listings.pricing_mode,
                listings.spot_premium,
                listings.floor_price,
                listings.pricing_metal,
                listings.seller_id,
                listings.photo_filename,
                lp.file_path,
                listings.graded,
                listings.grading_service,
                users.username AS seller_username,
                categories.id AS category_id,
                categories.metal,
                categories.product_line,
                categories.product_type,
                categories.weight,
                categories.mint,
                categories.year,
                categories.finish,
                categories.grade,
                categories.purity,
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
            JOIN listings   ON cart.listing_id = listings.id
            JOIN categories ON listings.category_id = categories.id
            JOIN users      ON listings.seller_id = users.id
            LEFT JOIN listing_photos AS lp ON lp.listing_id = listings.id
            WHERE cart.user_id = ?
              AND listings.active = 1
              AND listings.quantity > 0
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
                listings.pricing_mode,
                listings.spot_premium,
                listings.floor_price,
                listings.pricing_metal,
                listings.seller_id,
                listings.photo_filename,
                lp.file_path,
                listings.graded,
                listings.grading_service,
                users.username AS seller_username,
                categories.id AS category_id,
                categories.metal,
                categories.product_line,
                categories.product_type,
                categories.weight,
                categories.mint,
                categories.year,
                categories.finish,
                categories.grade,
                categories.purity,
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
            JOIN users      ON listings.seller_id = users.id
            LEFT JOIN listing_photos AS lp ON lp.listing_id = listings.id
            WHERE listings.id IN ({placeholders})
              AND listings.active = 1
              AND listings.quantity > 0
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
                listings.pricing_mode,
                listings.spot_premium,
                listings.floor_price,
                listings.pricing_metal,
                listings.seller_id,
                listings.graded,
                listings.grading_service,
                users.username AS seller_username,
                categories.id AS category_id,
                categories.metal,
                categories.product_line,
                categories.product_type,
                categories.weight,
                categories.purity,
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
              AND listings.active = 1
              AND listings.quantity > 0
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
                listings.pricing_mode,
                listings.spot_premium,
                listings.floor_price,
                listings.pricing_metal,
                listings.seller_id,
                listings.graded,
                listings.grading_service,
                users.username AS seller_username,
                categories.id AS category_id,
                categories.metal,
                categories.product_line,
                categories.product_type,
                categories.weight,
                categories.purity,
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
              AND listings.active = 1
              AND listings.quantity > 0
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
            'grading_preference': row.get('grading_preference'),
            'graded': row.get('graded'),
            'grading_service': row.get('grading_service')
        })

        bucket['total_qty'] += qty
        bucket['total_price'] += line_total
        bucket['category'] = {
            'metal': row['metal'],
            'product_line': row['product_line'],
            'product_type': row['product_type'],
            'weight': row['weight'],
            'purity': row['purity'],
            'mint': row['mint'],
            'year': row['year'],
            'finish': row['finish'],
            'grade': row['grade']
        }

        cart_total += line_total

    # Add total available quantity for each bucket
    for cat_id, bucket in buckets.items():
        if bucket['total_qty'] > 0:
            bucket['avg_price'] = bucket['total_price'] / bucket['total_qty']

        # Get total available quantity for this category
        result = conn.execute('''
            SELECT SUM(quantity) as total_available
            FROM listings
            WHERE category_id = ? AND active = 1
        ''', (cat_id,)).fetchone()
        bucket['total_available'] = result['total_available'] if result and result['total_available'] else 0

    return dict(buckets), cart_total
