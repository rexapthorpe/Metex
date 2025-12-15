# Monotonic Interpolation Implementation Summary

## Overview
Refined the bucket price history chart to use monotonic cubic spline interpolation, preventing impossible vertical self-overlaps while maintaining smooth, visually appealing curves. Also changed the default time interval from 1M to 1D.

## Problem Statement
The previous implementation used Bezier curve smoothing (`tension: 0.4`) which could create visual "loops" where the price line appears to double back on itself vertically. This is mathematically impossible since price cannot have two different values at the same timestamp, creating a confusing and misleading visualization.

## Solution Implemented

### 1. Monotonic Cubic Spline Interpolation
**File:** `static/js/bucket_price_chart.js` (Lines 404-405)

**Changed from:**
```javascript
tension: 0.4,
```

**Changed to:**
```javascript
cubicInterpolationMode: 'monotone',  // Use monotone cubic spline to prevent vertical loops
tension: 0,  // Disable Bezier tension (monotone handles smoothing)
```

**How it works:**
- Chart.js's `'monotone'` mode uses a monotone cubic interpolation algorithm
- Guarantees the curve never reverses direction between data points
- Prevents vertical self-overlaps and impossible "loops"
- Still provides smooth, visually appealing curves
- May slightly round sharp peaks/valleys, but stays faithful to overall trend

**Benefits:**
- ✅ No vertical loops or impossible price overlaps
- ✅ Mathematically sound visualization
- ✅ Smooth appearance without artifacts
- ✅ Faithful to data trends
- ✅ Professional, trustworthy appearance

### 2. Timestamp Deduplication Logic
**File:** `static/js/bucket_price_chart.js` (Lines 247-263)

**Added:**
```javascript
// Handle duplicate or extremely close timestamps to prevent degenerate curve artifacts
// Add tiny offsets (milliseconds) purely for rendering while preserving data integrity
for (let i = 1; i < chartData.length; i++) {
    const prevDate = chartData[i - 1].timestamp instanceof Date ?
        chartData[i - 1].timestamp : new Date(chartData[i - 1].timestamp);
    const currDate = chartData[i].timestamp instanceof Date ?
        chartData[i].timestamp : new Date(chartData[i].timestamp);

    // If timestamps are identical or within 1 second, add small offset
    const timeDiff = currDate.getTime() - prevDate.getTime();
    if (timeDiff < 1000) {
        // Offset by i milliseconds to maintain ordering
        const offsetDate = new Date(prevDate.getTime() + i);
        chartData[i].timestamp = offsetDate;
        console.log('[BucketChart] Adjusted close timestamp:', currDate, '->', offsetDate);
    }
}
```

**How it works:**
- Detects when two consecutive data points have identical or very close timestamps (< 1 second apart)
- Adds tiny millisecond offsets purely for rendering purposes
- Preserves data integrity (actual price values unchanged)
- Prevents degenerate curve artifacts from duplicate x-coordinates
- Maintains proper chronological ordering

**Why this is needed:**
- Two points at identical timestamps would create a vertical line
- Monotone interpolation needs distinct x-coordinates to work properly
- Tiny offsets (milliseconds) are imperceptible to users but fix mathematical edge case

### 3. Default Interval Changed to 1D
**File:** `static/js/bucket_price_chart.js` (Line 10)

**Changed from:**
```javascript
let currentBucketTimeRange = '1m';
```

**Changed to:**
```javascript
let currentBucketTimeRange = '1d';  // Default to 1D instead of 1M
```

**File:** `templates/view_bucket.html` (Line 359)

**Changed from:**
```html
<button class="bucket-time-btn" data-range="1d">1D</button>
<button class="bucket-time-btn" data-range="1w">1W</button>
<button class="bucket-time-btn active" data-range="1m">1M</button>
```

**Changed to:**
```html
<button class="bucket-time-btn active" data-range="1d">1D</button>
<button class="bucket-time-btn" data-range="1w">1W</button>
<button class="bucket-time-btn" data-range="1m">1M</button>
```

**Benefits:**
- Users see most recent 24-hour price activity by default
- More immediately relevant than 30-day view
- Aligns with common financial chart conventions (intraday as default)

## Consistent Application Across All Intervals

The monotonic interpolation is applied uniformly across all time ranges:
- **1D** (24 hours) - Rolling window, 3-hour ticks
- **1W** (7 days) - Daily ticks
- **1M** (30 days) - Every 5 days
- **3M** (90 days) - Every 2 weeks
- **1Y** (365 days) - Monthly ticks

All intervals use the same chart configuration with `cubicInterpolationMode: 'monotone'`, ensuring consistent behavior regardless of time range selected.

## Mathematical Background

### What is Monotonic Cubic Interpolation?
Monotonic cubic interpolation is a method of drawing smooth curves through data points with the following properties:

1. **Monotonicity preservation:** If the data is increasing (or decreasing) between two points, the curve is also strictly increasing (or decreasing) - no reversals
2. **C1 continuity:** The curve and its first derivative are continuous (smooth, no sharp corners)
3. **Local behavior:** The curve between two points only depends on nearby points, not the entire dataset

### Why Not Regular Cubic Splines?
Regular cubic splines (Bezier curves with tension) can "overshoot" at local extrema:
- Between an increase and a decrease, the curve might go higher than both points
- This creates a visual "loop" when projected onto the Y-axis
- With price data, this makes it look like the price was at two different values simultaneously

