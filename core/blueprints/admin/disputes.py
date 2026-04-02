"""
Admin Dispute Routes (Phase 3)
================================
Admin adjudication and resolution endpoints for the dispute workflow.

Endpoints (all under /admin prefix via blueprint registration):
  GET  /api/disputes                     — list with optional filters
  GET  /api/disputes/<id>                — full dispute detail
  POST /api/disputes/<id>/status         — change to non-terminal status
  POST /api/disputes/<id>/resolve        — resolve (refund / deny / close)
  POST /api/disputes/<id>/note           — add internal admin note

All endpoints require admin login (@admin_required).
"""

from flask import jsonify, request, session
from utils.auth_utils import admin_required
from . import admin_bp
from services.dispute_service import (
    get_dispute_list,
    get_dispute_detail,
    admin_change_status,
    admin_add_note,
    admin_resolve,
)


def _admin_id():
    return session.get('user_id')


@admin_bp.route('/api/disputes')
@admin_required
def admin_list_disputes():
    """
    Return paginated dispute list for admin.

    Query params (all optional):
      status         — filter by exact status string
      dispute_type   — filter by dispute_type
      buyer          — buyer username substring
      seller         — seller username substring
    """
    status = request.args.get('status', '').strip() or None
    dispute_type = request.args.get('dispute_type', '').strip() or None
    buyer_username = request.args.get('buyer', '').strip() or None
    seller_username = request.args.get('seller', '').strip() or None

    try:
        disputes, stats = get_dispute_list(
            status=status,
            dispute_type=dispute_type,
            buyer_username=buyer_username,
            seller_username=seller_username,
        )
        return jsonify({'success': True, 'disputes': disputes, 'stats': stats})
    except Exception as exc:
        print(f'[Admin Disputes] Error listing disputes: {exc}')
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/disputes/<int:dispute_id>')
@admin_required
def admin_get_dispute(dispute_id):
    """Return full dispute detail including evidence, timeline, and transaction snapshots."""
    try:
        detail = get_dispute_detail(dispute_id)
        if not detail:
            return jsonify({'success': False, 'error': 'Dispute not found.'}), 404
        return jsonify({'success': True, 'dispute': detail})
    except Exception as exc:
        print(f'[Admin Disputes] Error fetching dispute {dispute_id}: {exc}')
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/disputes/<int:dispute_id>/status', methods=['POST'])
@admin_required
def admin_update_dispute_status(dispute_id):
    """
    Move a dispute to a non-terminal status.

    Body (JSON or form):
      new_status  — target status string
      note        — optional note (stored in timeline)
    """
    data = request.get_json(silent=True) or {}
    new_status = (data.get('new_status') or request.form.get('new_status', '')).strip()
    note = (data.get('note') or request.form.get('note', '')).strip() or None

    if not new_status:
        return jsonify({'success': False, 'error': 'new_status is required.'}), 400

    try:
        admin_change_status(dispute_id, _admin_id(), new_status, note)
        return jsonify({'success': True})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        print(f'[Admin Disputes] Error updating status for {dispute_id}: {exc}')
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/disputes/<int:dispute_id>/resolve', methods=['POST'])
@admin_required
def admin_resolve_dispute(dispute_id):
    """
    Resolve a dispute as admin.

    Body (JSON or form):
      resolution  — 'resolved_refund' | 'resolved_denied' | 'closed'
      note        — required resolution note

    For 'resolved_refund': attempts Stripe full refund and writes refunds table row.
    Partial refunds are NOT yet supported (Phase 4).
    """
    data = request.get_json(silent=True) or {}
    resolution = (data.get('resolution') or request.form.get('resolution', '')).strip()
    note = (data.get('note') or request.form.get('note', '')).strip()

    if not resolution:
        return jsonify({'success': False, 'error': 'resolution is required.'}), 400
    if not note:
        return jsonify({'success': False, 'error': 'A resolution note is required.'}), 400

    try:
        refund_result = admin_resolve(dispute_id, _admin_id(), resolution, note)
        return jsonify({'success': True, 'refund_result': refund_result})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        print(f'[Admin Disputes] Error resolving dispute {dispute_id}: {exc}')
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/disputes/<int:dispute_id>/note', methods=['POST'])
@admin_required
def admin_add_dispute_note(dispute_id):
    """
    Add an internal admin-only note to a dispute.
    Stored as event_type='admin_note' in dispute_timeline.
    NOT visible to buyers or sellers.

    Body (JSON or form):
      note  — required note text
    """
    data = request.get_json(silent=True) or {}
    note = (data.get('note') or request.form.get('note', '')).strip()

    if not note:
        return jsonify({'success': False, 'error': 'Note text is required.'}), 400

    try:
        admin_add_note(dispute_id, _admin_id(), note)
        return jsonify({'success': True})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        print(f'[Admin Disputes] Error adding note for {dispute_id}: {exc}')
        return jsonify({'success': False, 'error': str(exc)}), 500
