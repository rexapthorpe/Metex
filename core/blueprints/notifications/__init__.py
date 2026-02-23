"""
Notifications Blueprint

Notification API routes: get, mark read, delete.
"""

from flask import Blueprint

notification_bp = Blueprint('notifications', __name__)

# Import routes to register them with the blueprint
from . import routes

__all__ = ['notification_bp']
