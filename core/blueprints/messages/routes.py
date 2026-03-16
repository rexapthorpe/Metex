"""
Messages Routes

Message routes: get sellers, buyers, messages, post messages, mark read.
"""

from flask import request, jsonify, session
from database import get_db_connection
from services.notification_types import notify_new_message

from . import messages_bp

# Import rate limiting (optional - graceful fallback if not available)
try:
    from utils.rate_limit import limit_message_send
    RATE_LIMIT_ENABLED = True
except ImportError:
    RATE_LIMIT_ENABLED = False
    def limit_message_send(f): return f


@messages_bp.route('/orders/api/<int:order_id>/rate_sellers')
def get_order_sellers_for_rating(order_id):
    """
    Return all sellers in an order with per-seller rating status for the
    current buyer.  Used by the ratings modal to support multi-seller rating.
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    order = conn.execute('SELECT buyer_id FROM orders WHERE id = ?', (order_id,)).fetchone()
    if not order or order['buyer_id'] != user_id:
        conn.close()
        return jsonify({'error': 'Order not found or access denied'}), 403

    rows = conn.execute(
        """
        SELECT DISTINCT
            l.seller_id    AS seller_id,
            u.username     AS username,
            r.rating       AS existing_rating,
            CASE WHEN r.id IS NOT NULL THEN 1 ELSE 0 END AS already_rated
        FROM order_items oi
        JOIN listings l  ON oi.listing_id = l.id
        JOIN users u     ON l.seller_id   = u.id
        LEFT JOIN ratings r ON r.order_id  = ?
                           AND r.rater_id  = ?
                           AND r.ratee_id  = l.seller_id
        WHERE oi.order_id = ?
        """,
        (order_id, user_id, order_id)
    ).fetchall()

    conn.close()
    return jsonify([
        {
            'seller_id':       r['seller_id'],
            'username':        r['username'],
            'already_rated':   bool(r['already_rated']),
            'existing_rating': r['existing_rating'],
        }
        for r in rows
    ])


@messages_bp.route('/orders/api/<int:order_id>/message_sellers')
def get_message_sellers(order_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    # SECURITY: Explicit authorization check - must be buyer to get sellers
    from utils.security import authorize_order_participant, AuthorizationError
    try:
        auth_result = authorize_order_participant(order_id)
        if auth_result.get('role') != 'buyer':
            return jsonify({'error': 'Only buyers can get seller list'}), 403
    except AuthorizationError:
        return jsonify({'error': 'Order not found or access denied'}), 403

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

    # SECURITY: Explicit authorization check - must be seller to get buyers
    from utils.security import authorize_order_participant, AuthorizationError
    try:
        auth_result = authorize_order_participant(order_id)
        if auth_result.get('role') != 'seller':
            return jsonify({'error': 'Only sellers can get buyer list'}), 403
    except AuthorizationError:
        return jsonify({'error': 'Order not found or access denied'}), 403

    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT DISTINCT
            o.buyer_id    AS participant_id,
            u.username    AS username,
            r.rating      AS existing_rating,
            CASE WHEN r.id IS NOT NULL THEN 1 ELSE 0 END AS already_rated
        FROM orders o
        JOIN users u        ON o.buyer_id   = u.id
        JOIN order_items oi ON oi.order_id  = o.id
        JOIN listings l     ON oi.listing_id = l.id
        LEFT JOIN ratings r ON r.order_id   = o.id
                           AND r.rater_id   = ?
                           AND r.ratee_id   = o.buyer_id
        WHERE o.id       = ?
          AND l.seller_id = ?
        """,
        (user_id, order_id, user_id)
    ).fetchall()

    buyers = [
        {
            'buyer_id':        r['participant_id'],
            'username':        r['username'],
            'already_rated':   bool(r['already_rated']),
            'existing_rating': r['existing_rating'],
        }
        for r in rows
    ]
    return jsonify(buyers)


