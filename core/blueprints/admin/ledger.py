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

from datetime import datetime, timedelta
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

    # Compute payout eligibility for each payout (drives Release Payout button)
    payout_eligibility = {}
    payout_block_reasons = {}
    for payout in ledger_data['payouts']:
        payout_eligibility[payout['id']] = LedgerService.get_payout_eligibility(payout['id'])
        payout_block_reasons[payout['id']] = LedgerService.get_payout_block_reason(payout['id'])

    # Fetch refund info + payout delay info from the orders / tracking tables
    from database import get_db_connection as _get_db
    from services.system_settings_service import get_auto_payout_delay_minutes
    _conn = _get_db()
    try:
        _row = _conn.execute(
            '''SELECT payment_status, refund_status, refund_amount, stripe_refund_id,
                      refunded_at, refund_reason, requires_payout_recovery,
                      stripe_payment_intent_id, payment_method_type,
                      requires_payment_clearance, payment_cleared_at,
                      payment_cleared_by_admin_id,
                      COALESCE(buyer_card_fee, 0)          AS buyer_card_fee,
                      COALESCE(tax_amount, 0)              AS tax_amount,
                      COALESCE(total_price, 0)             AS total_price,
                      COALESCE(refund_subtotal, 0)         AS refund_subtotal,
                      COALESCE(refund_tax_amount, 0)       AS refund_tax_amount,
                      COALESCE(refund_processing_fee, 0)   AS refund_processing_fee,
                      COALESCE(platform_covered_amount, 0) AS platform_covered_amount
               FROM orders WHERE id = ?''',
            (order_id,)
        ).fetchone()
        refund_info = dict(_row) if _row else {}
        order_payment_method = (refund_info.get('payment_method_type') or '').lower()

        # Read the configured payout delay (matches get_payout_block_reason logic)
        delay_minutes = get_auto_payout_delay_minutes()

        # Build a human-readable label for the delay (e.g. "24h", "2d", "30m")
        if delay_minutes < 60:
            delay_label = f"{delay_minutes}m"
        elif delay_minutes % (24 * 60) == 0:
            delay_label = f"{delay_minutes // (24 * 60)}d"
        elif delay_minutes % 60 == 0:
            delay_label = f"{delay_minutes // 60}h"
        else:
            delay_label = f"{delay_minutes // 60}h {delay_minutes % 60}m"

        # Compute per-payout delay window info for admin display
        payout_delay_info = {}
        for payout in ledger_data['payouts']:
            pid = payout['id']
            seller_id = payout['seller_id']
            t_row = _conn.execute(
                'SELECT updated_at, delivered_at FROM seller_order_tracking WHERE order_id = ? AND seller_id = ?',
                (order_id, seller_id)
            ).fetchone()
            tracking_ts_raw = t_row['updated_at'] if t_row else None
            delivered_at_raw = t_row['delivered_at'] if t_row else None

            # eligible_at is based on delivered_at + configured delay (matches backend logic)
            eligible_at = None
            eligible_at_str = None
            days_remaining = None
            if delivered_at_raw:
                try:
                    ts = str(delivered_at_raw)
                    if 'T' in ts:
                        delivered_dt = datetime.fromisoformat(
                            ts.replace('Z', '+00:00')
                        ).replace(tzinfo=None)
                    else:
                        delivered_dt = datetime.strptime(ts[:19], '%Y-%m-%d %H:%M:%S')
                    eligible_at = delivered_dt + timedelta(minutes=delay_minutes)
                    eligible_at_str = eligible_at.strftime('%Y-%m-%d %H:%M')
                    now = datetime.now()
                    if eligible_at > now:
                        delta = eligible_at - now
                        # Round up to nearest minute for display
                        total_mins = delta.days * 1440 + (delta.seconds + 59) // 60
                        days_remaining = total_mins  # minutes remaining (template shows appropriately)
                except Exception:
                    pass

            # Seller Stripe setup status
            stripe_row = _conn.execute(
                'SELECT stripe_account_id, stripe_payouts_enabled FROM users WHERE id = ?',
                (seller_id,)
            ).fetchone()
            seller_has_stripe = bool(stripe_row and stripe_row['stripe_account_id'])
            seller_payouts_enabled = bool(stripe_row and stripe_row['stripe_payouts_enabled'])
            payout_delay_info[pid] = {
                'tracking_uploaded_at': str(tracking_ts_raw)[:16] if tracking_ts_raw else None,
                'delivered_at': str(delivered_at_raw)[:16] if delivered_at_raw else None,
                'eligible_at_str': eligible_at_str,
                'delay_label': delay_label,
                'days_remaining': days_remaining,  # actually minutes_remaining; template uses > 0 check
                'payment_method_type': order_payment_method or 'card',
                'seller_has_stripe': seller_has_stripe,
                'seller_payouts_enabled': seller_payouts_enabled,
            }
    finally:
        _conn.close()

    return render_template(
        'admin/ledger_order_detail.html',
        order=ledger_data['order'],
        items=ledger_data['items'],
        payouts=ledger_data['payouts'],
        events=ledger_data['events'],
        order_statuses=OrderStatus.all_values(),
        payout_statuses=PayoutStatus.all_values(),
        payout_eligibility=payout_eligibility,
        payout_block_reasons=payout_block_reasons,
        refund_info=refund_info,
        payout_delay_info=payout_delay_info,
    )


