"""
Admin Reports/Disputes Routes

This module contains reports and disputes management routes for the admin panel.

IMPORTANT NOTE: The original admin_routes.py had DUPLICATE route definitions:
- /api/reports was defined at line 1715 (get_all_reports) AND line 3077 (admin_get_reports)
- /api/reports/<report_id> was defined at line 1821 (get_report_details_admin) AND line 3150 (admin_get_report_detail)

Flask uses "last wins" for duplicate routes, so the later definitions (admin_get_reports and
admin_get_report_detail) are the ones that actually serve those endpoints.

To preserve this exact behavior, we define the v1 routes first, then v2 routes later.
The v2 routes will override v1 (as in the original file).

Routes:
- /api/reports - Get all reports (v2 version - paginated)
- /api/reports/<report_id> - Get report details (v2 version)
- /api/reports/<report_id>/status - Update report status
- /api/reports/<report_id>/resolve - Resolve report with action
- /api/reports/<report_id>/halt-funds - Halt funds (placeholder)
- /api/reports/<report_id>/refund - Refund buyer (placeholder)
- /api/user/<user_id>/stats - Get user stats for modal

IMPORTANT: All route URLs and endpoint names are preserved from original admin_routes.py
"""

from flask import jsonify, request, session
from utils.auth_utils import admin_required
from . import admin_bp
from .dashboard import _format_time_ago


# ==========================================================================
# REPORTS V1 ROUTES (lines 1715-2094 in original)
# These are defined first, will be overridden by V2 routes with same URL
# ==========================================================================

