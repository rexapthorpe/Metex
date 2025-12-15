# Modal Fix - Complete Implementation

## Issues Identified

From the console output you provided, I identified these critical issues:

1. **[AddToCartAJAX] Found 0 Add to Cart forms** - The AJAX selector was using the wrong URL pattern
2. **window.showOwnListingsSkippedModal was a function instead of boolean** - The modal script was overwriting the flag
3. **Buy Item button missing user listings skip logic** - The checkout route didn't filter user's own listings

## Fixes Applied

### Fix #1: AJAX Selector Mismatch

**Problem:** The AJAX script searched for `'form[action*="auto_fill_bucket_purchase"]'` but the actual route URL is `/purchase_from_bucket/<bucket_id>`

**Solution:**
- Updated selector in `static/js/add_to_cart_ajax.js` line 12 from `auto_fill_bucket_purchase` to `purchase_from_bucket`

```javascript
// OLD (wrong)
const addToCartForms = document.querySelectorAll('form[action*="auto_fill_bucket_purchase"]');

// NEW (correct)
const addToCartForms = document.querySelectorAll('form[action*="purchase_from_bucket"]');
```

**Result:** AJAX script now finds the Add to Cart forms correctly

---

### Fix #2: Function Overwriting Boolean Flag

**Problem:** Line 84 of `own_listings_skipped_modal.js` was:
```javascript
window.showOwnListingsSkippedModal = showOwnListingsSkippedModal;
```

This overwrote any boolean flag set by the template with the function itself. When the script checked `if (window.showOwnListingsSkippedModal === true)`, it was comparing a function to `true`, which always failed.

**Console showed:**
```
window.showOwnListingsSkippedModal: ƒ showOwnListingsSkippedModal() { ... }  Type: function
```

**Solution:**
- Renamed global functions to avoid collision with boolean flags

**Files modified:**

1. `static/js/modals/own_listings_skipped_modal.js` (lines 84-85):
```javascript
// OLD
window.showOwnListingsSkippedModal = showOwnListingsSkippedModal;
window.hideOwnListingsSkippedModal = hideOwnListingsSkippedModal;

// NEW
window.showOwnListingsSkippedModalFunc = showOwnListingsSkippedModal;
window.hideOwnListingsSkippedModalFunc = hideOwnListingsSkippedModal;
```

2. `static/js/add_to_cart_ajax.js` (lines 64, 80, 94, 106):
- Updated all references from `showOwnListingsSkippedModal` to `window.showOwnListingsSkippedModalFunc`
- Updated all references from `hideOwnListingsSkippedModal` to `window.hideOwnListingsSkippedModalFunc`

**Result:** Boolean flags from templates are no longer overwritten

---

### Fix #3: Buy Item Button Missing User Listings Skip Logic

**Problem:** The "Buy Item" button goes through `checkout_routes.py` which didn't filter out user's own listings or support the modal flow.

**Solution:** Added complete user listings filtering and AJAX support to the checkout route

**Files modified:**

