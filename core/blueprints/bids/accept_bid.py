"""
Accept Bid Routes

Contains routes for accepting and cancelling bids:
- /accept_bid/<bucket_id> (POST) - Accept one or more bids from a bucket
- /cancel/<bid_id> (POST) - Cancel an active bid
"""

from flask import request, redirect, url_for, session, flash, jsonify
from database import get_db_connection
from services.notification_service import notify_bid_filled
from services.pricing_service import get_effective_price, get_effective_bid_price

from . import bid_bp


@bid_bp.route('/accept_bid/<int:bucket_id>', methods=['POST'])
def accept_bid(bucket_id):
    """
    Accept one or more bids from this bucket. Frontend submits:
      - selected_bids: list of bid IDs
      - accept_qty[<bid_id>]: integer accepted quantity for that bid (0..remaining_quantity)
    Falls back to legacy quantity_<bid_id> if present.
    """
    # Debug logging for session
    print(f"[DEBUG] /accept_bid session keys: {list(session.keys())}")
    print(f"[DEBUG] /accept_bid user_id in session: {'user_id' in session}")
    if 'user_id' in session:
        print(f"[DEBUG] /accept_bid user_id value: {session['user_id']}")

    # Check authentication - return JSON 401 for AJAX, redirect for traditional form submissions
    if 'user_id' not in session:
        print(f"[ERROR] /accept_bid - No user_id in session. Session: {dict(session)}")
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if is_ajax:
            return jsonify(success=False, message="Authentication required. Please log in."), 401
        else:
            return redirect(url_for('auth.login'))

    seller_id = session['user_id']
    selected_bid_ids = request.form.getlist('selected_bids')

    if not selected_bid_ids:
        flash("⚠️ No bids selected.", "warning")
        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch spot prices once for all bids
    spot_prices_rows = cursor.execute('SELECT metal, price_usd_per_oz FROM spot_prices').fetchall()
    spot_prices = {row['metal'].lower(): row['price_usd_per_oz'] for row in spot_prices_rows}

    total_filled = 0

    # Collect notification data (will send after commit to avoid database locking)
    notifications_to_send = []

    # Collect order details for AJAX response (for success modal) - SUPPORTS MULTIPLE BIDS
    all_order_details = []

    for bid_id in selected_bid_ids:
        # Load bid with all pricing fields needed to calculate effective price
        bid = cursor.execute('''
            SELECT b.id, b.category_id, b.quantity_requested, b.remaining_quantity,
                   b.price_per_coin, b.buyer_id, b.delivery_address, b.status,
                   b.pricing_mode, b.spot_premium, b.ceiling_price, b.pricing_metal,
                   b.recipient_first_name, b.recipient_last_name,
                   c.metal, c.weight
            FROM bids b
            JOIN categories c ON b.category_id = c.id
            WHERE b.id = ?
        ''', (bid_id,)).fetchone()
        if not bid:
            continue

        # PREVENT SELF-ACCEPTING: Skip bids from the current user
        if bid['buyer_id'] == seller_id:
            continue

        category_id          = bid['category_id']
        buyer_id             = bid['buyer_id']
        delivery_address     = bid['delivery_address']
        recipient_first_name = bid['recipient_first_name']
        recipient_last_name  = bid['recipient_last_name']

        # Calculate effective bid price (handles both static and premium-to-spot)
        bid_dict = dict(bid)
        effective_bid_price = get_effective_bid_price(bid_dict, spot_prices=spot_prices)
        price_limit = effective_bid_price

        # Requested accept quantity from form (supports new and legacy names)
        req_qty = 0
        key_new = f'accept_qty[{bid_id}]'
        key_legacy = f'quantity_{bid_id}'
        if key_new in request.form:
            try:
                req_qty = int(request.form.get(key_new, '0'))
            except ValueError:
                req_qty = 0
        elif key_legacy in request.form:
            try:
                req_qty = int(request.form.get(key_legacy, '0'))
            except ValueError:
                req_qty = 0

        # Determine remaining on the bid (fallback to quantity_requested if remaining_quantity is NULL)
        remaining_qty = bid['remaining_quantity'] if bid['remaining_quantity'] is not None else (bid['quantity_requested'] or 0)
        if remaining_qty <= 0:
            continue

        # Clamp request; skip if user chose 0
        quantity_needed = max(0, min(remaining_qty, req_qty))
        if quantity_needed == 0:
            continue

        # Try to fill from seller's listings first (if any)
        # Fetch all pricing fields to calculate effective prices
        listings = cursor.execute('''
            SELECT l.id, l.quantity, l.price_per_coin, l.seller_id,
                   l.pricing_mode, l.spot_premium, l.floor_price, l.pricing_metal,
                   c.metal, c.weight
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE l.category_id = ?
              AND l.seller_id   = ?
              AND l.active = 1
        ''', (category_id, seller_id)).fetchall()

        # Filter listings by effective price and sort by effective price
        matched_listings = []
        for listing in listings:
            listing_dict = dict(listing)
            listing_effective_price = get_effective_price(listing_dict, spot_prices=spot_prices)

            # Only match if listing's current effective price is at or below bid's effective price
            if listing_effective_price <= effective_bid_price:
                listing_dict['effective_price'] = listing_effective_price
                matched_listings.append(listing_dict)

        # Sort by effective price (cheapest first)
        matched_listings.sort(key=lambda x: x['effective_price'])

        # Calculate total that will be filled
        filled = 0
        order_items_to_create = []

        for listing in matched_listings:
            if filled >= quantity_needed:
                break
            if listing['quantity'] <= 0:
                continue

            fill_qty = min(listing['quantity'], quantity_needed - filled)

            # Update listing inventory
            new_list_qty = listing['quantity'] - fill_qty
            if new_list_qty <= 0:
                cursor.execute('UPDATE listings SET quantity = 0, active = 0 WHERE id = ?', (listing['id'],))
            else:
                cursor.execute('UPDATE listings SET quantity = ? WHERE id = ?', (new_list_qty, listing['id']))

            # Queue order item creation
            # Use bid's effective price as the transaction price
            # Buyer pays what they bid, platform captures the spread
            order_items_to_create.append({
                'listing_id': listing['id'],
                'quantity': fill_qty,
                'price_each': effective_bid_price
            })

            filled += fill_qty

        # If seller commits to fulfill remaining quantity (even without listings)
        # create a committed listing placeholder first
        if filled < quantity_needed:
            unfilled_qty = quantity_needed - filled

            # Create a committed listing (already sold, so quantity=0, active=0)
            # Use the bid's effective price as the committed price
            cursor.execute('''
                INSERT INTO listings (category_id, seller_id, quantity, price_per_coin,
                                     graded, grading_service, image_url, active)
                VALUES (?, ?, 0, ?, 0, NULL, NULL, 0)
            ''', (category_id, seller_id, effective_bid_price))

            committed_listing_id = cursor.lastrowid

            # Queue order item with the committed listing
            order_items_to_create.append({
                'listing_id': committed_listing_id,
                'quantity': unfilled_qty,
                'price_each': effective_bid_price
            })

            filled += unfilled_qty

        # Calculate new_remaining for use in both notification and bid update
        new_remaining = remaining_qty - filled

        # Only create order if something was filled
        if filled > 0 and order_items_to_create:
            # Calculate total price for this order
            total_price = sum(item['quantity'] * item['price_each'] for item in order_items_to_create)

            # Create the order record
            cursor.execute('''
                INSERT INTO orders (buyer_id, total_price, shipping_address, status, created_at,
                                   recipient_first_name, recipient_last_name)
                VALUES (?, ?, ?, 'Pending Shipment', datetime('now'), ?, ?)
            ''', (buyer_id, total_price, delivery_address, recipient_first_name, recipient_last_name))

            order_id = cursor.lastrowid

            # Capture order details for THIS accepted bid (for AJAX response to show in modal)
            # Get buyer name
            buyer_info = cursor.execute('SELECT username, first_name, last_name FROM users WHERE id = ?', (buyer_id,)).fetchone()
            all_order_details.append({
                'buyer_name': buyer_info['username'] if buyer_info else 'Unknown',
                'buyer_first_name': buyer_info['first_name'] if buyer_info else '',
                'buyer_last_name': buyer_info['last_name'] if buyer_info else '',
                'delivery_address': delivery_address,
                'price_per_coin': effective_bid_price,
                'quantity': filled,
                'total_price': total_price,
                'order_id': order_id
            })

            # Create order_items for each fill
            for item in order_items_to_create:
                cursor.execute('''
                    INSERT INTO order_items (order_id, listing_id, quantity, price_each)
                    VALUES (?, ?, ?, ?)
                ''', (order_id, item['listing_id'], item['quantity'], item['price_each']))

            # Collect notification data for this bid (will send after commit)
            # Get category info for the item description
            category = cursor.execute('SELECT metal, product_type, product_line, weight, year FROM categories WHERE id = ?', (category_id,)).fetchone()
            item_desc_parts = []
            if category:
                if category['metal']:
                    item_desc_parts.append(category['metal'])
                if category['product_line']:
                    item_desc_parts.append(category['product_line'])
                if category['weight']:
                    item_desc_parts.append(category['weight'])
                if category['year']:
                    item_desc_parts.append(str(category['year']))
            item_description = ' '.join(item_desc_parts) if item_desc_parts else 'Item'

            # Add to notification queue
            # Calculate average price per unit based on actual transaction prices
            avg_price_per_unit = total_price / filled if filled > 0 else effective_bid_price
            notifications_to_send.append({
                'buyer_id': buyer_id,
                'order_id': order_id,
                'bid_id': bid_id,
                'item_description': item_description,
                'quantity_filled': filled,
                'price_per_unit': avg_price_per_unit,
                'total_amount': total_price,
                'is_partial': new_remaining > 0,
                'remaining_quantity': new_remaining
            })

        total_filled += filled

        # Update bid status / remaining
        if filled == 0:
            # no change
            pass
        elif new_remaining <= 0:
            cursor.execute('''
                UPDATE bids
                   SET remaining_quantity = 0,
                       active = 0,
                       status = 'Filled'
                 WHERE id = ?
            ''', (bid_id,))
        else:
            cursor.execute('''
                UPDATE bids
                   SET remaining_quantity = ?,
                       status = 'Partially Filled'
                 WHERE id = ?
            ''', (new_remaining, bid_id))

    conn.commit()
    conn.close()

    # Send notifications AFTER commit (avoids database locking)
    for notif_data in notifications_to_send:
        try:
            notify_bid_filled(**notif_data)
        except Exception as notify_error:
            print(f"[ERROR] Failed to notify buyer {notif_data['buyer_id']}: {notify_error}")

    # Check if this is an AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if is_ajax:
        # Return JSON for AJAX requests
        if total_filled > 0:
            response_data = {
                'success': True,
                'message': f'You fulfilled a total of {total_filled} coin(s) across {len(all_order_details)} bid(s).',
                'total_filled': total_filled,
                'orders_created': len(all_order_details)
            }
            # Include ALL order details (for success modal to show all accepted bids)
            if all_order_details:
                response_data['all_order_details'] = all_order_details
                # Keep first one for backward compatibility with old JS
                response_data['order_details'] = all_order_details[0] if all_order_details else None
            return jsonify(response_data)
        else:
            return jsonify({
                'success': False,
                'message': 'None of the selected bids could be filled.'
            }), 400
    else:
        # Traditional HTML response
        if total_filled > 0:
            flash(f"✅ You fulfilled a total of {total_filled} coin(s) across selected bids.", "success")
        else:
            flash("❌ None of the selected bids could be filled from your listings.", "error")

        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))


