"""
Buy Routes - Re-export wrapper for backward compatibility.

All buy routes are now in core/blueprints/buy/ (split into modules):
- buy_page.py: Main /buy page with category listings and fee indicators
- bucket_view.py: /bucket/<id> view and availability JSON
- sellers_api.py: /api/bucket/<id>/sellers API
- cart.py: /add_to_cart, /view_cart, /readd_seller_to_cart
- purchase.py: /preview_buy, /order_success, /refresh_price_lock
- direct_purchase.py: /direct_buy, /purchase_from_bucket
"""
from core.blueprints.buy import buy_bp

__all__ = ['buy_bp']
