# routes/bid_routes.py

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from database import get_db_connection
from services.notification_service import notify_bid_filled
from services.spot_price_service import get_spot_price
from services.pricing_service import get_effective_price, get_effective_bid_price

bid_bp = Blueprint('bid', __name__, url_prefix='/bids')

@bid_bp.route('/place_bid/<int:bucket_id>', methods=['POST'])
def place_bid(bucket_id):
    if 'user_id' not in session:
        flash("❌ You must be logged in to place a bid.", "error")
        return redirect(url_for('auth.login'))

    try:
        # Extract pricing mode
        pricing_mode = request.form.get('bid_pricing_mode', 'static').strip()

        # Extract quantity (different field names based on mode)
        if pricing_mode == 'premium_to_spot':
            bid_quantity = int(request.form.get('bid_quantity_premium', 1))
        else:
            bid_quantity = int(request.form.get('bid_quantity', 1))

        delivery_address = request.form['delivery_address'].strip()
        requires_grading = request.form.get('requires_grading') == 'yes'
        preferred_grader = request.form.get('preferred_grader') if requires_grading else None

        # Extract pricing parameters based on mode
        if pricing_mode == 'premium_to_spot':
            # Premium-to-spot mode
            spot_premium_str = request.form.get('bid_spot_premium', '0').strip()
            ceiling_price_str = request.form.get('bid_ceiling_price', '0').strip()

            # Handle empty strings by using 0 as default
            spot_premium = float(spot_premium_str) if spot_premium_str else 0.0
            ceiling_price = float(ceiling_price_str) if ceiling_price_str else 0.0
            pricing_metal = request.form.get('bid_pricing_metal', '').strip()

            # For backwards compatibility, store ceiling_price as price_per_coin
            bid_price = ceiling_price
        else:
            # Static mode
            bid_price_str = request.form.get('bid_price', '0').strip()
            bid_price = float(bid_price_str) if bid_price_str else 0.0
            spot_premium = None
            ceiling_price = None
            pricing_metal = None
            pricing_mode = 'static'

    except (ValueError, KeyError) as e:
        flash(f"❌ Invalid form data: {str(e)}", "error")
        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    # Validate based on pricing mode
    if pricing_mode == 'premium_to_spot':
        if ceiling_price <= 0:
            flash("❌ Max price (ceiling) must be greater than zero for premium-to-spot bids.", "error")
            return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))
        if spot_premium < 0:
            flash("❌ Premium cannot be negative.", "error")
            return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))
    else:
        if bid_price <= 0:
            flash("❌ Bid price must be greater than zero.", "error")
            return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    if bid_quantity <= 0:
        flash("❌ Bid quantity must be greater than zero.", "error")
        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''
        INSERT INTO bids (
            category_id, buyer_id, quantity_requested, price_per_coin,
            remaining_quantity, active, requires_grading, preferred_grader,
            delivery_address, status,
            pricing_mode, spot_premium, ceiling_price, pricing_metal
        ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, 'Open', ?, ?, ?, ?)
        ''',
        (
            bucket_id,
            session['user_id'],
            bid_quantity,
            bid_price,
            bid_quantity,
            1 if requires_grading else 0,
            preferred_grader,
            delivery_address,
            pricing_mode,
            spot_premium,
            ceiling_price,
            pricing_metal
        )
    )
    conn.commit()
    conn.close()

    flash("✅ Your bid was placed successfully!", "success")
    return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

### for the submit bid page
@bid_bp.route('/edit_bid/<int:bid_id>')
def edit_bid(bid_id):
    """Full-page bid editor for non-modal use (e.g., bucket view page)."""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    bid = cursor.execute(
        'SELECT * FROM bids WHERE id = ? AND buyer_id = ?',
        (bid_id, session['user_id'])
    ).fetchone()

    if not bid:
        conn.close()
        flash("Bid not found or unauthorized.", "danger")
        return redirect(url_for('bid.my_bids'))

    bucket = cursor.execute(
        'SELECT * FROM categories WHERE id = ?',
        (bid['category_id'],)
    ).fetchone()

    listings = cursor.execute(
        '''
        SELECT price_per_coin FROM listings
        WHERE category_id = ? AND active = 1 AND quantity > 0
        ORDER BY price_per_coin ASC
        LIMIT 10
        ''',
        (bid['category_id'],)
    ).fetchall()

    conn.close()

    if listings:
        prices = [row['price_per_coin'] for row in listings]
        best_bid_price = round(sum(prices) / len(prices), 2)
        good_bid_price = round(best_bid_price * 0.95, 2)
    else:
        best_bid_price = bid['price_per_coin']
        good_bid_price = round(bid['price_per_coin'] * 0.95, 2)

    return render_template(
        'submit_bid.html',
        bucket=bucket,
        bid=bid,
        is_edit=True,
        form_action_url=url_for('bid.update_bid'),
        best_bid_price=best_bid_price,
        good_bid_price=good_bid_price
    )


@bid_bp.route('/update', methods=['POST'])
def update_bid():
    if 'user_id' not in session:
        return jsonify(success=False, message="Authentication required"), 401

    errors = {}
    try:
        bid_id = int(request.form['bid_id'])

        # Extract pricing mode
        pricing_mode = request.form.get('bid_pricing_mode', 'static').strip()

        # Extract quantity (different field names based on mode)
        if pricing_mode == 'premium_to_spot':
            bid_quantity = int(request.form.get('bid_quantity_premium', 1))
        else:
            bid_quantity = int(request.form.get('bid_quantity', 1))

        # May be empty string
        delivery_address = (request.form.get('delivery_address') or '').strip()

        requires_grading = (request.form.get('requires_grading') == 'yes')
        preferred_grader = request.form.get('preferred_grader')
        if not requires_grading:
            preferred_grader = None

        # Extract pricing parameters based on mode
        if pricing_mode == 'premium_to_spot':
            # Premium-to-spot mode
            spot_premium_str = request.form.get('bid_spot_premium', '0').strip()
            ceiling_price_str = request.form.get('bid_ceiling_price', '0').strip()

            # Handle empty strings by using 0 as default
            spot_premium = float(spot_premium_str) if spot_premium_str else 0.0
            ceiling_price = float(ceiling_price_str) if ceiling_price_str else 0.0
            pricing_metal = request.form.get('bid_pricing_metal', '').strip()

            # For backwards compatibility, store ceiling_price as price_per_coin
            bid_price = ceiling_price
        else:
            # Static mode
            bid_price_str = request.form.get('bid_price', '0').strip()
            bid_price = float(bid_price_str) if bid_price_str else 0.0
            spot_premium = None
            ceiling_price = None
            pricing_metal = None
            pricing_mode = 'static'

    except (ValueError, KeyError) as e:
        return jsonify(success=False, message=f"Invalid input data: {str(e)}"), 400

    # Server-side rounding to tick 0.01
    bid_price = round(bid_price + 1e-9, 2)
    if spot_premium is not None:
        spot_premium = round(spot_premium + 1e-9, 2)
    if ceiling_price is not None:
        ceiling_price = round(ceiling_price + 1e-9, 2)

    # Validate based on pricing mode
    if pricing_mode == 'premium_to_spot':
        if ceiling_price is None or ceiling_price <= 0:
            errors['bid_ceiling_price'] = "Max price (ceiling) must be greater than zero for premium-to-spot bids."
        if spot_premium is not None and spot_premium < 0:
            errors['bid_spot_premium'] = "Premium cannot be negative."
    else:
        if bid_price <= 0:
            errors['bid_price'] = "Price must be greater than zero."

    if bid_quantity < 1:
        errors['bid_quantity'] = "Quantity must be at least 1."
    if requires_grading and not delivery_address:
        errors['delivery_address'] = "Delivery address is required when grading is selected."
    if errors:
        return jsonify(success=False, errors=errors), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Ensure ownership & fetch existing address so we can preserve if blank
    existing = cursor.execute(
        'SELECT buyer_id, delivery_address FROM bids WHERE id = ?',
        (bid_id,)
    ).fetchone()
    if not existing or existing['buyer_id'] != session['user_id']:
        conn.close()
        return jsonify(success=False, message="Unauthorized"), 403

    # Preserve prior address if user left it blank and grading is off
    new_address = delivery_address if delivery_address else (existing['delivery_address'] or '')

    # Get current bid state before update
    current_bid = cursor.execute(
        'SELECT quantity_fulfilled FROM bids WHERE id = ?',
        (bid_id,)
    ).fetchone()

    quantity_fulfilled = current_bid['quantity_fulfilled'] if current_bid else 0

    cursor.execute(
        '''
        UPDATE bids
           SET price_per_coin      = ?,
               quantity_requested  = ?,
               remaining_quantity  = ?,
               requires_grading    = ?,
               preferred_grader    = ?,
               delivery_address    = ?,
               pricing_mode        = ?,
               spot_premium        = ?,
               ceiling_price       = ?,
               pricing_metal       = ?,
               status              = 'Open',
               active              = 1
         WHERE id = ? AND buyer_id = ?
        ''',
        (
            bid_price,
            bid_quantity,
            bid_quantity - quantity_fulfilled,  # remaining = total - already fulfilled
            1 if requires_grading else 0,
            preferred_grader,
            new_address,
            pricing_mode,
            spot_premium,
            ceiling_price,
            pricing_metal,
            bid_id,
            session['user_id']
        )
    )

    # Auto-match bid to available listings (in case price increase opens new matches)
    match_result = auto_match_bid_to_listings(bid_id, cursor)

    # Get the updated bid with all fields for effective price calculation
    updated_bid = cursor.execute('''
        SELECT b.*, c.metal, c.weight, c.product_type
        FROM bids b
        JOIN categories c ON b.category_id = c.id
        WHERE b.id = ?
    ''', (bid_id,)).fetchone()

    conn.commit()
    conn.close()

    # Calculate effective bid price
    bid_dict = dict(updated_bid) if updated_bid else {}
    effective_price = get_effective_bid_price(bid_dict) if updated_bid else bid_price

    # Get current spot price if variable pricing
    current_spot_price = None
    if pricing_mode == 'premium_to_spot' and pricing_metal:
        current_spot_price = get_spot_price(pricing_metal)

    # Build response message
    if match_result['filled_quantity'] > 0:
        message = f"Bid updated successfully! ✅ {match_result['message']}"
    else:
        message = "Bid updated successfully"

    return jsonify(
        success=True,
        message=message,
        filled_quantity=match_result.get('filled_quantity', 0),
        orders_created=match_result.get('orders_created', 0),
        pricing_mode=pricing_mode,
        effective_price=effective_price,
        current_spot_price=current_spot_price
    )


@bid_bp.route('/edit_form/<int:bid_id>', methods=['GET'])
def edit_bid_form(bid_id):
    if 'user_id' not in session:
        return jsonify(error="Authentication required"), 401

    conn = get_db_connection()
    cursor = conn.cursor()

    # Load bid, enforce ownership
    bid = cursor.execute(
        'SELECT * FROM bids WHERE id = ? AND buyer_id = ?',
        (bid_id, session['user_id'])
    ).fetchone()
    if not bid:
        conn.close()
        return jsonify(error="Bid not found or unauthorized"), 404

    category_id = bid['category_id']

    # Current item price = lowest ask among active listings in this bucket
    row_lowest = cursor.execute(
        '''
        SELECT MIN(price_per_coin) AS min_price
        FROM listings
        WHERE category_id = ?
          AND active = 1
          AND quantity > 0
        ''',
        (category_id,)
    ).fetchone()
    current_item_price = float(row_lowest['min_price']) if row_lowest and row_lowest['min_price'] is not None else float(bid['price_per_coin'])

    # Best Bid pill = highest active bid price for this bucket (excluding cancelled/inactive)
    row_best_bid = cursor.execute(
        '''
        SELECT MAX(price_per_coin) AS max_bid
        FROM bids
        WHERE category_id = ?
          AND active = 1
        ''',
        (category_id,)
    ).fetchone()
    best_bid_price = float(row_best_bid['max_bid']) if row_best_bid and row_best_bid['max_bid'] is not None else float(bid['price_per_coin'])

    conn.close()

    # Render the new single-screen tab (not the old wizard)
    return render_template(
        'tabs/bid_form.html',
        bid=bid,
        current_item_price=round(current_item_price, 2),
        best_bid_price=round(best_bid_price, 2),
        form_action_url=url_for('bid.update_bid')
    )


@bid_bp.route('/my_bids')
def my_bids():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    bids = conn.execute(
        'SELECT * FROM bids WHERE buyer_id = ? ORDER BY created_at DESC',
        (session['user_id'],)
    ).fetchall()
    conn.close()

    return render_template('my_bids.html', bids=bids)


@bid_bp.route("/bid/<int:bucket_id>", methods=["GET"])
def bid_page(bucket_id):
    if "user_id" not in session:
        flash(("error", "You must be logged in to submit a bid."))
        return redirect(url_for("auth.login"))

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM categories WHERE id = ?", (bucket_id,))
    bucket = c.fetchone()

    if not bucket:
        conn.close()
        flash(("error", "Item not found."))
        return redirect(url_for("buy.buy"))

    # ✅ Calculate lowest listed price
    lowest = c.execute('''
        SELECT MIN(price_per_coin) as min_price
        FROM listings
        WHERE category_id = ? AND active = 1 AND quantity > 0
    ''', (bucket_id,)).fetchone()
    lowest_listed_price = lowest['min_price'] or 0

    # ✅ Calculate highest active bid
    highest = c.execute('''
        SELECT MAX(price_per_coin) as max_bid
        FROM bids
        WHERE category_id = ? AND active = 1
    ''', (bucket_id,)).fetchone()
    highest_current_bid = highest['max_bid'] or 0

    conn.close()

    return render_template(
        "submit_bid.html",
        bucket=bucket,
        bid=None,
        is_edit=False,
        form_action_url=url_for('bid.place_bid', bucket_id=bucket_id),
        best_bid_price=round(lowest_listed_price + 5, 2),
        good_bid_price=round(highest_current_bid, 2)
    )


@bid_bp.route('/accept_bid/<int:bucket_id>', methods=['POST'])
def accept_bid(bucket_id):
    """
    Accept one or more bids from this bucket. Frontend submits:
      - selected_bids: list of bid IDs
      - accept_qty[<bid_id>]: integer accepted quantity for that bid (0..remaining_quantity)
    Falls back to legacy quantity_<bid_id> if present.
    """
    if 'user_id' not in session:
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

    # Collect order details for AJAX response (for success modal)
    first_order_details = None

    for bid_id in selected_bid_ids:
        # Load bid with all pricing fields needed to calculate effective price
        bid = cursor.execute('''
            SELECT b.id, b.category_id, b.quantity_requested, b.remaining_quantity,
                   b.price_per_coin, b.buyer_id, b.delivery_address, b.status,
                   b.pricing_mode, b.spot_premium, b.ceiling_price, b.pricing_metal,
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

        category_id      = bid['category_id']
        buyer_id         = bid['buyer_id']
        delivery_address = bid['delivery_address']

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
                                     graded, grading_service, photo_filename, active)
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
                INSERT INTO orders (buyer_id, total_price, shipping_address, status, created_at)
                VALUES (?, ?, ?, 'Pending Shipment', datetime('now'))
            ''', (buyer_id, total_price, delivery_address))

            order_id = cursor.lastrowid

            # Capture order details for first accepted bid (for AJAX response to show in modal)
            if first_order_details is None:
                # Get buyer name
                buyer_info = cursor.execute('SELECT username, first_name, last_name FROM users WHERE id = ?', (buyer_id,)).fetchone()
                first_order_details = {
                    'buyer_name': buyer_info['username'] if buyer_info else 'Unknown',
                    'buyer_first_name': buyer_info['first_name'] if buyer_info else '',
                    'buyer_last_name': buyer_info['last_name'] if buyer_info else '',
                    'delivery_address': delivery_address,
                    'price_per_coin': effective_bid_price,
                    'quantity': filled,
                    'total_price': total_price
                }

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
                'message': f'You fulfilled a total of {total_filled} coin(s) across selected bids.',
                'total_filled': total_filled
            }
            # Include order details if available (for success modal)
            if first_order_details:
                response_data['order_details'] = first_order_details
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

    # 2) Verify bid is open & owned by this user
    row = cursor.execute(
        'SELECT active, status FROM bids WHERE id = ? AND buyer_id = ?',
        (bid_id, user_id)
    ).fetchone()

    if not row or not row['active'] or row['status'] != 'Open':
        conn.close()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(error="Cannot cancel this bid"), 400
        flash("❌ Cannot cancel that bid.", "error")
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


# ==============================================================================
# UNIFIED BID MODAL ROUTES (NEW SYSTEM)
# These routes support the unified bid modal that handles both CREATE and EDIT
# ==============================================================================

@bid_bp.route('/form/<int:bucket_id>', methods=['GET'])
@bid_bp.route('/form/<int:bucket_id>/<int:bid_id>', methods=['GET'])
def bid_form_unified(bucket_id, bid_id=None):
    """
    Unified endpoint for bid form (create or edit).

    Routes:
    - GET /bids/form/<bucket_id> → CREATE mode (bid_id=None)
    - GET /bids/form/<bucket_id>/<bid_id> → EDIT mode

    Returns:
        HTML partial (bid_form.html) for AJAX injection into modal
    """
    if 'user_id' not in session:
        return jsonify(error="Authentication required"), 401

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get bucket/category info
    bucket = cursor.execute(
        'SELECT * FROM categories WHERE id = ?',
        (bucket_id,)
    ).fetchone()

    if not bucket:
        conn.close()
        return jsonify(error="Category not found"), 404

    # EDIT mode: load existing bid
    if bid_id:
        bid = cursor.execute(
            'SELECT * FROM bids WHERE id = ? AND buyer_id = ?',
            (bid_id, session['user_id'])
        ).fetchone()

        if not bid:
            conn.close()
            return jsonify(error="Bid not found or unauthorized"), 404

        is_edit = True
        form_action_url = url_for('bid.update_bid')

        # Parse delivery_address to populate individual fields
        # Format: "First Last • Address Line 1 • Address Line 2 • City, State, Zip"
        parsed_address = {}
        if bid['delivery_address']:
            parts = [p.strip() for p in bid['delivery_address'].split('•')]
            if len(parts) >= 1:
                # First part: name
                name_parts = parts[0].split(None, 1)  # Split on first space
                parsed_address['first_name'] = name_parts[0] if len(name_parts) > 0 else ''
                parsed_address['last_name'] = name_parts[1] if len(name_parts) > 1 else ''

            if len(parts) >= 2:
                parsed_address['line1'] = parts[1]

            if len(parts) >= 3:
                # Check if this is city/state/zip or line2
                if len(parts) == 3:
                    # Last part is city/state/zip
                    city_state_zip = parts[2]
                else:
                    # This is line2
                    parsed_address['line2'] = parts[2]
                    city_state_zip = parts[3] if len(parts) >= 4 else ''

                # Parse city, state, zip from "City, State, Zip" format
                if len(parts) >= 3:
                    city_state_zip = parts[-1]  # Always last part
                    city_parts = [p.strip() for p in city_state_zip.split(',')]
                    if len(city_parts) >= 1:
                        parsed_address['city'] = city_parts[0]
                    if len(city_parts) >= 2:
                        parsed_address['state'] = city_parts[1]
                    if len(city_parts) >= 3:
                        parsed_address['zip'] = city_parts[2]

        # Add parsed address to context
        bid = dict(bid)
        bid['parsed_address'] = parsed_address

    # CREATE mode: no existing bid
    else:
        bid = None
        is_edit = False
        form_action_url = url_for('bid.create_bid_unified', bucket_id=bucket_id)

    # Calculate current market price and get pricing mode information
    lowest = cursor.execute('''
        SELECT MIN(price_per_coin) as min_price,
               pricing_mode,
               spot_premium,
               floor_price,
               pricing_metal
        FROM listings
        WHERE category_id = ? AND active = 1 AND quantity > 0
        ORDER BY price_per_coin ASC
        LIMIT 1
    ''', (bucket_id,)).fetchone()

    # Calculate highest active bid
    highest_bid = cursor.execute('''
        SELECT MAX(price_per_coin) as max_bid
        FROM bids
        WHERE category_id = ? AND active = 1
    ''', (bucket_id,)).fetchone()

    # Fetch user's saved addresses
    addresses = cursor.execute('''
        SELECT * FROM addresses
        WHERE user_id = ?
        ORDER BY id
    ''', (session['user_id'],)).fetchall()

    # Fetch user's first and last name for auto-populating billing fields
    user_info = cursor.execute('''
        SELECT first_name, last_name FROM users
        WHERE id = ?
    ''', (session['user_id'],)).fetchone()

    conn.close()

    current_item_price = float(lowest['min_price']) if lowest and lowest['min_price'] else 0
    best_bid_price = float(highest_bid['max_bid']) if highest_bid and highest_bid['max_bid'] else 0

    # Extract pricing information for premium-to-spot listings
    # Note: sqlite3.Row doesn't have .get() method, use dictionary-style access
    pricing_info = None
    if lowest:
        try:
            # Check if pricing_mode exists and equals 'premium_to_spot'
            pricing_mode = lowest['pricing_mode'] if 'pricing_mode' in lowest.keys() else None
            if pricing_mode == 'premium_to_spot':
                pricing_info = {
                    'pricing_mode': pricing_mode,
                    'spot_premium': float(lowest['spot_premium']) if lowest['spot_premium'] else 0,
                    'floor_price': float(lowest['floor_price']) if lowest['floor_price'] else 0,
                    'pricing_metal': lowest['pricing_metal'] if lowest['pricing_metal'] else bucket['metal']
                }
        except (KeyError, TypeError) as e:
            # If pricing columns don't exist (old data), pricing_info remains None
            print(f"[DEBUG] No pricing mode data available: {e}")
            pricing_info = None

    # Get current spot price for the bucket's metal
    current_spot_price = None
    if bucket and bucket['metal']:
        try:
            current_spot_price = get_spot_price(bucket['metal'])
        except Exception as e:
            print(f"[DEBUG] Could not fetch spot price for {bucket['metal']}: {e}")

    return render_template(
        'tabs/bid_form.html',
        bid=bid,
        bucket=bucket,
        is_edit=is_edit,
        form_action_url=form_action_url,
        current_item_price=round(current_item_price, 2),
        best_bid_price=round(best_bid_price, 2),
        addresses=addresses,
        user_info=user_info,
        pricing_info=pricing_info,
        current_spot_price=current_spot_price
    )


def auto_match_bid_to_listings(bid_id, cursor):
    """
    Automatically match a bid to available listings.
    Called immediately after bid creation to auto-fill if possible.

    IMPORTANT: For premium-to-spot bids, this calculates the effective bid price
    (spot + premium, capped at ceiling) and only matches listings at or below that price.

    Args:
        bid_id: The ID of the newly created bid
        cursor: Database cursor (assumes transaction is already open)

    Returns:
        dict with 'filled_quantity', 'orders_created', 'message'
    """
    # Load the bid with all fields including metal and weight for price calculation
    bid = cursor.execute('''
        SELECT b.*, c.metal, c.weight, c.product_type
        FROM bids b
        JOIN categories c ON b.category_id = c.id
        WHERE b.id = ?
    ''', (bid_id,)).fetchone()

    if not bid or bid['remaining_quantity'] <= 0:
        return {'filled_quantity': 0, 'orders_created': 0, 'message': 'No quantity to fill'}

    category_id = bid['category_id']
    buyer_id = bid['buyer_id']
    delivery_address = bid['delivery_address']
    requires_grading = bid['requires_grading']
    preferred_grader = bid['preferred_grader']
    quantity_needed = bid['remaining_quantity']

    # Fetch spot prices from the SAME database connection
    # This ensures test databases and production use consistent spot prices
    spot_prices_rows = cursor.execute('SELECT metal, price_usd_per_oz FROM spot_prices').fetchall()
    spot_prices = {row['metal'].lower(): row['price_usd_per_oz'] for row in spot_prices_rows}

    # Calculate effective bid price (handles both static and premium-to-spot modes)
    # For premium-to-spot, this calculates spot + premium and enforces ceiling
    bid_dict = dict(bid)
    effective_bid_price = get_effective_bid_price(bid_dict, spot_prices=spot_prices)

    # This is the maximum price the buyer will pay
    bid_price = effective_bid_price

    # Query matching listings - fetch ALL fields needed for effective price calculation
    # We'll filter by effective price in Python after calculating it for each listing
    if requires_grading and preferred_grader:
        # Bid requires specific grader
        listings = cursor.execute('''
            SELECT l.id, l.seller_id, l.quantity, l.price_per_coin, l.grading_service,
                   l.pricing_mode, l.spot_premium, l.floor_price, l.pricing_metal,
                   c.metal, c.weight
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE l.category_id = ?
              AND l.active = 1
              AND l.quantity > 0
              AND l.graded = 1
              AND l.grading_service = ?
        ''', (category_id, preferred_grader)).fetchall()
    elif requires_grading:
        # Bid requires any grader
        listings = cursor.execute('''
            SELECT l.id, l.seller_id, l.quantity, l.price_per_coin, l.grading_service,
                   l.pricing_mode, l.spot_premium, l.floor_price, l.pricing_metal,
                   c.metal, c.weight
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE l.category_id = ?
              AND l.active = 1
              AND l.quantity > 0
              AND l.graded = 1
        ''', (category_id,)).fetchall()
    else:
        # No grading requirement
        listings = cursor.execute('''
            SELECT l.id, l.seller_id, l.quantity, l.price_per_coin, l.grading_service,
                   l.pricing_mode, l.spot_premium, l.floor_price, l.pricing_metal,
                   c.metal, c.weight
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE l.category_id = ?
              AND l.active = 1
              AND l.quantity > 0
        ''', (category_id,)).fetchall()

    if not listings:
        return {'filled_quantity': 0, 'orders_created': 0, 'message': 'No matching listings found'}

    # Calculate effective price for each listing and filter by effective bid price
    # This ensures we only match listings whose CURRENT effective price is <= bid's effective price
    matched_listings = []
    for listing in listings:
        listing_dict = dict(listing)
        listing_effective_price = get_effective_price(listing_dict, spot_prices=spot_prices)

        # Only match if listing's current effective price is at or below bid's effective price
        if listing_effective_price <= effective_bid_price:
            # Store the effective price on the listing for later use
            listing_dict['effective_price'] = listing_effective_price
            matched_listings.append(listing_dict)

    # Sort by effective price (cheapest first), then by id for consistency
    matched_listings.sort(key=lambda x: (x['effective_price'], x['id']))

    if not matched_listings:
        return {'filled_quantity': 0, 'orders_created': 0, 'message': 'No matching listings found (effective prices do not overlap)'}

    # Group fills by seller (one order per seller)
    seller_fills = {}  # seller_id -> list of {listing_id, quantity, price_each}
    total_filled = 0

    for listing in matched_listings:
        if total_filled >= quantity_needed:
            break

        seller_id = listing['seller_id']
        available = listing['quantity']
        fill_qty = min(available, quantity_needed - total_filled)

        # Update listing quantity
        new_qty = available - fill_qty
        if new_qty <= 0:
            cursor.execute('UPDATE listings SET quantity = 0, active = 0 WHERE id = ?', (listing['id'],))
        else:
            cursor.execute('UPDATE listings SET quantity = ? WHERE id = ?', (new_qty, listing['id']))

        # Track fill for this seller
        if seller_id not in seller_fills:
            seller_fills[seller_id] = []

        # Use bid's effective price as the transaction price
        # Buyer pays what they bid, platform captures the spread between bid and listing
        seller_fills[seller_id].append({
            'listing_id': listing['id'],
            'quantity': fill_qty,
            'price_each': effective_bid_price
        })

        total_filled += fill_qty

    # Create one order per seller
    orders_created = 0
    for seller_id, items in seller_fills.items():
        total_price = sum(item['quantity'] * item['price_each'] for item in items)

        # Create order
        cursor.execute('''
            INSERT INTO orders (buyer_id, total_price, shipping_address, status, created_at)
            VALUES (?, ?, ?, 'Pending Shipment', datetime('now'))
        ''', (buyer_id, total_price, delivery_address))

        order_id = cursor.lastrowid
        orders_created += 1

        # Create order_items
        for item in items:
            cursor.execute('''
                INSERT INTO order_items (order_id, listing_id, quantity, price_each)
                VALUES (?, ?, ?, ?)
            ''', (order_id, item['listing_id'], item['quantity'], item['price_each']))

    # Update bid status
    new_remaining = quantity_needed - total_filled
    if new_remaining <= 0:
        # Fully filled
        cursor.execute('''
            UPDATE bids
            SET remaining_quantity = 0,
                quantity_fulfilled = quantity_requested,
                active = 0,
                status = 'Filled'
            WHERE id = ?
        ''', (bid_id,))
        message = f'Bid fully filled! Matched {total_filled} items from {orders_created} seller(s).'
    else:
        # Partially filled
        cursor.execute('''
            UPDATE bids
            SET remaining_quantity = ?,
                quantity_fulfilled = quantity_fulfilled + ?,
                status = 'Partially Filled'
            WHERE id = ?
        ''', (new_remaining, total_filled, bid_id))
        message = f'Bid partially filled! Matched {total_filled} of {quantity_needed} items from {orders_created} seller(s). {new_remaining} items still open.'

    return {
        'filled_quantity': total_filled,
        'orders_created': orders_created,
        'message': message
    }


@bid_bp.route('/create/<int:bucket_id>', methods=['POST'])
def create_bid_unified(bucket_id):
    """
    Create a new bid (unified modal version).
    Returns JSON for AJAX handling.

    After creating the bid, automatically attempts to match it with available listings.

    Form parameters:
    - bid_pricing_mode: 'static' or 'premium_to_spot'
    - Static mode: bid_price, bid_quantity
    - Premium mode: bid_spot_premium, bid_ceiling_price, bid_quantity_premium, bid_pricing_metal
    - delivery_address: string
    - requires_grading: 'yes' or 'no'
    - preferred_grader: string (optional)
    """
    if 'user_id' not in session:
        return jsonify(success=False, message="Authentication required"), 401

    errors = {}
    try:
        # Extract pricing mode
        pricing_mode = request.form.get('bid_pricing_mode', 'static').strip()

        # Extract quantity (different field names based on mode)
        if pricing_mode == 'premium_to_spot':
            bid_quantity_str = request.form.get('bid_quantity_premium', '').strip()
            bid_quantity = int(bid_quantity_str) if bid_quantity_str else 0
        else:
            bid_quantity_str = request.form.get('bid_quantity', '').strip()
            bid_quantity = int(bid_quantity_str) if bid_quantity_str else 0

        delivery_address = request.form.get('delivery_address', '').strip()
        requires_grading = request.form.get('requires_grading') == 'yes'
        preferred_grader = request.form.get('preferred_grader') if requires_grading else None

        # Extract pricing parameters based on mode
        if pricing_mode == 'premium_to_spot':
            # Premium-to-spot mode
            spot_premium_str = request.form.get('bid_spot_premium', '').strip()
            ceiling_price_str = request.form.get('bid_ceiling_price', '').strip()

            # Handle empty strings - premium can be 0, ceiling must be positive
            spot_premium = float(spot_premium_str) if spot_premium_str else 0.0
            ceiling_price = float(ceiling_price_str) if ceiling_price_str else 0.0
            pricing_metal = request.form.get('bid_pricing_metal', '').strip()

            # For backwards compatibility, store ceiling_price as price_per_coin
            bid_price = ceiling_price
        else:
            # Static mode
            bid_price_str = request.form.get('bid_price', '').strip()
            bid_price = float(bid_price_str) if bid_price_str else 0.0
            spot_premium = None
            ceiling_price = None
            pricing_metal = None
            pricing_mode = 'static'

    except (ValueError, KeyError) as e:
        return jsonify(success=False, message=f"Invalid form data: {str(e)}"), 400

    # Server-side validation based on pricing mode
    if pricing_mode == 'premium_to_spot':
        if ceiling_price <= 0:
            errors['bid_ceiling_price'] = "Max price (ceiling) must be greater than zero for premium-to-spot bids."
        if spot_premium < 0:
            errors['bid_spot_premium'] = "Premium cannot be negative."
    else:
        if bid_price <= 0:
            errors['bid_price'] = "Price must be greater than zero."

    if bid_quantity <= 0:
        errors['bid_quantity'] = "Quantity must be greater than zero."
    if not delivery_address:
        errors['delivery_address'] = "Delivery address is required."

    if errors:
        return jsonify(success=False, errors=errors), 400

    # Insert bid into database
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            '''
            INSERT INTO bids (
                category_id, buyer_id, quantity_requested, price_per_coin,
                remaining_quantity, active, requires_grading, preferred_grader,
                delivery_address, status,
                pricing_mode, spot_premium, ceiling_price, pricing_metal
            ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, 'Open', ?, ?, ?, ?)
            ''',
            (
                bucket_id,
                session['user_id'],
                bid_quantity,
                bid_price,
                bid_quantity,  # remaining_quantity starts equal to quantity_requested
                1 if requires_grading else 0,
                preferred_grader,
                delivery_address,
                pricing_mode,
                spot_premium,
                ceiling_price,
                pricing_metal
            )
        )
        new_bid_id = cursor.lastrowid

        # Auto-match bid to available listings
        match_result = auto_match_bid_to_listings(new_bid_id, cursor)

        conn.commit()

        # Get the created bid with all fields for effective price calculation
        created_bid = conn.execute('''
            SELECT b.*, c.metal, c.weight, c.product_type
            FROM bids b
            JOIN categories c ON b.category_id = c.id
            WHERE b.id = ?
        ''', (new_bid_id,)).fetchone()

        conn.close()

        # Calculate effective bid price
        bid_dict = dict(created_bid) if created_bid else {}
        effective_price = get_effective_bid_price(bid_dict) if created_bid else bid_price

        # Get current spot price if variable pricing
        current_spot_price = None
        if pricing_mode == 'premium_to_spot' and pricing_metal:
            from services.spot_price_service import get_spot_price
            current_spot_price = get_spot_price(pricing_metal)

        # Build response message
        if pricing_mode == 'premium_to_spot':
            base_message = f"Your variable bid (effective price: ${effective_price:.2f}) for {bid_quantity} item(s) was placed successfully!"
        else:
            base_message = f"Your bid of ${bid_price:.2f} for {bid_quantity} item(s) was placed successfully!"

        if match_result['filled_quantity'] > 0:
            # Bid was filled (fully or partially)
            full_message = f"{base_message}\n\n✅ {match_result['message']}"
        else:
            # Bid is still open, no matches found
            full_message = f"{base_message} Your bid is now open and waiting for matching listings."

        return jsonify(
            success=True,
            message=full_message,
            bid_id=new_bid_id,
            filled_quantity=match_result['filled_quantity'],
            orders_created=match_result['orders_created'],
            pricing_mode=pricing_mode,
            effective_price=effective_price,
            current_spot_price=current_spot_price
        )

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify(success=False, message=f"Database error: {str(e)}"), 500


# Note: update_bid route (lines 111-185) already returns JSON and works for both systems
# No changes needed there - it's already compatible with the unified modal


@bid_bp.route('/api/bid/<int:bid_id>/bidder_info')
def get_bidder_info(bid_id):
    """
    API endpoint to fetch bidder information for a specific bid
    Used by the View Bidder modal on the Bucket ID page
    """
    conn = get_db_connection()

    try:
        # Get bid and bidder information
        bidder = conn.execute("""
            SELECT
                b.id as bid_id,
                b.buyer_id,
                b.quantity_requested,
                b.remaining_quantity,
                u.username,
                COALESCE(AVG(r.rating), 0) as rating,
                COUNT(r.id) as num_reviews
            FROM bids b
            JOIN users u ON b.buyer_id = u.id
            LEFT JOIN ratings r ON u.id = r.ratee_id
            WHERE b.id = ?
            GROUP BY b.id, b.buyer_id, b.quantity_requested, b.remaining_quantity, u.username
        """, (bid_id,)).fetchone()

        if not bidder:
            return jsonify({'error': 'Bid not found'}), 404

        # Calculate quantity for this bid
        requested = bidder['quantity_requested'] or 0
        remaining = bidder['remaining_quantity'] if bidder['remaining_quantity'] is not None else requested

        result = {
            'buyer_id': bidder['buyer_id'],
            'username': bidder['username'],
            'rating': round(bidder['rating'], 1),
            'num_reviews': bidder['num_reviews'],
            'quantity': remaining  # Show remaining quantity
        }

        return jsonify(result)

    except Exception as e:
        print(f"Error fetching bidder info: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


