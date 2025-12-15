"""
Pricing Service
Centralized pricing logic for both static and premium-to-spot pricing modes
"""

from services.spot_price_service import get_current_spot_prices, get_spot_price
from database import get_db_connection
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def convert_weight_to_troy_ounces(weight, weight_unit='oz'):
    """
    Convert weight to troy ounces

    Args:
        weight: Weight value
        weight_unit: Unit of weight (oz, g, kg, etc.)

    Returns:
        float: Weight in troy ounces
    """
    # Conversion factors to troy ounces
    conversions = {
        'oz': 1.0,  # Assume ounces are troy ounces
        'g': 0.0321507,  # grams to troy oz
        'kg': 32.1507,  # kilograms to troy oz
        'lb': 14.5833,  # pounds to troy oz
    }

    unit = weight_unit.lower()

    if unit in conversions:
        return weight * conversions[unit]
    else:
        # Default to assuming it's already in troy ounces
        logger.warning(f"Unknown weight unit '{weight_unit}', assuming troy ounces")
        return weight


def get_effective_price(listing, spot_prices=None):
    """
    Calculate the effective price per coin for a listing

    This is the SINGLE SOURCE OF TRUTH for "what is the price of this listing right now"

    Args:
        listing: Listing dict/row with pricing mode and related fields
        spot_prices: Optional dict of current spot prices (if not provided, will be fetched)

    Returns:
        float: Effective price per coin
    """
    pricing_mode = listing.get('pricing_mode', 'static')

    # STATIC MODE: Return the fixed price
    if pricing_mode == 'static':
        return listing.get('price_per_coin', 0.0)

    # PREMIUM-TO-SPOT MODE: Calculate dynamic price
    elif pricing_mode == 'premium_to_spot':
        # Get spot prices if not provided
        if spot_prices is None:
            spot_prices = get_current_spot_prices()

        # Determine which metal to use for pricing
        # Use pricing_metal if specified, otherwise fall back to category metal
        pricing_metal = listing.get('pricing_metal') or listing.get('metal')

        if not pricing_metal:
            logger.error(f"Listing {listing.get('id')} has premium_to_spot mode but no metal specified")
            # Fall back to static price or floor price
            return listing.get('price_per_coin') or listing.get('floor_price', 0.0)

        # Get spot price for this metal
        spot_price_per_oz = spot_prices.get(pricing_metal.lower())

        if not spot_price_per_oz:
            logger.warning(f"No spot price available for {pricing_metal}, using fallback price")
            # Fall back to static price or floor price
            return listing.get('price_per_coin') or listing.get('floor_price', 0.0)

        # Get weight in troy ounces
        weight = listing.get('weight', 1.0)

        # Parse weight if it's a string (e.g., "1 oz", "10 oz")
        if isinstance(weight, str):
            import re
            # Extract numeric value from strings like "1 oz", "1oz", "0.5 oz"
            match = re.match(r'([0-9.]+)\s*(oz|g|kg|lb)?', weight.strip(), re.IGNORECASE)
            if match:
                weight_value = float(match.group(1))
                weight_unit = match.group(2) or 'oz'
                weight_oz = convert_weight_to_troy_ounces(weight_value, weight_unit)
            else:
                logger.warning(f"Could not parse weight '{weight}', assuming 1.0 oz")
                weight_oz = 1.0
        else:
            # Weight is already numeric
            weight_oz = float(weight)

        # Calculate spot-based price
        # Price = (spot price per oz * weight in oz) + premium
        spot_premium = listing.get('spot_premium', 0.0)
        if spot_premium is None:
            spot_premium = 0.0

        computed_price = (spot_price_per_oz * weight_oz) + spot_premium

        # Enforce floor price (for listings)
        # Note: This is for LISTINGS. Bids use ceiling price instead (see get_effective_bid_price)
        floor_price = listing.get('floor_price', 0.0)
        if floor_price is None:
            floor_price = 0.0

        # Ensure computed_price is not None before comparison
        if computed_price is None:
            logger.error(f"Computed price is None for listing {listing.get('id')}, using floor price")
            effective_price = floor_price
        else:
            effective_price = max(computed_price, floor_price)

        return round(effective_price, 2)

    else:
        # Unknown pricing mode - fall back to static price
        logger.warning(f"Unknown pricing mode '{pricing_mode}', falling back to static price")
        return listing.get('price_per_coin', 0.0)


