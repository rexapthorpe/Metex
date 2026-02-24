"""
Bucket View Routes

Contains routes for viewing bucket details and availability:
- /bucket/<int:bucket_id> - view_bucket
- /bucket/<int:bucket_id>/availability_json - bucket_availability_json
"""

from flask import render_template, request, redirect, url_for, session, flash
from database import get_db_connection
from services.pricing_service import get_effective_price, get_effective_bid_price
from services.spot_price_service import get_spot_price
from services.ledger_constants import DEFAULT_PLATFORM_FEE_VALUE
from . import buy_bp


@buy_bp.route('/bucket/<int:bucket_id>')
def view_bucket(bucket_id):
    conn = get_db_connection()

    # User ID for ownership checks
    user_id = session.get('user_id')

    # If user is logged in, try to get category from their own listing first
    # This ensures specs show the actual item they'll be shipping when accepting bids
    if user_id:
        bucket = conn.execute('''
            SELECT DISTINCT c.*
            FROM categories c
            JOIN listings l ON c.id = l.category_id
            WHERE c.bucket_id = ? AND l.seller_id = ? AND l.active = 1
            LIMIT 1
        ''', (bucket_id, user_id)).fetchone()

    # If user not logged in or has no listings, get any category in bucket
    if not user_id or not bucket:
        bucket = conn.execute('SELECT * FROM categories WHERE bucket_id = ? LIMIT 1', (bucket_id,)).fetchone()

    if not bucket:
        conn.close()
        flash("Item not found.", "error")
        return redirect(url_for('buy.buy'))

    # Get title and description from a listing in this bucket
    listing_info = conn.execute('''
        SELECT name, description
        FROM listings
        WHERE category_id IN (SELECT id FROM categories WHERE bucket_id = ?)
          AND active = 1
        LIMIT 1
    ''', (bucket_id,)).fetchone()

    listing_title = listing_info['name'] if listing_info and listing_info['name'] else None
    listing_description = listing_info['description'] if listing_info and listing_info['description'] else None

    cols = set(bucket.keys()) if hasattr(bucket, 'keys') else set()

    def take(*names):
        for n in names:
            if n in cols:
                v = bucket[n]
                if v is not None and str(v).strip() != "":
                    return v
        return None

    specs = {
        'Metal'          : take('metal'),
        'Product line'   : take('product_line', 'coin_series'),
        'Product type'   : take('product_type'),
        'Weight'         : take('weight'),
        'Year'           : take('year'),
        'Mint'           : take('mint'),
        'Purity'         : take('purity'),
        'Finish'         : take('finish'),
        'Series variant' : take('series_variant'),
    }
    # Don't convert None to '--' here - let the frontend handle empty values
    # This allows JavaScript to properly use its own fallback values
    # specs = {k: (('--' if (v is None or str(v).strip() == '') else v)) for k, v in specs.items()}

    # Add graded and grading_service fields directly from bucket (preserving original values)
    specs['graded'] = bucket['graded'] if 'graded' in cols else 0
    specs['grading_service'] = bucket['grading_service'] if 'grading_service' in cols else ''

    images = []

    # --- packaging filters from query (multi-select) ---
    packaging_styles = request.args.getlist('packaging_styles')
    # Clean and validate packaging styles
    packaging_styles = [ps.strip() for ps in packaging_styles if ps.strip()]

    # --- random year mode from query ---
    random_year = request.args.get('random_year') == '1'

    # Update Year display for Random Year mode
    if random_year:
        specs['Year'] = 'Random'

    # --- Random Year aggregation: find matching buckets ---
    if random_year:
        # Get all bucket_ids that match current bucket's specs except year
        matching_buckets_query = '''
            SELECT bucket_id FROM categories
            WHERE metal = ? AND product_type = ? AND weight = ? AND purity = ?
              AND mint = ? AND finish = ? AND grade = ? AND product_line = ?
              AND condition_category IS NOT DISTINCT FROM ?
              AND series_variant IS NOT DISTINCT FROM ?
              AND is_isolated = 0
        '''
        matching_buckets = conn.execute(matching_buckets_query, (
            bucket['metal'], bucket['product_type'], bucket['weight'], bucket['purity'],
            bucket['mint'], bucket['finish'], bucket['grade'], bucket['product_line'],
            bucket['condition_category'], bucket['series_variant']
        )).fetchall()

        bucket_ids = [row['bucket_id'] for row in matching_buckets] if matching_buckets else [bucket_id]
        bucket_id_clause = f"c.bucket_id IN ({','.join('?' * len(bucket_ids))})"
    else:
        bucket_ids = [bucket_id]
        bucket_id_clause = "c.bucket_id = ?"

    # Get ALL listings for best ask calculation (including user's own)
    all_listings_query = f'''
        SELECT l.*, c.metal, c.weight, c.product_type, c.year
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE {bucket_id_clause} AND l.active = 1
    '''
    all_listings_params = bucket_ids.copy()

    # Apply packaging filters to all_listings if specified
    if packaging_styles:
        packaging_placeholders = ','.join('?' * len(packaging_styles))
        all_listings_query += f' AND l.packaging_type IN ({packaging_placeholders})'
        all_listings_params.extend(packaging_styles)

    # Listings query (respect filters) - JOIN with categories to query by bucket_id
    # Include pricing fields for effective price calculation
    # Exclude user's own listings from the detailed listings display
    listings_query = f'''
        SELECT l.*, c.metal, c.weight, c.product_type, c.year
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE {bucket_id_clause} AND l.active = 1
    '''
    listings_params = bucket_ids.copy()

    # Exclude current user's own listings from detailed view if logged in
    if user_id:
        listings_query += ' AND l.seller_id != ?'
        listings_params.append(user_id)

    # Apply packaging filters to visible listings if specified
    if packaging_styles:
        packaging_placeholders = ','.join('?' * len(packaging_styles))
        listings_query += f' AND l.packaging_type IN ({packaging_placeholders})'
        listings_params.extend(packaging_styles)

    # Execute listings query
    listings_raw = conn.execute(listings_query, listings_params).fetchall()
    # Calculate effective prices for all listings
    listings = []
    for listing in listings_raw:
        listing_dict = dict(listing)
        listing_dict['effective_price'] = get_effective_price(listing_dict)
        listings.append(listing_dict)

    # Calculate availability from ALL listings (including user's own) for best ask
    all_listings_raw = conn.execute(all_listings_query, all_listings_params).fetchall()
    all_listings = []
    has_non_user_listings = False
    for listing in all_listings_raw:
        listing_dict = dict(listing)
        listing_dict['effective_price'] = get_effective_price(listing_dict)
        all_listings.append(listing_dict)
        # Check if this is not the user's listing
        if user_id and listing_dict['seller_id'] != user_id:
            has_non_user_listings = True

    # Calculate availability from ALL listings with effective prices
    if all_listings:
        lowest_price = min(l['effective_price'] for l in all_listings)
        total_available = sum(l['quantity'] for l in all_listings)
        # Determine if all listings are user's own
        all_listings_are_users = not has_non_user_listings and user_id is not None
        availability = {
            'lowest_price': lowest_price,
            'total_available': total_available,
            'all_listings_are_users': all_listings_are_users
        }
    else:
        availability = {
            'lowest_price': None,
            'total_available': 0,
            'all_listings_are_users': False
        }

    user_bids = []
    if user_id:
        user_bids_rows = conn.execute('''
            SELECT b.id, b.quantity_requested, b.remaining_quantity, b.price_per_coin,
                   b.status, b.created_at, b.active, b.requires_grading, b.preferred_grader,
                   b.pricing_mode, b.spot_premium, b.ceiling_price, b.pricing_metal,
                   c.metal, c.weight, c.product_type
            FROM bids b
            JOIN categories c ON b.category_id = c.id
            WHERE b.buyer_id = ? AND c.bucket_id = ? AND b.active = 1
            ORDER BY b.price_per_coin DESC
        ''', (user_id, bucket_id)).fetchall()
        # Calculate effective prices for user bids
        user_bids = []
        for bid in user_bids_rows:
            bid_dict = dict(bid)
            bid_dict['effective_price'] = get_effective_bid_price(bid_dict)
            user_bids.append(bid_dict)

    if user_id:
        bids_rows = conn.execute('''
            SELECT bids.id, bids.buyer_id, bids.category_id, bids.quantity_requested,
                   bids.remaining_quantity, bids.price_per_coin, bids.delivery_address,
                   bids.status, bids.created_at, bids.active, bids.requires_grading,
                   bids.preferred_grader, bids.pricing_mode, bids.spot_premium,
                   bids.ceiling_price, bids.pricing_metal,
                   users.username AS buyer_name,
                   c.metal, c.weight, c.product_type
            FROM bids
            JOIN users ON bids.buyer_id = users.id
            JOIN categories c ON bids.category_id = c.id
            WHERE c.bucket_id = ? AND bids.active = 1 AND bids.buyer_id != ?
            ORDER BY bids.price_per_coin DESC
        ''', (bucket_id, user_id)).fetchall()
    else:
        bids_rows = conn.execute('''
            SELECT bids.id, bids.buyer_id, bids.category_id, bids.quantity_requested,
                   bids.remaining_quantity, bids.price_per_coin, bids.delivery_address,
                   bids.status, bids.created_at, bids.active, bids.requires_grading,
                   bids.preferred_grader, bids.pricing_mode, bids.spot_premium,
                   bids.ceiling_price, bids.pricing_metal,
                   users.username AS buyer_name,
                   c.metal, c.weight, c.product_type
            FROM bids
            JOIN users ON bids.buyer_id = users.id
            JOIN categories c ON bids.category_id = c.id
            WHERE c.bucket_id = ? AND bids.active = 1
            ORDER BY bids.price_per_coin DESC
        ''', (bucket_id,)).fetchall()

    # Calculate effective prices for all bids
    bids = []
    for bid in bids_rows:
        bid_dict = dict(bid)
        bid_dict['effective_price'] = get_effective_bid_price(bid_dict)
        bids.append(bid_dict)

    # Get best bid - exclude current user's bids if logged in
    if user_id:
        best_bid_row = conn.execute('''
            SELECT bids.id, bids.price_per_coin, bids.quantity_requested,
                   bids.remaining_quantity, bids.delivery_address,
                   bids.pricing_mode, bids.spot_premium, bids.ceiling_price, bids.pricing_metal,
                   users.username AS buyer_name,
                   c.metal, c.weight, c.product_type
            FROM bids
            JOIN users ON bids.buyer_id = users.id
            JOIN categories c ON bids.category_id = c.id
            WHERE c.bucket_id = ? AND bids.active = 1
              AND bids.buyer_id != ?
            ORDER BY bids.price_per_coin DESC
            LIMIT 1
        ''', (bucket_id, user_id)).fetchone()
    else:
        best_bid_row = conn.execute('''
            SELECT bids.id, bids.price_per_coin, bids.quantity_requested,
                   bids.remaining_quantity, bids.delivery_address,
                   bids.pricing_mode, bids.spot_premium, bids.ceiling_price, bids.pricing_metal,
                   users.username AS buyer_name,
                   c.metal, c.weight, c.product_type
            FROM bids
            JOIN users ON bids.buyer_id = users.id
            JOIN categories c ON bids.category_id = c.id
            WHERE c.bucket_id = ? AND bids.active = 1
            ORDER BY bids.price_per_coin DESC
            LIMIT 1
        ''', (bucket_id,)).fetchone()

    if best_bid_row:
        best_bid = dict(best_bid_row)
        best_bid['effective_price'] = get_effective_bid_price(best_bid)
    else:
        best_bid = None

    # Get sellers with effective prices (use multi-year bucket_ids if Random Year is ON)
    sellers_query = f'''
        SELECT
          u.id                  AS seller_id,
          u.username            AS username,
          rr.rating             AS rating,
          rr.rating_count       AS rating_count,
          l.id                  AS listing_id,
          l.price_per_coin,
          l.pricing_mode,
          l.spot_premium,
          l.floor_price,
          l.pricing_metal,
          l.quantity,
          c.metal,
          c.weight,
          c.product_type,
          c.year
        FROM listings AS l
        JOIN categories c ON l.category_id = c.id
        JOIN users AS u ON u.id = l.seller_id
        LEFT JOIN (
            SELECT ratee_id, AVG(rating) AS rating, COUNT(*) AS rating_count
            FROM ratings GROUP BY ratee_id
        ) AS rr ON rr.ratee_id = u.id
        WHERE {bucket_id_clause} AND l.active = 1 AND l.quantity > 0
    '''
    sellers_params = bucket_ids.copy()

    # Apply packaging filters to sellers if specified
    if packaging_styles:
        packaging_placeholders = ','.join('?' * len(packaging_styles))
        sellers_query += f' AND l.packaging_type IN ({packaging_placeholders})'
        sellers_params.extend(packaging_styles)

    sellers_raw = conn.execute(sellers_query, sellers_params).fetchall()

    # Aggregate sellers with effective prices
    sellers_data = {}
    for row in sellers_raw:
        seller_id = row['seller_id']
        listing_dict = dict(row)
        effective_price = get_effective_price(listing_dict)

        if seller_id not in sellers_data:
            sellers_data[seller_id] = {
                'seller_id': seller_id,
                'username': row['username'],
                'rating': row['rating'],
                'rating_count': row['rating_count'],
                'lowest_price': effective_price,
                'total_qty': row['quantity']
            }
        else:
            sellers_data[seller_id]['lowest_price'] = min(
                sellers_data[seller_id]['lowest_price'],
                effective_price
            )
            sellers_data[seller_id]['total_qty'] += row['quantity']

    # Convert to list and sort
    sellers = list(sellers_data.values())
    sellers.sort(key=lambda s: (s['rating'] is None, -s['rating'] if s['rating'] else 0, s['lowest_price']))

    user_is_logged_in = 'user_id' in session

    # Fetch spot price for the bucket's metal
    bucket_metal = specs.get('Metal')
    spot_price = None
    if bucket_metal and bucket_metal != '--':
        spot_price = get_spot_price(bucket_metal)

    # Get isolated/set information from listing
    # Check if this bucket has isolated listings
    is_isolated = bucket['is_isolated'] if 'is_isolated' in cols else 0
    isolated_type = None
    issue_number = None
    issue_total = None
    set_items = []
    cover_photo_url = None
    thumbnail_urls = []
    # Listing-level fields for item details display
    listing_packaging_type = None
    listing_packaging_notes = None
    listing_condition_notes = None
    listing_edition_number = None
    listing_edition_total = None

    if is_isolated:
        # Get isolated details from any active listing in this bucket
        # Include packaging, condition, and edition fields for display
        listing_info = conn.execute('''
            SELECT isolated_type, issue_number, issue_total,
                   packaging_type, packaging_notes, condition_notes,
                   edition_number, edition_total
            FROM listings
            WHERE category_id IN (
                SELECT id FROM categories WHERE bucket_id = ?
            )
            AND active = 1
            LIMIT 1
        ''', (bucket_id,)).fetchone()

        if listing_info:
            isolated_type = listing_info['isolated_type']
            issue_number = listing_info['issue_number']
            issue_total = listing_info['issue_total']
            # Extract listing-level fields
            listing_packaging_type = listing_info['packaging_type']
            listing_packaging_notes = listing_info['packaging_notes']
            listing_condition_notes = listing_info['condition_notes']
            listing_edition_number = listing_info['edition_number']
            listing_edition_total = listing_info['edition_total']

            # Get the listing ID for photo retrieval
            listing_id_row = conn.execute('''
                SELECT l.id
                FROM listings l
                JOIN categories c ON l.category_id = c.id
                WHERE c.bucket_id = ? AND l.active = 1
                LIMIT 1
            ''', (bucket_id,)).fetchone()

            if listing_id_row:
                listing_id = listing_id_row['id']

                # Get all listing photos for gallery
                all_photos_raw = conn.execute('''
                    SELECT file_path
                    FROM listing_photos
                    WHERE listing_id = ?
                    ORDER BY id ASC
                ''', (listing_id,)).fetchall()

                if all_photos_raw:
                    # First photo is cover (shown on buy page tile), rest are item detail photos
                    cover_photo_url = f"/static/{all_photos_raw[0]['file_path']}"
                    thumbnail_urls = [f"/static/{p['file_path']}" for p in all_photos_raw[1:]]

                # For one-of-a-kind: gallery shows item photos (thumbnail_urls)
                # Fall back to cover_photo_url if no item photos (old listings created before fix)
                if isolated_type != 'set':
                    images = thumbnail_urls if thumbnail_urls else ([cover_photo_url] if cover_photo_url else [])

                # If this is a set, get all set items with photos
                if isolated_type == 'set':
                    # Get set items
                    set_items_raw = conn.execute('''
                        SELECT *
                        FROM listing_set_items
                        WHERE listing_id = ?
                        ORDER BY position_index
                    ''', (listing_id,)).fetchall()

                    set_items = [dict(item) for item in set_items_raw]

                    # Fetch multiple photos for each set item from listing_set_item_photos
                    for item in set_items:
                        photos_raw = conn.execute('''
                            SELECT file_path, position_index
                            FROM listing_set_item_photos
                            WHERE set_item_id = ?
                            ORDER BY position_index
                            LIMIT 3
                        ''', (item['id'],)).fetchall()
                        # Convert to URLs (up to 3 photos per item)
                        item['photo_urls'] = [f"/static/{p['file_path']}" for p in photos_raw]

                        # Collect each set item's first photo for the gallery
                        if photos_raw:
                            first_photo_url = f"/static/{photos_raw[0]['file_path']}"
                            if first_photo_url not in thumbnail_urls:
                                thumbnail_urls.append(first_photo_url)

                    # For set listings: gallery shows cover photo + each item's first photo
                    images = ([cover_photo_url] if cover_photo_url else []) + thumbnail_urls

    conn.close()

    # Compute fee indicator for this bucket
    fee_indicator = None
    fee_display = None
    fee_type = bucket['platform_fee_type'] if bucket else None
    fee_value = bucket['platform_fee_value'] if bucket else None

    if fee_type == 'percent' and fee_value is not None:
        if fee_value < DEFAULT_PLATFORM_FEE_VALUE:
            fee_indicator = 'reduced'
            fee_display = f"{fee_value:.1f}% fee"
        elif fee_value > DEFAULT_PLATFORM_FEE_VALUE:
            fee_indicator = 'elevated'
            fee_display = f"{fee_value:.1f}% fee"
    elif fee_type == 'flat' and fee_value is not None:
        fee_indicator = 'custom'
        fee_display = f"${fee_value:.2f} fee"

    return render_template(
        'view_bucket.html',
        bucket=bucket,
        fee_indicator=fee_indicator,
        fee_display=fee_display,
        specs=specs,
        images=images,
        listings=listings,
        availability=availability,
        packaging_styles=packaging_styles,  # <<< updated for multi-select packaging filter
        random_year=random_year,  # <<< added for random year mode
        user_bids=user_bids,
        bids=bids,
        best_bid=best_bid,
        sellers=sellers,
        user_is_logged_in=user_is_logged_in,
        spot_price=spot_price,   # <<< added
        is_isolated=is_isolated,  # <<< added for isolated/set display
        isolated_type=isolated_type,
        issue_number=issue_number,
        issue_total=issue_total,
        set_items=set_items,
        cover_photo_url=cover_photo_url,  # <<< URL for main gallery image
        thumbnail_urls=thumbnail_urls,  # <<< URLs for thumbnail gallery
        listing_title=listing_title,
        listing_description=listing_description,
        # Listing-level fields for item details display
        listing_packaging_type=listing_packaging_type,
        listing_packaging_notes=listing_packaging_notes,
        listing_condition_notes=listing_condition_notes,
        listing_edition_number=listing_edition_number,
        listing_edition_total=listing_edition_total
    )


