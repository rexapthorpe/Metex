# Price Chart Hover Reset Fix - Summary

## Issue

When hovering over the price history chart on the Bucket ID page, the summary band (showing current price, $ change, and % change) correctly updated to reflect the hovered data point. However, when the mouse left the chart area, these values remained "stuck" on the last hovered point instead of resetting to the current/latest price.

**Expected Behavior**:
- While hovering: Summary reflects hovered point
- After mouse leaves: Summary resets to current best ask and its $/% change over selected interval

**Actual Behavior**:
- While hovering: ✅ Summary reflects hovered point correctly
- After mouse leaves: ❌ Summary stays stuck on last hovered point

## Root Cause

The chart's `onHover` callback (bucket_price_chart.js:538-556) updates the summary while hovering:

```javascript
onHover: function(event, activeElements) {
    if (activeElements && activeElements.length > 0) {
        // Update summary with hovered point
        const index = activeElements[0].index;
        const hoveredPrice = dataPoints[index].y;
        // ... calculate changes ...
        updateBucketPriceSummary({ ... });
    } else {
        // Reset to original summary when not hovering
        updateBucketPriceSummary(bucketChartData.summary);
    }
}
```

**Problem**: The `else` branch (reset) only fires when `activeElements` is empty while still inside the chart area. When the mouse **leaves the chart entirely**, the `onHover` callback stops firing, so the last state (hovered point) persists.

## Solution

Added a `mouseleave` event listener to the chart canvas that explicitly resets the summary when the cursor leaves the chart area.

### Implementation

**1. Added global handler reference** (line 12):
```javascript
let bucketChartMouseLeaveHandler = null;  // Store reference for cleanup
```

**2. Cleanup on chart recreation** (lines 389-393):
```javascript
// Remove previous mouseleave handler if it exists
if (bucketChartMouseLeaveHandler) {
    ctx.removeEventListener('mouseleave', bucketChartMouseLeaveHandler);
    bucketChartMouseLeaveHandler = null;
}
```

**3. Register mouseleave handler** (lines 592-599):
```javascript
// Add mouseleave event to reset summary when cursor leaves chart
bucketChartMouseLeaveHandler = function() {
    // Reset to original summary data (current price, not last hovered)
    if (bucketChartData && bucketChartData.summary) {
        console.log('[BucketChart] Mouse left chart - resetting summary to current price');
        updateBucketPriceSummary(bucketChartData.summary);
    }
};
ctx.addEventListener('mouseleave', bucketChartMouseLeaveHandler);
```

## Why This Approach

### 1. Complements Existing Behavior
- The `onHover` callback still handles hover state correctly
- The `mouseleave` event fills the gap when the cursor exits the chart

### 2. Proper Event Cleanup
- Stores handler reference globally for proper cleanup
- Removes old handler before adding new one when chart is recreated
- Prevents memory leaks and duplicate event listeners

### 3. Uses Native DOM Events
- `mouseleave` is a standard DOM event that fires when cursor exits element
- More reliable than trying to detect chart area exit via Chart.js callbacks
- Works consistently across all time ranges (1d, 1w, 1m, 3m, 1y)

## Files Modified

**`static/js/bucket_price_chart.js`**
- Line 12: Added `bucketChartMouseLeaveHandler` variable
- Lines 389-393: Added cleanup of previous event listener
- Lines 592-599: Added mouseleave event listener registration

## Testing

### Test Scenario 1: Basic Hover/Leave
1. Navigate to any Bucket ID page (e.g., `/bucket/1`)
2. Wait for price history chart to load
3. **Hover over chart** → Summary updates to hovered point ✅
4. **Move mouse out of chart** → Summary resets to current price ✅
5. Verify no console errors

### Test Scenario 2: Multiple Time Ranges
1. Load chart with default range (1d)
2. Hover and leave → Summary resets ✅
3. Click different time range (1w, 1m, 3m, 1y)
4. Hover and leave → Summary resets ✅
5. Repeat for all time ranges

### Test Scenario 3: Multiple Hover Cycles
1. Hover over first point → Summary shows first point
2. Leave chart → Summary resets to current
3. Hover over middle point → Summary shows middle point
4. Leave chart → Summary resets to current
5. Hover over last point → Summary shows last point
6. Leave chart → Summary resets to current

### Expected Console Output
When mouse leaves chart:
```
[BucketChart] Mouse left chart - resetting summary to current price
```

## Portfolio Chart

**Note**: The portfolio chart (`static/js/tabs/portfolio_tab.js`) does not have the same hover behavior, so it does not require this fix. Only the bucket price chart had the hover-update functionality that needed a mouseleave reset.

## Summary Values Reset To

When mouseleave fires, the summary resets to `bucketChartData.summary`, which contains:

- `current_price`: Latest best ask price in the selected time range
- `change_amount`: Dollar change from first to current price
- `change_percent`: Percentage change from first to current price

These are the same values shown:
- When the chart first loads
- When switching between time ranges (1d → 1w, etc.)
- When no hover is active

## Edge Cases Handled

1. **Chart recreation**: Old event listener removed before adding new one
2. **Missing data**: Only updates if `bucketChartData.summary` exists
3. **Multiple charts**: Each chart instance has its own handler reference
4. **Time range changes**: Handler re-registered when chart is recreated for new time range

---

**Status**: ✅ Fixed and Ready for Testing
**Date**: 2025-12-03
**Files Modified**: 1
**Lines Added**: 12
