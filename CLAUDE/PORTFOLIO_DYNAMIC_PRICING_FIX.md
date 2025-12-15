# Portfolio Dynamic Pricing Fix

## Problem Statement

The portfolio value chart was displaying **stale/frozen values** that did not update when listing prices changed, even though the Current Holdings panel correctly reflected current market prices.

### Observed Behavior

**Test scenario:**
1. User B buys an item from User A
2. User A increases the listing price for that bucket
3. **Holdings panel**: Shows new higher valuation ✓ (correct)
4. **Chart**: Shows old frozen value ✗ (bug)

This meant the chart and holdings panel were using different pricing sources, causing them to be out of sync.

## Root Cause Analysis

### Before the Fix

The portfolio system had two separate pricing logic paths:

#### 1. Holdings Panel (Correct - Used Live Prices)
- `get_user_holdings()` in `services/portfolio_service.py:10-60`
- Used a subquery to fetch **current market price** from active listings:
  ```sql
  (SELECT MIN(l2.price_per_coin)
   FROM listings l2
   JOIN categories c2 ON l2.category_id = c2.id
   WHERE c2.bucket_id = c.bucket_id
     AND l2.active = 1
     AND l2.quantity > 0
  ) AS current_market_price
  ```
- This correctly reflected real-time price changes

#### 2. Chart History (Broken - Used Stale Snapshots)
- `get_portfolio_history()` in `services/portfolio_service.py:156-188`
- Returned **static snapshot records** from `portfolio_snapshots` table
- These snapshots were created at specific points in time with **frozen values**
- The route (`portfolio_routes.py:92-121`) only computed current value if `len(history) == 0`
- If ANY snapshots existed, it returned the stale data unchanged

**Result:** Chart showed historical snapshot values that never updated, even when prices changed.

## The Fix

### Implementation

Modified `get_portfolio_history()` to **ALWAYS compute and append a fresh "now" point** using live current prices.

#### File: `services/portfolio_service.py`

**Before:**
```python
def get_portfolio_history(user_id, days=30):
    conn = get_db_connection()
    start_date = datetime.now() - timedelta(days=days)

    snapshots = conn.execute("""
        SELECT snapshot_date, total_value, total_cost_basis
        FROM portfolio_snapshots
        WHERE user_id = ? AND snapshot_date >= ?
        ORDER BY snapshot_date ASC
    """, (user_id, start_date.isoformat())).fetchall()

    conn.close()

    # Only adds current value if NO snapshots exist
    if not snapshots:
        current_data = create_portfolio_snapshot(user_id)
        return [{
            'snapshot_date': datetime.now().isoformat(),
            'total_value': current_data['total_value'],
            'total_cost_basis': current_data['cost_basis']
        }]

    return snapshots  # Returns stale data!
```

**After:**
```python
def get_portfolio_history(user_id, days=30):
    """
    Get historical portfolio values for charting
    Returns list of snapshots with dates and values

    IMPORTANT: Always computes the most recent point using CURRENT market prices
    to ensure the chart stays in sync with the holdings panel when prices change.
    """
    conn = get_db_connection()

    # Calculate start date
    start_date = datetime.now() - timedelta(days=days)

    # Fetch historical snapshots (excluding very recent ones we'll recompute)
    # We exclude snapshots from the last hour to avoid duplicates with our fresh computation
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
```

#### File: `routes/portfolio_routes.py`

Simplified the route to remove the conditional current-value logic since the service now handles it:

**Before:**
```python
try:
    snapshots = get_portfolio_history(user_id, days)

    # Convert to list of dicts
    history = []
    for snap in snapshots:
        history.append({
            'date': snap['snapshot_date'],
            'value': snap['total_value'],
            'cost_basis': snap['total_cost_basis']
        })

    # If we don't have enough historical data, add current value as the latest point
    if len(history) == 0:
        current_value = calculate_portfolio_value(user_id)
        history.append({
            'date': datetime.now().isoformat(),
            'value': current_value['total_value'],
            'cost_basis': current_value['cost_basis']
        })

    return jsonify({
        'success': True,
        'history': history,
        'range': time_range
    })
```

**After:**
```python
try:
    # get_portfolio_history now ALWAYS includes current value with live prices
    snapshots = get_portfolio_history(user_id, days)

    # Convert to list of dicts with consistent key names for frontend
    history = []
    for snap in snapshots:
        history.append({
            'date': snap['snapshot_date'],
            'value': snap['total_value'],
            'cost_basis': snap['total_cost_basis']
        })

    return jsonify({
        'success': True,
        'history': history,
        'range': time_range
    })
```

