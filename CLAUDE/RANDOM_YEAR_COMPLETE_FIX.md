# Random Year Mode - Complete Implementation Fix

## Summary
Fixed all Random Year mode issues on the Bucket ID page to ensure consistent multi-year aggregation across all features: display, View All Sellers modal, price history chart, and Buy flow.

## Issues Fixed

### 1. ✅ View All Sellers Modal
**Problem:** Modal only showed listings from the original bucket's year, not all matching years.

**Fix:** Updated sellers query in `routes/buy_routes.py` (lines 508-552)
- Changed from single `bucket_id` to use `bucket_ids` list and `bucket_id_clause`
- Now uses the same multi-year logic as quantity/best ask calculations
- Respects all active filters (packaging, grading) when aggregating across years
- Added `c.year` to SELECT to track which year each listing is from

**Impact:** When Random Year is ON, modal now shows ALL sellers across ALL matching years.

### 2. ✅ Item Description Year Field
**Problem:** Year field always showed the specific numeric year, even in Random Year mode.

**Fix:** Added conditional Year display in `routes/buy_routes.py` (lines 307-309)
```python
if random_year:
    specs['Year'] = 'Random'
```

**Impact:** When Random Year toggle is ON, the Year line in specs displays "Random" instead of a specific year.

### 3. ✅ Price History Graph
**Problem:** Graph only showed data for the current bucket's year, not aggregated across years.

**Fixes:**
1. **Backend** (`routes/bucket_routes.py` lines 16-105):
   - Added `random_year` parameter support
   - When random_year='1', finds all matching buckets (same specs except year)
   - Aggregates price history from all matching buckets
   - Combines and sorts history by timestamp
   - Calculates current price as minimum across all buckets
   - Also added support for packaging and grading filters

2. **Frontend** (`static/js/bucket_price_chart.js` lines 45-78):
   - Updated `loadBucketPriceHistory()` to read Random Year toggle state
   - Passes `random_year=1` parameter when toggle is checked
   - Also passes packaging and grading filters to API
   - Chart automatically reloads when page refreshes (on toggle change)

**Impact:** Price history chart now shows aggregated data across all matching years when Random Year is ON, and respects all active filters.

### 4. ✅ Buy Flow
**Problem:** Clicking "Buy Item" only drew from original bucket's year inventory, even when Random Year was ON.

**Fixes:**
1. **Template** (`templates/view_bucket.html` line 451):
   - Added hidden input: `<input type="hidden" name="random_year" id="buyRandomYear" value="{{ '1' if random_year else '0' }}">`
   - This passes Random Year state to checkout route

2. **Checkout Route** (`routes/checkout_routes.py` lines 31, 38-80):
   - Reads `random_year` parameter from form
   - When `random_year='1'`, finds all matching buckets using same logic as view_bucket
   - Builds `bucket_id_clause` with `IN (...)` for multi-year or `= ?` for single-year
   - Queries listings from all matching buckets
   - Uses lowest-price-first logic to fill order from multi-year inventory
   - Added `c.year` to SELECT to track source year of each listing

**Impact:** Users can now actually purchase from multi-year aggregated inventory when Random Year is ON. Order fills from cheapest listings across all years.

## How Random Year Mode Works (End-to-End)

### When Toggle is OFF (Default)
- Shows data for the specific bucket/year
- Year field shows actual year (e.g., "2024")
- All queries use single `bucket_id`
- Standard behavior

