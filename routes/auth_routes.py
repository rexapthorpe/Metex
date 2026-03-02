# routes/auth_routes.py — re-export wrapper
# Active implementation lives in core/blueprints/auth/routes.py
from core.blueprints.auth import auth_bp

__all__ = ['auth_bp']