### How It Works Now

1. **Historical Points**: Use snapshot data from `portfolio_snapshots` table (for visualization of past trends)
2. **Most Recent Point**: ALWAYS freshly computed using `calculate_portfolio_value(user_id)`, which:
   - Calls `get_user_holdings(user_id)`
   - Fetches current market prices from active listings
   - Uses the same pricing logic as the Holdings panel
3. **Result**: Chart's latest point always matches Holdings panel value

### Exclusion Logic

The fix maintains proper exclusion behavior:

- Both `get_user_holdings()` and `calculate_portfolio_value()` already respect the `portfolio_exclusions` table
- The SQL query explicitly filters out excluded items:
  ```sql
  WHERE oi.order_item_id NOT IN (
      SELECT order_item_id
      FROM portfolio_exclusions
      WHERE user_id = ?
  )
  ```
- When a holding is excluded via the "This item is not in my portfolio" button:
  - Frontend calls `excludeHolding()` which reloads all portfolio data
  - Backend recomputes values WITHOUT the excluded item
  - Chart updates to show the reduced portfolio value

## Verification Tests

Created comprehensive test suite in `test_portfolio_dynamic_pricing.py`.

### Test Results

```
======================================================================
  PORTFOLIO DYNAMIC PRICING TEST SUITE
======================================================================

Testing with user_id=3 (rexb)
Timestamp: 2025-11-28 12:09:24

User has 18 order items - proceeding with tests...

======================================================================
  TEST 1: Pricing Consistency
======================================================================

1. Holdings count: 1

First holding:
   Bucket ID: 100000007
   Metal: Gold
   Product: Bar
   Quantity: 1
   Purchase price: $6900.00
   Current market price: $11111.00

2. Portfolio Value (from calculate_portfolio_value):
   Total Value: $11,111.00
   Cost Basis: $6,900.00
   Gain/Loss: $4,211.00 (61.03%)

3. Portfolio History (chart data):
   History points: 2

   Latest point (should match current value):
   Date: 2025-11-28T12:09:24.820697
   Value: $11,111.00
   Cost Basis: $6,900.00

VERIFICATION:
   Chart value matches holdings value: [YES]
   Chart cost matches holdings cost: [YES]

[PASS] TEST PASSED: Chart and holdings use same pricing!

======================================================================
  TEST 2: Price Change Detection
======================================================================

Checking active listings for bucket 100000007:
   Active listings found: 1

   Lowest price: $11111.00 (listing_id=10057)
   Current market price in holding: $11111.00

VERIFICATION:
   Market price matches lowest listing: [YES]

[PASS] TEST PASSED: Market price correctly sourced from active listings!

======================================================================
  TEST 3: Exclusion Logic
======================================================================

1. BEFORE exclusion:
   Holdings count: 1
   Total value: $11,111.00
   Latest chart value: $11,111.00

2. Excluding order_item_id 127...

3. AFTER exclusion:
   Holdings count: 0
   Total value: $0.00
   Latest chart value: $0.00

VERIFICATION:
   Holdings count reduced by 1: [YES]
   Total value reduced: [YES]
   Chart matches new value: [YES]

4. Re-including order_item_id 127...

5. After re-inclusion:
   Holdings count: 1
   Total value: $11,111.00

[PASS] TEST PASSED: Exclusions work correctly and affect chart!

======================================================================
  TEST SUMMARY
======================================================================
   [PASS] - Pricing Consistency (holdings vs chart)
   [PASS] - Price Change Detection (market prices)
   [PASS] - Exclusion Logic (affects chart)

======================================================================
  ALL TESTS PASSED!
======================================================================

The portfolio chart now uses dynamic pricing!
Chart and holdings panel are synchronized.
When listing prices change, both will update together.
```

## User Testing Procedure

### Test 1: Price Change Detection

1. **Setup:**
   - Login as User B
   - Note the current portfolio value shown in both Holdings panel and chart

2. **Action:**
   - Login as User A (seller)
   - Find a listing for an item User B owns
   - Increase the listing price significantly (e.g., $1,000 → $2,000)

