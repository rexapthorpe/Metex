
from flask import Blueprint, render_template, session, redirect, url_for, flash, request, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from database import get_db_connection
from utils.cart_utils import get_cart_data
from services.pricing_service import get_effective_price, get_effective_bid_price
from services.spot_price_service import get_current_spot_prices
from collections import defaultdict
import os



account_bp = Blueprint('account', __name__)
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
    spot_prices = get_current_spot_prices()

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
        bids.append(bid)

    # 3) Ratings
    avg_rating = conn.execute(
        "SELECT ROUND(AVG(rating),2) AS average FROM ratings WHERE ratee_id = ?",
        (user_id,)
    ).fetchone()
    received_ratings = conn.execute(
        """SELECT r.rating, r.comment, r.timestamp, u.username AS rater_name
           FROM ratings r
           JOIN users u ON r.rater_id = u.id
          WHERE r.ratee_id = ?
          ORDER BY r.timestamp DESC
        """, (user_id,)
    ).fetchall()

    # 4) Orders (pending & completed) + helper to attach sellers
    def attach_sellers(order_rows):
        out = []
        for row in order_rows:
            order = dict(row)
            seller_rows = conn.execute(
                """SELECT DISTINCT u.username
                   FROM order_items oi
                   JOIN listings l  ON oi.listing_id = l.id
                   JOIN users u     ON l.seller_id = u.id
                  WHERE oi.order_id = ?
                """, (order['id'],)
            ).fetchall()
            order['sellers'] = [r['username'] for r in seller_rows]

            # Set year to "Random" if order has items from multiple years
            if order.get('year_count', 1) > 1:
                order['year'] = 'Random'

            out.append(order)
        return out

    raw_pending = conn.execute(
        """SELECT
             o.id AS id,
             SUM(oi.quantity) AS quantity,
             SUM(oi.quantity*oi.price_each)*1.0/SUM(oi.quantity) AS price_each,
             o.status, o.created_at AS order_date,
             COALESCE(o.delivery_address, o.shipping_address) AS delivery_address,
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
             MAX(oi.third_party_grading_requested) AS third_party_grading,
             SUM(oi.grading_fee_charged) AS grading_fee_total,
             MAX(oi.grading_service) AS grading_service_requested,
             MAX(oi.grading_status) AS grading_status,
             (SELECT 1 FROM ratings r
                WHERE r.order_id = o.id
                  AND r.rater_id = ?
             ) AS already_rated,
             (SELECT COUNT(*) FROM order_items oi2
                JOIN portfolio_exclusions pe ON pe.order_item_id = oi2.order_item_id
               WHERE oi2.order_id = o.id
                 AND pe.user_id = ?
             ) AS excluded_count
           FROM orders o
           JOIN order_items oi ON oi.order_id = o.id
           JOIN listings l     ON oi.listing_id = l.id
           JOIN categories c   ON l.category_id = c.id
          WHERE o.buyer_id = ?
            AND o.status IN ('Pending','Pending Shipment','Awaiting Shipment','Awaiting Delivery')
          GROUP BY o.id, o.status, o.created_at, o.delivery_address, o.shipping_address
          ORDER BY o.created_at DESC
        """, (user_id, user_id, user_id)
    ).fetchall()
    raw_completed = conn.execute(
        """SELECT
             o.id AS id,
             SUM(oi.quantity) AS quantity,
             SUM(oi.quantity*oi.price_each)*1.0/SUM(oi.quantity) AS price_each,
             o.status, o.created_at AS order_date,
             COALESCE(o.delivery_address, o.shipping_address) AS delivery_address,
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
             MAX(oi.third_party_grading_requested) AS third_party_grading,
             SUM(oi.grading_fee_charged) AS grading_fee_total,
             MAX(oi.grading_service) AS grading_service_requested,
             MAX(oi.grading_status) AS grading_status,
             (SELECT 1 FROM ratings r
                WHERE r.order_id = o.id
                  AND r.rater_id = ?
             ) AS already_rated,
             (SELECT COUNT(*) FROM order_items oi2
                JOIN portfolio_exclusions pe ON pe.order_item_id = oi2.order_item_id
               WHERE oi2.order_id = o.id
                 AND pe.user_id = ?
             ) AS excluded_count
           FROM orders o
           JOIN order_items oi ON oi.order_id = o.id
           JOIN listings l     ON oi.listing_id = l.id
           JOIN categories c   ON l.category_id = c.id
           JOIN users u        ON l.seller_id = u.id
          WHERE o.buyer_id = ?
            AND o.status IN ('Delivered','Complete','Refunded','Cancelled')
          GROUP BY o.id, o.status, o.created_at, o.delivery_address, o.shipping_address
          ORDER BY o.created_at DESC
        """, (user_id, user_id, user_id)
    ).fetchall()

    pending_orders   = attach_sellers(raw_pending)
    completed_orders = attach_sellers(raw_completed)

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
    from datetime import datetime
    for order in pending_orders + completed_orders:
        if order.get('order_date'):
            dt = datetime.fromisoformat(order['order_date'])
            order['formatted_order_date'] = dt.strftime('%I:%M %p, %d %B %Y').lstrip('0')  # Remove leading zero from hour

    # 5) Active listings & sales
    active_listings_raw = conn.execute(
        """SELECT l.id   AS listing_id,
                l.quantity,
                l.price_per_coin,
                l.pricing_mode,
                l.spot_premium,
                l.floor_price,
                l.pricing_metal,
                lp.file_path AS photo_path,
                l.graded,
                l.grading_service,
                c.id AS category_id,
                c.bucket_id,
                c.metal, c.product_type,
                c.special_designation,
                c.weight, c.mint, c.year, c.finish, c.grade,
                c.purity, c.product_line, c.coin_series
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        LEFT JOIN listing_photos lp ON lp.listing_id = l.id
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
                  oi.third_party_grading_requested,
                  oi.grading_fee_charged,
                  oi.grading_service AS grading_service_requested,
                  oi.grading_status,
                  oi.seller_tracking_to_grader,
                  (SELECT 1 FROM ratings r
                     WHERE r.order_id = o.id
                       AND r.rater_id = ?
                  ) AS already_rated
           FROM orders o
           JOIN order_items oi ON o.id = oi.order_id
           JOIN listings l     ON oi.listing_id = l.id
           JOIN categories c   ON l.category_id = c.id
           JOIN users u        ON o.buyer_id = u.id
          WHERE l.seller_id = ?
          ORDER BY o.created_at DESC
        """, (user_id, user_id)
    ).fetchall()

    # ✅ Build shipping name from order-level recipient fields (source of truth)
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
        sales.append(sale)

    # 6) Cart
    buckets, _ = get_cart_data(conn)  # Ignore old cart_total, we'll recalculate with effective prices
    cart_total = 0  # Recalculate with effective prices
    for bucket in buckets.values():
        total_qty = sum(item['quantity'] for item in bucket['listings'])
        bucket['total_quantity'] = total_qty
        # Calculate effective price for each listing and sum
        total_cost = 0
        for item in bucket['listings']:
            effective_price = get_effective_price(item)
            item['effective_price'] = effective_price  # Store for template use
            total_cost += item['quantity'] * effective_price
        bucket['avg_price'] = (total_cost/total_qty) if total_qty else 0
        bucket['total_price'] = total_cost  # Update with effective price total
        cart_total += total_cost  # Add to overall cart total

    # 7) Conversations
    conv_rows = conn.execute(
        """
        SELECT
          m.order_id,
          o.buyer_id                    AS order_buyer_id,
          CASE WHEN m.sender_id = ? THEN m.receiver_id ELSE m.sender_id END
            AS other_user_id,
          u.username            AS other_username,
          m.content             AS last_message_content,
          m.timestamp           AS last_message_time,
          SUM(CASE WHEN m.receiver_id = ? THEN 1 ELSE 0 END)
            AS unread_count
        FROM messages m
        JOIN orders o ON o.id = m.order_id
        JOIN users u  ON u.id = other_user_id
        WHERE m.sender_id = ? OR m.receiver_id = ?
        GROUP BY m.order_id, other_user_id
        ORDER BY last_message_time DESC
        """, (user_id, user_id, user_id, user_id)
    ).fetchall()

    conversations = []
    for r in conv_rows:
        convo = {
            'order_id':             r['order_id'],
            'other_user_id':        r['other_user_id'],
            'other_username':       r['other_username'],
            'last_message_content': r['last_message_content'],
            'last_message_time':    r['last_message_time'],
            'unread_count':         r['unread_count'],
            'type': 'seller' if r['order_buyer_id'] == user_id else 'buyer',
            'messages': []
        }
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
        convo['messages'] = [
            {'sender_id': m['sender_id'],
             'content':   m['content'],
             'timestamp': m['timestamp']}
            for m in history
        ]
        conversations.append(convo)

    conn.close()

    # Import grading service addresses for Sold tab grading instructions
    from config import GRADING_SERVICE_ADDRESSES

    # 8) Single return with _all_ context
    return render_template(
        'account.html',
        user=user,
        addresses=addresses,
        user_preferences=user_preferences,
        bids=bids,
        avg_rating=(avg_rating['average'] if avg_rating else None),
        received_ratings=received_ratings,
        pending_orders=pending_orders,
        completed_orders=completed_orders,
        listings=active_listings,
        sales=sales,
        buckets=buckets,
        cart_total=cart_total,
        conversations=conversations,
        current_user_id=user_id,
        grading_service_addresses=GRADING_SERVICE_ADDRESSES
    )


