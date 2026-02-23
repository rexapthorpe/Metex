"""
Checkout Routes

Checkout routes: checkout page, order confirmation.
"""

from flask import render_template, redirect, url_for, request, session, flash, jsonify
from database import get_db_connection
from services.order_service import create_order
from utils.cart_utils import get_cart_items
from services.notification_service import notify_listing_sold, notify_order_confirmed
from services.pricing_service import get_effective_price, create_price_lock
from utils.auth_utils import frozen_check

from . import checkout_bp


def _create_ledger_for_order(buyer_id, order_id, cart_data, conn):
    """
    Create ledger records for an order.
    This is a minimal integration point that builds a cart_snapshot from cart_data
    and calls the ledger service.

    Args:
        buyer_id: The buyer's user ID
        order_id: The created order ID
        cart_data: List of dicts with listing_id, quantity, price_each
        conn: Database connection for fetching seller_ids
    """
    try:
        from services.ledger_service import LedgerService, init_ledger_tables

        # Ensure ledger tables exist (idempotent)
        init_ledger_tables()

        # Build cart_snapshot with seller_ids
        cart_snapshot = []
        for item in cart_data:
            # Get seller_id from the listing
            listing = conn.execute(
                'SELECT seller_id FROM listings WHERE id = ?',
                (item['listing_id'],)
            ).fetchone()

            if listing:
                cart_snapshot.append({
                    'seller_id': listing['seller_id'],
                    'listing_id': item['listing_id'],
                    'quantity': item['quantity'],
                    'unit_price': item['price_each']
                    # fee_type and fee_value will use defaults from ledger service
                })

        if cart_snapshot:
            ledger_id = LedgerService.create_order_ledger_from_cart(
                buyer_id=buyer_id,
                cart_snapshot=cart_snapshot,
                payment_method=None,  # Stripe not integrated yet
                order_id=order_id
            )
            print(f"[CHECKOUT] Created ledger record {ledger_id} for order {order_id}")
            return ledger_id
    except Exception as e:
        # Don't fail checkout if ledger creation fails - log and continue
        print(f"[CHECKOUT] Warning: Failed to create ledger for order {order_id}: {e}")
        import traceback
        traceback.print_exc()
    return None


