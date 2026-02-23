"""
Checkout Blueprint

Checkout routes: checkout page, order confirmation.
"""

from flask import Blueprint

checkout_bp = Blueprint('checkout', __name__)

# Import routes to register them with the blueprint
from . import routes

__all__ = ['checkout_bp']
