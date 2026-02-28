"""
Notification Routes
API endpoints for notification management and per-type user settings.
"""

from flask import jsonify, session, request
from services.notification_service import (
    get_user_notifications,
    mark_notification_read,
    mark_all_notifications_read,
    delete_notification,
    get_unread_count,
    get_user_notification_settings,
    update_notification_settings,
)

from . import notification_bp


@notification_bp.route('/notifications', methods=['GET'])
def get_notifications():
    """Get all notifications for the current user."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    user_id = session['user_id']
    unread_only = request.args.get('unread_only', 'false').lower() == 'true'
    limit = int(request.args.get('limit', 50))

    notifications = get_user_notifications(user_id, unread_only=unread_only, limit=limit)
    return jsonify({'success': True, 'notifications': notifications})


@notification_bp.route('/notifications/unread-count', methods=['GET'])
def get_unread_notification_count():
    """Get count of unread notifications."""
    if 'user_id' not in session:
        return jsonify({'count': 0})

    count = get_unread_count(session['user_id'])
    return jsonify({'success': True, 'count': count})


@notification_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
def mark_read(notification_id):
    """Mark a single notification as read."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    try:
        mark_notification_read(notification_id)
        return jsonify({'success': True})
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@notification_bp.route('/notifications/mark-all-read', methods=['POST'])
def mark_all_read():
    """Mark all notifications as read for the current user."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    try:
        mark_all_notifications_read(session['user_id'])
        return jsonify({'success': True})
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@notification_bp.route('/notifications/<int:notification_id>', methods=['DELETE'])
def delete_notif(notification_id):
    """Delete a notification (ownership-checked)."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    success = delete_notification(notification_id, session['user_id'])
    if success:
        return jsonify({'success': True})
    return jsonify({'error': 'Notification not found or unauthorized'}), 404


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@notification_bp.route('/notifications/settings', methods=['GET'])
def get_settings():
    """Return the current user's notification settings as {type: bool}."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    settings = get_user_notification_settings(session['user_id'])
    return jsonify({'success': True, 'settings': settings})


@notification_bp.route('/notifications/settings', methods=['POST'])
def save_settings():
    """
    Update one or more notification settings.
    Accepts JSON body: { "notification_type": true/false, ... }
    or form data with the same keys.
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    # Accept both JSON and form-encoded bodies
    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = {k: v in ('1', 'true', 'True', True) for k, v in request.form.items()}

    if not data:
        return jsonify({'error': 'No settings provided'}), 400

    # Coerce to {str: bool}
    settings = {}
    for k, v in data.items():
        if isinstance(v, bool):
            settings[k] = v
        else:
            settings[k] = str(v).lower() in ('1', 'true')

    try:
        update_notification_settings(session['user_id'], settings)
        return jsonify({'success': True})
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500
