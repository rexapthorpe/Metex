# Random Year Toggle Fix

## Problem
When toggling Random Year ON on the Bucket ID page, the application crashed with:
```
AttributeError: 'sqlite3.Row' object has no attribute 'get'
File "routes/buy_routes.py", line 321, in view_bucket
    bucket.get('condition_category'), bucket.get('series_variant')
```

## Root Cause
At line 321 in `routes/buy_routes.py`, the code was incorrectly calling `.get()` method on a `sqlite3.Row` object. While `sqlite3.Row` supports dictionary-like bracket access (`bucket['key']`), it does **not** have a `.get()` method.

This was the ONLY place in the entire function where `.get()` was used on the bucket object - all other places correctly used bracket notation.

## Fix Applied

### File: `routes/buy_routes.py` (line 321)

**Before:**
```python
matching_buckets = conn.execute(matching_buckets_query, (
    bucket['metal'], bucket['product_type'], bucket['weight'], bucket['purity'],
    bucket['mint'], bucket['finish'], bucket['grade'], bucket['product_line'],
    bucket.get('condition_category'), bucket.get('series_variant')  # ❌ WRONG
)).fetchall()
```

**After:**
```python
matching_buckets = conn.execute(matching_buckets_query, (
    bucket['metal'], bucket['product_type'], bucket['weight'], bucket['purity'],
    bucket['mint'], bucket['finish'], bucket['grade'], bucket['product_line'],
    bucket['condition_category'], bucket['series_variant']  # ✅ CORRECT
)).fetchall()
```

## Verification

### Query Confirmation
The bucket is fetched using:
- Line 235: `SELECT DISTINCT c.*` (includes all columns)
- Line 244: `SELECT * FROM categories` (includes all columns)

Both queries include `condition_category` and `series_variant` columns, so the bracket access will work correctly.

### NULL Value Handling
Even if a bucket has NULL values for these columns (all existing buckets do), the code will work correctly because:
1. Bracket access returns `None` for NULL values (no error)
2. The SQL query uses `IS NOT DISTINCT FROM ?` which properly handles NULL comparisons:
   - `NULL IS NOT DISTINCT FROM NULL` → `TRUE` ✓
   - `'BU' IS NOT DISTINCT FROM NULL` → `FALSE` ✓

## Testing Instructions

### Test 1: Toggle Random Year with NULL Values
1. Navigate to any existing bucket (which has NULL for condition_category/series_variant)
2. Toggle Random Year **ON**
3. **Expected:** No crash, page loads successfully
4. **Expected:** Shows aggregated data across all years matching the bucket specs

### Test 2: Toggle Random Year with Non-NULL Values
1. Create a new listing with Condition Category and Series Variant filled
2. Navigate to that bucket's page
3. Toggle Random Year **ON**
4. **Expected:** No crash, page loads successfully
5. **Expected:** Only aggregates buckets with matching condition_category and series_variant

### Test 3: Verify Aggregation Logic
With Random Year ON, the page should:
- ✅ Aggregate listings from all years with matching specs
- ✅ Include condition_category and series_variant in the match criteria
- ✅ Calculate correct total availability across aggregated buckets
- ✅ Show correct lowest price across aggregated buckets
- ✅ Display all matching listings in the sellers modal

## Impact
- ✅ Random Year toggle no longer crashes
- ✅ Properly aggregates buckets by condition_category and series_variant
- ✅ Consistent access pattern throughout the view_bucket function
- ✅ Handles both NULL and non-NULL values correctly
