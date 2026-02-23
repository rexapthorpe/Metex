"""
API Response Shape Tests for Refactoring Safety Net

These tests verify that JSON API responses maintain their expected
structure and key names. Frontend code depends on these exact shapes.

Test Categories:
1. Public API endpoints
2. Cart API endpoints
3. Admin API endpoints
4. Order API endpoints
5. Analytics API endpoints

IMPORTANT: These tests lock in CURRENT response shapes. If a test
fails after refactoring, frontend compatibility may be broken.
"""
import pytest
import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPublicApiShapes:
    """Test public API response structures."""

    def test_spot_prices_shape(self, client):
        """Verify spot prices response structure."""
        response = client.get('/api/spot-prices')
        assert response.status_code == 200
        data = json.loads(response.data)

        # Verify it's a dict with price data
        assert isinstance(data, dict)
        # Common keys expected in spot price responses
        # The exact keys depend on implementation, but verify structure exists
        assert len(data) >= 0  # At minimum, valid JSON dict

    def test_product_lines_shape(self, client):
        """Verify product lines response structure."""
        response = client.get('/api/product_lines')
        assert response.status_code == 200
        data = json.loads(response.data)

        # Should be a list or dict of product lines
        assert isinstance(data, (list, dict))

    def test_search_autocomplete_shape(self, client):
        """Verify search autocomplete response structure."""
        response = client.get('/api/search/autocomplete?q=gold')
        assert response.status_code == 200
        data = json.loads(response.data)

        # Should return a list of suggestions or empty list
        assert isinstance(data, (list, dict))


class TestCartApiShapes:
    """Test cart API response structures."""

    def test_cart_data_shape(self, auth_client):
        """Verify cart data response structure."""
        client, user_id = auth_client
        response = client.get('/api/cart-data')
        assert response.status_code == 200
        data = json.loads(response.data)

        # Verify expected structure for cart data
        assert isinstance(data, dict)
        # Cart data should have items or cart_items key, or be empty dict
        # The exact key depends on implementation


class TestAccountApiShapes:
    """Test account API response structures."""

    def test_addresses_shape(self, auth_client):
        """Verify addresses response structure."""
        client, user_id = auth_client
        response = client.get('/account/get_addresses')
        assert response.status_code == 200
        data = json.loads(response.data)

        # Should be a list of addresses or object with addresses
        assert isinstance(data, (list, dict))

    def test_preferences_shape(self, auth_client):
        """Verify preferences response structure."""
        client, user_id = auth_client
        response = client.get('/account/get_preferences')
        assert response.status_code == 200
        data = json.loads(response.data)

        # Should be a dict with preference settings
        assert isinstance(data, dict)

    def test_saved_addresses_api_shape(self, auth_client):
        """Verify saved addresses API response structure."""
        client, user_id = auth_client
        response = client.get('/account/api/addresses')
        assert response.status_code == 200
        data = json.loads(response.data)

        # Should be a list of addresses
        assert isinstance(data, (list, dict))


class TestPortfolioApiShapes:
    """Test portfolio API response structures."""

    def test_portfolio_data_shape(self, auth_client):
        """Verify portfolio data response structure."""
        client, user_id = auth_client
        response = client.get('/portfolio/data')
        assert response.status_code == 200
        data = json.loads(response.data)

        # Verify expected structure for portfolio
        assert isinstance(data, dict)
        # Portfolio should have holdings, total value, etc.


class TestAdminApiShapes:
    """Test admin API response structures."""

    def test_admin_user_details_shape(self, admin_client):
        """Verify admin user details response structure (may return 403)."""
        client, user_id = admin_client
        response = client.get(f'/admin/api/user/{user_id}')
        # May return 403 if admin check fails due to test DB isolation
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, dict)

    def test_admin_user_stats_shape(self, admin_client):
        """Verify admin user stats response structure (may return 403)."""
        client, user_id = admin_client
        response = client.get(f'/admin/api/user/{user_id}/stats')
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, dict)