def get_listing_with_effective_price(listing_id):
    """
    Get a listing with its effective price calculated

    Returns:
        dict: Listing with 'effective_price' field added
    """
    conn = get_db_connection()

    listing = conn.execute("""
        SELECT
            l.*,
            c.metal,
            c.weight,
            c.product_type
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.id = ?
    """, (listing_id,)).fetchone()

    conn.close()

    if not listing:
        return None

    # Convert to dict
    listing_dict = dict(listing)

    # Calculate effective price
    effective_price = get_effective_price(listing_dict)
    listing_dict['effective_price'] = effective_price

    return listing_dict


def create_price_lock(listing_id, user_id, lock_duration_seconds=10):
    """
    Create a temporary price lock for a listing during checkout

    Args:
        listing_id: ID of the listing
        user_id: ID of the user
        lock_duration_seconds: How long the lock lasts (default 10 seconds)

    Returns:
        dict: Lock details (id, locked_price, spot_price_at_lock, expires_at)
        or None on failure
    """
    # Get the listing with current effective price
    listing = get_listing_with_effective_price(listing_id)

    if not listing:
        logger.error(f"Cannot create price lock: listing {listing_id} not found")
        return None

    locked_price = listing['effective_price']

    # If it's a premium-to-spot listing, record the spot price
    spot_price_at_lock = None
    if listing['pricing_mode'] == 'premium_to_spot':
        pricing_metal = listing.get('pricing_metal') or listing.get('metal')
        if pricing_metal:
            spot_price_at_lock = get_spot_price(pricing_metal)

    # Calculate expiration time
    expires_at = datetime.now() + timedelta(seconds=lock_duration_seconds)

    # Save to database
    conn = get_db_connection()

    try:
        conn.execute("""
            INSERT INTO price_locks (listing_id, user_id, locked_price, spot_price_at_lock, expires_at)
            VALUES (?, ?, ?, ?, ?)
        """, (listing_id, user_id, locked_price, spot_price_at_lock, expires_at.isoformat()))

        conn.commit()

        lock_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.close()

        logger.info(f"Created price lock {lock_id} for listing {listing_id}, user {user_id}: ${locked_price:.2f}")

        return {
            'id': lock_id,
            'listing_id': listing_id,
            'locked_price': locked_price,
            'spot_price_at_lock': spot_price_at_lock,
            'expires_at': expires_at.isoformat(),
            'duration_seconds': lock_duration_seconds
        }

    except Exception as e:
        logger.error(f"Error creating price lock: {e}")
        conn.close()
        return None


def get_active_price_lock(listing_id, user_id):
    """
    Get active price lock for a listing and user (if one exists)

    Returns:
        dict: Lock details or None if no active lock
    """
    conn = get_db_connection()

    lock = conn.execute("""
        SELECT *
        FROM price_locks
        WHERE listing_id = ?
          AND user_id = ?
          AND expires_at > ?
        ORDER BY created_at DESC
        LIMIT 1
    """, (listing_id, user_id, datetime.now().isoformat())).fetchone()

    conn.close()

    if not lock:
        return None

    return dict(lock)


def cleanup_expired_price_locks():
    """
    Remove expired price locks from database

    Returns:
        int: Number of locks removed
    """
    conn = get_db_connection()

    result = conn.execute("""
        DELETE FROM price_locks
        WHERE expires_at <= ?
    """, (datetime.now().isoformat(),))

    deleted_count = result.rowcount

    conn.commit()
    conn.close()

    if deleted_count > 0:
        logger.info(f"Cleaned up {deleted_count} expired price locks")

    return deleted_count


def get_price_for_order_item(order_item):
    """
    Determine the price to use for an order item

    If there's an active price lock, use the locked price
    Otherwise, use the current effective price

    Args:
        order_item: dict with listing_id, user_id, and quantity

    Returns:
        dict: {price_per_coin, total_price, locked, lock_expires_at}
    """
    listing_id = order_item.get('listing_id')
    user_id = order_item.get('user_id') or order_item.get('buyer_id')
    quantity = order_item.get('quantity', 1)

    # Check for active price lock
    price_lock = get_active_price_lock(listing_id, user_id)

    if price_lock:
        # Use locked price
        price_per_coin = price_lock['locked_price']
        locked = True
        lock_expires_at = price_lock['expires_at']

        logger.info(f"Using locked price ${price_per_coin:.2f} for listing {listing_id}")
    else:
        # Use current effective price
        listing = get_listing_with_effective_price(listing_id)

        if not listing:
            logger.error(f"Cannot get price: listing {listing_id} not found")
            return None

        price_per_coin = listing['effective_price']
        locked = False
        lock_expires_at = None

        logger.info(f"Using current price ${price_per_coin:.2f} for listing {listing_id}")

    total_price = price_per_coin * quantity

    return {
        'price_per_coin': round(price_per_coin, 2),
        'total_price': round(total_price, 2),
        'locked': locked,
        'lock_expires_at': lock_expires_at
    }


