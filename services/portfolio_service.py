"""
Portfolio Service
Handles all portfolio-related calculations and data processing
"""

from database import get_db_connection
from datetime import datetime, timedelta
from services.pricing_service import get_effective_price
import time


def get_user_holdings(user_id):
    """
    Get all holdings (order items) for a user, excluding items marked as excluded
    Returns list of holdings consolidated by bucket_id with aggregated quantities and values
    """
    conn = get_db_connection()

    # Get all holdings (individual lots)
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
            l.graded,
            l.grading_service,
            c.is_isolated,
            l.isolated_type,
            l.issue_number,
            l.issue_total,
            o.created_at AS purchase_date,
            o.status AS order_status,
            u.username AS seller_username
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.id
        JOIN listings l ON oi.listing_id = l.id
        JOIN categories c ON l.category_id = c.id
        LEFT JOIN users u ON l.seller_id = u.id
        WHERE o.buyer_id = ?
          AND oi.order_item_id NOT IN (
              SELECT order_item_id
              FROM portfolio_exclusions
              WHERE user_id = ?
          )
        ORDER BY o.created_at DESC
    """, (user_id, user_id)).fetchall()

    # Group holdings by bucket_id and aggregate
    consolidated_holdings = {}

    for holding in holdings:
        holding_dict = dict(holding)
        bucket_id = holding_dict['bucket_id']

        if bucket_id not in consolidated_holdings:
            # First occurrence of this bucket - create consolidated entry
            # Get current market price using effective pricing
            current_price = _get_current_market_price_for_bucket(conn, bucket_id)

            consolidated_holdings[bucket_id] = {
                'bucket_id': bucket_id,
                'metal': holding_dict['metal'],
                'product_type': holding_dict['product_type'],
                'weight': holding_dict['weight'],
                'mint': holding_dict['mint'],
                'year': holding_dict['year'],
                'finish': holding_dict['finish'],
                'grade': holding_dict['grade'],
                'purity': holding_dict['purity'],
                'product_line': holding_dict['product_line'],
                'coin_series': holding_dict['coin_series'],
                'special_designation': holding_dict['special_designation'],
                'image_url': holding_dict['image_url'],
                'graded': holding_dict['graded'],
                'grading_service': holding_dict['grading_service'],
                'is_isolated': holding_dict['is_isolated'],
                'isolated_type': holding_dict['isolated_type'],
                'issue_number': holding_dict['issue_number'],
                'issue_total': holding_dict['issue_total'],
                'seller_username': holding_dict['seller_username'],
                'purchase_date': holding_dict['purchase_date'],  # Use earliest purchase date
                'current_market_price': current_price,
                'quantity': 0,  # Will be summed
                'total_cost_basis': 0.0,  # Will be summed
                'order_item_ids': []  # Track all order_item_ids for this bucket
            }

        # Aggregate quantities and cost basis
        quantity = holding_dict['quantity']
        purchase_price = holding_dict['purchase_price']
        cost_basis = quantity * purchase_price

        consolidated_holdings[bucket_id]['quantity'] += quantity
        consolidated_holdings[bucket_id]['total_cost_basis'] += cost_basis
        consolidated_holdings[bucket_id]['order_item_ids'].append(holding_dict['order_item_id'])

    # Convert to list and calculate average purchase price and values
    holdings_list = []
    for bucket_id, holding in consolidated_holdings.items():
        # Calculate average purchase price (for display consistency)
        holding['purchase_price'] = holding['total_cost_basis'] / holding['quantity'] if holding['quantity'] > 0 else 0

        # Calculate current value and gain/loss
        current_price = holding['current_market_price'] or holding['purchase_price']
        holding['current_value'] = holding['quantity'] * current_price
        holding['gain_loss'] = holding['current_value'] - holding['total_cost_basis']
        holding['gain_loss_percent'] = (holding['gain_loss'] / holding['total_cost_basis'] * 100) if holding['total_cost_basis'] > 0 else 0

        # For compatibility with existing code, also set cost_basis
        holding['cost_basis'] = holding['total_cost_basis']

        holdings_list.append(holding)

    conn.close()
    return holdings_list


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
    - Always uses dynamic computation to ensure accurate historical representation
    - Historical points show cost basis (purchase prices)
    - Current point shows current market value
    - This accurately reflects gains/losses over time
    """
    # Always use dynamic computation for consistent, accurate results
    # This ensures the chart properly reflects acquisitions and market changes
    return _compute_dynamic_history(user_id, days)


