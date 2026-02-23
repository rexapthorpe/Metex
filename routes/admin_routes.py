"""
Admin Routes - Re-export wrapper for backward compatibility.

All admin routes are now in core/blueprints/admin/ (split into 8 modules):
- dashboard.py: Main dashboard page and overview stats
- users.py: User management (ban, freeze, delete, messages)
- analytics.py: Analytics page and API endpoints
- ledger.py: Ledger management routes
- buckets.py: Bucket CRUD operations
- reports.py: Reports management
- orders.py: Order hold/approve/refund operations
- metrics.py: Metrics performance API
"""
from core.blueprints.admin import admin_bp

__all__ = ['admin_bp']