def get_effective_bid_price(bid, spot_prices=None):
    """
    Calculate the effective price for a bid

    This is the SINGLE SOURCE OF TRUTH for "what is the current price of this bid"

    For BIDS, pricing works differently than listings:
    - Static mode: Fixed price
    - Premium-to-spot mode: Spot + Premium, but capped at ceiling_price (maximum)

    Args:
        bid: Bid dict/row with pricing mode and related fields
        spot_prices: Optional dict of current spot prices (if not provided, will be fetched)

    Returns:
        float: Effective bid price (maximum price buyer will pay)
    """
    pricing_mode = bid.get('pricing_mode', 'static')

    # STATIC MODE: Return the fixed price
    if pricing_mode == 'static':
        return bid.get('price_per_coin', 0.0)

    # PREMIUM-TO-SPOT MODE: Calculate dynamic price with ceiling
    elif pricing_mode == 'premium_to_spot':
        # Get spot prices if not provided
        if spot_prices is None:
            spot_prices = get_current_spot_prices()

        # Determine which metal to use for pricing
        pricing_metal = bid.get('pricing_metal') or bid.get('metal')

        if not pricing_metal:
            logger.error(f"Bid {bid.get('id')} has premium_to_spot mode but no metal specified")
            # Fall back to static price or ceiling price
            return bid.get('price_per_coin') or bid.get('ceiling_price', 0.0)

        # Get spot price for this metal
        spot_price_per_oz = spot_prices.get(pricing_metal.lower())

        if not spot_price_per_oz:
            logger.warning(f"No spot price available for {pricing_metal}, using fallback price")
            # Fall back to static price or ceiling price
            return bid.get('price_per_coin') or bid.get('ceiling_price', 0.0)

        # Get weight in troy ounces
        weight = bid.get('weight', 1.0)

        # Parse weight if it's a string
        if isinstance(weight, str):
            import re
            match = re.match(r'([0-9.]+)\s*(oz|g|kg|lb)?', weight.strip(), re.IGNORECASE)
            if match:
                weight_value = float(match.group(1))
                weight_unit = match.group(2) or 'oz'
                weight_oz = convert_weight_to_troy_ounces(weight_value, weight_unit)
            else:
                logger.warning(f"Could not parse weight '{weight}', assuming 1.0 oz")
                weight_oz = 1.0
        else:
            weight_oz = float(weight)

        # Calculate spot-based price
        # Price = (spot price per oz * weight in oz) + premium
        spot_premium = bid.get('spot_premium', 0.0)
        if spot_premium is None:
            spot_premium = 0.0

        computed_price = (spot_price_per_oz * weight_oz) + spot_premium

        # Enforce ceiling price (MAXIMUM for bids)
        # Buyer won't pay more than ceiling_price
        ceiling_price = bid.get('ceiling_price', 0.0)
        if ceiling_price is None:
            ceiling_price = 0.0

        # Ensure computed_price is not None before comparison
        if computed_price is None:
            logger.error(f"Computed price is None for bid {bid.get('id')}, using ceiling price or 0")
            effective_price = ceiling_price if ceiling_price > 0 else 0.0
        elif ceiling_price > 0:
            effective_price = min(computed_price, ceiling_price)
        else:
            # If no ceiling set, use computed price
            effective_price = computed_price

        return round(effective_price, 2)

    else:
        # Unknown pricing mode - fall back to static price
        logger.warning(f"Unknown pricing mode '{pricing_mode}', falling back to static price")
        return bid.get('price_per_coin', 0.0)


