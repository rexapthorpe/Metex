"""
Ratings Blueprint

Rating routes: rate order.
"""

from flask import Blueprint

ratings_bp = Blueprint('ratings', __name__)

# Import routes to register them with the blueprint
from . import routes

__all__ = ['ratings_bp']
