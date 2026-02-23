# Portfolio Exclusions - Complete Fix

## Problem Statement

Portfolio exclusions were not being applied consistently across all calculations. Specifically:

1. **Holdings list, value, cost basis, allocation** - ✓ Correctly excluded items
2. **Historical data** - ✗ **Did NOT exclude items from historical snapshots**

This meant when a user excluded an item, it would disappear from the current holdings list and reduce the current portfolio value, but the historical chart still showed values that included the excluded item at past time points.

**User Requirement:**
"When a user clicks 'This item is not in my portfolio', treat that order item as if the user never bought it" - complete removal from ALL calculations, including historical data "as if that order item had never existed at any time."

## Root Cause

### The Issue

The `portfolio_snapshots` table stores **aggregate values** (`total_value`, `total_cost_basis`) at specific points in time:

```sql
CREATE TABLE portfolio_snapshots (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    snapshot_date TIMESTAMP,
    total_value REAL,        -- Aggregate value (all items combined)
    total_cost_basis REAL,   -- Aggregate cost (all items combined)
    snapshot_type TEXT
);
```

When a snapshot was created at time T:
- If an item was NOT yet excluded, its value was included in `total_value`
- Later, if the user excluded that item, the old snapshot still showed the higher value
- We couldn't retroactively remove the item's contribution because snapshots don't store per-item data

### Example Scenario

1. **Day 1**: User has 2 items (A + B), total value = $20,000
   - Snapshot created: `total_value = $20,000`
2. **Day 5**: User excludes item B (value = $5,000)
   - Current calculations show $15,000 ✓
   - Historical snapshot from Day 1 still shows $20,000 ✗

## The Fix

Modified `get_portfolio_history()` to detect when a user has exclusions and **dynamically recompute ALL historical points** to exclude those items retroactively.

### Implementation

#### File: `services/portfolio_service.py`

Added two key features:

**1. Exclusion Detection** (Lines 169-181)
```python
def get_portfolio_history(user_id, days=30):
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
        conn.close()
        return _compute_dynamic_history(user_id, days)

    # No exclusions - use stored snapshots for performance
    # ... existing snapshot logic ...
```

**2. Dynamic History Computation** (Lines 222-324)

Created new function `_compute_dynamic_history()` that:

1. Fetches all order_items for the user (excluding currently excluded items)
2. Determines time points where portfolio composition changed (purchase dates)
3. For each time point, computes portfolio value by:
   - Checking which items existed at that time (`purchase_date <= time_point`)
   - Filtering out excluded items
   - Computing value using current market prices
   - Computing cost basis using purchase prices

```python
def _compute_dynamic_history(user_id, days=30):
    """
    Dynamically compute historical portfolio values by checking which holdings
    existed at each point in time and filtering out currently excluded items.

    This ensures that when a user excludes an item, ALL historical points
    are recomputed as if that item never existed.
    """
    conn = get_db_connection()

    # Get all non-excluded order_items with their purchase dates
    all_items = conn.execute("""
        SELECT
            oi.order_item_id,
            oi.quantity,
            oi.price_each AS purchase_price,
            o.created_at AS purchase_date,
            c.bucket_id,
            (SELECT MIN(l2.price_per_coin) FROM listings l2 ...) AS current_market_price
        FROM order_items oi
        ...
        WHERE o.buyer_id = ?
          AND oi.order_item_id NOT IN (
              SELECT order_item_id FROM portfolio_exclusions WHERE user_id = ?
          )
    """, (user_id, user_id)).fetchall()

    # Create time points at purchase dates
    time_points = [start_date]
    for item in all_items:
        purchase_dt = datetime.fromisoformat(item['purchase_date'])
        if start_date <= purchase_dt <= now:
            time_points.append(purchase_dt)
    time_points.append(now)

    # Compute value at each time point
    history = []
    for time_point in sorted(set(time_points)):
        total_value = 0.0
        total_cost = 0.0

        for item in all_items:
            purchase_dt = datetime.fromisoformat(item['purchase_date'])

            # Include item if it existed at this time point
            if purchase_dt <= time_point:
                quantity = item['quantity']
                purchase_price = item['purchase_price']
                current_price = item['current_market_price'] or purchase_price

                total_cost += quantity * purchase_price
                total_value += quantity * current_price

        history.append({
            'snapshot_date': time_point.isoformat(),
            'total_value': round(total_value, 2),
            'total_cost_basis': round(total_cost, 2)
        })

    return history
```

