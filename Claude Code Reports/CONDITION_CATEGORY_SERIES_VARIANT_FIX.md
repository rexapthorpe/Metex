# Condition Category & Series Variant Autofill Fix

## Problem
When clicking "List this item" from a Bucket ID page, the Sell page was NOT pre-filling the Condition Category and Series Variant dropdowns, even though other fields (Metal, Product type, Weight, etc.) were being correctly pre-filled.

## Root Cause
The `get_or_create_category()` function in `utils/category_manager.py` was **completely ignoring** the `condition_category` and `series_variant` fields when:
1. Looking up existing categories
2. Looking up existing buckets
3. Creating new categories

This meant that even though:
- The Sell page form collected these values
- The backend passed them in the `category_spec` dictionary
- The frontend JavaScript had them in the prefill mapping

...they were **never saved to the database** when creating listings.

## Files Modified

### 1. `utils/category_manager.py`
**Changes:**
- Extract `condition_category` and `series_variant` from `category_spec` (lines 30-31)
- Include them in the WHERE clause when looking for existing categories (lines 41-42, 47)
- Include them in the WHERE clause when looking for existing buckets (lines 62-63, 67-68)
- Include them in the INSERT statement when creating new categories (lines 99-100, 116-117)

**Impact:**
- Non-isolated listings now properly save and match on these bucket-level fields
- Ensures that items with different condition categories or series variants go into different buckets

### 2. `routes/sell_routes.py`
**Changes:**
- Updated isolated listing creation INSERT statement to include `condition_category` and `series_variant` (lines 242, 246)

**Impact:**
- Isolated (one-of-a-kind and set) listings now also save these fields to the database

## Complete Data Flow

### When Creating a Listing:
1. User fills out Sell form including Condition Category and Series Variant
2. Backend extracts these from form data (lines 147-148 in sell_routes.py)
3. Backend builds `category_spec` dict including these fields (lines 163-164)
4. Backend calls `get_or_create_category(conn, category_spec)` or creates isolated category
5. **NOW FIXED:** These fields are saved to the categories table

### When Clicking "List this item":
1. view_bucket.html passes bucket's `condition_category` and `series_variant` as URL params (line 212)
2. sell_routes.py reads them from query params into `prefill` dict (lines 510-511)
3. sell.html passes `prefill` to JavaScript as `window.sellPrefillData` (line 520)
4. sell.js extracts and sets field values including these two fields (lines 138-139, 143-151)
5. **NOW WORKS:** Because the bucket actually has these values saved

## Testing Instructions

### Test 1: Create a New Listing with These Fields
1. Go to the Sell page
2. Fill out all required fields
3. **Select a Condition Category** (e.g., "BU")
4. **Select a Series Variant** (e.g., "First_Strike")
5. Upload a photo and submit
6. Verify the listing was created successfully

### Test 2: Verify Database Saved the Values
```bash
cd "C:\Users\rex.apthorpe\OneDrive - West Point\Desktop\MetalsExchangeApp\Metex"
python check_bucket_values.py
```
You should now see buckets with condition_category and series_variant populated.

### Test 3: Verify Autofill Works
1. Navigate to a Bucket ID page that has condition_category and series_variant set
2. Click "List this item" at the bottom right of the gallery
3. **VERIFY:** Sell page opens with:
   - Metal pre-filled ✓
   - Product type pre-filled ✓
   - Weight pre-filled ✓
   - Product line pre-filled ✓
   - Year pre-filled ✓
   - Finish pre-filled ✓
   - **Condition Category pre-filled** ✓ ← **THIS IS THE FIX**
   - **Series Variant pre-filled** ✓ ← **THIS IS THE FIX**

## Important Notes

### Existing Buckets
All existing buckets (created before this fix) have NULL values for condition_category and series_variant. This is expected and correct. When users create new listings with these fields filled out, new buckets will be created with the proper values.

### Bucket Grouping
Items with different condition categories or series variants will now go into **different buckets**, even if all other specs match. This is intentional and correct behavior - a "BU" coin should not be in the same bucket as a "Circulated" coin.

For example:
- 2024 Gold American Eagle 1oz BU → Bucket A
- 2024 Gold American Eagle 1oz Circulated → Bucket B

### JavaScript Already Worked
The JavaScript prefill code in `sell.js` was **already correct** - it had condition_category and series_variant in the fieldMapping since the beginning. The issue was purely on the backend (data not being saved to the database).

## Summary
✅ Categories now save condition_category and series_variant
✅ Category/bucket lookup now considers these fields
✅ Autofill from "List this item" button now works for these fields
✅ All existing code paths (sell, edit, view) unchanged except for the fixes
