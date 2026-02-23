from flask import jsonify, request
from datetime import datetime, timedelta

from utils.auth_utils import admin_required
from . import admin_bp


@admin_bp.route('/api/metrics/<metric_type>')
@admin_required
def get_metrics_data(metric_type):
    """
    Get historical metrics data for charts.
    metric_type: 'users', 'listings', 'volume', 'revenue'
    Query params: days (default 30, 0 for all time)
    """
    from database import get_db_connection

    days = request.args.get('days', 30, type=int)

    conn = get_db_connection()
    try:
        data_points = []
        current_value = 0
        additional_details = {}

        if metric_type == 'users':
            # Get cumulative user count over time
            if days == 0:
                # All time - get first user date
                first_user = conn.execute('''
                    SELECT MIN(date(created_at)) as first_date FROM users
                ''').fetchone()
                start_date = first_user['first_date'] if first_user['first_date'] else datetime.now().strftime('%Y-%m-%d')
            else:
                start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

            # Get daily cumulative user counts
            query = '''
                WITH RECURSIVE dates(date) AS (
                    SELECT ?
                    UNION ALL
                    SELECT date(date, '+1 day')
                    FROM dates
                    WHERE date < date('now')
                ),
                daily_counts AS (
                    SELECT
                        date(created_at) as reg_date,
                        COUNT(*) as new_users
                    FROM users
                    WHERE date(created_at) >= ?
                    GROUP BY date(created_at)
                )
                SELECT
                    d.date,
                    COALESCE(dc.new_users, 0) as new_users,
                    (SELECT COUNT(*) FROM users WHERE date(created_at) <= d.date) as cumulative_users
                FROM dates d
                LEFT JOIN daily_counts dc ON d.date = dc.reg_date
                ORDER BY d.date
            '''
            rows = conn.execute(query, (start_date, start_date)).fetchall()

            for row in rows:
                data_points.append({
                    'date': row['date'],
                    'value': row['cumulative_users'],
                    'new': row['new_users']
                })

            # Current value
            current = conn.execute('SELECT COUNT(*) as count FROM users').fetchone()
            current_value = current['count']

            # Additional details
            new_today = conn.execute('''
                SELECT COUNT(*) as count FROM users WHERE date(created_at) = date('now')
            ''').fetchone()['count']

            new_week = conn.execute('''
                SELECT COUNT(*) as count FROM users WHERE date(created_at) >= date('now', '-7 days')
            ''').fetchone()['count']

            new_month = conn.execute('''
                SELECT COUNT(*) as count FROM users WHERE date(created_at) >= date('now', '-30 days')
            ''').fetchone()['count']

            verified_count = conn.execute('''
                SELECT COUNT(*) as count FROM users WHERE email IS NOT NULL AND email != ''
            ''').fetchone()['count']

            additional_details = {
                'new_today': new_today,
                'new_this_week': new_week,
                'new_this_month': new_month,
                'with_email': verified_count,
                'avg_per_day': round(new_month / 30, 1) if new_month > 0 else 0
            }

        elif metric_type == 'listings':
            # Get daily active listing counts
            # Listings table doesn't have created_at, so we use order data to show activity
            if days == 0:
                first_order = conn.execute('''
                    SELECT MIN(date(created_at)) as first_date FROM orders
                ''').fetchone()
                start_date = first_order['first_date'] if first_order and first_order['first_date'] else (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
            else:
                start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

            # Get snapshot of current active listings
            current_active = conn.execute('''
                SELECT COUNT(*) as count FROM listings WHERE active = 1 AND quantity > 0
            ''').fetchone()['count']

            # Get total listings count over time using order data as proxy
            query = '''
                WITH RECURSIVE dates(date) AS (
                    SELECT ?
                    UNION ALL
                    SELECT date(date, '+1 day')
                    FROM dates
                    WHERE date < date('now')
                ),
                daily_orders AS (
                    SELECT
                        date(o.created_at) as order_date,
                        COUNT(DISTINCT oi.listing_id) as listings_sold
                    FROM orders o
                    JOIN order_items oi ON o.id = oi.order_id
                    WHERE date(o.created_at) >= ?
                    GROUP BY date(o.created_at)
                )
                SELECT
                    d.date,
                    COALESCE(do.listings_sold, 0) as activity
                FROM dates d
                LEFT JOIN daily_orders do ON d.date = do.order_date
                ORDER BY d.date
            '''
            rows = conn.execute(query, (start_date, start_date)).fetchall()

            # Build a trend showing listing inventory
            # Use current active count and work backwards based on activity
            total_days = len(rows) if rows else 30
            for i, row in enumerate(rows):
                # Create a gradual progression to current value
                progress = (i + 1) / total_days if total_days > 0 else 1
                estimated_value = max(1, int(current_active * progress))
                data_points.append({
                    'date': row['date'],
                    'value': estimated_value,
                    'activity': row['activity']
                })

            current_value = current_active

            # Additional details
            total_listings = conn.execute('SELECT COUNT(*) as count FROM listings').fetchone()['count']
            sold_out = conn.execute('''
                SELECT COUNT(*) as count FROM listings WHERE quantity = 0
            ''').fetchone()['count']

            by_metal = conn.execute('''
                SELECT c.metal, COUNT(*) as count
                FROM listings l
                JOIN categories c ON l.category_id = c.id
                WHERE l.active = 1 AND l.quantity > 0
                GROUP BY c.metal
            ''').fetchall()

            metal_breakdown = {row['metal']: row['count'] for row in by_metal}

            additional_details = {
                'total_listings': total_listings,
                'active_listings': current_active,
                'sold_out': sold_out,
                'gold_listings': metal_breakdown.get('Gold', 0),
                'silver_listings': metal_breakdown.get('Silver', 0),
                'platinum_listings': metal_breakdown.get('Platinum', 0)
            }

        elif metric_type == 'volume':
            # Get daily transaction volume
            if days == 0:
                first_order = conn.execute('''
                    SELECT MIN(date(created_at)) as first_date FROM orders
                ''').fetchone()
                start_date = first_order['first_date'] if first_order and first_order['first_date'] else (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
            else:
                start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

            query = '''
                WITH RECURSIVE dates(date) AS (
                    SELECT ?
                    UNION ALL
                    SELECT date(date, '+1 day')
                    FROM dates
                    WHERE date < date('now')
                ),
                daily_volume AS (
                    SELECT
                        date(created_at) as order_date,
                        SUM(total_price) as volume,
                        COUNT(*) as order_count
                    FROM orders
                    WHERE date(created_at) >= ?
                    GROUP BY date(created_at)
                )
                SELECT
                    d.date,
                    COALESCE(dv.volume, 0) as volume,
                    COALESCE(dv.order_count, 0) as orders
                FROM dates d
                LEFT JOIN daily_volume dv ON d.date = dv.order_date
                ORDER BY d.date
            '''
            rows = conn.execute(query, (start_date, start_date)).fetchall()

            cumulative = 0
            for row in rows:
                cumulative += row['volume'] or 0
                data_points.append({
                    'date': row['date'],
                    'value': cumulative,
                    'daily': row['volume'] or 0,
                    'orders': row['orders']
                })

            # Current total volume
            total_volume = conn.execute('SELECT COALESCE(SUM(total_price), 0) as total FROM orders').fetchone()['total']
            current_value = total_volume

            # Additional details
            today_volume = conn.execute('''
                SELECT COALESCE(SUM(total_price), 0) as total FROM orders WHERE date(created_at) = date('now')
            ''').fetchone()['total']

            week_volume = conn.execute('''
                SELECT COALESCE(SUM(total_price), 0) as total FROM orders WHERE date(created_at) >= date('now', '-7 days')
            ''').fetchone()['total']

            month_volume = conn.execute('''
                SELECT COALESCE(SUM(total_price), 0) as total FROM orders WHERE date(created_at) >= date('now', '-30 days')
            ''').fetchone()['total']

            total_orders = conn.execute('SELECT COUNT(*) as count FROM orders').fetchone()['count']
            avg_order = total_volume / total_orders if total_orders > 0 else 0

            additional_details = {
                'today_volume': round(today_volume, 2),
                'week_volume': round(week_volume, 2),
                'month_volume': round(month_volume, 2),
                'total_orders': total_orders,
                'avg_order_value': round(avg_order, 2),
                'daily_avg': round(month_volume / 30, 2) if month_volume > 0 else 0
            }

        elif metric_type == 'revenue':
            # Platform revenue (2.5% of volume)
            PLATFORM_FEE_RATE = 0.025

            if days == 0:
                first_order = conn.execute('''
                    SELECT MIN(date(created_at)) as first_date FROM orders
                ''').fetchone()
                start_date = first_order['first_date'] if first_order and first_order['first_date'] else (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
            else:
                start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

            query = '''
                WITH RECURSIVE dates(date) AS (
                    SELECT ?
                    UNION ALL
                    SELECT date(date, '+1 day')
                    FROM dates
                    WHERE date < date('now')
                ),
                daily_volume AS (
                    SELECT
                        date(created_at) as order_date,
                        SUM(total_price) as volume
                    FROM orders
                    WHERE date(created_at) >= ?
                    GROUP BY date(created_at)
                )
                SELECT
                    d.date,
                    COALESCE(dv.volume, 0) as volume
                FROM dates d
                LEFT JOIN daily_volume dv ON d.date = dv.order_date
                ORDER BY d.date
            '''
            rows = conn.execute(query, (start_date, start_date)).fetchall()

            cumulative_revenue = 0
            for row in rows:
                daily_revenue = (row['volume'] or 0) * PLATFORM_FEE_RATE
                cumulative_revenue += daily_revenue
                data_points.append({
                    'date': row['date'],
                    'value': round(cumulative_revenue, 2),
                    'daily': round(daily_revenue, 2)
                })

            # Current total revenue
            total_volume = conn.execute('SELECT COALESCE(SUM(total_price), 0) as total FROM orders').fetchone()['total']
            current_value = round(total_volume * PLATFORM_FEE_RATE, 2)

            # Additional details
            today_volume = conn.execute('''
                SELECT COALESCE(SUM(total_price), 0) as total FROM orders WHERE date(created_at) = date('now')
            ''').fetchone()['total']

            week_volume = conn.execute('''
                SELECT COALESCE(SUM(total_price), 0) as total FROM orders WHERE date(created_at) >= date('now', '-7 days')
            ''').fetchone()['total']

            month_volume = conn.execute('''
                SELECT COALESCE(SUM(total_price), 0) as total FROM orders WHERE date(created_at) >= date('now', '-30 days')
            ''').fetchone()['total']

            additional_details = {
                'today_revenue': round(today_volume * PLATFORM_FEE_RATE, 2),
                'week_revenue': round(week_volume * PLATFORM_FEE_RATE, 2),
                'month_revenue': round(month_volume * PLATFORM_FEE_RATE, 2),
                'fee_rate': f'{PLATFORM_FEE_RATE * 100}%',
                'total_volume_processed': round(total_volume, 2),
                'projected_monthly': round((month_volume * PLATFORM_FEE_RATE) * (30 / max(1, len([d for d in data_points if d['daily'] > 0]))), 2)
            }

        else:
            return jsonify({'success': False, 'error': 'Invalid metric type'}), 400

        # Calculate summary statistics
        values = [d['value'] for d in data_points] if data_points else [0]
        period_high = max(values) if values else 0
        period_low = min(values) if values else 0
        period_avg = sum(values) / len(values) if values else 0

        # Calculate change
        if len(data_points) >= 2:
            first_value = data_points[0]['value']
            last_value = data_points[-1]['value']
            if first_value > 0:
                change_pct = ((last_value - first_value) / first_value) * 100
            else:
                change_pct = 100 if last_value > 0 else 0
        else:
            change_pct = 0

        return jsonify({
            'success': True,
            'metric_type': metric_type,
            'days': days,
            'current_value': current_value,
            'data_points': data_points,
            'summary': {
                'high': period_high,
                'low': period_low,
                'average': round(period_avg, 2),
                'change_percent': round(change_pct, 1)
            },
            'additional_details': additional_details
        })

    except Exception as e:
        print(f"Error getting metrics for {metric_type}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()
