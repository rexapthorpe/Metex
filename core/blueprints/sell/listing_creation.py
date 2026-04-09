# core/blueprints/sell/listing_creation.py
"""
Listing creation logic for sell route POST handling.

Extracted from routes.py during refactor - NO BEHAVIOR CHANGE.
"""

from flask import request, session, flash, jsonify
from database import get_db_connection
from routes.category_options import get_dropdown_options
from utils.category_manager import get_or_create_category, validate_category_specification
from services.bucket_price_history_service import update_bucket_price
from services.pricing_service import get_effective_price
from werkzeug.utils import secure_filename
import os
import re

# Folder where listing photos will be stored (relative to project root)
UPLOAD_FOLDER = os.path.join("static", "uploads", "listings")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "heic"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def handle_sell_post():
    """
    Handle POST request for creating a new listing.

    Returns:
        Response: JSON response for AJAX or rendered template/redirect for form POST
    """
    try:
        # Hard safety check: if edit_listing_id is present, this should have gone to
        # edit_listing() via the dispatcher in routes.py. Refuse to create a new listing.
        edit_id_str = request.form.get('edit_listing_id', '').strip()
        if edit_id_str and edit_id_str.isdigit():
            error_msg = 'Cannot create a new listing when edit_listing_id is present.'
            print(f"[SAFETY] handle_sell_post called with edit_listing_id={edit_id_str} — refusing to create new listing")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify(success=False, message=error_msg), 400
            flash(error_msg, 'error')
            options = get_dropdown_options()
            return _render_sell_template(options)

        # Enforce Stripe seller onboarding before allowing listing creation
        _stripe_check_conn = get_db_connection()
        _stripe_user = _stripe_check_conn.execute(
            'SELECT stripe_charges_enabled, stripe_payouts_enabled FROM users WHERE id = ?',
            (session['user_id'],)
        ).fetchone()
        _stripe_check_conn.close()
        _stripe_ready = (
            _stripe_user is not None and
            bool(_stripe_user['stripe_charges_enabled']) and
            bool(_stripe_user['stripe_payouts_enabled'])
        )
        if not _stripe_ready:
            error_msg = 'You must complete seller payment setup before listing items.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify(success=False, message=error_msg, error_code='stripe_not_ready'), 403
            flash(error_msg, 'error')
            options = get_dropdown_options()
            return _render_sell_template(options)

        print(">>> /sell POST content_length:", request.content_length)
        print(">>> Content-Type:", request.headers.get("Content-Type"))
        print(">>> files keys:", list(request.files.keys()))
        print(">>> form keys:", list(request.form.keys())[:30], "...")
        import sys
        sys.stdout.flush()

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

        print(f"[MODE DEBUG] is_isolated={is_isolated}, is_set={is_set}, is_isolated_raw='{request.form.get('is_isolated')}', is_set_raw='{request.form.get('is_set')}'")

        # Convert issue numbers to integers if provided
        issue_number = int(issue_number) if issue_number else None
        issue_total = int(issue_total) if issue_total else None

        # Extract edition numbering for one-of-a-kind listings
        edition_number_str = request.form.get('edition_number', '').strip()
        edition_total_str = request.form.get('edition_total', '').strip()
        edition_number = int(edition_number_str) if edition_number_str else None
        edition_total = int(edition_total_str) if edition_total_str else None

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
            return _render_sell_template(options)

        # Validate issue number <= issue total
        if issue_number and issue_total and issue_number > issue_total:
            error_msg = "Issue number cannot be greater than issue total."
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify(success=False, message=error_msg), 400
            flash(error_msg, "error")
            options = get_dropdown_options()
            return _render_sell_template(options)

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
            # Set listings are always 1-of-a-kind (isolated); quantity defaults to 1 if blank
            raw_quantity = request.form.get('quantity', '').strip()
            quantity = int(raw_quantity) if raw_quantity else 1 if is_set else int(request.form['quantity'])

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
                    return _render_sell_template(options)
            else:
                error_msg = "Invalid pricing mode."
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify(success=False, message=error_msg), 400
                flash(error_msg, "error")
                options = get_dropdown_options()
                return _render_sell_template(options)

        except (ValueError, KeyError) as e:
            error_msg = "Invalid quantity or price. Please enter valid numbers."
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify(success=False, message=error_msg), 400
            flash(error_msg, "error")
            options = get_dropdown_options()
            return _render_sell_template(options)

        # Extract packaging fields
        # For one-of-a-kind/isolated listings, use item_ prefixed fields
        # For standard listings, use non-prefixed fields
        packaging_type = request.form.get('item_packaging_type', '').strip() or request.form.get('packaging_type', '').strip() or None
        packaging_notes = request.form.get('item_packaging_notes', '').strip() or request.form.get('packaging_notes', '').strip() or None

        # Extract additional specification fields
        condition_category = request.form.get('condition_category', '').strip() or None
        series_variant = request.form.get('series_variant', '').strip() or None
        cert_number = request.form.get('cert_number', '').strip() or None
        # For one-of-a-kind/isolated listings, use item_condition_notes
        condition_notes = request.form.get('item_condition_notes', '').strip() or request.form.get('condition_notes', '').strip() or None

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
        # EXCEPTION: For set listings with 2+ items already in set_items array, main form is optional
        options = get_dropdown_options()

        # Check if this is a set with 2+ items already added.
        # Prefer set_items_json (explicit JSON blob from frontend) over individual hidden inputs.
        set_item_indices = set()
        set_items_json_data = None  # Parsed JSON data if present
        if is_set:
            import json as _json
            _set_items_json_str = request.form.get('set_items_json', '').strip()
            if _set_items_json_str:
                try:
                    set_items_json_data = _json.loads(_set_items_json_str)
                    # Build synthetic indices from JSON data (1-based)
                    for i in range(len(set_items_json_data)):
                        set_item_indices.add(i + 1)
                    print(f"[SET VALIDATION DEBUG] Using set_items_json: {len(set_items_json_data)} items")
                except Exception as _je:
                    print(f"[SET VALIDATION DEBUG] set_items_json parse error: {_je}")
                    set_items_json_data = None

            if not set_items_json_data:
                # Fallback: count items in set_items[N] individual hidden inputs
                for key in request.form.keys():
                    match = re.match(r'set_items\[(\d+)\]\[', key)
                    if match:
                        set_item_indices.add(int(match.group(1)))

            print(f"[SET VALIDATION DEBUG] is_set={is_set}, set_item_indices={set_item_indices}, count={len(set_item_indices)}")
            print(f"[SET VALIDATION DEBUG] main form metal='{metal}', product_line='{product_line}'")

            # If 2+ items exist in array, skip main form validation
            if len(set_item_indices) >= 2:
                # Set listing with sufficient items - main form is optional, skip validation
                print("[SET VALIDATION DEBUG] Skipping main form validation (2+ items exist)")
                pass
            else:
                # Set listing with < 2 items - validate main form (it will become item #1)
                print(f"[SET VALIDATION DEBUG] Validating main form (only {len(set_item_indices)} items)")
                is_valid, error_msg = validate_category_specification(category_spec, options)
                if not is_valid:
                    print(f"[SET VALIDATION DEBUG] Validation failed: {error_msg}")
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return jsonify(success=False, message=error_msg), 400
                    flash(error_msg, "error")
                    return _render_sell_template(options, prefill=category_spec)
        else:
            # Standard or one-of-a-kind: always validate main form
            is_valid, error_msg = validate_category_specification(category_spec, options)
            if not is_valid:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify(success=False, message=error_msg), 400
                flash(error_msg, "error")
                return _render_sell_template(options, prefill=category_spec)

        conn = get_db_connection()

        # --- Handle photo upload(s) ---
        # For sets: use cover_photo as main
        # For one-of-a-kind (isolated): use cover_photo as main tile image, item_photo_1/2/3 as additional
        # For standard: use item_photo_1/2/3
        standard_photos = []  # Additional photos beyond the main one
        if is_set:
            # Set listing: require cover photo
            photo_file = request.files.get('cover_photo')
            if not photo_file or photo_file.filename == "":
                error_msg = "Please upload a cover photo for your set listing."
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify(success=False, message=error_msg), 400
                flash(error_msg, "error")
                options = get_dropdown_options()
                return _render_sell_template(options)
        elif is_isolated:
            # One-of-a-kind listing: cover_photo is the main tile image
            photo_file = request.files.get('cover_photo')
            # Collect item_photo_1/2/3 as additional detail photos
            for photo_idx in range(1, 4):
                pf = request.files.get(f'item_photo_{photo_idx}')
                if pf and pf.filename:
                    standard_photos.append(pf)
            if not photo_file or photo_file.filename == "":
                error_msg = "Please upload a cover photo for your one-of-a-kind listing."
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify(success=False, message=error_msg), 400
                flash(error_msg, "error")
                options = get_dropdown_options()
                return _render_sell_template(options)
        else:
            # Standard listing: use item_photo_1/2/3
            for photo_idx in range(1, 4):  # Check for photos 1, 2, 3
                pf = request.files.get(f'item_photo_{photo_idx}')
                if pf and pf.filename:
                    standard_photos.append(pf)

            if standard_photos:
                # Use first photo as main photo_file for backwards compatibility
                photo_file = standard_photos[0]
            else:
                # Fallback to single photo (legacy)
                photo_file = request.files.get('item_photo')

            if not photo_file or photo_file.filename == "":
                error_msg = "Please upload a photo of your item."
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify(success=False, message=error_msg), 400
                flash(error_msg, "error")
                options = get_dropdown_options()
                return _render_sell_template(options)

        if not allowed_file(photo_file.filename):
            error_msg = "Invalid file type. Please upload a PNG, JPG, JPEG, WEBP, or HEIC image."
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify(success=False, message=error_msg), 400
            flash(error_msg, "error")
            options = get_dropdown_options()
            return _render_sell_template(options)

        # Save the main/cover photo with full content validation (magic bytes + image decode)
        from utils.upload_security import save_secure_upload
        upload_result = save_secure_upload(
            photo_file,
            upload_dir='uploads/listings',
            allowed_types=['image/png', 'image/jpeg', 'image/webp', 'image/heic'],
            category='listing_photo'
        )
        if not upload_result['success']:
            error_msg = f"Photo rejected: {upload_result['error']}"
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify(success=False, message=error_msg), 400
            flash(error_msg, "error")
            options = get_dropdown_options()
            return _render_sell_template(options)

        photo_filename = os.path.basename(upload_result['path'])

        # ========== BUCKET/CATEGORY CREATION WITH ISOLATION LOGIC ==========
        cursor = conn.cursor()

        if is_isolated:
            # ISOLATED LISTING: Always create a new isolated bucket
            # Generate unique integer bucket_id (MAX + 1, same as standard buckets)
            new_bucket = cursor.execute(
                'SELECT COALESCE(MAX(bucket_id), 0) + 1 AS new_bucket_id FROM categories'
            ).fetchone()
            bucket_id = new_bucket['new_bucket_id']

            # For sets with 2+ items and blank main form, use first set item specs for category
            category_metal = metal
            category_product_line = product_line
            category_product_type = product_type
            category_weight = weight
            category_purity = purity
            category_mint = mint
            category_year = year
            category_finish = finish
            category_grade = grade
            category_coin_series = category_spec.get('coin_series', '')

            if is_set and len(set_item_indices) >= 2:
                # Get specs from first set item if main form is blank/minimal
                if not metal or not product_line:
                    first_idx = sorted(set_item_indices)[0]
                    category_metal = request.form.get(f'set_items[{first_idx}][metal]', '').strip() or metal
                    category_product_line = request.form.get(f'set_items[{first_idx}][product_line]', '').strip() or product_line
                    category_product_type = request.form.get(f'set_items[{first_idx}][product_type]', '').strip() or product_type
                    category_weight = request.form.get(f'set_items[{first_idx}][weight]', '').strip() or weight
                    category_purity = request.form.get(f'set_items[{first_idx}][purity]', '').strip() or purity
                    category_mint = request.form.get(f'set_items[{first_idx}][mint]', '').strip() or mint
                    category_year = request.form.get(f'set_items[{first_idx}][year]', '').strip() or year
                    category_finish = request.form.get(f'set_items[{first_idx}][finish]', '').strip() or finish
                    category_grade = request.form.get(f'set_items[{first_idx}][grade]', '').strip() or grade

            # Create new isolated category
            cursor.execute('''
                INSERT INTO categories (
                    metal, product_line, product_type, weight, purity,
                    mint, year, finish, grade, coin_series, bucket_id, is_isolated,
                    condition_category, series_variant
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            ''', (category_metal, category_product_line, category_product_type, category_weight, category_purity,
                  category_mint, category_year, category_finish, category_grade, category_coin_series, bucket_id,
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
                edition_number,
                edition_total,
                active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
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
            condition_notes,
            edition_number,
            edition_total
        ))

        # Get the newly created listing ID
        listing_id = cursor.lastrowid

        # Insert photo(s) into listing_photos table
        # For standard mode with multiple photos, insert all photos
        # For other modes, insert the single main photo

        # First photo was already saved above as photo_filename
        file_path = f"uploads/listings/{photo_filename}"
        cursor.execute('''
            INSERT INTO listing_photos (listing_id, uploader_id, file_path)
            VALUES (?, ?, ?)
        ''', (listing_id, session['user_id'], file_path))

        # Save additional photos:
        # - Standard mode: skip first (already saved as photo_file), save 2nd and 3rd
        # - One-of-a-kind: cover_photo already saved; save all item_photo_1/2/3 as additional
        extra_photos = standard_photos if is_isolated else (standard_photos[1:] if len(standard_photos) > 1 else [])
        if extra_photos:
            for idx, std_photo in enumerate(extra_photos, start=2):
                if std_photo and std_photo.filename:
                    extra_result = save_secure_upload(
                        std_photo,
                        upload_dir='uploads/listings',
                        allowed_types=['image/png', 'image/jpeg', 'image/webp', 'image/heic'],
                        category='listing_photo'
                    )
                    if not extra_result['success']:
                        continue  # Skip rejected photos silently (main photo already accepted)
                    std_file_path = f"uploads/listings/{os.path.basename(extra_result['path'])}"

                    cursor.execute('''
                        INSERT INTO listing_photos (listing_id, uploader_id, file_path)
                        VALUES (?, ?, ?)
                    ''', (listing_id, session['user_id'], std_file_path))

        # ========== CREATE SET ITEMS IF THIS IS A SET LISTING ==========
        if is_set:
            result = _create_set_items(cursor, conn, listing_id, set_item_indices, options,
                                       set_items_json_data=set_items_json_data)
            if result is not None:
                return result  # Error response

        # Auto-match intentionally disabled: bids fill only when a seller manually
        # accepts via /bids/accept_bid/<bucket_id>, which charges the buyer's card.
        # Calling auto_match_listing_to_bids here would create orders without payment.
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
            'issue_total': issue_total,
            'condition_category': condition_category,
            'series_variant': series_variant,
            'packaging_type': packaging_type,
            'packaging_notes': packaging_notes,
            'condition_notes': condition_notes
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

        # Notify seller that their listing was published
        try:
            from services.notification_types import notify_listing_created
            item_desc = ' '.join(filter(None, [
                str(weight) if weight else '',
                str(metal) if metal else '',
                str(product_line) if product_line else '',
                str(product_type) if product_type else '',
            ])).strip() or 'item'
            notify_listing_created(session['user_id'], listing_id, item_desc)
        except Exception as _notif_err:
            print(f'[NOTIFICATION WARNING] listing_created_success failed: {_notif_err}')

        # Check if AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(
                success=True,
                message='Your item was successfully listed!',
                listing=listing_data,
                category=category_dict,
                set_items=set_items_data
            )

        return "Your item was successfully listed!"

    except Exception as e:
        # Catch any unexpected errors and return proper JSON for AJAX requests
        import traceback
        import sys
        error_trace = traceback.format_exc()
        print("=" * 80)
        print("[ERROR] Sell listing error:")
        print(error_trace)
        print("=" * 80)
        sys.stdout.flush()
        sys.stderr.flush()

        error_msg = f"An error occurred while creating your listing: {str(e)}"
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(success=False, message=error_msg), 500

        flash(error_msg, "error")
        options = get_dropdown_options()
        return _render_sell_template(options)


