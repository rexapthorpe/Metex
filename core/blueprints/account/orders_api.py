"""
Orders API Routes

API routes for order details, sellers, and items.

SECURITY: All routes verify user is participant (buyer or seller) in the order
to prevent IDOR attacks.
"""

from flask import session, jsonify, url_for
from database import get_db_connection
from collections import defaultdict
from datetime import datetime

from . import account_bp

# Import authorization helpers
from utils.security import (
    authorize_order_participant,
    AuthorizationError,
    handle_authorization_errors
)

# Import audit logging (optional)
try:
    from services.audit_service import log_unauthorized_access
    AUDIT_ENABLED = True
except ImportError:
    AUDIT_ENABLED = False


def _verify_order_access(order_id: int, user_id: int) -> dict:
    """
    Verify user has access to an order (is buyer or seller).

    Args:
        order_id: The order to check
        user_id: The user requesting access

    Returns:
        Order dict with role if authorized

    Raises:
        Returns None if not authorized (for API error handling)
    """
    conn = get_db_connection()

    # Get distinct sellers from order items
    order = conn.execute("""
        SELECT DISTINCT
            o.id AS order_id,
            o.buyer_id,
            l.seller_id
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        JOIN listings l ON oi.listing_id = l.id
        WHERE o.id = ?
          AND (o.buyer_id = ? OR l.seller_id = ?)
        LIMIT 1
    """, (order_id, user_id, user_id)).fetchone()
    conn.close()

    return order


@account_bp.route('/orders/api/<int:order_id>/details')
def order_details(order_id):
    """
    Get full order details including product info, price, and date.

    SECURITY: Only buyer or seller can access order details.
    """
    if 'user_id' not in session:
        return jsonify(error="Authentication required"), 401

    user_id = session['user_id']

    # SECURITY: Verify user is participant in this order
    access_check = _verify_order_access(order_id, user_id)
    if not access_check:
        # Log the unauthorized access attempt
        if AUDIT_ENABLED:
            log_unauthorized_access('order', order_id, 'view_details')
        return jsonify(error="You do not have access to this order"), 403

    conn = get_db_connection()

    # Get order and product details
    order = conn.execute("""
        SELECT
            o.id AS order_id,
            o.buyer_id,
            o.created_at,
            o.total_price,
            SUM(oi.quantity * oi.price_each) AS order_total,
            GROUP_CONCAT(c.metal || ' ' || c.product_line || ' ' || c.weight, ', ') AS product_name,
            MIN(lp.file_path) AS product_image,
            u.id AS seller_id,
            u.username AS seller_username
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        JOIN listings l ON oi.listing_id = l.id
        JOIN categories c ON l.category_id = c.id
        JOIN users u ON l.seller_id = u.id
        LEFT JOIN listing_photos lp ON lp.listing_id = l.id
        WHERE o.id = ?
        GROUP BY o.id
    """, (order_id,)).fetchone()

    conn.close()

    if not order:
        return jsonify(error="Order not found"), 404

    return jsonify({
        'order_id': order['order_id'],
        'buyer_id': order['buyer_id'],
        'seller_id': order['seller_id'],
        'seller_username': order['seller_username'],
        'product_name': order['product_name'],
        'product_image': order['product_image'],
        'total_price': float(order['order_total']) if order['order_total'] else 0.0,
        'created_at': order['created_at']
    })


