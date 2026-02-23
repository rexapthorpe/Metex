"""
Admin Ledger Routes

This module contains all ledger-related admin routes:
- /ledger: Main ledger dashboard page
- /ledger/order/<order_id>: Order detail page
- /api/ledger/orders: API for filtered order list
- /api/ledger/order/<order_id>: API for order detail
- /api/ledger/stats: API for ledger statistics
- /api/ledger/order/<order_id>/events: API for order events

IMPORTANT: Route URLs and endpoint names preserved exactly from admin_routes.py
"""

from datetime import datetime
from flask import render_template, jsonify, request
from utils.auth_utils import admin_required
from . import admin_bp


def _format_time_ago(timestamp_str):
    """Format a timestamp string as 'X time ago'"""
    if not timestamp_str:
        return 'Unknown'

    try:
        # Parse the timestamp
        if 'T' in timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        else:
            timestamp = datetime.strptime(timestamp_str[:19], '%Y-%m-%d %H:%M:%S')

        # Make naive if needed
        if timestamp.tzinfo:
            timestamp = timestamp.replace(tzinfo=None)

        now = datetime.now()
        diff = now - timestamp

        # Handle future timestamps
        if diff.total_seconds() < 0:
            return 'Just now'

        days = diff.days
        seconds = diff.seconds

        if days >= 365:
            years = days // 365
            return f"{years} year{'s' if years > 1 else ''} ago"
        elif days >= 30:
            months = days // 30
            return f"{months} month{'s' if months > 1 else ''} ago"
        elif days > 0:
            return f"{days} day{'s' if days > 1 else ''} ago"
        elif seconds >= 3600:
            hours = seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif seconds >= 60:
            minutes = seconds // 60
            return f"{minutes} min ago"
        else:
            return "Just now"
    except Exception:
        return 'Unknown'


@admin_bp.route('/ledger')
@admin_required
def ledger_dashboard():
    """Render the admin ledger dashboard"""
    from services.ledger_constants import OrderStatus, PayoutStatus

    return render_template(
        'admin/ledger.html',
        order_statuses=OrderStatus.all_values(),
        payout_statuses=PayoutStatus.all_values()
    )


@admin_bp.route('/ledger/order/<int:order_id>')
@admin_required
def ledger_order_detail(order_id):
    """Render the order detail page for the ledger"""
    from services.ledger_service import LedgerService
    from services.ledger_constants import OrderStatus, PayoutStatus
    import json

    ledger_data = LedgerService.get_order_ledger(order_id)

    if not ledger_data:
        return render_template('admin/ledger_order_not_found.html', order_id=order_id), 404

    # Parse event payloads
    for event in ledger_data['events']:
        if event.get('payload_json'):
            try:
                event['payload'] = json.loads(event['payload_json'])
            except json.JSONDecodeError:
                event['payload'] = {}
        else:
            event['payload'] = {}

    return render_template(
        'admin/ledger_order_detail.html',
        order=ledger_data['order'],
        items=ledger_data['items'],
        payouts=ledger_data['payouts'],
        events=ledger_data['events'],
        order_statuses=OrderStatus.all_values(),
        payout_statuses=PayoutStatus.all_values()
    )