### Key Design Decisions

**1. Conditional Dynamic Computation**
- **If user has NO exclusions**: Use stored snapshots (fast, efficient)
- **If user HAS exclusions**: Compute dynamically (ensures correctness)

This hybrid approach maintains performance for most users while ensuring accuracy for users with exclusions.

**2. Time Points Selection**
- Start of date range
- Each purchase date (when portfolio composition changed)
- Current time

This creates a step-function chart that accurately shows when items were added to the portfolio.

**3. Current Prices for All Historical Points**
- Uses current market prices for ALL time points (including historical ones)
- This is a limitation since we don't store per-item historical prices
- Alternative would require storing price history, which is a future enhancement

## Verification

### Comprehensive Test Results

Created test suite (`test_portfolio_exclusions_complete.py`) that verifies:

```
ALL EXCLUSION TESTS PASSED!

[PASS] - Holdings list updated
[PASS] - Portfolio value decreased exactly
[PASS] - Cost basis decreased exactly
[PASS] - All historical ranges updated (1D/1W/1M/3M/1Y)
[PASS] - All historical points respect exclusion
[PASS] - Allocation updated
[PASS] - Re-inclusion restored values
```

### Test Scenario

**Setup:**
- User has 1 holding: Gold Bar
- Quantity: 1
- Purchase price: $6,900
- Current market price: $11,111

**Test Steps:**

1. **Before Exclusion:**
   - Holdings count: 1
   - Portfolio value: $11,111
   - Cost basis: $6,900
   - Allocation: Gold 100%

2. **After Exclusion:**
   - Holdings count: 0 ✓
   - Portfolio value: $0 ✓
   - Cost basis: $0 ✓
   - Allocation: (empty) ✓
   - All history ranges (1D/1W/1M/3M/1Y): $0 ✓

3. **After Re-inclusion:**
   - All values restored to original ✓

## Exclusion Logic Summary

### Where Exclusions Are Applied

**1. Current Holdings List**
- **Function:** `get_user_holdings(user_id)`
- **Logic:** SQL filter `WHERE oi.order_item_id NOT IN (SELECT order_item_id FROM portfolio_exclusions ...)`
- **Result:** Excluded items do not appear in list ✓

**2. Portfolio Value & Cost Basis**
- **Function:** `calculate_portfolio_value(user_id)`
- **Logic:** Uses `get_user_holdings()`, which filters exclusions
- **Result:** Excluded items don't contribute to totals ✓

**3. Portfolio Allocation**
- **Function:** `get_portfolio_allocation(user_id)`
- **Logic:** Uses `get_user_holdings()`, which filters exclusions
- **Result:** Excluded items don't appear in metal breakdown ✓

**4. Portfolio History (ALL RANGES)**
- **Function:** `get_portfolio_history(user_id, days)`
- **Logic:**
  - Detects if user has exclusions
  - If yes: Calls `_compute_dynamic_history()` which filters excluded items
  - If no: Uses snapshots (faster)
- **Result:** Excluded items removed from ALL historical points ✓

### Exclusion Database Schema

```sql
CREATE TABLE portfolio_exclusions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    order_item_id INTEGER NOT NULL,
    excluded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (order_item_id) REFERENCES order_items(id) ON DELETE CASCADE,
    UNIQUE(user_id, order_item_id)
);
```

### API Endpoints

**Exclude an item:**
```
POST /portfolio/exclude/<order_item_id>
```

**Re-include an item:**
```
POST /portfolio/include/<order_item_id>
```

### Frontend Behavior

When user clicks "This item is not in my portfolio":

1. **`excludeHolding(button)`** in `portfolio_tab.js` (line 497-524)
   - Calls `/portfolio/exclude/<order_item_id>`
   - Removes tile from UI with animation
   - Calls `loadPortfolioData()` to refresh ALL data

2. **`loadPortfolioData()`** (line 33-52)
   - Fetches `/portfolio/data` (holdings, value, allocation)
   - Calls `loadPortfolioHistory(currentTimeRange)` (refreshes chart)
   - All calculations now exclude the item