def get_listings_with_effective_prices(listing_ids=None, category_id=None, bucket_id=None):
    """
    Get multiple listings with their effective prices

    Args:
        listing_ids: Optional list of listing IDs to fetch
        category_id: Optional category ID to filter by
        bucket_id: Optional bucket ID to filter by

    Returns:
        list: List of listing dicts with 'effective_price' field
    """
    conn = get_db_connection()

    # Build query based on filters
    query = """
        SELECT
            l.*,
            c.metal,
            c.weight,
            c.product_type,
            c.bucket_id
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE 1=1
    """

    params = []

    if listing_ids:
        placeholders = ','.join(['?' for _ in listing_ids])
        query += f" AND l.id IN ({placeholders})"
        params.extend(listing_ids)

    if category_id:
        query += " AND l.category_id = ?"
        params.append(category_id)

    if bucket_id:
        query += " AND c.bucket_id = ?"
        params.append(bucket_id)

    listings = conn.execute(query, params).fetchall()
    conn.close()

    # Get current spot prices once (for efficiency)
    spot_prices = get_current_spot_prices()

    # Calculate effective price for each listing
    result = []
    for listing in listings:
        listing_dict = dict(listing)
        listing_dict['effective_price'] = get_effective_price(listing_dict, spot_prices)
        result.append(listing_dict)

    return result


# ============================================================================
# SPREAD MODEL FUNCTIONS FOR AUTOFILL MATCHING
# ============================================================================

def can_bid_fill_listing(bid, listing, spot_prices=None):
    """
    Determine if a bid can fill a listing based on effective prices.

    Works for ALL combinations:
    - Fixed bid ↔ Fixed listing
    - Fixed bid ↔ Variable listing
    - Variable bid ↔ Fixed listing
    - Variable bid ↔ Variable listing

    Args:
        bid: Bid dict/row with pricing fields
        listing: Listing dict/row with pricing fields
        spot_prices: Optional dict of current spot prices

    Returns:
        dict: {
            'can_fill': bool,
            'bid_effective_price': float,
            'listing_effective_price': float,
            'spread': float (bid - listing, >= 0 if can_fill)
        }
    """
    # Get spot prices if not provided
    if spot_prices is None:
        spot_prices = get_current_spot_prices()

    # Calculate bid effective price
    # For static: fixed price
    # For premium-to-spot: min(spot + premium, ceiling)
    bid_effective = get_effective_bid_price(bid, spot_prices=spot_prices)

    # Calculate listing effective price
    # For static: fixed price
    # For premium-to-spot: max(spot + premium, floor)
    listing_effective = get_effective_price(listing, spot_prices=spot_prices)

    # Can fill if bid price >= listing price
    can_fill = bid_effective >= listing_effective

    # Calculate spread (buyer pays more than seller receives)
    spread = bid_effective - listing_effective

    return {
        'can_fill': can_fill,
        'bid_effective_price': round(bid_effective, 2),
        'listing_effective_price': round(listing_effective, 2),
        'spread': round(spread, 2)
    }


def calculate_trade_prices(bid, listing, quantity, spot_prices=None):
    """
    Calculate execution prices for a trade between bid and listing.

    This implements the spread model:
    - Buyer pays: bid effective price
    - Seller receives: listing effective price
    - Metex spread: bid effective price - listing effective price

    Args:
        bid: Bid dict/row with pricing fields
        listing: Listing dict/row with pricing fields
        quantity: Number of units being traded
        spot_prices: Optional dict of current spot prices

    Returns:
        dict: {
            'buyer_unit_price': float (per unit),
            'seller_unit_price': float (per unit),
            'spread_unit': float (per unit),
            'buyer_total': float (total buyer pays),
            'seller_total': float (total seller receives),
            'spread_total': float (total Metex keeps)
        }
    """
    # Get pricing info
    pricing_info = can_bid_fill_listing(bid, listing, spot_prices=spot_prices)

    if not pricing_info['can_fill']:
        logger.warning(f"Attempted to calculate trade prices for non-matching bid/listing")
        return None

    buyer_unit = pricing_info['bid_effective_price']
    seller_unit = pricing_info['listing_effective_price']
    spread_unit = pricing_info['spread']

    # Calculate totals
    buyer_total = buyer_unit * quantity
    seller_total = seller_unit * quantity
    spread_total = spread_unit * quantity

    return {
        'buyer_unit_price': round(buyer_unit, 2),
        'seller_unit_price': round(seller_unit, 2),
        'spread_unit': round(spread_unit, 2),
        'buyer_total': round(buyer_total, 2),
        'seller_total': round(seller_total, 2),
        'spread_total': round(spread_total, 2)
    }