def _compute_dynamic_history(user_id, days=30):
    """
    Dynamically compute historical portfolio values by checking which holdings
    existed at each point in time and filtering out currently excluded items.

    This ensures that when a user excludes an item, ALL historical points
    are recomputed as if that item never existed.

    IMPORTANT: Historical points use purchase prices to show actual cost basis growth.
    Only the final/current point uses current market prices to show current value.
    This accurately reflects gains/losses over time.

    UNIFORM INTERVALS: Generates evenly-spaced time points for consistent x-axis spacing.
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
            'snapshot_date': datetime.utcnow().isoformat(),
            'total_value': 0.0,
            'total_cost_basis': 0.0
        }]

    # Use local time to match bucket chart behavior and display correct timezone
    # Determine uniform time points based on the selected range
    start_date = datetime.now() - timedelta(days=days)
    now = datetime.now()

    # Generate UNIFORM time points based on range
    # This ensures consistent x-axis spacing regardless of purchase dates
    time_points = []

    if days == 1:
        # 1D: Every hour (24 points)
        interval_hours = 1
        num_points = 24
        for i in range(num_points + 1):
            time_points.append(start_date + timedelta(hours=i * interval_hours))
    elif days == 7:
        # 1W: Every day (7 points)
        for i in range(8):
            time_points.append(start_date + timedelta(days=i))
    elif days == 30:
        # 1M: Every day (30 points)
        for i in range(31):
            time_points.append(start_date + timedelta(days=i))
    elif days == 90:
        # 3M: Every 3 days (~30 points)
        for i in range(31):
            time_points.append(start_date + timedelta(days=i * 3))
    elif days == 365:
        # 1Y: Every week (~52 points)
        for i in range(53):
            time_points.append(start_date + timedelta(weeks=i))
    else:
        # Default: Daily intervals
        num_days = days + 1
        for i in range(num_days):
            time_points.append(start_date + timedelta(days=i))

    # Ensure the last point is exactly 'now' for current market value
    time_points[-1] = now

    # Remove any points beyond 'now' and sort
    time_points = sorted([tp for tp in time_points if tp <= now])

    # Log for debugging
    print(f"[Portfolio History] Computing for {len(time_points)} time points")
    print(f"[Portfolio History] Time range: {start_date} to {now}")
    if all_items:
        first_purchase = datetime.fromisoformat(all_items[0]['purchase_date'])
        print(f"[Portfolio History] First purchase date: {first_purchase}")
        print(f"[Portfolio History] Total items: {len(all_items)}")

    # Compute portfolio value at each time point
    history = []
    for i, time_point in enumerate(time_points):
        # Determine if this is the current/final time point
        is_current_point = (i == len(time_points) - 1)

        # Determine which items existed at this time
        total_value = 0.0
        total_cost = 0.0

        for item in all_items:
            # Parse purchase date - stored as UTC in database
            purchase_dt_utc = datetime.fromisoformat(item['purchase_date'])

            # Convert UTC to local time for comparison with time_point (which is local)
            # Database uses datetime('now') which is UTC, but we compare with datetime.now() which is local
            # Get system UTC offset (seconds east of UTC, negative for western timezones)
            utc_offset_seconds = time.localtime().tm_gmtoff if hasattr(time.localtime(), 'tm_gmtoff') else -time.timezone
            utc_offset_hours = utc_offset_seconds / 3600
            # Convert: local_time = utc_time + offset (e.g., UTC 14:00 + (-5) = 09:00 EST)
            purchase_dt = purchase_dt_utc + timedelta(hours=utc_offset_hours)

            # Include item if it was purchased on or before this time point
            if purchase_dt <= time_point:
                quantity = item['quantity']
                purchase_price = item['purchase_price']
                current_price = item['current_market_price'] or purchase_price

                # Cost basis never changes (always purchase price)
                total_cost += quantity * purchase_price

                # For historical points: use purchase price (shows actual portfolio growth)
                # For current point: use current market price (shows current value)
                if is_current_point:
                    # Current point - use live market prices
                    total_value += quantity * current_price
                else:
                    # Historical point - use purchase price (what it was worth when acquired)
                    total_value += quantity * purchase_price

        history.append({
            'snapshot_date': time_point.isoformat(),
            'total_value': round(total_value, 2),
            'total_cost_basis': round(total_cost, 2)
        })

    # Log summary of computed history
    if history:
        print(f"[Portfolio History] Computed {len(history)} points")
        print(f"[Portfolio History] First value: ${history[0]['total_value']}, Last value: ${history[-1]['total_value']}")
    else:
        print(f"[Portfolio History] No history computed (empty result)")

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