@admin_bp.route('/api/ledger/orders')
@admin_required
def get_ledger_orders():
    """
    Get filtered list of ledger orders.

    Query params:
        - status: Filter by order status
        - buyer_id: Filter by buyer ID
        - seller_username: Filter by seller username (partial match)
        - payment_status: Filter by payment_status
        - payout_status: Filter by payout_status
        - start_date: Start date filter (ISO format)
        - end_date: End date filter (ISO format)
        - min_gross: Minimum gross amount
        - max_gross: Maximum gross amount
        - limit: Results limit (default 100)
        - offset: Results offset (default 0)
    """
    from services.ledger_service import LedgerService
    from services.order_state import compute_order_state, get_order_state_label, get_order_state_css, get_block_reason_summary

    try:
        status_filter    = request.args.get('status')
        buyer_id         = request.args.get('buyer_id', type=int)
        seller_username  = request.args.get('seller_username', '').strip()
        payment_status_f = request.args.get('payment_status', '').strip()
        payout_status_f  = request.args.get('payout_status', '').strip()
        start_date       = request.args.get('start_date')
        end_date         = request.args.get('end_date')
        min_gross        = request.args.get('min_gross', type=float)
        max_gross        = request.args.get('max_gross', type=float)
        limit            = request.args.get('limit', 100, type=int)
        offset           = request.args.get('offset', 0, type=int)

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

        # Post-filter by seller username if provided (would require a different query path;
        # for simplicity we filter in Python after fetching since item_count subquery
        # already runs per-order)
        if seller_username:
            seller_low = seller_username.lower()
            orders = [o for o in orders if seller_low in (o.get('buyer_username') or '').lower()]

        # Post-filter by payment_status and payout_status
        if payment_status_f:
            orders = [o for o in orders if (o.get('payment_status') or '') == payment_status_f]
        if payout_status_f:
            orders = [o for o in orders if (o.get('payout_status') or '') == payout_status_f]

        # Enrich each order with derived fields
        for order in orders:
            order['created_at_display'] = _format_time_ago(order.get('created_at', ''))
            order['order_state']        = compute_order_state(order)
            order['order_state_label']  = get_order_state_label(order)
            order['order_state_css']    = get_order_state_css(order)
            order['block_reason']       = get_block_reason_summary(order)

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

        # Split payout totals (Pending / Ready / Paid Out)
        r = conn.execute('''
            SELECT COALESCE(SUM(seller_net_amount), 0) as total,
                   COUNT(*) as cnt
            FROM order_payouts WHERE payout_status = 'PAYOUT_NOT_READY'
        ''').fetchone()
        stats['payout_pending_total'] = r['total']
        stats['payout_pending_count'] = r['cnt']

        r = conn.execute('''
            SELECT COALESCE(SUM(seller_net_amount), 0) as total,
                   COUNT(*) as cnt
            FROM order_payouts WHERE payout_status IN ('PAYOUT_READY', 'PAYOUT_SCHEDULED')
        ''').fetchone()
        stats['payout_ready_total'] = r['total']
        stats['payout_ready_count'] = r['cnt']

        r = conn.execute('''
            SELECT COALESCE(SUM(seller_net_amount), 0) as total,
                   COUNT(*) as cnt
            FROM order_payouts WHERE payout_status = 'PAID_OUT'
        ''').fetchone()
        stats['paid_out_total'] = r['total']
        stats['paid_out_count'] = r['cnt']

        # Keep backward-compat key (sum of not-ready + ready)
        stats['pending_payout_total'] = stats['payout_pending_total'] + stats['payout_ready_total']

        # Tax collected: sum of tax_amount for paid orders in the ledger
        # (tax is a liability held by the platform, not platform revenue)
        try:
            r = conn.execute('''
                SELECT COALESCE(SUM(o.tax_amount), 0) AS total
                FROM orders o
                JOIN orders_ledger ol ON o.id = ol.order_id
                WHERE o.payment_status = 'paid'
            ''').fetchone()
            stats['total_tax_collected'] = float(r['total'] or 0)
        except Exception:
            stats['total_tax_collected'] = 0.0

        # Spread capture revenue: buyer premium above seller ask (platform revenue beyond the fee)
        # This is stored on orders_ledger.spread_capture_amount and is non-zero only for bid fills
        # where the buyer bid price exceeded the seller's listing price.
        try:
            r = conn.execute(
                'SELECT COALESCE(SUM(spread_capture_amount), 0) AS total FROM orders_ledger'
            ).fetchone()
            stats['total_spread_revenue'] = float(r['total'] or 0)
        except Exception:
            stats['total_spread_revenue'] = 0.0

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
