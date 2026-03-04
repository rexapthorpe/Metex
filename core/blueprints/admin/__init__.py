"""
Admin Blueprint Package

This package contains all admin-related routes, split by domain for maintainability.
The admin_bp Blueprint is defined here and routes are registered by importing sub-modules.

Structure:
- __init__.py: Blueprint definition and assembly
- dashboard.py: Dashboard page and overview stats
- users.py: User management (ban, freeze, delete, messages)
- analytics.py: Analytics page and API endpoints
- ledger.py: Ledger management routes
- buckets.py: Bucket CRUD operations
- reports.py: Reports management (both v1 and v2 routes)
- orders.py: Order hold/approve/refund operations
- metrics.py: Metrics performance API

IMPORTANT: This split preserves ALL original route URLs, endpoint names, and behavior.
The blueprint name remains 'admin' for URL prefix compatibility.
"""

from flask import Blueprint

# Create the admin blueprint - MUST keep name='admin' for URL prefix compatibility
admin_bp = Blueprint('admin', __name__)

# Import all route modules to register routes with admin_bp
# Order matters: later imports can override earlier routes with same URL
# (preserving original behavior where duplicate routes existed)
from . import dashboard
from . import users
from . import analytics
from . import ledger
from . import buckets
from . import reports
from . import orders
from . import metrics
from . import system

# Re-export for compatibility
__all__ = ['admin_bp']
