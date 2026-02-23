# Sell Page UI Polish - Complete

## Summary

Successfully fixed and polished the Sell page UI and backend wiring for the new category controls. All new fields now behave consistently with existing category dropdowns, and obsolete fields have been removed.

## Changes Made

### 1. Condition Category & Series Variant - Converted to Searchable Inputs

**Before:** Used plain `<select>` dropdowns
**After:** Use validated-datalist searchable inputs (matching existing category fields)

**Files Modified:**
- `templates/sell.html` (lines 265-301)

**Changes:**
```html
<!-- Before -->
<select name="condition_category" id="condition_category">
  <option value="">Select condition...</option>
  {% for condition in condition_categories %}
    <option value="{{ condition }}">{{ condition.replace('_', ' ') }}</option>
  {% endfor %}
</select>

<!-- After -->
<input
  type="text"
  name="condition_category"
  id="condition_category"
  class="validated-datalist custom-dropdown-input"
  data-list-id="condition_category_options"
  autocomplete="off"
>
<datalist id="condition_category_options">
  {% for condition in condition_categories %}
  <option value="{{ condition }}"></option>
  {% endfor %}
</datalist>
```

**Benefits:**
- Searchable/filterable dropdowns
- Consistent with Product Type, Metal, Weight, etc.
- Same styling and behavior
- Uses existing `setupCustomDropdown()` JavaScript function

### 2. Removed "Actual Year (optional)" Field

**Reason:** Redundant with the primary Year field

**Files Modified:**
- `templates/sell.html` - Removed input field completely
- `routes/sell_routes.py` (line 153) - Removed extraction: `actual_year = request.form.get('actual_year')`
- `routes/sell_routes.py` (lines 253-294) - Removed from INSERT statement

**Database Column:**
- Column `listings.actual_year` still exists but is no longer used
- No data is written to this column for new listings
- Safe to deprecate; can be dropped in future migration if needed

### 3. Removed "Item has been graded?" Toggle

**Reason:** Obsolete - grading moved to buyer-side add-on, and Grade field (e.g., PF-70, MS-69) is sufficient

**Files Modified:**

**Template (`templates/sell.html`):**
- Removed "Item has been graded?" select input (was lines 392-399)
- Removed "Grading Service" conditional section (was lines 401-409)

**JavaScript (`static/js/sell.js`):**
- Removed `toggleGradingService()` function (was lines 1-8)
- Removed initialization call in DOMContentLoaded

**JavaScript Inline (`templates/sell.html`):**
- Removed graded/grading_service from `captureSpecValues()` function
- Removed from `clearSpecFields()` function

**Backend (`routes/sell_routes.py`):**
- Removed extraction (was lines 142-143):
  ```python
  graded = int(request.form.get('graded', 0))
  grading_service = request.form.get('grading_service') if graded else None
  ```
- Removed from main listing INSERT (lines 253-294)
- Removed from set item INSERT statements (lines 332-341, 384-394)

**Database Columns:**
- Columns `listings.graded` and `listings.grading_service` still exist but are no longer used
- Column `listing_set_items.graded` and `listing_set_items.grading_service` also deprecated
- Existing graded listings still display correctly
- New listings won't set these fields

### 4. Added Conditional Visibility for Numismatic Issue Fields

**Before:** "Issue X out of Y" fields always visible
**After:** Only visible when "isolated / numismatic item" toggle is ON

**Files Modified:**
- `templates/sell.html` (line 304) - Added `id="numismaticFields"` and `display: none`

**JavaScript Changes (`templates/sell.html` inline script):**
- Added `numismaticFields` constant reference (line 527)
- Show fields when isolated toggle turns ON (lines 607-609)
- Show fields when numismatic values entered (lines 621-623)
- Show fields when set toggle forces isolated (lines 647-649)
- Hide fields when set toggle turns OFF and isolated is unchecked (lines 667-669)

**Behavior:**
- When user checks "List as isolated / numismatic item": Numismatic fields appear
- When user unchecks the toggle: Fields hide
- When user fills in issue number/total: Auto-checks isolated toggle and shows fields
- When user checks "List as part of a set": Forces isolated ON and shows numismatic fields

## Files Modified Summary

1. **templates/sell.html**
   - Converted Condition Category to validated-datalist
   - Converted Series Variant to validated-datalist
   - Removed Actual Year input
   - Removed Item has been graded select
   - Removed Grading Service section
   - Added conditional visibility for Numismatic fields

2. **static/js/sell.js**
   - Removed toggleGradingService function
   - Removed initialization call