@admin_bp.route('/api/reports')
@admin_required
def get_all_reports():
    """Get all reports for the admin disputes tab"""
    from database import get_db_connection

    status_filter = request.args.get('status', 'all')

    conn = get_db_connection()
    try:
        query = '''
            SELECT
                r.id,
                r.reporter_user_id,
                r.reported_user_id,
                r.order_id,
                r.reason,
                r.comment,
                r.status,
                r.resolution_note,
                r.admin_notes,
                r.created_at,
                r.resolved_at,
                reporter.username as reporter_username,
                reported.username as reported_username,
                o.total_price as order_amount,
                (SELECT COUNT(*) FROM report_attachments WHERE report_id = r.id) as photo_count
            FROM reports r
            JOIN users reporter ON r.reporter_user_id = reporter.id
            JOIN users reported ON r.reported_user_id = reported.id
            LEFT JOIN orders o ON r.order_id = o.id
        '''

        if status_filter == 'open':
            query += " WHERE r.status IN ('open', 'under_investigation', 'pending_review')"
        elif status_filter == 'resolved':
            query += " WHERE r.status = 'resolved'"
        elif status_filter == 'dismissed':
            query += " WHERE r.status = 'dismissed'"

        query += ' ORDER BY r.created_at DESC'

        reports = conn.execute(query).fetchall()

        # Count stats
        stats = {
            'open': conn.execute("SELECT COUNT(*) as c FROM reports WHERE status IN ('open', 'under_investigation', 'pending_review')").fetchone()['c'],
            'resolved_today': conn.execute("SELECT COUNT(*) as c FROM reports WHERE status = 'resolved' AND date(resolved_at) = date('now')").fetchone()['c'],
            'total': conn.execute("SELECT COUNT(*) as c FROM reports").fetchone()['c']
        }

        # Format reports
        reports_list = []
        for r in reports:
            # Map reason to display text
            reason_map = {
                'counterfeit_fake': 'Counterfeit/Fake Items',
                'not_as_described': 'Item Not as Described',
                'scam_fraud': 'Scam/Fraud',
                'harassment_abuse': 'Harassment/Abuse',
                'payment_issues': 'Payment Issues',
                'other': 'Other'
            }

            status_map = {
                'open': 'Investigating',
                'under_investigation': 'Investigating',
                'pending_review': 'Pending Review',
                'resolved': 'Resolved',
                'dismissed': 'Dismissed'
            }

            reports_list.append({
                'id': r['id'],
                'reporter_user_id': r['reporter_user_id'],
                'reporter_username': r['reporter_username'],
                'reported_user_id': r['reported_user_id'],
                'reported_username': r['reported_username'],
                'order_id': r['order_id'],
                'order_amount': r['order_amount'] or 0,
                'reason': r['reason'],
                'reason_display': reason_map.get(r['reason'], r['reason']),
                'comment': r['comment'],
                'status': r['status'],
                'status_display': status_map.get(r['status'], r['status']),
                'resolution_note': r['resolution_note'],
                'admin_notes': r['admin_notes'],
                'photo_count': r['photo_count'],
                'created_at': r['created_at'],
                'resolved_at': r['resolved_at'],
                'time_ago': _format_time_ago(r['created_at'])
            })

        return jsonify({
            'success': True,
            'reports': reports_list,
            'stats': stats
        })

    except Exception as e:
        print(f"Error getting reports: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/reports/<int:report_id>')
@admin_required
def get_report_details_admin(report_id):
    """Get detailed information about a report for admin"""
    from database import get_db_connection

    conn = get_db_connection()
    try:
        report = conn.execute('''
            SELECT
                r.*,
                reporter.username as reporter_username,
                reporter.email as reporter_email,
                reported.username as reported_username,
                reported.email as reported_email,
                o.total_price as order_amount,
                o.status as order_status,
                o.created_at as order_created_at
            FROM reports r
            JOIN users reporter ON r.reporter_user_id = reporter.id
            JOIN users reported ON r.reported_user_id = reported.id
            LEFT JOIN orders o ON r.order_id = o.id
            WHERE r.id = ?
        ''', (report_id,)).fetchone()

        if not report:
            return jsonify({'success': False, 'error': 'Report not found'}), 404

        # Get attachments
        attachments = conn.execute('''
            SELECT id, file_path, original_filename, created_at
            FROM report_attachments
            WHERE report_id = ?
        ''', (report_id,)).fetchall()

        attachments_list = [{
            'id': a['id'],
            'url': f'/api/reports/{report_id}/attachments/{a["id"]}',
            'original_filename': a['original_filename']
        } for a in attachments]

        # Map reason and status
        reason_map = {
            'counterfeit_fake': 'Counterfeit/Fake Items',
            'not_as_described': 'Item Not as Described',
            'scam_fraud': 'Scam/Fraud',
            'harassment_abuse': 'Harassment/Abuse',
            'payment_issues': 'Payment Issues',
            'other': 'Other'
        }

        status_map = {
            'open': 'Investigating',
            'under_investigation': 'Investigating',
            'pending_review': 'Pending Review',
            'resolved': 'Resolved',
            'dismissed': 'Dismissed'
        }

        return jsonify({
            'success': True,
            'report': {
                'id': report['id'],
                'reporter_user_id': report['reporter_user_id'],
                'reporter_username': report['reporter_username'],
                'reporter_email': report['reporter_email'],
                'reported_user_id': report['reported_user_id'],
                'reported_username': report['reported_username'],
                'reported_email': report['reported_email'],
                'order_id': report['order_id'],
                'order_amount': report['order_amount'],
                'order_status': report['order_status'],
                'reason': report['reason'],
                'reason_display': reason_map.get(report['reason'], report['reason']),
                'comment': report['comment'],
                'status': report['status'],
                'status_display': status_map.get(report['status'], report['status']),
                'resolution_note': report['resolution_note'],
                'admin_notes': report['admin_notes'],
                'created_at': report['created_at'],
                'resolved_at': report['resolved_at'],
                'attachments': attachments_list
            }
        })

    except Exception as e:
        print(f"Error getting report details: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/reports/<int:report_id>/status', methods=['POST'])
@admin_required
def update_report_status(report_id):
    """Update the status of a report"""
    from database import get_db_connection

    data = request.get_json() or {}
    new_status = data.get('status')
    resolution_note = data.get('resolution_note', '').strip()
    admin_notes = data.get('admin_notes', '').strip()

    valid_statuses = ['open', 'under_investigation', 'pending_review', 'resolved', 'dismissed']
    if new_status not in valid_statuses:
        return jsonify({'success': False, 'error': 'Invalid status'}), 400

    conn = get_db_connection()
    try:
        # Check report exists
        report = conn.execute('SELECT id, status FROM reports WHERE id = ?', (report_id,)).fetchone()
        if not report:
            return jsonify({'success': False, 'error': 'Report not found'}), 404

        # Update report
        admin_id = session.get('user_id')
        resolved_at = 'CURRENT_TIMESTAMP' if new_status in ('resolved', 'dismissed') else None

        if resolved_at:
            conn.execute('''
                UPDATE reports
                SET status = ?, resolution_note = ?, admin_notes = ?,
                    resolved_at = CURRENT_TIMESTAMP, resolved_by = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (new_status, resolution_note, admin_notes, admin_id, report_id))
        else:
            conn.execute('''
                UPDATE reports
                SET status = ?, admin_notes = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (new_status, admin_notes, report_id))

        conn.commit()

        return jsonify({
            'success': True,
            'message': f'Report status updated to {new_status}'
        })

    except Exception as e:
        print(f"Error updating report status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/user/<int:user_id>/stats')
@admin_required
def get_user_stats(user_id):
    """Get comprehensive stats for a user (for the User Stats modal)"""
    from database import get_db_connection

    conn = get_db_connection()
    try:
        # Get user info
        user = conn.execute('''
            SELECT id, username, email, created_at, is_admin, is_banned, is_frozen
            FROM users WHERE id = ?
        ''', (user_id,)).fetchone()

        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        # Reports filed
        reports_filed = conn.execute(
            'SELECT COUNT(*) as c FROM reports WHERE reporter_user_id = ?',
            (user_id,)
        ).fetchone()['c']

        # Reports received
        reports_received = conn.execute(
            'SELECT COUNT(*) as c FROM reports WHERE reported_user_id = ?',
            (user_id,)
        ).fetchone()['c']

        # Rating stats
        rating = conn.execute('''
            SELECT AVG(rating) as avg_rating, COUNT(*) as count
            FROM ratings WHERE ratee_id = ?
        ''', (user_id,)).fetchone()

        # Listings stats
        active_listings = conn.execute(
            'SELECT COUNT(*) as c FROM listings WHERE seller_id = ? AND active = 1 AND quantity > 0',
            (user_id,)
        ).fetchone()['c']

        total_listings = conn.execute(
            'SELECT COUNT(*) as c FROM listings WHERE seller_id = ?',
            (user_id,)
        ).fetchone()['c']

        # Orders as buyer
        orders_as_buyer = conn.execute(
            'SELECT COUNT(*) as c FROM orders WHERE buyer_id = ?',
            (user_id,)
        ).fetchone()['c']

        # Sales as seller
        sales_as_seller = conn.execute('''
            SELECT COUNT(DISTINCT o.id) as c
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            JOIN listings l ON oi.listing_id = l.id
            WHERE l.seller_id = ?
        ''', (user_id,)).fetchone()['c']

        # Total volume (buy + sell)
        buy_volume = conn.execute(
            'SELECT COALESCE(SUM(total_price), 0) as total FROM orders WHERE buyer_id = ?',
            (user_id,)
        ).fetchone()['total']

        sell_volume = conn.execute('''
            SELECT COALESCE(SUM(oi.quantity * oi.price_each), 0) as total
            FROM order_items oi
            JOIN listings l ON oi.listing_id = l.id
            WHERE l.seller_id = ?
        ''', (user_id,)).fetchone()['total']

        return jsonify({
            'success': True,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'email': user['email'],
                'created_at': user['created_at'],
                'member_since': _format_time_ago(user['created_at']),
                'is_admin': user['is_admin'],
                'is_banned': user['is_banned'],
                'is_frozen': user['is_frozen'],
                'stats': {
                    'reports_filed': reports_filed,
                    'reports_received': reports_received,
                    'rating_avg': round(rating['avg_rating'], 1) if rating['avg_rating'] else 0,
                    'rating_count': rating['count'],
                    'active_listings': active_listings,
                    'total_listings': total_listings,
                    'orders_as_buyer': orders_as_buyer,
                    'sales_as_seller': sales_as_seller,
                    'buy_volume': buy_volume,
                    'sell_volume': sell_volume,
                    'total_volume': buy_volume + sell_volume
                }
            }
        })

    except Exception as e:
        print(f"Error getting user stats: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/reports/<int:report_id>/halt-funds', methods=['POST'])
@admin_required
def halt_funds(report_id):
    """Placeholder for halting funds - not implemented yet"""
    return jsonify({
        'success': False,
        'error': 'Not implemented yet',
        'message': 'Funds halting functionality is not yet implemented. This will be available in a future update.'
    }), 501


@admin_bp.route('/api/reports/<int:report_id>/refund', methods=['POST'])
@admin_required
def refund_buyer(report_id):
    """Placeholder for refunding buyer - not implemented yet"""
    return jsonify({
        'success': False,
        'error': 'Not implemented yet',
        'message': 'Refund functionality is not yet implemented. This will be available in a future update.'
    }), 501


# ==========================================================================
# REPORTS V2 ROUTES (lines 3077-3380 in original)
# These are defined AFTER v1 routes, so they override the duplicate URLs
# This preserves the original Flask behavior (last registration wins)
# ==========================================================================

@admin_bp.route('/api/reports')
@admin_required
def admin_get_reports():
    """
    Get paginated list of reports for admin review.

    Query params:
    - status: Filter by report status
    - page: Page number (default 1)
    - per_page: Items per page (default 20)
    """
    from database import get_db_connection

    status_filter = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page

    conn = get_db_connection()
    try:
        query = '''
            SELECT
                r.*,
                reporter.username as reporter_username,
                reported.username as reported_username,
                ol.order_status as ledger_order_status,
                (SELECT COUNT(*) FROM report_attachments WHERE report_id = r.id) as attachment_count,
                (SELECT COUNT(*) FROM order_payouts
                 WHERE order_id = r.order_id AND payout_status = 'PAYOUT_ON_HOLD') as held_payouts,
                (SELECT COUNT(*) FROM order_events
                 WHERE order_id = r.order_id AND event_type = 'AUTO_HOLD_FAILED'
                 AND payload_json LIKE '%"report_id": ' || r.id || '%') as auto_hold_failed
            FROM reports r
            JOIN users reporter ON r.reporter_user_id = reporter.id
            JOIN users reported ON r.reported_user_id = reported.id
            LEFT JOIN orders_ledger ol ON r.order_id = ol.order_id
            WHERE 1=1
        '''
        params = []

        if status_filter:
            query += ' AND r.status = ?'
            params.append(status_filter)

        query += ' ORDER BY r.created_at DESC LIMIT ? OFFSET ?'
        params.extend([per_page, offset])

        reports = conn.execute(query, params).fetchall()

        # Get total count
        count_query = 'SELECT COUNT(*) as count FROM reports'
        if status_filter:
            count_query += ' WHERE status = ?'
            total = conn.execute(count_query, [status_filter] if status_filter else []).fetchone()['count']
        else:
            total = conn.execute(count_query).fetchone()['count']

        return jsonify({
            'success': True,
            'reports': [dict(r) for r in reports],
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page
        })

    except Exception as e:
        print(f"Error getting reports: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/reports/<int:report_id>')
@admin_required
def admin_get_report_detail(report_id):
    """Get detailed report information for admin review"""
    from database import get_db_connection
    import json

    conn = get_db_connection()
    try:
        # Get report with user info
        report = conn.execute('''
            SELECT
                r.*,
                reporter.username as reporter_username,
                reported.username as reported_username,
                o.buyer_id,
                ol.order_status as ledger_order_status,
                ol.gross_amount,
                ol.platform_fee_amount
            FROM reports r
            JOIN users reporter ON r.reporter_user_id = reporter.id
            JOIN users reported ON r.reported_user_id = reported.id
            JOIN orders o ON r.order_id = o.id
            LEFT JOIN orders_ledger ol ON r.order_id = ol.order_id
            WHERE r.id = ?
        ''', (report_id,)).fetchone()

        if not report:
            return jsonify({'success': False, 'error': 'Report not found'}), 404

        report_data = dict(report)

        # Determine if reported is buyer or seller
        report_data['reported_is_buyer'] = report['reported_user_id'] == report['buyer_id']

        # Get attachments — return secure serve URLs, not raw filesystem paths
        attachments = conn.execute('''
            SELECT id, original_filename, created_at FROM report_attachments WHERE report_id = ?
        ''', (report_id,)).fetchall()
        report_data['attachments'] = [
            {
                'id': a['id'],
                'url': f'/api/reports/{report_id}/attachments/{a["id"]}',
                'original_filename': a['original_filename'],
                'created_at': a['created_at'],
            }
            for a in attachments
        ]

        # Get order payouts status
        payouts = conn.execute('''
            SELECT op.*, u.username as seller_username
            FROM order_payouts op
            JOIN users u ON op.seller_id = u.id
            WHERE op.order_id = ?
        ''', (report['order_id'],)).fetchall()
        report_data['payouts'] = [dict(p) for p in payouts]

        # Get related events (including AUTO_HOLD_FAILED for visibility)
        events = conn.execute('''
            SELECT * FROM order_events
            WHERE order_id = ? AND event_type IN (
                'ORDER_HELD', 'ORDER_APPROVED', 'PAYOUT_HELD', 'PAYOUT_RELEASED',
                'REPORT_CREATED', 'AUTO_HOLD_FAILED'
            )
            ORDER BY created_at DESC
            LIMIT 20
        ''', (report['order_id'],)).fetchall()

        events_list = []
        auto_hold_failed_event = None
        report_created_event = None

        for e in events:
            event = dict(e)
            if event.get('payload_json'):
                try:
                    event['payload'] = json.loads(event['payload_json'])
                except json.JSONDecodeError:
                    event['payload'] = {}

                # Check if this AUTO_HOLD_FAILED event is for this specific report
                if event['event_type'] == 'AUTO_HOLD_FAILED':
                    payload = event.get('payload', {})
                    if payload.get('report_id') == report_id:
                        auto_hold_failed_event = event

                # Check for REPORT_CREATED event for this report
                if event['event_type'] == 'REPORT_CREATED':
                    payload = event.get('payload', {})
                    if payload.get('report_id') == report_id:
                        report_created_event = event

            events_list.append(event)

        report_data['related_events'] = events_list

        # Determine auto_hold_status based on events
        if auto_hold_failed_event:
            report_data['auto_hold_status'] = 'failed'
            report_data['auto_hold_error'] = auto_hold_failed_event.get('payload', {}).get('error')
        elif report_created_event:
            payload = report_created_event.get('payload', {})
            if payload.get('auto_hold_applied'):
                report_data['auto_hold_status'] = 'success'
                report_data['auto_hold_type'] = payload.get('hold_type')
            else:
                report_data['auto_hold_status'] = 'skipped'
                report_data['auto_hold_error'] = payload.get('reason')
        else:
            # No events found - report may have been created before Phase 2
            report_data['auto_hold_status'] = 'unknown'

        return jsonify({
            'success': True,
            'report': report_data
        })

    except Exception as e:
        print(f"Error getting report detail: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/reports/<int:report_id>/resolve', methods=['POST'])
@admin_required
def admin_resolve_report(report_id):
    """
    Admin action: Resolve a report with specified action.

    POST /admin/api/reports/<report_id>/resolve
    Body: {
        "resolution": "approve" | "refund_full" | "refund_partial" | "dismiss",
        "resolution_note": "string (required)",
        "seller_id": int (for partial refund),
        "order_item_ids": [int] (for partial refund)
    }
    """
    from database import get_db_connection
    from services.ledger_service import LedgerService, EscrowControlError

    data = request.get_json() or {}
    resolution = data.get('resolution')
    resolution_note = data.get('resolution_note', '').strip()
    seller_id = data.get('seller_id')
    order_item_ids = data.get('order_item_ids')

    valid_resolutions = ['approve', 'refund_full', 'refund_partial', 'dismiss']
    if resolution not in valid_resolutions:
        return jsonify({'success': False, 'error': f'Resolution must be one of: {valid_resolutions}'}), 400

    if not resolution_note:
        return jsonify({'success': False, 'error': 'Resolution note is required'}), 400

    admin_id = session.get('user_id')

    conn = get_db_connection()
    try:
        # Get report
        report = conn.execute('SELECT * FROM reports WHERE id = ?', (report_id,)).fetchone()
        if not report:
            return jsonify({'success': False, 'error': 'Report not found'}), 404

        order_id = report['order_id']
        result = {'resolution': resolution}

        # Execute resolution action
        if resolution == 'approve':
            # Release the order from review
            try:
                LedgerService.approve_order(order_id, admin_id)
                result['action_taken'] = 'Order approved and released'
            except EscrowControlError as e:
                # Order might not be in UNDER_REVIEW - try releasing individual payouts
                result['action_taken'] = f'Could not approve order: {str(e)}'

        elif resolution == 'refund_full':
            refund_result = LedgerService.process_refund(
                order_id=order_id,
                admin_id=admin_id,
                refund_type='full',
                reason=f'Report resolution: {resolution_note}'
            )
            result['refund'] = refund_result
            result['action_taken'] = 'Full refund processed'

        elif resolution == 'refund_partial':
            if not seller_id and not order_item_ids:
                return jsonify({'success': False, 'error': 'Partial refund requires seller_id or order_item_ids'}), 400
            refund_result = LedgerService.process_refund(
                order_id=order_id,
                admin_id=admin_id,
                refund_type='partial',
                reason=f'Report resolution: {resolution_note}',
                seller_id=seller_id,
                order_item_ids=order_item_ids
            )
            result['refund'] = refund_result
            result['action_taken'] = 'Partial refund processed'

        elif resolution == 'dismiss':
            # Just dismiss the report, release any holds
            try:
                LedgerService.approve_order(order_id, admin_id)
                result['action_taken'] = 'Report dismissed, order released'
            except EscrowControlError:
                result['action_taken'] = 'Report dismissed (order was not under review)'

        # Update report status
        new_status = 'resolved' if resolution != 'dismiss' else 'dismissed'
        conn.execute('''
            UPDATE reports
            SET status = ?,
                resolution_note = ?,
                resolved_at = CURRENT_TIMESTAMP,
                resolved_by = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (new_status, resolution_note, admin_id, report_id))

        conn.commit()

        return jsonify({
            'success': True,
            'message': f'Report {report_id} resolved',
            'result': result
        })

    except EscrowControlError as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

    except Exception as e:
        conn.rollback()
        print(f"Error resolving report {report_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()
