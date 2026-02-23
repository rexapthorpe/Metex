"""
Cart Blueprint

Cart management routes: remove seller, remove item, update quantities.
"""

from flask import Blueprint

cart_bp = Blueprint('cart', __name__, url_prefix='/cart')

# Import routes to register them with the blueprint
from . import routes

__all__ = ['cart_bp']
