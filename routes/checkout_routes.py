# routes/checkout_routes.py
from flask import Blueprint, render_template, redirect, url_for, request, session, flash, jsonify
from database import get_db_connection
from services.order_service import create_order
from utils.cart_utils import get_cart_items
from services.notification_service import notify_listing_sold
from services.pricing_service import get_effective_price, create_price_lock

checkout_bp = Blueprint('checkout', __name__)

@checkout_bp.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    conn = get_db_connection()

    if request.method == 'POST':
        # Check if this is an AJAX request (from modal)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        # For AJAX requests, expect JSON data
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
                        print(f"[CHECKOUT] Failed to send notification: {e}")

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

        # Original POST handling for non-AJAX requests
        bucket_id = request.form.get('bucket_id')
        quantity = int(request.form.get('quantity', 1))

        if bucket_id:
            # User is buying directly from a bucket (not from cart)
            graded_only = request.form.get('graded_only') == '1'
            any_grader = request.form.get('any_grader') == '1'
            pcgs = request.form.get('pcgs') == '1'
            ngc = request.form.get('ngc') == '1'

            grading_filter_applied = graded_only and (any_grader or pcgs or ngc)

            # Get listings with pricing fields for effective price calculation
            query = '''
                SELECT l.id, l.quantity, l.price_per_coin, l.pricing_mode,
                       l.spot_premium, l.floor_price, l.pricing_metal,
                       c.metal, c.weight, c.product_type
                FROM listings l
                JOIN categories c ON l.category_id = c.id
                WHERE l.category_id = ? AND l.active = 1 AND l.quantity > 0
            '''
            params = [bucket_id]

            if grading_filter_applied:
                query += ' AND l.graded = 1'
                if not any_grader:
                    services = []
                    if pcgs:
                        services.append("'PCGS'")
                    if ngc:
                        services.append("'NGC'")
                    if services:
                        query += f" AND l.grading_service IN ({', '.join(services)})"
                    else:
                        flash("No matching graded listings found.", "error")
                        conn.close()
                        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

            listings_raw = conn.execute(query, params).fetchall()

            # Calculate effective prices and sort
            listings_with_prices = []
            for listing in listings_raw:
                listing_dict = dict(listing)
                listing_dict['effective_price'] = get_effective_price(listing_dict)
                listings_with_prices.append(listing_dict)

            # Sort by effective price
            listings = sorted(listings_with_prices, key=lambda x: x['effective_price'])

            selected = []
            remaining = quantity

            for listing in listings:
                if remaining <= 0:
                    break
                take = min(listing['quantity'], remaining)
                selected.append({
                    'listing_id': listing['id'],
                    'quantity': take,
                    'price_each': listing['effective_price']
                })
                remaining -= take

            if remaining > 0:
                flash("Not enough inventory to fulfill your request.")
                conn.close()
                return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

            # Keep the selection in session for the GET render and final POST
            session['checkout_items'] = selected
            conn.close()
            return redirect(url_for('checkout.checkout'))

        else:
            # Final submit: create the order from either session-selected items or the cart
            shipping_address = request.form.get('shipping_address')

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
                return redirect(url_for('cart.view_cart'))

            # Create the order record (service inserts into orders & order_items)
            order_id = create_order(user_id, cart_data, shipping_address)

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

            return redirect(url_for('checkout.order_confirmation', order_id=order_id))

    else:
        # Render the checkout page
        # IMPORTANT: do NOT pop here; we still need the selection for the final POST
        session_items = session.get('checkout_items')

        if session_items:
            cart_data = session_items
            listings_info = []
            for item in cart_data:
                listing = conn.execute('''
                    SELECT listings.price_per_coin, listings.quantity,
                           listings.pricing_mode, listings.spot_premium,
                           listings.floor_price, listings.pricing_metal,
                           categories.metal, categories.product_type,
                           categories.weight, categories.mint, categories.year,
                           categories.finish, categories.grade
                    FROM listings
                    JOIN categories ON listings.category_id = categories.id
                    WHERE listings.id = ?
                ''', (item['listing_id'],)).fetchone()

                if listing:
                    listing_dict = dict(listing)
                    listing_dict['quantity'] = item['quantity']
                    # Use the price_each from session (already calculated as effective price)
                    listing_dict['price_per_coin'] = item['price_each']
                    listings_info.append(listing_dict)
        else:
            raw_items = get_cart_items(conn)
            # Calculate effective prices for cart items
            listings_info = []
            for row in raw_items:
                item_dict = dict(row)
                effective_price = get_effective_price(item_dict)
                item_dict['price_per_coin'] = effective_price
                listings_info.append(item_dict)

        conn.close()

        buckets = {}
        cart_total = 0

        for item in listings_info:
            bucket_key = f"{item['metal']}-{item['product_type']}-{item['weight']}-{item['mint']}-{item['year']}-{item['finish']}-{item['grade']}"

            if bucket_key not in buckets:
                buckets[bucket_key] = {
                    'category': {
                        'metal': item['metal'],
                        'product_type': item['product_type'],
                        'weight': item['weight'],
                        'mint': item['mint'],
                        'year': item['year'],
                        'finish': item['finish'],
                        'grade': item['grade']
                    },
                    'quantity': 0,
                    'total_qty': 0,
                    'total_price': 0,
                    'avg_price': 0
                }

                # Attach grading_preference when present
                if 'grading_preference' in item and item['grading_preference']:
                    buckets[bucket_key]['grading_preference'] = item['grading_preference']

            subtotal = item['price_per_coin'] * item['quantity']
            buckets[bucket_key]['quantity'] += item['quantity']
            buckets[bucket_key]['total_qty'] += item['quantity']
            buckets[bucket_key]['total_price'] += subtotal
            cart_total += subtotal

        for bucket in buckets.values():
            if bucket['quantity'] > 0:
                bucket['avg_price'] = round(bucket['total_price'] / bucket['quantity'], 2)

        return render_template(
            'checkout_new.html',
            buckets=buckets,
            cart_total=round(cart_total, 2),
            grading_preference=session.get('grading_preference')
        )


@checkout_bp.route('/checkout/confirm/<int:order_id>')
def order_confirmation(order_id):
    return render_template('order_confirmation.html', order_id=order_id)