def _render_sell_template(options, prefill=None):
    """Render sell.html with given options and optional prefill data."""
    from flask import render_template
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
        prefill=prefill or {}
    )


def _create_set_items(cursor, conn, listing_id, set_item_indices, options,
                      set_items_json_data=None):
    """
    Create set items for a set listing.

    set_items_json_data: parsed list of item dicts from set_items_json form field (preferred).
    Falls back to reading individual set_items[N][field] form fields when absent.

    Returns None on success, or an error response tuple on failure.
    """
    # Validate that set has at least 2 items
    if len(set_item_indices) < 2:
        error_msg = "Set listings require at least 2 items to be added before submission."
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(success=False, message=error_msg), 400
        flash(error_msg, "error")
        conn.close()
        return _render_sell_template(options)

    from utils.upload_security import save_secure_upload

    # Helper function to save set item photo with full content validation
    def save_set_item_photo(photo_file):
        if not photo_file or photo_file.filename == "":
            return None
        result = save_secure_upload(
            photo_file,
            upload_dir='uploads/listings',
            allowed_types=['image/png', 'image/jpeg', 'image/webp', 'image/heic'],
            category='listing_photo'
        )
        if not result['success']:
            return None
        return f"uploads/listings/{os.path.basename(result['path'])}"

    # Process all items from set_items[N] array
    # Main form is not used for set listings with 2+ items
    position = 0

    # Additional set items from form — prefer JSON blob, fall back to individual hidden inputs
    for idx in sorted(set_item_indices):
        # When set_items_json_data is available, read fields from it (idx is 1-based)
        _jitem = set_items_json_data[idx - 1] if set_items_json_data else None

        def _fv(field, default=''):
            """Read field from JSON item or individual form key."""
            if _jitem is not None:
                return str(_jitem.get(field, default) or default).strip()
            return request.form.get(f'set_items[{idx}][{field}]', default).strip()

        set_item_title = _fv('item_title')
        set_metal = _fv('metal')
        set_product_line = _fv('product_line')
        set_product_type = _fv('product_type')
        set_weight = _fv('weight')
        set_purity = _fv('purity')
        set_mint = _fv('mint')
        set_year = _fv('year')
        set_finish = _fv('finish')
        set_grade = _fv('grade')
        set_coin_series = _fv('coin_series')
        raw_set_qty = _fv('quantity')
        set_quantity = int(raw_set_qty) if raw_set_qty else 1
        # Additional item details
        set_packaging_type = _fv('packaging_type') or None
        set_packaging_notes = _fv('packaging_notes') or None
        set_condition_notes = _fv('condition_notes') or None
        set_edition_number = _fv('edition_number')
        set_edition_total = request.form.get(f'set_items[{idx}][edition_total]', '').strip()
        set_edition_number = int(set_edition_number) if set_edition_number else None
        set_edition_total = int(set_edition_total) if set_edition_total else None

        # Collect all photos for this set item (up to 3)
        set_item_photos = []
        for photo_idx in range(1, 4):  # Check for photos 1, 2, 3
            photo_file = request.files.get(f'set_item_photo_{idx}_{photo_idx}')
            if photo_file and photo_file.filename:
                set_item_photos.append(photo_file)

        # Backend validation: each set item requires at least 1 photo
        if not set_item_photos:
            error_msg = f"Set item #{position + 1} requires at least one photo."
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify(success=False, message=error_msg), 400
            flash(error_msg, "error")
            conn.close()
            return _render_sell_template(options)

        # Backend validation: first 2 items require all fields (grade removed from requirements)
        if position < 2:
            if not all([set_metal, set_product_line, set_product_type, set_weight,
                       set_purity, set_mint, set_year, set_finish]):
                error_msg = f"Set item #{position + 1} is missing required specifications."
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify(success=False, message=error_msg), 400
                flash(error_msg, "error")
                conn.close()
                return _render_sell_template(options)

        # Only insert if at least metal is present (items 3+ can have minimal specs)
        if set_metal or set_product_line or set_item_photos:
            # Insert set item with all fields including item details
            cursor.execute('''
                INSERT INTO listing_set_items (
                    listing_id, position_index,
                    metal, product_line, product_type, weight, purity,
                    mint, year, finish, grade, coin_series,
                    quantity, photo_path, item_title,
                    packaging_type, packaging_notes, condition_notes,
                    edition_number, edition_total
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (listing_id, position,
                  set_metal, set_product_line, set_product_type, set_weight, set_purity,
                  set_mint, set_year, set_finish, set_grade, set_coin_series,
                  set_quantity, None, set_item_title or None,
                  set_packaging_type, set_packaging_notes, set_condition_notes,
                  set_edition_number, set_edition_total))  # photo_path set to NULL, using separate table now

            # Get the set_item_id for the newly created item
            set_item_id = cursor.lastrowid

            # Save all photos for this set item to listing_set_item_photos table
            for photo_position, photo_file in enumerate(set_item_photos, start=1):
                photo_path = save_set_item_photo(photo_file)
                if photo_path:
                    cursor.execute('''
                        INSERT INTO listing_set_item_photos (
                            set_item_id, file_path, position_index
                        ) VALUES (?, ?, ?)
                    ''', (set_item_id, photo_path, photo_position))

            position += 1

    return None  # Success
