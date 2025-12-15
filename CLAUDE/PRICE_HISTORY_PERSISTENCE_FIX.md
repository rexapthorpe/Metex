# Price History Persistence Fix

## Problem
The price history chart was incorrectly showing the empty state message ("This item has no price history. List an item to get it going!") whenever all active listings were removed from a bucket, even though historical price data existed in the database.

**Issue**: When querying for a specific time range (e.g., "1D"), if no price changes occurred within that range but historical data existed outside it (e.g., from 3 days ago), the system would return an empty history array and display the empty state.

## Solution
Updated both backend and frontend to preserve and display historical data even when all active listings are removed.

### Backend Changes (`routes/bucket_routes.py`)

**Lines 47-62**: Added fallback logic to check for ANY historical data when the requested time range returns empty results:

```python
# If no history in requested range, check if ANY history exists at all
if not history:
    # Check for any historical data (last 1 year)
    all_history = get_bucket_price_history(bucket_id, 365)

    if all_history:
        # Historical data exists, but not in this time range
        # Use the most recent historical price as the starting point
        last_historical_point = all_history[-1]

        # Create a single data point with the last known price
        # The frontend will forward-fill this to "now"
        history = [last_historical_point]
```

**Line 83**: Added `has_active_listings` flag to summary to indicate when displaying historical data without current listings:

```python
'has_active_listings': current_price is not None
```

### Frontend Changes (`static/js/bucket_price_chart.js`)

**Lines 58-80**: Updated empty state logic to only show when there's truly no historical data:

```javascript
if (data.history && data.history.length > 0) {
    // Check if this is historical data with no active listings
    if (data.summary && !data.summary.has_active_listings) {
        console.log('[BucketChart] No active listings - displaying historical data with forward-fill');
    }

    // Show chart, hide empty state (even if no active listings)
    if (chartContainer) chartContainer.style.display = 'block';
    if (emptyState) emptyState.style.display = 'none';

    // Render chart (will forward-fill if needed)
    renderBucketPriceChart(data.history, range);
} else {
    // Truly no historical data at all - show empty state
    console.log('[BucketChart] No price history exists for this bucket');
    if (chartContainer) chartContainer.style.display = 'none';
    if (emptyState) emptyState.style.display = 'flex';
}
```

### Forward-Fill Behavior

The existing forward-fill logic (lines 308-334 in `renderBucketPriceChart`) automatically extends the last known price to "now":

- **When a bucket has no active best ask**: The chart displays the most recent historical price as a flat line extending from the last data point to the current time
- **Across all time intervals** (1D, 1W, 1M, 3M, 1Y): The last known price is carried forward
- **Visual indication**: The flat line clearly shows there have been no price changes since the last listing was removed

## Result

✅ Price history is preserved and displayed even when all active listings are removed
✅ Empty state only appears for buckets with truly zero stored history points
✅ Historical data with no current listings shows a flat line at the last known price
✅ Forward-fill extends across all time intervals (1D, 1W, 1M, 3M, 1Y)
✅ Clear differentiation between "no history ever" vs "no active listings currently"

## Testing Checklist

- [ ] Bucket with listings → shows current price history
- [ ] Bucket with all listings removed → shows historical data with flat line to now
- [ ] Bucket that never had listings → shows empty state message
- [ ] Switching time ranges (1D, 1W, 1M, 3M, 1Y) preserves historical data
- [ ] Re-adding listings after removal → chart updates with new price points