@messages_bp.route('/orders/api/<int:order_id>/messages/<int:participant_id>', methods=['GET'])
def get_messages(order_id, participant_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    # SECURITY: Explicit authorization check - must be buyer or seller
    from utils.security import authorize_order_participant, AuthorizationError
    try:
        authorize_order_participant(order_id)
    except AuthorizationError:
        return jsonify({'error': 'Order not found or access denied'}), 403

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
@limit_message_send
def post_message(order_id, participant_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    # SECURITY: Explicit authorization check - must be buyer or seller
    from utils.security import authorize_order_participant, AuthorizationError
    try:
        authorize_order_participant(order_id)
    except AuthorizationError:
        return jsonify({'error': 'Order not found or access denied'}), 403

    # SECURITY: Verify participant_id is the OTHER party in this specific order
    # (prevents messaging arbitrary users by guessing IDs)
    conn2 = get_db_connection()
    counterparty_check = conn2.execute("""
        SELECT 1 FROM orders o
        LEFT JOIN order_items oi ON oi.order_id = o.id
        LEFT JOIN listings l ON oi.listing_id = l.id
        WHERE o.id = ?
          AND (
            (o.buyer_id = ? AND l.seller_id = ?)
            OR (l.seller_id = ? AND o.buyer_id = ?)
          )
        LIMIT 1
    """, (order_id, user_id, participant_id, user_id, participant_id)).fetchone()
    conn2.close()
    if not counterparty_check:
        return jsonify({'error': 'Recipient is not a party to this order'}), 403

    # Check if request has files (FormData) or JSON
    if request.is_json:
        data = request.get_json() or {}
        text = data.get('message_text', '').strip()
    else:
        # FormData with potential file uploads
        text = request.form.get('message_text', '').strip()

    # Must have either text or files
    if not text and not request.files:
        return jsonify({'error': 'Empty message'}), 400

    # Handle file uploads (if any)
    file_paths = []
    if request.files:
        import os
        from utils.upload_security import save_secure_upload

        for file_key in request.files:
            file = request.files[file_key]
            if not file or not file.filename:
                continue

            # Validate and save the upload securely (content-type + size checked)
            result = save_secure_upload(
                file,
                upload_dir='uploads/messages',
                allowed_types=['image/png', 'image/jpeg', 'image/webp', 'image/gif'],
                category='message_attachment'
            )
            if not result['success']:
                return jsonify({'error': f'File upload rejected: {result["error"]}'}), 400

            # Store the relative path (e.g. uploads/messages/abc123.jpg)
            # Prefix with /static/ for web-accessible URL construction
            file_paths.append('static/' + result['path'])

    # Reject messages that try to inject [Files: ...] through text content
    if '[Files:' in text:
        text = text.replace('[Files:', '[files:')

    # If we have files but no text, use placeholder
    if file_paths and not text:
        text = f"[{len(file_paths)} attachment(s)]"

    # Append file references to message text (web-relative paths only)
    if file_paths:
        text = text + " [Files: " + ", ".join(file_paths) + "]"

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
    conn.close()

    # Send notification to recipient (respects user's inapp_messages preference)
    try:
        # Use original text without file path info for preview
        message_preview = request.form.get('message_text', '').strip() if request.content_type and 'multipart' in request.content_type else (request.get_json() or {}).get('message_text', '').strip()
        notify_new_message(
            receiver_id=participant_id,
            sender_id=user_id,
            order_id=order_id,
            message_preview=message_preview
        )
    except Exception as e:
        print(f"[MESSAGES] Failed to send message notification: {e}")

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

    # SECURITY: Explicit authorization check - must be buyer or seller
    from utils.security import authorize_order_participant, AuthorizationError
    try:
        authorize_order_participant(order_id)
    except AuthorizationError:
        return jsonify({'error': 'Order not found or access denied'}), 403

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


@messages_bp.route('/orders/api/<int:order_id>/details', methods=['GET'])
def get_order_details(order_id):
    """
    Get basic order details for display in message modal header
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()

    # Get order info with first listing photo
    # Handle both regular listings (listing_photos) and set listings (listing_set_item_photos)
    order_data = conn.execute("""
        SELECT
            o.id,
            o.status,
            o.created_at,
            COALESCE(MIN(lp.file_path),
                     (SELECT lsip.file_path
                      FROM listing_set_items lsi
                      JOIN listing_set_item_photos lsip ON lsip.set_item_id = lsi.id
                      WHERE lsi.listing_id = l.id
                      LIMIT 1)) as photo_path,
            MIN(c.metal) as metal,
            MIN(c.product_line) as product_line,
            MIN(c.product_type) as product_type,
            MIN(c.weight) as weight,
            MIN(c.year) as year,
            MIN(l.name) as listing_name,
            MIN(c.bucket_id) as bucket_id
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        JOIN listings l ON oi.listing_id = l.id
        JOIN categories c ON l.category_id = c.id
        LEFT JOIN listing_photos lp ON lp.listing_id = l.id
        WHERE o.id = ?
          AND (o.buyer_id = ? OR l.seller_id = ?)
        GROUP BY o.id, o.status, o.created_at
    """, (order_id, user_id, user_id)).fetchone()

    if not order_data:
        return jsonify({'error': 'Order not found'}), 404

    # Convert photo path to URL
    image_url = None
    if order_data['photo_path']:
        raw_path = str(order_data['photo_path'])
        if raw_path.startswith('/'):
            image_url = raw_path
        elif raw_path.startswith('static/'):
            image_url = '/' + raw_path
        else:
            image_url = '/static/' + raw_path

    # Construct item title
    title_parts = []
    if order_data['year']:
        title_parts.append(str(order_data['year']))
    if order_data['metal']:
        title_parts.append(order_data['metal'])
    if order_data['product_line']:
        title_parts.append(order_data['product_line'])
    if order_data['weight']:
        title_parts.append(order_data['weight'])

    title = ' '.join(title_parts) if title_parts else (order_data['listing_name'] or 'Order Item')

    result = {
        'id': order_data['id'],
        'status': order_data['status'],
        'created_at': order_data['created_at'],
        'image_url': image_url,
        'title': title,
        'metal': order_data['metal'],
        'product_line': order_data['product_line'],
        'product_type': order_data['product_type'],
        'weight': order_data['weight'],
        'year': order_data['year'],
        'bucket_id': order_data['bucket_id']
    }

    return jsonify(result)


@messages_bp.route('/api/messages/admin-unread')
def check_admin_unread():
    """
    Check if the current user has any unread messages from admin users.
    Used for the global admin message banner.
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'has_unread': False})

    conn = get_db_connection()
    try:
        # Find any unread messages from admin users
        # An admin message is unread if:
        # 1. The sender is an admin (is_admin = 1)
        # 2. The receiver is the current user
        # 3. The message timestamp is after the last_read_ts (or no read record exists)
        result = conn.execute("""
            SELECT COUNT(*) as unread_count
            FROM messages m
            JOIN users sender ON m.sender_id = sender.id
            LEFT JOIN message_reads mr ON
                mr.user_id = ? AND
                mr.participant_id = m.sender_id AND
                mr.order_id = m.order_id
            WHERE m.receiver_id = ?
              AND sender.is_admin = 1
              AND (mr.last_read_ts IS NULL OR m.timestamp > mr.last_read_ts)
        """, (user_id, user_id)).fetchone()

        has_unread = result and result['unread_count'] > 0

        return jsonify({
            'has_unread': has_unread,
            'count': result['unread_count'] if result else 0
        })

    except Exception as e:
        print(f"Error checking admin unread: {e}")
        return jsonify({'has_unread': False, 'error': str(e)})
    finally:
        conn.close()