1. **`routes/checkout_routes.py`** (lines 147-248):

   **Added seller_id to query** (line 151):
   ```python
   SELECT l.id, l.quantity, l.price_per_coin, l.pricing_mode,
          l.spot_premium, l.floor_price, l.pricing_metal, l.seller_id,  # ← Added
          c.metal, c.weight, c.product_type
   ```

   **Separated user listings from others** (lines 176-191):
   ```python
   # Calculate effective prices and separate user's listings from others
   user_listings = []
   other_listings = []

   for listing in listings_raw:
       listing_dict = dict(listing)
       listing_dict['effective_price'] = get_effective_price(listing_dict)

       if listing_dict['seller_id'] == user_id:
           user_listings.append(listing_dict)
       else:
           other_listings.append(listing_dict)

   # Sort by effective price
   user_listings.sort(key=lambda x: x['effective_price'])
   other_listings.sort(key=lambda x: x['effective_price'])
   ```

   **Auto-fill from other sellers only** (lines 193-217):
   ```python
   # Try to fill from other sellers first (skip user's own listings)
   selected = []
   remaining = quantity
   user_listings_skipped = False

   for listing in other_listings:
       if remaining <= 0:
           break
       take = min(listing['quantity'], remaining)
       selected.append({
           'listing_id': listing['id'],
           'quantity': take,
           'price_each': listing['effective_price']
       })
       remaining -= take

   # Track if we had to skip user's listings that would have been selected
   if user_listings and remaining < quantity:
       # Check if user had competitive listings that got skipped
       for user_listing in user_listings:
           # If user's listing price is competitive with what we selected, it was skipped
           if selected and user_listing['effective_price'] <= max(item['price_each'] for item in selected):
               user_listings_skipped = True
               print(f"[CHECKOUT] User listing at ${user_listing['effective_price']:.2f} was skipped")
               break
   ```

   **Added AJAX detection and JSON response** (lines 224-248):
   ```python
   # Check if this is an AJAX request (from Buy Item button)
   is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

   if is_ajax:
       # Return JSON for AJAX requests (so modal can be shown before redirect)
       print(f"[CHECKOUT] AJAX request. user_listings_skipped={user_listings_skipped}, items_selected={len(selected)}")
       # Store selection in session for when user is redirected
       session['checkout_items'] = selected
       conn.close()
       return jsonify({
           'success': True,
           'user_listings_skipped': user_listings_skipped and len(selected) > 0,
           'items_selected': len(selected),
           'message': f'{len(selected)} item(s) selected for checkout'
       })
   else:
       # Traditional redirect for non-AJAX requests (backward compatibility)
       if user_listings_skipped and len(selected) > 0:
           session['show_own_listings_skipped_modal'] = True
           print(f"[CHECKOUT] User listings were skipped. Setting session flag. User ID: {user_id}")

       # Keep the selection in session for the GET render and final POST
       session['checkout_items'] = selected
       conn.close()
       return redirect(url_for('checkout.checkout'))
   ```

2. **`static/js/add_to_cart_ajax.js`** (lines 11-21, 130-235):

   **Find Buy Item forms** (lines 14-18):
   ```javascript
   // Find Buy Item forms (forms with action containing "checkout" that have bucket_id input)
   const allCheckoutForms = document.querySelectorAll('form[action*="checkout"]');
   const buyItemForms = Array.from(allCheckoutForms).filter(form =>
       form.querySelector('input[name="bucket_id"]')
   );
   ```

   **Added event listeners for Buy Item forms** (lines 130-235):
   - Intercepts form submission
   - Sends AJAX POST with `X-Requested-With: XMLHttpRequest` header
   - Shows modal if `user_listings_skipped === true`
   - Redirects to `/checkout` after modal dismissed
   - Falls back to immediate redirect if no modal needed

**Result:** Both "Buy Item" and "Add to Cart" buttons now:
- Filter out user's own listings
- Show modal when user listings are skipped
- Redirect to appropriate page after modal dismissed

---

## Complete Flow Comparison

### OLD FLOW (Broken):
```
1. User clicks "Add to Cart" or "Buy Item"
2. Form submits traditionally
3. Backend processes but doesn't detect issue
4. User redirected immediately
5. Modal never appears (multiple bugs prevented it)
```

### NEW FLOW (Fixed):
```
1. User clicks "Add to Cart" or "Buy Item"
2. JavaScript intercepts form submission
3. AJAX POST sent to backend with X-Requested-With header
4. Backend filters out user's own listings
5. Backend returns JSON: {user_listings_skipped: true/false}
6. IF skipped:
   a. Modal appears IMMEDIATELY (before redirect)
   b. User clicks OK
   c. Redirect to cart or checkout page
7. IF not skipped:
   a. Immediate redirect (no modal)
```

