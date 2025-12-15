# routes/sell_routes.py

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from database import get_db_connection
from .category_options import get_dropdown_options
from utils.category_manager import get_or_create_category, validate_category_specification
from services.notification_service import notify_bid_filled
from services.spot_price_service import get_current_spot_prices
from services.bucket_price_history_service import update_bucket_price
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
        try:
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

            # ========== NEW: Extract isolated/set/numismatic fields ==========
            is_isolated = request.form.get('is_isolated') == '1'
            is_set = request.form.get('is_set') == '1'
            issue_number = request.form.get('issue_number', '').strip()
            issue_total = request.form.get('issue_total', '').strip()

            # Convert issue numbers to integers if provided
            issue_number = int(issue_number) if issue_number else None
            issue_total = int(issue_total) if issue_total else None

            # Extract title and description
            listing_title = request.form.get('listing_title', '').strip()
            listing_description = request.form.get('listing_description', '').strip()

            # Validate numismatic fields (both or neither)
            if (issue_number and not issue_total) or (not issue_number and issue_total):
                error_msg = "Both issue number and total must be provided, or leave both empty."
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify(success=False, message=error_msg), 400
                flash(error_msg, "error")
                options = get_dropdown_options()
                return render_template('sell.html', **options)

            # Validate issue number <= issue total
            if issue_number and issue_total and issue_number > issue_total:
                error_msg = "Issue number cannot be greater than issue total."
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify(success=False, message=error_msg), 400
                flash(error_msg, "error")
                options = get_dropdown_options()
                return render_template('sell.html', **options)

            # Determine isolated_type
            isolated_type = None
            if is_set:
                is_isolated = True
                isolated_type = 'set'
            elif is_isolated:
                isolated_type = 'one_of_a_kind'

            # Force isolated if numismatic fields are filled
            if issue_number and issue_total:
                is_isolated = True
                if not isolated_type:
                    isolated_type = 'one_of_a_kind'

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
                        error_msg = "Floor price must be greater than zero."
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            return jsonify(success=False, message=error_msg), 400
                        flash(error_msg, "error")
                        options = get_dropdown_options()
                        return render_template('sell.html', **options)
                else:
                    error_msg = "Invalid pricing mode."
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return jsonify(success=False, message=error_msg), 400
                    flash(error_msg, "error")
                    options = get_dropdown_options()
                    return render_template('sell.html', **options)

            except (ValueError, KeyError) as e:
                error_msg = "Invalid quantity or price. Please enter valid numbers."
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify(success=False, message=error_msg), 400
                flash(error_msg, "error")
                options = get_dropdown_options()
                return render_template('sell.html', **options)

            # Extract packaging fields
            packaging_type = request.form.get('packaging_type', '').strip() or None
            packaging_notes = request.form.get('packaging_notes', '').strip() or None

            # Extract additional specification fields
            condition_category = request.form.get('condition_category', '').strip() or None
            series_variant = request.form.get('series_variant', '').strip() or None
            cert_number = request.form.get('cert_number', '').strip() or None
            condition_notes = request.form.get('condition_notes', '').strip() or None

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
                'grade': grade,
                'condition_category': condition_category,
                'series_variant': series_variant
            }

            # Backend validation - ensure all values are from allowed dropdown options
            options = get_dropdown_options()
            is_valid, error_msg = validate_category_specification(category_spec, options)
            if not is_valid:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify(success=False, message=error_msg), 400
                flash(error_msg, "error")
                return render_template('sell.html', **options, prefill=category_spec)

            conn = get_db_connection()


            # --- Handle photo upload(s) ---
            # For sets: use cover_photo, for non-sets: use item_photo
            if is_set:
                # Set listing: require cover photo
                photo_file = request.files.get('cover_photo')
                if not photo_file or photo_file.filename == "":
                    error_msg = "Please upload a cover photo for your set listing."
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return jsonify(success=False, message=error_msg), 400
                    flash(error_msg, "error")
                    options = get_dropdown_options()
                    return render_template('sell.html', **options)
            else:
                # Standard or one-of-a-kind listing: require item photo
                photo_file = request.files.get('item_photo')
                if not photo_file or photo_file.filename == "":
                    error_msg = "Please upload a photo of your item."
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return jsonify(success=False, message=error_msg), 400
                    flash(error_msg, "error")
                    options = get_dropdown_options()
                    return render_template('sell.html', **options)

            if not allowed_file(photo_file.filename):
                error_msg = "Invalid file type. Please upload a JPG, PNG, or GIF image."
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify(success=False, message=error_msg), 400
                flash(error_msg, "error")
                options = get_dropdown_options()
                return render_template('sell.html', **options)

            # Save the main/cover photo
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

            # ========== BUCKET/CATEGORY CREATION WITH ISOLATION LOGIC ==========
            cursor = conn.cursor()

            if is_isolated:
                # ISOLATED LISTING: Always create a new isolated bucket
                # Generate unique integer bucket_id (MAX + 1, same as standard buckets)
                new_bucket = cursor.execute(
                    'SELECT COALESCE(MAX(bucket_id), 0) + 1 AS new_bucket_id FROM categories'
                ).fetchone()
                bucket_id = new_bucket['new_bucket_id']

                # Create new isolated category
                cursor.execute('''
                    INSERT INTO categories (
                        metal, product_line, product_type, weight, purity,
                        mint, year, finish, grade, coin_series, bucket_id, is_isolated,
                        condition_category, series_variant
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ''', (metal, product_line, product_type, weight, purity,
                      mint, year, finish, grade, category_spec.get('coin_series', ''), bucket_id,
                      condition_category, series_variant))

                category_id = cursor.lastrowid
            else:
                # NON-ISOLATED LISTING: Use unified category management (excludes isolated buckets)
                category_id = get_or_create_category(conn, category_spec)

            # Insert listing with pricing mode AND isolated/set/numismatic fields AND title/description
            cursor.execute('''
                INSERT INTO listings (
                    category_id,
                    seller_id,
                    quantity,
                    price_per_coin,
                    pricing_mode,
                    spot_premium,
                    floor_price,
                    pricing_metal,
                    is_isolated,
                    isolated_type,
                    issue_number,
                    issue_total,
                    name,
                    description,
                    packaging_type,
                    packaging_notes,
                    cert_number,
                    condition_notes,
                    active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ''', (
                category_id,
                session['user_id'],
                quantity,
                price_per_coin,
                pricing_mode,
                spot_premium,
                floor_price,
                pricing_metal,
                1 if is_isolated else 0,
                isolated_type,
                issue_number,
                issue_total,
                listing_title,
                listing_description,
                packaging_type,
                packaging_notes,
                cert_number,
                condition_notes
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

            # ========== CREATE SET ITEMS IF THIS IS A SET LISTING ==========
            if is_set:
                # Helper function to save set item photo
                def save_set_item_photo(photo_file):
                    if not photo_file or photo_file.filename == "":
                        return None
                    if not allowed_file(photo_file.filename):
                        return None

                    safe_name = secure_filename(photo_file.filename)
                    base, ext = os.path.splitext(safe_name)
                    candidate = safe_name
                    i = 1
                    while os.path.exists(os.path.join(UPLOAD_FOLDER, candidate)):
                        candidate = f"{base}_{i}{ext}"
                        i += 1

                    photo_path_full = os.path.join(UPLOAD_FOLDER, candidate)
                    photo_file.save(photo_path_full)
                    return f"uploads/listings/{candidate}"  # Relative path for database

                # Item #1 is the main form fields - check for set_item_photo_1
                item_1_photo = request.files.get('set_item_photo_1')
                item_1_photo_path = save_set_item_photo(item_1_photo)

                cursor.execute('''
                    INSERT INTO listing_set_items (
                        listing_id, position_index,
                        metal, product_line, product_type, weight, purity,
                        mint, year, finish, grade, coin_series,
                        photo_path
                    ) VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (listing_id, metal, product_line, product_type, weight, purity,
                      mint, year, finish, grade, category_spec.get('coin_series', ''),
                      item_1_photo_path))

                # Additional set items from form (set_items[N][field])
                position = 1
                import re
                # Find all set item indices
                set_item_indices = set()
                for key in request.form.keys():
                    match = re.match(r'set_items\[(\d+)\]\[', key)
                    if match:
                        set_item_indices.add(int(match.group(1)))

                # Process each set item
                for idx in sorted(set_item_indices):
                    set_metal = request.form.get(f'set_items[{idx}][metal]', '').strip()
                    set_product_line = request.form.get(f'set_items[{idx}][product_line]', '').strip()
                    set_product_type = request.form.get(f'set_items[{idx}][product_type]', '').strip()
                    set_weight = request.form.get(f'set_items[{idx}][weight]', '').strip()
                    set_purity = request.form.get(f'set_items[{idx}][purity]', '').strip()
                    set_mint = request.form.get(f'set_items[{idx}][mint]', '').strip()
                    set_year = request.form.get(f'set_items[{idx}][year]', '').strip()
                    set_finish = request.form.get(f'set_items[{idx}][finish]', '').strip()
                    set_grade = request.form.get(f'set_items[{idx}][grade]', '').strip()
                    set_coin_series = request.form.get(f'set_items[{idx}][coin_series]', '').strip()

                    # Handle photo for this set item
                    set_item_photo = request.files.get(f'set_item_photo_{idx}')
                    set_item_photo_path = save_set_item_photo(set_item_photo)

                    # Backend validation: first 2 items require all fields
                    if position < 2:
                        if not all([set_metal, set_product_line, set_product_type, set_weight,
                                   set_purity, set_mint, set_year, set_finish, set_grade]):
                            error_msg = f"Set item #{position + 1} is missing required specifications."
                            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                                return jsonify(success=False, message=error_msg), 400
                            flash(error_msg, "error")
                            conn.close()
                            options = get_dropdown_options()
                            return render_template('sell.html', **options)

                    # Only insert if at least metal is present (items 3+ can have minimal specs)
                    if set_metal or set_product_line or set_item_photo_path:
                        cursor.execute('''
                            INSERT INTO listing_set_items (
                                listing_id, position_index,
                                metal, product_line, product_type, weight, purity,
                                mint, year, finish, grade, coin_series,
                                photo_path
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (listing_id, position,
                              set_metal, set_product_line, set_product_type, set_weight, set_purity,
                              set_mint, set_year, set_finish, set_grade, set_coin_series,
                              set_item_photo_path))
                        position += 1

            conn.commit()

            # Update bucket price history after creating new listing
            try:
                bucket_id_row = conn.execute(
                    'SELECT bucket_id FROM categories WHERE id = ?',
                    (category_id,)
                ).fetchone()
                if bucket_id_row:
                    bucket_id = bucket_id_row['bucket_id']
                    update_bucket_price(bucket_id)
            except Exception as e:
                # Don't fail the listing creation if price tracking fails
                print(f"[WARNING] Failed to update bucket price: {e}")

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
                'grade': grade,
                'is_isolated': 1 if is_isolated else 0,
                'isolated_type': isolated_type,
                'issue_number': issue_number,
                'issue_total': issue_total
            }

            # Get set items for response if this is a set listing
            set_items_data = []
            if is_set:
                set_items_rows = conn.execute('''
                    SELECT * FROM listing_set_items
                    WHERE listing_id = ?
                    ORDER BY position_index
                ''', (listing_id,)).fetchall()
                set_items_data = [dict(row) for row in set_items_rows]

            conn.close()

            # Check if AJAX request
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify(
                    success=True,
                    message='Your item was successfully listed!',
                    listing=listing_data,
                    category=category_dict,
                    set_items=set_items_data
                )

            return "✅ Your item was successfully listed!"

        except Exception as e:
            # Catch any unexpected errors and return proper JSON for AJAX requests
            import traceback
            error_trace = traceback.format_exc()
            print(f"[ERROR] Sell listing error: {error_trace}")

            error_msg = f"An error occurred while creating your listing: {str(e)}"
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify(success=False, message=error_msg), 500

            flash(error_msg, "error")
            options = get_dropdown_options()
            return render_template('sell.html', **options)

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
        'grade': request.args.get('grade', ''),
        'condition_category': request.args.get('condition_category', ''),
        'series_variant': request.args.get('series_variant', '')
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
        packaging_types=options['packaging_types'],
        condition_categories=options['condition_categories'],
        series_variants=options['series_variants'],
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
