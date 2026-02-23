"""
Analytics Service Package

This package contains all analytics-related functionality for the admin dashboard.

Structure:
- kpis.py: KPI calculations
- timeseries.py: Time series data
- rankings.py: Top items, users, transactions
- metrics.py: Market health, user analytics, operational metrics
- drilldowns.py: Drilldown queries for detailed views

IMPORTANT: This split preserves ALL original function signatures, return values, and behavior.
The AnalyticsService class is assembled here by importing methods from sub-modules.
"""

# Import all functions from sub-modules
from .kpis import get_kpis
from .timeseries import get_timeseries, get_timeseries_by_category
from .rankings import get_top_items, get_top_users, get_largest_transactions
from .metrics import get_market_health, get_user_analytics, get_operational_metrics, get_category_stats
from .drilldowns import (
    get_volume_drilldown,
    get_revenue_drilldown,
    get_trades_drilldown,
    get_listings_drilldown,
    get_users_drilldown,
    get_user_detail
)

# Marketplace fee rate constant
MARKETPLACE_FEE_RATE = 0.05  # 5% marketplace fee


class AnalyticsService:
    """
    Service for calculating analytics and metrics.

    This class assembles all analytics methods as static methods for backward compatibility.
    All methods are imported from the sub-modules above.
    """

    MARKETPLACE_FEE_RATE = MARKETPLACE_FEE_RATE

    # KPIs
    get_kpis = staticmethod(get_kpis)

    # Timeseries
    get_timeseries = staticmethod(get_timeseries)
    get_timeseries_by_category = staticmethod(get_timeseries_by_category)

    # Rankings
    get_top_items = staticmethod(get_top_items)
    get_top_users = staticmethod(get_top_users)
    get_largest_transactions = staticmethod(get_largest_transactions)

    # Metrics
    get_market_health = staticmethod(get_market_health)
    get_user_analytics = staticmethod(get_user_analytics)
    get_operational_metrics = staticmethod(get_operational_metrics)
    get_category_stats = staticmethod(get_category_stats)

    # Drilldowns
    get_volume_drilldown = staticmethod(get_volume_drilldown)
    get_revenue_drilldown = staticmethod(get_revenue_drilldown)
    get_trades_drilldown = staticmethod(get_trades_drilldown)
    get_listings_drilldown = staticmethod(get_listings_drilldown)
    get_users_drilldown = staticmethod(get_users_drilldown)
    get_user_detail = staticmethod(get_user_detail)


# Re-export everything for backward compatibility
__all__ = [
    'MARKETPLACE_FEE_RATE',
    'AnalyticsService',
    'get_kpis',
    'get_timeseries',
    'get_timeseries_by_category',
    'get_top_items',
    'get_top_users',
    'get_largest_transactions',
    'get_market_health',
    'get_user_analytics',
    'get_operational_metrics',
    'get_category_stats',
    'get_volume_drilldown',
    'get_revenue_drilldown',
    'get_trades_drilldown',
    'get_listings_drilldown',
    'get_users_drilldown',
    'get_user_detail',
]
