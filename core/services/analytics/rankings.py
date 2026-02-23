"""
Analytics Rankings

Top items, users, and transactions rankings.
"""

import database


def get_db_connection():
    """Get database connection - wrapper for late binding in tests"""
    return database.get_db_connection()


def get_top_items(start_date=None, end_date=None, limit=10):
    """
    Get top traded items by volume and trade count

    Returns:
        dict: Top items by different metrics
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    date_filter = ""
    params = []
    if start_date and end_date:
        date_filter = "AND o.created_at BETWEEN ? AND ?"
        params = [start_date, end_date]

    # Most traded by volume
    cursor.execute(f"""
        SELECT
            c.metal,
            c.product_type,
            c.weight,
            c.purity,
            COALESCE(SUM(oi.price_each * oi.quantity), 0) as total_volume,
            COUNT(DISTINCT o.id) as trade_count,
            COALESCE(AVG(oi.price_each), 0) as avg_price
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        JOIN listings l ON oi.listing_id = l.id
        JOIN categories c ON l.category_id = c.id
        WHERE o.status IN ('Delivered', 'Complete')
        {date_filter}
        GROUP BY c.metal, c.product_type, c.weight, c.purity
        ORDER BY total_volume DESC
        LIMIT ?
    """, params + [limit])
    top_by_volume = cursor.fetchall()

    # Most traded by count
    cursor.execute(f"""
        SELECT
            c.metal,
            c.product_type,
            c.weight,
            c.purity,
            COUNT(DISTINCT o.id) as trade_count,
            COALESCE(SUM(oi.price_each * oi.quantity), 0) as total_volume,
            COALESCE(AVG(oi.price_each), 0) as avg_price
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        JOIN listings l ON oi.listing_id = l.id
        JOIN categories c ON l.category_id = c.id
        WHERE o.status IN ('Delivered', 'Complete')
        {date_filter}
        GROUP BY c.metal, c.product_type, c.weight, c.purity
        ORDER BY trade_count DESC
        LIMIT ?
    """, params + [limit])
    top_by_count = cursor.fetchall()

    conn.close()

    return {
        'by_volume': [dict(row) for row in top_by_volume],
        'by_count': [dict(row) for row in top_by_count]
    }


def get_top_users(start_date=None, end_date=None, limit=10):
    """
    Get top sellers and buyers

    Returns:
        dict: Top sellers and buyers by different metrics
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    date_filter = ""
    params = []
    if start_date and end_date:
        date_filter = "AND o.created_at BETWEEN ? AND ?"
        params = [start_date, end_date]

    # Top sellers by volume
    cursor.execute(f"""
        SELECT
            u.id,
            u.username,
            u.email,
            COALESCE(SUM(oi.price_each * oi.quantity), 0) as total_volume,
            COUNT(DISTINCT o.id) as order_count,
            COALESCE(AVG(r.rating), 0) as avg_rating
        FROM users u
        JOIN listings l ON u.id = l.seller_id
        JOIN order_items oi ON l.id = oi.listing_id
        JOIN orders o ON oi.order_id = o.id
        LEFT JOIN ratings r ON u.id = r.ratee_id
        WHERE o.status IN ('Delivered', 'Complete')
        {date_filter}
        GROUP BY u.id, u.username, u.email
        ORDER BY total_volume DESC
        LIMIT ?
    """, params + [limit])
    top_sellers = cursor.fetchall()

    # Top buyers by volume
    cursor.execute(f"""
        SELECT
            u.id,
            u.username,
            u.email,
            COALESCE(SUM(o.total_price), 0) as total_volume,
            COUNT(DISTINCT o.id) as order_count,
            COALESCE(AVG(r.rating), 0) as avg_rating
        FROM users u
        JOIN orders o ON u.id = o.buyer_id
        LEFT JOIN ratings r ON u.id = r.ratee_id
        WHERE o.status IN ('Delivered', 'Complete')
        {date_filter}
        GROUP BY u.id, u.username, u.email
        ORDER BY total_volume DESC
        LIMIT ?
    """, params + [limit])
    top_buyers = cursor.fetchall()

    conn.close()

    return {
        'sellers': [dict(row) for row in top_sellers],
        'buyers': [dict(row) for row in top_buyers]
    }


def get_largest_transactions(limit=10):
    """
    Get largest transactions by value

    Returns:
        list: Largest orders
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            o.id,
            o.total_price,
            o.created_at,
            o.status,
            u.username as buyer_username,
            COUNT(oi.order_item_id) as item_count
        FROM orders o
        JOIN users u ON o.buyer_id = u.id
        JOIN order_items oi ON o.id = oi.order_id
        WHERE o.status IN ('Delivered', 'Complete')
        GROUP BY o.id
        ORDER BY o.total_price DESC
        LIMIT ?
    """, [limit])
    results = cursor.fetchall()
    conn.close()

    return [dict(row) for row in results]
