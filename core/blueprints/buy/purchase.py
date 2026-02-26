# core/blueprints/buy/purchase.py
"""
Purchase operations for the buy blueprint.

Routes:
- /purchase_from_bucket/<int:bucket_id> - Auto-fill bucket purchase (add to cart)
- /preview_buy/<int:bucket_id> - Preview purchase breakdown without creating orders

Heavy routes extracted to:
- direct_purchase.py: refresh_price_lock, direct_buy_item
"""

from flask import request, redirect, url_for, session, flash, jsonify
from database import get_db_connection
from services.pricing_service import get_effective_price
from config import GRADING_FEE_PER_UNIT

from . import buy_bp

# Import extracted module to register routes
from . import direct_purchase  # noqa: F401 - registers direct_buy and refresh_price_lock routes


@buy_bp.route('/purchase_from_bucket/<int:bucket_id>', methods=['POST'])
def auto_fill_bucket_purchase(bucket_id):
    quantity_to_buy = int(request.form['quantity_to_buy'])
    user_id = session.get('user_id')  # May be None for guests

    conn = get_db_connection()
    cursor = conn.cursor()

    # TPG (Third-Party Grading) service add-on
    third_party_grading = int(request.form.get('third_party_grading', 0))

    # Grading preference (buyer-selected: NONE, ANY, PCGS, NGC)
    grading_preference = (request.form.get('grading_preference', 'NONE') or 'NONE').strip()
    if grading_preference != 'NONE':
        third_party_grading = 1  # Grading pref implies TPG

    # Random Year mode and packaging filter
    random_year = request.form.get('random_year') == '1'
    packaging_filter = request.form.get('packaging_filter', '').strip()

    # Check if this is an AJAX request (needed for MAX_REACHED response)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    # --- Random Year aggregation for cart ---
    if random_year:
        # Get the current bucket's specs
        bucket_specs = cursor.execute('SELECT * FROM categories WHERE bucket_id = ? LIMIT 1', (bucket_id,)).fetchone()
        if bucket_specs:
            # Find all matching bucket_ids (same specs except year)
            matching_buckets = cursor.execute('''
                SELECT bucket_id FROM categories
                WHERE metal = ? AND product_type = ? AND weight = ? AND purity = ?
                  AND mint = ? AND finish = ? AND grade = ? AND product_line = ?
                  AND condition_category IS NOT DISTINCT FROM ?
                  AND series_variant IS NOT DISTINCT FROM ?
                  AND is_isolated = 0
            ''', (
                bucket_specs['metal'], bucket_specs['product_type'], bucket_specs['weight'], bucket_specs['purity'],
                bucket_specs['mint'], bucket_specs['finish'], bucket_specs['grade'], bucket_specs['product_line'],
                bucket_specs.get('condition_category'), bucket_specs.get('series_variant')
            )).fetchall()
            bucket_ids = [row['bucket_id'] for row in matching_buckets] if matching_buckets else [bucket_id]
        else:
            bucket_ids = [bucket_id]
        bucket_id_clause = f"c.bucket_id IN ({','.join('?' * len(bucket_ids))})"
    else:
        bucket_ids = [bucket_id]
        bucket_id_clause = "c.bucket_id = ?"

    # Build listings query with grading filters - JOIN with categories to query by bucket_id
    # Include pricing fields for effective price calculation
    # IMPORTANT: Include ALL listings (including user's own) to detect when they're skipped
    listings_query = f'''
        SELECT l.*, c.metal, c.weight, c.product_type, c.year
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE {bucket_id_clause} AND l.active = 1
    '''
    params = bucket_ids.copy()

    # Apply packaging filter if specified
    if packaging_filter:
        listings_query += ' AND l.packaging_type = ?'
        params.append(packaging_filter)

    listings_raw = cursor.execute(listings_query, params).fetchall()

    # Calculate effective prices for all listings
    listings_with_prices = []
    for listing in listings_raw:
        listing_dict = dict(listing)
        listing_dict['effective_price'] = get_effective_price(listing_dict)
        listings_with_prices.append(listing_dict)

    # Sort by effective price (cheapest first)
    listings_sorted = sorted(listings_with_prices, key=lambda x: x['effective_price'])

    # Separate user's listings from others
    user_listings = []
    other_listings = []

    for listing in listings_sorted:
        if user_id and listing['seller_id'] == user_id:
            user_listings.append(listing)
        else:
            other_listings.append(listing)

    print(f"[DEBUG] user_listings: {len(user_listings)}, other_listings: {len(other_listings)}")

    # Check if there are any non-user listings available
    if not other_listings:
        total_active = cursor.execute('''
            SELECT COUNT(*)
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE c.bucket_id = ? AND l.active = 1
        ''', (bucket_id,)).fetchone()[0]

        if total_active > 0:
            flash("You cannot add your own listings to your cart.", "error")
        else:
            flash("No listings available to fulfill your request.", "error")
        conn.close()
        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    # ===== MAX-REACHED CHECK =====
    # For non-random-year mode, check if user already holds all available stock for this bucket.
    # If so, block the add and return MAX_REACHED so the frontend can show the replace modal.
    if not random_year and is_ajax:
        available_qty = sum(l['quantity'] for l in other_listings)

        if user_id:
            in_cart_row = cursor.execute('''
                SELECT COALESCE(SUM(cart.quantity), 0) AS in_cart,
                       MAX(cart.grading_preference) AS current_grading
                FROM cart
                JOIN listings ON cart.listing_id = listings.id
                JOIN categories ON listings.category_id = categories.id
                WHERE cart.user_id = ? AND categories.bucket_id = ?
            ''', (user_id, bucket_id)).fetchone()
            in_cart_qty = in_cart_row['in_cart'] if in_cart_row else 0
            current_grading = in_cart_row['current_grading'] or 'NONE'
        else:
            guest_items = session.get('guest_cart', [])
            in_cart_qty = 0
            current_grading = 'NONE'
            if guest_items:
                listing_ids = [it['listing_id'] for it in guest_items]
                placeholders = ','.join('?' * len(listing_ids))
                bucket_rows = cursor.execute(
                    f'SELECT l.id AS listing_id, c.bucket_id FROM listings l '
                    f'JOIN categories c ON l.category_id = c.id WHERE l.id IN ({placeholders})',
                    listing_ids
                ).fetchall()
                bmap = {row['listing_id']: row['bucket_id'] for row in bucket_rows}
                for it in guest_items:
                    if bmap.get(it['listing_id']) == bucket_id:
                        in_cart_qty += it['quantity']
                        current_grading = it.get('grading_preference', 'NONE') or 'NONE'

        if available_qty > 0 and in_cart_qty >= available_qty:
            conn.close()
            return jsonify({
                'status': 'MAX_REACHED',
                'success': False,
                'message': 'You already have the maximum available quantity from this bucket in your cart.',
                'in_cart_qty': in_cart_qty,
                'available_qty': available_qty,
                'in_cart_grading': current_grading,
                'new_grading': grading_preference,
            })
    # ===== END MAX-REACHED CHECK =====

    # Fill cart from other sellers' listings only
    total_filled = 0
    guest_cart = session.get('guest_cart', [])
    user_listings_skipped = False  # Track if we skipped any user listings
    selected_prices = []  # Track prices of listings we actually selected

    print(f"[DEBUG] Starting to fill cart. user_id={user_id}, quantity_to_buy={quantity_to_buy}")

    for listing in other_listings:
        if total_filled >= quantity_to_buy:
            break

        available = listing['quantity']
        to_add = min(available, quantity_to_buy - total_filled)

        # Track the price of this listing we're selecting
        selected_prices.append(listing['effective_price'])

        if user_id:
            # Authenticated user: update DB cart
            existing = cursor.execute('''
                SELECT quantity FROM cart
                WHERE user_id = ? AND listing_id = ?
            ''', (user_id, listing['id'])).fetchone()

            if existing:
                new_qty = existing['quantity'] + to_add
                cursor.execute('''
                    UPDATE cart SET quantity = ?, third_party_grading_requested = ?, grading_preference = ?
                    WHERE user_id = ? AND listing_id = ?
                ''', (new_qty, third_party_grading, grading_preference, user_id, listing['id']))
                print(f"[DEBUG] Updated cart: user_id={user_id}, listing_id={listing['id']}, new_qty={new_qty}")
            else:
                cursor.execute('''
                    INSERT INTO cart (user_id, listing_id, quantity, third_party_grading_requested, grading_preference)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, listing['id'], to_add, third_party_grading, grading_preference))
                print(f"[DEBUG] Inserted into cart: user_id={user_id}, listing_id={listing['id']}, quantity={to_add}")
        else:
            # Guest user: use session cart
            for item in guest_cart:
                if item['listing_id'] == listing['id']:
                    item['quantity'] += to_add
                    item['third_party_grading_requested'] = third_party_grading
                    item['grading_preference'] = grading_preference
                    break
            else:
                guest_cart.append({
                    'listing_id': listing['id'],
                    'quantity': to_add,
                    'third_party_grading_requested': third_party_grading,
                    'grading_preference': grading_preference,
                })

        total_filled += to_add

    # After filling, check if we skipped any competitive user listings
    if user_listings and selected_prices and total_filled > 0:
        # If any user listing price is <= the highest price we selected, it was competitive
        max_selected_price = max(selected_prices)
        for user_listing in user_listings:
            if user_listing['effective_price'] <= max_selected_price:
                user_listings_skipped = True
                print(f"[DEBUG] User listing at ${user_listing['effective_price']:.2f} was skipped (would have been selected)")
                break

    if not user_id:
        session['guest_cart'] = guest_cart

    conn.commit()
    conn.close()

    if total_filled == 0:
        flash("No listings available to fulfill your request.", "error")
        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    if total_filled < quantity_to_buy:
        flash(f"Only {total_filled} units could be added to your cart due to limited stock.", "warning")

    if is_ajax:
        # Return JSON for AJAX requests (so modal can be shown before redirect)
        print(f"[DEBUG] AJAX request. user_listings_skipped={user_listings_skipped}, total_filled={total_filled}")
        return jsonify({
            'status': 'OK',
            'success': True,
            'user_listings_skipped': user_listings_skipped and total_filled > 0,
            'total_filled': total_filled,
            'message': f'{total_filled} items added to cart'
        })
    else:
        # Traditional redirect for non-AJAX requests (backward compatibility)
        if user_listings_skipped and total_filled > 0:
            session['show_own_listings_skipped_modal'] = True
            print(f"[DEBUG] User listings were skipped. Setting session flag. User ID: {user_id}")
        else:
            print(f"[DEBUG] No user listings skipped. user_listings_skipped={user_listings_skipped}, total_filled={total_filled}")

        return redirect(url_for('buy.view_cart'))  # Sends user directly to cart


@buy_bp.route('/replace_cart_grading/<int:bucket_id>', methods=['POST'])
def replace_cart_grading(bucket_id):
    """
    Replace the grading_preference for existing cart items under this bucket.
    Called when user chooses "Replace" from the MAX_REACHED modal.
    Supports both DB-backed (logged-in) and session (guest) carts.
    """
    user_id = session.get('user_id')
    data = request.get_json(silent=True) or {}
    new_grading = (data.get('grading_preference') or request.form.get('grading_preference', 'NONE') or 'NONE').strip()
    new_tpg = 0 if new_grading == 'NONE' else 1

    conn = get_db_connection()
    cursor = conn.cursor()

    if user_id:
        cursor.execute('''
            UPDATE cart SET grading_preference = ?, third_party_grading_requested = ?
            WHERE user_id = ? AND listing_id IN (
                SELECT l.id FROM listings l
                JOIN categories c ON l.category_id = c.id
                WHERE c.bucket_id = ?
            )
        ''', (new_grading, new_tpg, user_id, bucket_id))
        conn.commit()
    else:
        guest_cart = session.get('guest_cart', [])
        if guest_cart:
            listing_ids = [it['listing_id'] for it in guest_cart]
            placeholders = ','.join('?' * len(listing_ids))
            bucket_rows = cursor.execute(
                f'SELECT l.id AS listing_id, c.bucket_id FROM listings l '
                f'JOIN categories c ON l.category_id = c.id WHERE l.id IN ({placeholders})',
                listing_ids
            ).fetchall()
            bmap = {row['listing_id']: row['bucket_id'] for row in bucket_rows}
            updated = False
            for it in guest_cart:
                if bmap.get(it['listing_id']) == bucket_id:
                    it['grading_preference'] = new_grading
                    it['third_party_grading_requested'] = new_tpg
                    updated = True
            if updated:
                session['guest_cart'] = guest_cart
                session.modified = True

    conn.close()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'OK', 'success': True, 'grading_preference': new_grading})

    flash('Cart updated with new grading preference.', 'success')
    return redirect(url_for('buy.view_cart'))


@buy_bp.route('/preview_buy/<int:bucket_id>', methods=['POST'])
def preview_buy(bucket_id):
    """
    Preview purchase breakdown without creating orders.
    Returns the actual total and item breakdown for confirmation modal.
    For premium-to-spot listings, creates price locks.
    Supports Random Year mode for multi-year aggregation.
    """
    from services.pricing_service import create_price_lock
    user_id = session.get('user_id')

    try:
        # Get form data
        quantity = int(request.form.get('quantity', 1))
        random_year = request.form.get('random_year') == '1'
        third_party_grading = request.form.get('third_party_grading') == '1'

        # Get packaging filters (multi-select)
        packaging_styles = request.form.getlist('packaging_styles')
        packaging_styles = [ps.strip() for ps in packaging_styles if ps.strip()]

        conn = get_db_connection()
        cursor = conn.cursor()

        # Get bucket_ids to query based on Random Year mode
        if random_year:
            # Get the base bucket info
            bucket = conn.execute('SELECT * FROM categories WHERE bucket_id = ? LIMIT 1', (bucket_id,)).fetchone()

            if not bucket:
                conn.close()
                return jsonify(success=False, message='Item not found.'), 404

            # Find all matching buckets (same specs except year)
            matching_buckets_query = '''
                SELECT bucket_id FROM categories
                WHERE metal = ? AND product_type = ? AND weight = ? AND purity = ?
                  AND mint = ? AND finish = ? AND grade = ? AND product_line = ?
                  AND condition_category IS NOT DISTINCT FROM ?
                  AND series_variant IS NOT DISTINCT FROM ?
                  AND is_isolated = 0
            '''
            matching_buckets = conn.execute(matching_buckets_query, (
                bucket['metal'], bucket['product_type'], bucket['weight'], bucket['purity'],
                bucket['mint'], bucket['finish'], bucket['grade'], bucket['product_line'],
                bucket['condition_category'], bucket['series_variant']
            )).fetchall()

            bucket_ids = [row['bucket_id'] for row in matching_buckets] if matching_buckets else [bucket_id]
            bucket_id_clause = f"c.bucket_id IN ({','.join('?' * len(bucket_ids))})"
            params = bucket_ids.copy()
        else:
            bucket_ids = [bucket_id]
            bucket_id_clause = "c.bucket_id = ?"
            params = [bucket_id]

        # Build listings query (include pricing fields for effective price calculation)
        listings_query = f'''
            SELECT l.*, c.metal, c.weight, c.product_type, c.year
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE {bucket_id_clause} AND l.active = 1 AND l.quantity > 0
        '''

        # Exclude user's own listings
        if user_id:
            listings_query += ' AND l.seller_id != ?'
            params.append(user_id)

        # Apply packaging filters if specified
        if packaging_styles:
            packaging_placeholders = ','.join('?' * len(packaging_styles))
            listings_query += f' AND l.packaging_type IN ({packaging_placeholders})'
            params.extend(packaging_styles)

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

        # Calculate grading fees if requested
        grading_fee_per_unit = GRADING_FEE_PER_UNIT if third_party_grading else 0
        grading_fee_total = grading_fee_per_unit * total_filled
        grand_total = total_cost + grading_fee_total

        # Return preview data with price lock info and grading fees
        response_data = {
            'success': True,
            'total_quantity': total_filled,
            'total_cost': total_cost,
            'average_price': total_cost / total_filled if total_filled > 0 else 0,
            'breakdown': breakdown,
            'can_fill_completely': total_filled >= quantity,
            'has_price_lock': has_premium_to_spot and len(price_locks) > 0,
            'price_locks': price_locks,
            'lock_expires_at': lock_expires_at,
            'third_party_grading': third_party_grading,
            'grading_fee_per_unit': grading_fee_per_unit,
            'grading_fee_total': grading_fee_total,
            'grand_total': grand_total
        }

        return jsonify(response_data)

    except Exception as e:
        print(f"Preview buy error: {e}")
        return jsonify(success=False, message=str(e)), 500
