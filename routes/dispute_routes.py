# Re-export wrapper — backward-compat thin shim.
from core.blueprints.disputes import disputes_bp  # noqa: F401

__all__ = ['disputes_bp']
