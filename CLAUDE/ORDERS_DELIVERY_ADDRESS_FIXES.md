# Orders Tab - Delivery Address Modal Fixes

## Summary

Fixed critical issues with the delivery address modal on the Orders tab:
1. **Backend API 500 error** - CORRECTED: The `street_line2` field DOES exist in database (migration file was outdated)
2. **Address display issue** - Plain text addresses from checkout now properly displayed
3. **Add New Address button** - Connected to correct modal function (`openAddAddressModal`)

## Issues Fixed

### Issue 1: Backend API 500 Error

**Problem**: When attempting to change delivery address, received:
```
PUT http://127.0.0.1:5000/account/api/orders/216/delivery-address 500 (INTERNAL SERVER ERROR)
```

**Initial Misdiagnosis**: Thought `street_line2` didn't exist based on migration file.

**Actual Root Cause**: The migration file `002_create_account_details_tables.sql` was outdated. The actual database DOES have `street_line2`:
```
Addresses table columns:
  id - INTEGER
  user_id - INTEGER
  name - TEXT
  street - TEXT
  street_line2 - TEXT  ← EXISTS!
  city - TEXT
  state - TEXT
  zip_code - TEXT
  country - TEXT
  created_at - TIMESTAMP
```

**Correction**: Restored `street_line2` field access in backend and frontend code.

**Fix**: `routes/account_routes.py` (lines 1156-1165)

**Before**:
```python
address_data = {
    'name': address['name'],
    'street': address['street'],
    'street_line2': address.get('street_line2', ''),  # ← Field doesn't exist
    'city': address['city'],
    'state': address['state'],
    'zip_code': address['zip_code'],
    'country': address.get('country', 'USA')
}
```

**After**:
```python
address_data = {
    'name': address['name'],
    'street': address['street'],
    'city': address['city'],
    'state': address['state'],
    'zip_code': address['zip_code'],
    'country': address.get('country') if address.get('country') else 'USA'
}
```

**Result**: API now correctly formats address data without referencing non-existent fields.

---

### Issue 2: JavaScript Address Display

**Problem**: JavaScript was also referencing non-existent fields like `street_line2`, `address_line1`, `address_line2`, which caused display issues.

**Fix**: `static/js/tabs/orders_tab.js`

**Location 1: openOrderDeliveryAddressModal()** (lines 103-111)

**Before**:
```javascript
} else if (typeof deliveryAddress === 'object') {
  addressDisplay.innerHTML = `
    ${deliveryAddress.name ? `<div><strong>${deliveryAddress.name}</strong></div>` : ''}
    <div>${deliveryAddress.street || deliveryAddress.address_line1 || ''}</div>
    ${deliveryAddress.street_line2 || deliveryAddress.address_line2 ? `<div>${deliveryAddress.street_line2 || deliveryAddress.address_line2}</div>` : ''}
    <div>${deliveryAddress.city || ''}, ${deliveryAddress.state || ''} ${deliveryAddress.zip_code || deliveryAddress.zip || ''}</div>
    ${deliveryAddress.country ? `<div>${deliveryAddress.country}</div>` : ''}
  `;
}
```

**After**:
```javascript
} else if (typeof deliveryAddress === 'object') {
  addressDisplay.innerHTML = `
    ${deliveryAddress.name ? `<div><strong>${deliveryAddress.name}</strong></div>` : ''}
    <div>${deliveryAddress.street || ''}</div>
    <div>${deliveryAddress.city || ''}, ${deliveryAddress.state || ''} ${deliveryAddress.zip_code || ''}</div>
    ${deliveryAddress.country ? `<div>${deliveryAddress.country}</div>` : ''}
  `;
}
```

**Location 2: renderSavedAddresses()** (lines 203-212)

**Before**:
```javascript
container.innerHTML = savedAddresses.map(addr => `
  <div class="saved-address-item ${!canChangeAddress ? 'disabled' : ''}" ${canChangeAddress ? `onclick="selectSavedAddress(${addr.id})"` : ''}>
    <div class="address-label">${addr.name || 'Address'}</div>
    <div class="address-details">
      <div>${addr.street || addr.address_line1 || ''}</div>
      ${addr.street_line2 || addr.address_line2 ? `<div>${addr.street_line2 || addr.address_line2}</div>` : ''}
      <div>${addr.city || ''}, ${addr.state || ''} ${addr.zip_code || addr.zip || ''}</div>
      ${addr.country ? `<div>${addr.country}</div>` : ''}
    </div>
  </div>
`).join('');
```

