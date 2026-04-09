"""
Admin Refunds Routes (Phase 5)
================================
Admin read-only endpoints for refund records.

Endpoints (all under /admin prefix):
  GET /api/refunds              — list refunds with optional filters
  GET /api/refunds/<id>         — single refund detail

All endpoints require admin login (@admin_required).
Refunds are write-protected: they are only created by admin_resolve() in
dispute_service.py and are auditable records, not editable.
"""

from datetime import datetime, timedelta
from flask import jsonify, request
from utils.auth_utils import admin_required
from . import admin_bp
import database as _db_module


def _get_conn():
    return _db_module.get_db_connection()


@admin_bp.route('/api/refunds')
@admin_required
def admin_list_refunds():
    """
    Return refund list for admin.

    Query params (all optional):
      date_from   — ISO date string (YYYY-MM-DD), inclusive
      date_to     — ISO date string (YYYY-MM-DD), inclusive
      dispute_id  — exact dispute ID integer
      buyer       — buyer username substring
      seller      — seller username substring
    """
    date_from  = request.args.get('date_from', '').strip() or None
    date_to    = request.args.get('date_to', '').strip() or None
    dispute_id = request.args.get('dispute_id', '').strip() or None
    buyer      = request.args.get('buyer', '').strip() or None
    seller     = request.args.get('seller', '').strip() or None

    try:
        conn = _get_conn()
        query = '''
            SELECT
                r.id,
                r.dispute_id,
                r.order_id,
                r.buyer_id,
                r.seller_id,
                r.amount,
                r.provider_refund_id,
                r.issued_by_admin_id,
                r.issued_at,
                r.note,
                buyer_u.username  AS buyer_username,
                seller_u.username AS seller_username,
                admin_u.username  AS issued_by_admin_username
            FROM refunds r
            LEFT JOIN users buyer_u  ON r.buyer_id           = buyer_u.id
            LEFT JOIN users seller_u ON r.seller_id          = seller_u.id
            LEFT JOIN users admin_u  ON r.issued_by_admin_id = admin_u.id
            WHERE 1=1
        '''
        params = []

        if date_from:
            query += ' AND r.issued_at >= ?'
            params.append(date_from)

        if date_to:
            # Make date_to inclusive by extending to end of the day
            query += ' AND r.issued_at < ?'
            try:
                dt_to = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
                params.append(dt_to.strftime('%Y-%m-%d'))
            except ValueError:
                params.append(date_to)

        if dispute_id:
            query += ' AND r.dispute_id = ?'
            try:
                params.append(int(dispute_id))
            except ValueError:
                pass

        if buyer:
            query += ' AND buyer_u.username LIKE ?'
            params.append(f'%{buyer}%')

        if seller:
            query += ' AND seller_u.username LIKE ?'
            params.append(f'%{seller}%')

        query += ' ORDER BY r.issued_at DESC LIMIT 200'

        rows = conn.execute(query, params).fetchall()

        # Summary stats
        total_amount = sum((r['amount'] or 0) for r in rows)
        count = len(rows)

        conn.close()
        return jsonify({
            'success': True,
            'refunds': [dict(r) for r in rows],
            'summary': {'count': count, 'total_amount': round(total_amount, 2)},
        })

    except Exception as exc:
        print(f'[Admin Refunds] list error: {exc}')
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/refunds/<int:refund_id>')
@admin_required
def admin_get_refund(refund_id):
    """Return a single refund with breakdown, recovery details, and linked dispute/order."""
    try:
        conn = _get_conn()
        row = conn.execute(
            '''
            SELECT
                r.*,
                buyer_u.username  AS buyer_username,
                seller_u.username AS seller_username,
                admin_u.username  AS issued_by_admin_username,
                d.dispute_type,
                d.status          AS dispute_status,
                d.description     AS dispute_description,
                o.total_price     AS order_total,
                o.status          AS order_status,
                o.stripe_payment_intent_id,
                o.refund_status,
                o.refund_subtotal,
                o.refund_tax_amount,
                o.refund_processing_fee,
                o.platform_covered_amount,
                o.refund_reason,
                o.refunded_at,
                o.stripe_refund_id
            FROM refunds r
            LEFT JOIN users buyer_u  ON r.buyer_id           = buyer_u.id
            LEFT JOIN users seller_u ON r.seller_id          = seller_u.id
            LEFT JOIN users admin_u  ON r.issued_by_admin_id = admin_u.id
            LEFT JOIN disputes d     ON r.dispute_id         = d.id
            LEFT JOIN orders o       ON r.order_id           = o.id
            WHERE r.id = ?
            ''',
            (refund_id,),
        ).fetchone()

        if not row:
            conn.close()
            return jsonify({'success': False, 'error': 'Refund not found.'}), 404

        refund = dict(row)

        # Fetch per-seller payout recovery details for this order
        if refund.get('order_id'):
            payout_rows = conn.execute(
                '''
                SELECT op.id, op.seller_id, op.payout_status, op.payout_recovery_status,
                       op.provider_transfer_id, op.provider_reversal_id,
                       op.seller_net_amount, op.recovery_failure_reason,
                       u.username AS seller_username
                FROM order_payouts op
                LEFT JOIN users u ON op.seller_id = u.id
                WHERE op.order_id = ?
                ORDER BY op.id
                ''',
                (refund['order_id'],),
            ).fetchall()
            refund['payouts'] = [dict(p) for p in payout_rows]
        else:
            refund['payouts'] = []

        conn.close()
        return jsonify({'success': True, 'refund': refund})

    except Exception as exc:
        print(f'[Admin Refunds] detail error for {refund_id}: {exc}')
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/overview-metrics')
@admin_required
def admin_overview_metrics():
    """
    Phase 5 operational metrics for the admin Overview tab.

    Returns:
      open_disputes_count       — active disputes not in a terminal state
      avg_resolution_hours      — average hours from opened_at to resolved_at
      refunds_30d_total         — sum of refund amounts in last 30 days
      high_risk_users_count     — users with manual_risk_flag != 'none'
    """
    try:
        conn = _get_conn()
        result = {}

        # Open disputes (not terminal)
        try:
            row = conn.execute(
                """SELECT COUNT(*) AS cnt FROM disputes
                   WHERE status IN ('open','evidence_requested','under_review','escalated')"""
            ).fetchone()
            result['open_disputes_count'] = row['cnt'] or 0
        except Exception as exc:
            print(f'[Overview] open_disputes_count failed: {exc}')
            result['open_disputes_count'] = None

        # Average resolution time in hours (resolved disputes only).
        # Computed in Python to avoid julianday() which is SQLite-only.
        try:
            rows = conn.execute(
                """SELECT opened_at, resolved_at FROM disputes
                   WHERE resolved_at IS NOT NULL AND opened_at IS NOT NULL"""
            ).fetchall()
            total_hours = 0.0
            count = 0
            for r in rows:
                try:
                    opened   = datetime.fromisoformat(str(r['opened_at']))
                    resolved = datetime.fromisoformat(str(r['resolved_at']))
                    total_hours += (resolved - opened).total_seconds() / 3600.0
                    count += 1
                except Exception:
                    pass
            avg_h = (total_hours / count) if count > 0 else None
            result['avg_resolution_hours'] = round(avg_h, 1) if avg_h is not None else None
        except Exception as exc:
            print(f'[Overview] avg_resolution_hours failed: {exc}')
            result['avg_resolution_hours'] = None

        # Refunds in last 30 days
        try:
            window_start = (datetime.now() - timedelta(days=30)).isoformat()
            row = conn.execute(
                'SELECT COALESCE(SUM(amount), 0) AS total FROM refunds WHERE issued_at >= ?',
                (window_start,),
            ).fetchone()
            result['refunds_30d_total'] = round(row['total'] or 0, 2)
        except Exception as exc:
            print(f'[Overview] refunds_30d_total failed: {exc}')
            result['refunds_30d_total'] = None

        # High-risk users: manual flag is not 'none'
        try:
            row = conn.execute(
                """SELECT COUNT(*) AS cnt FROM user_risk_profile
                   WHERE manual_risk_flag IS NOT NULL AND manual_risk_flag != 'none'"""
            ).fetchone()
            result['high_risk_users_count'] = row['cnt'] or 0
        except Exception as exc:
            print(f'[Overview] high_risk_users_count failed: {exc}')
            result['high_risk_users_count'] = None

        conn.close()
        return jsonify({'success': True, **result})

    except Exception as exc:
        print(f'[Admin Overview Metrics] error: {exc}')
        return jsonify({'success': False, 'error': str(exc)}), 500
