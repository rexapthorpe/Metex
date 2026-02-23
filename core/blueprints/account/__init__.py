"""
Account Blueprint Package

This package contains all account-related routes, split by domain for maintainability.
The account_bp Blueprint is defined here and routes are registered by importing sub-modules.

Structure:
- __init__.py: Blueprint definition and assembly
- account_page.py: Main account page route
- orders.py: Order viewing routes (my_orders, order details, sold_orders)
- messages.py: Messages route
- orders_api.py: Order API routes (details, sellers, items)
- settings.py: Account settings routes (personal info, password, notifications, profile)
- addresses.py: Address management routes (add, edit, delete, get)
- preferences_api.py: Preferences and additional API routes

IMPORTANT: This split preserves ALL original route URLs, endpoint names, and behavior.
The blueprint name remains 'account' for compatibility.
"""

from flask import Blueprint

# Create the account blueprint - MUST keep name='account' for URL compatibility
account_bp = Blueprint('account', __name__)

# Import all route modules to register routes with account_bp
from . import account_page
from . import orders
from . import messages
from . import orders_api
from . import settings
from . import addresses
from . import preferences_api
from . import payment_methods

# Re-export for compatibility
__all__ = ['account_bp']