@account_bp.route('/orders/api/<int:order_id>/order_sellers')
def order_sellers(order_id):
    if 'user_id' not in session:
        return jsonify(error="Authentication required"), 401

    user_id = session['user_id']

    # SECURITY: Verify user is participant in this order
    access_check = _verify_order_access(order_id, user_id)
    if not access_check:
        if AUDIT_ENABLED:
            log_unauthorized_access('order', order_id, 'view_sellers')
        return jsonify(error="You do not have access to this order"), 403

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
          SUM(oi.quantity)         AS total_quantity,
          AVG(oi.price_each)       AS avg_price,
          SUM(oi.quantity * oi.price_each) AS total_price
        FROM order_items oi
        JOIN listings l      ON oi.listing_id = l.id
        JOIN users u         ON l.seller_id = u.id
        WHERE oi.order_id = ?
        GROUP BY u.id, u.username
        ORDER BY u.username
    """, (order_id,)).fetchall()

    # Enrich seller data with additional details (matching cart_sellers endpoint)
    enriched_sellers = []
    for row in rows:
        seller_id = row['seller_id']
        seller_data = {
            'seller_id': seller_id,
            'username': row['username'],
            'rating': row['rating'],
            'num_reviews': row['num_reviews'],
            'quantity': row['total_quantity'],
            # Order-specific metrics for this seller's items
            'total_qty': row['total_quantity'],
            'avg_price': row['avg_price'] or 0,
            'total_price': row['total_price'] or 0
        }

        # Get user info (member since, display name)
        user_info = conn.execute('''
            SELECT username, first_name, last_name, created_at
            FROM users WHERE id = ?
        ''', (seller_id,)).fetchone()

        if user_info:
            # Display name: use first_name + last_name if available, else username
            display_name = f"{user_info['first_name'] or ''} {user_info['last_name'] or ''}".strip()
            if not display_name:
                display_name = user_info['username']
            seller_data['display_name'] = display_name

            # Member since year
            if user_info['created_at']:
                seller_data['member_since'] = user_info['created_at'][:4]
            else:
                seller_data['member_since'] = None

        # Check verified seller status (rating >= 4.7 and num_reviews > 100)
        rating = seller_data.get('rating') or 0
        num_reviews = seller_data.get('num_reviews') or 0
        seller_data['is_verified'] = rating >= 4.7 and num_reviews > 100

        # Get transaction count (orders where this seller has sold items)
        transaction_result = conn.execute('''
            SELECT COUNT(DISTINCT o.id) as transaction_count
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            JOIN listings l ON oi.listing_id = l.id
            WHERE l.seller_id = ?
        ''', (seller_id,)).fetchone()
        seller_data['transaction_count'] = transaction_result['transaction_count'] if transaction_result else 0

        # Calculate repeat buyers percentage
        buyers_result = conn.execute('''
            SELECT o.buyer_id, COUNT(DISTINCT o.id) as order_count
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            JOIN listings l ON oi.listing_id = l.id
            WHERE l.seller_id = ?
            GROUP BY o.buyer_id
        ''', (seller_id,)).fetchall()

        total_buyers = len(buyers_result)
        repeat_buyers = sum(1 for b in buyers_result if b['order_count'] >= 2)
        if total_buyers > 0:
            seller_data['repeat_buyers_pct'] = round((repeat_buyers / total_buyers) * 100)
        else:
            seller_data['repeat_buyers_pct'] = 0

        # Get ships from location (state from seller's first address)
        address_result = conn.execute('''
            SELECT city, state FROM addresses WHERE user_id = ? LIMIT 1
        ''', (seller_id,)).fetchone()
        if address_result:
            seller_data['ships_from'] = f"{address_result['city']}, {address_result['state']}"
        else:
            seller_data['ships_from'] = None

        # Get top 3 product lines (specializations) from sold items
        specializations_result = conn.execute('''
            SELECT c.product_line, COUNT(*) as sale_count
            FROM order_items oi
            JOIN listings l ON oi.listing_id = l.id
            JOIN categories c ON l.category_id = c.id
            WHERE l.seller_id = ? AND c.product_line IS NOT NULL AND c.product_line != ''
            GROUP BY c.product_line
            ORDER BY sale_count DESC
            LIMIT 3
        ''', (seller_id,)).fetchall()
        seller_data['specializations'] = [s['product_line'] for s in specializations_result]

        # Calculate median response time
        response_times = conn.execute('''
            SELECT
                m1.timestamp as received_at,
                MIN(m2.timestamp) as responded_at
            FROM messages m1
            JOIN messages m2 ON m1.order_id = m2.order_id
                AND m2.sender_id = m1.receiver_id
                AND m2.timestamp > m1.timestamp
            WHERE m1.receiver_id = ?
            GROUP BY m1.id
        ''', (seller_id,)).fetchall()

        if response_times:
            deltas = []
            for rt in response_times:
                try:
                    received = datetime.fromisoformat(rt['received_at'].replace('Z', '+00:00'))
                    responded = datetime.fromisoformat(rt['responded_at'].replace('Z', '+00:00'))
                    delta_hours = (responded - received).total_seconds() / 3600
                    deltas.append(delta_hours)
                except:
                    pass

            if deltas:
                deltas.sort()
                median_idx = len(deltas) // 2
                median_hours = deltas[median_idx]
                if median_hours < 1:
                    seller_data['response_time'] = "< 1 hour"
                elif median_hours < 24:
                    seller_data['response_time'] = f"< {int(median_hours) + 1} hours"
                else:
                    days = int(median_hours / 24)
                    seller_data['response_time'] = f"< {days + 1} days"
            else:
                seller_data['response_time'] = None
        else:
            seller_data['response_time'] = None

        # Avg ship time - placeholder (tracking not built yet)
        seller_data['avg_ship_time'] = None

        enriched_sellers.append(seller_data)

    conn.close()
    return jsonify(enriched_sellers)


@account_bp.route('/orders/api/<int:order_id>/order_items')
def order_items(order_id):
    if 'user_id' not in session:
        return jsonify(error="Authentication required"), 401

    user_id = session['user_id']

    # SECURITY: Verify user is participant in this order
    access_check = _verify_order_access(order_id, user_id)
    if not access_check:
        if AUDIT_ENABLED:
            log_unauthorized_access('order', order_id, 'view_items')
        return jsonify(error="You do not have access to this order"), 403

    conn = get_db_connection()
    cur = conn.cursor()

    # 1) Pull all item-level data, including listing_photos and seller
    raw_rows = cur.execute(
        """
        SELECT
          oi.id AS item_id,
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
        ORDER BY oi.price_each DESC, oi.id
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
