# routes/checkout_routes.py
# Re-export wrapper — actual implementation lives in core/blueprints/checkout/
from core.blueprints.checkout import checkout_bp

__all__ = ['checkout_bp']
