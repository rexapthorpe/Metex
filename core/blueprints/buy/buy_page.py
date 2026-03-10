# core/blueprints/buy/buy_page.py

from flask import render_template, request, session
from database import get_db_connection
from services.pricing_service import get_effective_price
from services.reference_price_service import get_current_spots_from_snapshots
from services.ledger_constants import DEFAULT_PLATFORM_FEE_VALUE

from . import buy_bp


@buy_bp.route('/buy')
def buy():
    conn = get_db_connection()

    # Read grading filters from GET parameters
    graded_only = request.args.get('graded_only') == '1'
    any_grader = request.args.get('any_grader') == '1'
    pcgs = request.args.get('pcgs') == '1'
    ngc = request.args.get('ngc') == '1'

    # Read category filters from GET parameters
    filter_type = request.args.get('filter')  # 'popular', 'new'
    metal_filter = request.args.get('metal')  # 'Gold', 'Silver', 'Platinum'
    product_line_filter = request.args.get('product_line')  # 'American Eagle', etc.
    search_query = request.args.get('search', '').strip().lower()  # Free-text search

    # Get current user ID to exclude their own listings
    user_id = session.get('user_id')

    # Build category filter clauses
    category_filter_clauses = []
    category_filter_params = []

    if metal_filter:
        category_filter_clauses.append('categories.metal = ?')
        category_filter_params.append(metal_filter)

    if product_line_filter:
        category_filter_clauses.append('(categories.product_line = ? OR categories.coin_series = ?)')
        category_filter_params.extend([product_line_filter, product_line_filter])

    category_filter_sql = ''
    if category_filter_clauses:
        category_filter_sql = ' AND ' + ' AND '.join(category_filter_clauses)

    # Get NON-ISOLATED categories (standard listings)
    # IMPORTANT: Filter out categories with NULL bucket_id to prevent URL building errors
    standard_categories_query = '''
        SELECT DISTINCT
            categories.id AS category_id,
            categories.bucket_id,
            categories.metal,
            categories.product_type,
            categories.weight,
            categories.mint,
            categories.year,
            categories.finish,
            categories.grade,
            categories.coin_series,
            categories.product_line,
            categories.platform_fee_type,
            categories.platform_fee_value
        FROM categories
        WHERE categories.bucket_id IS NOT NULL
          AND categories.is_isolated = 0
    ''' + category_filter_sql
    standard_categories = conn.execute(standard_categories_query, category_filter_params).fetchall()

    # Get ISOLATED categories (one-of-a-kind and sets)
    isolated_categories_query = '''
        SELECT DISTINCT
            categories.id AS category_id,
            categories.bucket_id,
            categories.metal,
            categories.product_type,
            categories.weight,
            categories.mint,
            categories.year,
            categories.finish,
            categories.grade,
            categories.coin_series,
            categories.product_line,
            categories.is_isolated,
            categories.platform_fee_type,
            categories.platform_fee_value,
            listings.isolated_type,
            listings.issue_number,
            listings.issue_total,
            listings.name AS listing_title
        FROM categories
        LEFT JOIN listings ON categories.id = listings.category_id AND listings.active = 1
        WHERE categories.bucket_id IS NOT NULL
          AND categories.is_isolated = 1
    ''' + category_filter_sql
    isolated_categories = conn.execute(isolated_categories_query, category_filter_params).fetchall()

    # Combine both lists for listings query
    categories = list(standard_categories) + list(isolated_categories)

    # Then, get all active listings with pricing fields
    # IMPORTANT: Include ALL listings (including user's own) for best ask calculation
    listings_query = '''
        SELECT
            l.id, l.category_id, l.quantity, l.price_per_coin, l.seller_id,
            l.pricing_mode, l.spot_premium, l.floor_price, l.pricing_metal,
            l.graded, l.grading_service,
            c.metal, c.weight, c.product_type, c.bucket_id
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.active = 1 AND l.quantity > 0
    '''

    where_clauses = []
    params = []

    # DO NOT exclude user's own listings - we need them for best ask calculation

    if graded_only:
        where_clauses.append('l.graded = 1')
        if not any_grader:
            services = []
            if pcgs:
                services.append("'PCGS'")
            if ngc:
                services.append("'NGC'")
            if services:
                where_clauses.append(f"l.grading_service IN ({', '.join(services)})")
            elif not pcgs and not ngc:
                # No grader selected = no results
                conn.close()
                return render_template('buy.html', buckets=[], graded_only=graded_only)

    if where_clauses:
        listings_query += ' AND ' + ' AND '.join(where_clauses)

    listings = conn.execute(listings_query, params).fetchall()

    # Pre-fetch spot prices from DB snapshots — same source as the bucket page
    # so that the tile price always matches the Best Ask shown on /bucket/<id>.
    spot_prices = get_current_spots_from_snapshots(conn)

    # Calculate effective prices for all listings
    listings_with_prices = []
    for listing in listings:
        listing_dict = dict(listing)
        listing_dict['effective_price'] = get_effective_price(listing_dict, spot_prices)
        listings_with_prices.append(listing_dict)

    # Aggregate by bucket_id
    # Track all listings and non-user listings separately
    bucket_data = {}
    for listing in listings_with_prices:
        bucket_id = listing['bucket_id']
        is_user_listing = user_id and listing['seller_id'] == user_id

        if bucket_id not in bucket_data:
            bucket_data[bucket_id] = {
                'lowest_price': round(listing['effective_price'], 2),
                'lowest_price_pricing_mode': listing.get('pricing_mode', 'static'),
                'lowest_price_metal': (listing.get('pricing_metal') or listing.get('metal') or '').lower(),
                'total_available': listing['quantity'],
                'has_non_user_listings': not is_user_listing,
                'total_non_user_available': 0 if is_user_listing else listing['quantity']
            }
        else:
            if listing['effective_price'] < bucket_data[bucket_id]['lowest_price']:
                bucket_data[bucket_id]['lowest_price'] = round(listing['effective_price'], 2)
                bucket_data[bucket_id]['lowest_price_pricing_mode'] = listing.get('pricing_mode', 'static')
                bucket_data[bucket_id]['lowest_price_metal'] = (listing.get('pricing_metal') or listing.get('metal') or '').lower()
            bucket_data[bucket_id]['total_available'] += listing['quantity']
            if not is_user_listing:
                bucket_data[bucket_id]['has_non_user_listings'] = True
                bucket_data[bucket_id]['total_non_user_available'] += listing['quantity']

    # Last executed trade price per bucket — fallback when no active listings exist
    _cleared_rows = conn.execute('''
        SELECT c.bucket_id, oi.price_each
        FROM order_items oi
        JOIN listings l  ON oi.listing_id = l.id
        JOIN categories c ON l.category_id = c.id
        INNER JOIN (
            SELECT c2.bucket_id, MAX(oi2.order_id) AS max_order_id
            FROM order_items oi2
            JOIN listings l2  ON oi2.listing_id = l2.id
            JOIN categories c2 ON l2.category_id = c2.id
            WHERE c2.bucket_id IS NOT NULL
            GROUP BY c2.bucket_id
        ) latest ON c.bucket_id = latest.bucket_id
                AND oi.order_id = latest.max_order_id
    ''').fetchall()
    _last_cleared_by_bucket = {r['bucket_id']: float(r['price_each']) for r in _cleared_rows}

    # Display price priority: 1) best ask  2) last cleared trade  3) None
    for _key in bucket_data:
        best_ask = bucket_data[_key].get('lowest_price')
        if best_ask is not None:
            bucket_data[_key]['lowest_price'] = best_ask  # already rounded
        elif _key in _last_cleared_by_bucket:
            bucket_data[_key]['lowest_price'] = round(_last_cleared_by_bucket[_key], 2)
        else:
            bucket_data[_key]['lowest_price'] = None

    # Merge bucket data with standard categories
    standard_buckets = []
    for category in standard_categories:
        cat_dict = dict(category)
        bucket_id = cat_dict['bucket_id']

        # Skip categories with NULL bucket_id (defensive check)
        if bucket_id is None:
            continue

        if bucket_id in bucket_data:
            cat_dict['lowest_price'] = bucket_data[bucket_id]['lowest_price']
            cat_dict['total_available'] = bucket_data[bucket_id]['total_available']
            cat_dict['all_listings_are_users'] = not bucket_data[bucket_id]['has_non_user_listings']
            cat_dict['total_non_user_available'] = bucket_data[bucket_id]['total_non_user_available']
            pricing_mode = bucket_data[bucket_id].get('lowest_price_pricing_mode', 'static')
            cat_dict['is_variable_pricing'] = pricing_mode == 'premium_to_spot'
            if cat_dict['is_variable_pricing']:
                metal = bucket_data[bucket_id].get('lowest_price_metal', '')
                cat_dict['spot_price'] = spot_prices.get(metal)
                cat_dict['spot_metal'] = metal
        else:
            cat_dict['lowest_price'] = None
            cat_dict['total_available'] = 0
            cat_dict['all_listings_are_users'] = False
            cat_dict['total_non_user_available'] = 0
            cat_dict['is_variable_pricing'] = False

        standard_buckets.append(cat_dict)

    # Merge bucket data with isolated categories and split into two groups
    one_of_a_kind_buckets = []
    set_buckets = []

    for category in isolated_categories:
        cat_dict = dict(category)
        bucket_id = cat_dict['bucket_id']

        # Skip categories with NULL bucket_id (defensive check)
        if bucket_id is None:
            continue

        if bucket_id in bucket_data:
            cat_dict['lowest_price'] = bucket_data[bucket_id]['lowest_price']
            cat_dict['total_available'] = bucket_data[bucket_id]['total_available']
            cat_dict['all_listings_are_users'] = not bucket_data[bucket_id]['has_non_user_listings']
            cat_dict['total_non_user_available'] = bucket_data[bucket_id]['total_non_user_available']
            pricing_mode = bucket_data[bucket_id].get('lowest_price_pricing_mode', 'static')
            cat_dict['is_variable_pricing'] = pricing_mode == 'premium_to_spot'
            if cat_dict['is_variable_pricing']:
                metal = bucket_data[bucket_id].get('lowest_price_metal', '')
                cat_dict['spot_price'] = spot_prices.get(metal)
                cat_dict['spot_metal'] = metal
        else:
            cat_dict['lowest_price'] = None
            cat_dict['total_available'] = 0
            cat_dict['all_listings_are_users'] = False
            cat_dict['total_non_user_available'] = 0
            cat_dict['is_variable_pricing'] = False

        # ISOLATED BUCKET VISIBILITY RULE:
        # Skip isolated buckets with qty=0 (remove from Buy page)
        # Standard pooled buckets keep current behavior (shown even with qty=0)
        if cat_dict['total_available'] == 0:
            continue

        # Split into sets vs one-of-a-kind/numismatic
        if cat_dict.get('isolated_type') == 'set':
            set_buckets.append(cat_dict)
        else:
            # One-of-a-kind or numismatic (has issue_number/issue_total)
            one_of_a_kind_buckets.append(cat_dict)

    # Handle special sorting based on filter_type
    if filter_type == 'popular':
        # Get transaction counts per bucket for popularity sorting
        # Note: orders -> order_items -> listings -> categories
        popularity_query = '''
            SELECT c.bucket_id, COUNT(oi.id) as order_count
            FROM order_items oi
            JOIN listings l ON oi.listing_id = l.id
            JOIN categories c ON l.category_id = c.id
            WHERE c.bucket_id IS NOT NULL
            GROUP BY c.bucket_id
        '''
        popularity_data = {row['bucket_id']: row['order_count'] for row in conn.execute(popularity_query).fetchall()}

        # Add popularity count to buckets
        for bucket in standard_buckets + one_of_a_kind_buckets + set_buckets:
            bucket['popularity'] = popularity_data.get(bucket['bucket_id'], 0)

        # Sort by popularity (most popular first), then by price
        standard_buckets.sort(key=lambda b: (-b.get('popularity', 0), b['lowest_price'] is None, b['lowest_price'] if b['lowest_price'] is not None else 0))
        one_of_a_kind_buckets.sort(key=lambda b: (-b.get('popularity', 0), b['lowest_price'] is None, b['lowest_price'] if b['lowest_price'] is not None else 0))
        set_buckets.sort(key=lambda b: (-b.get('popularity', 0), b['lowest_price'] is None, b['lowest_price'] if b['lowest_price'] is not None else 0))

    elif filter_type == 'new':
        # Get newest listing ID per bucket (higher ID = newer listing)
        newest_query = '''
            SELECT c.bucket_id, MAX(l.id) as newest_id
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE l.active = 1 AND c.bucket_id IS NOT NULL
            GROUP BY c.bucket_id
        '''
        newest_data = {row['bucket_id']: row['newest_id'] for row in conn.execute(newest_query).fetchall()}

        # Add newest ID to buckets
        for bucket in standard_buckets + one_of_a_kind_buckets + set_buckets:
            bucket['newest_id'] = newest_data.get(bucket['bucket_id'], 0)

        # Sort by newest first (highest ID first)
        standard_buckets.sort(key=lambda b: (b.get('newest_id', 0)), reverse=True)
        one_of_a_kind_buckets.sort(key=lambda b: (b.get('newest_id', 0)), reverse=True)
        set_buckets.sort(key=lambda b: (b.get('newest_id', 0)), reverse=True)

    else:
        # Default sort: items with no listings last, then by lowest_price
        standard_buckets.sort(key=lambda b: (b['lowest_price'] is None, b['lowest_price'] if b['lowest_price'] is not None else 0))
        one_of_a_kind_buckets.sort(key=lambda b: (b['lowest_price'] is None, b['lowest_price'] if b['lowest_price'] is not None else 0))
        set_buckets.sort(key=lambda b: (b['lowest_price'] is None, b['lowest_price'] if b['lowest_price'] is not None else 0))

    # Apply free-text search filter if present
    if search_query:
        def _bucket_matches(bucket):
            fields = [
                bucket.get('metal') or '',
                bucket.get('product_line') or '',
                bucket.get('coin_series') or '',
                bucket.get('product_type') or '',
                bucket.get('mint') or '',
                bucket.get('year') or '',
                bucket.get('finish') or '',
                bucket.get('grade') or '',
                bucket.get('listing_title') or '',
                bucket.get('weight') or '',
            ]
            return any(search_query in str(f).lower() for f in fields)

        standard_buckets = [b for b in standard_buckets if _bucket_matches(b)]
        one_of_a_kind_buckets = [b for b in one_of_a_kind_buckets if _bucket_matches(b)]
        set_buckets = [b for b in set_buckets if _bucket_matches(b)]

    # Add fee indicator data for buckets with non-default fees
    for bucket in standard_buckets + one_of_a_kind_buckets + set_buckets:
        fee_type = bucket.get('platform_fee_type')
        fee_value = bucket.get('platform_fee_value')

        # Only show indicator if bucket has a custom fee set
        if fee_type == 'percent' and fee_value is not None:
            if fee_value < DEFAULT_PLATFORM_FEE_VALUE:
                bucket['fee_indicator'] = 'reduced'
                bucket['fee_display'] = f"{fee_value:.1f}% fee"
            elif fee_value > DEFAULT_PLATFORM_FEE_VALUE:
                bucket['fee_indicator'] = 'elevated'
                bucket['fee_display'] = f"{fee_value:.1f}% fee"
            # If equal to default, no indicator needed
        elif fee_type == 'flat' and fee_value is not None:
            # Flat fees are always "custom" - show as elevated/neutral
            bucket['fee_indicator'] = 'custom'
            bucket['fee_display'] = f"${fee_value:.2f} fee"

    # Add tile images for one-of-a-kind listings
    for bucket in one_of_a_kind_buckets:
        bucket_id = bucket['bucket_id']
        # Get first photo from any active listing in this bucket
        photo_row = conn.execute('''
            SELECT lp.file_path
            FROM listing_photos lp
            JOIN listings l ON lp.listing_id = l.id
            JOIN categories c ON l.category_id = c.id
            WHERE c.bucket_id = ? AND l.active = 1
            ORDER BY lp.id ASC
            LIMIT 1
        ''', (bucket_id,)).fetchone()
        bucket['tile_image_url'] = f"/static/{photo_row['file_path']}" if photo_row else None

    # Add tile images for set listings (cover photo)
    for bucket in set_buckets:
        bucket_id = bucket['bucket_id']
        # Get first photo (cover photo) from any active listing in this bucket
        photo_row = conn.execute('''
            SELECT lp.file_path
            FROM listing_photos lp
            JOIN listings l ON lp.listing_id = l.id
            JOIN categories c ON l.category_id = c.id
            WHERE c.bucket_id = ? AND l.active = 1
            ORDER BY lp.id ASC
            LIMIT 1
        ''', (bucket_id,)).fetchone()
        bucket['tile_image_url'] = f"/static/{photo_row['file_path']}" if photo_row else None

    conn.close()

    return render_template('buy.html',
                         standard_buckets=standard_buckets,
                         one_of_a_kind_buckets=one_of_a_kind_buckets,
                         set_buckets=set_buckets,
                         graded_only=graded_only,
                         filter_type=filter_type,
                         metal_filter=metal_filter,
                         product_line_filter=product_line_filter,
                         search_query=search_query)
