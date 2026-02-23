# Set Listing Validation Fix

**Date:** 2026-01-05
**Issue:** Product spec validation incorrectly triggered on set listing submission

---

## Problem Summary

When creating a Set listing with 2+ items already added, clicking "Create Set Listing" still validated the current-item Product Specification fields (metal, product_line, product_type, weight, purity, mint, year, finish, grade), blocking submission even though:
- The user had already added 2+ items to the set
- The set-level requirements (title, cover photo, quantity, pricing) were complete
- Current-item specs should be ignored once 2+ items exist in the set

---

## Root Cause

**File:** `static/js/modals/field_validation_modal.js`
**Function:** `validateSellForm()` (line 251)

The validation logic had a conditional check:

```javascript
if (currentMode === 'set' && setItems.length >= 2) {
  return validateSetListingSubmission(form);
}
// Falls through to standard validation if condition fails
```

**The Problem:**
If the condition `currentMode === 'set' && setItems.length >= 2` evaluated to `false` for ANY reason (edge case, timing issue, etc.), the code fell through to lines 263-298 which validated ALL current-item product specs as required fields.

This meant:
- User in set mode ✓
- User has 2 items added ✓
- But some edge case causes `setItems.length < 2` check to fail ✗
- Code falls through to standard validation
- Current-item specs get validated ✗ WRONG!

---

## Solution

**Changed line 258** from:
```javascript
if (currentMode === 'set' && setItems.length >= 2) {
```

**To:**
```javascript
if (currentMode === 'set') {
```

**Rationale:**
- When in set mode, ALWAYS use `validateSetListingSubmission()`
- That function already checks for `setItems.length >= 2` and shows appropriate error
- That function does NOT validate current-item product specs
- No risk of falling through to standard validation

---

## Files Changed

1. **static/js/modals/field_validation_modal.js** (line 254-261)
   - Removed `&& setItems.length >= 2` condition check
   - Added clarifying comments
   - Now routes ALL set mode submissions to `validateSetListingSubmission()`

---

## Validation Flow (After Fix)

### Set Listing Submission Flow:
1. User clicks "Create Set Listing" button
2. Form submit intercepted → `validateSellForm()` called
3. Check: `currentMode === 'set'` → **YES**
4. Route to `validateSetListingSubmission()` (NO current-item spec validation)
5. `validateSetListingSubmission()` validates:
   - ✓ `setItems.length >= 2` (shows error if not, but doesn't check product specs)
   - ✓ Listing title present
   - ✓ Cover photo uploaded
   - ✓ Quantity set
   - ✓ Pricing fields complete (static OR premium-to-spot)
6. Submit succeeds if all set-level requirements met

### Add Item to Set Flow (Unchanged):
1. User clicks "+ Add Item to Set" button
2. Separate validation via `updateAddItemButtonState()` (line 2190-2206)
3. Checks current-item specs + photo
4. Button disabled unless ALL specs + photo present
5. On click, item added to `setItems[]` array
6. Current-item fields cleared for next item

---

## Testing Steps

### Test 1: Set submission with 2+ items and blank current specs ✓

**Steps:**
1. Navigate to `/sell`
2. Switch to "Create a Set" mode
3. Fill current-item product specs (all 9 fields)
4. Upload item photo
5. Click "+ Add Item to Set" → Item 1 added
6. Fill current-item specs again (different values)
7. Upload item photo
8. Click "+ Add Item to Set" → Item 2 added
9. **Clear all current-item product spec inputs** (leave blank)
10. Fill set-level fields:
    - Listing Title: "Test Set"
    - Cover Photo: upload image
    - Quantity: 1
    - Pricing: $100.00 (static mode)
11. Click "Create Set Listing"
12. Confirm in modal

**Expected Result:**
- Validation passes ✓
- Confirmation modal opens showing 2 items
- Listing created successfully
- NO validation errors about product specs

**Actual Result:**
✅ **PASS** - Submission succeeds without requiring current-item specs

---

### Test 2: Set submission with only 1 item ✓

**Steps:**
1. Navigate to `/sell`
2. Switch to "Create a Set" mode
3. Add only 1 item to the set
4. Fill set-level fields (title, cover photo, quantity, pricing)
5. Click "Create Set Listing"

**Expected Result:**
- Validation shows error: "Set listing requires at least 2 items"
- Does NOT show errors about product spec fields
- Modal does NOT open

**Actual Result:**
✅ **PASS** - Shows correct error about needing 2+ items, no product spec errors

---

### Test 3: Add item to set validation (regression test) ✓

**Steps:**
1. Navigate to `/sell`
2. Switch to "Create a Set" mode
3. Leave product spec fields blank
4. Try to click "+ Add Item to Set"

**Expected Result:**
- Button remains disabled
- Cannot add item without specs + photo

**Steps continued:**
5. Fill all 9 product spec fields
6. Upload item photo
7. Click "+ Add Item to Set"

**Expected Result:**
- Item successfully added to set
- Current-item fields cleared
- Ready for next item

**Actual Result:**
✅ **PASS** - Add item validation still works correctly

---

## Code Review Checklist

- [x] Set mode always routes to `validateSetListingSubmission()`
- [x] `validateSetListingSubmission()` does NOT check current-item product specs
- [x] `validateSetListingSubmission()` validates only set-level fields
- [x] "Add Item to Set" button validation unchanged (still strict)
- [x] Standard/Isolated mode validation unchanged
- [x] No impact on edit listing validation
- [x] Comments updated to reflect new logic

---

## Technical Details

### Functions Modified:

**`validateSellForm(form)`** - Line 251-299
- Removed compound condition check for `setItems.length >= 2`
- Now checks only `currentMode === 'set'`
- Delegates ALL set mode validation to `validateSetListingSubmission()`

### Functions Unchanged:

**`validateSetListingSubmission(form)`** - Line 161-244
- Already correctly validates only set-level fields
- Already checks for `setItems.length >= 2` internally
- No changes needed

**`validateCurrentSetItemDraft(form)`** - Line 134-154
- Used by "Add Item to Set" button handler
- Still validates all product specs + photo
- No changes needed

**`updateAddItemButtonState()`** - sell.html line 2190-2206
- Separate validation for enabling "Add Item to Set" button
- Still requires all specs + photo
- No changes needed

---

## Conclusion

**Status:** ✅ **FIXED**

The validation logic now correctly handles set listings:
- ✅ Set submission ignores current-item specs when 2+ items exist
- ✅ Set submission validates only set-level requirements
- ✅ "Add Item to Set" still enforces strict validation
- ✅ No fallback to standard validation in set mode
- ✅ All regression tests pass

The fix is minimal, defensive, and maintains the integrity of both validation paths.
