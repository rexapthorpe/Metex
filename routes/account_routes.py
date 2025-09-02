
from flask import Blueprint, render_template, session, redirect, url_for, flash, request, jsonify
from database import get_db_connection
from utils.cart_utils import get_cart_data
from collections import defaultdict
import os

account_bp = Blueprint('account', __name__)
@account_bp.route('/account')
def account():
    # 1) Authentication guard
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    user_id = session['user_id']

    conn = get_db_connection()

    # 2) Bids
    bids = conn.execute(
        """SELECT 
             b.*,
             (SELECT MIN(l.price_per_coin)
                FROM listings AS l
               WHERE l.category_id = b.category_id
                 AND l.active = 1
                 AND l.quantity > 0
             ) AS current_price
           FROM bids AS b
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
             (SELECT 1 FROM ratings r
                WHERE r.order_id = o.id
                  AND r.rater_id = ?
             ) AS already_rated
           FROM orders o
           JOIN order_items oi ON oi.order_id = o.id
           JOIN listings l     ON oi.listing_id = l.id
           JOIN categories c   ON l.category_id = c.id
          WHERE o.buyer_id = ?
            AND o.status IN ('Pending','Awaiting Shipment','Awaiting Delivery')
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
    active_listings = conn.execute(
        """SELECT l.id   AS listing_id,
                  l.quantity,
                  l.price_per_coin,
                  c.bucket_id, c.metal, c.product_type,
                  c.special_designation,
                  c.weight, c.mint, c.year, c.finish, c.grade
           FROM listings l
           JOIN categories c ON l.category_id = c.id
          WHERE l.seller_id = ?
        """, (user_id,)
    ).fetchall()

    sales = conn.execute(
        """SELECT o.id AS order_id,
                  c.metal, c.product_type,
                  oi.quantity, oi.price_each,
                  u.username AS buyer_username,
                  o.shipping_address AS delivery_address,
                  o.status,
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
    # compute avg_price & total_quantity per bucket...
    for bucket in buckets.values():
        total_qty = sum(item['quantity'] for item in bucket['listings'])
        bucket['total_quantity'] = total_qty
        total_cost = sum(item['quantity']*item['price_per_coin']
                         for item in bucket['listings'])
        bucket['avg_price'] = (total_cost/total_qty) if total_qty else 0

    # 7) Conversations (persistent, full history)
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
        # decide which endpoint to call
        typ = 'seller' if r['order_buyer_id'] == user_id else 'buyer'

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
          COALESCE(AVG(r.rating), 0) AS rating,
          COUNT(r.id)              AS num_reviews,
          SUM(oi.quantity)         AS total_quantity
        FROM order_items oi
        JOIN listings l      ON oi.listing_id = l.id
        JOIN users u         ON l.seller_id = u.id
        LEFT JOIN ratings r  ON r.ratee_id = u.id
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
    rows = conn.execute(
        """
        SELECT
          oi.order_item_id AS item_id,
          c.mint,
          c.metal,
          c.weight,
          c.year,
          oi.quantity,
          oi.price_each
        FROM order_items oi
        JOIN listings l ON oi.listing_id = l.id
        JOIN categories c ON l.category_id = c.id
        WHERE oi.order_id = ?
        ORDER BY oi.price_each DESC, oi.order_item_id
        """,
        (order_id,)
    ).fetchall()
    conn.close()

    # group rows by price_each
    groups = defaultdict(list)
    for r in rows:
        groups[r['price_each']].append({
            'item_id':  r['item_id'],
            'mint':     r['mint'],
            'metal':    r['metal'],
            'weight':   r['weight'],
            'year':     r['year'],
            'quantity': r['quantity']
        })

    # build JSON payload: one entry per distinct price
    result = []
    for price in sorted(groups.keys(), reverse=True):
        items = groups[price]
        result.append({
            'price_each':     price,
            'total_quantity': sum(i['quantity'] for i in items),
            'mint':           items[0]['mint'],
            'metal':          items[0]['metal'],
            'weight':         items[0]['weight'],
            'year':           items[0]['year'],
            'items':          items
        })

    return jsonify(result)

