"""
Place Bid Routes

Routes for placing and creating bids.

Routes:
- POST /bids/place_bid/<bucket_id>: place_bid - Traditional form-based bid placement
- POST /bids/create/<bucket_id>: create_bid_unified - AJAX-based unified modal bid creation
"""

from flask import request, redirect, url_for, session, flash, jsonify
from database import get_db_connection
from services.notification_service import notify_bid_filled
from services.notification_types import notify_bid_placed, notify_bid_on_bucket
from services.pricing_service import get_effective_bid_price
from utils.auth_utils import frozen_check

from . import bid_bp
from .auto_match import auto_match_bid_to_listings


@bid_bp.route('/place_bid/<int:bucket_id>', methods=['POST'])
@frozen_check
def place_bid(bucket_id):
    if 'user_id' not in session:
        flash("You must be logged in to place a bid.", "error")
        return redirect(url_for('auth.login'))

    try:
        # Extract pricing mode (normalize 'variable' to 'premium_to_spot' for backward compatibility)
        pricing_mode = request.form.get('bid_pricing_mode', 'static').strip()
        if pricing_mode == 'variable':
            pricing_mode = 'premium_to_spot'

        # Extract quantity (use shared bid_quantity field for both modes)
        bid_quantity = int(request.form.get('bid_quantity', 1))

        delivery_address = request.form['delivery_address'].strip()
        requires_grading = request.form.get('requires_grading') == 'yes'
        random_year = 1 if request.form.get('random_year') == 'on' else 0

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
        flash(f"Invalid form data: {str(e)}", "error")
        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    # Validate based on pricing mode
    if pricing_mode == 'premium_to_spot':
        if ceiling_price <= 0:
            flash("Max price (ceiling) must be greater than zero for premium-to-spot bids.", "error")
            return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))
        if spot_premium < 0:
            flash("Premium cannot be negative.", "error")
            return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))
    else:
        if bid_price <= 0:
            flash("Bid price must be greater than zero.", "error")
            return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    if bid_quantity <= 0:
        flash("Bid quantity must be greater than zero.", "error")
        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    # Get recipient name from user's Account Details (source of truth)
    conn = get_db_connection()
    cursor = conn.cursor()

    user_info = cursor.execute(
        'SELECT first_name, last_name FROM users WHERE id = ?',
        (session['user_id'],)
    ).fetchone()

    if not user_info or not user_info['first_name'] or not user_info['last_name']:
        conn.close()
        flash("Please add your full name in Account Details before placing a bid.", "error")
        return redirect('/account#personal-info')

    recipient_first = user_info['first_name']
    recipient_last = user_info['last_name']

    cursor.execute(
        '''
        INSERT INTO bids (
            category_id, buyer_id, quantity_requested, price_per_coin,
            remaining_quantity, active, requires_grading,
            delivery_address, status,
            pricing_mode, spot_premium, ceiling_price, pricing_metal,
            recipient_first_name, recipient_last_name, random_year
        ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, 'Open', ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            bucket_id,
            session['user_id'],
            bid_quantity,
            bid_price,
            bid_quantity,
            1 if requires_grading else 0,
            delivery_address,
            pricing_mode,
            spot_premium,
            ceiling_price,
            pricing_metal,
            recipient_first,
            recipient_last,
            random_year
        )
    )
    conn.commit()
    conn.close()

    flash("Your bid was placed successfully!", "success")
    return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))


@bid_bp.route('/create/<int:bucket_id>', methods=['POST'])
@frozen_check
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
        # Extract pricing mode (normalize 'variable' to 'premium_to_spot' for backward compatibility)
        pricing_mode = request.form.get('bid_pricing_mode', 'static').strip()
        if pricing_mode == 'variable':
            pricing_mode = 'premium_to_spot'

        # Extract quantity (use shared bid_quantity field for both modes)
        bid_quantity_str = request.form.get('bid_quantity', '').strip()
        bid_quantity = int(bid_quantity_str) if bid_quantity_str else 0

        delivery_address = request.form.get('delivery_address', '').strip()
        requires_grading = request.form.get('requires_grading') == 'yes'
        random_year = 1 if request.form.get('random_year') == 'on' else 0

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

    # Get recipient name from user's Account Details (source of truth)
    conn = get_db_connection()
    cursor = conn.cursor()

    user_info = cursor.execute(
        'SELECT first_name, last_name FROM users WHERE id = ?',
        (session['user_id'],)
    ).fetchone()

    if not user_info or not user_info['first_name'] or not user_info['last_name']:
        conn.close()
        return jsonify(
            success=False,
            message="Please add your full name in Account Details before placing a bid.",
            redirect_to="/account#personal-info"
        ), 400

    recipient_first = user_info['first_name']
    recipient_last = user_info['last_name']

    # Insert bid into database
    try:
        cursor.execute(
            '''
            INSERT INTO bids (
                category_id, buyer_id, quantity_requested, price_per_coin,
                remaining_quantity, active, requires_grading,
                delivery_address, status,
                pricing_mode, spot_premium, ceiling_price, pricing_metal,
                recipient_first_name, recipient_last_name, random_year
            ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, 'Open', ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                bucket_id,
                session['user_id'],
                bid_quantity,
                bid_price,
                bid_quantity,  # remaining_quantity starts equal to quantity_requested
                1 if requires_grading else 0,
                delivery_address,
                pricing_mode,
                spot_premium,
                ceiling_price,
                pricing_metal,
                recipient_first,
                recipient_last,
                random_year
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

        # Get bucket info for item description (before closing connection)
        bucket_info = conn.execute('''
            SELECT metal, product_type, product_line, weight, year
            FROM categories WHERE id = ?
        ''', (bucket_id,)).fetchone()

        # Get all unique sellers with active listings in this bucket (for notifications)
        # Get bidder username for the notification
        bidder_info = conn.execute('SELECT username FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        bidder_username = bidder_info['username'] if bidder_info else 'Someone'

        sellers = conn.execute('''
            SELECT DISTINCT l.seller_id
            FROM listings l
            WHERE l.category_id = ?
              AND l.active = 1
              AND l.quantity > 0
              AND l.seller_id != ?
        ''', (bucket_id, session['user_id'])).fetchall()

        # Fetch spot prices from DB *before* closing the connection so that
        # effective_price uses the same authoritative prices as auto_match.
        spot_prices_rows = conn.execute(
            'SELECT metal, price_usd_per_oz FROM spot_prices'
        ).fetchall()
        db_spot_prices = {row['metal'].lower(): row['price_usd_per_oz'] for row in spot_prices_rows}

        conn.close()

        # Calculate effective bid price: min(spot + premium, ceiling).
        # Pass the DB spot prices explicitly to avoid falling back to the external
        # spot-price service (which may be unavailable and would return ceiling instead).
        bid_dict = dict(created_bid) if created_bid else {}
        effective_price = get_effective_bid_price(bid_dict, spot_prices=db_spot_prices) if created_bid else bid_price

        # Expose the current spot price for the success modal display
        current_spot_price = db_spot_prices.get(pricing_metal.lower()) if pricing_metal else None

        # Build item description from bucket info
        item_desc_parts = []
        if bucket_info:
            if bucket_info['metal']:
                item_desc_parts.append(bucket_info['metal'])
            if bucket_info['product_line']:
                item_desc_parts.append(bucket_info['product_line'])
            if bucket_info['weight']:
                item_desc_parts.append(bucket_info['weight'])
            if bucket_info['year']:
                item_desc_parts.append(str(bucket_info['year']))
        item_description = ' '.join(item_desc_parts) if item_desc_parts else 'Item'

        # Send notifications (after connection closed)
        # 1. Notify the bidder that their bid was placed
        try:
            notify_bid_placed(
                bidder_id=session['user_id'],
                bid_id=new_bid_id,
                bucket_id=bucket_id,
                item_description=item_description,
                quantity=bid_quantity,
                price_per_unit=effective_price
            )
        except Exception as e:
            print(f"[NOTIFICATION ERROR] Failed to send bid_placed notification: {e}")

        # 2. Notify sellers in this bucket about the new bid
        try:
            for seller in sellers:
                notify_bid_on_bucket(
                    seller_id=seller['seller_id'],
                    bidder_username=bidder_username,
                    bucket_id=bucket_id,
                    item_description=item_description,
                    bid_price=effective_price,
                    quantity=bid_quantity
                )
        except Exception as e:
            print(f"[NOTIFICATION ERROR] Failed to send bid_on_bucket notifications: {e}")

        # 3. If bid was auto-filled, notify the buyer
        if match_result.get('notifications'):
            for notif_data in match_result['notifications']:
                try:
                    notify_bid_filled(**notif_data)
                except Exception as e:
                    print(f"[NOTIFICATION ERROR] Failed to send bid_filled notification: {e}")

        # Build response message
        if pricing_mode == 'premium_to_spot':
            base_message = f"Your variable bid (effective price: ${effective_price:.2f}) for {bid_quantity} item(s) was placed successfully!"
        else:
            base_message = f"Your bid of ${bid_price:.2f} for {bid_quantity} item(s) was placed successfully!"

        if match_result['filled_quantity'] > 0:
            # Bid was filled (fully or partially)
            full_message = f"{base_message}\n\n{match_result['message']}"
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
        try:
            conn.rollback()
            conn.close()
        except:
            pass  # Connection may already be closed
        return jsonify(success=False, message=f"Database error: {str(e)}"), 500