@admin_bp.route('/api/ledger/orders')
@admin_required
def get_ledger_orders():
    """
    Get filtered list of ledger orders.

    Query params:
        - status: Filter by order status
        - buyer_id: Filter by buyer ID
        - start_date: Start date filter (ISO format)
        - end_date: End date filter (ISO format)
        - min_gross: Minimum gross amount
        - max_gross: Maximum gross amount
        - limit: Results limit (default 100)
        - offset: Results offset (default 0)
    """
    from services.ledger_service import LedgerService

    try:
        status_filter = request.args.get('status')
        buyer_id = request.args.get('buyer_id', type=int)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        min_gross = request.args.get('min_gross', type=float)
        max_gross = request.args.get('max_gross', type=float)
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)

        orders = LedgerService.get_orders_ledger_list(
            status_filter=status_filter,
            buyer_id=buyer_id,
            start_date=start_date,
            end_date=end_date,
            min_gross=min_gross,
            max_gross=max_gross,
            limit=limit,
            offset=offset
        )

        # Format for response
        for order in orders:
            order['created_at_display'] = _format_time_ago(order.get('created_at', ''))

        return jsonify({
            'success': True,
            'orders': orders,
            'count': len(orders)
        })

    except Exception as e:
        print(f"Error getting ledger orders: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/ledger/order/<int:order_id>')
@admin_required
def get_ledger_order_detail(order_id):
    """Get detailed ledger data for a specific order"""
    from services.ledger_service import LedgerService
    import json

    try:
        ledger_data = LedgerService.get_order_ledger(order_id)

        if not ledger_data:
            return jsonify({'success': False, 'error': 'Order not found in ledger'}), 404

        # Parse event payloads
        for event in ledger_data['events']:
            if event.get('payload_json'):
                try:
                    event['payload'] = json.loads(event['payload_json'])
                except json.JSONDecodeError:
                    event['payload'] = {}
            else:
                event['payload'] = {}

        # Format timestamps
        if ledger_data['order'].get('created_at'):
            ledger_data['order']['created_at_display'] = _format_time_ago(
                ledger_data['order']['created_at']
            )

        return jsonify({
            'success': True,
            'data': ledger_data
        })

    except Exception as e:
        print(f"Error getting ledger order detail: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/ledger/stats')
@admin_required
def get_ledger_stats():
    """Get summary statistics for the ledger dashboard"""
    from database import get_db_connection
    from services.ledger_constants import OrderStatus, PayoutStatus

    conn = get_db_connection()
    try:
        stats = {}

        # Total ledger orders
        result = conn.execute('SELECT COUNT(*) as count FROM orders_ledger').fetchone()
        stats['total_orders'] = result['count']

        # Orders by status
        status_counts = {}
        for status in OrderStatus.all_values():
            result = conn.execute(
                'SELECT COUNT(*) as count FROM orders_ledger WHERE order_status = ?',
                (status,)
            ).fetchone()
            status_counts[status] = result['count']
        stats['orders_by_status'] = status_counts

        # Total gross volume
        result = conn.execute(
            'SELECT COALESCE(SUM(gross_amount), 0) as total FROM orders_ledger'
        ).fetchone()
        stats['total_gross_volume'] = result['total']

        # Total platform fees
        result = conn.execute(
            'SELECT COALESCE(SUM(platform_fee_amount), 0) as total FROM orders_ledger'
        ).fetchone()
        stats['total_platform_fees'] = result['total']

        # Payouts by status
        payout_counts = {}
        for status in PayoutStatus.all_values():
            result = conn.execute(
                'SELECT COUNT(*) as count FROM order_payouts WHERE payout_status = ?',
                (status,)
            ).fetchone()
            payout_counts[status] = result['count']
        stats['payouts_by_status'] = payout_counts

        # Pending payout total
        result = conn.execute('''
            SELECT COALESCE(SUM(seller_net_amount), 0) as total
            FROM order_payouts
            WHERE payout_status IN ('PAYOUT_NOT_READY', 'PAYOUT_READY', 'PAYOUT_SCHEDULED')
        ''').fetchone()
        stats['pending_payout_total'] = result['total']

        return jsonify({
            'success': True,
            'stats': stats
        })

    except Exception as e:
        print(f"Error getting ledger stats: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/ledger/order/<int:order_id>/events')
@admin_required
def get_ledger_order_events(order_id):
    """Get chronological events for an order"""
    from database import get_db_connection
    import json

    conn = get_db_connection()
    try:
        events = conn.execute('''
            SELECT * FROM order_events
            WHERE order_id = ?
            ORDER BY created_at ASC
        ''', (order_id,)).fetchall()

        events_list = []
        for event in events:
            e = dict(event)
            if e.get('payload_json'):
                try:
                    e['payload'] = json.loads(e['payload_json'])
                except json.JSONDecodeError:
                    e['payload'] = {}
            else:
                e['payload'] = {}
            e['created_at_display'] = _format_time_ago(e.get('created_at', ''))
            events_list.append(e)

        return jsonify({
            'success': True,
            'events': events_list
        })

    except Exception as e:
        print(f"Error getting order events: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()