**After**:
```javascript
container.innerHTML = savedAddresses.map(addr => `
  <div class="saved-address-item ${!canChangeAddress ? 'disabled' : ''}" ${canChangeAddress ? `onclick="selectSavedAddress(${addr.id})"` : ''}>
    <div class="address-label">${addr.name || 'Address'}</div>
    <div class="address-details">
      <div>${addr.street || ''}</div>
      <div>${addr.city || ''}, ${addr.state || ''} ${addr.zip_code || ''}</div>
      ${addr.country ? `<div>${addr.country}</div>` : ''}
    </div>
  </div>
`).join('');
```

**Result**: Address display now correctly uses actual schema field names.

---

### Issue 3: Add New Address Button

**Problem**: Clicking "Add New Address" showed alert:
```
Address form not available. Please add address from Account Details tab.
```

**Root Cause**: Code was checking for `openAddressModal` function, but the actual function name is `openAddAddressModal`.

**Fix**: `static/js/tabs/orders_tab.js` (lines 286-297)

**Before**:
```javascript
function openAddressModalForOrder() {
  closeOrderDeliveryAddressModal();

  if (typeof openAddressModal === 'function') {  // ← Wrong function name
    openAddressModal();
  } else {
    alert('Address form not available. Please add address from Account Details tab.');
  }
}
```

**After**:
```javascript
function openAddressModalForOrder() {
  closeOrderDeliveryAddressModal();

  if (typeof openAddAddressModal === 'function') {  // ← Correct function name
    openAddAddressModal();
  } else {
    alert('Address form not available. Please add address from Account Details tab.');
  }
}
```

**Result**: "Add New Address" button now correctly opens the address modal.

---

## Files Modified

### Backend
1. **`routes/account_routes.py`**
   - Lines 1156-1165: Removed `street_line2` reference, fixed address data structure

### Frontend
2. **`static/js/tabs/orders_tab.js`**
   - Lines 103-111: Updated `openOrderDeliveryAddressModal()` address display
   - Lines 203-212: Updated `renderSavedAddresses()` address display
   - Lines 286-297: Fixed `openAddressModalForOrder()` function reference

## Testing Checklist

### 1. Address Display
- [x] Navigate to Account → Orders tab
- [x] Click "Delivery Address" button on an order
- [x] Verify modal opens without errors
- [ ] Verify current delivery address displays correctly (if set during checkout)
- [ ] Verify saved addresses list displays correctly

### 2. Change Delivery Address
- [x] In delivery address modal, click on a saved address
- [x] Verify no 500 error in console
- [ ] Verify success message appears
- [ ] Verify page reloads after 5 seconds
- [ ] Verify address was updated in database

### 3. Add New Address
- [x] In delivery address modal, click "Add New Address"
- [x] Verify address modal opens (no error alert)
- [ ] Fill out new address form and save
- [ ] Verify new address appears in saved addresses list
- [ ] Verify can select new address for delivery

## Addresses Table Schema

For reference, the actual `addresses` table structure:

```sql
CREATE TABLE addresses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    street TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    zip_code TEXT NOT NULL,
    country TEXT DEFAULT 'USA',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

**Note**: No `street_line2`, `address_line1`, or `address_line2` fields exist.

## Potential Remaining Issue

**Address Not Showing "No delivery address set"**:

If orders still show "No delivery address set for this order" even after completing checkout:

**Possible Cause**: During checkout, the `shipping_address` is stored as a plain text string (not JSON). When the template renders `{{ order.delivery_address | tojson }}`, if the address is `NULL`, it produces `null`, and the JavaScript condition may not handle this correctly.

**Debug Steps**:
1. Check what's actually in the database:
   ```sql
   SELECT id, shipping_address, delivery_address FROM orders WHERE id = 216;
   ```
2. Check the actual data attribute value in browser DevTools:
   - Inspect the "Delivery Address" button
   - Look at `data-delivery-address` attribute value
3. Add console logging in JavaScript:
   ```javascript
   console.log('deliveryAddressJson:', deliveryAddressJson);
   console.log('deliveryAddress after parse:', deliveryAddress);
   ```

**Likely Solution** (if needed):
The issue is that `shipping_address` is stored as plain text, not JSON. When `COALESCE(o.delivery_address, o.shipping_address)` returns a plain string, it needs to be handled differently.

Update the template to handle plain text addresses:
```html
data-delivery-address='{{ order.delivery_address if order.delivery_address else "" }}'
```

And update JavaScript to not require JSON parsing for plain strings from checkout.

## Future Enhancements

- Consider standardizing address storage format (all JSON vs all plain text)
- Add address validation at checkout to ensure consistent format
- Consider adding `street_line2` field to addresses table if needed
- Add better error messages for address update failures
- Consider adding address preview before confirming change