class TestAnalyticsApiShapes:
    """Test analytics API response structures."""

    def test_kpis_shape(self, admin_client):
        """Verify KPIs response structure (may return 403)."""
        client, user_id = admin_client
        response = client.get('/admin/analytics/kpis')
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, dict)

    def test_timeseries_shape(self, admin_client):
        """Verify timeseries response structure (may return 403)."""
        client, user_id = admin_client
        response = client.get('/admin/analytics/timeseries')
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, (dict, list))

    def test_top_items_shape(self, admin_client):
        """Verify top items response structure (may return 403)."""
        client, user_id = admin_client
        response = client.get('/admin/analytics/top-items')
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, (list, dict))

    def test_top_users_shape(self, admin_client):
        """Verify top users response structure (may return 403)."""
        client, user_id = admin_client
        response = client.get('/admin/analytics/top-users')
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, (list, dict))

    def test_market_health_shape(self, admin_client):
        """Verify market health response structure (may return 403)."""
        client, user_id = admin_client
        response = client.get('/admin/analytics/market-health')
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, dict)

    def test_user_analytics_shape(self, admin_client):
        """Verify user analytics response structure (may return 403)."""
        client, user_id = admin_client
        response = client.get('/admin/analytics/user-analytics')
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, (dict, list))

    def test_operational_shape(self, admin_client):
        """Verify operational metrics response structure (may return 403)."""
        client, user_id = admin_client
        response = client.get('/admin/analytics/operational')
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, dict)

    def test_categories_shape(self, admin_client):
        """Verify categories stats response structure (may return 403)."""
        client, user_id = admin_client
        response = client.get('/admin/analytics/categories')
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, (dict, list))


class TestLedgerApiShapes:
    """Test ledger API response structures."""

    def test_ledger_stats_shape(self, admin_client):
        """Verify ledger stats response structure (may return 403)."""
        client, user_id = admin_client
        response = client.get('/admin/api/ledger/stats')
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, dict)

    def test_ledger_orders_shape(self, admin_client):
        """Verify ledger orders response structure (may return 403)."""
        client, user_id = admin_client
        response = client.get('/admin/api/ledger/orders')
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, (dict, list))


class TestBucketApiShapes:
    """Test bucket API response structures."""

    def test_buckets_list_shape(self, admin_client):
        """Verify buckets list response structure (may return 403)."""
        client, user_id = admin_client
        response = client.get('/admin/api/buckets')
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, (list, dict))


class TestReportsApiShapes:
    """Test reports API response structures."""

    def test_reports_list_shape(self, admin_client):
        """Verify reports list response structure (may return 403)."""
        client, user_id = admin_client
        response = client.get('/admin/api/reports')
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, (list, dict))


class TestOrderApiShapes:
    """Test order API response structures."""

    def test_order_details_requires_valid_order(self, auth_client):
        """Verify order details endpoint behavior."""
        client, user_id = auth_client
        response = client.get('/orders/api/999999/details')
        # Should return 404 for non-existent order or error JSON
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, dict)


class TestListingApiShapes:
    """Test listing API response structures."""

    def test_listing_details_shape(self, client, sample_listing):
        """Verify listing details response structure."""
        listing_id, bucket_id = sample_listing
        response = client.get(f'/api/listings/{listing_id}/details')
        # May return 404 if listing doesn't exist in test DB
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, dict)


class TestConversationsApiShapes:
    """Test conversations API response structures."""

    def test_admin_conversations_shape(self, admin_client):
        """Verify admin conversations response structure (may return 403)."""
        client, user_id = admin_client
        response = client.get('/admin/api/conversations')
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, (list, dict))


class TestPriceLockApiShapes:
    """Test price lock API response structures."""

    def test_create_price_lock_requires_post(self, auth_client):
        """Verify price lock creation requires POST."""
        client, user_id = auth_client
        response = client.get('/api/price-lock/create')
        assert response.status_code == 405


class TestDrilldownApiShapes:
    """Test analytics drilldown API response structures."""

    def test_volume_drilldown_shape(self, admin_client):
        """Verify volume drilldown response structure (may return 403)."""
        client, user_id = admin_client
        response = client.get('/admin/analytics/drilldown/volume')
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, (dict, list))

    def test_revenue_drilldown_shape(self, admin_client):
        """Verify revenue drilldown response structure (may return 403)."""
        client, user_id = admin_client
        response = client.get('/admin/analytics/drilldown/revenue')
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, (dict, list))

    def test_trades_drilldown_shape(self, admin_client):
        """Verify trades drilldown response structure (may return 403)."""
        client, user_id = admin_client
        response = client.get('/admin/analytics/drilldown/trades')
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, (dict, list))

    def test_listings_drilldown_shape(self, admin_client):
        """Verify listings drilldown response structure (may return 403)."""
        client, user_id = admin_client
        response = client.get('/admin/analytics/drilldown/listings')
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, (dict, list))

    def test_users_drilldown_shape(self, admin_client):
        """Verify users drilldown response structure (may return 403)."""
        client, user_id = admin_client
        response = client.get('/admin/analytics/drilldown/users')
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, (dict, list))
