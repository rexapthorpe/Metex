# Cart Tab Data Mismatch Fix

## Summary

Fixed a data mismatch where the Account → Cart tab was showing "--" for Product Line and Purity fields, while the standalone Cart page displayed these fields correctly.

## Problem

The Cart tab item tiles were displaying:
- **Product Line:** `--`
- **Purity:** `--`

While the same items on the standalone Cart page showed actual values like:
- **Product Line:** `American Eagle`
- **Purity:** `.9999`

## Root Cause

The `get_cart_data()` function in `utils/cart_utils.py` (used by the Account page Cart tab) was missing `product_line` and `purity` fields in its SQL queries, while `get_cart_items()` (used by the standalone Cart page) included these fields.

### Comparison

**get_cart_items()** (lines 132-176) - CORRECT:
```sql
SELECT
    ...
    categories.metal,
    categories.product_line,    -- ✅ Included
    categories.product_type,
    categories.weight,
    categories.mint,
    categories.year,
    categories.finish,
    categories.grade,
    categories.purity,          -- ✅ Included
    ...
```

**get_cart_data()** (lines 252-285) - MISSING FIELDS:
```sql
SELECT
    ...
    categories.metal,
    -- categories.product_line,  ❌ Missing
    categories.product_type,
    categories.weight,
    categories.mint,
    categories.year,
    categories.finish,
    categories.grade,
    -- categories.purity,        ❌ Missing
    ...
```

## Changes Made

### 1. Updated Logged-In User Query (`utils/cart_utils.py` lines 252-288)

**Before:**
```sql
SELECT
    listings.id AS listing_id,
    cart.quantity,
    cart.grading_preference,
    listings.price_per_coin,
    listings.pricing_mode,
    listings.spot_premium,
    listings.floor_price,
    listings.pricing_metal,
    listings.seller_id,
    users.username AS seller_username,
    categories.id AS category_id,
    categories.metal,
    categories.product_type,  -- Missing product_line here
    categories.weight,
    categories.mint,          -- Missing purity here
    categories.year,
    categories.finish,
    categories.grade,
    ...
```

**After:**
```sql
SELECT
    listings.id AS listing_id,
    cart.quantity,
    cart.grading_preference,
    listings.price_per_coin,
    listings.pricing_mode,
    listings.spot_premium,
    listings.floor_price,
    listings.pricing_metal,
    listings.seller_id,
    users.username AS seller_username,
    categories.id AS category_id,
    categories.metal,
    categories.product_line,   -- ✅ Added
    categories.product_type,
    categories.weight,
    categories.purity,         -- ✅ Added
    categories.mint,
    categories.year,
    categories.finish,
    categories.grade,
    ...
```

### 2. Updated Guest Cart Query (`utils/cart_utils.py` lines 300-331)

Applied the same fix to the guest cart query to ensure consistency.

### 3. Updated Bucket Category Data (`utils/cart_utils.py` lines 366-376)

**Before:**
```python
bucket['category'] = {
    'metal': row['metal'],
    'product_type': row['product_type'],
    'weight': row['weight'],
    'mint': row['mint'],
    'year': row['year'],
    'finish': row['finish'],
    'grade': row['grade']
}
```

**After:**
```python
bucket['category'] = {
    'metal': row['metal'],
    'product_line': row['product_line'],    # ✅ Added
    'product_type': row['product_type'],
    'weight': row['weight'],
    'purity': row['purity'],                # ✅ Added
    'mint': row['mint'],
    'year': row['year'],
    'finish': row['finish'],
    'grade': row['grade']
}
```

### 4. Removed Hard-Coded Fallbacks (`templates/tabs/cart_tab.html` lines 27, 32)

**Before:**
```html
<div><strong>Purity:</strong> {{ bucket.category.purity or '--' }}</div>
...
<div><strong>Product Line:</strong> {{ bucket.category.product_line or '--' }}</div>
```

**After:**
```html
<div><strong>Purity:</strong> {{ bucket.category.purity }}</div>
...
<div><strong>Product Line:</strong> {{ bucket.category.product_line }}</div>
```

The `or '--'` fallbacks were masking the missing data issue. Now that the data is properly provided, these fallbacks are unnecessary.

## Files Modified

1. `utils/cart_utils.py` - Added missing fields to SQL queries and bucket data
2. `templates/tabs/cart_tab.html` - Removed hard-coded `--` fallbacks

## Testing Checklist

To verify the fix:

### Test 1: Cart Tab Display
1. ✅ Add items to cart with various Product Lines and Purities
2. ✅ Navigate to Account → Cart tab
3. ✅ Verify **Product Line** displays actual value (e.g., "American Eagle", "Maple Leaf")
4. ✅ Verify **Purity** displays actual value (e.g., ".9999", ".999")
5. ✅ Verify no fields show "--"

### Test 2: Standalone Cart Page Display
1. ✅ Navigate to standalone Cart page (`/cart`)
2. ✅ Verify same items show identical Product Line and Purity values
3. ✅ Confirm data matches between Cart tab and Cart page

### Test 3: Guest Cart
1. ✅ Log out
2. ✅ Add items to guest cart
3. ✅ Navigate to Cart page
4. ✅ Verify Product Line and Purity display correctly for guest users

### Test 4: Multiple Items
1. ✅ Add multiple different items to cart
2. ✅ Verify each item displays its own unique Product Line and Purity
3. ✅ Confirm no data mixing between buckets

## Technical Notes

### Why the Fallbacks Were Problematic

The template fallbacks (`or '--'`) were hiding the real issue:
1. Backend wasn't providing the data
2. Template showed "--" as fallback
3. User thought data was missing in database
4. Actually, query was incomplete

By removing the fallbacks after fixing the query, we ensure:
- Data integrity is visible
- Missing data issues surface immediately
- No silent failures

### Data Flow

```
Database (categories table)
    ↓
get_cart_data() SQL query
    ↓
bucket['category'] dictionary
    ↓
Jinja template (cart_tab.html)
    ↓
Rendered HTML
```

The fix ensures `product_line` and `purity` flow through all stages correctly.

### Consistency with Other Queries

This fix aligns `get_cart_data()` with `get_cart_items()`, ensuring both functions provide complete category information for consistent cart displays across the application.

## Related Functions

Other cart-related functions that already include these fields:
- `get_cart_items()` - Already correct
- Account page Order queries - Include product_line and purity
- Standalone Cart page - Uses `get_cart_items()` (already correct)

Now all cart-related queries are consistent and complete.
