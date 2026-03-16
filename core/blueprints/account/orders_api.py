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

            # Member since (formatted as "Mon YYYY")
            raw_date = user_info['created_at']
            if raw_date:
                try:
                    dt = datetime.fromisoformat(str(raw_date).replace('Z', ''))
                    seller_data['member_since'] = dt.strftime('%b %Y')
                except (ValueError, TypeError):
                    seller_data['member_since'] = str(raw_date)[:4]
            else:
                seller_data['member_since'] = None

        # Check verified seller status (rating >= 4.7 and num_reviews > 100)
        rating = seller_data.get('rating') or 0
        num_reviews = seller_data.get('num_reviews') or 0
        seller_data['is_verified'] = rating >= 4.7 and num_reviews > 100

        # Metex Guaranteed designation
        mg_row = conn.execute(
            'SELECT COALESCE(is_metex_guaranteed, 0) AS v FROM users WHERE id = ?',
            (seller_id,)
        ).fetchone()
        seller_data['is_metex_guaranteed'] = bool(mg_row and mg_row['v'])

        # Transaction count: only orders confirmed as delivered
        transaction_result = conn.execute('''
            SELECT COUNT(DISTINCT o.id) as transaction_count
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            JOIN listings l ON oi.listing_id = l.id
            WHERE l.seller_id = ?
              AND o.status IN ('Delivered', 'Complete')
        ''', (seller_id,)).fetchone()
        seller_data['transaction_count'] = transaction_result['transaction_count'] if transaction_result else 0

        # Fulfillment percentage (non-canceled orders / total orders)
        fulfillment_result = conn.execute('''
            SELECT
                COUNT(DISTINCT o.id) AS total,
                SUM(CASE WHEN o.canceled_at IS NULL THEN 1 ELSE 0 END) AS fulfilled
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            JOIN listings l ON oi.listing_id = l.id
            WHERE l.seller_id = ?
        ''', (seller_id,)).fetchone()
        if fulfillment_result and fulfillment_result['total']:
            seller_data['fulfillment_pct'] = round(
                (fulfillment_result['fulfilled'] / fulfillment_result['total']) * 100
            )
        else:
            seller_data['fulfillment_pct'] = None

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

        # Avg ship time: days from order creation to tracking number entry
        # Computed in Python to avoid julianday() (SQLite-only) vs EXTRACT (PostgreSQL)
        ship_rows = conn.execute('''
            SELECT sot.created_at AS shipped_at, o.created_at AS ordered_at
            FROM seller_order_tracking sot
            JOIN orders o ON sot.order_id = o.id
            WHERE sot.seller_id = ?
              AND sot.tracking_number IS NOT NULL
              AND sot.tracking_number != ?
        ''', (seller_id, '')).fetchall()
        ship_deltas = []
        for sr in ship_rows:
            try:
                t0 = datetime.fromisoformat(str(sr['ordered_at']).replace('Z', ''))
                t1 = datetime.fromisoformat(str(sr['shipped_at']).replace('Z', ''))
                ship_deltas.append((t1 - t0).total_seconds() / 86400)
            except Exception:
                pass
        if ship_deltas:
            avg_days = sum(ship_deltas) / len(ship_deltas)
            d = round(avg_days)
            seller_data['avg_ship_time'] = f"{d} day{'s' if d != 1 else ''}"
        else:
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
          c.series_variant,
          c.coin_series,

          l.graded,
          l.grading_service,
          l.is_isolated,
          l.isolated_type,
          l.packaging_type,
          l.packaging_notes,
          l.edition_number,
          l.edition_total,
          l.condition_notes,
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
            "series_variant" : first.get("series_variant"),
            "coin_series"    : first.get("coin_series"),
            "grading_service": grading_service,
            "seller_username": first.get("seller_username"),

            # image for the group
            "image_url"      : first.get("image_url"),

            # set listing metadata (for set item arrow navigation in modal)
            "listing_id"     : first.get("listing_id"),
            "is_isolated"    : first.get("is_isolated"),
            "isolated_type"  : first.get("isolated_type"),
            "packaging_type" : first.get("packaging_type"),
            "packaging_notes": first.get("packaging_notes"),
            "edition_number" : first.get("edition_number"),
            "edition_total"  : first.get("edition_total"),
            "condition_notes": first.get("condition_notes"),

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


