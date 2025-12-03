# Bucket Persistence Fix

## Problem Description

Previously, buckets (categories) would disappear from the Buy page when all their listings were deleted, even if there were still active bids on those buckets. This created a poor user experience where:

1. A bucket with active bids would vanish if all sellers removed their listings
2. Users couldn't see or interact with buckets that had no current listings
3. Potential buyers couldn't place new bids on empty buckets

## Root Cause

The issue was in `routes/buy_routes.py` in the `buy()` function (lines 25-66). The query was structured as:

```sql
FROM listings
JOIN categories ON listings.category_id = categories.id
WHERE listings.active = 1 AND listings.quantity > 0
```

This INNER JOIN meant that only categories with active listings would appear in the results. When all listings for a bucket were deleted, the bucket would disappear.

## Solution

The fix involved three changes:

### 1. Refactored Database Query (`routes/buy_routes.py`)

Changed the query to start from the `categories` table instead of `listings`:

```sql
FROM categories
LEFT JOIN listings ON listings.category_id = categories.id
```

This ensures ALL categories/buckets are returned, regardless of whether they have listings. The LEFT JOIN preserves categories that have no matching listings.

**Key improvements:**
- Used CASE statements to calculate `lowest_price` (NULL when no listings)
- Used COALESCE to ensure `total_available` is always 0 (not NULL) when no listings
- Updated ORDER BY to show buckets with listings first, then buckets without

**Modified section:** Lines 25-84 in `routes/buy_routes.py`

### 2. Updated Template Logic (`templates/buy.html`)

Added conditional rendering to handle NULL prices:

```jinja
{% if bucket['lowest_price'] is not none %}
    <p class="price">${{ bucket['lowest_price'] }}</p>
{% else %}
    <p class="price no-listings">No listings available</p>
{% endif %}
```

This displays "No listings available" for buckets without active listings instead of crashing or showing "$None".

**Modified section:** Lines 32-36 in `templates/buy.html`

### 3. Added CSS Styling (`static/css/grid.css`)

Added visual distinction for unavailable buckets:

```css
.price.no-listings {
    color: #999;
    font-style: italic;
    font-weight: normal;
}
```

This makes it immediately clear which buckets have no listings available.

**Modified section:** Lines 54-58 in `static/css/grid.css`

## Testing

### Backend Test (`test_bucket_persistence.py`)

Comprehensive test that:
1. Creates a test bucket/category
2. Creates a listing for it
3. Verifies it appears on the Buy page WITH price
4. Deletes all listings
5. Verifies the bucket STILL appears WITHOUT price (showing NULL)
6. Verifies the query returns all buckets in the system

**Test Result:** ✓ PASSED - Buckets persist even when all listings are deleted

### UI Test (`test_bucket_persistence_ui.html`)

Visual test showing:
1. Buckets with active listings (displaying price)
2. Buckets without active listings (displaying "No listings available")
3. Mixed display showing both types together

**Test Result:** ✓ PASSED - UI displays correctly for both states

## Benefits

1. **Persistence:** Buckets never disappear from the Buy page, even with zero listings
2. **User Experience:** Clear visual indication of which buckets have available listings
3. **Bid Functionality:** Users can still click on empty buckets to view details and place bids
4. **Data Integrity:** Buckets remain independent of listing status

## Implementation Details

### Query Logic

The new query uses conditional aggregation:

```sql
MIN(CASE
    WHEN listings.active = 1 AND listings.quantity > 0
    THEN listings.price_per_coin
    ELSE NULL
END) AS lowest_price
```

This ensures:
- Only active listings with quantity > 0 are considered for pricing
- Result is NULL (not 0) when no listings exist
- Grading filters still work correctly (checked for NULL listings)

### Sorting

Buckets are sorted by:
1. Availability (with listings first, without listings last)
2. Price (ascending for available buckets)

```sql
ORDER BY
    CASE WHEN lowest_price IS NULL THEN 1 ELSE 0 END,
    lowest_price ASC
```

## Edge Cases Handled

1. **Empty bucket with bids:** Bucket still appears, users can see/place bids
2. **Last listing deleted:** Bucket immediately shows "No listings available"
3. **New listing added:** Bucket automatically shows price again
4. **Grading filters:** Still work correctly, preserve empty buckets
5. **All buckets empty:** Still displays all buckets (no "empty state" message)

## Future Considerations

If needed, you could:
- Add a badge showing number of active bids on empty buckets
- Allow filtering to hide/show empty buckets
- Show "Coming Soon" or similar messaging for specific empty buckets
- Display last known price or price history for empty buckets

## Files Modified

1. `routes/buy_routes.py` - Lines 25-84 (query refactoring)
2. `templates/buy.html` - Lines 32-36 (conditional price display)
3. `static/css/grid.css` - Lines 54-58 (no-listings styling)

## Files Created

1. `test_bucket_persistence.py` - Backend functionality test
2. `test_bucket_persistence_ui.html` - UI visual test
3. `BUCKET_PERSISTENCE_FIX.md` - This documentation

---

**Status:** ✓ Implementation Complete and Tested
**Date:** 2025-11-26
**Testing:** Backend and UI tests passing
