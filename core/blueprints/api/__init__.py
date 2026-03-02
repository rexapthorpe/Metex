"""
API Blueprint

General API routes: cart data, spot prices, price locks, search, listing details.
"""

from flask import Blueprint

api_bp = Blueprint('api', __name__)

# Import routes to register them with the blueprint
from . import routes
from . import bucket_reference

__all__ = ['api_bp']
