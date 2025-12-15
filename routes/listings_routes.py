
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
from database import get_db_connection
from .category_options import get_dropdown_options
from utils.category_manager import get_or_create_category, validate_category_specification
from services.pricing_service import get_effective_price
from services.spot_price_service import get_current_spot_prices, get_spot_price
from services.bucket_price_history_service import update_bucket_price
from werkzeug.utils import secure_filename
import sqlite3
import os

listings_bp = Blueprint('listings', __name__)

# Photo upload settings
UPLOAD_FOLDER = os.path.join("static", "uploads", "listings")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@listings_bp.route('/edit_listing/<int:listing_id>', methods=['GET', 'POST'])
def edit_listing(listing_id):
    import time
    start_time = time.time()

    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    # Always use context manager so the connection is closed even on error
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row

        # ---- Load the listing (shared by GET and POST) ----
        query_start = time.time()
        listing = conn.execute(
            '''
            SELECT
                l.id          AS listing_id,
                l.quantity,
                l.price_per_coin,
                l.pricing_mode,
                l.spot_premium,
                l.floor_price,
                l.pricing_metal,
                l.graded      AS graded,
                l.grading_service,
                lp.file_path  AS photo_path,
                c.id          AS category_id,
                c.metal,
                c.product_line,
                c.product_type,
                c.purity,
                c.weight,
                c.mint,
                c.year,
                c.finish,
                c.grade
            FROM listings l
            JOIN categories c       ON l.category_id = c.id
            LEFT JOIN listing_photos lp ON lp.listing_id = l.id
            WHERE l.id = ? AND l.seller_id = ?
            ''',
            (listing_id, session['user_id'])
        ).fetchone()
        print(f"[PERF] Listing query took: {time.time() - query_start:.3f}s")

        if not listing:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'message': 'Listing not found or unauthorized'}), 404
            return "Listing not found or unauthorized", 404

        # ===================================================
        # POST: update listing, creating/reusing categories
        # ===================================================
        if request.method == 'POST':
            try:
                graded = 1 if request.form.get('graded') == 'yes' else 0
                grading_service = request.form.get('grading_service') if graded else None
                new_quantity = int(request.form['quantity'])

                # Extract category fields FIRST (needed for pricing_metal default)
                metal        = request.form.get('metal', '').strip()
                product_line = request.form.get('product_line', '').strip()
                product_type = request.form.get('product_type', '').strip()
                weight       = request.form.get('weight', '').strip()
                purity       = request.form.get('purity', '').strip()
                mint         = request.form.get('mint', '').strip()
                year         = request.form.get('year', '').strip()
                finish       = request.form.get('finish', '').strip()
                grade        = request.form.get('grade', '').strip()

                # Extract pricing mode
                pricing_mode = request.form.get('pricing_mode', 'static').strip()

                # Extract pricing parameters based on mode
                if pricing_mode == 'static':
                    # Static mode: require price_per_coin
                    price_per_coin_str = request.form.get('price_per_coin', '').strip()
                    # Treat empty or "0.00" as invalid
                    if not price_per_coin_str or price_per_coin_str == '0.00' or float(price_per_coin_str) <= 0:
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            return jsonify({'message': 'Price per coin is required for static pricing'}), 400
                        return 'Price per coin is required for static pricing', 400
                    new_price = float(price_per_coin_str)
                    spot_premium = None
                    floor_price = None
                    pricing_metal = None
                elif pricing_mode == 'premium_to_spot':
                    # Premium-to-spot mode: require premium and floor
                    spot_premium_str = request.form.get('spot_premium', '').strip()
                    floor_price_str = request.form.get('floor_price', '').strip()

                    # Validate premium (can be 0 or positive)
                    if not spot_premium_str:
                        spot_premium_str = '0.00'
                    spot_premium = float(spot_premium_str)

                    # Validate floor price (must be positive)
                    if not floor_price_str or floor_price_str == '0.00' or float(floor_price_str) <= 0:
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            return jsonify({'message': 'Floor price must be greater than 0 for premium-to-spot pricing'}), 400
                        return 'Floor price must be greater than 0 for premium-to-spot pricing', 400
                    floor_price = float(floor_price_str)

                    pricing_metal = request.form.get('pricing_metal', metal).strip()
                    # For premium-to-spot, price_per_coin will be calculated dynamically
                    # Store the floor price as the base price_per_coin for backwards compatibility
                    new_price = floor_price
                else:
                    # Default to static if invalid mode
                    pricing_mode = 'static'
                    new_price = float(request.form.get('price_per_coin', 0))
                    spot_premium = None
                    floor_price = None
                    pricing_metal = None

                # Build category specification (category fields already extracted above)
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
                valid_options = get_dropdown_options()
                is_valid, error_msg = validate_category_specification(category_spec, valid_options)
                if not is_valid:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return jsonify({'message': error_msg}), 400
                    return error_msg, 400

                cur = conn.cursor()

                # Use unified category management - handles bucket_id automatically
                new_cat_id = get_or_create_category(conn, category_spec)

                # ---- Optional: photo upload ----
                photo_file = request.files.get('item_photo')
                if photo_file and photo_file.filename and allowed_file(photo_file.filename):
                    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                    safe_name = secure_filename(photo_file.filename)

                    base, ext = os.path.splitext(safe_name)
                    candidate = safe_name
                    i = 1
                    while os.path.exists(os.path.join(UPLOAD_FOLDER, candidate)):
                        candidate = f"{base}_{i}{ext}"
                        i += 1

                    photo_filename = candidate
                    photo_path = os.path.join(UPLOAD_FOLDER, photo_filename)
                    photo_file.save(photo_path)

                    file_path = f"uploads/listings/{photo_filename}"

                    existing_photo = conn.execute(
                        'SELECT id FROM listing_photos WHERE listing_id = ?',
                        (listing_id,)
                    ).fetchone()

                    if existing_photo:
                        conn.execute(
                            '''
                            UPDATE listing_photos
                               SET file_path = ?, uploader_id = ?
                             WHERE listing_id = ?
                            ''',
                            (file_path, session['user_id'], listing_id)
                        )
                    else:
                        conn.execute(
                            '''
                            INSERT INTO listing_photos (listing_id, uploader_id, file_path)
                            VALUES (?, ?, ?)
                            ''',
                            (listing_id, session['user_id'], file_path)
                        )

                # ---- Update listings row itself ----
                # Ensure quantity is valid (prevent accidental deactivation)
                if new_quantity < 1:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return jsonify({'message': 'Quantity must be at least 1'}), 400
                    return 'Quantity must be at least 1', 400

                conn.execute(
                    '''
                    UPDATE listings
                       SET category_id     = ?,
                           quantity        = ?,
                           price_per_coin  = ?,
                           pricing_mode    = ?,
                           spot_premium    = ?,
                           floor_price     = ?,
                           pricing_metal   = ?,
                           graded          = ?,
                           grading_service = ?,
                           active          = 1
                     WHERE id = ?
                    ''',
                    (
                        new_cat_id,
                        new_quantity,
                        new_price,
                        pricing_mode,
                        spot_premium,
                        floor_price,
                        pricing_metal,
                        graded,
                        grading_service,
                        listing_id
                    )
                )

                # Explicitly commit the transaction
                conn.commit()

                # Update bucket price history after listing change
                try:
                    bucket_id_row = conn.execute(
                        'SELECT bucket_id FROM categories WHERE id = ?',
                        (new_cat_id,)
                    ).fetchone()
                    if bucket_id_row:
                        bucket_id = bucket_id_row['bucket_id']
                        update_bucket_price(bucket_id)
                except Exception as e:
                    # Don't fail the listing update if price tracking fails
                    print(f"[WARNING] Failed to update bucket price: {e}")

                # Fetch the updated listing with full details for success modal
                updated_listing = conn.execute(
                    '''
                    SELECT
                        l.id          AS listing_id,
                        l.quantity,
                        l.price_per_coin,
                        l.pricing_mode,
                        l.spot_premium,
                        l.floor_price,
                        l.pricing_metal,
                        l.graded      AS graded,
                        l.grading_service,
                        lp.file_path  AS photo_path,
                        c.id          AS category_id,
                        c.metal,
                        c.product_line,
                        c.product_type,
                        c.purity,
                        c.weight,
                        c.mint,
                        c.year,
                        c.finish,
                        c.grade
                    FROM listings l
                    JOIN categories c       ON l.category_id = c.id
                    LEFT JOIN listing_photos lp ON lp.listing_id = l.id
                    WHERE l.id = ?
                    ''',
                    (listing_id,)
                ).fetchone()

                # Prepare response data for success modal
                response_data = {
                    'success': True,
                    'listingId': listing_id,
                    'metal': updated_listing['metal'] or '—',
                    'productLine': updated_listing['product_line'] or '—',
                    'productType': updated_listing['product_type'] or '—',
                    'weight': updated_listing['weight'] or '—',
                    'purity': updated_listing['purity'] or '—',
                    'year': updated_listing['year'] or '—',
                    'mint': updated_listing['mint'] or '—',
                    'finish': updated_listing['finish'] or '—',
                    'grade': updated_listing['grade'] or '—',
                    'quantity': updated_listing['quantity'],
                    'graded': updated_listing['graded'] == 1,
                    'gradingService': updated_listing['grading_service'] or None,
                    'hasPhoto': updated_listing['photo_path'] is not None,
                    'pricingMode': updated_listing['pricing_mode']
                }

                # Add pricing details based on mode
                if updated_listing['pricing_mode'] == 'premium_to_spot':
                    # Get current spot prices
                    spot_prices = get_current_spot_prices()
                    pricing_metal = updated_listing['pricing_metal'] or updated_listing['metal']

                    if pricing_metal and pricing_metal.lower() in spot_prices:
                        current_spot_price = spot_prices[pricing_metal.lower()]
                        response_data['currentSpotPrice'] = current_spot_price

                        # Calculate effective price using pricing service
                        listing_dict = dict(updated_listing)
                        effective_price = get_effective_price(listing_dict, spot_prices)

                        response_data['effectivePrice'] = effective_price
                        response_data['spotPremium'] = updated_listing['spot_premium'] or 0.0
                        response_data['floorPrice'] = updated_listing['floor_price'] or 0.0
                        response_data['pricingMetal'] = pricing_metal
                    else:
                        # Fallback if spot price not available
                        response_data['currentSpotPrice'] = None
                        response_data['effectivePrice'] = updated_listing['floor_price'] or 0.0
                        response_data['spotPremium'] = updated_listing['spot_premium'] or 0.0
                        response_data['floorPrice'] = updated_listing['floor_price'] or 0.0
                        response_data['pricingMetal'] = pricing_metal
                else:
                    # Static pricing
                    response_data['pricePerCoin'] = updated_listing['price_per_coin']

                # Return success response
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify(response_data), 200
                return redirect(url_for('listings.my_listings'))

            except Exception as e:
                # context manager will roll back automatically on exception
                msg = f'Error updating listing: {e}'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'message': msg}), 500
                return msg, 500

        # ==========================================
        # GET: return modal HTML (fast, read-only)
        # ==========================================
        options_start = time.time()
        options = get_dropdown_options()
        print(f"[PERF] get_dropdown_options took: {time.time() - options_start:.3f}s")
        grading_services = ['PCGS', 'NGC', 'ANACS', 'ICG']

        # Fetch current spot price for the listing's metal
        current_spot_price = None
        listing_metal = listing['metal']
        if listing_metal:
            try:
                current_spot_price = get_spot_price(listing_metal)
                print(f"[INFO] Fetched spot price for {listing_metal}: ${current_spot_price}")
            except Exception as e:
                print(f"[WARNING] Failed to fetch spot price for {listing_metal}: {e}")
                # Continue without spot price - modal will still work

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            render_start = time.time()
            html = render_template(
                'modals/edit_listing_modal.html',
                listing=listing,
                metals=options['metals'],
                product_lines=options['product_lines'],
                product_types=options['product_types'],
                special_designations=[],  # not used in this modal
                purities=options['purities'],
                weights=options['weights'],
                mints=options['mints'],
                years=options['years'],
                finishes=options['finishes'],
                grades=options['grades'],
                grading_services=grading_services,
                current_spot_price=current_spot_price  # Add spot price for display
            )
            print(f"[PERF] Template render took: {time.time() - render_start:.3f}s")
            print(f"[PERF] TOTAL edit_listing GET request took: {time.time() - start_time:.3f}s")
            return html

        # Fallback full-page edit
        return render_template('edit_listing_fullpage.html', listing=listing)

