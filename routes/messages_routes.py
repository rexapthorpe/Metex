# routes/messages_routes.py
from flask import Blueprint, request, jsonify, session
from database import get_db_connection

messages_bp = Blueprint('messages', __name__)

@messages_bp.route('/orders/api/<int:order_id>/message_sellers')
def get_message_sellers(order_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT DISTINCT
            l.seller_id    AS participant_id,
            u.username     AS username
        FROM order_items oi
        JOIN orders o     ON oi.order_id   = o.id
        JOIN listings l   ON oi.listing_id = l.id
        JOIN users u      ON l.seller_id   = u.id
        WHERE o.id        = ?
          AND o.buyer_id  = ?
        """,
        (order_id, user_id)
    ).fetchall()

    sellers = [
        {'seller_id': r['participant_id'], 'username': r['username']}
        for r in rows
    ]
    return jsonify(sellers)


@messages_bp.route('/orders/api/<int:order_id>/message_buyers')
def get_message_buyers(order_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT
            o.buyer_id    AS participant_id,
            u.username    AS username
        FROM orders o
        JOIN users u     ON o.buyer_id = u.id
        JOIN order_items oi ON oi.order_id = o.id
        JOIN listings l  ON oi.listing_id = l.id
        WHERE o.id       = ?
          AND l.seller_id = ?
        """,
        (order_id, user_id)
    ).fetchall()

    buyers = [
        {'buyer_id': r['participant_id'], 'username': r['username']}
        for r in rows
    ]
    return jsonify(buyers)


@messages_bp.route('/orders/api/<int:order_id>/messages/<int:participant_id>', methods=['GET'])
def get_messages(order_id, participant_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT
            m.id,
            m.sender_id,
            m.receiver_id,
            m.content      AS message_text,
            m.timestamp,
            u.username     AS sender_username
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE m.order_id = ?
          AND ((m.sender_id = ? AND m.receiver_id = ?)
            OR (m.sender_id = ? AND m.receiver_id = ?))
        ORDER BY m.timestamp ASC
        """,
        (order_id,
         user_id, participant_id,
         participant_id, user_id)
    ).fetchall()

    msgs = [
        {
            'id': r['id'],
            'sender_id': r['sender_id'],
            'sender_username': r['sender_username'],
            'message_text': r['message_text'],
            'timestamp': r['timestamp']
        }
        for r in rows
    ]
    return jsonify(msgs)


@messages_bp.route('/orders/api/<int:order_id>/messages/<int:participant_id>', methods=['POST'])
def post_message(order_id, participant_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    text = data.get('message_text', '').strip()
    if not text:
        return jsonify({'error': 'Empty message'}), 400

    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO messages
            (order_id, sender_id, receiver_id, content)
        VALUES (?, ?, ?, ?)
        """,
        (order_id, user_id, participant_id, text)
    )
    conn.commit()
    return jsonify({'status': 'sent'})


@messages_bp.route('/orders/api/<int:order_id>/messages/<int:participant_id>/read', methods=['POST'])
def mark_messages_read(order_id, participant_id):
    """
    Mark a thread as read for the current user. We store a single 'last_read_ts'
    per (order_id, current_user_id, participant_id) so the UI can remain accurate
    across reloads/devices. This creates the table on first use.
    """
    user_id = session.get('user_id')
    if not user_id:
      return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    # Create a tiny state table if it doesn't exist yet
    conn.execute("""
      CREATE TABLE IF NOT EXISTS message_reads (
        user_id        INTEGER NOT NULL,
        participant_id INTEGER NOT NULL,
        order_id       INTEGER NOT NULL,
        last_read_ts   DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, participant_id, order_id)
      )
    """)
    # Upsert the last_read_ts
    conn.execute("""
      INSERT INTO message_reads (user_id, participant_id, order_id, last_read_ts)
      VALUES (?, ?, ?, CURRENT_TIMESTAMP)
      ON CONFLICT(user_id, participant_id, order_id)
      DO UPDATE SET last_read_ts = CURRENT_TIMESTAMP
    """, (user_id, participant_id, order_id))
    conn.commit()
    return jsonify({'status': 'ok'})