@account_bp.route('/my_orders')
def my_orders():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    conn = get_db_connection()

    pending_orders = conn.execute(''' ... ''', (session['user_id'], session['user_id'])).fetchall()
    completed_orders = conn.execute(''' ... ''', (session['user_id'], session['user_id'])).fetchall()

    # NEW: attach seller lists to each order
    def fetch_sellers_for_orders(conn, orders):
        for order in orders:
            sellers = conn.execute('''
                SELECT DISTINCT users.username
                FROM order_items
                JOIN listings ON order_items.listing_id = listings.id
                JOIN users ON listings.seller_id = users.id
                WHERE order_items.order_id = ?
            ''', (order['id'],)).fetchall()
            order['sellers'] = sellers

    fetch_sellers_for_orders(conn, pending_orders)
    fetch_sellers_for_orders(conn, completed_orders)

    conn.close()

    return render_template(
        'my_orders.html',
        pending_orders=pending_orders,
        completed_orders=completed_orders
    )


@account_bp.route('/order/<int:order_id>')
def view_order_details(order_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    conn = get_db_connection()

    order = conn.execute('''
        SELECT orders.id, orders.total_price, orders.status, orders.shipping_address, orders.created_at
        FROM orders
        WHERE orders.id = ? AND orders.buyer_id = ?
    ''', (order_id, session['user_id'])).fetchone()

    if not order:
        conn.close()
        flash('Order not found.')
        return redirect(url_for('account.my_orders'))

    order_items = conn.execute('''
        SELECT categories.metal, categories.product_type, order_items.quantity, order_items.price_each
        FROM order_items
        JOIN listings ON order_items.listing_id = listings.id
        JOIN categories ON listings.category_id = categories.id
        WHERE order_items.order_id = ?
    ''', (order_id,)).fetchall()

    tracking = conn.execute('''
        SELECT carrier, tracking_number, tracking_status
        FROM tracking
        WHERE order_id = ?
    ''', (order_id,)).fetchone()

    conn.close()

    return render_template('order_details.html', order=order, order_items=order_items, tracking=tracking)


@account_bp.route('/sold_orders')
def sold_orders():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    conn = get_db_connection()

    orders = conn.execute('''
        SELECT orders.id,
               orders.buyer_id,
               orders.quantity,
               orders.price_each,
               orders.status,
               orders.created_at,
               categories.metal,
               categories.product_type
        FROM orders
        JOIN categories ON orders.category_id = categories.id
        WHERE orders.seller_id = ?
        ORDER BY orders.created_at DESC
    ''', (session['user_id'],)).fetchall()

    conn.close()
    return render_template('sold_orders.html', orders=orders)


@account_bp.route('/messages')
def my_messages():
    print("⚡ /messages route hit!")

    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    conn = get_db_connection()

    # First, get list of distinct conversations with latest message details
    base_conversations = conn.execute('''
        SELECT
            users.id AS other_user_id,
            users.username AS other_username,
            messages.content AS latest_message,
            messages.timestamp AS latest_timestamp
        FROM messages
        JOIN (
            SELECT
                CASE
                    WHEN sender_id = ? THEN receiver_id
                    ELSE sender_id
                END AS other_id,
                MAX(timestamp) AS max_time
            FROM messages
            WHERE sender_id = ? OR receiver_id = ?
            GROUP BY other_id
        ) AS latest_convos
        ON (
            (messages.sender_id = ? AND messages.receiver_id = latest_convos.other_id)
            OR (messages.sender_id = latest_convos.other_id AND messages.receiver_id = ?)
        )
        AND messages.timestamp = latest_convos.max_time
        JOIN users ON users.id = latest_convos.other_id
        ORDER BY messages.timestamp DESC;
    ''', (user_id, user_id, user_id, user_id, user_id)).fetchall()

    conversations = []

    for convo in base_conversations:
        other_user_id = convo['other_user_id']
        convo_data = {
            'other_user_id': other_user_id,
            'other_username': convo['other_username'],
            'last_message_content': convo['latest_message'],
            'last_message_time': convo['latest_timestamp'],
            'messages': []
        }

        # Now get all messages for this conversation
        convo_data['messages'] = conn.execute('''
            SELECT sender_id, receiver_id, content, timestamp
            FROM messages
            WHERE (sender_id = ? AND receiver_id = ?)
               OR (sender_id = ? AND receiver_id = ?)
            ORDER BY timestamp ASC
        ''', (user_id, other_user_id, other_user_id, user_id)).fetchall()

        conversations.append(convo_data)

    conn.close()
    print("Loaded messages route. Conversations found:", len(conversations))

    return render_template('partials/my_messages.html', conversations=conversations, current_user_id=user_id)

@account_bp.route('/orders/api/<int:order_id>/order_sellers')
def order_sellers(order_id):
    if 'user_id' not in session:
        return jsonify(error="Authentication required"), 401

    conn = get_db_connection()
    rows = conn.execute("""
        SELECT
          u.id                     AS seller_id,
          u.username               AS username,
          COALESCE((SELECT AVG(r.rating)
                    FROM ratings r
                    WHERE r.ratee_id = u.id), 0) AS rating,
          COALESCE((SELECT COUNT(r.id)
                    FROM ratings r
                    WHERE r.ratee_id = u.id), 0) AS num_reviews,
          SUM(oi.quantity)         AS total_quantity
        FROM order_items oi
        JOIN listings l      ON oi.listing_id = l.id
        JOIN users u         ON l.seller_id = u.id
        WHERE oi.order_id = ?
        GROUP BY u.id, u.username
        ORDER BY u.username
    """, (order_id,)).fetchall()
    conn.close()

    sellers = [{
        'seller_id':   row['seller_id'],
        'username':    row['username'],
        'rating':      row['rating'],
        'num_reviews': row['num_reviews'],
        'quantity':    row['total_quantity']
    } for row in rows]

    return jsonify(sellers)


@account_bp.route('/orders/api/<int:order_id>/order_items')
def order_items(order_id):
    if 'user_id' not in session:
        return jsonify(error="Authentication required"), 401

    conn = get_db_connection()
    cur = conn.cursor()

    # 1) Pull all item-level data, including listing_photos and seller
    raw_rows = cur.execute(
        """
        SELECT
          oi.order_item_id AS item_id,
          oi.order_id,
          oi.listing_id,
          oi.quantity,
          oi.price_each,

          c.mint,
          c.metal,
          c.weight,
          c.year,
          c.product_line,
          c.product_type,
          c.purity,
          c.finish,
          c.grade,

          l.graded,
          l.grading_service,
          u.username AS seller_username,

          lp.file_path
        FROM order_items AS oi
        JOIN listings      AS l   ON oi.listing_id = l.id
        JOIN categories    AS c   ON l.category_id = c.id
        JOIN users         AS u   ON l.seller_id = u.id
        LEFT JOIN listing_photos AS lp
               ON lp.listing_id = l.id
        WHERE oi.order_id = ?
        ORDER BY oi.price_each DESC, oi.order_item_id
        """,
        (order_id,)
    ).fetchall()

    conn.close()

    # 2) Normalize rows and build a clean image_url
    normalized = []
    for r in raw_rows:
        rd = dict(r)
        raw_path = rd.get('file_path')

        image_url = None
        if raw_path:
            # handle several possible storage formats without guessing later
            raw_path = str(raw_path)
            if raw_path.startswith('/'):
                # already an absolute path (e.g. "/static/uploads/listings/foo.jpg")
                image_url = raw_path
            elif raw_path.startswith('static/'):
                # stored as "static/uploads/listings/foo.jpg"
                image_url = '/' + raw_path
            else:
                # stored relative to static, e.g. "uploads/listings/foo.jpg"
                image_url = url_for('static', filename=raw_path)

        rd['image_url'] = image_url
        normalized.append(rd)

    # 3) Group by price_each (like your original logic),
    #    but now carry through the rich metadata.
    from collections import defaultdict
    groups = defaultdict(list)
    for rd in normalized:
        groups[rd['price_each']].append(rd)

    result = []
    for price, items in sorted(groups.items(), key=lambda kv: kv[0], reverse=True):
        # Take metadata from the first item in this price group
        first = items[0]

        # Compute grading service label
        if first.get('graded'):
            grading_service = first.get('grading_service') or "Unknown Grading Service"
        else:
            grading_service = "No 3rd Party Grading Verification"

        total_qty = sum(i['quantity'] for i in items)

        result.append({
            "price_each"     : float(price),
            "total_quantity" : int(total_qty),

            # descriptive fields (what your modal shows)
            "mint"           : first.get("mint"),
            "metal"          : first.get("metal"),
            "weight"         : first.get("weight"),
            "year"           : first.get("year"),
            "product_line"   : first.get("product_line"),
            "product_type"   : first.get("product_type"),
            "purity"         : first.get("purity"),
            "finish"         : first.get("finish"),
            "grade"          : first.get("grade"),
            "grading_service": grading_service,
            "seller_username": first.get("seller_username"),

            # image for the group
            "image_url"      : first.get("image_url"),

            # raw items if you ever want them
            "items"          : [
                {
                    "item_id"   : i["item_id"],
                    "listing_id": i["listing_id"],
                    "quantity"  : i["quantity"],
                }
                for i in items
            ]
        })

    return jsonify(result)


# Account Details endpoints

@account_bp.route('/account/update_personal_info', methods=['POST'])
def update_personal_info():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        conn.execute('''
            UPDATE users
            SET first_name = ?, last_name = ?, phone = ?, email = ?
            WHERE id = ?
        ''', (
            request.form.get('first_name', ''),
            request.form.get('last_name', ''),
            request.form.get('phone', ''),
            request.form.get('email'),
            user_id
        ))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@account_bp.route('/account/change_password', methods=['POST'])
def change_password():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_id = session['user_id']
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')

    conn = get_db_connection()

    # Verify current password
    user = conn.execute('SELECT password_hash FROM users WHERE id = ?', (user_id,)).fetchone()

    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'}), 404

    # Use the same password verification as login
    if not check_password_hash(user['password_hash'], current_password):
        conn.close()
        return jsonify({'success': False, 'message': 'Current password is incorrect'}), 400

    try:
        # Hash the new password before storing
        new_password_hash = generate_password_hash(new_password)
        conn.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_password_hash, user_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@account_bp.route('/account/update_notifications', methods=['POST'])
def update_notifications():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        # Create or update notification preferences
        # You may need to create a notifications table first
        conn.execute('''
            INSERT OR REPLACE INTO notification_preferences
            (user_id, email_orders, email_bids, email_messages, email_promotions)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            user_id,
            1 if request.form.get('email_orders') else 0,
            1 if request.form.get('email_bids') else 0,
            1 if request.form.get('email_messages') else 0,
            1 if request.form.get('email_promotions') else 0
        ))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@account_bp.route('/account/update_profile', methods=['POST'])
def update_profile():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        conn.execute('''
            UPDATE users
            SET bio = ?
            WHERE id = ?
        ''', (
            request.form.get('bio', ''),
            user_id
        ))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@account_bp.route('/account/delete_address/<int:address_id>', methods=['POST'])
def delete_address(address_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        # Verify address belongs to user
        address = conn.execute(
            'SELECT * FROM addresses WHERE id = ? AND user_id = ?',
            (address_id, user_id)
        ).fetchone()

        if not address:
            conn.close()
            return jsonify({'success': False, 'message': 'Address not found'}), 404

        conn.execute('DELETE FROM addresses WHERE id = ?', (address_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@account_bp.route('/account/add_address', methods=['POST'])
def add_address():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        conn.execute('''
            INSERT INTO addresses (user_id, name, street, street_line2, city, state, zip_code, country)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            request.form.get('name'),
            request.form.get('street'),
            request.form.get('street_line2', ''),
            request.form.get('city'),
            request.form.get('state'),
            request.form.get('zip_code'),
            request.form.get('country', 'USA')
        ))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@account_bp.route('/account/edit_address/<int:address_id>', methods=['POST'])
