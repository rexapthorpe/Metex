"""
Analytics Timeseries

Time series data calculations for charts.
"""

import database

MARKETPLACE_FEE_RATE = 0.05

# Maps SQLite strftime format strings to PostgreSQL TO_CHAR format strings.
_PG_DATE_FMT = {
    '%Y-%m-%d': 'YYYY-MM-DD',
    '%Y-W%W':   'IYYY-"W"IW',
    '%Y-%m':    'YYYY-MM',
}


def get_db_connection():
    """Get database connection - wrapper for late binding in tests"""
    return database.get_db_connection()


def _period_expr(date_format, col='o.created_at'):
    """Return a SQL date-grouping expression for both SQLite and PostgreSQL."""
    if database.IS_POSTGRES:
        pg_fmt = _PG_DATE_FMT.get(date_format, 'YYYY-MM-DD')
        return f"TO_CHAR({col}, '{pg_fmt}')"
    return f"strftime('{date_format}', {col})"


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
    period = _period_expr(date_format)
    if metric == 'volume':
        query = f"""
            SELECT
                {period} as period,
                COALESCE(SUM(o.total_price), 0) as value
            FROM orders o
            WHERE o.status IN ('Delivered', 'Complete')
            AND o.created_at BETWEEN ? AND ?
            GROUP BY 1
            ORDER BY 1
        """
    elif metric == 'revenue':
        query = f"""
            SELECT
                {period} as period,
                COALESCE(SUM(o.total_price) * {MARKETPLACE_FEE_RATE}, 0) as value
            FROM orders o
            WHERE o.status IN ('Delivered', 'Complete')
            AND o.created_at BETWEEN ? AND ?
            GROUP BY 1
            ORDER BY 1
        """
    else:  # trades
        query = f"""
            SELECT
                {period} as period,
                COUNT(*) as value
            FROM orders o
            WHERE o.status IN ('Delivered', 'Complete')
            AND o.created_at BETWEEN ? AND ?
            GROUP BY 1
            ORDER BY 1
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

    period = _period_expr(date_format)
    query = f"""
        SELECT
            {period} as period,
            c.product_type,
            COALESCE(SUM(oi.price_each * oi.quantity), 0) as value
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        JOIN listings l ON oi.listing_id = l.id
        JOIN categories c ON l.category_id = c.id
        WHERE o.status IN ('Delivered', 'Complete')
        AND o.created_at BETWEEN ? AND ?
        GROUP BY 1, c.product_type
        ORDER BY 1, c.product_type
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
