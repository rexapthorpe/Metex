"""
Buy Blueprint Package

This package contains all buy-related routes, split by domain for maintainability.
The buy_bp Blueprint is defined here and routes are registered by importing sub-modules.

Structure:
- __init__.py: Blueprint definition and assembly
- buy_page.py: Main buy page with category listings
- bucket_view.py: Bucket viewing and availability JSON
- sellers_api.py: Sellers API for bucket
- cart.py: Cart operations (add, view, readd)
- purchase.py: Purchase operations (preview, direct buy, auto-fill, price lock)

IMPORTANT: This split preserves ALL original route URLs, endpoint names, and behavior.
The blueprint name remains 'buy' for compatibility.
"""

from flask import Blueprint

# Create the buy blueprint - MUST keep name='buy' for URL compatibility
buy_bp = Blueprint('buy', __name__)

# Import all route modules to register routes with buy_bp
from . import buy_page
from . import bucket_view
from . import sellers_api
from . import cart
from . import purchase

# Re-export for compatibility
__all__ = ['buy_bp']
