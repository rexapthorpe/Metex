"""
Analytics Metrics

Market health, user analytics, operational metrics, and category stats.
"""

import database


def get_db_connection():
    """Get database connection - wrapper for late binding in tests"""
    return database.get_db_connection()


def get_market_health(start_date=None, end_date=None):
    """
    Get market health and liquidity metrics

    Returns:
        dict: Market health indicators
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    date_filter = ""
    params = []
    if start_date and end_date:
        date_filter = "WHERE created_at BETWEEN ? AND ?"
        params = [start_date, end_date]

    # Median time to sell (for sold listings in period)
    cursor.execute(f"""
        SELECT AVG(days_to_sell) as median_days
        FROM (
            SELECT
                CAST(JULIANDAY(o.created_at) - JULIANDAY(l.created_at) AS INTEGER) as days_to_sell
            FROM listings l
            JOIN order_items oi ON l.id = oi.listing_id
            JOIN orders o ON oi.order_id = o.id
            WHERE o.status IN ('Delivered', 'Complete')
            {date_filter}
        )
    """, params if params else [])
    result = cursor.fetchone()
    median_time_to_sell = result['median_days'] if result['median_days'] else 0

    # Sell-through rate
    if start_date and end_date:
        cursor.execute("""
            SELECT COUNT(*) as total_created
            FROM listings
            WHERE created_at BETWEEN ? AND ?
        """, params)
        total_created = cursor.fetchone()['total_created']

        cursor.execute(f"""
            SELECT COUNT(DISTINCT l.id) as total_sold
            FROM listings l
            JOIN order_items oi ON l.id = oi.listing_id
            JOIN orders o ON oi.order_id = o.id
            WHERE o.status IN ('Delivered', 'Complete')
            AND l.created_at BETWEEN ? AND ?
        """, params)
        total_sold = cursor.fetchone()['total_sold']

        sell_through_rate = (total_sold / total_created * 100) if total_created > 0 else 0
    else:
        sell_through_rate = 0

    # Inventory depth per metal
    cursor.execute("""
        SELECT
            c.metal,
            COUNT(DISTINCT l.id) as listing_count,
            COALESCE(SUM(l.quantity), 0) as total_quantity
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.active = 1
        GROUP BY c.metal
    """)
    inventory_by_metal = cursor.fetchall()

    # Price dispersion (for active listings)
    cursor.execute("""
        SELECT
            c.metal,
            c.product_type,
            MIN(l.price_per_coin) as min_price,
            AVG(l.price_per_coin) as avg_price,
            MAX(l.price_per_coin) as max_price
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.active = 1
        GROUP BY c.metal, c.product_type
    """)
    price_dispersion = cursor.fetchall()

    conn.close()

    return {
        'median_time_to_sell': median_time_to_sell,
        'sell_through_rate': sell_through_rate,
        'inventory_by_metal': [dict(row) for row in inventory_by_metal],
        'price_dispersion': [dict(row) for row in price_dispersion]
    }


def get_user_analytics(start_date=None, end_date=None):
    """
    Get user activity and engagement metrics

    Returns:
        dict: User analytics
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Active users (users who placed bid, listed item, or purchased in period)
    if start_date and end_date:
        cursor.execute("""
            SELECT COUNT(DISTINCT user_id) as count
            FROM (
                SELECT seller_id as user_id FROM listings WHERE created_at BETWEEN ? AND ?
                UNION
                SELECT buyer_id as user_id FROM orders WHERE created_at BETWEEN ? AND ?
                UNION
                SELECT buyer_id as user_id FROM bids WHERE created_at BETWEEN ? AND ?
            )
        """, [start_date, end_date, start_date, end_date, start_date, end_date])
        active_users = cursor.fetchone()['count']
    else:
        active_users = 0

    # Total registered users
    cursor.execute("SELECT COUNT(*) as count FROM users")
    total_users = cursor.fetchone()['count']

    conn.close()

    return {
        'active_users': active_users,
        'total_users': total_users,
        'activity_rate': (active_users / total_users * 100) if total_users > 0 else 0
    }


def get_operational_metrics(start_date=None, end_date=None):
    """
    Get operational and moderation metrics

    Returns:
        dict: Operational metrics
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    date_filter = ""
    params = []
    if start_date and end_date:
        date_filter = "WHERE timestamp BETWEEN ? AND ?"
        params = [start_date, end_date]

    # Message volume
    cursor.execute(f"""
        SELECT COUNT(*) as total_messages
        FROM messages
        {date_filter}
    """, params)
    total_messages = cursor.fetchone()['total_messages']

    # Ratings health
    cursor.execute("""
        SELECT
            AVG(rating) as avg_rating,
            COUNT(*) as total_ratings
        FROM ratings
    """)
    ratings_data = cursor.fetchone()

    # Rating distribution
    cursor.execute("""
        SELECT
            rating,
            COUNT(*) as count
        FROM ratings
        GROUP BY rating
        ORDER BY rating DESC
    """)
    rating_distribution = cursor.fetchall()

    conn.close()

    return {
        'total_messages': total_messages,
        'avg_rating': ratings_data['avg_rating'] if ratings_data['avg_rating'] else 0,
        'total_ratings': ratings_data['total_ratings'],
        'rating_distribution': [dict(row) for row in rating_distribution]
    }


def get_category_stats(start_date=None, end_date=None):
    """
    Get statistics by category

    Returns:
        list: Category statistics
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    date_filter = ""
    params = []
    if start_date and end_date:
        date_filter = "AND o.created_at BETWEEN ? AND ?"
        params = [start_date, end_date]

    cursor.execute(f"""
        SELECT
            c.product_type,
            c.metal,
            COALESCE(SUM(oi.price_each * oi.quantity), 0) as total_volume,
            COUNT(DISTINCT o.id) as trade_count,
            COALESCE(AVG(oi.price_each), 0) as avg_price
        FROM categories c
        JOIN listings l ON c.id = l.category_id
        JOIN order_items oi ON l.id = oi.listing_id
        JOIN orders o ON oi.order_id = o.id
        WHERE o.status IN ('Delivered', 'Complete')
        {date_filter}
        GROUP BY c.product_type, c.metal
        ORDER BY total_volume DESC
    """, params)
    results = cursor.fetchall()
    conn.close()

    return [dict(row) for row in results]
