"""
Analytics Timeseries

Time series data calculations for charts.
"""

import database

MARKETPLACE_FEE_RATE = 0.05


def get_db_connection():
    """Get database connection - wrapper for late binding in tests"""
    return database.get_db_connection()


def get_timeseries(start_date, end_date, group_by='day', metric='volume'):
    """
    Get time-series data for charts

    Args:
        start_date: Start date (ISO format)
        end_date: End date (ISO format)
        group_by: Grouping interval ('day', 'week', 'month')
        metric: Metric to calculate ('volume', 'revenue', 'trades')

    Returns:
        list: Time series data points
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Determine SQLite date grouping
    if group_by == 'day':
        date_format = '%Y-%m-%d'
    elif group_by == 'week':
        date_format = '%Y-W%W'
    elif group_by == 'month':
        date_format = '%Y-%m'
    else:
        date_format = '%Y-%m-%d'

    # Query based on metric
    if metric == 'volume':
        query = f"""
            SELECT
                strftime('{date_format}', o.created_at) as period,
                COALESCE(SUM(o.total_price), 0) as value
            FROM orders o
            WHERE o.status IN ('Delivered', 'Complete')
            AND o.created_at BETWEEN ? AND ?
            GROUP BY period
            ORDER BY period
        """
    elif metric == 'revenue':
        query = f"""
            SELECT
                strftime('{date_format}', o.created_at) as period,
                COALESCE(SUM(o.total_price) * {MARKETPLACE_FEE_RATE}, 0) as value
            FROM orders o
            WHERE o.status IN ('Delivered', 'Complete')
            AND o.created_at BETWEEN ? AND ?
            GROUP BY period
            ORDER BY period
        """
    else:  # trades
        query = f"""
            SELECT
                strftime('{date_format}', o.created_at) as period,
                COUNT(*) as value
            FROM orders o
            WHERE o.status IN ('Delivered', 'Complete')
            AND o.created_at BETWEEN ? AND ?
            GROUP BY period
            ORDER BY period
        """

    cursor.execute(query, [start_date, end_date])
    results = cursor.fetchall()
    conn.close()

    return [{'period': row['period'], 'value': row['value']} for row in results]


def get_timeseries_by_category(start_date, end_date, group_by='day'):
    """
    Get time-series data broken down by category

    Returns:
        dict: Category names as keys, time series as values
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    if group_by == 'day':
        date_format = '%Y-%m-%d'
    elif group_by == 'week':
        date_format = '%Y-W%W'
    elif group_by == 'month':
        date_format = '%Y-%m'
    else:
        date_format = '%Y-%m-%d'

    query = f"""
        SELECT
            strftime('{date_format}', o.created_at) as period,
            c.product_type,
            COALESCE(SUM(oi.price_each * oi.quantity), 0) as value
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        JOIN listings l ON oi.listing_id = l.id
        JOIN categories c ON l.category_id = c.id
        WHERE o.status IN ('Delivered', 'Complete')
        AND o.created_at BETWEEN ? AND ?
        GROUP BY period, c.product_type
        ORDER BY period, c.product_type
    """

    cursor.execute(query, [start_date, end_date])
    results = cursor.fetchall()
    conn.close()

    # Group by category
    category_data = {}
    for row in results:
        product_type = row['product_type'] or 'Unknown'
        if product_type not in category_data:
            category_data[product_type] = []
        category_data[product_type].append({
            'period': row['period'],
            'value': row['value']
        })

    return category_data
