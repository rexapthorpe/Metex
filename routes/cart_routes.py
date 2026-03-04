# routes/cart_routes.py
# Re-export wrapper — routes implemented in core/blueprints/cart/
from core.blueprints.cart import cart_bp  # noqa: F401

__all__ = ['cart_bp']
