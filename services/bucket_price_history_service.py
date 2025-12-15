"""
Bucket Price History Service
Tracks and manages historical best ask prices for each bucket (item type)

This service:
1. Records price changes whenever the best ask price for a bucket changes
2. Provides historical data for charting with appropriate aggregation
3. Cleans up old data (>1 year)
4. Does NOT backfill historical prices - only tracks forward from when listings exist
"""

from database import get_db_connection
from datetime import datetime, timedelta
from services.pricing_service import get_effective_price


def get_current_best_ask(bucket_id, exclude_user_id=None, packaging_styles=None):
    """
    Calculate the current best ask price for a bucket

    For isolated buckets (one-of-a-kind and sets):
    - If no active bids: price = listing price
    - If active bids exist: price = midpoint (listing_price + highest_bid) / 2

    For standard pooled buckets:
    - Price = lowest effective price among all listings

    Args:
        bucket_id: The bucket ID to check
        exclude_user_id: Optional user ID to exclude from listings (for "don't show my own" logic)
        packaging_styles: Optional list of packaging types to filter by

    Returns:
        The calculated price, or None if no listings exist
    """
    conn = get_db_connection()

    # Check if this bucket is isolated
    is_isolated_check = conn.execute("""
        SELECT is_isolated
        FROM categories
        WHERE bucket_id = ?
        LIMIT 1
    """, (bucket_id,)).fetchone()

    is_isolated = is_isolated_check['is_isolated'] if is_isolated_check else 0

    # Get all active listings in this bucket with pricing fields
    query = """
        SELECT
            l.price_per_coin, l.pricing_mode,
            l.spot_premium, l.floor_price, l.pricing_metal,
            c.metal, c.weight, c.product_type
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ?
          AND l.active = 1
          AND l.quantity > 0
    """
    params = [bucket_id]

    # Exclude specific user's listings if requested
    if exclude_user_id is not None:
        query += " AND l.seller_id != ?"
        params.append(exclude_user_id)

    # Apply packaging filters if specified
    if packaging_styles:
        packaging_placeholders = ','.join('?' * len(packaging_styles))
        query += f" AND l.packaging_type IN ({packaging_placeholders})"
        params.extend(packaging_styles)

    listings = conn.execute(query, params).fetchall()

    if not listings:
        conn.close()
        return None

    # Calculate effective price for each listing and find minimum
    min_price = None
    for listing in listings:
        listing_dict = dict(listing)
        effective_price = get_effective_price(listing_dict)

        if min_price is None or effective_price < min_price:
            min_price = effective_price

    # ISOLATED BUCKET MIDPOINT LOGIC
    if is_isolated and min_price is not None:
        # Get highest active bid for this bucket
        highest_bid_row = conn.execute("""
            SELECT MAX(b.price_per_coin) as highest_bid
            FROM bids b
            JOIN categories c ON b.category_id = c.id
            WHERE c.bucket_id = ?
              AND b.active = 1
        """, (bucket_id,)).fetchone()

        if highest_bid_row and highest_bid_row['highest_bid'] is not None:
            highest_bid = highest_bid_row['highest_bid']
            # Midpoint calculation: (listing_price + highest_bid) / 2
            min_price = (min_price + highest_bid) / 2

    conn.close()
    return min_price


def record_price_change(bucket_id, new_price):
    """
    Record a new price point for a bucket

    This should be called whenever the best ask price changes.
    It automatically checks if the price has actually changed to avoid duplicate entries.

    Args:
        bucket_id: The bucket ID
        new_price: The new best ask price

    Returns:
        True if a new record was created, False if price unchanged
    """
    if new_price is None:
        return False

    conn = get_db_connection()

    # Get the most recent price for this bucket
    last_record = conn.execute("""
        SELECT best_ask_price
        FROM bucket_price_history
        WHERE bucket_id = ?
        ORDER BY timestamp DESC
        LIMIT 1
    """, (bucket_id,)).fetchone()

    # Only record if price has changed
    if last_record:
        last_price = last_record['best_ask_price']
        # Use a small tolerance for floating point comparison
        if abs(last_price - new_price) < 0.01:
            conn.close()
            return False

    # Record the new price
    conn.execute("""
        INSERT INTO bucket_price_history (bucket_id, best_ask_price, timestamp)
        VALUES (?, ?, ?)
    """, (bucket_id, new_price, datetime.now()))

    conn.commit()
    conn.close()

    return True


def update_bucket_price(bucket_id, exclude_user_id=None):
    """
    Check and update the current best ask price for a bucket

    This is the main function to call when listings change or spot prices update.
    It calculates the current best ask and records it if it has changed.

    Args:
        bucket_id: The bucket ID to update
        exclude_user_id: Optional user ID to exclude from price calculation

    Returns:
        The current best ask price, or None if no listings
    """
    current_price = get_current_best_ask(bucket_id, exclude_user_id)

    if current_price is not None:
        record_price_change(bucket_id, current_price)

    return current_price