@bid_bp.route('/cancel/<int:bid_id>', methods=['POST'])
def cancel_bid(bid_id):
    # 1) Auth guard
    if 'user_id' not in session:
        # AJAX?
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(error="Authentication required"), 401
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    # 2) Verify bid exists & is owned by this user
    row = cursor.execute(
        'SELECT active, status, remaining_quantity FROM bids WHERE id = ? AND buyer_id = ?',
        (bid_id, user_id)
    ).fetchone()

    if not row:
        conn.close()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(error="Bid not found"), 404
        flash("❌ Bid not found.", "error")
        return redirect(url_for('bid.my_bids'))

    # Check if bid can be cancelled (must be active with remaining quantity)
    # Allow cancelling 'Open' or 'Partially Filled' bids that still have remaining quantity
    if not row['active'] or (row['remaining_quantity'] or 0) <= 0:
        conn.close()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(error="This bid cannot be cancelled (already inactive or fully filled)"), 400
        flash("❌ This bid cannot be cancelled (already inactive or fully filled).", "error")
        return redirect(url_for('bid.my_bids'))

    # 3) Soft‐delete it
    cursor.execute(
        '''
        UPDATE bids
           SET active = 0,
               status = 'Cancelled'
         WHERE id = ? AND buyer_id = ?
        ''',
        (bid_id, user_id)
    )
    conn.commit()
    conn.close()

    # 4) Response
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return ('', 204)

    flash("✅ Your bid has been cancelled.", "success")
    return redirect(request.referrer or url_for('bid.my_bids'))
