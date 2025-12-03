
from flask import Blueprint, render_template, session, redirect, url_for, flash, request, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from database import get_db_connection
from utils.cart_utils import get_cart_data
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

    # 2) Bids (with category details)
    bids = conn.execute(
        """SELECT
             b.*,
             c.bucket_id, c.weight, c.metal, c.product_type, c.mint, c.year, c.finish,
             c.grade, c.coin_series, c.purity, c.product_line,
             (SELECT MIN(l.price_per_coin)
                FROM listings AS l
               WHERE l.category_id = b.category_id
                 AND l.active = 1
                 AND l.quantity > 0
             ) AS current_price
           FROM bids AS b
           LEFT JOIN categories AS c ON b.category_id = c.id
          WHERE b.buyer_id = ?
          ORDER BY b.created_at DESC
        """, (user_id,)
    ).fetchall()

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
            out.append(order)
        return out

    raw_pending = conn.execute(
        """SELECT
             o.id AS id,
             SUM(oi.quantity) AS quantity,
             SUM(oi.quantity*oi.price_each)*1.0/SUM(oi.quantity) AS price_each,
             o.status, o.created_at AS order_date,
             MIN(c.metal)       AS metal,
             MIN(c.product_type)AS product_type,
             MIN(c.weight)      AS weight,
             MIN(c.purity)      AS purity,
             MIN(c.mint)        AS mint,
             MIN(c.year)        AS year,
             MIN(c.finish)      AS finish,
             MIN(c.grade)       AS grade,
             MIN(c.product_line)AS product_line,
             (SELECT 1 FROM ratings r
                WHERE r.order_id = o.id
                  AND r.rater_id = ?
             ) AS already_rated
           FROM orders o
           JOIN order_items oi ON oi.order_id = o.id
           JOIN listings l     ON oi.listing_id = l.id
           JOIN categories c   ON l.category_id = c.id
          WHERE o.buyer_id = ?
            AND o.status IN ('Pending','Pending Shipment','Awaiting Shipment','Awaiting Delivery')
          GROUP BY o.id, o.status, o.created_at
          ORDER BY o.created_at DESC
        """, (user_id, user_id)
    ).fetchall()
    raw_completed = conn.execute(
        """SELECT
             o.id AS id,
             SUM(oi.quantity) AS quantity,
             SUM(oi.quantity*oi.price_each)*1.0/SUM(oi.quantity) AS price_each,
             o.status, o.created_at AS order_date,
             MIN(c.metal)       AS metal,
             MIN(c.product_type)AS product_type,
             MIN(c.weight)      AS weight,
             MIN(c.purity)      AS purity,
             MIN(c.mint)        AS mint,
             MIN(c.year)        AS year,
             MIN(c.finish)      AS finish,
             MIN(c.grade)       AS grade,
             MIN(c.product_line)AS product_line,
             MIN(u.username)    AS seller_username,
             (SELECT 1 FROM ratings r
                WHERE r.order_id = o.id
                  AND r.rater_id = ?
             ) AS already_rated
           FROM orders o
           JOIN order_items oi ON oi.order_id = o.id
           JOIN listings l     ON oi.listing_id = l.id
           JOIN categories c   ON l.category_id = c.id
           JOIN users u        ON l.seller_id = u.id
          WHERE o.buyer_id = ?
            AND o.status IN ('Delivered','Complete','Refunded','Cancelled')
          GROUP BY o.id, o.status, o.created_at
          ORDER BY o.created_at DESC
        """, (user_id, user_id)
    ).fetchall()

    pending_orders   = attach_sellers(raw_pending)
    completed_orders = attach_sellers(raw_completed)

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
    from services.pricing_service import get_effective_price
    from services.spot_price_service import get_current_spot_prices

    spot_prices = get_current_spot_prices()
    active_listings = []
    for listing in active_listings_raw:
        listing_dict = dict(listing)
        # Calculate effective price if variable pricing
        if listing_dict.get('pricing_mode') == 'premium_to_spot':
            listing_dict['effective_price'] = get_effective_price(listing_dict, spot_prices)
        else:
            listing_dict['effective_price'] = listing_dict.get('price_per_coin', 0)
        active_listings.append(listing_dict)

    sales = conn.execute(
        """SELECT o.id AS order_id,
                  c.metal, c.product_type, c.weight, c.mint, c.year,
                  c.finish, c.grade, c.purity, c.product_line, c.coin_series,
                  c.special_designation,
                  oi.quantity,
                  l.price_per_coin AS price_each,
                  l.graded,
                  l.grading_service,
                  u.username AS buyer_username,
                  u.first_name AS buyer_first_name,
                  u.last_name AS buyer_last_name,
                  o.shipping_address AS shipping_address,
                  o.shipping_address AS delivery_address,
                  o.status,
                  o.created_at AS order_date,
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

    # 6) Cart
    buckets, cart_total = get_cart_data(conn)
    for bucket in buckets.values():
        total_qty = sum(item['quantity'] for item in bucket['listings'])
        bucket['total_quantity'] = total_qty
        total_cost = sum(item['quantity']*item['price_per_coin']
                         for item in bucket['listings'])
        bucket['avg_price'] = (total_cost/total_qty) if total_qty else 0

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
        current_user_id=user_id
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
