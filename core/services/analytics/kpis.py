"""
Analytics KPIs

Key Performance Indicators calculations.
"""

from datetime import datetime
import database

MARKETPLACE_FEE_RATE = 0.05


def get_db_connection():
    """Get database connection - wrapper for late binding in tests"""
    return database.get_db_connection()


def get_kpis(start_date=None, end_date=None, compare_previous=False):
    """
    Get key performance indicators (KPIs) for the dashboard

    Args:
        start_date: Start date for metrics (ISO format string or datetime)
        end_date: End date for metrics (ISO format string or datetime)
        compare_previous: Whether to include comparison to previous period

    Returns:
        dict: KPIs including volume, revenue, trades, listings, users
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Build date filter
    date_filter = ""
    params = []
    if start_date and end_date:
        date_filter = "AND o.created_at BETWEEN ? AND ?"
        params = [start_date, end_date]

    # Total volume traded (sum of completed order totals)
    cursor.execute(f"""
        SELECT COALESCE(SUM(total_price), 0) as volume
        FROM orders o
        WHERE status IN ('Delivered', 'Complete')
        {date_filter}
    """, params)
    volume_traded = cursor.fetchone()['volume']

    # Website revenue (5% of volume)
    website_revenue = volume_traded * MARKETPLACE_FEE_RATE

    # Number of trades (completed orders)
    cursor.execute(f"""
        SELECT COUNT(*) as count
        FROM orders o
        WHERE status IN ('Delivered', 'Complete')
        {date_filter}
    """, params)
    num_trades = cursor.fetchone()['count']

    # Active listings (currently available)
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM listings
        WHERE active = 1 AND quantity > 0
    """)
    active_listings = cursor.fetchone()['count']

    # Total users
    cursor.execute("SELECT COUNT(*) as count FROM users")
    total_users = cursor.fetchone()['count']

    # New users in period
    if start_date and end_date:
        cursor.execute("""
            SELECT COUNT(*) as count FROM users
            WHERE id IN (
                SELECT DISTINCT seller_id FROM listings
                UNION
                SELECT DISTINCT buyer_id FROM orders
            )
        """)
        new_users = cursor.fetchone()['count']
    else:
        new_users = 0

    # Conversion funnel
    cursor.execute("SELECT COUNT(DISTINCT seller_id) FROM listings")
    users_with_listings = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT buyer_id) FROM orders")
    users_with_purchases = cursor.fetchone()[0]

    # Canceled orders metrics
    cursor.execute(f"""
        SELECT
            COUNT(*) as count,
            COALESCE(SUM(total_price), 0) as volume
        FROM orders o
        WHERE status IN ('Canceled', 'Cancelled')
        {date_filter}
    """, params)
    canceled_result = cursor.fetchone()
    canceled_orders = canceled_result['count']
    canceled_volume = canceled_result['volume']

    # Previous period comparison
    prev_period_data = None
    if compare_previous and start_date and end_date:
        # Calculate previous period
        start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        period_length = end_dt - start_dt
        prev_start = (start_dt - period_length).isoformat()
        prev_end = start_dt.isoformat()

        cursor.execute(f"""
            SELECT COALESCE(SUM(total_price), 0) as volume
            FROM orders o
            WHERE status IN ('Delivered', 'Complete')
            AND o.created_at BETWEEN ? AND ?
        """, [prev_start, prev_end])
        prev_volume = cursor.fetchone()['volume']

        cursor.execute(f"""
            SELECT COUNT(*) as count
            FROM orders o
            WHERE status IN ('Delivered', 'Complete')
            AND o.created_at BETWEEN ? AND ?
        """, [prev_start, prev_end])
        prev_trades = cursor.fetchone()['count']

        prev_period_data = {
            'volume_traded': prev_volume,
            'website_revenue': prev_volume * MARKETPLACE_FEE_RATE,
            'num_trades': prev_trades
        }

    conn.close()

    return {
        'volume_traded': volume_traded,
        'website_revenue': website_revenue,
        'num_trades': num_trades,
        'active_listings': active_listings,
        'total_users': total_users,
        'new_users': new_users,
        'conversion_funnel': {
            'total_users': total_users,
            'users_with_listings': users_with_listings,
            'users_with_purchases': users_with_purchases
        },
        'canceled_orders': canceled_orders,
        'canceled_volume': canceled_volume,
        'previous_period': prev_period_data
    }
