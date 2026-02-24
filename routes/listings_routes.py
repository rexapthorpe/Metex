# routes/listings_routes.py
# Re-export wrapper for backward compatibility.
# Actual implementation is in core/blueprints/listings/

from core.blueprints.listings import listings_bp

__all__ = ['listings_bp']