@listings_bp.route('/cancel_listing/<int:listing_id>', methods=['POST'])
def cancel_listing(listing_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    conn = get_db_connection()

    listing = conn.execute('SELECT seller_id FROM listings WHERE id = ?', (listing_id,)).fetchone()

    if listing and listing['seller_id'] == session['user_id']:
        # Get bucket_id before deactivating
        bucket_id_row = conn.execute('''
            SELECT c.bucket_id
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE l.id = ?
        ''', (listing_id,)).fetchone()

        conn.execute('UPDATE listings SET active = 0 WHERE id = ?', (listing_id,))
        conn.commit()

        # Update bucket price history after deactivating listing
        if bucket_id_row:
            try:
                bucket_id = bucket_id_row['bucket_id']
                update_bucket_price(bucket_id)
            except Exception as e:
                # Don't fail the deactivation if price tracking fails
                print(f"[WARNING] Failed to update bucket price: {e}")

    conn.close()
    # if this is an AJAX request, just return 204 No Content
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return ('', 204)
    # otherwise fall back to a full‐page redirect
    return redirect(url_for('listings.my_listings'))


@listings_bp.route('/cancel_listing_confirmation_modal/<int:listing_id>')
def cancel_listing_confirmation_modal(listing_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    # Simply render the partial template
    return render_template('modals/cancel_listing_confirmation_modal.html', listing_id=listing_id)

@listings_bp.route('/my_listings')
def my_listings():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    conn = get_db_connection()

    # Fetch Active Listings
    listings = conn.execute('''
        SELECT listings.id as listing_id, 
                listings.quantity, 
                listings.price_per_coin, 
                categories.bucket_id  AS bucket_id,
                categories.metal, 
                categories.product_type, 
                special_designation, 
                categories.weight, 
                categories.mint, 
                categories.year, 
                categories.finish, 
                categories.grade
        FROM listings
        JOIN categories ON listings.category_id = categories.id
        WHERE listings.seller_id = ? AND listings.active = 1 AND listings.quantity > 0
    ''', (session['user_id'],)).fetchall()

    # Orders from listings
    sales_from_listings = conn.execute('''
        SELECT orders.id AS order_id,
               order_items.quantity,
               order_items.price_each,
               orders.status,
               orders.delivery_address, 
               users.username AS buyer_username,
               categories.metal,
               categories.product_type,
               categories.special_designation,
               0 AS already_rated
        FROM orders
        JOIN order_items ON orders.id = order_items.order_id
        JOIN listings ON order_items.listing_id = listings.id
        JOIN categories ON listings.category_id = categories.id
        JOIN users ON orders.buyer_id = users.id
        WHERE listings.seller_id = ?
    ''', (session['user_id'],)).fetchall()

    # Orders from accepted bids
    sales_from_bids = conn.execute('''
        SELECT orders.id AS order_id,
               orders.quantity,
               orders.price_each,
               orders.status,
               orders.delivery_address,
               users.username AS buyer_username,
               categories.metal,
               categories.product_type,
               categories.special_designation,
               0 AS already_rated
        FROM orders
        JOIN categories ON orders.category_id = categories.id
        JOIN users ON orders.buyer_id = users.id
        WHERE orders.seller_id = ?
    ''', (session['user_id'],)).fetchall()

    # Combine all orders
    sales = sales_from_listings + sales_from_bids

    conn.close()
    return render_template('my_listings.html', listings=listings, sales=sales)