@checkout_bp.route('/checkout', methods=['GET', 'POST'])
@frozen_check
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    conn = get_db_connection()

    if request.method == 'POST':
        # Check for bucket purchase first (before AJAX cart checkout)
        bucket_id = request.form.get('bucket_id')
        quantity = int(request.form.get('quantity') or 1)  # Handle empty string

        if bucket_id:
            # User is buying directly from a bucket (not from cart)
            bucket_id = int(bucket_id)
            random_year = request.form.get('random_year') == '1'

            # Initialize user_listings_skipped early (before any potential early returns)
            user_listings_skipped = False

            # Get bucket_ids to query based on Random Year mode
            if random_year:
                # Get the base bucket info
                bucket = conn.execute('SELECT * FROM categories WHERE bucket_id = ? LIMIT 1', (bucket_id,)).fetchone()

                if not bucket:
                    flash("Item not found.", "error")
                    conn.close()
                    return redirect(url_for('buy.buy'))

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

            # Get listings with pricing fields for effective price calculation
            # IMPORTANT: Include ALL listings (including user's own) to detect when they're skipped
            query = f'''
                SELECT l.id, l.quantity, l.price_per_coin, l.pricing_mode,
                       l.spot_premium, l.floor_price, l.pricing_metal, l.seller_id,
                       c.metal, c.weight, c.product_type, c.year
                FROM listings l
                JOIN categories c ON l.category_id = c.id
                WHERE {bucket_id_clause} AND l.active = 1 AND l.quantity > 0
            '''

            listings_raw = conn.execute(query, params).fetchall()

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
                if listing['seller_id'] == user_id:
                    user_listings.append(listing)
                else:
                    other_listings.append(listing)

            # Try to fill from other sellers' listings only (skip user's own listings)
            selected = []
            selected_prices = []
            remaining = quantity

            for listing in other_listings:
                if remaining <= 0:
                    break
                take = min(listing['quantity'], remaining)
                selected.append({
                    'listing_id': listing['id'],
                    'quantity': take,
                    'price_each': listing['effective_price']
                })
                selected_prices.append(listing['effective_price'])
                remaining -= take

            # Check if we skipped any competitive user listings
            if user_listings and selected_prices and len(selected) > 0:
                # If any user listing price is <= the highest price we selected, it was competitive
                max_selected_price = max(selected_prices)
                for user_listing in user_listings:
                    if user_listing['effective_price'] <= max_selected_price:
                        user_listings_skipped = True
                        print(f"[CHECKOUT] User listing at ${user_listing['effective_price']:.2f} was skipped")
                        break

            if remaining > 0:
                flash("Not enough inventory to fulfill your request.")
                conn.close()
                return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

            # Check if this is an AJAX request (from Buy Item button)
            is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

            if is_ajax:
                # Return JSON for AJAX requests (so modal can be shown before redirect)
                print(f"[CHECKOUT] AJAX request. user_listings_skipped={user_listings_skipped}, items_selected={len(selected)}")
                # Store selection in session for when user is redirected
                session['checkout_items'] = selected
                conn.close()
                return jsonify({
                    'success': True,
                    'user_listings_skipped': user_listings_skipped and len(selected) > 0,
                    'items_selected': len(selected),
                    'message': f'{len(selected)} item(s) selected for checkout'
                })
            else:
                # Traditional redirect for non-AJAX requests (backward compatibility)
                if user_listings_skipped and len(selected) > 0:
                    session['show_own_listings_skipped_modal'] = True
                    print(f"[CHECKOUT] User listings were skipped. Setting session flag. User ID: {user_id}")

                # Keep the selection in session for the GET render and final POST
                session['checkout_items'] = selected
                conn.close()
                return redirect(url_for('checkout.checkout'))

        else:
            # Not a bucket purchase - handle cart checkout
            # Check if this is an AJAX request (from checkout modal)
            is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

            # For AJAX cart checkout requests, expect JSON data
            if is_ajax:
                try:
                    data = request.get_json()
                    shipping_address = data.get('shipping_address', 'Default Address')

                    # Get cart items with pricing fields for effective price calculation
                    cart_items = conn.execute('''
                        SELECT cart.id, cart.quantity, cart.listing_id,
                               listings.price_per_coin, listings.pricing_mode,
                               listings.spot_premium, listings.floor_price, listings.pricing_metal,
                               categories.metal, categories.weight, categories.product_type
                        FROM cart
                        JOIN listings ON cart.listing_id = listings.id
                        JOIN categories ON listings.category_id = categories.id
                        WHERE cart.user_id = ?
                          AND listings.active = 1
                          AND listings.quantity > 0
                    ''', (user_id,)).fetchall()

                    if not cart_items:
                        conn.close()
                        return jsonify({
                            'success': False,
                            'message': 'Your cart is empty or items are no longer available'
                        })

                    # Calculate effective prices for cart items
                    cart_data = []
                    for item in cart_items:
                        item_dict = dict(item)
                        effective_price = get_effective_price(item_dict)
                        cart_data.append({
                            'listing_id': item['listing_id'],
                            'quantity': item['quantity'],
                            'price_each': effective_price
                        })

                    # Create order
                    order_id = create_order(user_id, cart_data, shipping_address)

                    # Create ledger records for this order
                    _create_ledger_for_order(user_id, order_id, cart_data, conn)

                    # Calculate totals for response
                    total_items = sum(item['quantity'] for item in cart_data)
                    order_total = sum(item['quantity'] * item['price_each'] for item in cart_data)

                    # Collect notification data (will send after commit to avoid database locking)
                    notifications_to_send = []

                    # Decrement inventory
                    for item in cart_data:
                        listing_info = conn.execute('''
                            SELECT listings.quantity, listings.seller_id, listings.category_id,
                                   categories.metal, categories.product_type
                            FROM listings
                            JOIN categories ON listings.category_id = categories.id
                            WHERE listings.id = ?
                        ''', (item['listing_id'],)).fetchone()

                        if listing_info:
                            old_quantity = listing_info['quantity']
                            new_quantity = old_quantity - item['quantity']

                            # Update inventory
                            if new_quantity <= 0:
                                conn.execute('UPDATE listings SET quantity = 0, active = 0 WHERE id = ?', (item['listing_id'],))
                            else:
                                conn.execute('UPDATE listings SET quantity = ? WHERE id = ?', (new_quantity, item['listing_id']))

                            # Collect notification data (will send after commit)
                            item_description = f"{listing_info['metal']} {listing_info['product_type']}"
                            is_partial = new_quantity > 0
                            notifications_to_send.append({
                                'seller_id': listing_info['seller_id'],
                                'order_id': order_id,
                                'listing_id': item['listing_id'],
                                'item_description': item_description,
                                'quantity_sold': item['quantity'],
                                'price_per_unit': item['price_each'],
                                'total_amount': item['quantity'] * item['price_each'],
                                'shipping_address': shipping_address,
                                'is_partial': is_partial,
                                'remaining_quantity': new_quantity if is_partial else 0
                            })

                    # Clear cart
                    conn.execute('DELETE FROM cart WHERE user_id = ?', (user_id,))
                    conn.commit()
                    conn.close()

                    # Send notifications AFTER commit (avoids database locking)
                    for notif_data in notifications_to_send:
                        try:
                            notify_listing_sold(**notif_data)
                        except Exception as e:
                            print(f"[CHECKOUT] Failed to send seller notification: {e}")

                    # Send buyer notification
                    try:
                        # Calculate aggregate item description for the buyer
                        item_descriptions = []
                        for notif_data in notifications_to_send:
                            item_descriptions.append(notif_data['item_description'])

                        # Use first item description or "Multiple items" if more than one type
                        if len(set(item_descriptions)) == 1:
                            buyer_item_description = item_descriptions[0]
                        else:
                            buyer_item_description = f"{len(set(item_descriptions))} different items"

                        notify_order_confirmed(
                            buyer_id=user_id,
                            order_id=order_id,
                            item_description=buyer_item_description,
                            quantity_purchased=total_items,
                            price_per_unit=order_total / total_items if total_items > 0 else 0,
                            total_amount=order_total
                        )
                    except Exception as e:
                        print(f"[CHECKOUT] Failed to send buyer notification: {e}")

                    # Return JSON response
                    return jsonify({
                        'success': True,
                        'order_id': order_id,
                        'total_items': total_items,
                        'order_total': round(order_total, 2)
                    })

                except Exception as e:
                    conn.close()
                    return jsonify({
                        'success': False,
                        'message': f'Error processing order: {str(e)}'
                    }), 500

            # Final submit: create the order from either session-selected items or the cart
            shipping_address = request.form.get('shipping_address')
            recipient_first = request.form.get('recipient_first_name', '')
            recipient_last = request.form.get('recipient_last_name', '')

            # Prefer direct-bucket selection if present
            session_items = session.pop('checkout_items', None)
            if session_items:
                cart_data = [{
                    'listing_id': item['listing_id'],
                    'quantity': item['quantity'],
                    'price_each': item['price_each']
                } for item in session_items]
            else:
                # Fallback to the user's cart - get with pricing fields
                cart_items = conn.execute('''
                    SELECT cart.id, cart.quantity, cart.listing_id,
                           listings.price_per_coin, listings.pricing_mode,
                           listings.spot_premium, listings.floor_price, listings.pricing_metal,
                           categories.metal, categories.weight, categories.product_type
                    FROM cart
                    JOIN listings ON cart.listing_id = listings.id
                    JOIN categories ON listings.category_id = categories.id
                    WHERE cart.user_id = ?
                      AND listings.active = 1
                      AND listings.quantity > 0
                ''', (user_id,)).fetchall()

                # Calculate effective prices
                cart_data = []
                for item in cart_items:
                    item_dict = dict(item)
                    effective_price = get_effective_price(item_dict)
                    cart_data.append({
                        'listing_id': item['listing_id'],
                        'quantity': item['quantity'],
                        'price_each': effective_price
                    })

            if not cart_data:
                flash("Your cart is empty or items are no longer available.")
                conn.close()
                return redirect(url_for('buy.view_cart'))

            # Create the order record (service inserts into orders & order_items)
            order_id = create_order(user_id, cart_data, shipping_address, recipient_first, recipient_last)

            # Create ledger records for this order
            _create_ledger_for_order(user_id, order_id, cart_data, conn)

            # Decrement inventory and deactivate when needed + Send notifications to sellers
            for item in cart_data:
                # Get listing details including seller info and category
                listing_info = conn.execute('''
                    SELECT listings.quantity, listings.seller_id, listings.category_id,
                           categories.metal, categories.product_type
                    FROM listings
                    JOIN categories ON listings.category_id = categories.id
                    WHERE listings.id = ?
                ''', (item['listing_id'],)).fetchone()

                if listing_info:
                    old_quantity = listing_info['quantity']
                    new_quantity = old_quantity - item['quantity']

                    # Update inventory
                    if new_quantity <= 0:
                        conn.execute('UPDATE listings SET quantity = 0, active = 0 WHERE id = ?', (item['listing_id'],))
                    else:
                        conn.execute('UPDATE listings SET quantity = ? WHERE id = ?', (new_quantity, item['listing_id']))

                    # Send notification to seller
                    try:
                        item_description = f"{listing_info['metal']} {listing_info['product_type']}"
                        is_partial = new_quantity > 0

                        notify_listing_sold(
                            seller_id=listing_info['seller_id'],
                            order_id=order_id,
                            listing_id=item['listing_id'],
                            item_description=item_description,
                            quantity_sold=item['quantity'],
                            price_per_unit=item['price_each'],
                            total_amount=item['quantity'] * item['price_each'],
                            shipping_address=shipping_address,
                            is_partial=is_partial,
                            remaining_quantity=new_quantity if is_partial else 0
                        )
                    except Exception as e:
                        print(f"[CHECKOUT] Failed to send notification to seller: {e}")

            # Clear cart regardless (safe if buying from bucket)
            conn.execute('DELETE FROM cart WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()

            # Send buyer notification AFTER commit
            try:
                # Calculate totals
                total_items = sum(item['quantity'] for item in cart_data)
                order_total = sum(item['quantity'] * item['price_each'] for item in cart_data)

                # Get unique item types for description
                conn_temp = get_db_connection()
                item_types = set()
                for item in cart_data:
                    listing = conn_temp.execute('''
                        SELECT categories.metal, categories.product_type
                        FROM listings
                        JOIN categories ON listings.category_id = categories.id
                        WHERE listings.id = ?
                    ''', (item['listing_id'],)).fetchone()
                    if listing:
                        item_types.add(f"{listing['metal']} {listing['product_type']}")
                conn_temp.close()

                # Use first item description or "Multiple items" if more than one type
                if len(item_types) == 1:
                    buyer_item_description = list(item_types)[0]
                else:
                    buyer_item_description = f"{len(item_types)} different items"

                notify_order_confirmed(
                    buyer_id=user_id,
                    order_id=order_id,
                    item_description=buyer_item_description,
                    quantity_purchased=total_items,
                    price_per_unit=order_total / total_items if total_items > 0 else 0,
                    total_amount=order_total
                )
            except Exception as e:
                print(f"[CHECKOUT] Failed to send buyer notification: {e}")

            return redirect(url_for('checkout.order_confirmation', order_id=order_id))

    else:
        # Render the checkout page
        # IMPORTANT: do NOT pop here; we still need the selection for the final POST
        session_items = session.get('checkout_items')

        raw_cart_items = []
        subtotal = 0

        if session_items:
            # Items from direct bucket purchase
            for item in session_items:
                listing = conn.execute('''
                    SELECT listings.id, listings.price_per_coin, listings.quantity as available_qty,
                           listings.pricing_mode, listings.spot_premium,
                           listings.floor_price, listings.pricing_metal, listings.seller_id,
                           listings.category_id,
                           categories.metal, categories.product_type, categories.product_line,
                           categories.weight, categories.mint, categories.year,
                           categories.finish, categories.grade, categories.purity,
                           categories.bucket_id,
                           users.username as seller_username,
                           (SELECT file_path FROM listing_photos WHERE listing_id = listings.id LIMIT 1) as photo_path
                    FROM listings
                    JOIN categories ON listings.category_id = categories.id
                    JOIN users ON listings.seller_id = users.id
                    WHERE listings.id = ?
                ''', (item['listing_id'],)).fetchone()

                if listing:
                    listing_dict = dict(listing)
                    listing_dict['quantity'] = item['quantity']
                    listing_dict['price_per_coin'] = item['price_each']
                    listing_dict['total_price'] = item['quantity'] * item['price_each']
                    subtotal += listing_dict['total_price']
                    raw_cart_items.append(listing_dict)
        else:
            # Items from cart
            raw_items = conn.execute('''
                SELECT cart.id, cart.quantity, cart.listing_id,
                       listings.price_per_coin, listings.pricing_mode,
                       listings.spot_premium, listings.floor_price, listings.pricing_metal,
                       listings.seller_id, listings.category_id,
                       categories.metal, categories.product_type, categories.product_line,
                       categories.weight, categories.purity, categories.mint, categories.year,
                       categories.finish, categories.grade, categories.bucket_id,
                       users.username as seller_username,
                       (SELECT file_path FROM listing_photos WHERE listing_id = listings.id LIMIT 1) as photo_path
                FROM cart
                JOIN listings ON cart.listing_id = listings.id
                JOIN categories ON listings.category_id = categories.id
                JOIN users ON listings.seller_id = users.id
                WHERE cart.user_id = ?
                  AND listings.active = 1
                  AND listings.quantity > 0
            ''', (user_id,)).fetchall()

            for row in raw_items:
                item_dict = dict(row)
                effective_price = get_effective_price(item_dict)
                item_dict['price_per_coin'] = effective_price
                item_dict['total_price'] = item_dict['quantity'] * effective_price
                subtotal += item_dict['total_price']
                raw_cart_items.append(item_dict)

        # Group items by bucket_id (same bucket should appear as one tile)
        bucket_groups = {}
        for item in raw_cart_items:
            bucket_id = item.get('bucket_id') or item.get('category_id')
            if bucket_id not in bucket_groups:
                # Initialize the group with first item's info
                bucket_groups[bucket_id] = {
                    'metal': item['metal'],
                    'product_type': item['product_type'],
                    'product_line': item['product_line'],
                    'weight': item['weight'],
                    'year': item['year'],
                    'mint': item.get('mint'),
                    'finish': item.get('finish'),
                    'grade': item.get('grade'),
                    'purity': item.get('purity'),
                    'photo_path': item.get('photo_path'),
                    'quantity': 0,
                    'total_price': 0,
                    'price_per_coin': 0,
                    'sellers': set(),
                    'listing_ids': []
                }

            group = bucket_groups[bucket_id]
            group['quantity'] += item['quantity']
            group['total_price'] += item['total_price']
            group['sellers'].add(item.get('seller_username', 'Seller'))
            group['listing_ids'].append(item.get('id') or item.get('listing_id'))
            # Use first photo if none yet
            if not group['photo_path'] and item.get('photo_path'):
                group['photo_path'] = item['photo_path']

        # Convert groups to list and calculate average price
        cart_items = []
        for bucket_id, group in bucket_groups.items():
            group['price_per_coin'] = group['total_price'] / group['quantity'] if group['quantity'] > 0 else 0
            # Format sellers display
            sellers_list = list(group['sellers'])
            if len(sellers_list) == 1:
                group['seller_username'] = sellers_list[0]
            else:
                group['seller_username'] = f"{len(sellers_list)} sellers"
            del group['sellers']  # Remove set before passing to template
            cart_items.append(group)

        if not cart_items:
            conn.close()
            flash("Your cart is empty.", "error")
            return redirect(url_for('buy.view_cart'))

        # Fetch user info for auto-population
        user_info = conn.execute('''
            SELECT first_name, last_name, email, phone
            FROM users WHERE id = ?
        ''', (user_id,)).fetchone()

        conn.close()

        # Calculate totals
        item_count = sum(item['quantity'] for item in cart_items)
        insurance = round(subtotal * 0.01, 2)  # 1% insurance
        cart_total = round(subtotal + insurance, 2)

        return render_template(
            'checkout_page.html',
            cart_items=cart_items,
            item_count=item_count,
            subtotal=round(subtotal, 2),
            insurance=insurance,
            cart_total=cart_total,
            user_info=dict(user_info) if user_info else {}
        )


@checkout_bp.route('/checkout/confirm/<int:order_id>')
def order_confirmation(order_id):
    """Display order confirmation page with animated success"""
    # SECURITY: Must verify user is the buyer of this order
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    conn = get_db_connection()

    # Get order details - EXPLICITLY verify buyer ownership
    order = conn.execute('''
        SELECT o.id, o.total_price, o.created_at, o.buyer_id,
               COUNT(oi.id) as item_count,
               SUM(oi.quantity) as total_quantity
        FROM orders o
        LEFT JOIN order_items oi ON o.id = oi.order_id
        WHERE o.id = ? AND o.buyer_id = ?
        GROUP BY o.id
    ''', (order_id, user_id)).fetchone()

    conn.close()

    if not order:
        # Order doesn't exist or user is not the buyer
        flash("Order not found.", "error")
        return redirect(url_for('account.account'))

    return render_template(
        'order_confirmation.html',
        order_id=order_id,
        order_total=order['total_price'],
        item_count=order['total_quantity'] or order['item_count']
    )