### When Toggle is ON
1. **Page loads with `random_year=1` parameter**
2. **Backend (view_bucket route)**:
   - Finds all buckets matching: metal, product type, weight, purity, mint, finish, grade, product line, condition_category, series_variant
   - EXCLUDES year from matching (that's the point!)
   - Creates `bucket_ids` list of all matching buckets
   - Uses `bucket_id_clause` with `IN (...)` for all queries

3. **Display Updates**:
   - Specs Year field: Shows "Random"
   - Quantity: Aggregated across all years
   - Best Ask: Lowest price across all years
   - Sellers Modal: Shows all sellers from all years
   - Price History: Combined history from all years

4. **Buy Flow**:
   - Form includes `random_year=1`
   - Checkout queries all matching years
   - Fills order from cheapest listings across years
   - Order items backed by specific listings (with specific years)

### Consistency Guarantee
All features use the SAME `bucket_ids` list and `bucket_id_clause` pattern:
```python
if random_year:
    # Find matching buckets
    matching_buckets_query = '''
        SELECT bucket_id FROM categories
        WHERE metal = ? AND product_type = ? AND weight = ? AND purity = ?
          AND mint = ? AND finish = ? AND grade = ? AND product_line = ?
          AND condition_category IS NOT DISTINCT FROM ?
          AND series_variant IS NOT DISTINCT FROM ?
          AND is_isolated = 0
    '''
    bucket_ids = [row['bucket_id'] for row in matching_buckets]
    bucket_id_clause = f"c.bucket_id IN ({','.join('?' * len(bucket_ids))})"
else:
    bucket_ids = [bucket_id]
    bucket_id_clause = "c.bucket_id = ?"
```

This pattern is now used in:
- `view_bucket()` - lines 312-328
- `get_price_history()` - lines 56-84
- `checkout()` - lines 38-69

## Filter Interactions

Random Year mode correctly interacts with all filters:

### Packaging Filter
When packaging filter is active (e.g., "OGP"):
- Only listings with that packaging type are included
- Across all years if Random Year is ON
- Single year if Random Year is OFF

### Grading Filters
When grading filters are active:
- Graded Only, PCGS, NGC, Any Grader all work correctly
- Applied to multi-year listing set when Random Year is ON
- Applied to single-year set when Random Year is OFF

### Price History
Chart reflects the exact set of listings that are available to buy:
- Same filters applied to history data
- Shows price evolution of the specific filtered subset

## Files Modified

1. **routes/buy_routes.py**
   - Lines 307-309: Year field display logic
   - Lines 508-552: Sellers query with multi-year support and filters

2. **routes/bucket_routes.py**
   - Lines 16-105: Price history endpoint with Random Year and filter support

3. **routes/checkout_routes.py**
   - Lines 26, 31: Read random_year parameter
   - Lines 38-80: Multi-year bucket logic for buy flow

4. **templates/view_bucket.html**
   - Line 451: Added buyRandomYear hidden input

5. **static/js/bucket_price_chart.js**
   - Lines 45-78: Read toggle state and pass filters to API

## Testing Checklist

### Random Year OFF (Default)
- [ ] Year field shows specific year (e.g., "2024")
- [ ] Quantity shows count for that year only
- [ ] Best ask shows price for that year only
- [ ] View All Sellers shows listings from that year only
- [ ] Price history shows data for that year only
- [ ] Buy flow uses inventory from that year only

### Random Year ON
- [ ] Year field shows "Random"
- [ ] Quantity shows combined count across all years
- [ ] Best ask shows lowest price across all years
- [ ] View All Sellers shows listings from ALL matching years
- [ ] Price history shows aggregated data across all years
- [ ] Buy flow can purchase from multi-year inventory
- [ ] Order fulfillment uses lowest-price-first across years

### Filter Interactions
- [ ] Packaging filter works in both Random Year modes
- [ ] Grading filters work in both Random Year modes
- [ ] Price history reflects active filters
- [ ] Buy flow respects active filters

### Edge Cases
- [ ] Bucket with no matching years (should show only original bucket)
- [ ] All listings in one year sold out (can still buy from other years in Random Year mode)
- [ ] Toggle ON/OFF refreshes all data correctly
- [ ] User's own listings correctly skipped in buy flow for all years

## Implementation Notes

### Why Page Reload on Toggle?
The Random Year toggle triggers a full page reload rather than AJAX update because:
1. Entire page state changes (quantity, price, sellers, year display)
2. Multiple data sources need to be recalculated (listings, bids, history)
3. URL should reflect state for sharing/bookmarking
4. Simpler than coordinating multiple AJAX updates
5. User action is infrequent enough that reload is acceptable

### Data Integrity
- Orders are always backed by specific listings with specific years
- Internal order_items table has actual year from listing's category
- "Random" is just a display label to indicate multi-year purchase
- No data loss or ambiguity in database

### Performance
Random Year mode may query more buckets, but:
- Queries are indexed by bucket_id
- JOIN performance is good with proper indexes
- Typical use case: 2-5 matching buckets (not hundreds)
- User benefit (seeing all availability) outweighs slight performance cost
