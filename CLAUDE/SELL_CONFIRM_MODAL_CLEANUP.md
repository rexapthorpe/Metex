# Sell Confirm Modal - Field Cleanup and Grading Fix

## Summary

Fixed two issues in the Sell page Confirm Listing modal:
1. Removed unused fields from Item Category Details
2. Fixed "Require 3rd Party Grading" display bug

## Changes Made

### 1. Removed Unused Fields

**Removed from HTML template** (`templates/modals/sell_listing_modals.html`):
- ❌ Country of Origin
- ❌ Coin Series
- ❌ Denomination
- ❌ Special Designation

**Kept fields** (10 total):
- ✅ Metal
- ✅ Product Line
- ✅ Product Type
- ✅ Weight
- ✅ Purity
- ✅ Mint
- ✅ Year
- ✅ Grade
- ✅ Finish
- ✅ Require 3rd Party Grading

**Removed from JavaScript** (`static/js/modals/sell_listing_modals.js`):
- Removed extraction of unused fields (country, coinSeries, denomination, specialDesignation)
- Removed population of unused field elements

### 2. Fixed Grading Display Bug

**Problem:** The modal always showed "Require 3rd Party Grading: No" even when user selected "Yes" and chose a grader.

**Root Cause:** The JavaScript was checking for `formData.get('graded') === 'on'` (checkbox syntax), but the sell form uses a `<select>` dropdown with values "0" and "1".

**Fix Applied** (`static/js/modals/sell_listing_modals.js` lines 35-44):

```javascript
// Get grading information
const isGraded = formData.get('graded') === '1';  // Changed from === 'on'
let gradedText = 'No';
if (isGraded) {
  const gradingService = formData.get('grading_service') || '';
  if (gradingService) {
    gradedText = `Yes (${gradingService})`;  // Shows "Yes (PCGS)" or "Yes (NBS)"
  } else {
    gradedText = 'Yes';
  }
}
```

**Also removed:** The check for `coin_grade` field which doesn't exist in the sell form.

### 3. Label Update

Changed label from "3rd Party Graded" to "Require 3rd Party Grading" for consistency with the form field label.

## Testing Checklist

To verify the fixes:

### Test 1: Ungraded Listing
1. ✅ Create listing with "Item has been graded?" = "No"
2. ✅ Verify modal shows "Require 3rd Party Grading: No"

### Test 2: PCGS Graded Listing
1. ✅ Create listing with "Item has been graded?" = "Yes"
2. ✅ Select "Grading Service" = "PCGS"
3. ✅ Verify modal shows "Require 3rd Party Grading: Yes (PCGS)"

### Test 3: NBS Graded Listing
1. ✅ Create listing with "Item has been graded?" = "Yes"
2. ✅ Select "Grading Service" = "NBS"
3. ✅ Verify modal shows "Require 3rd Party Grading: Yes (NBS)"

### Test 4: Field Cleanup
1. ✅ Verify modal no longer shows Country of Origin, Coin Series, Denomination, or Special Designation
2. ✅ Verify modal still shows all 10 retained fields in proper grid layout
3. ✅ Verify grey container styling remains intact

## Files Modified

1. `templates/modals/sell_listing_modals.html` - Removed 4 unused field rows
2. `static/js/modals/sell_listing_modals.js` - Fixed grading check, removed unused field extraction/population

## Technical Notes

### Form Field vs Checkbox Difference
- **Checkbox:** Returns `'on'` when checked, `null` when unchecked
- **Select dropdown:** Returns the selected option's value (`'0'` or `'1'`)

The sell form uses a `<select>` element:
```html
<select name="graded" id="graded" required>
  <option value="0" selected>No</option>
  <option value="1">Yes</option>
</select>
```

Therefore, the correct check is `formData.get('graded') === '1'`, not `=== 'on'`.

### Grading Service Options
Available in the sell form:
- PCGS (Professional Coin Grading Service)
- NBS (Numismatic Guaranty Corporation)

The modal now correctly displays the selected service when grading is required.
