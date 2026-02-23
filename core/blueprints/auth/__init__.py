"""
Auth Blueprint

Authentication routes: login, logout, register, password reset.
"""

from flask import Blueprint

auth_bp = Blueprint('auth', __name__)

# Import routes to register them with the blueprint
from . import routes

__all__ = ['auth_bp']
