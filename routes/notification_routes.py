"""
Notification Routes
API endpoints for notification management and per-type user settings.
"""

from flask import Blueprint, jsonify, session, request
from services.notification_service import (
    get_user_notifications,
    mark_notification_read,
    mark_all_notifications_read,
    delete_notification,
    get_unread_count,
    get_user_notification_settings,
    update_notification_settings,
)

notification_bp = Blueprint('notifications', __name__)


@notification_bp.route('/notifications', methods=['GET'])
def get_notifications():
    """Get all notifications for the current user"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    user_id = session['user_id']
    unread_only = request.args.get('unread_only', 'false').lower() == 'true'
    limit = int(request.args.get('limit', 50))

    notifications = get_user_notifications(user_id, unread_only=unread_only, limit=limit)

    return jsonify({
        'success': True,
        'notifications': notifications
    })


@notification_bp.route('/notifications/unread-count', methods=['GET'])
def get_unread_notification_count():
    """Get count of unread notifications"""
    if 'user_id' not in session:
        return jsonify({'count': 0})

    user_id = session['user_id']
    count = get_unread_count(user_id)

    return jsonify({
        'success': True,
        'count': count
    })


@notification_bp.route('/notifications/mark-all-read', methods=['POST'])
def mark_all_read():
    """Mark all notifications as read for the current user"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    user_id = session['user_id']
    mark_all_notifications_read(user_id)
    return jsonify({'success': True})


@notification_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
def mark_read(notification_id):
    """Mark a notification as read"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    try:
        mark_notification_read(notification_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@notification_bp.route('/notifications/<int:notification_id>', methods=['DELETE'])
def delete_notif(notification_id):
    """Delete a notification"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    user_id = session['user_id']
    success = delete_notification(notification_id, user_id)

    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Notification not found or unauthorized'}), 404


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
    Accepts JSON: { "notification_type": true/false, ... }
    or form-encoded with the same keys.
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = dict(request.form)

    if not data:
        return jsonify({'error': 'No settings provided'}), 400

    # Coerce values to bool
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
