"""
Portfolio Service
Handles all portfolio-related calculations and data processing
"""

from database import get_db_connection
from datetime import datetime, timedelta
from services.pricing_service import get_effective_price


def get_user_holdings(user_id):
    """
    Get all holdings (order items) for a user, excluding items marked as excluded
    Returns list of holdings with current market values calculated using effective pricing
    """
    conn = get_db_connection()

    # Get holdings without current_market_price (we'll calculate it separately using effective pricing)
    holdings = conn.execute("""
        SELECT
            oi.order_item_id,
            oi.order_id,
            oi.quantity,
            oi.price_each AS purchase_price,
            c.bucket_id,
            c.metal,
            c.product_type,
            c.weight,
            c.mint,
            c.year,
            c.finish,
            c.grade,
            c.purity,
            c.product_line,
            c.coin_series,
            c.special_designation,
            l.image_url,
            o.created_at AS purchase_date,
            o.status AS order_status
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.id
        JOIN listings l ON oi.listing_id = l.id
        JOIN categories c ON l.category_id = c.id
        WHERE o.buyer_id = ?
          AND oi.order_item_id NOT IN (
              SELECT order_item_id
              FROM portfolio_exclusions
              WHERE user_id = ?
          )
        ORDER BY o.created_at DESC
    """, (user_id, user_id)).fetchall()

    # Calculate current market price for each holding using effective pricing
    holdings_with_prices = []
    for holding in holdings:
        holding_dict = dict(holding)

        # Get current market price using effective pricing
        current_price = _get_current_market_price_for_bucket(conn, holding_dict['bucket_id'])
        holding_dict['current_market_price'] = current_price

        holdings_with_prices.append(holding_dict)

    conn.close()
    return holdings_with_prices


def _get_current_market_price_for_bucket(conn, bucket_id):
    """
    Helper function to calculate the current lowest effective price for a bucket
    Accounts for both static and premium-to-spot pricing modes
    """
    # Get all active listings in this bucket with pricing fields
    listings = conn.execute("""
        SELECT
            l.price_per_coin, l.pricing_mode,
            l.spot_premium, l.floor_price, l.pricing_metal,
            c.metal, c.weight, c.product_type
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ?
          AND l.active = 1
          AND l.quantity > 0
    """, (bucket_id,)).fetchall()

    if not listings:
        return None

    # Calculate effective price for each listing and find minimum
    min_price = None
    for listing in listings:
        listing_dict = dict(listing)
        effective_price = get_effective_price(listing_dict)

        if min_price is None or effective_price < min_price:
            min_price = effective_price

    return min_price


def calculate_portfolio_value(user_id):
    """
    Calculate current total portfolio value
    Returns dict with total_value, cost_basis, and gain/loss info
    """
    holdings = get_user_holdings(user_id)

    total_value = 0
    total_cost = 0

    for holding in holdings:
        quantity = holding['quantity']
        purchase_price = holding['purchase_price']
        current_price = holding['current_market_price']

        # Add to cost basis
        total_cost += quantity * purchase_price

        # Add to current value (use purchase price if no market price available)
        if current_price:
            total_value += quantity * current_price
        else:
            total_value += quantity * purchase_price

    return {
        'total_value': round(total_value, 2),
        'cost_basis': round(total_cost, 2),
        'gain_loss': round(total_value - total_cost, 2),
        'gain_loss_percent': round(((total_value - total_cost) / total_cost * 100), 2) if total_cost > 0 else 0,
        'holdings_count': len(holdings)
    }


def get_portfolio_allocation(user_id):
    """
    Calculate portfolio allocation by metal type
    Returns list of allocations with percentages and values
    """
    holdings = get_user_holdings(user_id)

    # Group by metal type
    allocation = {}
    total_value = 0

    for holding in holdings:
        metal = holding['metal']
        quantity = holding['quantity']
        current_price = holding['current_market_price'] or holding['purchase_price']

        value = quantity * current_price
        total_value += value

        if metal in allocation:
            allocation[metal] += value
        else:
            allocation[metal] = value

    # Calculate percentages
    result = []
    for metal, value in allocation.items():
        percentage = (value / total_value * 100) if total_value > 0 else 0
        result.append({
            'metal': metal,
            'value': round(value, 2),
            'percentage': round(percentage, 2)
        })

    # Sort by value descending
    result.sort(key=lambda x: x['value'], reverse=True)

    return result


def create_portfolio_snapshot(user_id):
    """
    Create a snapshot of current portfolio value
    Used for historical tracking
    """
    conn = get_db_connection()

    portfolio_data = calculate_portfolio_value(user_id)

    conn.execute("""
        INSERT INTO portfolio_snapshots (user_id, total_value, total_cost_basis, snapshot_type)
        VALUES (?, ?, ?, 'auto')
    """, (user_id, portfolio_data['total_value'], portfolio_data['cost_basis']))

    conn.commit()
    conn.close()

    return portfolio_data


