"""
Listings Blueprint

Listing routes: edit listing, cancel listing, my listings.
"""

from flask import Blueprint

listings_bp = Blueprint('listings', __name__)

# Import routes to register them with the blueprint
from . import routes

__all__ = ['listings_bp']
