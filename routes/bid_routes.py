# routes/bid_routes.py

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from database import get_db_connection

bid_bp = Blueprint('bid', __name__, url_prefix='/bids')

@bid_bp.route('/place_bid/<int:bucket_id>', methods=['POST'])
def place_bid(bucket_id):
    if 'user_id' not in session:
        flash("❌ You must be logged in to place a bid.", "error")
        return redirect(url_for('auth.login'))

    try:
        bid_price        = float(request.form['bid_price'])
        bid_quantity     = int(request.form['bid_quantity'])
        delivery_address = request.form['delivery_address'].strip()
        requires_grading = request.form.get('requires_grading') == 'yes'
        preferred_grader = request.form.get('preferred_grader') if requires_grading else None
    except (ValueError, KeyError):
        flash("❌ Invalid form data.", "error")
        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    if bid_price <= 0 or bid_quantity <= 0:
        flash("❌ Bid price and quantity must be greater than zero.", "error")
        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''
        INSERT INTO bids (
            category_id, buyer_id, quantity_requested, price_per_coin,
            remaining_quantity, active, requires_grading, preferred_grader,
            delivery_address, status
        ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, 'Open')
        ''',
        (
            bucket_id,
            session['user_id'],
            bid_quantity,
            bid_price,
            bid_quantity,
            1 if requires_grading else 0,
            preferred_grader,
            delivery_address
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
        bid_price = float(request.form['bid_price'])
        bid_quantity = int(request.form['bid_quantity'])
        # May be empty string
        delivery_address = (request.form.get('delivery_address') or '').strip()

        requires_grading = (request.form.get('requires_grading') == 'yes')
        preferred_grader = request.form.get('preferred_grader')
        if not requires_grading:
            preferred_grader = None
    except (ValueError, KeyError):
        return jsonify(success=False, message="Invalid input data"), 400

    # Server-side rounding to tick 0.01
    bid_price = round(bid_price + 1e-9, 2)

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

    cursor.execute(
        '''
        UPDATE bids
           SET price_per_coin      = ?,
               quantity_requested  = ?,
               remaining_quantity  = ?,
               requires_grading    = ?,
               preferred_grader    = ?,
               delivery_address    = ?,
               status              = 'Open',
               active              = 1
         WHERE id = ? AND buyer_id = ?
        ''',
        (
            bid_price,
            bid_quantity,
            bid_quantity,
            1 if requires_grading else 0,
            preferred_grader,
            new_address,
            bid_id,
            session['user_id']
        )
    )
    conn.commit()
    conn.close()

    return jsonify(success=True, message="Bid updated successfully")


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

    total_filled = 0

    for bid_id in selected_bid_ids:
        # Load bid
        bid = cursor.execute('''
            SELECT id, category_id, quantity_requested, remaining_quantity,
                   price_per_coin, buyer_id, delivery_address, status
            FROM bids
            WHERE id = ?
        ''', (bid_id,)).fetchone()
        if not bid:
            continue

        category_id      = bid['category_id']
        buyer_id         = bid['buyer_id']
        price_limit      = bid['price_per_coin']
        delivery_address = bid['delivery_address']

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

        # Seller's listings that match price
        listings = cursor.execute('''
            SELECT id, quantity, price_per_coin
            FROM listings
            WHERE category_id = ?
              AND seller_id   = ?
              AND price_per_coin <= ?
              AND active = 1
            ORDER BY price_per_coin ASC
        ''', (category_id, seller_id, price_limit)).fetchall()

        filled = 0
        for listing in listings:
            if filled >= quantity_needed:
                break
            if listing['quantity'] <= 0:
                continue

            fill_qty = min(listing['quantity'], quantity_needed - filled)

            # Upsert into buyer's cart
            existing = cursor.execute(
                'SELECT quantity FROM cart WHERE user_id = ? AND listing_id = ?',
                (buyer_id, listing['id'])
            ).fetchone()

            if existing:
                cursor.execute(
                    'UPDATE cart SET quantity = ? WHERE user_id = ? AND listing_id = ?',
                    (existing['quantity'] + fill_qty, buyer_id, listing['id'])
                )
            else:
                cursor.execute(
                    'INSERT INTO cart (user_id, listing_id, quantity) VALUES (?, ?, ?)',
                    (buyer_id, listing['id'], fill_qty)
                )

            # Update listing inventory
            new_list_qty = listing['quantity'] - fill_qty
            if new_list_qty <= 0:
                cursor.execute('UPDATE listings SET quantity = 0, active = 0 WHERE id = ?', (listing['id'],))
            else:
                cursor.execute('UPDATE listings SET quantity = ? WHERE id = ?', (new_list_qty, listing['id']))

            # Create order line for this fill
            cursor.execute('''
                INSERT INTO orders (listing_id, buyer_id, seller_id, quantity, price_each, status, delivery_address)
                VALUES (?, ?, ?, ?, ?, 'Pending Shipment', ?)
            ''', (listing['id'], buyer_id, seller_id, fill_qty, listing['price_per_coin'], delivery_address))

            filled += fill_qty

        total_filled += filled

        # Update bid status / remaining
        new_remaining = remaining_qty - filled
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


