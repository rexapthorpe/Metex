"""
Listings Blueprint - Routes

Contains routes for editing, canceling, and viewing listings.
Helper functions are in helpers.py.
"""

from flask import render_template, request, redirect, url_for, session, jsonify
from database import get_db_connection
from routes.category_options import get_dropdown_options
from utils.category_manager import get_or_create_category, validate_category_specification
from services.pricing_service import get_effective_price
from services.spot_price_service import get_current_spot_prices, get_spot_price
from services.bucket_price_history_service import update_bucket_price
import sqlite3

from . import listings_bp
from .helpers import (
    allowed_file,
    validate_edition_numbers,
    save_uploaded_photo,
    update_set_items,
    handle_set_item_photos,
    UPLOAD_FOLDER,
    ALLOWED_EXTENSIONS
)


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
                l.name        AS listing_name,
                l.description AS listing_description,
                l.is_isolated,
                l.isolated_type,
                l.issue_number,
                l.issue_total,
                l.edition_number,
                l.edition_total,
                l.packaging_type,
                l.packaging_notes,
                l.cert_number,
                l.condition_notes,
                l.actual_year,
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
                c.grade,
                c.series_variant,
                c.condition_category,
                c.coin_series
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
                print(f"[DEBUG] ===== EDIT LISTING POST START =====")
                print(f"[DEBUG] Listing ID from URL: {listing_id}")
                print(f"[DEBUG] User ID: {session['user_id']}")
                print(f"[DEBUG] Form data keys: {list(request.form.keys())}")

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

                # Extract new optional fields
                series_variant = request.form.get('series_variant', '').strip() or None
                condition_category = request.form.get('condition_category', '').strip() or None
                coin_series = request.form.get('coin_series', '').strip() or None

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
                    'grade': grade,
                    'series_variant': series_variant,
                    'condition_category': condition_category,
                    'coin_series': coin_series
                }

                # Backend validation - ensure all values are from allowed dropdown options
                # EXCEPTION: For set listings with 2+ items already in set_items array,
                # skip main form spec validation. The set items carry their own specs;
                # the main form fields are intentionally empty (cleared after each item is added).
                # This mirrors the same logic in listing_creation.py for the create path.
                valid_options = get_dropdown_options()
                _skip_main_validation = False
                if listing['is_isolated'] == 1 and listing['isolated_type'] == 'set':
                    import re as _re
                    _set_item_indices = set()
                    for _key in request.form.keys():
                        _m = _re.match(r'set_items\[(\d+)\]\[', _key)
                        if _m:
                            _set_item_indices.add(int(_m.group(1)))
                    if len(_set_item_indices) >= 2:
                        _skip_main_validation = True
                        print(f"[EDIT VALIDATION] Skipping main form validation — {len(_set_item_indices)} set items present")
                if not _skip_main_validation:
                    is_valid, error_msg = validate_category_specification(category_spec, valid_options)
                    if not is_valid:
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            return jsonify({'message': error_msg}), 400
                        return error_msg, 400

                cur = conn.cursor()

                # For isolated (OOK/Set) listings, update the existing isolated category
                # in-place to preserve is_isolated=1 and the unique bucket_id.
                # For standard listings, use the shared category pool.
                if listing['is_isolated'] == 1:
                    existing_cat_id = listing['category_id']
                    cur.execute(
                        '''UPDATE categories SET
                               metal = ?, product_line = ?, product_type = ?, weight = ?,
                               purity = ?, mint = ?, year = ?, finish = ?, grade = ?,
                               condition_category = ?, series_variant = ?, coin_series = ?
                           WHERE id = ?''',
                        (metal, product_line, product_type, weight, purity, mint, year,
                         finish, grade, condition_category, series_variant, coin_series,
                         existing_cat_id)
                    )
                    new_cat_id = existing_cat_id
                else:
                    # Use unified category management - handles bucket_id automatically
                    new_cat_id = get_or_create_category(conn, category_spec)

                # ---- Extract isolated listing fields ----
                listing_name = None
                listing_description = None
                if listing['is_isolated'] == 1:
                    # Accept both 'listing_name' (edit modal) and 'listing_title' (sell page form)
                    listing_name = (
                        request.form.get('listing_name', '').strip() or
                        request.form.get('listing_title', '').strip() or
                        None
                    )
                    listing_description = request.form.get('listing_description', '').strip() or None

                # ---- Extract edition/issue numbering fields ----
                issue_number_str = request.form.get('issue_number', '').strip()
                issue_total_str = request.form.get('issue_total', '').strip()
                edition_number_str = request.form.get('edition_number', '').strip()
                edition_total_str = request.form.get('edition_total', '').strip()

                issue_number = int(issue_number_str) if issue_number_str else None
                issue_total = int(issue_total_str) if issue_total_str else None
                edition_number = int(edition_number_str) if edition_number_str else None
                edition_total = int(edition_total_str) if edition_total_str else None

                # Validate edition numbers
                is_valid_numbers, numbers_error = validate_edition_numbers(
                    issue_number, issue_total, edition_number, edition_total
                )
                if not is_valid_numbers:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return jsonify({'message': numbers_error}), 400
                    return numbers_error, 400

                # ---- Extract optional specification fields ----
                # Check both field names: item_* (for isolated/set modes) and regular (for standard mode)
                packaging_type = request.form.get('item_packaging_type', '').strip() or request.form.get('packaging_type', '').strip() or None
                packaging_notes = request.form.get('item_packaging_notes', '').strip() or request.form.get('packaging_notes', '').strip() or None
                cert_number = request.form.get('cert_number', '').strip() or None
                condition_notes = request.form.get('item_condition_notes', '').strip() or request.form.get('condition_notes', '').strip() or None
                actual_year = request.form.get('actual_year', '').strip() or None

                # ---- Photo upload handling ----
                # Handle photo removal - delete photos not in keep_photo_ids
                keep_photo_ids_str = request.form.get('keep_photo_ids', '').strip()
                if keep_photo_ids_str:
                    keep_photo_ids = [int(pid.strip()) for pid in keep_photo_ids_str.split(',') if pid.strip().isdigit()]
                else:
                    keep_photo_ids = []

                # Get all current photos for this listing
                current_photos = conn.execute(
                    'SELECT id FROM listing_photos WHERE listing_id = ?',
                    (listing_id,)
                ).fetchall()

                # Server-side cover photo enforcement for set listings.
                # A set listing must have a cover photo at all times.
                # It satisfies this if: a new cover photo is being uploaded OR at least one
                # existing photo survives (i.e. is in keep_photo_ids, or no deletions requested).
                if listing['is_isolated'] == 1 and listing['isolated_type'] == 'set':
                    new_cover = request.files.get('cover_photo')
                    has_new_cover = bool(new_cover and new_cover.filename)
                    if keep_photo_ids_str:
                        surviving_count = len(keep_photo_ids)
                    else:
                        surviving_count = len(current_photos)
                    if not has_new_cover and surviving_count == 0:
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            return jsonify({'message': 'Set listings require a cover photo. Please upload a cover photo.'}), 400
                        return 'Set listings require a cover photo.', 400

                # Delete photos that are not in the keep list (if keep list was provided)
                if keep_photo_ids_str is not None and keep_photo_ids_str != '':
                    for photo in current_photos:
                        if photo['id'] not in keep_photo_ids:
                            conn.execute('DELETE FROM listing_photos WHERE id = ?', (photo['id'],))
                            print(f"[INFO] Deleted photo {photo['id']} from listing {listing_id}")

                # Handle multiple new item photos (modal format: 'item_photos')
                new_photos = request.files.getlist('item_photos')
                for photo_file in new_photos:
                    if photo_file and photo_file.filename:
                        file_path = save_uploaded_photo(photo_file)
                        if file_path:
                            conn.execute(
                                '''
                                INSERT INTO listing_photos (listing_id, uploader_id, file_path)
                                VALUES (?, ?, ?)
                                ''',
                                (listing_id, session['user_id'], file_path)
                            )
                            print(f"[INFO] Added new photo to listing {listing_id}: {file_path}")

                # Also handle sell-page-format photo inputs (item_photo_1, item_photo_2, item_photo_3)
                for i in range(1, 4):
                    photo_file = request.files.get(f'item_photo_{i}')
                    if photo_file and photo_file.filename:
                        file_path = save_uploaded_photo(photo_file)
                        if file_path:
                            conn.execute(
                                '''
                                INSERT INTO listing_photos (listing_id, uploader_id, file_path)
                                VALUES (?, ?, ?)
                                ''',
                                (listing_id, session['user_id'], file_path)
                            )
                            print(f"[INFO] Added sell-page photo {i} to listing {listing_id}: {file_path}")

                # Handle cover photo for isolated listings (single file)
                # Cover photos are stored in listing_photos table; removal handled by keep_photo_ids above
                cover_photo = request.files.get('cover_photo')
                if cover_photo and cover_photo.filename:
                    file_path = save_uploaded_photo(cover_photo)
                    if file_path:
                        conn.execute(
                            '''
                            INSERT INTO listing_photos (listing_id, uploader_id, file_path)
                            VALUES (?, ?, ?)
                            ''',
                            (listing_id, session['user_id'], file_path)
                        )
                        print(f"[INFO] Added cover photo to listing {listing_id}: {file_path}")

                # Backwards compatibility: also handle single item_photo field
                single_photo = request.files.get('item_photo')
                if single_photo and single_photo.filename:
                    file_path = save_uploaded_photo(single_photo)
                    if file_path:
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
                           name            = ?,
                           description     = ?,
                           issue_number    = ?,
                           issue_total     = ?,
                           edition_number  = ?,
                           edition_total   = ?,
                           packaging_type  = ?,
                           packaging_notes = ?,
                           cert_number     = ?,
                           condition_notes = ?,
                           actual_year     = ?,
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
                        listing_name,
                        listing_description,
                        issue_number,
                        issue_total,
                        edition_number,
                        edition_total,
                        packaging_type,
                        packaging_notes,
                        cert_number,
                        condition_notes,
                        actual_year,
                        listing_id
                    )
                )

                # Explicitly commit the transaction
                conn.commit()
                print(f"[DEBUG] ===== UPDATE COMPLETED =====")
                print(f"[DEBUG] Updated listing ID: {listing_id}")
                print(f"[DEBUG] New category ID: {new_cat_id}")

                # ---- Cancel bids on non-pricing change (OOK/Set only) ----
                if listing['is_isolated'] == 1:
                    def _norm(v):
                        return '' if v is None else str(v).strip()

                    old_fields = [
                        listing['metal'], listing['product_line'], listing['product_type'],
                        listing['weight'], listing['purity'], listing['mint'],
                        listing['year'], listing['finish'], listing['grade'],
                        listing['series_variant'], listing['condition_category'], listing['coin_series'],
                        listing['quantity'], listing['graded'], listing['grading_service'],
                        listing['listing_name'], listing['listing_description'],
                        listing['issue_number'], listing['issue_total'],
                        listing['edition_number'], listing['edition_total'],
                        listing['packaging_type'], listing['packaging_notes'],
                        listing['cert_number'], listing['condition_notes'], listing['actual_year'],
                    ]
                    new_fields = [
                        metal, product_line, product_type,
                        weight, purity, mint,
                        year, finish, grade,
                        series_variant, condition_category, coin_series,
                        new_quantity, graded, grading_service,
                        listing_name, listing_description,
                        issue_number, issue_total,
                        edition_number, edition_total,
                        packaging_type, packaging_notes,
                        cert_number, condition_notes, actual_year,
                    ]

                    non_pricing_changed = any(
                        _norm(o) != _norm(n) for o, n in zip(old_fields, new_fields)
                    )

                    # Photo additions or removals also count as a change
                    if not non_pricing_changed:
                        photos_added = (
                            any(f and f.filename for f in new_photos) or
                            bool(cover_photo and cover_photo.filename) or
                            any(
                                request.files.get(f'item_photo_{i}') and
                                request.files.get(f'item_photo_{i}').filename
                                for i in range(1, 4)
                            )
                        )
                        photos_removed = (
                            bool(keep_photo_ids_str) and
                            len(keep_photo_ids) < len(current_photos)
                        )
                        non_pricing_changed = photos_added or photos_removed

                    if non_pricing_changed:
                        affected_bids = conn.execute(
                            '''SELECT id, buyer_id FROM bids
                               WHERE category_id = ? AND active = 1
                                 AND status IN ('Open', 'Partially Filled')''',
                            (listing['category_id'],)
                        ).fetchall()

                        if affected_bids:
                            conn.execute(
                                '''UPDATE bids SET active = 0, status = 'Cancelled'
                                   WHERE category_id = ? AND active = 1
                                     AND status IN ('Open', 'Partially Filled')''',
                                (listing['category_id'],)
                            )
                            conn.commit()
                            print(f"[INFO] Cancelled {len(affected_bids)} bids on listing {listing_id} due to non-pricing edit")

                            try:
                                from services.notification_service import create_notification
                                for bid in affected_bids:
                                    create_notification(
                                        user_id=bid['buyer_id'],
                                        notification_type='bid_cancelled',
                                        title='Bid Cancelled',
                                        message='Your bid was cancelled because the seller updated the listing details.',
                                        related_listing_id=listing_id
                                    )
                            except Exception as e:
                                print(f"[WARNING] Failed to send bid cancellation notifications: {e}")

                # ---- Handle set items for set listings ----
                if listing['is_isolated'] == 1 and listing['isolated_type'] == 'set':
                    import json
                    # Get set items data from form (sent as JSON string)
                    set_items_json = request.form.get('set_items_data')
                    if set_items_json:
                        try:
                            set_items_data = json.loads(set_items_json)
                            # Validate minimum 2 items for sets
                            if len(set_items_data) < 2:
                                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                                    return jsonify({'message': 'Set listings must have at least 2 items'}), 400
                                return 'Set listings must have at least 2 items', 400

                            # Update set items
                            update_set_items(conn, listing_id, set_items_data)

                            # Handle photos for each set item
                            for item_data in set_items_data:
                                item_id = item_data.get('id')
                                if item_id:
                                    # Collect photos for this item (up to 3)
                                    photo_files = []
                                    for i in range(1, 4):
                                        photo_key = f'set_item_{item_id}_photo_{i}'
                                        photo_file = request.files.get(photo_key)
                                        if photo_file and photo_file.filename:
                                            photo_files.append(photo_file)

                                    if photo_files:
                                        handle_set_item_photos(conn, item_id, photo_files)

                            conn.commit()
                        except json.JSONDecodeError as e:
                            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                                return jsonify({'message': f'Invalid set items data: {e}'}), 400
                            return f'Invalid set items data: {e}', 400

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
                        l.name        AS listing_name,
                        l.description AS listing_description,
                        l.is_isolated,
                        l.isolated_type,
                        l.issue_number,
                        l.issue_total,
                        l.edition_number,
                        l.edition_total,
                        l.packaging_type,
                        l.packaging_notes,
                        l.cert_number,
                        l.condition_notes,
                        l.actual_year,
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
                        c.grade,
                        c.series_variant,
                        c.condition_category,
                        c.coin_series
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
                    'seriesVariant': updated_listing['series_variant'] or None,
                    'conditionCategory': updated_listing['condition_category'] or None,
                    'coinSeries': updated_listing['coin_series'] or None,
                    'quantity': updated_listing['quantity'],
                    'graded': updated_listing['graded'] == 1,
                    'gradingService': updated_listing['grading_service'] or None,
                    'listingName': updated_listing['listing_name'] or None,
                    'listingDescription': updated_listing['listing_description'] or None,
                    'isIsolated': updated_listing['is_isolated'] == 1,
                    'isolatedType': updated_listing['isolated_type'] or None,
                    'issueNumber': updated_listing['issue_number'] or None,
                    'issueTotal': updated_listing['issue_total'] or None,
                    'editionNumber': updated_listing['edition_number'] or None,
                    'editionTotal': updated_listing['edition_total'] or None,
                    'packagingType': updated_listing['packaging_type'] or None,
                    'packagingNotes': updated_listing['packaging_notes'] or None,
                    'certNumber': updated_listing['cert_number'] or None,
                    'conditionNotes': updated_listing['condition_notes'] or None,
                    'actualYear': updated_listing['actual_year'] or None,
                    'hasPhoto': updated_listing['photo_path'] is not None,
                    'pricingMode': updated_listing['pricing_mode']
                }

                # Add set items if this is a set listing
                if updated_listing['is_isolated'] == 1 and updated_listing['isolated_type'] == 'set':
                    set_items_with_photos = []
                    set_items_rows = conn.execute(
                        '''
                        SELECT id, position_index, metal, product_line, product_type, weight, purity, mint, year, finish, grade, coin_series, special_designation, graded, grading_service, edition_number, edition_total
                        FROM listing_set_items
                        WHERE listing_id = ?
                        ORDER BY position_index
                        ''',
                        (listing_id,)
                    ).fetchall()

                    for item in set_items_rows:
                        item_dict = dict(item)
                        # Fetch photos for this item
                        photos = conn.execute(
                            'SELECT file_path, position_index FROM listing_set_item_photos WHERE set_item_id = ? ORDER BY position_index',
                            (item['id'],)
                        ).fetchall()
                        item_dict['photos'] = [dict(p) for p in photos]
                        set_items_with_photos.append(item_dict)

                    response_data['setItems'] = set_items_with_photos

                # Add pricing details based on mode
                if updated_listing['pricing_mode'] == 'premium_to_spot':
                    # Get current spot prices
                    spot_data = get_current_spot_prices()
                    spot_prices = spot_data.get('prices', spot_data) if isinstance(spot_data, dict) else {}
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
                return redirect(url_for('account.account'))

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

        # Add dropdown options for new fields
        packaging_types = ['Loose', 'Capsule', 'OGP', 'Tube_Full', 'Tube_Partial', 'MonsterBox_Full', 'MonsterBox_Partial', 'Assay_Card']
        series_variants = ['None', 'First_Strike', 'Early_Releases', 'First_Day_of_Issue', 'Privy', 'MintDirect']
        condition_categories = ['BU', 'AU', 'Circulated', 'Cull', 'Random_Condition', 'None']

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

        # Convert listing to dict so we can add listing_photos
        listing = dict(listing)

        # Fetch all listing photos (for standard and one-of-a-kind listings, not sets)
        # Sets have their own item photos, not listing-level photos
        if not (listing['is_isolated'] == 1 and listing['isolated_type'] == 'set'):
            listing_photos = conn.execute(
                '''
                SELECT id, file_path
                FROM listing_photos
                WHERE listing_id = ?
                ORDER BY id
                ''',
                (listing_id,)
            ).fetchall()
            listing['listing_photos'] = [dict(p) for p in listing_photos]
            print(f"[DEBUG] Loaded {len(listing['listing_photos'])} photos for listing {listing_id}")
        else:
            listing['listing_photos'] = []

        # For set listings, fetch all set items and their photos
        set_items = []
        if listing['is_isolated'] == 1 and listing['isolated_type'] == 'set':
            set_items_query = conn.execute(
                '''
                SELECT
                    id,
                    position_index,
                    metal,
                    product_line,
                    product_type,
                    weight,
                    purity,
                    mint,
                    year,
                    finish,
                    grade,
                    coin_series,
                    special_designation,
                    graded,
                    grading_service,
                    edition_number,
                    edition_total,
                    quantity,
                    packaging_type,
                    packaging_notes,
                    condition_notes
                FROM listing_set_items
                WHERE listing_id = ?
                ORDER BY position_index
                ''',
                (listing_id,)
            ).fetchall()

            # For each set item, fetch its photos
            for item in set_items_query:
                item_dict = dict(item)
                photos = conn.execute(
                    '''
                    SELECT file_path, position_index
                    FROM listing_set_item_photos
                    WHERE set_item_id = ?
                    ORDER BY position_index
                    ''',
                    (item['id'],)
                ).fetchall()
                item_dict['photos'] = [dict(p) for p in photos]
                set_items.append(item_dict)

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
                packaging_types=packaging_types,
                series_variants=series_variants,
                condition_categories=condition_categories,
                set_items=set_items,
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
