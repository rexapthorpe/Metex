"""
Messages Blueprint

Message routes: get sellers, buyers, messages, post messages, mark read.
"""

from flask import Blueprint

messages_bp = Blueprint('messages', __name__)

# Import routes to register them with the blueprint
from . import routes

__all__ = ['messages_bp']
