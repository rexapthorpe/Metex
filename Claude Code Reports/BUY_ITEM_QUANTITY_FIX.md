# Buy Item Quantity Field Fix

## Issue

When clicking the "Buy Item" button, the AJAX request returned HTML instead of JSON with the error:
```
SyntaxError: Unexpected token '<', "<!DOCTYPE "... is not valid JSON
```

## Root Cause

The Buy Item form has a hidden quantity input field (`#buyQuantityInput`) that is populated by JavaScript:

```html
<input type="hidden" name="quantity" id="buyQuantityInput">
```

When the form is submitted via AJAX, if the JavaScript hasn't populated this field yet, it remains empty.

In `routes/checkout_routes.py:22`, the code tried to convert this value to an integer:

```python
quantity = int(request.form.get('quantity', 1))
```

**The Problem:**
- When the form field exists but is empty, `request.form.get('quantity', 1)` returns an empty string `''` (not `None`)
- The default value `1` is only used if the field doesn't exist at all
- `int('')` raises a `ValueError: invalid literal for int() with base 10: ''`
- This exception caused Flask to return an error page as HTML (status 200)
- The AJAX code tried to parse this HTML as JSON, causing the SyntaxError

## Fix

Changed line 22 in `routes/checkout_routes.py`:

**Before:**
```python
quantity = int(request.form.get('quantity', 1))
```

**After:**
```python
quantity = int(request.form.get('quantity') or 1)  # Handle empty string
```

**How it works:**
- `request.form.get('quantity')` returns the value or `None` if field doesn't exist
- If the value is empty string `''`, the `or 1` ensures we use `1` as the default
- This handles both missing fields and empty fields correctly

## Files Modified

1. **`routes/checkout_routes.py:22`** - Fixed quantity parsing to handle empty strings

## Testing

The Buy Item button should now:
- ✅ Send AJAX request with session credentials
- ✅ Handle empty quantity field correctly
- ✅ Return JSON response from backend
- ✅ Show modal when user listings are skipped
- ✅ Redirect to checkout page after modal

## Related

This same pattern appears in `routes/buy_routes.py` for the Add to Cart flow, which was already working correctly because the form field is populated before submission. The Buy Item flow needed the same defensive handling for empty values.
