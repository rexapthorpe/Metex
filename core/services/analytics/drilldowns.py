"""
Analytics Drilldowns

Detailed drilldown queries for admin views.
"""

import database

MARKETPLACE_FEE_RATE = 0.05


def get_db_connection():
    """Get database connection - wrapper for late binding in tests"""
    return database.get_db_connection()


def get_volume_drilldown(start_date=None, end_date=None, limit=100, offset=0):
    """
    Get detailed breakdown of orders contributing to total volume

    Returns:
        dict: Orders list with summary stats
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    date_filter = ""
    params = []
    if start_date and end_date:
        date_filter = "AND o.created_at BETWEEN ? AND ?"
        params = [start_date, end_date]

    # Get detailed orders
    query = f"""
        SELECT
            o.id as order_id,
            o.created_at as order_date,
            o.total_price,
            o.status,
            buyer.username as buyer_username,
            buyer.email as buyer_email,
            COUNT(DISTINCT oi.order_item_id) as item_count,
            GROUP_CONCAT(DISTINCT c.product_type) as product_types
        FROM orders o
        JOIN users buyer ON o.buyer_id = buyer.id
        JOIN order_items oi ON o.id = oi.order_id
        JOIN listings l ON oi.listing_id = l.id
        JOIN categories c ON l.category_id = c.id
        WHERE o.status IN ('Delivered', 'Complete')
        {date_filter}
        GROUP BY o.id
        ORDER BY o.total_price DESC
        LIMIT ? OFFSET ?
    """

    cursor.execute(query, params + [limit, offset])
    orders = cursor.fetchall()

    # Get summary stats
    cursor.execute(f"""
        SELECT
            COUNT(*) as total_count,
            COALESCE(SUM(total_price), 0) as total_volume,
            COALESCE(AVG(total_price), 0) as avg_order_size,
            COALESCE(MAX(total_price), 0) as largest_order,
            COALESCE(
                (SELECT total_price FROM orders
                 WHERE status IN ('Delivered', 'Complete') {date_filter.replace('o.', '')}
                 ORDER BY total_price LIMIT 1 OFFSET
                 (SELECT COUNT(*)/2 FROM orders
                  WHERE status IN ('Delivered', 'Complete') {date_filter.replace('o.', '')})),
                0
            ) as median_order_size
        FROM orders o
        WHERE status IN ('Delivered', 'Complete')
        {date_filter}
    """, params)
    summary = cursor.fetchone()

    conn.close()

    return {
        'orders': [dict(row) for row in orders],
        'summary': dict(summary) if summary else {},
        'total_count': summary['total_count'] if summary else 0,
        'has_more': summary['total_count'] > (offset + limit) if summary else False
    }


def get_revenue_drilldown(start_date=None, end_date=None, limit=100, offset=0):
    """
    Get detailed breakdown of fees/revenue

    Returns:
        dict: Revenue breakdown with summary stats
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    date_filter = ""
    params = []
    if start_date and end_date:
        date_filter = "AND o.created_at BETWEEN ? AND ?"
        params = [start_date, end_date]

    # Get orders with fee breakdown
    query = f"""
        SELECT
            o.id as order_id,
            o.created_at as order_date,
            o.total_price,
            (o.total_price * {MARKETPLACE_FEE_RATE}) as fee,
            buyer.username as buyer_username,
            c.product_type,
            c.metal,
            COUNT(DISTINCT oi.order_item_id) as item_count
        FROM orders o
        JOIN users buyer ON o.buyer_id = buyer.id
        JOIN order_items oi ON o.id = oi.order_id
        JOIN listings l ON oi.listing_id = l.id
        JOIN categories c ON l.category_id = c.id
        WHERE o.status IN ('Delivered', 'Complete')
        {date_filter}
        GROUP BY o.id, c.product_type, c.metal
        ORDER BY fee DESC
        LIMIT ? OFFSET ?
    """

    cursor.execute(query, params + [limit, offset])
    orders = cursor.fetchall()

    # Summary stats
    cursor.execute(f"""
        SELECT
            COALESCE(SUM(total_price * {MARKETPLACE_FEE_RATE}), 0) as total_revenue,
            COALESCE(AVG(total_price * {MARKETPLACE_FEE_RATE}), 0) as avg_fee,
            COALESCE(MAX(total_price * {MARKETPLACE_FEE_RATE}), 0) as largest_fee,
            COUNT(*) as total_count
        FROM orders o
        WHERE status IN ('Delivered', 'Complete')
        {date_filter}
    """, params)
    summary = cursor.fetchone()

    conn.close()

    return {
        'orders': [dict(row) for row in orders],
        'summary': dict(summary) if summary else {},
        'total_count': summary['total_count'] if summary else 0,
        'has_more': summary['total_count'] > (offset + limit) if summary else False
    }


