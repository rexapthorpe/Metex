"""
Admin Analytics Routes

This module contains analytics dashboard routes for the admin panel.
Routes:
- /analytics - Analytics dashboard page
- /analytics/kpis - KPI data
- /analytics/timeseries - Time-series chart data
- /analytics/top-items - Top traded items
- /analytics/top-users - Top sellers/buyers
- /analytics/market-health - Market health metrics
- /analytics/user-analytics - User activity metrics
- /analytics/operational - Operational metrics
- /analytics/largest-transactions - Largest transactions
- /analytics/categories - Category statistics
- /analytics/drilldown/* - Drilldown endpoints
- /api/clear-data - Clear marketplace data

IMPORTANT: All route URLs and endpoint names are preserved from original admin_routes.py
"""

from flask import render_template, jsonify, request
from datetime import datetime, timedelta
from utils.auth_utils import admin_required
from services.analytics_service import AnalyticsService
from database import get_db_connection, IS_POSTGRES
from . import admin_bp


@admin_bp.route('/analytics')
@admin_required
def analytics():
    """Render the analytics dashboard page"""
    return render_template('admin/analytics.html')


@admin_bp.route('/analytics/kpis')
@admin_required
def get_kpis():
    """
    Get KPI data for the analytics dashboard

    Query params:
        - start: Start date (ISO format)
        - end: End date (ISO format)
        - compare: Whether to compare to previous period (true/false)
    """
    try:
        start_date = request.args.get('start')
        end_date = request.args.get('end')
        compare = request.args.get('compare', 'false').lower() == 'true'

        # Default to last 30 days if not specified
        if not start_date or not end_date:
            end_date = datetime.now().isoformat()
            start_date = (datetime.now() - timedelta(days=30)).isoformat()

        kpis = AnalyticsService.get_kpis(start_date, end_date, compare)

        return jsonify({
            'success': True,
            'data': kpis
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/analytics/timeseries')
@admin_required
def get_timeseries():
    """
    Get time-series data for charts

    Query params:
        - start: Start date (ISO format)
        - end: End date (ISO format)
        - group_by: Grouping interval (day/week/month)
        - metric: Metric to calculate (volume/revenue/trades)
        - breakdown: Whether to break down by category (true/false)
    """
    try:
        start_date = request.args.get('start')
        end_date = request.args.get('end')
        group_by = request.args.get('group_by', 'day')
        metric = request.args.get('metric', 'volume')
        breakdown = request.args.get('breakdown', 'false').lower() == 'true'

        # Default to last 30 days if not specified
        if not start_date or not end_date:
            end_date = datetime.now().isoformat()
            start_date = (datetime.now() - timedelta(days=30)).isoformat()

        if breakdown:
            data = AnalyticsService.get_timeseries_by_category(start_date, end_date, group_by)
        else:
            data = AnalyticsService.get_timeseries(start_date, end_date, group_by, metric)

        return jsonify({
            'success': True,
            'data': data
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/analytics/top-items')
@admin_required
def get_top_items():
    """
    Get top traded items

    Query params:
        - start: Start date (ISO format)
        - end: End date (ISO format)
        - limit: Number of items to return (default: 10)
    """
    try:
        start_date = request.args.get('start')
        end_date = request.args.get('end')
        limit = int(request.args.get('limit', 10))

        data = AnalyticsService.get_top_items(start_date, end_date, limit)

        return jsonify({
            'success': True,
            'data': data
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/analytics/top-users')
@admin_required
def get_top_users():
    """
    Get top sellers and buyers

    Query params:
        - start: Start date (ISO format)
        - end: End date (ISO format)
        - limit: Number of users to return (default: 10)
    """
    try:
        start_date = request.args.get('start')
        end_date = request.args.get('end')
        limit = int(request.args.get('limit', 10))

        data = AnalyticsService.get_top_users(start_date, end_date, limit)

        return jsonify({
            'success': True,
            'data': data
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/analytics/market-health')
@admin_required
def get_market_health():
    """
    Get market health and liquidity metrics

    Query params:
        - start: Start date (ISO format)
        - end: End date (ISO format)
    """
    try:
        start_date = request.args.get('start')
        end_date = request.args.get('end')

        data = AnalyticsService.get_market_health(start_date, end_date)

        return jsonify({
            'success': True,
            'data': data
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/analytics/user-analytics')
@admin_required
def get_user_analytics():
    """
    Get user activity and engagement metrics

    Query params:
        - start: Start date (ISO format)
        - end: End date (ISO format)
    """
    try:
        start_date = request.args.get('start')
        end_date = request.args.get('end')

        data = AnalyticsService.get_user_analytics(start_date, end_date)

        return jsonify({
            'success': True,
            'data': data
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/analytics/operational')
@admin_required
def get_operational():
    """
    Get operational and moderation metrics

    Query params:
        - start: Start date (ISO format)
        - end: End date (ISO format)
    """
    try:
        start_date = request.args.get('start')
        end_date = request.args.get('end')

        data = AnalyticsService.get_operational_metrics(start_date, end_date)

        return jsonify({
            'success': True,
            'data': data
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/analytics/largest-transactions')
@admin_required
def get_largest_transactions():
    """
    Get largest transactions

    Query params:
        - limit: Number of transactions to return (default: 10)
    """
    try:
        limit = int(request.args.get('limit', 10))

        data = AnalyticsService.get_largest_transactions(limit)

        return jsonify({
            'success': True,
            'data': data
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/analytics/categories')
@admin_required
def get_category_stats():
    """
    Get category statistics

    Query params:
        - start: Start date (ISO format)
        - end: End date (ISO format)
    """
    try:
        start_date = request.args.get('start')
        end_date = request.args.get('end')

        data = AnalyticsService.get_category_stats(start_date, end_date)

        return jsonify({
            'success': True,
            'data': data
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# KPI Drilldown Endpoints

@admin_bp.route('/analytics/drilldown/volume')
@admin_required
def get_volume_drilldown_data():
    """
    Get detailed breakdown of orders contributing to total volume

    Query params:
        - start: Start date
        - end: End date
        - limit: Results limit (default 100)
        - offset: Results offset (default 0)
    """
    try:
        start_date = request.args.get('start')
        end_date = request.args.get('end')
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))

        data = AnalyticsService.get_volume_drilldown(start_date, end_date, limit, offset)

        return jsonify({
            'success': True,
            'data': data
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/analytics/drilldown/revenue')
@admin_required
def get_revenue_drilldown_data():
    """
    Get detailed breakdown of revenue/fees

    Query params:
        - start: Start date
        - end: End date
        - limit: Results limit (default 100)
        - offset: Results offset (default 0)
    """
    try:
        start_date = request.args.get('start')
        end_date = request.args.get('end')
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))

        data = AnalyticsService.get_revenue_drilldown(start_date, end_date, limit, offset)

        return jsonify({
            'success': True,
            'data': data
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/analytics/drilldown/trades')
@admin_required
def get_trades_drilldown_data():
    """
    Get detailed list of trades

    Query params:
        - start: Start date
        - end: End date
        - limit: Results limit (default 100)
        - offset: Results offset (default 0)
    """
    try:
        start_date = request.args.get('start')
        end_date = request.args.get('end')
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))

        data = AnalyticsService.get_trades_drilldown(start_date, end_date, limit, offset)

        return jsonify({
            'success': True,
            'data': data
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/analytics/drilldown/listings')
@admin_required
def get_listings_drilldown_data():
    """
    Get detailed list of active listings

    Query params:
        - limit: Results limit (default 100)
        - offset: Results offset (default 0)
    """
    try:
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))

        data = AnalyticsService.get_listings_drilldown(limit, offset)

        return jsonify({
            'success': True,
            'data': data
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/analytics/drilldown/users')
@admin_required
def get_users_drilldown_data():
    """
    Get detailed user list with stats

    Query params:
        - limit: Results limit (default 100)
        - offset: Results offset (default 0)
        - search: Search term for username/email
        - filter: 'sellers', 'buyers', 'both', or None
    """
    try:
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        search = request.args.get('search')
        filter_type = request.args.get('filter')

        data = AnalyticsService.get_users_drilldown(limit, offset, search, filter_type)

        return jsonify({
            'success': True,
            'data': data
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/analytics/user/<int:user_id>')
@admin_required
def get_user_detail_data(user_id):
    """
    Get comprehensive analytics for a single user

    Path params:
        - user_id: User ID
    """
    try:
        data = AnalyticsService.get_user_detail(user_id)

        if not data:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404

        return jsonify({
            'success': True,
            'data': data
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/api/clear-data', methods=['POST'])
@admin_required
def clear_marketplace_data():
    """
    Clear selected data from database based on options provided.
    Options: listings, orders, bids, cart, ratings, price_history, messages, notifications,
             addresses, phones, emails, accounts
    """
    from database import get_db_connection

    data = request.get_json() or {}
    options = data.get('options', [])

    if not options:
        return jsonify({'success': False, 'error': 'No options selected'}), 400

    # Define which tables to clear for each option
    option_tables = {
        'listings': ['listings', 'listing_photos', 'listing_set_items', 'listing_set_item_photos'],
        'orders': ['orders', 'order_items'],
        'bids': ['bids', 'bid_fills'],
        'cart': ['cart_items', 'cart_buckets'],
        'ratings': ['ratings'],
        'price_history': ['bucket_price_history', 'price_history'],
        'messages': ['messages'],
        'notifications': ['notifications'],
        'addresses': ['addresses'],
        'buckets': ['categories', 'bucket_price_history'],
    }

    # Special options that update user table fields instead of deleting tables
    user_field_options = {
        'phones': 'phone',
        'emails': 'email',
        'accounts': None  # Special handling - delete users
    }

    conn = get_db_connection()
    try:
        # Disable FK constraints
        conn.execute('PRAGMA foreign_keys = OFF')

        total_deleted = 0
        deleted_tables = []
        cleared_fields = []

        # Process table deletions
        for option in options:
            if option in option_tables:
                for table in option_tables[option]:
                    try:
                        # Check if table exists
                        check = conn.execute(
                            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                            (table,)
                        ).fetchone()
                        if not check:
                            continue

                        count = conn.execute(f'SELECT COUNT(*) as count FROM {table}').fetchone()['count']
                        if count > 0:
                            conn.execute(f'DELETE FROM {table}')
                            # Reset auto-increment
                            conn.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table,))
                            total_deleted += count
                            deleted_tables.append({'table': table, 'count': count})
                    except Exception as e:
                        print(f"Error clearing {table}: {e}")

        # Process user field updates
        for option in options:
            if option in user_field_options:
                field = user_field_options[option]
                try:
                    if option == 'accounts':
                        # Delete all users (dangerous!)
                        count = conn.execute('SELECT COUNT(*) as count FROM users').fetchone()['count']
                        if count > 0:
                            conn.execute('DELETE FROM users')
                            conn.execute("DELETE FROM sqlite_sequence WHERE name = 'users'")
                            total_deleted += count
                            deleted_tables.append({'table': 'users', 'count': count})
                    elif field:
                        # Clear specific field in users table
                        count = conn.execute(f'SELECT COUNT(*) as count FROM users WHERE {field} IS NOT NULL AND {field} != ""').fetchone()['count']
                        if count > 0:
                            conn.execute(f'UPDATE users SET {field} = NULL')
                            cleared_fields.append({'field': field, 'count': count})
                            total_deleted += count
                except Exception as e:
                    print(f"Error clearing user field {option}: {e}")

        # Re-enable FK constraints
        conn.execute('PRAGMA foreign_keys = ON')
        conn.commit()

        # Build summary message
        parts = []
        if deleted_tables:
            parts.append(f"{len(deleted_tables)} tables cleared")
        if cleared_fields:
            parts.append(f"{len(cleared_fields)} user fields cleared")

        message = f'Successfully cleared {total_deleted:,} records'
        if parts:
            message += f' ({", ".join(parts)})'

        return jsonify({
            'success': True,
            'message': message,
            'total_deleted': total_deleted,
            'tables_cleared': deleted_tables,
            'fields_cleared': cleared_fields
        })

    except Exception as e:
        print(f"Error clearing data: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()