def edit_address(address_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        # Verify address belongs to user
        address = conn.execute(
            'SELECT * FROM addresses WHERE id = ? AND user_id = ?',
            (address_id, user_id)
        ).fetchone()

        if not address:
            conn.close()
            return jsonify({'success': False, 'message': 'Address not found'}), 404

        conn.execute('''
            UPDATE addresses
            SET name = ?, street = ?, street_line2 = ?, city = ?, state = ?, zip_code = ?, country = ?
            WHERE id = ?
        ''', (
            request.form.get('name'),
            request.form.get('street'),
            request.form.get('street_line2', ''),
            request.form.get('city'),
            request.form.get('state'),
            request.form.get('zip_code'),
            request.form.get('country', 'USA'),
            address_id
        ))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@account_bp.route('/account/get_addresses', methods=['GET'])
def get_addresses():
    """Fetch all addresses for the current user (for dropdowns)"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        # Fetch user info for auto-populating recipient name fields
        user_info = conn.execute(
            'SELECT first_name, last_name FROM users WHERE id = ?',
            (user_id,)
        ).fetchone()

        addresses = conn.execute(
            'SELECT * FROM addresses WHERE user_id = ? ORDER BY id',
            (user_id,)
        ).fetchall()
        conn.close()

        # Convert to list of dicts
        addresses_list = []
        for addr in addresses:
            addresses_list.append({
                'id': addr['id'],
                'name': addr['name'],
                'street': addr['street'],
                'street_line2': addr['street_line2'] if 'street_line2' in addr.keys() else '',
                'city': addr['city'],
                'state': addr['state'],
                'zip_code': addr['zip_code'],
                'country': addr['country']
            })

        return jsonify({
            'success': True,
            'addresses': addresses_list,
            'user_info': {
                'first_name': user_info['first_name'] if user_info else '',
                'last_name': user_info['last_name'] if user_info else ''
            }
        })
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@account_bp.route('/account/get_address/<int:address_id>', methods=['GET'])
def get_address(address_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        address = conn.execute(
            'SELECT * FROM addresses WHERE id = ? AND user_id = ?',
            (address_id, user_id)
        ).fetchone()
        conn.close()

        if not address:
            return jsonify({'success': False, 'message': 'Address not found'}), 404

        return jsonify({
            'success': True,
            'address': {
                'id': address['id'],
                'name': address['name'],
                'street': address['street'],
                'street_line2': address['street_line2'] if 'street_line2' in address.keys() else '',
                'city': address['city'],
                'state': address['state'],
                'zip_code': address['zip_code'],
                'country': address['country']
            }
        })
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@account_bp.route('/account/get_preferences', methods=['GET'])
def get_preferences():
    """Get user notification preferences"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        prefs = conn.execute(
            'SELECT * FROM user_preferences WHERE user_id = ?',
            (user_id,)
        ).fetchone()
        conn.close()

        if not prefs:
            # Return default preferences if not set
            return jsonify({
                'success': True,
                'preferences': {
                    'email_listing_sold': 1,
                    'email_bid_filled': 1,
                    'inapp_listing_sold': 1,
                    'inapp_bid_filled': 1
                }
            })

        return jsonify({
            'success': True,
            'preferences': {
                'email_listing_sold': prefs['email_listing_sold'],
                'email_bid_filled': prefs['email_bid_filled'],
                'inapp_listing_sold': prefs['inapp_listing_sold'],
                'inapp_bid_filled': prefs['inapp_bid_filled']
            }
        })
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@account_bp.route('/account/update_preferences', methods=['POST'])
def update_preferences():
    """Update user notification preferences"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_id = session['user_id']
    data = request.get_json()

    if not data:
        return jsonify({'success': False, 'message': 'No data provided'}), 400

    conn = get_db_connection()

    try:
        # Extract preferences from request
        email_listing_sold = 1 if data.get('email_listing_sold') else 0
        email_bid_filled = 1 if data.get('email_bid_filled') else 0
        inapp_listing_sold = 1 if data.get('inapp_listing_sold') else 0
        inapp_bid_filled = 1 if data.get('inapp_bid_filled') else 0

        # Use INSERT OR REPLACE to handle both insert and update
        conn.execute('''
            INSERT OR REPLACE INTO user_preferences
            (user_id, email_listing_sold, email_bid_filled, inapp_listing_sold, inapp_bid_filled, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, email_listing_sold, email_bid_filled, inapp_listing_sold, inapp_bid_filled))

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Preferences updated successfully'
        })
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


# API: Get saved addresses
@account_bp.route('/account/api/addresses', methods=['GET'])
def get_saved_addresses():
    """Get all saved addresses for the current user"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        addresses = conn.execute(
            "SELECT * FROM addresses WHERE user_id = ? ORDER BY id",
            (user_id,)
        ).fetchall()

        addresses_list = [dict(row) for row in addresses]
        conn.close()

        return jsonify({
            'success': True,
            'addresses': addresses_list
        })
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