### Monotone Cubic Spline Algorithm
Chart.js likely uses the **Fritsch-Carlson method** or similar:
1. Compute slopes (derivatives) at each data point
2. Adjust slopes to prevent overshoot
3. Use adjusted slopes to construct cubic polynomial segments
4. Result: Smooth curve that never overshoots local extrema

**Trade-off:** May slightly "flatten" sharp peaks compared to Bezier curves, but this is acceptable since it maintains visual accuracy.

## Testing

### Test File Created: `test_monotonic_interpolation.html`

Comprehensive test suite with visual comparisons:

#### Test 1: Side-by-Side Comparison
- **Left:** Old behavior (Bezier, tension 0.4) - Orange line showing potential loops
- **Right:** New behavior (Monotone cubic) - Blue line with guaranteed no loops
- Uses sharp price change data that would expose looping issues

#### Test 2: Duplicate/Close Timestamps
- Tests the timestamp deduplication logic
- Shows that points within 1 second are automatically offset
- Validates that the curve renders correctly without vertical artifacts

#### Test 3: Sharp Price Changes
- Rapid increases/decreases that stress-test the interpolation
- Demonstrates that monotone prevents overshooting
- Peaks may be slightly rounded but no impossible loops

#### Test 4: All Intervals Consistency
- Switch between 1D, 1W, 1M, 3M, 1Y
- Confirms monotonic behavior is consistent across all ranges
- Validates that 1D is the default active tab

### How to Test
1. Open `test_monotonic_interpolation.html` in browser
2. Compare old vs. new behavior in side-by-side charts
3. Look for any vertical loops in the orange line (old) that are absent in blue line (new)
4. Switch time ranges to verify consistent behavior
5. Check that duplicate timestamp data renders smoothly

## Files Modified

### `static/js/bucket_price_chart.js`
- **Line 10:** Changed default time range from `'1m'` to `'1d'`
- **Lines 247-263:** Added timestamp deduplication logic for close/duplicate timestamps
- **Lines 404-405:** Changed from Bezier tension to monotonic cubic interpolation

### `templates/view_bucket.html`
- **Line 359:** Moved `active` class from 1M button to 1D button

## Files Created
- `test_monotonic_interpolation.html` - Visual test suite with side-by-side comparisons
- `MONOTONIC_INTERPOLATION_SUMMARY.md` - This documentation

## Backward Compatibility
✅ Fully backward compatible:
- Chart.js built-in feature (no new dependencies)
- API responses unchanged
- Existing data formats work as-is
- No breaking changes to function signatures

## Performance Impact
✅ Minimal or positive:
- Monotone cubic interpolation is computationally similar to Bezier
- O(n) complexity for n data points
- Timestamp deduplication is O(n) single pass
- No performance degradation

## Visual Comparison

### Before (Bezier with tension: 0.4)
```
Price
  ^
  |     /\
  |    /  \___
  |   /   /   \
  |  /   /     \
  | /   |       \
  |/____|________\___> Time
      ↑ Loop/Overshoot
```

### After (Monotone cubic spline)
```
Price
  ^
  |     __
  |    /  \___
  |   /       \
  |  /         \
  | /           \
  |/_____________\___> Time
    ✓ No loops, faithful curve
```

## Key Benefits Summary

| Aspect | Old Behavior | New Behavior |
|--------|-------------|--------------|
| **Curve Type** | Bezier (tension 0.4) | Monotone cubic spline |
| **Vertical Loops** | ❌ Can occur | ✅ Impossible |
| **Visual Accuracy** | ⚠️ May mislead | ✅ Mathematically sound |
| **Smoothness** | Smooth | Smooth |
| **Peak Rounding** | Sharp peaks | Slightly rounded (accurate) |
| **Duplicate Timestamps** | ⚠️ May artifact | ✅ Auto-handled |
| **Consistency** | N/A | ✅ All intervals (1D-1Y) |
| **Default View** | 1M (30 days) | 1D (24 hours) |

## User Impact

### What Users Will Notice
1. **No more confusing loops:** Price lines now clearly show price moving in one direction at a time
2. **Trustworthy visualization:** Chart accurately represents price behavior
3. **Better default view:** Opens to 24-hour view instead of 30-day view
4. **Consistent experience:** Same smooth, accurate rendering across all time ranges

### What Users Won't Notice (But Benefits Them)
1. Timestamp deduplication (happens invisibly)
2. Mathematical correctness of the interpolation
3. Prevention of rendering artifacts

## Future Enhancements (Optional)
- Add a toggle to switch between monotone and linear interpolation
- Show tooltip indicating when timestamps were adjusted
- Provide option for step chart (no interpolation) for ultra-precise view
- Add animation when switching between interpolation modes

## References
- **Chart.js Documentation:** https://www.chartjs.org/docs/latest/charts/line.html#cubicinterpolationmode
- **Fritsch-Carlson Algorithm:** Original monotone cubic interpolation method
- **Monotone Cubic Spline:** https://en.wikipedia.org/wiki/Monotone_cubic_interpolation

## Conclusion
The monotonic cubic spline interpolation provides a mathematically sound, visually accurate representation of price history that prevents impossible vertical self-overlaps. Combined with timestamp deduplication and a better default interval (1D), the bucket price history chart now delivers a professional, trustworthy experience for users tracking price changes over time.
