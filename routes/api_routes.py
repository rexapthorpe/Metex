"""
API Routes - Re-export wrapper for backward compatibility.

All API routes are now in core/blueprints/api/routes.py:
- /api/product_lines - Product lines lookup
- /api/cart-data - Cart data for checkout
- /api/spot-prices - Current spot prices
- /api/spot-prices/refresh - Force refresh spot prices
- /api/price-lock/create - Create price lock
- /api/price-lock/get/<listing_id> - Get active price lock
- /api/search/autocomplete - Search autocomplete (NEW)
- /api/listings/<listing_id>/details - Listing details (NEW)
"""
from core.blueprints.api import api_bp

__all__ = ['api_bp']
