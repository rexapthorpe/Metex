"""
Sell Blueprint

Sell routes: create listing, upload tracking, accept bids, sold orders.
"""

from flask import Blueprint

sell_bp = Blueprint('sell', __name__)

# Import routes to register them with the blueprint
from . import routes

__all__ = ['sell_bp']