@buy_bp.route('/bucket/<int:bucket_id>/availability_json')
def bucket_availability_json(bucket_id):
    conn = get_db_connection()
    user_id = session.get('user_id')

    # Parse packaging filters from query string
    packaging_styles = request.args.getlist('packaging_styles')

    # Get listings with pricing fields
    query = '''
        SELECT l.*, c.metal, c.weight, c.product_type
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ? AND l.active = 1
    '''
    params = [bucket_id]

    # Apply packaging filters if specified
    if packaging_styles:
        packaging_placeholders = ','.join('?' * len(packaging_styles))
        query += f' AND l.packaging_type IN ({packaging_placeholders})'
        params.extend(packaging_styles)

    # Exclude user's own listings if logged in
    if user_id:
        query += ' AND l.seller_id != ?'
        params.append(user_id)

    listings = conn.execute(query, params).fetchall()
    conn.close()

    # Calculate effective prices and aggregate
    if listings:
        lowest_price = None
        total_available = 0
        for listing in listings:
            listing_dict = dict(listing)
            effective_price = get_effective_price(listing_dict)
            if lowest_price is None or effective_price < lowest_price:
                lowest_price = effective_price
            total_available += listing_dict['quantity']
    else:
        lowest_price = None
        total_available = 0

    return {'lowest_price': lowest_price, 'total_available': total_available}
