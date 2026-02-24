# routes/sell_routes.py
# Re-export wrapper for backward compatibility.
# Actual implementation is in core/blueprints/sell/

from core.blueprints.sell import sell_bp

__all__ = ['sell_bp']