def _get_primary_admin_id(conn):
    """
    Get the primary admin user ID.
    SECURITY: Admin identity is server-controlled, never from URL parameters.
    """
    admin = conn.execute(
        "SELECT id FROM users WHERE is_admin = 1 ORDER BY id ASC LIMIT 1"
    ).fetchone()
    return admin['id'] if admin else None


@messages_bp.route('/api/admin/messages/<int:admin_id>', methods=['GET'])
@messages_bp.route('/api/admin/messages', methods=['GET'])
def get_admin_messages(admin_id=None):
    """
    Get messages between the current user and admin (order_id = 0).
    SECURITY: The admin_id URL param is IGNORED - admin identity is server-derived.
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    try:
        # SECURITY: Always use server-selected admin, ignore any URL param
        actual_admin_id = _get_primary_admin_id(conn)
        if not actual_admin_id:
            return jsonify({'error': 'No admin available'}), 404

        rows = conn.execute("""
            SELECT
                m.id,
                m.sender_id,
                m.receiver_id,
                m.content AS message_text,
                m.timestamp
            FROM messages m
            WHERE m.order_id = 0
              AND ((m.sender_id = ? AND m.receiver_id = ?)
                OR (m.sender_id = ? AND m.receiver_id = ?))
            ORDER BY m.timestamp ASC
        """, (user_id, actual_admin_id, actual_admin_id, user_id)).fetchall()

        messages = [dict(r) for r in rows]
        return jsonify(messages)

    except Exception as e:
        print(f"Error fetching admin messages: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@messages_bp.route('/api/admin/messages/<int:admin_id>', methods=['POST'])
@messages_bp.route('/api/admin/messages', methods=['POST'])
@limit_message_send
def send_admin_message_reply(admin_id=None):
    """
    Send a reply message to admin (order_id = 0).
    SECURITY: The admin_id URL param is IGNORED - admin identity is server-derived.
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.form if request.form else request.get_json() or {}
    message_text = data.get('message_text', '').strip()[:4000]

    if not message_text:
        return jsonify({'error': 'Message cannot be empty'}), 400

    conn = get_db_connection()
    try:
        # SECURITY: Always use server-selected admin, ignore any URL param
        actual_admin_id = _get_primary_admin_id(conn)
        if not actual_admin_id:
            return jsonify({'error': 'No admin available'}), 404

        # Insert the reply message with order_id = 0
        conn.execute("""
            INSERT INTO messages (order_id, sender_id, receiver_id, content)
            VALUES (0, ?, ?, ?)
        """, (user_id, actual_admin_id, message_text))
        conn.commit()

        return jsonify({'status': 'sent'})

    except Exception as e:
        print(f"Error sending admin message reply: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@messages_bp.route('/api/feedback', methods=['POST'])
@limit_message_send
def send_feedback():
    """
    Submit user feedback. Stored as a message with message_type='feedback'.
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.form if request.form else request.get_json() or {}
    message_text = data.get('message_text', '').strip()[:4000]

    if not message_text:
        return jsonify({'error': 'Message cannot be empty'}), 400

    conn = get_db_connection()
    try:
        actual_admin_id = _get_primary_admin_id(conn)
        if not actual_admin_id:
            return jsonify({'error': 'No admin available'}), 404

        conn.execute("""
            INSERT INTO messages (order_id, sender_id, receiver_id, content, message_type)
            VALUES (0, ?, ?, ?, 'feedback')
        """, (user_id, actual_admin_id, message_text))
        conn.commit()

        return jsonify({'status': 'sent'})

    except Exception as e:
        print(f"Error sending feedback: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@messages_bp.route('/api/admin/messages/<int:admin_id>/read', methods=['POST'])
@messages_bp.route('/api/admin/messages/read', methods=['POST'])
def mark_admin_message_read(admin_id=None):
    """
    Mark admin messages as read.
    SECURITY: The admin_id URL param is IGNORED - admin identity is server-derived.
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    try:
        # SECURITY: Always use server-selected admin, ignore any URL param
        actual_admin_id = _get_primary_admin_id(conn)
        if not actual_admin_id:
            return jsonify({'error': 'No admin available'}), 404

        conn.execute("""
            INSERT INTO message_reads (user_id, participant_id, order_id, last_read_ts)
            VALUES (?, ?, 0, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, participant_id, order_id) DO UPDATE SET
                last_read_ts = CURRENT_TIMESTAMP
        """, (user_id, actual_admin_id))
        conn.commit()

        return jsonify({'status': 'ok'})

    except Exception as e:
        print(f"Error marking admin message read: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@messages_bp.route('/api/admin/participant/<int:admin_id>')
@messages_bp.route('/api/admin/participant')
def get_admin_participant(admin_id=None):
    """
    Get admin participant info for the message modal.
    SECURITY: The admin_id URL param is IGNORED - admin identity is server-derived.
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    try:
        # SECURITY: Always use server-selected admin, ignore any URL param
        actual_admin_id = _get_primary_admin_id(conn)
        if not actual_admin_id:
            return jsonify({'error': 'No admin available'}), 404

        admin = conn.execute("""
            SELECT id, username, is_admin FROM users WHERE id = ?
        """, (actual_admin_id,)).fetchone()

        return jsonify([{
            'admin_id': admin['id'],
            'username': admin['username']
        }])

    except Exception as e:
        print(f"Error fetching admin participant: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@messages_bp.route('/orders/api/<int:order_id>/pricing', methods=['GET'])
def get_order_pricing(order_id):
    """
    Get order pricing information
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    # SECURITY: Explicit authorization check - must be buyer or seller
    from utils.security import authorize_order_participant, AuthorizationError
    try:
        authorize_order_participant(order_id)
    except AuthorizationError:
        return jsonify({'error': 'Order not found or access denied'}), 403

    conn = get_db_connection()

    # Get order pricing (SQL still scoped for defense in depth)
    pricing_data = conn.execute("""
        SELECT
            SUM(oi.quantity * oi.price_each) as total_price,
            SUM(oi.quantity) as total_quantity
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        JOIN listings l ON oi.listing_id = l.id
        WHERE o.id = ?
          AND (o.buyer_id = ? OR l.seller_id = ?)
    """, (order_id, user_id, user_id)).fetchone()

    if not pricing_data:
        return jsonify({'error': 'Order not found'}), 404

    result = {
        'total_price': float(pricing_data['total_price']) if pricing_data['total_price'] else 0.0,
        'total_quantity': pricing_data['total_quantity'] or 0
    }

    return jsonify(result)