---

## Expected Console Output

### When User Listings ARE Skipped:

**Backend:**
```
[CHECKOUT] User listing at $140.00 was skipped
[CHECKOUT] AJAX request. user_listings_skipped=True, items_selected=1
```

**Frontend:**
```
[BucketPurchaseAJAX] Initializing...
[BucketPurchaseAJAX] Found 1 Add to Cart forms
[BucketPurchaseAJAX] Found 1 Buy Item forms
[BucketPurchaseAJAX] Buy Item form submitted - intercepting
[BucketPurchaseAJAX] Sending AJAX POST to: /checkout
[BucketPurchaseAJAX] Response status: 200
[BucketPurchaseAJAX] Response data: {success: true, user_listings_skipped: true, ...}
[BucketPurchaseAJAX] User listings were skipped - showing modal
[OwnListingsSkippedModal] Showing modal
[BucketPurchaseAJAX] Modal OK clicked - redirecting to checkout
```

### When User Listings NOT Skipped:

**Backend:**
```
[CHECKOUT] AJAX request. user_listings_skipped=False, items_selected=1
```

**Frontend:**
```
[BucketPurchaseAJAX] Buy Item form submitted - intercepting
[BucketPurchaseAJAX] Response data: {success: true, user_listings_skipped: false, ...}
[BucketPurchaseAJAX] No user listings skipped - redirecting to checkout
```

---

## Files Modified

1. **static/js/add_to_cart_ajax.js**
   - Fixed selector to match actual route URL
   - Renamed function references to avoid overwriting flags
   - Added Buy Item form handling
   - Added AJAX interception for both buttons

2. **static/js/modals/own_listings_skipped_modal.js**
   - Renamed global function exports to avoid collision

3. **routes/checkout_routes.py**
   - Added seller_id to listings query
   - Added user listings filtering logic
   - Added user_listings_skipped tracking
   - Added AJAX detection and JSON response
   - Maintained backward compatibility

---

## Testing

### Test Scenario 1: Add to Cart (User Listings Skipped)
1. Create your own listing at $140 (lowest price)
2. Have another seller's listing at $145
3. Click "Add to Cart"
4. **Expected:**
   - Modal appears immediately
   - After clicking OK, redirects to cart page
   - Console shows modal-related logs

### Test Scenario 2: Buy Item (User Listings Skipped)
1. Create your own listing at $140 (lowest price)
2. Have another seller's listing at $145
3. Click "Buy Item"
4. **Expected:**
   - Modal appears immediately
   - After clicking OK, redirects to checkout page
   - Console shows modal-related logs

### Test Scenario 3: No User Listings
1. Create your own listing at $150
2. Have another seller's listing at $140 (lowest)
3. Click either button
4. **Expected:**
   - No modal appears
   - Immediate redirect
   - Clean UX

---

## Diagnostic Tool

Created `diagnose_modal_issue.py` to automatically detect these issues in the future. Run with:

```bash
python diagnose_modal_issue.py
```

This will check:
- AJAX selector matches route URLs
- Buy Item route has skipping logic
- No function overwrites boolean flags

---

## Success Criteria

✅ Console shows `[BucketPurchaseAJAX] Found 1 Add to Cart forms` (not 0)
✅ Console shows `[BucketPurchaseAJAX] Found 1 Buy Item forms` (not 0)
✅ `window.showOwnListingsSkippedModal` is boolean `true`/`false`, not a function
✅ Modal appears immediately after clicking button (before redirect)
✅ Modal only appears when user's listings are actually skipped
✅ Both "Buy Item" and "Add to Cart" buttons work correctly

---

## Conclusion

All three critical bugs have been fixed:
1. ✅ AJAX selector now finds the forms
2. ✅ Boolean flags no longer overwritten by functions
3. ✅ Buy Item button now filters user listings and supports modal

The modal should now appear correctly for both buttons when user's listings are skipped!