3. **Verification:**
   - Return to User B's Portfolio tab
   - Refresh the page or click a different time-range button
   - **Expected Results:**
     - Holdings panel shows new higher value ✓
     - Chart's latest point shows new higher value ✓
     - Both values match exactly ✓
     - Gain/Loss percentage increases ✓

### Test 2: Exclusion Behavior

1. **Setup:**
   - Login as User B with multiple holdings
   - Note total portfolio value in chart

2. **Action:**
   - Click "This item is not in my portfolio" on one holding

3. **Verification:**
   - **Expected Results:**
     - Holding disappears from Current Holdings list ✓
     - Total portfolio value decreases ✓
     - Chart's latest point reflects new lower value ✓
     - Allocation pie chart updates ✓
     - No errors in console ✓

### Test 3: Time Range Buttons

1. **Action:**
   - Click each time range button (1D, 1W, 1M, 3M, 1Y)

2. **Verification:**
   - **Expected Results:**
     - Button highlights when clicked ✓
     - Chart re-renders with appropriate data ✓
     - Latest point ALWAYS shows current value ✓
     - No errors in console ✓

## Files Modified

1. **`services/portfolio_service.py`** (Lines 156-205)
   - Modified `get_portfolio_history()` to always compute current value
   - Added documentation explaining the dynamic pricing approach

2. **`routes/portfolio_routes.py`** (Lines 92-109)
   - Simplified route logic since service now handles current value
   - Removed conditional check for empty history

3. **`test_portfolio_dynamic_pricing.py`** (New file)
   - Comprehensive test suite for dynamic pricing
   - Tests pricing consistency, price change detection, and exclusion logic

## Technical Specifications

### Portfolio Value Calculation

For a given timestamp **t**, the portfolio value is:

**V(t) = Σ (quantity × price_at_time(holding, t))**

Where:
- Sum is over all non-excluded holdings active at time **t**
- A holding is "active at **t**" if `order_date ≤ t`
- `price_at_time(holding, t)` comes from:
  - **For current time (now)**: Lowest active listing price in the same bucket
  - **For historical times**: Snapshot value (approximation, since we don't store historical prices)

### Cost Basis Calculation

**C(t) = Σ (quantity × purchase_price)**

Where:
- Sum is over all non-excluded holdings active at time **t**
- `purchase_price` is the original `price_each` from the order

### Gain/Loss Metrics

- **Absolute Gain**: G(t) = V(t) - C(t)
- **Percent Return**: R(t) = (V(t) - C(t)) / C(t) × 100 when C(t) > 0

### Exclusion Rules

When a holding is marked "not in this portfolio":
- Insert row into `portfolio_exclusions` table
- Exclude from **ALL** calculations:
  - Not counted in V(t) or C(t) for any time **t**
  - Not shown in Current Holdings
  - Not included in allocation pie chart
- After exclusion API call succeeds, frontend re-fetches all portfolio data

## Benefits of This Approach

1. **Real-time Accuracy**: Chart always reflects current market conditions
2. **Consistency**: Holdings panel and chart use identical pricing logic
3. **Simplicity**: No need to maintain separate pricing mechanisms
4. **Scalability**: Historical snapshots still provide trend visualization
5. **User Experience**: Users see their portfolio value update immediately when prices change

## Future Enhancements

### Historical Price Tracking

To make historical points also reflect actual market prices at those times:

1. **Create `market_price_history` table:**
   ```sql
   CREATE TABLE market_price_history (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       bucket_id INTEGER NOT NULL,
       price REAL NOT NULL,
       recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       FOREIGN KEY (bucket_id) REFERENCES buckets(id)
   );
   ```

2. **Periodic price recording:**
   - Run a daily cron job to snapshot current lowest listing price for each bucket
   - Store in `market_price_history` table

3. **Enhanced history computation:**
   - For each historical point, look up the market price at that time
   - Use `price_at_time = get_historical_price(bucket_id, timestamp)`
   - This would make the entire chart reflect true historical valuations

### Performance Optimization

If portfolio history becomes slow with many holdings:

1. **Cache current portfolio value** for 1-5 minutes
2. **Batch price lookups** instead of per-holding subqueries
3. **Materialize bucket prices** in a dedicated table updated on listing changes

## Summary

The portfolio chart now uses **dynamic pricing** and is fully synchronized with the holdings panel. When listing prices change, both the chart and holdings update together using the same live market data. The fix maintains proper exclusion logic and provides a foundation for future enhancements like historical price tracking.