3. **routes/sell_routes.py**
   - Removed graded/grading_service extraction
   - Removed actual_year extraction
   - Updated main listing INSERT (removed 3 columns)
   - Updated set item INSERT statements (removed 2 columns each)

## Testing Results

All tests passed ✓

**Template Structure:**
- ✓ Condition Category uses validated-datalist
- ✓ Series Variant uses validated-datalist
- ✓ Actual Year field removed
- ✓ Item has been graded field removed
- ✓ Grading Service field removed
- ✓ Numismatic fields have conditional visibility

**Backend Processing:**
- ✓ graded extraction removed
- ✓ grading_service extraction removed
- ✓ actual_year extraction removed
- ✓ Fields not in INSERT statements

**JavaScript:**
- ✓ toggleGradingService function removed
- ✓ Function calls removed

**Page Load Integration:**
- ✓ Status 200 OK
- ✓ Condition Category input present
- ✓ Series Variant input present
- ✓ Numismatic fields present with correct ID
- ✓ Actual Year NOT present
- ✓ Graded toggle NOT present

## Database Impact

**Columns Deprecated (Not Dropped):**
- `listings.graded` - No longer written to
- `listings.grading_service` - No longer written to
- `listings.actual_year` - No longer written to
- `listing_set_items.graded` - No longer written to
- `listing_set_items.grading_service` - No longer written to

**Reason for Not Dropping:**
- Existing listings may reference these columns
- Safe to leave columns in place
- Can be dropped in future migration if desired
- No performance impact from unused columns

## User-Facing Changes

### What Users Will See

**Category Fields (Improved):**
- Condition Category now has searchable dropdown (like other category fields)
- Series Variant now has searchable dropdown (like other category fields)
- Both fields auto-filter as you type
- Consistent look and feel with Metal, Product Type, Weight, etc.

**Removed Fields (Simplified):**
- "Actual Year (optional)" input removed - use main Year field instead
- "Item has been graded?" toggle removed - use Grade field (PF-70, MS-69, etc.) directly
- "Grading Service" section removed - grading is now buyer-side service

**Conditional Display (Better UX):**
- Numismatic "Issue X out of Y" fields now only appear when relevant
- Hidden by default
- Appear when "List as isolated / numismatic item" is checked
- Cleaner interface when not listing limited editions

### Workflow Examples

**Standard Listing:**
1. User fills in category fields (searchable dropdowns)
2. Numismatic fields hidden (not needed)
3. Upload photo, set price
4. Submit

**Numismatic Listing:**
1. User fills in category fields
2. Checks "List as isolated / numismatic item"
3. Numismatic "Issue X out of Y" fields appear
4. User fills in issue number and total
5. Upload photo, set price
6. Submit

**Set Listing:**
1. User fills in category fields
2. Checks "List as part of a set"
3. Isolated toggle auto-checks
4. Numismatic fields appear (optional to use)
5. Add items to set
6. Upload cover photo
7. Submit

## Consistency Achieved

All category controls now use the same pattern:

| Field | Input Type | Searchable | Validated | Datalist |
|-------|-----------|------------|-----------|----------|
| Metal | text | ✓ | ✓ | ✓ |
| Product Line | text | ✓ | ✓ | ✓ |
| Product Type | text | ✓ | ✓ | ✓ |
| Weight | text | ✓ | ✓ | ✓ |
| Purity | text | ✓ | ✓ | ✓ |
| Mint | text | ✓ | ✓ | ✓ |
| Year | text | ✓ | ✓ | ✓ |
| Finish | text | ✓ | ✓ | ✓ |
| Grade | text | ✓ | ✓ | ✓ |
| **Condition Category** | **text** | **✓** | **✓** | **✓** |
| **Series Variant** | **text** | **✓** | **✓** | **✓** |

## Next Steps (Optional)

If you want to fully clean up deprecated columns:

```sql
-- Create migration: 014_drop_deprecated_listing_columns.sql
ALTER TABLE listings DROP COLUMN graded;
ALTER TABLE listings DROP COLUMN grading_service;
ALTER TABLE listings DROP COLUMN actual_year;

ALTER TABLE listing_set_items DROP COLUMN graded;
ALTER TABLE listing_set_items DROP COLUMN grading_service;
```

**Note:** This is optional. Leaving the columns doesn't cause any issues.

## Status

✅ **COMPLETE** - All UI polish tasks finished and tested successfully.

**Date:** 2025-12-08
**Test Results:** All tests passed
**Files Modified:** 3 files
**Lines Changed:** ~150 lines
