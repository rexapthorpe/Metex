# Cart Tab 3rd Party Grading Display Fix

## Summary

Fixed the 3rd party grading display on the Account → Cart tab to correctly show the actual listing's grading status instead of incorrectly showing "No" for graded listings.

## Problem

The Cart tab was displaying incorrect grading information:
- **Cart page:** Correctly showed "3rd party graded: Yes (PCGS)" for graded listings
- **Cart tab:** Incorrectly showed "3rd party graded: No" for the same graded listings

This occurred when a graded listing was added to the cart, even if the user didn't select the grading toggle on the bucket page (e.g., it was the only available listing).

## Root Cause

The `get_cart_data()` function in `utils/cart_utils.py` was missing two critical fields from its SQL queries and data structures:

1. **SQL queries missing fields:** `listings.graded` and `listings.grading_service` were not selected
2. **Bucket listings missing fields:** The `bucket['listings']` array didn't include these fields

### What Was Missing

**SQL Query (lines 252-289):**
```sql
SELECT
    listings.id AS listing_id,
    cart.quantity,
    cart.grading_preference,  -- ✓ Has preference (user toggle)
    listings.price_per_coin,
    ...
    -- listings.graded,         ❌ Missing actual listing grading status
    -- listings.grading_service, ❌ Missing grading service (PCGS/NGC)
```

**Bucket Listings Dictionary (lines 355-362):**
```python
bucket['listings'].append({
    'listing_id': row['listing_id'],
    'price_per_coin': price,
    'quantity': qty,
    'seller_username': row['seller_username'],
    'seller_rating': row['seller_rating'],
    'grading_preference': row.get('grading_preference'),  # ✓ User preference
    # 'graded': row.get('graded'),                        ❌ Missing
    # 'grading_service': row.get('grading_service')       ❌ Missing
})
```

### The Confusion

- **grading_preference:** User's toggle selection on bucket page (not reliable)
- **graded:** Actual listing's grading status (what we need)
- **grading_service:** Actual grading service (PCGS/NGC) (what we need)

The template was trying to access `first_listing.graded` and `first_listing.grading_service`, but these fields didn't exist in the data, causing the display to fail silently or show incorrect information.

## Changes Made

### 1. Updated Logged-In User SQL Query (`utils/cart_utils.py` lines 252-290)

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
    listings.graded,            -- ✅ Added
    listings.grading_service,   -- ✅ Added
    users.username AS seller_username,
    categories.id AS category_id,
    ...
```

### 2. Updated Guest Cart SQL Query (`utils/cart_utils.py` lines 302-335)

Applied the same fix to ensure consistency for guest users.

### 3. Updated Bucket Listings Dictionary (`utils/cart_utils.py` lines 359-368)

**Before:**
```python
bucket['listings'].append({
    'listing_id': row['listing_id'],
    'price_per_coin': price,
    'quantity': qty,
    'seller_username': row['seller_username'],
    'seller_rating': row['seller_rating'],
    'grading_preference': row.get('grading_preference')
})
```

**After:**
```python
bucket['listings'].append({
    'listing_id': row['listing_id'],
    'price_per_coin': price,
    'quantity': qty,
    'seller_username': row['seller_username'],
    'seller_rating': row['seller_rating'],
    'grading_preference': row.get('grading_preference'),
    'graded': row.get('graded'),                    -- ✅ Added
    'grading_service': row.get('grading_service')   -- ✅ Added
})
```

## Template Logic (Already Correct)

The template logic in both `view_cart.html` and `cart_tab.html` was already correct:

```html
{% if bucket.listings %}
  {% set first_listing = bucket.listings[0] %}
  {% if first_listing.graded %}
    <div><strong>3rd party graded:</strong> Yes ({{ first_listing.grading_service }})</div>
  {% else %}
    <div><strong>3rd party graded:</strong> No</div>
  {% endif %}
{% endif %}
```

The template was correctly trying to access the listing's actual grading status, but the backend wasn't providing it. Now that the backend provides these fields, the template works as intended.

## Files Modified

1. `utils/cart_utils.py` - Added missing grading fields to SQL queries and bucket data

## Testing Checklist

### Test 1: Ungraded Listing
1. ✅ Add an ungraded listing to cart
2. ✅ Navigate to Cart page
3. ✅ Verify shows "3rd party graded: No"
4. ✅ Navigate to Account → Cart tab
5. ✅ Verify shows "3rd party graded: No"
6. ✅ Confirm both pages match

### Test 2: Graded Listing (PCGS)
1. ✅ Add a PCGS-graded listing to cart
2. ✅ Navigate to Cart page
3. ✅ Verify shows "3rd party graded: Yes (PCGS)"
4. ✅ Navigate to Account → Cart tab
5. ✅ Verify shows "3rd party graded: Yes (PCGS)"
6. ✅ Confirm both pages match

### Test 3: Graded Listing (NGC)
1. ✅ Add an NGC-graded listing to cart
2. ✅ Navigate to Cart page
3. ✅ Verify shows "3rd party graded: Yes (NGC)"
4. ✅ Navigate to Account → Cart tab
5. ✅ Verify shows "3rd party graded: Yes (NGC)"
6. ✅ Confirm both pages match

### Test 4: Mixed Cart
1. ✅ Add both graded and ungraded listings to cart
2. ✅ Verify each bucket shows correct grading status on both pages
3. ✅ Confirm no mixing of grading information between buckets

### Test 5: Graded Listing Added Without Toggle
**This is the specific scenario the user reported:**
1. ✅ Navigate to a bucket page with only graded listings
2. ✅ Add listing to cart WITHOUT enabling grading toggle
3. ✅ Navigate to Cart page
4. ✅ Verify shows "3rd party graded: Yes (grader)"
5. ✅ Navigate to Account → Cart tab
6. ✅ Verify shows "3rd party graded: Yes (grader)" (not "No")
7. ✅ Confirm both pages correctly reflect the actual listing's grading status

### Test 6: Guest Cart
1. ✅ Log out
2. ✅ Add graded listings to guest cart
3. ✅ Verify Cart page shows correct grading status
4. ✅ Log in and check Account → Cart tab still shows correct status

## Technical Notes

### Why the Fix Works

The fix ensures the cart display always reflects the **actual listing's properties**, not the user's preferences:

```
Database (listings table)
    ↓
listings.graded = 1
listings.grading_service = "PCGS"
    ↓
get_cart_data() SQL query
    ↓
row['graded'] = 1
row['grading_service'] = "PCGS"
    ↓
bucket['listings'][0]
    ↓
first_listing.graded = 1
first_listing.grading_service = "PCGS"
    ↓
Template displays: "Yes (PCGS)"
```

### Preference vs Actual Status

- **cart.grading_preference:** User's toggle on bucket page (what they wanted)
- **listings.graded:** What's actually in their cart (what they got)

The cart should always show what's actually in the cart, not what the user originally wanted.

### Consistency with Cart Page

This fix aligns the Cart tab with the standalone Cart page, which was already using `get_cart_items()` that correctly included these fields.

Now both pages use the same logic:
- Pull actual listing grading status from database
- Display based on listing properties, not user preferences
- Show consistent information across the entire cart UI

## Related Functions

Functions that correctly included grading fields before this fix:
- `get_cart_items()` - Already had listings.graded and listings.grading_service
- Standalone Cart page - Uses `get_cart_items()` (already correct)

Functions that were missing these fields (now fixed):
- `get_cart_data()` - Used by Account page Cart tab
- Both logged-in and guest cart queries
- Bucket listings dictionary construction

All cart functions now provide complete and consistent grading information.
