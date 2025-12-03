"""
Notification Routes
API endpoints for notification management
"""

from flask import Blueprint, jsonify, session, request
from services.notification_service import (
    get_user_notifications,
    mark_notification_read,
    delete_notification,
    get_unread_count
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
