# routes/sell_routes.py

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from database import get_db_connection
from .category_options import get_dropdown_options
from utils.category_manager import get_or_create_category, validate_category_specification
from services.notification_service import notify_bid_filled
from services.spot_price_service import get_current_spot_prices
from werkzeug.utils import secure_filename
import os
import sqlite3




sell_bp = Blueprint('sell', __name__)



# Folder where listing photos will be stored (relative to project root)
UPLOAD_FOLDER = os.path.join("static", "uploads", "listings")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS



# --- Sell Route ---
@sell_bp.route('/sell', methods=['GET', 'POST'])
def sell():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        # Extract form data
        metal = request.form.get('metal', '').strip()
        product_line = request.form.get('product_line', '').strip()
        product_type = request.form.get('product_type', '').strip()
        weight = request.form.get('weight', '').strip()
        purity = request.form.get('purity', '').strip()
        mint = request.form.get('mint', '').strip()
        year = request.form.get('year', '').strip()
        finish = request.form.get('finish', '').strip()
        grade = request.form.get('grade', '').strip()

        # Extract pricing mode
        pricing_mode = request.form.get('pricing_mode', 'static').strip()

        # Validate and extract pricing parameters based on mode
        try:
            quantity = int(request.form['quantity'])

            if pricing_mode == 'static':
                # Static mode: require price_per_coin
                price_per_coin = float(request.form['price_per_coin'])
                spot_premium = None
                floor_price = None
                pricing_metal = None
            elif pricing_mode == 'premium_to_spot':
                # Premium-to-spot mode: require premium and floor
                spot_premium = float(request.form.get('spot_premium', 0))
                floor_price = float(request.form.get('floor_price', 0))
                pricing_metal = request.form.get('pricing_metal', metal).strip()

                # For premium-to-spot, price_per_coin is not set by user
                # We'll set it to floor_price as a fallback
                price_per_coin = floor_price

                # Validation for premium-to-spot
                if floor_price <= 0:
                    flash("Floor price must be greater than zero.", "error")
                    options = get_dropdown_options()
                    return render_template('sell.html', **options)
            else:
                flash("Invalid pricing mode.", "error")
                options = get_dropdown_options()
                return render_template('sell.html', **options)

        except (ValueError, KeyError) as e:
            flash("Invalid quantity or price. Please enter valid numbers.", "error")
            options = get_dropdown_options()
            return render_template('sell.html', **options)

        graded = int(request.form.get('graded', 0))
        grading_service = request.form.get('grading_service') if graded else None

        # Build category specification
        category_spec = {
            'metal': metal,
            'product_line': product_line,
            'product_type': product_type,
            'weight': weight,
            'purity': purity,
            'mint': mint,
            'year': year,
            'finish': finish,
            'grade': grade
        }

        # Backend validation - ensure all values are from allowed dropdown options
        options = get_dropdown_options()
        is_valid, error_msg = validate_category_specification(category_spec, options)
        if not is_valid:
            flash(error_msg, "error")
            return render_template('sell.html', **options, prefill=category_spec)

        conn = get_db_connection()


        # --- Handle required item photo upload ---
        photo_file = request.files.get('item_photo')
        if not photo_file or photo_file.filename == "":
            flash("Please upload a photo of your item.", "error")
            options = get_dropdown_options()
            return render_template(
                'sell.html',
                metals=options['metals'],
                product_lines=options['product_lines'],
                product_types=options['product_types'],
                weights=options['weights'],
                purities=options['purities'],
                mints=options['mints'],
                years=options['years'],
                finishes=options['finishes'],
                grades=options['grades']
            )

        if not allowed_file(photo_file.filename):
            flash("Invalid file type. Please upload a JPG, PNG, or GIF image.", "error")
            options = get_dropdown_options()
            return render_template(
                'sell.html',
                metals=options['metals'],
                product_lines=options['product_lines'],
                product_types=options['product_types'],
                weights=options['weights'],
                purities=options['purities'],
                mints=options['mints'],
                years=options['years'],
                finishes=options['finishes'],
                grades=options['grades']
            )

        # Save the file
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        safe_name = secure_filename(photo_file.filename)

        # Make filename unique by adding numeric suffix if needed
        base, ext = os.path.splitext(safe_name)
        candidate = safe_name
        i = 1
        while os.path.exists(os.path.join(UPLOAD_FOLDER, candidate)):
            candidate = f"{base}_{i}{ext}"
            i += 1

        photo_filename = candidate
        photo_path = os.path.join(UPLOAD_FOLDER, photo_filename)
        photo_file.save(photo_path)

        # Use unified category management - handles bucket_id automatically
        category_id = get_or_create_category(conn, category_spec)

        # Insert listing with pricing mode fields
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO listings (
                category_id,
                seller_id,
                quantity,
                price_per_coin,
                graded,
                grading_service,
                pricing_mode,
                spot_premium,
                floor_price,
                pricing_metal,
                active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        ''', (
            category_id,
            session['user_id'],
            quantity,
            price_per_coin,
            graded,
            grading_service,
            pricing_mode,
            spot_premium,
            floor_price,
            pricing_metal
        ))

        # Get the newly created listing ID
        listing_id = cursor.lastrowid

        # Insert photo into listing_photos table
        # Store path relative to static folder: uploads/listings/filename.jpg
        file_path = f"uploads/listings/{photo_filename}"
        cursor.execute('''
            INSERT INTO listing_photos (listing_id, uploader_id, file_path)
            VALUES (?, ?, ?)
        ''', (listing_id, session['user_id'], file_path))

        conn.commit()

        # Get category data and listing data for response
        category_row = conn.execute('''
            SELECT * FROM categories WHERE id = ?
        ''', (category_id,)).fetchone()

        # Convert Row to dict BEFORE closing connection
        category_dict = dict(category_row) if category_row else {}

        # Calculate effective price for premium-to-spot listings
        effective_price = None
        if pricing_mode == 'premium_to_spot':
            from services.pricing_service import get_effective_price
            # Build a listing dict for pricing calculation
            temp_listing = {
                'pricing_mode': pricing_mode,
                'price_per_coin': price_per_coin,
                'spot_premium': spot_premium,
                'floor_price': floor_price,
                'pricing_metal': pricing_metal or metal,
                'metal': metal,
                'weight': weight
            }
            effective_price = get_effective_price(temp_listing)

        # Build listing data for response
        listing_data = {
            'id': listing_id,
            'quantity': quantity,
            'price_per_coin': price_per_coin,
            'graded': graded,
            'grading_service': grading_service,
            'pricing_mode': pricing_mode,
            'spot_premium': spot_premium,
            'floor_price': floor_price,
            'pricing_metal': pricing_metal,
            'effective_price': effective_price,
            'metal': metal,
            'product_line': product_line,
            'product_type': product_type,
            'weight': weight,
            'year': year,
            'purity': purity,
            'mint': mint,
            'finish': finish,
            'grade': grade
        }

        conn.close()

        # Check if AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(
                success=True,
                message='Your item was successfully listed!',
                listing=listing_data,
                category=category_dict
            )

        return "✅ Your item was successfully listed!"

    # GET request - extract URL parameters for pre-population
    prefill = {
        'metal': request.args.get('metal', ''),
        'product_line': request.args.get('product_line', ''),
        'product_type': request.args.get('product_type', ''),
        'weight': request.args.get('weight', ''),
        'purity': request.args.get('purity', ''),
        'mint': request.args.get('mint', ''),
        'year': request.args.get('year', ''),
        'finish': request.args.get('finish', ''),
        'grade': request.args.get('grade', '')
    }

    options = get_dropdown_options()

    return render_template(
        'sell.html',
        metals=options['metals'],
        product_lines=options['product_lines'],
        product_types=options['product_types'],
        weights=options['weights'],
        purities=options['purities'],
        mints=options['mints'],
        years=options['years'],
        finishes=options['finishes'],
        grades=options['grades'],
        prefill=prefill
    )




@sell_bp.route('/upload_tracking/<int:order_id>', methods=['POST'])
def upload_tracking(order_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    tracking_number = request.form.get('tracking_number')
    carrier = request.form.get('carrier')

    if not tracking_number or not carrier:
        flash('Please provide tracking number and carrier.')
        return redirect(url_for('sell.sold_orders'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Insert or update tracking info
    cursor.execute('''
        INSERT INTO tracking (order_id, carrier, tracking_number, tracking_status)
        VALUES (?, ?, ?, 'In Transit')
        ON CONFLICT(order_id) DO UPDATE SET
            carrier=excluded.carrier,
            tracking_number=excluded.tracking_number,
            tracking_status='In Transit'
    ''', (order_id, carrier, tracking_number))

    # Update order status to 'Awaiting Delivery'
    cursor.execute('''
        UPDATE orders
        SET status = 'Awaiting Delivery'
        WHERE id = ?
    ''', (order_id,))

    conn.commit()
    conn.close()

    flash('Tracking number uploaded successfully!')
    return redirect(url_for('sell.sold_orders'))


@sell_bp.route('/sold_orders')
def sold_orders():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    conn = get_db_connection()


    # Fetch sold orders for this seller
    sold_orders = conn.execute('''
        SELECT orders.id, orders.quantity, orders.price, orders.status, orders.order_date,
            orders.shipping_address,
            categories.metal, categories.product_type,
            users.username AS buyer_username,
            (
                SELECT 1 FROM ratings
                WHERE ratings.order_id = orders.id AND ratings.rater_id = ?
            ) AS already_rated
        FROM orders
        JOIN listings ON orders.listing_id = listings.id
        JOIN categories ON listings.category_id = categories.id
        JOIN users ON orders.buyer_id = users.id
        WHERE listings.seller_id = ?
        ORDER BY orders.order_date DESC
    ''', (session['user_id'], session['user_id'])).fetchall()



    conn.close()

    return render_template('sold_orders.html', sold_orders=sold_orders)


@sell_bp.route('/accept_bid/<int:bucket_id>', methods=['POST'])
def accept_bid(bucket_id):
    from flask import flash, redirect, url_for, session, request
    if 'user_id' not in session:
        flash("🔒 Please log in to accept bids.", "warning")
        return redirect(url_for('auth.login'))

    seller_id = session['user_id']
    selected_bid_ids = request.form.getlist('selected_bids')

    if not selected_bid_ids:
        flash("⚠️ No bids selected.", "warning")
        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    conn = get_db_connection()
    c = conn.cursor()

    total_accepted = 0

    # Collect notification data (will send after commit to avoid database locking)
    notifications_to_send = []

    for bid_id in selected_bid_ids:
        accepted_qty = request.form.get(f'quantity_{bid_id}')
        if not accepted_qty or int(accepted_qty) <= 0:
            continue

        accepted_qty = int(accepted_qty)

        bid = c.execute('''
            SELECT buyer_id, category_id, quantity_requested, price_per_coin, status
            FROM bids WHERE id = ?
        ''', (bid_id,)).fetchone()

        if not bid or bid['status'].lower() not in ['open', 'pending', 'partially filled']:
            continue

        # PREVENT SELF-ACCEPTING: Skip bids from the current user
        if bid['buyer_id'] == seller_id:
            continue

        buyer_id = bid['buyer_id']
        category_id = bid['category_id']
        max_qty = bid['quantity_requested']
        price = bid['price_per_coin']

        qty_to_fulfill = min(accepted_qty, max_qty)

        # Create an order directly
        c.execute('''
            INSERT INTO orders (buyer_id, seller_id, category_id, quantity, price_each, status)
            VALUES (?, ?, ?, ?, ?, 'pending_shipment')
        ''', (buyer_id, seller_id, category_id, qty_to_fulfill, price))

        order_id = c.lastrowid

        # Update the bid
        remaining = max_qty - qty_to_fulfill
        is_partial = remaining > 0
        if remaining == 0:
            c.execute('UPDATE bids SET quantity_requested = 0, active = 0, status = "filled" WHERE id = ?', (bid_id,))
        else:
            c.execute('UPDATE bids SET quantity_requested = ?, status = "partially filled" WHERE id = ?', (remaining, bid_id))

        # Build item description from category
        category = c.execute('SELECT * FROM categories WHERE id = ?', (category_id,)).fetchone()
        item_desc_parts = []
        if category:
            if category['metal']:
                item_desc_parts.append(category['metal'])
            if category['product_line']:
                item_desc_parts.append(category['product_line'])
            if category['weight']:
                item_desc_parts.append(category['weight'])
            if category['year']:
                item_desc_parts.append(category['year'])
        item_description = ' '.join(item_desc_parts) if item_desc_parts else 'Item'

        # Collect notification data (will send after commit)
        notifications_to_send.append({
            'buyer_id': buyer_id,
            'order_id': order_id,
            'bid_id': bid_id,
            'item_description': item_description,
            'quantity_filled': qty_to_fulfill,
            'price_per_unit': price,
            'total_amount': qty_to_fulfill * price,
            'is_partial': is_partial,
            'remaining_quantity': remaining
        })

        total_accepted += qty_to_fulfill

    conn.commit()
    conn.close()

    # Send notifications AFTER commit (avoids database locking)
    for notif_data in notifications_to_send:
        try:
            notify_bid_filled(**notif_data)
        except Exception as notify_error:
            print(f"[ERROR] Failed to notify buyer {notif_data['buyer_id']}: {notify_error}")

    if total_accepted > 0:
        flash(f"✅ You accepted bids totaling {total_accepted} coin(s).", "success")
    else:
        flash("⚠️ No bids were accepted due to missing quantities.", "warning")

    return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))
