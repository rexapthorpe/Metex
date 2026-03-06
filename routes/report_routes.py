# routes/report_routes.py
"""
Routes for handling user reports
"""

import os
from flask import Blueprint, request, session, jsonify, send_file, abort
from werkzeug.utils import secure_filename
from datetime import datetime
from database import get_db_connection
from services.notification_service import notify_report_submitted

report_bp = Blueprint('reports', __name__)

# Report attachments are stored OUTSIDE static/ so they are NOT publicly accessible.
# The absolute path is constructed at runtime relative to this file.
_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_ATTACH_DIR = os.path.join(_APP_ROOT, 'data', 'uploads', 'reports')

# Legacy constant kept for reference only — no longer used for new uploads.
UPLOAD_FOLDER = 'static/uploads/reports'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB per file


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def generate_unique_filename(original_filename):
    """Generate a unique filename with timestamp"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    safe_name = secure_filename(original_filename)
    name, ext = os.path.splitext(safe_name)
    return f"{name}_{timestamp}{ext}"


@report_bp.route('/api/reports/create', methods=['POST'])
def create_report():
    """Create a new user report with optional photo attachments"""
    # Check login
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Login required'}), 401

    reporter_id = session['user_id']

    # Get form data
    reported_user_id = request.form.get('reported_user_id')
    order_id = request.form.get('order_id')
    reason = request.form.get('reason', '').strip()
    comment = request.form.get('comment', '').strip()

    # Validate required fields
    if not reported_user_id or not order_id or not reason:
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400

    try:
        reported_user_id = int(reported_user_id)
        order_id = int(order_id)
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid user or order ID'}), 400

    # Cannot report yourself
    if reporter_id == reported_user_id:
        return jsonify({'success': False, 'error': 'You cannot report yourself'}), 400

    # Validate reason
    valid_reasons = [
        'counterfeit_fake',
        'not_as_described',
        'scam_fraud',
        'harassment_abuse',
        'payment_issues',
        'other'
    ]
    if reason not in valid_reasons:
        return jsonify({'success': False, 'error': 'Invalid reason'}), 400

    # Validate comment length
    if len(comment) > 1000:
        return jsonify({'success': False, 'error': 'Comment exceeds 1000 characters'}), 400

    conn = get_db_connection()
    try:
        # Verify reported user exists
        reported_user = conn.execute(
            'SELECT id, username FROM users WHERE id = ?',
            (reported_user_id,)
        ).fetchone()
        if not reported_user:
            return jsonify({'success': False, 'error': 'Reported user not found'}), 404

        # Verify order exists and reporter is involved
        order = conn.execute('''
            SELECT o.id, o.buyer_id
            FROM orders o
            WHERE o.id = ?
        ''', (order_id,)).fetchone()

        if not order:
            return jsonify({'success': False, 'error': 'Order not found'}), 404

        # Check if reporter is involved in this order (as buyer or seller)
        # Get sellers for this order
        sellers = conn.execute('''
            SELECT DISTINCT l.seller_id
            FROM order_items oi
            JOIN listings l ON oi.listing_id = l.id
            WHERE oi.order_id = ?
        ''', (order_id,)).fetchall()
        seller_ids = [s['seller_id'] for s in sellers]

        is_buyer = order['buyer_id'] == reporter_id
        is_seller = reporter_id in seller_ids

        if not is_buyer and not is_seller:
            return jsonify({'success': False, 'error': 'You are not involved in this order'}), 403

        # Verify reported user is counterparty in this order
        if is_buyer:
            # Reporter is buyer, reported must be a seller
            if reported_user_id not in seller_ids:
                return jsonify({'success': False, 'error': 'Reported user is not a seller in this order'}), 400
        else:
            # Reporter is seller, reported must be the buyer
            if reported_user_id != order['buyer_id']:
                return jsonify({'success': False, 'error': 'Reported user is not the buyer in this order'}), 400

        # Check for duplicate report
        existing = conn.execute('''
            SELECT id FROM reports
            WHERE reporter_user_id = ? AND reported_user_id = ? AND order_id = ?
        ''', (reporter_id, reported_user_id, order_id)).fetchone()

        if existing:
            return jsonify({'success': False, 'error': 'You have already reported this user for this order'}), 400

        # Create the report
        cursor = conn.execute('''
            INSERT INTO reports (reporter_user_id, reported_user_id, order_id, reason, comment)
            VALUES (?, ?, ?, ?, ?)
        ''', (reporter_id, reported_user_id, order_id, reason, comment))
        report_id = cursor.lastrowid

        # Handle file uploads — stored OUTSIDE static/ (access-controlled, not publicly served).
        from utils.upload_security import validate_upload, generate_secure_filename
        import secrets as _secrets
        os.makedirs(REPORT_ATTACH_DIR, exist_ok=True)
        uploaded_files = []

        for key in request.files:
            file = request.files[key]
            if not file or not file.filename:
                continue

            # Content-validate (magic bytes + PIL decode)
            validation = validate_upload(
                file,
                allowed_types=['image/png', 'image/jpeg', 'image/webp'],
                category='report_evidence'
            )
            if not validation['valid']:
                continue  # Skip rejected files silently

            # Secure randomised filename, no path prefix stored in DB
            secure_name = generate_secure_filename(file.filename)
            dest_path = os.path.join(REPORT_ATTACH_DIR, secure_name)

            file.seek(0)
            with open(dest_path, 'wb') as fh:
                fh.write(file.read())

            # Store only the filename — full path reconstructed at serve time
            conn.execute('''
                INSERT INTO report_attachments (report_id, file_path, original_filename)
                VALUES (?, ?, ?)
            ''', (report_id, secure_name, file.filename))

            uploaded_files.append(secure_name)

        conn.commit()

        # Auto-hold funds based on report (Phase 2 Escrow Control)
        # HARDENING: Auto-hold failures must be visible and auditable
        hold_result = None
        auto_hold_status = 'pending'
        auto_hold_error = None

        try:
            from services.ledger_service import LedgerService
            hold_result = LedgerService.handle_report_auto_hold(
                report_id=report_id,
                order_id=order_id,
                reported_user_id=reported_user_id,
                reporter_id=reporter_id
            )
            print(f"[REPORT] Auto-hold result for report {report_id}: {hold_result}")

            # Check if auto-hold was actually applied
            if hold_result and hold_result.get('hold_type') is not None:
                auto_hold_status = 'success'
            else:
                # hold_type is None means hold was not applied (e.g., order in terminal state)
                auto_hold_status = 'skipped'
                auto_hold_error = hold_result.get('reason', 'Unknown reason')

        except Exception as e:
            # Don't fail the report creation if auto-hold fails, but LOG IT
            import traceback
            auto_hold_status = 'failed'
            auto_hold_error = str(e)
            stack_trace = traceback.format_exc()
            print(f"[REPORT WARNING] Auto-hold failed for report {report_id}: {e}")

            # Log AUTO_HOLD_FAILED event for auditability
            try:
                from services.ledger_service import LedgerService
                from services.ledger_constants import EventType, ActorType
                LedgerService.log_order_event(
                    order_id=order_id,
                    event_type=EventType.AUTO_HOLD_FAILED.value,
                    actor_type=ActorType.SYSTEM.value,
                    actor_id=None,
                    payload={
                        'report_id': report_id,
                        'reported_user_id': reported_user_id,
                        'reporter_id': reporter_id,
                        'error': str(e),
                        'stack_context': stack_trace[:500] if stack_trace else None
                    }
                )
            except Exception as log_error:
                print(f"[REPORT CRITICAL] Failed to log AUTO_HOLD_FAILED event: {log_error}")

        # Send notification to the reporter confirming their report was submitted
        try:
            notify_report_submitted(
                reporter_id=reporter_id,
                reported_username=reported_user['username'],
                report_id=report_id
            )
        except Exception as e:
            print(f"[NOTIFICATION ERROR] Failed to send report_submitted notification: {e}")

        return jsonify({
            'success': True,
            'message': 'Report submitted successfully',
            'report_id': report_id,
            'files_uploaded': len(uploaded_files),
            'escrow_hold': hold_result,
            'auto_hold_status': auto_hold_status,
            'auto_hold_error': auto_hold_error
        })

    except Exception as e:
        print(f"Error creating report: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@report_bp.route('/api/reports/my-reports')
def get_my_reports():
    """Get reports filed by the current user"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Login required'}), 401

    user_id = session['user_id']
    status_filter = request.args.get('status', 'all')

    conn = get_db_connection()
    try:
        # Build query based on filter
        query = '''
            SELECT
                r.id,
                r.reported_user_id,
                r.order_id,
                r.reason,
                r.comment,
                r.status,
                r.resolution_note,
                r.created_at,
                r.resolved_at,
                u.username as reported_username,
                (SELECT COUNT(*) FROM report_attachments WHERE report_id = r.id) as photo_count
            FROM reports r
            JOIN users u ON r.reported_user_id = u.id
            WHERE r.reporter_user_id = ?
        '''

        params = [user_id]

        if status_filter == 'active':
            query += " AND r.status IN ('open', 'under_investigation', 'pending_review')"
        elif status_filter == 'resolved':
            query += " AND r.status = 'resolved'"
        elif status_filter == 'dismissed':
            query += " AND r.status = 'dismissed'"

        query += ' ORDER BY r.created_at DESC'

        reports = conn.execute(query, params).fetchall()

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

            # Map status to display text
            status_map = {
                'open': 'Under Investigation',
                'under_investigation': 'Under Investigation',
                'pending_review': 'Pending Review',
                'resolved': 'Resolved',
                'dismissed': 'Dismissed'
            }

            # Format order ID
            order_id_formatted = f"ORD-{r['created_at'][:4]}-{r['order_id']:06d}" if r['created_at'] else f"ORD-{r['order_id']:06d}"

            reports_list.append({
                'id': r['id'],
                'reported_username': r['reported_username'],
                'reported_user_id': r['reported_user_id'],
                'order_id': r['order_id'],
                'order_id_formatted': order_id_formatted,
                'reason': r['reason'],
                'reason_display': reason_map.get(r['reason'], r['reason']),
                'comment': r['comment'],
                'status': r['status'],
                'status_display': status_map.get(r['status'], r['status']),
                'resolution_note': r['resolution_note'],
                'photo_count': r['photo_count'],
                'created_at': r['created_at'],
                'resolved_at': r['resolved_at']
            })

        # Count stats
        total = len(reports_list)
        active = sum(1 for r in reports_list if r['status'] in ('open', 'under_investigation', 'pending_review'))

        return jsonify({
            'success': True,
            'reports': reports_list,
            'total': total,
            'active': active
        })

    except Exception as e:
        print(f"Error getting reports: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@report_bp.route('/api/reports/check')
def check_report_exists():
    """Check if the current user has already reported a user for a specific order"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Login required'}), 401

    user_id = session['user_id']
    reported_user_id = request.args.get('reported_user_id')
    order_id = request.args.get('order_id')

    if not reported_user_id or not order_id:
        return jsonify({'success': False, 'error': 'Missing required parameters'}), 400

    try:
        reported_user_id = int(reported_user_id)
        order_id = int(order_id)
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid parameters'}), 400

    conn = get_db_connection()
    try:
        # Check if report exists
        existing = conn.execute('''
            SELECT id, status, created_at FROM reports
            WHERE reporter_user_id = ? AND reported_user_id = ? AND order_id = ?
        ''', (user_id, reported_user_id, order_id)).fetchone()

        if existing:
            return jsonify({
                'success': True,
                'has_reported': True,
                'report_id': existing['id'],
                'status': existing['status'],
                'created_at': existing['created_at']
            })
        else:
            return jsonify({
                'success': True,
                'has_reported': False
            })

    except Exception as e:
        print(f"Error checking report: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@report_bp.route('/api/reports/<int:report_id>')
def get_report_details(report_id):
    """Get details of a specific report (for the reporter)"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Login required'}), 401

    user_id = session['user_id']

    conn = get_db_connection()
    try:
        # Get report (only if user is reporter)
        report = conn.execute('''
            SELECT
                r.*,
                reporter.username as reporter_username,
                reported.username as reported_username
            FROM reports r
            JOIN users reporter ON r.reporter_user_id = reporter.id
            JOIN users reported ON r.reported_user_id = reported.id
            WHERE r.id = ? AND r.reporter_user_id = ?
        ''', (report_id, user_id)).fetchone()

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
            # Return a secure serve URL, not the raw filesystem path
            'url': f'/api/reports/{report_id}/attachments/{a["id"]}',
            'original_filename': a['original_filename'],
            'created_at': a['created_at']
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
            'open': 'Under Investigation',
            'under_investigation': 'Under Investigation',
            'pending_review': 'Pending Review',
            'resolved': 'Resolved',
            'dismissed': 'Dismissed'
        }

        order_id_formatted = f"ORD-{report['created_at'][:4]}-{report['order_id']:06d}" if report['created_at'] else f"ORD-{report['order_id']:06d}"

        return jsonify({
            'success': True,
            'report': {
                'id': report['id'],
                'reporter_username': report['reporter_username'],
                'reported_username': report['reported_username'],
                'reported_user_id': report['reported_user_id'],
                'order_id': report['order_id'],
                'order_id_formatted': order_id_formatted,
                'reason': report['reason'],
                'reason_display': reason_map.get(report['reason'], report['reason']),
                'comment': report['comment'],
                'status': report['status'],
                'status_display': status_map.get(report['status'], report['status']),
                'resolution_note': report['resolution_note'],
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


@report_bp.route('/api/reports/<int:report_id>/attachments/<int:attachment_id>')
def serve_report_attachment(report_id, attachment_id):
    """
    Serve a report attachment — access-controlled.

    Only the reporter or an admin may retrieve the file.
    Files live in data/uploads/reports/ which is NOT under static/ and
    therefore NOT publicly accessible by Flask's static file handler.
    """
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Login required'}), 401

    user_id = session['user_id']
    conn = get_db_connection()
    try:
        # Fetch the attachment and its parent report in one query
        row = conn.execute('''
            SELECT ra.file_path, ra.original_filename,
                   r.reporter_user_id
            FROM report_attachments ra
            JOIN reports r ON ra.report_id = r.id
            WHERE ra.id = ? AND ra.report_id = ?
        ''', (attachment_id, report_id)).fetchone()

        if not row:
            return jsonify({'success': False, 'error': 'Attachment not found'}), 404

        # Check authorisation: reporter or admin
        is_reporter = row['reporter_user_id'] == user_id
        if not is_reporter:
            admin_row = conn.execute('SELECT is_admin FROM users WHERE id = ?', (user_id,)).fetchone()
            if not admin_row or not admin_row['is_admin']:
                return jsonify({'success': False, 'error': 'Not authorized'}), 403

        # Resolve filesystem path — file_path is just the filename (no directory)
        filename = os.path.basename(row['file_path'])  # defence-in-depth: strip any path components
        full_path = os.path.join(REPORT_ATTACH_DIR, filename)

        if not os.path.exists(full_path):
            return jsonify({'success': False, 'error': 'File not found'}), 404

        return send_file(
            full_path,
            as_attachment=False,
            download_name=row['original_filename'] or filename
        )

    except Exception as e:
        print(f"Error serving report attachment: {e}")
        return jsonify({'success': False, 'error': 'Could not serve file'}), 500
    finally:
        conn.close()