@account_bp.route('/orders/api/<int:order_id>/buyer_info')
def order_buyer_info(order_id):
    """
    Get buyer profile stats for a sold order.

    SECURITY: Only the seller of that order can view buyer info.
    """
    if 'user_id' not in session:
        return jsonify(error="Authentication required"), 401

    user_id = session['user_id']

    # SECURITY: Verify user is a seller in this order
    access_check = _verify_order_access(order_id, user_id)
    if not access_check:
        if AUDIT_ENABLED:
            log_unauthorized_access('order', order_id, 'view_buyer')
        return jsonify(error="You do not have access to this order"), 403

    conn = get_db_connection()

    # Get buyer info
    buyer_row = conn.execute('''
        SELECT u.id AS buyer_id, u.username, u.first_name, u.last_name, u.created_at
        FROM orders o
        JOIN users u ON o.buyer_id = u.id
        WHERE o.id = ?
    ''', (order_id,)).fetchone()

    if not buyer_row:
        conn.close()
        return jsonify(error="Buyer not found"), 404

    buyer_id = buyer_row['buyer_id']

    display_name = f"{buyer_row['first_name'] or ''} {buyer_row['last_name'] or ''}".strip()
    if not display_name:
        display_name = buyer_row['username']

    raw_date = buyer_row['created_at']
    if raw_date:
        try:
            dt = datetime.fromisoformat(str(raw_date).replace('Z', ''))
            member_since = dt.strftime('%b %Y')
        except (ValueError, TypeError):
            member_since = str(raw_date)[:4]
    else:
        member_since = None

    # Rating and reviews
    rating_row = conn.execute('''
        SELECT COALESCE(AVG(r.rating), 0) AS rating,
               COUNT(r.id) AS num_reviews
        FROM ratings r WHERE r.ratee_id = ?
    ''', (buyer_id,)).fetchone()

    # Completed transaction count (as buyer)
    tx_row = conn.execute('''
        SELECT COUNT(DISTINCT o.id) AS transaction_count
        FROM orders o
        WHERE o.buyer_id = ? AND o.status IN ('Delivered', 'Complete')
    ''', (buyer_id,)).fetchone()

    # Repeat sellers percentage (sellers they've bought from more than once)
    sellers_rows = conn.execute('''
        SELECT l.seller_id, COUNT(DISTINCT o.id) AS order_count
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        JOIN listings l ON oi.listing_id = l.id
        WHERE o.buyer_id = ?
        GROUP BY l.seller_id
    ''', (buyer_id,)).fetchall()
    total_sellers = len(sellers_rows)
    repeat_sellers = sum(1 for s in sellers_rows if s['order_count'] >= 2)
    repeat_sellers_pct = round((repeat_sellers / total_sellers) * 100) if total_sellers > 0 else 0

    # Order quantity for this specific order
    qty_row = conn.execute('''
        SELECT SUM(oi.quantity) AS quantity
        FROM order_items oi WHERE oi.order_id = ?
    ''', (order_id,)).fetchone()

    is_verified = (rating_row['rating'] or 0) >= 4.7 and (rating_row['num_reviews'] or 0) > 100

    mg_row = conn.execute(
        'SELECT COALESCE(is_metex_guaranteed, 0) AS v FROM users WHERE id = ?',
        (buyer_id,)
    ).fetchone()
    is_metex_guaranteed = bool(mg_row and mg_row['v'])

    conn.close()

    return jsonify({
        'buyer_id': buyer_id,
        'username': buyer_row['username'],
        'display_name': display_name,
        'rating': float(rating_row['rating'] or 0),
        'num_reviews': int(rating_row['num_reviews'] or 0),
        'transaction_count': int(tx_row['transaction_count'] or 0),
        'repeat_sellers_pct': repeat_sellers_pct,
        'member_since': member_since,
        'quantity': int(qty_row['quantity'] or 0) if qty_row else 0,
        'is_verified': is_verified,
        'is_metex_guaranteed': is_metex_guaranteed,
    })