def get_trades_drilldown(start_date=None, end_date=None, limit=100, offset=0):
    """
    Get detailed list of trades/orders

    Returns:
        dict: Trades list with summary stats
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    date_filter = ""
    params = []
    if start_date and end_date:
        date_filter = "AND o.created_at BETWEEN ? AND ?"
        params = [start_date, end_date]

    # Get trades
    query = f"""
        SELECT
            o.id as order_id,
            o.created_at as order_date,
            o.total_price,
            o.status,
            buyer.username as buyer_username,
            COUNT(DISTINCT oi.order_item_id) as item_count
        FROM orders o
        JOIN users buyer ON o.buyer_id = buyer.id
        JOIN order_items oi ON o.id = oi.order_id
        WHERE o.status IN ('Delivered', 'Complete')
        {date_filter}
        GROUP BY o.id
        ORDER BY o.created_at DESC
        LIMIT ? OFFSET ?
    """

    cursor.execute(query, params + [limit, offset])
    trades = cursor.fetchall()

    # Calculate total count
    cursor.execute(f"""
        SELECT COUNT(*) as total_count
        FROM orders
        WHERE status IN ('Delivered', 'Complete')
        {date_filter.replace('o.', '')}
    """, params)
    total_count = cursor.fetchone()['total_count']

    conn.close()

    return {
        'trades': [dict(row) for row in trades],
        'total_count': total_count,
        'has_more': total_count > (offset + limit)
    }


def get_listings_drilldown(limit=100, offset=0):
    """
    Get detailed list of active listings

    Returns:
        dict: Active listings with summary stats
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get active listings
    query = """
        SELECT
            l.id as listing_id,
            l.created_at,
            l.price_per_coin,
            l.quantity,
            l.graded,
            l.grading_service,
            CAST(JULIANDAY('now') - JULIANDAY(l.created_at) AS INTEGER) as days_listed,
            seller.username as seller_username,
            seller.email as seller_email,
            c.metal,
            c.product_type,
            c.weight,
            c.purity
        FROM listings l
        JOIN users seller ON l.seller_id = seller.id
        JOIN categories c ON l.category_id = c.id
        WHERE l.active = 1 AND l.quantity > 0
        ORDER BY l.created_at DESC
        LIMIT ? OFFSET ?
    """

    cursor.execute(query, [limit, offset])
    listings = cursor.fetchall()

    # Summary stats
    cursor.execute("""
        SELECT
            COUNT(*) as total_listings,
            COALESCE(SUM(quantity), 0) as total_units,
            COUNT(DISTINCT category_id) as category_count
        FROM listings
        WHERE active = 1 AND quantity > 0
    """)
    summary = cursor.fetchone()

    conn.close()

    return {
        'listings': [dict(row) for row in listings],
        'summary': dict(summary) if summary else {},
        'total_count': summary['total_listings'] if summary else 0,
        'has_more': summary['total_listings'] > (offset + limit) if summary else False
    }


