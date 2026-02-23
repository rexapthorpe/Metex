"""
Edit Bid Routes

Contains routes for editing bids:
- /edit_bid/<int:bid_id> (GET) - edit_bid: Full-page bid editor
- /update (POST) - update_bid: Process bid update
- /edit_form/<int:bid_id> (GET) - edit_bid_form: Render edit form for modal
"""

from flask import render_template, request, redirect, url_for, session, flash, jsonify
from database import get_db_connection
from services.notification_service import notify_bid_filled
from services.spot_price_service import get_spot_price
from services.pricing_service import get_effective_bid_price
from utils.auth_utils import frozen_check

from . import bid_bp
from .auto_match import auto_match_bid_to_listings


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

    # Get listings with all pricing fields to calculate effective prices
    listings_raw = cursor.execute(
        '''
        SELECT l.price_per_coin, l.pricing_mode, l.spot_premium, l.floor_price, l.pricing_metal,
               c.metal, c.weight
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.category_id = ? AND l.active = 1 AND l.quantity > 0
        ORDER BY l.price_per_coin ASC
        LIMIT 10
        ''',
        (bid['category_id'],)
    ).fetchall()

    conn.close()

    if listings_raw:
        # Calculate effective prices for each listing
        from services.pricing_service import get_effective_price
        prices = []
        for row in listings_raw:
            listing_dict = dict(row)
            effective_price = get_effective_price(listing_dict)
            prices.append(effective_price)

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
@frozen_check
def update_bid():
    try:
        if 'user_id' not in session:
            return jsonify(success=False, message="Authentication required"), 401

        errors = {}
        print(f"[UPDATE_BID] Starting bid update for user {session.get('user_id')}")
        print(f"[UPDATE_BID] Form data: {dict(request.form)}")
    except Exception as e:
        print(f"[UPDATE_BID] Fatal error in initial setup: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify(success=False, message=f"Server error: {str(e)}"), 500

    try:
        bid_id = int(request.form['bid_id'])

        # Extract pricing mode (normalize 'variable' to 'premium_to_spot' for backward compatibility)
        pricing_mode = request.form.get('bid_pricing_mode', 'static').strip()
        if pricing_mode == 'variable':
            pricing_mode = 'premium_to_spot'

        # Extract quantity (use shared bid_quantity field for both modes)
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

    # Get recipient name from user's Account Details (source of truth)
    user_info = cursor.execute(
        'SELECT first_name, last_name FROM users WHERE id = ?',
        (session['user_id'],)
    ).fetchone()

    if not user_info or not user_info['first_name'] or not user_info['last_name']:
        conn.close()
        return jsonify(
            success=False,
            message="Please add your full name in Account Details before updating a bid.",
            redirect_to="/account#personal-info"
        ), 400

    recipient_first = user_info['first_name']
    recipient_last = user_info['last_name']

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
        'SELECT quantity_requested, remaining_quantity FROM bids WHERE id = ?',
        (bid_id,)
    ).fetchone()

    # Calculate quantity fulfilled from existing columns
    quantity_fulfilled = (current_bid['quantity_requested'] - current_bid['remaining_quantity']) if current_bid else 0

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
               recipient_first_name = ?,
               recipient_last_name  = ?,
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
            recipient_first,
            recipient_last,
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

    # Send bid_filled notifications if bid was auto-filled (after commit)
    if match_result.get('notifications'):
        for notif_data in match_result['notifications']:
            try:
                notify_bid_filled(**notif_data)
            except Exception as e:
                print(f"[NOTIFICATION ERROR] Failed to send bid_filled notification: {e}")

    # Calculate effective bid price
    bid_dict = dict(updated_bid) if updated_bid else {}
    effective_price = get_effective_bid_price(bid_dict) if updated_bid else bid_price

    # Get current spot price if variable pricing
    current_spot_price = None
    if pricing_mode == 'premium_to_spot' and pricing_metal:
        current_spot_price = get_spot_price(pricing_metal)

    # Build response message
    if match_result['filled_quantity'] > 0:
        message = f"Bid updated successfully! {match_result['message']}"
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
