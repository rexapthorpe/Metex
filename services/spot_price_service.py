"""
Spot Price Service
Fetches and caches live metal spot prices from MetalpriceAPI
"""

from database import get_db_connection
from datetime import datetime, timedelta
import requests
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MetalpriceAPI configuration
API_BASE_URL = "https://api.metalpriceapi.com/v1"
CACHE_TTL_MINUTES = 5  # How long to cache prices before refreshing


def get_api_key():
    """Get MetalpriceAPI key from environment variable"""
    api_key = os.getenv('METALPRICE_API_KEY')

    if not api_key:
        logger.warning("METALPRICE_API_KEY not found in environment variables")
        return None

    return api_key


def fetch_spot_prices_from_api():
    """
    Fetch current spot prices from MetalpriceAPI
    Returns dict: {metal: price_per_oz} or None on failure
    """
    api_key = get_api_key()

    if not api_key:
        logger.error("Cannot fetch spot prices: API key not configured")
        return None

    # Metals we support (in troy ounces)
    # MetalpriceAPI uses codes: XAU (gold), XAG (silver), XPT (platinum), XPD (palladium)
    metals = ['XAU', 'XAG', 'XPT', 'XPD']

    try:
        # API endpoint for latest prices
        url = f"{API_BASE_URL}/latest"

        params = {
            'api_key': api_key,
            'base': 'USD',
            'currencies': ','.join(metals)
        }

        logger.info(f"Fetching spot prices from MetalpriceAPI...")
        response = requests.get(url, params=params, timeout=10)

        if response.status_code != 200:
            logger.error(f"API request failed with status {response.status_code}: {response.text}")
            return None

        data = response.json()

        if not data.get('success'):
            logger.error(f"API returned error: {data}")
            return None

        # Extract rates (price per troy ounce)
        rates = data.get('rates', {})

        # Convert API codes to our metal names
        # API returns price per unit, we need to convert to per troy ounce
        # The API gives 1 USD = X units of metal, we want 1 troy oz = Y USD
        spot_prices = {}

        if 'XAU' in rates:
            # 1 USD = X troy oz, so 1 troy oz = 1/X USD
            spot_prices['gold'] = round(1 / rates['XAU'], 2)

        if 'XAG' in rates:
            spot_prices['silver'] = round(1 / rates['XAG'], 2)

        if 'XPT' in rates:
            spot_prices['platinum'] = round(1 / rates['XPT'], 2)

        if 'XPD' in rates:
            spot_prices['palladium'] = round(1 / rates['XPD'], 2)

        logger.info(f"Successfully fetched spot prices: {spot_prices}")
        return spot_prices

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error fetching spot prices: {e}")
        return None

    except Exception as e:
        logger.error(f"Unexpected error fetching spot prices: {e}")
        return None


def save_spot_prices_to_cache(spot_prices):
    """
    Save spot prices to database cache
    """
    if not spot_prices:
        return False

    conn = get_db_connection()

    try:
        for metal, price in spot_prices.items():
            conn.execute("""
                INSERT INTO spot_prices (metal, price_usd_per_oz, updated_at, source)
                VALUES (?, ?, CURRENT_TIMESTAMP, 'metalpriceapi')
                ON CONFLICT(metal) DO UPDATE SET
                    price_usd_per_oz = excluded.price_usd_per_oz,
                    updated_at = CURRENT_TIMESTAMP,
                    source = 'metalpriceapi'
            """, (metal, price))

        conn.commit()
        conn.close()

        logger.info(f"Saved {len(spot_prices)} spot prices to cache")
        return True

    except Exception as e:
        logger.error(f"Error saving spot prices to cache: {e}")
        conn.close()
        return False


def get_cached_spot_prices():
    """
    Get spot prices from database cache
    Returns dict: {metal: price_per_oz}
    """
    conn = get_db_connection()

    prices = conn.execute("""
        SELECT metal, price_usd_per_oz, updated_at
        FROM spot_prices
        ORDER BY metal
    """).fetchall()

    conn.close()

    if not prices:
        return {}

    # Convert to dict
    spot_prices = {}
    for row in prices:
        spot_prices[row['metal']] = row['price_usd_per_oz']

    return spot_prices


def is_cache_fresh():
    """
    Check if cached spot prices are still fresh (within TTL)
    Returns: (bool, datetime or None)
    """
    conn = get_db_connection()

    result = conn.execute("""
        SELECT MIN(updated_at) as oldest_update
        FROM spot_prices
    """).fetchone()

    conn.close()

    oldest_update = result['oldest_update'] if result else None

    if not oldest_update:
        return False, None

    # Parse timestamp
    try:
        update_time = datetime.fromisoformat(oldest_update)
        now = datetime.now()
        age_minutes = (now - update_time).total_seconds() / 60

        is_fresh = age_minutes < CACHE_TTL_MINUTES

        return is_fresh, update_time

    except Exception as e:
        logger.error(f"Error checking cache freshness: {e}")
        return False, None


def get_current_spot_prices(force_refresh=False):
    """
    Get current spot prices, using cache if fresh or fetching from API if stale

    Args:
        force_refresh: If True, bypass cache and fetch fresh data from API

    Returns:
        dict: {metal: price_per_oz}
    """

    # Check if we should use cache
    if not force_refresh:
        is_fresh, last_update = is_cache_fresh()

        if is_fresh:
            logger.info(f"Using cached spot prices (last updated: {last_update})")
            return get_cached_spot_prices()
        else:
            logger.info(f"Cache is stale (last updated: {last_update}), fetching fresh data...")
    else:
        logger.info("Force refresh requested, fetching fresh data from API...")

    # Fetch fresh prices from API
    fresh_prices = fetch_spot_prices_from_api()

    if fresh_prices:
        # Save to cache
        save_spot_prices_to_cache(fresh_prices)
        return fresh_prices
    else:
        # API failed - fall back to cache even if stale
        logger.warning("API fetch failed, falling back to cached prices (may be stale)")
        cached_prices = get_cached_spot_prices()

        if cached_prices:
            return cached_prices
        else:
            # No cache available - return empty dict
            logger.error("No cached prices available and API fetch failed")
            return {}


def get_spot_price(metal):
    """
    Get spot price for a specific metal

    Args:
        metal: Metal name ('gold', 'silver', 'platinum', 'palladium')

    Returns:
        float: Price per troy ounce, or None if not available
    """
    metal = metal.lower()
    spot_prices = get_current_spot_prices()

    return spot_prices.get(metal)


def refresh_spot_prices():
    """
    Manually refresh spot prices from API (used for scheduled tasks or admin actions)
    Returns: bool indicating success
    """
    logger.info("Manual spot price refresh triggered")

    fresh_prices = fetch_spot_prices_from_api()

    if fresh_prices:
        success = save_spot_prices_to_cache(fresh_prices)
        return success

    return False


def get_spot_price_age():
    """
    Get the age of the cached spot prices in minutes
    Returns: float (minutes since last update) or None if no cache
    """
    is_fresh, last_update = is_cache_fresh()

    if not last_update:
        return None

    now = datetime.now()
    age_minutes = (now - last_update).total_seconds() / 60

    return round(age_minutes, 1)
