"""
Analytics service for admin dashboard
Provides data aggregation and metrics calculation for marketplace analytics
"""
from datetime import datetime, timedelta
from database import get_db_connection


class AnalyticsService:
    """Service for calculating analytics and metrics"""

    MARKETPLACE_FEE_RATE = 0.05  # 5% marketplace fee

    @staticmethod
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
        website_revenue = volume_traded * AnalyticsService.MARKETPLACE_FEE_RATE

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
            # Assuming users table has created_at or similar - if not, we'll use id as proxy
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
                'website_revenue': prev_volume * AnalyticsService.MARKETPLACE_FEE_RATE,
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
            'previous_period': prev_period_data
        }

    @staticmethod
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
                    COALESCE(SUM(o.total_price) * {AnalyticsService.MARKETPLACE_FEE_RATE}, 0) as value
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

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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
                (o.total_price * {AnalyticsService.MARKETPLACE_FEE_RATE}) as fee,
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
                COALESCE(SUM(total_price * {AnalyticsService.MARKETPLACE_FEE_RATE}), 0) as total_revenue,
                COALESCE(AVG(total_price * {AnalyticsService.MARKETPLACE_FEE_RATE}), 0) as avg_fee,
                COALESCE(MAX(total_price * {AnalyticsService.MARKETPLACE_FEE_RATE}), 0) as largest_fee,
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

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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
                'message_count': message_count
            },
            'listings': [dict(row) for row in listings],
            'orders': [dict(row) for row in orders],
            'ratings_received': [dict(row) for row in ratings_received],
            'ratings_given': [dict(row) for row in ratings_given]
        }
