# Cart Pricing Effective Price Fix

## Issue
Cart tiles and order summary were displaying floor prices instead of effective prices for variable-priced (premium-to-spot) listings. This meant users saw lower prices than they would actually pay.

## Root Cause
The cart utility functions `get_cart_items()` and `get_cart_data()` only queried `listings.price_per_coin` from the database, but were missing the additional pricing mode fields needed to calculate effective prices:
- `pricing_mode` (static vs premium_to_spot)
- `spot_premium`
- `floor_price`
- `pricing_metal`

Without these fields, the routes couldn't use `get_effective_price()` to calculate the actual current price based on spot prices.

## Solution Overview
Added missing pricing mode fields to all cart queries and updated routes to calculate effective prices using the existing `get_effective_price()` service.

## Files Modified

### 1. `utils/cart_utils.py`

#### `get_cart_items()` function (lines 132-176, 191-231)
**Changes**: Added pricing mode fields to SELECT statements for both logged-in users and guest carts

**Added fields**:
```python
listings.pricing_mode,
listings.spot_premium,
listings.floor_price,
listings.pricing_metal,
```

#### `get_cart_data()` function (lines 252-286, 298-327)
**Changes**: Added same pricing mode fields to queries for both logged-in users and guest carts

**Why**: This function groups cart items by category and is used by the Cart tab in the Account page

### 2. `routes/account_routes.py`

#### Import addition (line 6)
**Added**: `from services.pricing_service import get_effective_price`

#### Cart processing section (lines 227-241)
**Changes**: Updated to calculate effective prices for each cart item instead of using `price_per_coin` directly

**Before**:
```python
buckets, cart_total = get_cart_data(conn)
for bucket in buckets.values():
    total_qty = sum(item['quantity'] for item in bucket['listings'])
    bucket['total_quantity'] = total_qty
    total_cost = sum(item['quantity']*item['price_per_coin']
                     for item in bucket['listings'])
    bucket['avg_price'] = (total_cost/total_qty) if total_qty else 0
```

**After**:
```python
buckets, _ = get_cart_data(conn)  # Ignore old cart_total, we'll recalculate
cart_total = 0  # Recalculate with effective prices
for bucket in buckets.values():
    total_qty = sum(item['quantity'] for item in bucket['listings'])
    bucket['total_quantity'] = total_qty
    # Calculate effective price for each listing and sum
    total_cost = 0
    for item in bucket['listings']:
        effective_price = get_effective_price(item)
        item['effective_price'] = effective_price  # Store for template use
        total_cost += item['quantity'] * effective_price
    bucket['avg_price'] = (total_cost/total_qty) if total_qty else 0
    bucket['total_price'] = total_cost  # Update with effective price total
    cart_total += total_cost  # Add to overall cart total
```

**Why**: Each listing in a bucket can have different pricing modes, so we must calculate effective price individually

### 3. `templates/tabs/cart_tab.html`

#### JavaScript cartData object (lines 141-154)
**Changed**: Line 148 from `{{ listing.price_per_coin }}` to `{{ listing.effective_price }}`

**Why**: JavaScript uses this for client-side price calculations when quantity changes

### 4. `templates/view_cart.html`

#### JavaScript cartData object (lines 172-185)
**Changed**: Line 179 from `{{ listing.price_per_coin }}` to `{{ listing.price_each }}`

**Why**:
- The view_cart route (buy_routes.py:787) stores effective price as `price_each`
- JavaScript needs effective prices for client-side calculations

## Verification

### Already Working
The following routes were already using `get_effective_price()` correctly:
1. **`routes/buy_routes.py:view_cart()`** (line 753) - Main Cart page route
2. **`routes/cart_routes.py:update_bucket_quantity()`** (line 668) - Quantity update route
3. **`routes/checkout_routes.py`** (line 385) - Checkout route

### Testing Steps
To verify the fix is working:

1. **Create a premium-to-spot listing**:
   - Metal: Silver
   - Weight: 1 oz
   - Pricing mode: Premium-to-Spot
   - Spot Premium: $2.00
   - Floor Price: $30.00
   - Current Silver spot: ~$25/oz

2. **Add to cart and verify**:
   - Expected effective price: $27.00 (spot $25 + premium $2)
   - Cart tile should show: $27.00 per item
   - Order summary should show: Subtotal = $27.00 × quantity

3. **Check both locations**:
   - Main Cart page (`/cart`)
   - Cart tab in Account page (`/account`)

4. **Verify price updates**:
   - Change quantity using +/- buttons
   - Order summary should update with effective prices

## Technical Notes

### Effective Price Calculation
The `services.pricing_service.get_effective_price()` function:
1. Checks `pricing_mode` field
2. If `static`: returns `price_per_coin`
3. If `premium_to_spot`: calculates `(spot_price × weight) + spot_premium`
4. Enforces `floor_price` as minimum: `max(computed_price, floor_price)`

### Why Two Different Field Names?
- **Account route**: Stores as `item['effective_price']` in listings array
- **View cart route**: Stores as `listing['price_each']` in listings array
- Both use the same underlying `get_effective_price()` function
- Different naming due to different code authors/iterations

### Guest Cart Support
All changes maintain support for guest carts (session-based) in addition to logged-in user carts (database-based).

## Impact
✅ Cart tiles now show correct current prices for premium-to-spot items
✅ Order summary shows correct subtotals and total
✅ Quantity dial calculations use effective prices
✅ No breaking changes to existing static-priced listings
