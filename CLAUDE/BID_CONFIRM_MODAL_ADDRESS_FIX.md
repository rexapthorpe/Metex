# Bid Confirmation Modal Address Display Fix

## Problem
The bid confirmation modal was displaying "—" for all delivery address fields instead of showing the actual address entered in the bid form.

### Console Log Evidence
```
[BID MODAL] Extracted delivery address:
[BID CONFIRM] Raw delivery_address:
[BID CONFIRM] No address provided
[BID CONFIRM] Parsed address: {street: '', street2: '', city: '', state: '', zip: ''}
```

## Root Cause
The address fields in the bid form template (`templates/tabs/bid_form.html`) **do not have `name` attributes** (lines 244-279). This is by design, as noted in the comment:

```html
<!-- Address fields (without names - moved to Billing) -->
```

The JavaScript code was attempting to extract address values using:
```javascript
const addressLine1 = formData.get('address_line1') || '';  // Returns empty!
```

Since FormData can only capture form fields with `name` attributes, these calls always returned empty strings.

## Solution
Changed the address extraction to use **direct DOM access by element ID** instead of FormData:

### File: `static/js/modals/bid_modal.js`

#### Change 1: Extract from DOM (Lines 601-606)
**Before:**
```javascript
const addressLine1 = formData.get('address_line1') || '';
const addressLine2 = formData.get('address_line2') || '';
const city = formData.get('city') || '';
const state = formData.get('state') || '';
const zipCode = formData.get('zip_code') || '';
```

**After:**
```javascript
// Extract delivery address from form (fields don't have name attributes, use IDs)
const addressLine1 = document.getElementById('addr-line1')?.value || '';
const addressLine2 = document.getElementById('addr-line2')?.value || '';
const city = document.getElementById('addr-city')?.value || '';
const state = document.getElementById('addr-state')?.value || '';
const zipCode = document.getElementById('addr-zip')?.value || '';
```

#### Change 2: Append to FormData (Lines 627-632)
Added code to append the extracted values to FormData so the backend receives them:

```javascript
// Add address fields to formData (they don't have name attributes in template)
formData.append('address_line1', addressLine1);
formData.append('address_line2', addressLine2);
formData.append('city', city);
formData.append('state', state);
formData.append('zip_code', zipCode);
```

#### Change 3: Updated Success Modal Extraction (Lines 730-752)
Also updated the address extraction for the bid success modal to use the same pattern with DOM fallback:

```javascript
// Extract delivery address from DOM (fields don't have name attributes, but we added them to formData)
const addressLine1 = formData.get('address_line1') || document.getElementById('addr-line1')?.value || '';
const addressLine2 = formData.get('address_line2') || document.getElementById('addr-line2')?.value || '';
const city = formData.get('city') || document.getElementById('addr-city')?.value || '';
const state = formData.get('state') || document.getElementById('addr-state')?.value || '';
const zipCode = formData.get('zip_code') || document.getElementById('addr-zip')?.value || '';

// Construct delivery address in bullet-separated format
let deliveryAddress = '';
if (addressLine1 || city || state || zipCode) {
  const parts = [];
  if (addressLine1) parts.push(addressLine1);
  if (addressLine2) parts.push(addressLine2);

  const cityStateZip = [city, state && zipCode ? `${state} ${zipCode}` : state || zipCode]
    .filter(Boolean)
    .join(', ');

  if (cityStateZip) parts.push(cityStateZip);

  deliveryAddress = parts.join(' • ');
}
```

## Expected Console Output After Fix
```
[BID MODAL] Extracted delivery address: 1 Main Street • Apt 6D • Brooklyn, NY 11201
[BID CONFIRM] Raw delivery_address: 1 Main Street • Apt 6D • Brooklyn, NY 11201
[BID CONFIRM] Parsed address: {street: '1 Main Street', street2: 'Apt 6D', city: 'Brooklyn', state: 'NY', zip: '11201'}
[BID CONFIRM] Line 1: 1 Main Street
[BID CONFIRM] Line 2: Apt 6D
[BID CONFIRM] City: Brooklyn
[BID CONFIRM] State: NY
[BID CONFIRM] ZIP: 11201
```

## Confirmation Modal Display
The bid confirmation modal will now show:
- **Address Line 1:** 1 Main Street
- **Address Line 2:** Apt 6D
- **City:** Brooklyn
- **State:** NY
- **ZIP Code:** 11201

## Related Components
This fix ensures consistency across all bid-related modals:
1. **Bid Confirmation Modal** - Shows address before bid submission
2. **Bid Success Modal** - Shows address after successful bid creation
3. **Backend Submission** - Receives complete address data in FormData

## Testing
1. Open test file: `test_bid_form_address_fix.html`
2. Verify DOM extraction works with simulated form fields
3. Create an actual bid in the application
4. Check console logs for successful address extraction
5. Verify confirmation modal displays all address components

## Files Modified
- `static/js/modals/bid_modal.js` (3 changes)
  - Lines 601-606: DOM-based address extraction
  - Lines 627-632: Append to FormData
  - Lines 730-752: Success modal address extraction

## Privacy Notice
The privacy notice in the confirmation modal is **correct and helpful**:
> "Your delivery address is hidden from sellers until your bid is accepted for the purpose of protecting user privacy."

This informs users that they can review their address for accuracy, but sellers won't see it until the bid is accepted.
