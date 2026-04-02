"""
Admin Risk Routes (Phase 4)
============================
Admin endpoints for user risk profile monitoring and management.

Endpoints (all under /admin prefix via blueprint registration):
  GET  /api/risk                          — list risk profiles (filterable)
  GET  /api/risk/<user_id>                — full user risk detail
  POST /api/risk/<user_id>/flag           — set manual risk flag
  POST /api/risk/<user_id>/flag/clear     — clear manual flag
  POST /api/risk/<user_id>/note           — update admin note
  POST /api/risk/<user_id>/recompute      — force score recomputation

All endpoints require admin login (@admin_required).
"""

from flask import jsonify, request, session
from utils.auth_utils import admin_required
from . import admin_bp
import services.risk_service as risk_service


def _admin_id():
    return session.get('user_id')


@admin_bp.route('/api/risk')
@admin_required
def admin_list_risk():
    """Return paginated risk profile list for admin."""
    flag       = request.args.get('flag', '').strip() or None
    score_min  = request.args.get('score_min', type=int)
    username   = request.args.get('username', '').strip() or None

    try:
        profiles = risk_service.get_risk_list(
            flag_filter=flag,
            score_min=score_min,
            username=username,
        )
        return jsonify({'success': True, 'profiles': profiles})
    except Exception as exc:
        print(f'[Admin Risk] list error: {exc}')
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/risk/<int:user_id>')
@admin_required
def admin_get_risk_detail(user_id):
    """Return full risk detail (profile + event history) for one user."""
    try:
        detail = risk_service.get_risk_detail(user_id)
        if not detail:
            return jsonify({'success': False, 'error': 'User not found.'}), 404
        return jsonify({'success': True, **detail})
    except Exception as exc:
        print(f'[Admin Risk] detail error for user {user_id}: {exc}')
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/risk/<int:user_id>/flag', methods=['POST'])
@admin_required
def admin_set_risk_flag(user_id):
    """Set a manual risk flag. Body: flag, reason, note (optional)."""
    data   = request.get_json(silent=True) or {}
    flag   = (data.get('flag')   or request.form.get('flag',   '')).strip()
    reason = (data.get('reason') or request.form.get('reason', '')).strip()
    note   = (data.get('note')   or request.form.get('note',   '')).strip() or None

    if not flag:
        return jsonify({'success': False, 'error': 'flag is required.'}), 400
    if not reason:
        return jsonify({'success': False, 'error': 'reason is required.'}), 400

    try:
        risk_service.set_manual_flag(user_id, _admin_id(), flag, reason, note)
        return jsonify({'success': True})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        print(f'[Admin Risk] set_flag error for user {user_id}: {exc}')
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/risk/<int:user_id>/flag/clear', methods=['POST'])
@admin_required
def admin_clear_risk_flag(user_id):
    """Clear manual risk flag (reset to 'none'). Body: note (optional)."""
    data = request.get_json(silent=True) or {}
    note = (data.get('note') or request.form.get('note', '')).strip() or None

    try:
        risk_service.clear_manual_flag(user_id, _admin_id(), note)
        return jsonify({'success': True})
    except Exception as exc:
        print(f'[Admin Risk] clear_flag error for user {user_id}: {exc}')
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/risk/<int:user_id>/note', methods=['POST'])
@admin_required
def admin_update_risk_note(user_id):
    """Update admin-only notes field. Body: note."""
    data = request.get_json(silent=True) or {}
    note = (data.get('note') or request.form.get('note', '')).strip()

    try:
        risk_service.update_admin_note(user_id, _admin_id(), note)
        return jsonify({'success': True})
    except Exception as exc:
        print(f'[Admin Risk] update_note error for user {user_id}: {exc}')
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/risk/<int:user_id>/recompute', methods=['POST'])
@admin_required
def admin_recompute_risk(user_id):
    """Force recomputation of risk score + auto-flag check. Returns updated detail."""
    try:
        risk_service.recompute_risk_profile(user_id)
        detail = risk_service.get_risk_detail(user_id)
        return jsonify({'success': True, **(detail or {})})
    except Exception as exc:
        print(f'[Admin Risk] recompute error for user {user_id}: {exc}')
        return jsonify({'success': False, 'error': str(exc)}), 500
