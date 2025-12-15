# Buy Item Flow - Simplified Fix

## Problem

After fixing the "own listings skipped" modal to appear correctly, the Buy Item flow had two issues:

1. **Weird modal after notification**: After clicking OK on the notification, users were redirected to the `/checkout` page which showed a checkout modal with missing/incomplete data
2. **404 error on close**: Clicking the X button tried to navigate to `/cart` which doesn't exist (should be `/view_cart`)

## Root Cause

The Buy Item button was using **AJAX** to submit, but then trying to redirect to a full **checkout page**, creating a mismatch between:
- AJAX-based flow (used by Add to Cart)
- Page-based flow (used by checkout)

## Solution

**Simplified the Buy Item flow** to use traditional form submission instead of AJAX:

### Add to Cart (AJAX flow) ✅
1. AJAX POST to `/purchase_from_bucket/<bucket_id>`
2. Returns JSON with `user_listings_skipped` flag
3. Shows notification modal if needed
4. Redirects to `/view_cart` page

### Buy Item (Traditional flow) ✅
1. **Traditional POST** to `/checkout` (not AJAX)
2. Backend detects if user listings were skipped and sets session flag
3. Redirects to checkout page
4. Checkout page shows notification modal if session flag is set
5. User completes purchase through checkout page

## Files Modified

### 1. `static/js/add_to_cart_ajax.js`
**Changed:** Removed AJAX interception for Buy Item forms
- Lines 131-145: Buy Item now uses traditional form submission
- Removed all the complex AJAX handling code (~110 lines)
- Kept only quantity sync before submission

### 2. `static/js/checkout.js`
**Changed:** Fixed the cart redirect URL
- Line 33: Changed `/cart` → `/view_cart`

## How It Works Now

### Add to Cart:
```
Click Add to Cart
  ↓ (AJAX)
Backend processes & returns JSON
  ↓
Show notification modal (if needed)
  ↓
Redirect to /view_cart
```

### Buy Item:
```
Click Buy Item
  ↓ (Traditional POST)
Backend processes & sets session flag
  ↓
Redirect to /checkout page
  ↓
Checkout page shows notification modal (if flag set)
  ↓
User completes purchase
```

## Benefits

1. **Simpler code**: Removed ~110 lines of complex AJAX handling
2. **Consistent with existing flow**: Buy Item now works as originally designed
3. **No modal conflicts**: Each flow uses its appropriate modal system
4. **No 404 errors**: Fixed `/cart` → `/view_cart` redirect

## Testing

- ✅ Add to Cart: Shows modal, redirects to cart
- ✅ Buy Item: Traditional flow, no weird modals
- ✅ Both flows: Show "own listings skipped" notification when needed
- ✅ No 404 errors when closing modals

The Buy Item flow now works cleanly with the existing checkout page infrastructure!
