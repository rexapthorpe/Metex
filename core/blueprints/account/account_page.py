"""
Account Page Route

Main account page that loads all account data for the user.
This is the primary route at /account.
"""

from flask import render_template, session, redirect, url_for
from database import get_db_connection
from utils.cart_utils import build_cart_summary, validate_and_refill_cart
from services.pricing_service import get_effective_price, get_effective_bid_price
from services.spot_price_service import get_current_spot_prices
from datetime import datetime

from . import account_bp


@account_bp.route('/account')
@account_bp.route('/account')
def account():
    # 1) Authentication guard
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    user_id = session['user_id']

    conn = get_db_connection()

    # Get user information
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    # Get user addresses (from addresses table)
    addresses = conn.execute(
        "SELECT * FROM addresses WHERE user_id = ? ORDER BY id",
        (user_id,)
    ).fetchall()

    # Get user preferences for notifications (may be NULL if never set)
    user_preferences = conn.execute(
        "SELECT * FROM user_preferences WHERE user_id = ?",
        (user_id,)
    ).fetchone()

    # 2) Bids (with category details and pricing info)
    bids_raw = conn.execute(
        """SELECT
             b.*,
             c.bucket_id, c.weight, c.metal, c.product_type, c.mint, c.year, c.finish,
             c.grade, c.coin_series, c.purity, c.product_line
           FROM bids AS b
           LEFT JOIN categories AS c ON b.category_id = c.id
          WHERE b.buyer_id = ?
          ORDER BY b.created_at DESC
        """, (user_id,)
    ).fetchall()

    # Get spot prices for calculating effective prices
    spot_data = get_current_spot_prices()
    spot_prices = spot_data['prices']

    # Process each bid to calculate effective prices
    bids = []
    for bid_row in bids_raw:
        bid = dict(bid_row)

        # Calculate bid effective price (min of spot+premium and ceiling)
        if bid.get('pricing_mode') == 'premium_to_spot':
            bid['bid_effective_price'] = get_effective_bid_price(bid, spot_prices)
            bid['bid_ceiling_price_display'] = bid.get('ceiling_price', 0)
        else:
            # Fixed price bid
            bid['bid_effective_price'] = bid.get('price_per_coin', 0)
            bid['bid_ceiling_price_display'] = None

        # Find the best (lowest effective price) listing for this category
        listings_for_category = conn.execute(
            """SELECT l.id, l.price_per_coin, l.pricing_mode, l.spot_premium,
                      l.floor_price, l.pricing_metal,
                      c.metal, c.weight
               FROM listings l
               JOIN categories c ON l.category_id = c.id
               WHERE l.category_id = ?
                 AND l.active = 1
                 AND l.quantity > 0
               ORDER BY l.price_per_coin ASC
            """,
            (bid['category_id'],)
        ).fetchall()

        # Calculate effective price for each listing and find the minimum
        min_listing_effective_price = None
        for listing_row in listings_for_category:
            listing_dict = dict(listing_row)
            if listing_dict.get('pricing_mode') == 'premium_to_spot':
                # Calculate effective price: max(spot + premium, floor)
                listing_effective = get_effective_price(listing_dict, spot_prices)
            else:
                # Fixed price listing
                listing_effective = listing_dict.get('price_per_coin', 0)

            if min_listing_effective_price is None or listing_effective < min_listing_effective_price:
                min_listing_effective_price = listing_effective

        bid['listing_effective_price'] = min_listing_effective_price

        # Add current spot price for this bid's metal
        bid_metal = bid.get('metal', '').lower() if bid.get('metal') else ''
        bid['current_spot_price'] = spot_prices.get(bid_metal, 0)

        # Get a photo for this bid from listings in the same bucket
        if bid.get('bucket_id'):
            photo_row = conn.execute('''
                SELECT lp.file_path
                FROM listing_photos lp
                JOIN listings l ON lp.listing_id = l.id
                JOIN categories c ON l.category_id = c.id
                WHERE c.bucket_id = ?
                ORDER BY lp.id ASC
                LIMIT 1
            ''', (bid['bucket_id'],)).fetchone()
            bid['photo_path'] = photo_row['file_path'] if photo_row else None
        else:
            bid['photo_path'] = None

        # Format bid created_at timestamp
        if bid.get('created_at'):
            dt = datetime.fromisoformat(bid['created_at'])
            bid['created_at'] = dt.strftime('%H:%M, %d, %A, %B, %Y')

        bids.append(bid)

    # 3) Ratings
    avg_rating = conn.execute(
        "SELECT ROUND(AVG(rating),2) AS average FROM ratings WHERE ratee_id = ?",
        (user_id,)
    ).fetchone()
    # Received ratings (ratings I received from others)
    received_ratings = conn.execute(
        """SELECT r.id, r.rating, r.comment, r.timestamp, r.order_id,
                  u.username AS rater_name, u.username AS rater_username,
                  GROUP_CONCAT(c.metal || ' ' || c.product_line || ' ' || c.weight, ', ') AS product_name,
                  MIN(lp.file_path) AS product_image,
                  'received' AS type
           FROM ratings r
           JOIN users u ON r.rater_id = u.id
           JOIN orders o ON r.order_id = o.id
           JOIN order_items oi ON oi.order_id = o.id
           JOIN listings l ON oi.listing_id = l.id
           JOIN categories c ON l.category_id = c.id
           LEFT JOIN listing_photos lp ON lp.listing_id = l.id
          WHERE r.ratee_id = ?
          GROUP BY r.id
          ORDER BY r.timestamp DESC
        """, (user_id,)
    ).fetchall()

    # Given ratings (ratings I gave to others)
    given_ratings = conn.execute(
        """SELECT r.id, r.rating, r.comment, r.timestamp, r.order_id,
                  u.username AS ratee_name, u.username AS ratee_username,
                  GROUP_CONCAT(c.metal || ' ' || c.product_line || ' ' || c.weight, ', ') AS product_name,
                  MIN(lp.file_path) AS product_image,
                  'given' AS type
           FROM ratings r
           JOIN users u ON r.ratee_id = u.id
           JOIN orders o ON r.order_id = o.id
           JOIN order_items oi ON oi.order_id = o.id
           JOIN listings l ON oi.listing_id = l.id
           JOIN categories c ON l.category_id = c.id
           LEFT JOIN listing_photos lp ON lp.listing_id = l.id
          WHERE r.rater_id = ?
          GROUP BY r.id
          ORDER BY r.timestamp DESC
        """, (user_id,)
    ).fetchall()

    # Pending ratings (orders where I haven't rated yet)
    pending_ratings = conn.execute(
        """SELECT o.id AS order_id,
                  CASE WHEN o.buyer_id = ? THEN l.seller_id ELSE o.buyer_id END AS ratee_id,
                  CASE WHEN o.buyer_id = ? THEN u.username ELSE ub.username END AS ratee_name,
                  CASE WHEN o.buyer_id = ? THEN u.username ELSE ub.username END AS ratee_username,
                  CASE WHEN o.buyer_id = ? THEN 'seller' ELSE 'buyer' END AS ratee_type,
                  o.created_at AS timestamp,
                  GROUP_CONCAT(c.metal || ' ' || c.product_line || ' ' || c.weight, ', ') AS product_name,
                  MIN(lp.file_path) AS product_image,
                  'pending' AS type
           FROM orders o
           JOIN order_items oi ON oi.order_id = o.id
           JOIN listings l ON oi.listing_id = l.id
           JOIN categories c ON l.category_id = c.id
           JOIN users u ON l.seller_id = u.id
           LEFT JOIN users ub ON o.buyer_id = ub.id
           LEFT JOIN listing_photos lp ON lp.listing_id = l.id
          WHERE (o.buyer_id = ? OR l.seller_id = ?)
            AND o.status IN ('Delivered', 'Complete')
            AND NOT EXISTS (
                SELECT 1 FROM ratings r
                WHERE r.order_id = o.id AND r.rater_id = ?
            )
          GROUP BY o.id
          ORDER BY o.created_at DESC
        """, (user_id, user_id, user_id, user_id, user_id, user_id, user_id)
    ).fetchall()

    # Format rating timestamps
    formatted_received = []
    for rating in received_ratings:
        r = dict(rating)
        if r.get('timestamp'):
            dt = datetime.fromisoformat(r['timestamp'])
            r['timestamp'] = dt.strftime('%H:%M, %d, %A, %B, %Y')
        formatted_received.append(r)
    received_ratings = formatted_received

    formatted_given = []
    for rating in given_ratings:
        r = dict(rating)
        if r.get('timestamp'):
            dt = datetime.fromisoformat(r['timestamp'])
            r['timestamp'] = dt.strftime('%H:%M, %d, %A, %B, %Y')
        formatted_given.append(r)
    given_ratings = formatted_given

    formatted_pending = []
    for rating in pending_ratings:
        r = dict(rating)
        if r.get('timestamp'):
            dt = datetime.fromisoformat(r['timestamp'])
            r['timestamp'] = dt.strftime('%H:%M, %d, %A, %B, %Y')
        formatted_pending.append(r)
    pending_ratings = formatted_pending

    # 4) Orders (pending & completed) + helper to attach sellers and cancellation status
    def attach_sellers(order_rows):
        out = []
        for row in order_rows:
            order = dict(row)

            # Get sellers with their shipping/tracking status
            seller_rows = conn.execute(
                """SELECT DISTINCT u.id AS seller_id, u.username,
                          sot.tracking_number, sot.carrier, sot.updated_at
                   FROM order_items oi
                   JOIN listings l ON oi.listing_id = l.id
                   JOIN users u ON l.seller_id = u.id
                   LEFT JOIN seller_order_tracking sot
                        ON sot.order_id = oi.order_id AND sot.seller_id = u.id
                  WHERE oi.order_id = ?
                """, (order['id'],)
            ).fetchall()

            # Build seller info with shipping status
            sellers_info = []
            for sr in seller_rows:
                seller_data = {
                    'id': sr['seller_id'],
                    'username': sr['username'],
                    'tracking_number': sr['tracking_number'],
                    'carrier': sr['carrier'],
                    'shipped_at': sr['updated_at'],
                    'has_shipped': bool(sr['tracking_number'])
                }
                # Determine seller-specific status based on tracking
                if order['status'] in ['Delivered', 'Complete']:
                    seller_data['status'] = 'Delivered'
                elif sr['tracking_number']:
                    seller_data['status'] = 'Shipped'
                elif order['status'] in ['Pending Shipment', 'Awaiting Shipment']:
                    seller_data['status'] = 'Processing'
                else:
                    seller_data['status'] = 'Placed'
                sellers_info.append(seller_data)

            order['sellers_info'] = sellers_info
            order['sellers'] = [r['username'] for r in seller_rows]

            # Set year to "Random" if order has items from multiple years
            if order.get('year_count', 1) > 1:
                order['year'] = 'Random'

            # Get cancellation status for this order
            cancel_request = conn.execute(
                """SELECT status FROM cancellation_requests WHERE order_id = ?""",
                (order['id'],)
            ).fetchone()
            order['cancellation_status'] = cancel_request['status'] if cancel_request else None

            # Check if any seller has tracking for this order
            has_tracking = conn.execute(
                """SELECT 1 FROM seller_order_tracking
                   WHERE order_id = ? AND tracking_number IS NOT NULL AND tracking_number != ''
                   LIMIT 1""",
                (order['id'],)
            ).fetchone()
            order['has_tracking'] = bool(has_tracking) or bool(order.get('tracking_number'))

            out.append(order)
        return out

    raw_pending = conn.execute(
        """SELECT
             o.id AS id,
             SUM(oi.quantity) AS quantity,
             COUNT(DISTINCT oi.id) AS item_count,
             SUM(oi.quantity*oi.price_each)*1.0/SUM(oi.quantity) AS price_each,
             o.status, o.created_at AS order_date,
             COALESCE(o.delivery_address, o.shipping_address) AS delivery_address,
             o.tracking_number,
             MIN(c.metal)       AS metal,
             MIN(c.product_type)AS product_type,
             MIN(c.weight)      AS weight,
             MIN(c.purity)      AS purity,
             MIN(c.mint)        AS mint,
             MIN(c.year)        AS year,
             COUNT(DISTINCT c.year) AS year_count,
             MIN(c.finish)      AS finish,
             MIN(c.grade)       AS grade,
             MIN(c.product_line)AS product_line,
             MIN(l.graded)      AS graded,
             MIN(l.grading_service) AS grading_service,
             MIN(c.is_isolated) AS is_isolated,
             MIN(l.isolated_type) AS isolated_type,
             MIN(l.issue_number) AS issue_number,
             MIN(l.issue_total) AS issue_total,
             MIN(u.username)    AS seller_username,
             MIN(lp.file_path) AS photo_path,
             MAX(oi.third_party_grading_requested) AS third_party_grading,
             SUM(oi.grading_fee_charged) AS grading_fee_total,
             MAX(oi.grading_service) AS grading_service_requested,
             MAX(oi.grading_status) AS grading_status,
             (SELECT 1 FROM ratings r
                WHERE r.order_id = o.id
                  AND r.rater_id = ?
             ) AS already_rated,
             (SELECT COUNT(*) FROM order_items oi2
                JOIN portfolio_exclusions pe ON pe.order_item_id = oi2.id
               WHERE oi2.order_id = o.id
                 AND pe.user_id = ?
             ) AS excluded_count
           FROM orders o
           JOIN order_items oi ON oi.order_id = o.id
           JOIN listings l     ON oi.listing_id = l.id
           JOIN categories c   ON l.category_id = c.id
           JOIN users u        ON l.seller_id = u.id
           LEFT JOIN listing_photos lp ON lp.listing_id = l.id
          WHERE o.buyer_id = ?
            AND o.status IN ('Pending','Pending Shipment','Awaiting Shipment','Awaiting Delivery')
          GROUP BY o.id, o.status, o.created_at, o.delivery_address, o.shipping_address, o.tracking_number
          ORDER BY o.created_at DESC
        """, (user_id, user_id, user_id)
    ).fetchall()
    raw_completed = conn.execute(
        """SELECT
             o.id AS id,
             SUM(oi.quantity) AS quantity,
             COUNT(DISTINCT oi.id) AS item_count,
             SUM(oi.quantity*oi.price_each)*1.0/SUM(oi.quantity) AS price_each,
             o.status, o.created_at AS order_date,
             COALESCE(o.delivery_address, o.shipping_address) AS delivery_address,
             o.tracking_number,
             MIN(c.metal)       AS metal,
             MIN(c.product_type)AS product_type,
             MIN(c.weight)      AS weight,
             MIN(c.purity)      AS purity,
             MIN(c.mint)        AS mint,
             MIN(c.year)        AS year,
             COUNT(DISTINCT c.year) AS year_count,
             MIN(c.finish)      AS finish,
             MIN(c.grade)       AS grade,
             MIN(c.product_line)AS product_line,
             MIN(l.graded)      AS graded,
             MIN(l.grading_service) AS grading_service,
             MIN(c.is_isolated) AS is_isolated,
             MIN(l.isolated_type) AS isolated_type,
             MIN(l.issue_number) AS issue_number,
             MIN(l.issue_total) AS issue_total,
             MIN(u.username)    AS seller_username,
             MIN(lp.file_path) AS photo_path,
             MAX(oi.third_party_grading_requested) AS third_party_grading,
             SUM(oi.grading_fee_charged) AS grading_fee_total,
             MAX(oi.grading_service) AS grading_service_requested,
             MAX(oi.grading_status) AS grading_status,
             (SELECT 1 FROM ratings r
                WHERE r.order_id = o.id
                  AND r.rater_id = ?
             ) AS already_rated,
             (SELECT COUNT(*) FROM order_items oi2
                JOIN portfolio_exclusions pe ON pe.order_item_id = oi2.id
               WHERE oi2.order_id = o.id
                 AND pe.user_id = ?
             ) AS excluded_count
           FROM orders o
           JOIN order_items oi ON oi.order_id = o.id
           JOIN listings l     ON oi.listing_id = l.id
           JOIN categories c   ON l.category_id = c.id
           JOIN users u        ON l.seller_id = u.id
           LEFT JOIN listing_photos lp ON lp.listing_id = l.id
          WHERE o.buyer_id = ?
            AND o.status IN ('Delivered','Complete','Refunded','Cancelled','Canceled')
          GROUP BY o.id, o.status, o.created_at, o.delivery_address, o.shipping_address, o.tracking_number
          ORDER BY o.created_at DESC
        """, (user_id, user_id, user_id)
    ).fetchall()

    pending_orders   = attach_sellers(raw_pending)
    completed_orders = attach_sellers(raw_completed)

    # Add image URLs to orders
    for order in pending_orders + completed_orders:
        raw_path = order.get('photo_path')
        image_url = None
        if raw_path:
            raw_path = str(raw_path)
            if raw_path.startswith('/'):
                image_url = raw_path
            elif raw_path.startswith('static/'):
                image_url = '/' + raw_path
            else:
                image_url = url_for('static', filename=raw_path)
        order['image_url'] = image_url

    # Parse delivery addresses from plain text to structured format
    def parse_delivery_address(address_text):
        """Parse plain text address into structured format for modal display"""
        if not address_text or address_text in ('null', 'None', ''):
            return None

        try:
            # Format: "street • street_line2 • city, state zip"
            # Split by bullet character (•) or similar separators
            parts = address_text.replace('�', '•').split('•')

            if len(parts) >= 3:
                street = parts[0].strip()
                street_line2 = parts[1].strip() if len(parts) > 1 else ''
                location_part = parts[2].strip() if len(parts) > 2 else ''

                # Parse "city, state zip"
                if ',' in location_part:
                    city_part, state_zip = location_part.split(',', 1)
                    city = city_part.strip()
                    state_zip = state_zip.strip().split()
                    state = state_zip[0] if state_zip else ''
                    zip_code = state_zip[1] if len(state_zip) > 1 else ''
                else:
                    city = ''
                    state = ''
                    zip_code = ''

                return {
                    'street': street,
                    'street_line2': street_line2,
                    'city': city,
                    'state': state,
                    'zip_code': zip_code
                }
            else:
                # Fallback: return as plain string if parsing fails
                return address_text
        except Exception:
            # If parsing fails, return the original string
            return address_text

    for order in pending_orders + completed_orders:
        if order.get('delivery_address'):
            parsed = parse_delivery_address(order['delivery_address'])
            if parsed:
                import json
                order['delivery_address'] = json.dumps(parsed) if isinstance(parsed, dict) else parsed

    # Format order dates
    for order in pending_orders + completed_orders:
        if order.get('order_date'):
            dt = datetime.fromisoformat(order['order_date'])
            order['formatted_order_date'] = dt.strftime('%H:%M, %d, %A, %B, %Y')

    # 5) Active listings & sales
    # Note: Use subquery to get only ONE photo per listing (the first one by ID)
    active_listings_raw = conn.execute(
        """SELECT l.id   AS listing_id,
                l.quantity,
                l.price_per_coin,
                l.pricing_mode,
                l.spot_premium,
                l.floor_price,
                l.pricing_metal,
                (SELECT file_path FROM listing_photos WHERE listing_id = l.id ORDER BY id LIMIT 1) AS photo_path,
                l.graded,
                l.grading_service,
                l.isolated_type,
                c.id AS category_id,
                c.bucket_id,
                c.is_isolated,
                c.metal, c.product_type,
                c.special_designation,
                c.weight, c.mint, c.year, c.finish, c.grade,
                c.purity, c.product_line, c.coin_series,
                c.condition_category, c.series_variant,
                l.packaging_type, l.packaging_notes, l.condition_notes
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.seller_id = ?
            AND l.active = 1
            AND l.quantity > 0
        """, (user_id,)
    ).fetchall()

    # Calculate effective price for variable pricing listings
    # Note: spot_prices already calculated earlier for bids
    active_listings = []
    for listing in active_listings_raw:
        listing_dict = dict(listing)
        # Calculate effective price if variable pricing
        if listing_dict.get('pricing_mode') == 'premium_to_spot':
            listing_dict['effective_price'] = get_effective_price(listing_dict, spot_prices)
        else:
            listing_dict['effective_price'] = listing_dict.get('price_per_coin', 0)
        active_listings.append(listing_dict)

    sales_raw = conn.execute(
        """SELECT o.id AS order_id,
                  o.buyer_id AS buyer_id,
                  c.metal, c.product_type, c.weight, c.mint, c.year,
                  c.finish, c.grade, c.purity, c.product_line, c.coin_series,
                  c.special_designation,
                  oi.quantity,
                  COALESCE(oi.seller_price_each, oi.price_each) AS price_each,
                  l.graded,
                  l.grading_service,
                  c.is_isolated,
                  l.isolated_type,
                  l.issue_number,
                  l.issue_total,
                  u.username AS buyer_username,
                  u.first_name AS buyer_first_name,
                  u.last_name AS buyer_last_name,
                  o.shipping_address AS shipping_address,
                  o.shipping_address AS delivery_address,
                  o.recipient_first_name,
                  o.recipient_last_name,
                  o.status,
                  o.created_at AS order_date,
                  o.tracking_number,
                  oi.third_party_grading_requested,
                  oi.grading_fee_charged,
                  oi.grading_service AS grading_service_requested,
                  oi.grading_status,
                  oi.seller_tracking_to_grader,
                  (SELECT 1 FROM ratings r
                     WHERE r.order_id = o.id
                       AND r.rater_id = ?
                  ) AS already_rated,
                  (SELECT 1 FROM reports rpt
                     WHERE rpt.order_id = o.id
                       AND rpt.reporter_user_id = ?
                       AND rpt.reported_user_id = o.buyer_id
                  ) AS already_reported
           FROM orders o
           JOIN order_items oi ON o.id = oi.order_id
           JOIN listings l     ON oi.listing_id = l.id
           JOIN categories c   ON l.category_id = c.id
           JOIN users u        ON o.buyer_id = u.id
          WHERE l.seller_id = ?
          ORDER BY o.created_at DESC
        """, (user_id, user_id, user_id)
    ).fetchall()

    # Build shipping name from order-level recipient fields (source of truth)
    # Fallback: parse from delivery_address for old orders (backward compatibility)
    sales = []
    for sale_row in sales_raw:
        sale = dict(sale_row)

        # Priority 1: Use recipient names from order (if available)
        if sale.get('recipient_first_name') or sale.get('recipient_last_name'):
            first = sale.get('recipient_first_name', '').strip()
            last = sale.get('recipient_last_name', '').strip()
            shipping_name = f"{first} {last}".strip()
        else:
            # Priority 2: Parse from delivery_address (backward compatibility for old orders)
            # Old format: "Name • Street • Street2 • City, State ZIP" (has name embedded)
            shipping_name = None
            if sale.get('delivery_address'):
                parts = sale['delivery_address'].split('•')

                # If 4+ parts, first part is the name
                if len(parts) >= 4:
                    shipping_name = parts[0].strip()
                # If 3 parts, check if first part looks like a name (not an address)
                elif len(parts) == 3:
                    first_part = parts[0].strip()
                    # Heuristic: names have spaces and don't start with digits
                    if ' ' in first_part and (not first_part or not first_part[0].isdigit()):
                        shipping_name = first_part

        # Add shipping_name to sale dict
        sale['shipping_name'] = shipping_name

        # Format order date
        if sale.get('order_date'):
            dt = datetime.fromisoformat(sale['order_date'])
            sale['order_date'] = dt.strftime('%H:%M, %d, %A, %B, %Y')

        # Get cancellation request data for this order (for seller view)
        cancel_request = conn.execute(
            """SELECT cr.id, cr.status, cr.reason, cr.additional_details, cr.created_at
               FROM cancellation_requests cr
               WHERE cr.order_id = ?""",
            (sale['order_id'],)
        ).fetchone()

        if cancel_request:
            sale['cancellation_request'] = dict(cancel_request)

            # Check if this seller has already responded
            seller_response = conn.execute(
                """SELECT response, responded_at
                   FROM cancellation_seller_responses
                   WHERE request_id = ? AND seller_id = ?""",
                (cancel_request['id'], user_id)
            ).fetchone()

            sale['cancellation_response'] = dict(seller_response) if seller_response else None

            # Flatten for template access
            sale['cancel_status'] = cancel_request['status']
            sale['cancel_reason'] = cancel_request['reason']
            sale['seller_cancel_response'] = seller_response['response'] if seller_response else None
        else:
            sale['cancellation_request'] = None
            sale['cancellation_response'] = None
            sale['cancel_status'] = None
            sale['cancel_reason'] = None
            sale['seller_cancel_response'] = None

        sales.append(sale)

    # 6) Cart — single authoritative source for all pricing and totals
    validate_and_refill_cart(conn, user_id)
    cart_summary = build_cart_summary(conn, user_id)
    buckets = cart_summary['buckets']
    cart_total = cart_summary['subtotal']
    grand_total = cart_summary['grand_total']
    has_tpg = cart_summary['has_tpg']

    # 7) Conversations
    # Ensure message_reads table exists
    conn.execute("""
      CREATE TABLE IF NOT EXISTS message_reads (
        user_id        INTEGER NOT NULL,
        participant_id INTEGER NOT NULL,
        order_id       INTEGER NOT NULL,
        last_read_ts   DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, participant_id, order_id)
      )
    """)

    conv_rows = conn.execute(
        """
        SELECT
          m.order_id,
          o.buyer_id                    AS order_buyer_id,
          CASE WHEN m.sender_id = ? THEN m.receiver_id ELSE m.sender_id END
            AS other_user_id,
          u.username            AS other_username,
          u.is_admin            AS is_admin_user,
          m.content             AS last_message_content,
          m.timestamp           AS last_message_time,
          (SELECT COUNT(*)
           FROM messages m2
           LEFT JOIN message_reads mr
             ON mr.user_id = ?
             AND mr.participant_id = CASE WHEN m.sender_id = ? THEN m.receiver_id ELSE m.sender_id END
             AND mr.order_id = m.order_id
           WHERE m2.order_id = m.order_id
             AND m2.receiver_id = ?
             AND m2.sender_id = CASE WHEN m.sender_id = ? THEN m.receiver_id ELSE m.sender_id END
             AND (mr.last_read_ts IS NULL OR m2.timestamp > mr.last_read_ts)
          ) AS unread_count
        FROM messages m
        LEFT JOIN orders o ON o.id = m.order_id
        JOIN users u  ON u.id = (CASE WHEN m.sender_id = ? THEN m.receiver_id ELSE m.sender_id END)
        WHERE m.sender_id = ? OR m.receiver_id = ?
        GROUP BY m.order_id, other_user_id
        ORDER BY u.is_admin DESC, last_message_time DESC
        """, (user_id, user_id, user_id, user_id, user_id, user_id, user_id, user_id)
    ).fetchall()

    conversations = []
    has_unread_admin_message = False
    for r in conv_rows:
        is_admin = bool(r['is_admin_user'])
        # Determine conversation type: admin messages (order_id=0) are 'admin' type
        if r['order_id'] == 0 or is_admin:
            conv_type = 'admin'
        elif r['order_buyer_id'] == user_id:
            conv_type = 'seller'
        else:
            conv_type = 'buyer'
        convo = {
            'order_id':             r['order_id'],
            'other_user_id':        r['other_user_id'],
            'other_username':       r['other_username'],
            'is_admin':             is_admin,
            'last_message_content': r['last_message_content'],
            'last_message_time':    r['last_message_time'],
            'unread_count':         r['unread_count'],
            'type': conv_type,
            'messages': []
        }
        # Track if there's an unread message from admin
        if is_admin and r['unread_count'] > 0:
            has_unread_admin_message = True
        history = conn.execute(
            """
            SELECT sender_id, receiver_id, content, timestamp
              FROM messages
             WHERE order_id = ?
               AND ((sender_id = ? AND receiver_id = ?)
                 OR (sender_id = ? AND receiver_id = ?))
             ORDER BY timestamp ASC
            """,
            (r['order_id'],
             user_id, r['other_user_id'],
             r['other_user_id'], user_id)
        ).fetchall()
        convo['messages'] = []
        for m in history:
            msg = dict(m)
            if msg.get('timestamp'):
                msg['timestamp'] = datetime.fromisoformat(msg['timestamp']).strftime('%H:%M, %d, %A, %B, %Y')
            convo['messages'].append({
                'sender_id': msg['sender_id'],
                'content': msg['content'],
                'timestamp': msg['timestamp']
            })

        # Format last_message_time
        if convo.get('last_message_time'):
            dt = datetime.fromisoformat(convo['last_message_time'])
            convo['last_message_time'] = dt.strftime('%H:%M, %d, %A, %B, %Y')

        conversations.append(convo)

    conn.close()

    # 8) Single return with _all_ context
    return render_template(
        'account.html',
        user=user,
        addresses=addresses,
        user_preferences=user_preferences,
        bids=bids,
        avg_rating=(avg_rating['average'] if avg_rating else None),
        received_ratings=received_ratings,
        given_ratings=given_ratings,
        pending_ratings=pending_ratings,
        pending_orders=pending_orders,
        completed_orders=completed_orders,
        listings=active_listings,
        sales=sales,
        buckets=buckets,
        cart_total=cart_total,
        grading_fee_per_unit=0.0,
        third_party_grading=False,
        grand_total=grand_total,
        conversations=conversations,
        has_unread_admin_message=has_unread_admin_message,
        current_user_id=user_id,
        grading_service_addresses={}
    )