## User Testing Procedure

### Test 1: Basic Exclusion

1. Login and navigate to Portfolio tab
2. Note total portfolio value and holdings count
3. Click "This item is not in my portfolio" on one holding
4. **Expected Results:**
   - Holding disappears from list ✓
   - Portfolio value decreases by exact item value ✓
   - Cost basis decreases by exact item cost ✓
   - Allocation pie chart updates ✓
   - Chart shows lower values across ALL time ranges ✓

### Test 2: Multiple Items with One Exclusion

1. Start with multiple holdings (e.g., 3 items: A, B, C)
2. Note individual values:
   - Item A: $5,000 value, $4,000 cost
   - Item B: $3,000 value, $2,500 cost
   - Item C: $2,000 value, $1,800 cost
   - Total: $10,000 value, $8,300 cost

3. Exclude Item B
4. **Expected Results:**
   - Holdings count: 3 → 2 ✓
   - Portfolio value: $10,000 → $7,000 (exactly $3,000 decrease) ✓
   - Cost basis: $8,300 → $5,800 (exactly $2,500 decrease) ✓
   - Item B's metal allocation decreases or disappears ✓

### Test 3: Historical Chart Verification

1. Create a portfolio with multiple items over time
2. Wait or create snapshots at different points
3. Exclude one item
4. Click through different time ranges (1D, 1W, 1M, 3M, 1Y)
5. **Expected Results:**
   - ALL historical points show reduced values ✓
   - Chart never shows the excluded item's value at any time ✓
   - History behaves "as if item never existed" ✓

### Test 4: Re-inclusion

1. Exclude an item (portfolio value drops)
2. Later, re-include the item (via API or UI if implemented)
3. **Expected Results:**
   - Item reappears in holdings list ✓
   - Portfolio value returns to previous total ✓
   - Historical chart shows item's value again ✓

## Files Modified

1. **`services/portfolio_service.py`**
   - Modified `get_portfolio_history()` to detect exclusions and switch to dynamic computation
   - Added `_compute_dynamic_history()` for retroactive exclusion logic
   - Lines 156-324

2. **`test_portfolio_exclusions_complete.py`** (New file)
   - Comprehensive test suite for exclusion logic
   - Tests all calculations, all time ranges, re-inclusion

## Performance Considerations

### Impact on Users WITHOUT Exclusions

**No performance impact** - continues to use fast snapshot queries

### Impact on Users WITH Exclusions

Dynamic history computation is more expensive:
- Queries all order_items with purchase dates
- Computes values at multiple time points
- For users with many holdings, this could be slower

**Mitigation strategies:**
1. Most users won't have exclusions (low impact)
2. Computation is still fast for typical portfolio sizes (<100 items)
3. Future optimization: Cache dynamic history for 1-5 minutes

### Future Enhancements

**1. Per-Item Snapshots**

Store individual item values over time:
```sql
CREATE TABLE portfolio_item_snapshots (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    order_item_id INTEGER,
    snapshot_date TIMESTAMP,
    value REAL,
    cost_basis REAL
);
```

Benefits:
- Can retroactively exclude items from aggregate snapshots
- Accurate historical values even with exclusions
- Better performance than full dynamic computation

**2. Exclusion Timestamp Awareness**

When displaying history, only exclude items for points after exclusion_date:
- Before exclusion: Show item's value
- After exclusion: Don't show item's value

This would give a more accurate historical view of when the exclusion occurred.

**3. Cached Dynamic History**

For users with exclusions, cache the computed history for 5 minutes:
- First request: Compute dynamically (slow)
- Subsequent requests within 5 min: Return cached result (fast)
- Invalidate cache when exclusions change

## Summary

Portfolio exclusions now work correctly across **ALL** calculations:

- ✓ Current holdings list
- ✓ Portfolio value and cost basis
- ✓ Historical time-series data (all ranges: 1D/1W/1M/3M/1Y)
- ✓ Allocation by metal

When a user excludes an item, the system treats it "as if the user never bought it" - complete removal from all calculations, including retroactive removal from historical data.

The implementation uses a hybrid approach:
- Users without exclusions: Fast (uses snapshots)
- Users with exclusions: Accurate (dynamic computation)

All tests pass, verifying exact value decreases and complete removal from all portfolio metrics.
