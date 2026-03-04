# core/blueprints/buy/direct_purchase.py
"""
Direct purchase operations for the buy blueprint.

Routes:
- /refresh_price_lock/<int:bucket_id> - Refresh price locks when timer expires
- /direct_buy/<int:bucket_id> - Directly create an order from bucket purchase

Extracted from purchase.py during refactor - NO BEHAVIOR CHANGE.
"""

from flask import request, session, jsonify
from datetime import datetime
from database import get_db_connection
from services.pricing_service import get_effective_price, create_price_lock
from services.notification_service import notify_listing_sold, notify_order_confirmed
from services.checkout_spot_service import (
    check_spot_map_freshness, SpotExpiredError, SpotUnavailableError
)
from config import GRADING_FEE_PER_UNIT, GRADING_SERVICE_DEFAULT, GRADING_STATUS_NOT_REQUESTED, GRADING_STATUS_PENDING_SELLER_SHIP

from . import buy_bp


@buy_bp.route('/refresh_price_lock/<int:bucket_id>', methods=['POST'])
def refresh_price_lock(bucket_id):
    """
    Refresh price locks when timer expires.
    Creates new price locks and returns updated prices.
    """
    user_id = session.get('user_id')

    if not user_id:
        return jsonify(success=False, message='You must be logged in.'), 401

    try:
        # Get form data (same as preview_buy)
        quantity = int(request.form.get('quantity', 1))

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
        random_year = request.form.get('random_year') == '1'
        third_party_grading = request.form.get('third_party_grading') == '1'

        # Get packaging filters (multi-select)
        packaging_styles = request.form.getlist('packaging_styles')
        packaging_styles = [ps.strip() for ps in packaging_styles if ps.strip()]

        # Get recipient name (source of truth for Buyer Name on Sold tiles)
        recipient_first = request.form.get('recipient_first', '').strip()
        recipient_last = request.form.get('recipient_last', '').strip()

        # Get selected address ID from form
        address_id = request.form.get('address_id')
        if not address_id:
            return jsonify(success=False, message='Please select a delivery address.'), 400

        # Get price lock IDs (comma-separated string from frontend)
        price_lock_ids_str = request.form.get('price_lock_ids', '')
        price_lock_ids = [int(id.strip()) for id in price_lock_ids_str.split(',') if id.strip().isdigit()]

        # Get user's selected shipping address
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

        # Get the selected address (verify it belongs to the user)
        address_row = cursor.execute(
            'SELECT street, street_line2, city, state, zip_code FROM addresses WHERE id = ? AND user_id = ?',
            (address_id, user_id)
        ).fetchone()

        if not address_row:
            conn.close()
            return jsonify(success=False, message='Selected address not found or does not belong to you.'), 400

        # Format shipping address with all components, using bullet as separator for Line 2
        street_line2 = address_row['street_line2'] or ''
        if street_line2.strip():
            shipping_address = f"{address_row['street']} • {street_line2} • {address_row['city']}, {address_row['state']} {address_row['zip_code']}"
        else:
            shipping_address = f"{address_row['street']} • {address_row['city']}, {address_row['state']} {address_row['zip_code']}"

        # Build structured delivery address for frontend (do this while connection is still open)
        delivery_address = {
            'line1': address_row['street'],
            'line2': address_row['street_line2'] or '',
            'city': address_row['city'],
            'state': address_row['state'],
            'zip': address_row['zip_code']
        }

        # Load price locks if provided
        price_lock_map = {}  # listing_id -> locked_price
        if price_lock_ids:
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

        # Build listings query (include pricing fields)
        # IMPORTANT: Include ALL listings (including user's own) to detect when they're skipped
        listings_query = f'''
            SELECT l.*, c.metal, c.weight, c.product_type, c.year
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE {bucket_id_clause} AND l.active = 1 AND l.quantity > 0
        '''

        # Apply packaging filters if specified
        if packaging_styles:
            packaging_placeholders = ','.join('?' * len(packaging_styles))
            listings_query += f' AND l.packaging_type IN ({packaging_placeholders})'
            params.extend(packaging_styles)

        listings_raw = cursor.execute(listings_query, params).fetchall()

        if not listings_raw:
            conn.close()
            return jsonify(success=False, message='No matching listings available for purchase.'), 400

        # ── Modal-first spot freshness check ─────────────────────────────────
        # Collect metals needed for premium_to_spot listings; check freshness
        # WITHOUT auto-refresh (check_spot_map_freshness).  If stale → 409
        # SPOT_EXPIRED so the frontend can show the recalculate prompt.
        spot_metals = {
            (dict(l).get('pricing_metal') or dict(l).get('metal') or '').lower()
            for l in listings_raw
            if dict(l).get('pricing_mode') == 'premium_to_spot'
        }
        spot_prices_dict = {}  # {metal: price_usd}
        if spot_metals:
            try:
                spot_map = check_spot_map_freshness(spot_metals)
                spot_prices_dict = {m: info['price_usd'] for m, info in spot_map.items() if info}
            except SpotExpiredError:
                conn.close()
                return jsonify(
                    success=False,
                    error_code='SPOT_EXPIRED',
                    message=SpotExpiredError.USER_MESSAGE,
                ), 409
            except SpotUnavailableError:
                conn.close()
                return jsonify(
                    success=False,
                    error_code='SPOT_UNAVAILABLE',
                    message=SpotUnavailableError.USER_MESSAGE,
                ), 503

        # Calculate effective prices for ALL listings
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
                listing_dict['effective_price'] = get_effective_price(
                    listing_dict, spot_prices=spot_prices_dict or None
                )
                listing_dict['price_was_locked'] = False

            listings_with_prices.append(listing_dict)

        # Sort ALL listings by effective price
        listings_sorted = sorted(listings_with_prices, key=lambda x: (x['effective_price'], x['id']))

        # Separate user's listings from others
        user_listings = []
        other_listings = []

        for listing in listings_sorted:
            if listing['seller_id'] == user_id:
                user_listings.append(listing)
            else:
                other_listings.append(listing)

        # Use only other sellers' listings for filling the order
        listings = other_listings

        # Fill order from listings (group by seller)
        seller_fills = {}  # seller_id -> list of {listing_id, quantity, price_each}
        total_filled = 0
        selected_prices = []

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
                'graded': listing.get('graded', 0),
                'grading_service': listing.get('grading_service')
            })

            selected_prices.append(listing['effective_price'])
            total_filled += fill_qty

        if total_filled == 0:
            conn.close()
            return jsonify(success=False, message='No items could be filled from available listings.'), 400

        # Check if we skipped any competitive user listings
        user_listings_skipped = False
        if user_listings and selected_prices and len(selected_prices) > 0:
            # If any user listing price is <= the highest price we selected, it was competitive
            max_selected_price = max(selected_prices)
            for user_listing in user_listings:
                if user_listing['effective_price'] <= max_selected_price:
                    user_listings_skipped = True
                    print(f"[DIRECT_BUY] User listing at ${user_listing['effective_price']:.2f} was skipped")
                    break

        # Get category/bucket info for notifications
        bucket_row = cursor.execute('SELECT * FROM categories WHERE bucket_id = ? LIMIT 1', (bucket_id,)).fetchone()
        bucket_dict = dict(bucket_row) if bucket_row else {}

        # Update year display for Random Year purchases
        if random_year:
            bucket_dict['year'] = 'Random'

        # Calculate grading fees if requested
        grading_fee_per_unit = GRADING_FEE_PER_UNIT if third_party_grading else 0

        # Collect notification data (will send after commit to avoid database locking)
        notifications_to_send = []

        # Create one order per seller
        orders_created = []
        for seller_id, items in seller_fills.items():
            # Calculate total for items
            items_total = sum(item['quantity'] * item['price_each'] for item in items)

            # Calculate grading fees for this order
            total_quantity_in_order = sum(item['quantity'] for item in items)
            grading_fee_total = grading_fee_per_unit * total_quantity_in_order

            # Grand total includes item cost + grading fees
            total_price = items_total + grading_fee_total

            # Create order
            cursor.execute('''
                INSERT INTO orders (buyer_id, total_price, shipping_address, status, created_at,
                                   recipient_first_name, recipient_last_name)
                VALUES (?, ?, ?, 'Pending Shipment', datetime('now'), ?, ?)
            ''', (user_id, total_price, shipping_address, recipient_first, recipient_last))

            order_id = cursor.lastrowid

            # Create order_items and notify seller for each listing
            for item in items:
                # Calculate grading fee for this line item
                item_grading_fee = grading_fee_per_unit * item['quantity']

                # Determine grading status
                grading_status = GRADING_STATUS_PENDING_SELLER_SHIP if third_party_grading else GRADING_STATUS_NOT_REQUESTED

                cursor.execute('''
                    INSERT INTO order_items (order_id, listing_id, quantity, price_each,
                                           third_party_grading_requested, grading_fee_charged,
                                           grading_service, grading_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (order_id, item['listing_id'], item['quantity'], item['price_each'],
                      1 if third_party_grading else 0, item_grading_fee,
                      GRADING_SERVICE_DEFAULT if third_party_grading else None, grading_status))

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
                'items_total': items_total,
                'grading_fee_total': grading_fee_total,
                'quantity': sum(i['quantity'] for i in items),
                'price_each': items[0]['price_each'],  # First item price for display
                'graded': items[0].get('graded', 0),  # Grading status from first item (legacy field)
                'grading_service': items[0].get('grading_service'),  # Grading service from first item (legacy field)
                'third_party_grading': third_party_grading,
                'grading_fee_per_unit': grading_fee_per_unit
            })

        conn.commit()
        conn.close()

        # Send notifications AFTER commit (avoids database locking)
        for notif_data in notifications_to_send:
            try:
                notify_listing_sold(**notif_data)
            except Exception as notify_error:
                print(f"[ERROR] Failed to notify seller {notif_data['seller_id']}: {notify_error}")

        # Send buyer notification for each order created
        for order in orders_created:
            try:
                # Get item description from bucket
                item_desc_parts = []
                if bucket_dict.get('metal'):
                    item_desc_parts.append(bucket_dict['metal'])
                if bucket_dict.get('product_type'):
                    item_desc_parts.append(bucket_dict['product_type'])
                if bucket_dict.get('weight'):
                    item_desc_parts.append(bucket_dict['weight'])
                item_description = ' '.join(item_desc_parts) if item_desc_parts else 'Item'

                notify_order_confirmed(
                    buyer_id=user_id,
                    order_id=order['order_id'],
                    item_description=item_description,
                    quantity_purchased=order['quantity'],
                    price_per_unit=order['price_each'],
                    total_amount=order['total_price']
                )
            except Exception as notify_error:
                print(f"[ERROR] Failed to notify buyer for order {order['order_id']}: {notify_error}")

        # Calculate overall grading fee
        overall_grading_fee_total = grading_fee_per_unit * total_filled

        # Build success response with order details
        return jsonify(
            success=True,
            message=f'Order created successfully! {total_filled} items purchased.',
            orders=orders_created,
            total_quantity=total_filled,
            bucket=bucket_dict,
            shipping_address=shipping_address,
            delivery_address=delivery_address,
            user_listings_skipped=user_listings_skipped,
            third_party_grading=third_party_grading,
            grading_fee_per_unit=grading_fee_per_unit,
            grading_fee_total=overall_grading_fee_total
        )

    except ValueError as e:
        return jsonify(success=False, message=f'Invalid input: {str(e)}'), 400
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return jsonify(success=False, message=f'Error creating order: {str(e)}'), 500
