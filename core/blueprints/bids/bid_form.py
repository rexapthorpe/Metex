"""
Bid Form Route

Handles the unified bid form endpoint for creating and editing bids.
"""

from flask import render_template, session, url_for, jsonify
from database import get_db_connection
from services.spot_price_service import get_spot_price

from . import bid_bp


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
    # Debug logging for session
    print(f"[DEBUG] /bids/form session keys: {list(session.keys())}")
    print(f"[DEBUG] /bids/form user_id in session: {'user_id' in session}")
    if 'user_id' in session:
        print(f"[DEBUG] /bids/form user_id value: {session['user_id']}")

    if 'user_id' not in session:
        print(f"[ERROR] /bids/form - No user_id in session. Session: {dict(session)}")
        return jsonify(error="Authentication required. Please log in to place a bid."), 401

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

        # Parse delivery_address to populate individual fields.
        # Current JS format (name is stored separately, NOT in this string):
        #   "Address Line 1 • City, State ZIP"          (no line2)
        #   "Address Line 1 • Address Line 2 • City, State ZIP"  (with line2)
        parsed_address = {}
        if bid['delivery_address']:
            parts = [p.strip() for p in bid['delivery_address'].split('•')]

            if len(parts) >= 1:
                parsed_address['line1'] = parts[0]

            if len(parts) == 2:
                # "line1 • City, State ZIP"
                city_state_zip = parts[1]
            elif len(parts) >= 3:
                # "line1 • line2 • City, State ZIP"
                parsed_address['line2'] = parts[1]
                city_state_zip = parts[-1]
            else:
                city_state_zip = ''

            # Parse "City, State ZIP" → city, state, zip
            # Split on first comma only: ["City", "State ZIP"]
            if city_state_zip:
                comma_parts = [p.strip() for p in city_state_zip.split(',', 1)]
                if comma_parts:
                    parsed_address['city'] = comma_parts[0]
                if len(comma_parts) >= 2:
                    # "State ZIP" → split on whitespace
                    state_zip_parts = comma_parts[1].split(None, 1)
                    parsed_address['state'] = state_zip_parts[0] if state_zip_parts else ''
                    parsed_address['zip'] = state_zip_parts[1].strip() if len(state_zip_parts) > 1 else ''

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