def get_portfolio_history(user_id, days=30):
    """
    Get historical portfolio values for charting
    Returns list of snapshots with dates and values

    IMPORTANT:
    - Always computes the most recent point using CURRENT market prices
    - If user has exclusions, recomputes ALL historical points to ensure
      excluded items never appear in history (as if never purchased)
    """
    conn = get_db_connection()

    # Check if user has any exclusions
    exclusions_count = conn.execute("""
        SELECT COUNT(*) as count
        FROM portfolio_exclusions
        WHERE user_id = ?
    """, (user_id,)).fetchone()['count']

    has_exclusions = exclusions_count > 0

    if has_exclusions:
        # User has exclusions - recompute ALL historical points dynamically
        # to ensure excluded items never appear in history
        conn.close()
        return _compute_dynamic_history(user_id, days)

    # No exclusions - use stored snapshots for performance
    start_date = datetime.now() - timedelta(days=days)
    one_hour_ago = datetime.now() - timedelta(hours=1)

    snapshots = conn.execute("""
        SELECT
            snapshot_date,
            total_value,
            total_cost_basis
        FROM portfolio_snapshots
        WHERE user_id = ?
          AND snapshot_date >= ?
          AND snapshot_date < ?
        ORDER BY snapshot_date ASC
    """, (user_id, start_date.isoformat(), one_hour_ago.isoformat())).fetchall()

    conn.close()

    # Convert snapshots to list of dicts
    history = []
    for snap in snapshots:
        history.append({
            'snapshot_date': snap['snapshot_date'],
            'total_value': snap['total_value'],
            'total_cost_basis': snap['total_cost_basis']
        })

    # ALWAYS compute and append current value with LIVE prices
    # This ensures chart updates when market prices change
    current_data = calculate_portfolio_value(user_id)
    history.append({
        'snapshot_date': datetime.now().isoformat(),
        'total_value': current_data['total_value'],
        'total_cost_basis': current_data['cost_basis']
    })

    return history


def _compute_dynamic_history(user_id, days=30):
    """
    Dynamically compute historical portfolio values by checking which holdings
    existed at each point in time and filtering out currently excluded items.

    This ensures that when a user excludes an item, ALL historical points
    are recomputed as if that item never existed.

    NOTE: Uses current market prices (with effective pricing) for all historical points
    since we don't store per-item historical prices.
    """
    conn = get_db_connection()

    # Get all order_items for this user with their purchase dates (without current_market_price)
    all_items = conn.execute("""
        SELECT
            oi.order_item_id,
            oi.quantity,
            oi.price_each AS purchase_price,
            o.created_at AS purchase_date,
            c.bucket_id
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.id
        JOIN listings l ON oi.listing_id = l.id
        JOIN categories c ON l.category_id = c.id
        WHERE o.buyer_id = ?
          AND oi.order_item_id NOT IN (
              SELECT order_item_id
              FROM portfolio_exclusions
              WHERE user_id = ?
          )
        ORDER BY o.created_at ASC
    """, (user_id, user_id)).fetchall()

    # Calculate current market price for each item using effective pricing
    items_with_prices = []
    for item in all_items:
        item_dict = dict(item)
        current_price = _get_current_market_price_for_bucket(conn, item_dict['bucket_id'])
        item_dict['current_market_price'] = current_price
        items_with_prices.append(item_dict)

    conn.close()

    all_items = items_with_prices

    if not all_items:
        # No holdings after exclusions - return zero value
        return [{
            'snapshot_date': datetime.now().isoformat(),
            'total_value': 0.0,
            'total_cost_basis': 0.0
        }]

    # Determine time points to compute
    start_date = datetime.now() - timedelta(days=days)
    now = datetime.now()

    # Create time points (start of range + now)
    # We'll add intermediate points if we have actual purchase dates in the range
    time_points = []

    # Add start of range
    time_points.append(start_date)

    # Add purchase dates that fall within the range (these create step changes in portfolio value)
    for item in all_items:
        purchase_dt = datetime.fromisoformat(item['purchase_date'])
        if start_date <= purchase_dt <= now:
            time_points.append(purchase_dt)

    # Add current time
    time_points.append(now)

    # Remove duplicates and sort
    time_points = sorted(set(time_points))

    # Compute portfolio value at each time point
    history = []
    for time_point in time_points:
        # Determine which items existed at this time
        total_value = 0.0
        total_cost = 0.0

        for item in all_items:
            purchase_dt = datetime.fromisoformat(item['purchase_date'])

            # Include item if it was purchased on or before this time point
            if purchase_dt <= time_point:
                quantity = item['quantity']
                purchase_price = item['purchase_price']
                current_price = item['current_market_price'] or purchase_price

                # Cost basis never changes (always purchase price)
                total_cost += quantity * purchase_price

                # Value uses current market price
                total_value += quantity * current_price

        history.append({
            'snapshot_date': time_point.isoformat(),
            'total_value': round(total_value, 2),
            'total_cost_basis': round(total_cost, 2)
        })

    return history


def exclude_holding(user_id, order_item_id):
    """
    Mark an order item as excluded from portfolio
    """
    conn = get_db_connection()

    try:
        conn.execute("""
            INSERT OR IGNORE INTO portfolio_exclusions (user_id, order_item_id)
            VALUES (?, ?)
        """, (user_id, order_item_id))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        conn.close()
        print(f"Error excluding holding: {e}")
        return False


def include_holding(user_id, order_item_id):
    """
    Remove an order item from exclusions (re-include in portfolio)
    """
    conn = get_db_connection()

    try:
        conn.execute("""
            DELETE FROM portfolio_exclusions
            WHERE user_id = ? AND order_item_id = ?
        """, (user_id, order_item_id))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        conn.close()
        print(f"Error including holding: {e}")
        return False