def get_users_drilldown(limit=100, offset=0, search=None, filter_type=None):
    """
    Get detailed user list with summary stats

    Args:
        filter_type: 'sellers', 'buyers', 'both', or None for all

    Returns:
        dict: User list with stats
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Build filter conditions
    conditions = []
    params = []

    if search:
        conditions.append("(u.username LIKE ? OR u.email LIKE ?)")
        search_term = f"%{search}%"
        params.extend([search_term, search_term])

    # For filters, we need to compute in subquery
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    # Get users with stats
    query = f"""
        SELECT
            u.id,
            u.username,
            u.email,
            u.is_admin,
            COALESCE(
                (SELECT SUM(o.total_price)
                 FROM orders o
                 WHERE o.buyer_id = u.id AND o.status IN ('Delivered', 'Complete')),
                0
            ) as total_purchase_volume,
            COALESCE(
                (SELECT SUM(oi.price_each * oi.quantity)
                 FROM order_items oi
                 JOIN listings l ON oi.listing_id = l.id
                 WHERE l.seller_id = u.id),
                0
            ) as total_sell_volume,
            COALESCE(
                (SELECT COUNT(*)
                 FROM orders o
                 WHERE o.buyer_id = u.id AND o.status IN ('Delivered', 'Complete')),
                0
            ) as buyer_count,
            COALESCE(
                (SELECT COUNT(DISTINCT o.id)
                 FROM orders o
                 JOIN order_items oi ON o.id = oi.order_id
                 JOIN listings l ON oi.listing_id = l.id
                 WHERE l.seller_id = u.id AND o.status IN ('Delivered', 'Complete')),
                0
            ) as seller_count,
            COALESCE(
                (SELECT COUNT(*) FROM listings WHERE seller_id = u.id),
                0
            ) as listing_count,
            COALESCE(
                (SELECT AVG(rating) FROM ratings WHERE ratee_id = u.id),
                0
            ) as avg_rating,
            COALESCE(
                (SELECT COUNT(*) FROM messages WHERE sender_id = u.id OR receiver_id = u.id),
                0
            ) as message_count
        FROM users u
        {where_clause}
        ORDER BY (total_purchase_volume + total_sell_volume) DESC
        LIMIT ? OFFSET ?
    """

    cursor.execute(query, params + [limit, offset])
    users_raw = cursor.fetchall()

    # Filter based on type after fetching
    users = []
    for user in users_raw:
        user_dict = dict(user)
        if filter_type == 'sellers' and user_dict['seller_count'] == 0:
            continue
        elif filter_type == 'buyers' and user_dict['buyer_count'] == 0:
            continue
        elif filter_type == 'both' and (user_dict['seller_count'] == 0 or user_dict['buyer_count'] == 0):
            continue
        users.append(user_dict)

    # Get total count (accounting for filter)
    count_query = f"""
        SELECT COUNT(*) as total
        FROM users u
        {where_clause}
    """
    cursor.execute(count_query, params)
    total_count = cursor.fetchone()['total']

    conn.close()

    return {
        'users': users,
        'total_count': len(users),
        'has_more': total_count > (offset + limit)
    }


def get_user_detail(user_id):
    """
    Get comprehensive analytics for a single user

    Returns:
        dict: Detailed user analytics
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # User overview
    cursor.execute("""
        SELECT
            id,
            username,
            email,
            is_admin,
            first_name,
            last_name,
            phone,
            bio
        FROM users
        WHERE id = ?
    """, [user_id])
    user = cursor.fetchone()

    if not user:
        conn.close()
        return None

    # Purchase stats
    cursor.execute("""
        SELECT
            COALESCE(SUM(total_price), 0) as total_purchase_volume,
            COUNT(*) as order_count,
            COALESCE(AVG(total_price), 0) as avg_order_value
        FROM orders
        WHERE buyer_id = ? AND status IN ('Delivered', 'Complete')
    """, [user_id])
    purchase_stats = cursor.fetchone()

    # Sell stats
    cursor.execute("""
        SELECT
            COALESCE(SUM(oi.price_each * oi.quantity), 0) as total_sell_volume,
            COUNT(DISTINCT o.id) as sell_count
        FROM order_items oi
        JOIN listings l ON oi.listing_id = l.id
        JOIN orders o ON oi.order_id = o.id
        WHERE l.seller_id = ? AND o.status IN ('Delivered', 'Complete')
    """, [user_id])
    sell_stats = cursor.fetchone()

    # Ratings
    cursor.execute("""
        SELECT
            COALESCE(AVG(rating), 0) as avg_rating,
            COUNT(*) as rating_count
        FROM ratings
        WHERE ratee_id = ?
    """, [user_id])
    rating_stats = cursor.fetchone()

    # Listings
    cursor.execute("""
        SELECT
            l.id as listing_id,
            l.created_at,
            l.price_per_coin,
            l.quantity,
            l.active,
            c.metal,
            c.product_type,
            CASE
                WHEN l.active = 0 THEN 'Inactive'
                WHEN l.quantity = 0 THEN 'Sold Out'
                ELSE 'Active'
            END as status
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.seller_id = ?
        ORDER BY l.created_at DESC
        LIMIT 50
    """, [user_id])
    listings = cursor.fetchall()

    # Orders (purchases)
    cursor.execute("""
        SELECT
            o.id as order_id,
            o.created_at,
            o.total_price,
            o.status,
            COUNT(oi.order_item_id) as item_count
        FROM orders o
        LEFT JOIN order_items oi ON o.id = oi.order_id
        WHERE o.buyer_id = ?
        GROUP BY o.id
        ORDER BY o.created_at DESC
        LIMIT 50
    """, [user_id])
    orders = cursor.fetchall()

    # Ratings received
    cursor.execute("""
        SELECT
            r.rating,
            r.comment,
            r.timestamp,
            u.username as rater_username
        FROM ratings r
        JOIN users u ON r.rater_id = u.id
        WHERE r.ratee_id = ?
        ORDER BY r.timestamp DESC
        LIMIT 20
    """, [user_id])
    ratings_received = cursor.fetchall()

    # Ratings given
    cursor.execute("""
        SELECT
            r.rating,
            r.comment,
            r.timestamp,
            u.username as ratee_username
        FROM ratings r
        JOIN users u ON r.ratee_id = u.id
        WHERE r.rater_id = ?
        ORDER BY r.timestamp DESC
        LIMIT 20
    """, [user_id])
    ratings_given = cursor.fetchall()

    # Messages count
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM messages
        WHERE sender_id = ? OR receiver_id = ?
    """, [user_id, user_id])
    message_count = cursor.fetchone()['count']

    # Cancellation stats for this user
    cursor.execute("""
        SELECT
            canceled_orders_as_buyer,
            canceled_volume_as_buyer,
            canceled_orders_as_seller,
            canceled_volume_as_seller,
            denied_cancellations
        FROM user_cancellation_stats
        WHERE user_id = ?
    """, [user_id])
    cancel_stats = cursor.fetchone()

    conn.close()

    return {
        'user': dict(user),
        'stats': {
            'total_purchase_volume': purchase_stats['total_purchase_volume'],
            'total_sell_volume': sell_stats['total_sell_volume'],
            'order_count': purchase_stats['order_count'],
            'sell_count': sell_stats['sell_count'],
            'avg_order_value': purchase_stats['avg_order_value'],
            'avg_rating': rating_stats['avg_rating'],
            'rating_count': rating_stats['rating_count'],
            'message_count': message_count,
            'canceled_orders_as_buyer': cancel_stats['canceled_orders_as_buyer'] if cancel_stats else 0,
            'canceled_volume_as_buyer': cancel_stats['canceled_volume_as_buyer'] if cancel_stats else 0,
            'canceled_orders_as_seller': cancel_stats['canceled_orders_as_seller'] if cancel_stats else 0,
            'canceled_volume_as_seller': cancel_stats['canceled_volume_as_seller'] if cancel_stats else 0,
            'denied_cancellations': cancel_stats['denied_cancellations'] if cancel_stats else 0
        },
        'listings': [dict(row) for row in listings],
        'orders': [dict(row) for row in orders],
        'ratings_received': [dict(row) for row in ratings_received],
        'ratings_given': [dict(row) for row in ratings_given]
    }