def get_bucket_price_history(bucket_id, days=30):
    """
    Get historical price data for a bucket WITHOUT aggregation

    Returns ALL price changes within the specified time range to preserve
    the complete step-like history of how the best ask price has changed.

    This ensures that when viewing price history, users see every price change:
    - If price went $140 → $139 → $138, all 3 points are returned
    - No aggregation or bucketing by time period
    - Chronological order from oldest to newest

    Args:
        bucket_id: The bucket ID
        days: Number of days of history to return

    Returns:
        List of dicts with 'timestamp' and 'price' keys, ordered chronologically
    """
    conn = get_db_connection()

    start_date = datetime.now() - timedelta(days=days)

    # Get all price history within the range
    raw_history = conn.execute("""
        SELECT timestamp, best_ask_price
        FROM bucket_price_history
        WHERE bucket_id = ?
          AND timestamp >= ?
        ORDER BY timestamp ASC
    """, (bucket_id, start_date)).fetchall()

    conn.close()

    if not raw_history:
        return []

    # Return ALL price changes without aggregation
    # This ensures we preserve every price point for step-like history visualization
    # (No aggregation means if price went $140 → $139 → $138, all 3 points show)
    history = []
    for record in raw_history:
        history.append({
            'timestamp': record['timestamp'],
            'price': record['best_ask_price']
        })

    return history


def _aggregate_by_hours(raw_history, hours=1):
    """
    Aggregate price history into hourly buckets
    Takes the last price in each hour bucket
    """
    if not raw_history:
        return []

    buckets = {}

    for record in raw_history:
        timestamp = datetime.fromisoformat(record['timestamp'])
        # Round down to the hour
        bucket_time = timestamp.replace(minute=0, second=0, microsecond=0)
        bucket_key = bucket_time.isoformat()

        # Keep the last (most recent) price in each bucket
        buckets[bucket_key] = {
            'timestamp': bucket_key,
            'price': record['best_ask_price']
        }

    # Sort by timestamp
    result = sorted(buckets.values(), key=lambda x: x['timestamp'])
    return result


def _aggregate_by_days(raw_history, days=1):
    """
    Aggregate price history into daily buckets
    Takes the last price in each day
    """
    if not raw_history:
        return []

    buckets = {}

    for record in raw_history:
        timestamp = datetime.fromisoformat(record['timestamp'])
        # Round down to the start of day
        bucket_time = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
        bucket_key = bucket_time.isoformat()

        # Keep the last (most recent) price in each bucket
        buckets[bucket_key] = {
            'timestamp': bucket_key,
            'price': record['best_ask_price']
        }

    # Sort by timestamp
    result = sorted(buckets.values(), key=lambda x: x['timestamp'])
    return result


def _aggregate_by_weeks(raw_history):
    """
    Aggregate price history into weekly buckets
    Takes the last price in each week
    """
    if not raw_history:
        return []

    buckets = {}

    for record in raw_history:
        timestamp = datetime.fromisoformat(record['timestamp'])
        # Get the start of the week (Monday)
        days_since_monday = timestamp.weekday()
        week_start = timestamp - timedelta(days=days_since_monday)
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        bucket_key = week_start.isoformat()

        # Keep the last (most recent) price in each bucket
        buckets[bucket_key] = {
            'timestamp': bucket_key,
            'price': record['best_ask_price']
        }

    # Sort by timestamp
    result = sorted(buckets.values(), key=lambda x: x['timestamp'])
    return result


def cleanup_old_price_history(days=365):
    """
    Remove price history older than the specified number of days

    This should be called periodically (e.g., daily cron job) to keep the database clean.
    Default is 365 days (1 year) as specified in requirements.

    Args:
        days: Number of days to keep (default: 365)

    Returns:
        Number of records deleted
    """
    conn = get_db_connection()

    cutoff_date = datetime.now() - timedelta(days=days)

    result = conn.execute("""
        DELETE FROM bucket_price_history
        WHERE timestamp < ?
    """, (cutoff_date,))

    deleted_count = result.rowcount
    conn.commit()
    conn.close()

    return deleted_count


def initialize_bucket_price(bucket_id):
    """
    Initialize price tracking for a bucket that has no history yet

    This creates the first price point based on current listings.
    Should be called when the first listing for a bucket is created.

    Args:
        bucket_id: The bucket ID to initialize

    Returns:
        The initial price, or None if no listings
    """
    current_price = get_current_best_ask(bucket_id)

    if current_price is not None:
        record_price_change(bucket_id, current_price)

    return current_price
