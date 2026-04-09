"""
Admin Feedback Routes

Provides API endpoints for the admin Feedback analytics tab.

Routes:
  GET  /admin/api/feedback        — paginated feedback list with filters
  GET  /admin/api/feedback/stats  — aggregate stats + trend data for charts
  GET  /admin/api/feedback/<id>   — single feedback item detail
"""

import logging

import database
from flask import jsonify, request
from utils.auth_utils import admin_required
from . import admin_bp

_log = logging.getLogger(__name__)

_VALID_TYPES = {'issue', 'improvement', 'praise', 'other'}
_TYPE_LABELS = {
    'issue':       'Issue / Bug',
    'improvement': 'Improvement',
    'praise':      'Praise',
    'other':       'Other',
}


@admin_bp.route('/api/feedback/stats', methods=['GET'])
@admin_required
def feedback_stats():
    """Return aggregate stats and 30-day trend data for feedback analytics."""
    conn = database.get_db_connection()
    try:
        # Total count
        total = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE message_type='feedback'"
        ).fetchone()[0]

        # By type
        type_rows = conn.execute(
            """SELECT COALESCE(feedback_type, 'unset') AS ft, COUNT(*) AS cnt
               FROM messages WHERE message_type='feedback'
               GROUP BY ft"""
        ).fetchall()
        by_type = {r['ft']: r['cnt'] for r in type_rows}

        # Last 30 days count
        last_30d = conn.execute(
            """SELECT COUNT(*) FROM messages
               WHERE message_type='feedback'
                 AND timestamp >= DATE('now', '-30 days')"""
        ).fetchone()[0]

        # Previous 30 days count (for trend arrow)
        prev_30d = conn.execute(
            """SELECT COUNT(*) FROM messages
               WHERE message_type='feedback'
                 AND timestamp >= DATE('now', '-60 days')
                 AND timestamp < DATE('now', '-30 days')"""
        ).fetchone()[0]

        # Daily trend for last 30 days
        trend_rows = conn.execute(
            """SELECT DATE(timestamp) AS day, COUNT(*) AS cnt
               FROM messages
               WHERE message_type='feedback'
                 AND timestamp >= DATE('now', '-30 days')
               GROUP BY day
               ORDER BY day"""
        ).fetchall()
        trend_data = [{'date': r['day'], 'count': r['cnt']} for r in trend_rows]

        # Average per week (based on total / weeks since first submission)
        first_row = conn.execute(
            "SELECT MIN(timestamp) AS first FROM messages WHERE message_type='feedback'"
        ).fetchone()
        avg_per_week = None
        if first_row and first_row['first'] and total > 0:
            try:
                from datetime import datetime
                first_dt = datetime.fromisoformat(str(first_row['first']))
                now_dt = datetime.utcnow()
                weeks = max((now_dt - first_dt).days / 7.0, 1.0)
                avg_per_week = round(total / weeks, 1)
            except Exception:
                pass

        return jsonify({
            'success': True,
            'total': total,
            'by_type': {
                'issue':       by_type.get('issue', 0),
                'improvement': by_type.get('improvement', 0),
                'praise':      by_type.get('praise', 0),
                'other':       by_type.get('other', 0),
                'unset':       by_type.get('unset', 0),
            },
            'last_30d': last_30d,
            'prev_30d': prev_30d,
            'avg_per_week': avg_per_week,
            'trend_data': trend_data,
        })
    except Exception as exc:
        _log.exception('feedback_stats error')
        return jsonify({'success': False, 'error': str(exc)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/feedback', methods=['GET'])
@admin_required
def list_feedback():
    """Return paginated feedback list, filterable by type/date/user."""
    feedback_type = request.args.get('type', '').strip().lower() or None
    date_from = request.args.get('date_from', '').strip() or None
    date_to   = request.args.get('date_to',   '').strip() or None
    user      = request.args.get('user',       '').strip() or None
    try:
        page     = max(1, int(request.args.get('page', 1)))
        per_page = min(100, max(10, int(request.args.get('per_page', 50))))
    except (ValueError, TypeError):
        page, per_page = 1, 50

    if feedback_type and feedback_type not in _VALID_TYPES:
        feedback_type = None

    conn = database.get_db_connection()
    try:
        conditions = ["m.message_type='feedback'"]
        params = []

        if feedback_type:
            conditions.append("m.feedback_type = ?")
            params.append(feedback_type)
        if date_from:
            conditions.append("DATE(m.timestamp) >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("DATE(m.timestamp) <= ?")
            params.append(date_to)
        if user:
            conditions.append("(u.username LIKE ? OR CAST(m.sender_id AS TEXT) = ?)")
            params += [f'%{user}%', user]

        where = ' AND '.join(conditions)

        total = conn.execute(
            f"""SELECT COUNT(*) FROM messages m
                LEFT JOIN users u ON u.id = m.sender_id
                WHERE {where}""",
            params
        ).fetchone()[0]

        offset = (page - 1) * per_page
        rows = conn.execute(
            f"""SELECT m.id, m.sender_id, m.content, m.feedback_type, m.timestamp,
                       u.username
                FROM messages m
                LEFT JOIN users u ON u.id = m.sender_id
                WHERE {where}
                ORDER BY m.timestamp DESC
                LIMIT ? OFFSET ?""",
            params + [per_page, offset]
        ).fetchall()

        feedback = []
        for r in rows:
            ft = r['feedback_type'] or None
            feedback.append({
                'id':            r['id'],
                'sender_id':     r['sender_id'],
                'username':      r['username'] or f'User #{r["sender_id"]}',
                'feedback_type': ft,
                'type_label':    _TYPE_LABELS.get(ft, 'Uncategorized') if ft else 'Uncategorized',
                'content':       r['content'] or '',
                'created_at':    str(r['timestamp']) if r['timestamp'] else None,
            })

        return jsonify({
            'success':   True,
            'feedback':  feedback,
            'total':     total,
            'page':      page,
            'per_page':  per_page,
            'pages':     max(1, (total + per_page - 1) // per_page),
        })
    except Exception as exc:
        _log.exception('list_feedback error')
        return jsonify({'success': False, 'error': str(exc)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/feedback/<int:feedback_id>', methods=['GET'])
@admin_required
def get_feedback_detail(feedback_id):
    """Return a single feedback item."""
    conn = database.get_db_connection()
    try:
        row = conn.execute(
            """SELECT m.id, m.sender_id, m.content, m.feedback_type, m.timestamp,
                      u.username, u.email
               FROM messages m
               LEFT JOIN users u ON u.id = m.sender_id
               WHERE m.id = ? AND m.message_type='feedback'""",
            (feedback_id,)
        ).fetchone()

        if not row:
            return jsonify({'success': False, 'error': 'Not found'}), 404

        ft = row['feedback_type'] or None
        return jsonify({
            'success': True,
            'item': {
                'id':            row['id'],
                'sender_id':     row['sender_id'],
                'username':      row['username'] or f'User #{row["sender_id"]}',
                'email':         row['email'] or '—',
                'feedback_type': ft,
                'type_label':    _TYPE_LABELS.get(ft, 'Uncategorized') if ft else 'Uncategorized',
                'content':       row['content'] or '',
                'created_at':    str(row['timestamp']) if row['timestamp'] else None,
            }
        })
    except Exception as exc:
        _log.exception('get_feedback_detail error')
        return jsonify({'success': False, 'error': str(exc)}), 500
    finally:
        conn.close()