# API: Include order in portfolio
@account_bp.route('/account/api/orders/<int:order_id>/portfolio/include', methods=['POST'])
def include_order_in_portfolio(order_id):
    """Remove all portfolio exclusions for order items in this order"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        # Verify order belongs to user
        order = conn.execute(
            "SELECT id FROM orders WHERE id = ? AND buyer_id = ?",
            (order_id, user_id)
        ).fetchone()

        if not order:
            conn.close()
            return jsonify({'success': False, 'error': 'Order not found'}), 404

        # Get all order_items for this order
        order_items = conn.execute(
            "SELECT order_item_id FROM order_items WHERE order_id = ?",
            (order_id,)
        ).fetchall()

        # Remove portfolio exclusions for all order items
        for item in order_items:
            conn.execute(
                "DELETE FROM portfolio_exclusions WHERE user_id = ? AND order_item_id = ?",
                (user_id, item['order_item_id'])
            )

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Order included in portfolio'
        })
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


# API: Update order delivery address
# REMOVED: Delivery address update route
# The delivery address feature has been removed from the Orders tab
"""
@account_bp.route('/account/api/orders/<int:order_id>/delivery-address', methods=['PUT'])
def update_order_delivery_address(order_id):
    # Update the delivery address for an order
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        # Verify order belongs to user
        order = conn.execute(
            "SELECT id FROM orders WHERE id = ? AND buyer_id = ?",
            (order_id, user_id)
        ).fetchone()

        if not order:
            conn.close()
            return jsonify({'success': False, 'error': 'Order not found'}), 404

        # Get address_id from request
        data = request.get_json()
        address_id = data.get('address_id')

        if not address_id:
            conn.close()
            return jsonify({'success': False, 'error': 'Address ID required'}), 400

        # Get address details
        address = conn.execute(
            "SELECT * FROM addresses WHERE id = ? AND user_id = ?",
            (address_id, user_id)
        ).fetchone()

        if not address:
            conn.close()
            return jsonify({'success': False, 'error': 'Address not found'}), 404

        # Format address as JSON string for storage
        import json
        address_data = {
            'name': address['name'],
            'street': address['street'],
            'street_line2': address['street_line2'] if address['street_line2'] else '',
            'city': address['city'],
            'state': address['state'],
            'zip_code': address['zip_code'],
            'country': address['country'] if address['country'] else 'USA'
        }

        # Update order delivery_address
        conn.execute(
            "UPDATE orders SET delivery_address = ? WHERE id = ?",
            (json.dumps(address_data), order_id)
        )

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Delivery address updated successfully',
            'updated_address': address_data
        })
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500
"""
