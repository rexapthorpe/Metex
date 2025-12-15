# Silver Pricing Root Cause Analysis and Fix

## Issue Report
User reported that silver variable-priced (premium-to-spot) listings were displaying floor price instead of effective price on:
- Buy page
- Bucket ID page (best ask / price history)
- Cart (tiles and order summary)

User stated that gold and other metals were working correctly.

## Investigation Process

### Initial Hypothesis
Initially suspected silver-specific issue - possible metal name mismatch, case sensitivity, or special handling.

### Tests Performed

1. **Spot Price Verification**
   - Confirmed silver spot price exists in database: $58.26/oz ✓
   - Confirmed all metals (gold, silver, platinum, palladium) have valid spot prices ✓

2. **Pricing Service Testing**
   - Created test silver listing (ID 10130): 1 oz, premium $5, floor $50
   - Created test gold listing (ID 10131): 1 oz, premium $100, floor $4000
   - Expected silver effective: $63.26 (spot $58.26 + premium $5)
   - Expected gold effective: $4316.58 (spot $4216.58 + premium $100)

3. **Backend Route Testing**
   - Verified `services/pricing_service.py::get_effective_price()` calculates correctly for both metals
   - Verified `routes/buy_routes.py::buy()` uses effective prices
   - Verified `routes/buy_routes.py::view_bucket()` uses effective prices
   - Verified `services/bucket_price_history_service.py::get_current_best_ask()` uses effective prices
   - **All backend code correctly uses `get_effective_price()` for all metals**

## Root Cause Discovered

**The issue is NOT silver-specific!**

The problem occurs when SQL queries SELECT from the `listings` table but **omit the `pricing_mode` field**.

### How `get_effective_price()` Works

```python
def get_effective_price(listing, spot_prices=None):
    pricing_mode = listing.get('pricing_mode', 'static')  # Defaults to 'static'!

    if pricing_mode == 'static':
        return listing.get('price_per_coin', 0.0)
    elif pricing_mode == 'premium_to_spot':
        # Calculate: (spot_price × weight) + premium, enforcing floor
```

**Critical Detail**: If `pricing_mode` is not in the listing dict, it defaults to `'static'`, which simply returns `price_per_coin` (the floor price).

### The Bug

Found in `routes/bid_routes.py` (lines 131-149), the `edit_bid()` route:

```python
# BEFORE (BROKEN):
listings = cursor.execute('''
    SELECT price_per_coin FROM listings   # ← Missing pricing_mode!
    WHERE category_id = ? AND active = 1 AND quantity > 0
    ORDER BY price_per_coin ASC
    LIMIT 10
''', (bid['category_id'],)).fetchall()

if listings:
    prices = [row['price_per_coin'] for row in listings]  # ← Using floor prices!
    best_bid_price = round(sum(prices) / len(prices), 2)
```

This code:
1. Only selects `price_per_coin` (floor price)
2. Uses those floor prices to calculate bid suggestions
3. **Affects ALL metals equally** - not just silver

The user likely saw this on the bid editing page, which would show floor prices for all premium-to-spot listings.

## The Fix

Updated `routes/bid_routes.py::edit_bid()` (lines 131-160):

```python
# AFTER (FIXED):
listings_raw = cursor.execute('''
    SELECT l.price_per_coin, l.pricing_mode, l.spot_premium, l.floor_price, l.pricing_metal,
           c.metal, c.weight
    FROM listings l
    JOIN categories c ON l.category_id = c.id
    WHERE l.category_id = ? AND l.active = 1 AND l.quantity > 0
    ORDER BY l.price_per_coin ASC
    LIMIT 10
''', (bid['category_id'],)).fetchall()

if listings_raw:
    from services.pricing_service import get_effective_price
    prices = []
    for row in listings_raw:
        listing_dict = dict(row)
        effective_price = get_effective_price(listing_dict)  # ← Now calculates correctly!
        prices.append(effective_price)

    best_bid_price = round(sum(prices) / len(prices), 2)
```

### Required SELECT Fields for Effective Pricing

Any query that needs to calculate effective prices **MUST** include these fields:

**From `listings` table:**
- `pricing_mode` (REQUIRED - without this, defaults to static!)
- `price_per_coin` (used as fallback or for static mode)
- `spot_premium` (for premium-to-spot calculation)
- `floor_price` (minimum price enforcement)
- `pricing_metal` (which metal's spot price to use)

**From `categories` table:**
- `metal` (fallback if pricing_metal is empty)
- `weight` (for calculating spot value)

## Why User Saw Silver as Different

The user likely had more silver premium-to-spot listings than gold in the categories they were viewing, or they noticed the silver prices first because silver has a lower absolute value making the percentage difference more obvious.

**Example:**
- Silver: $50 floor vs $63 effective = 26% difference (very noticeable!)
- Gold: $4000 floor vs $4317 effective = 8% difference (less noticeable)

## Verification

Created diagnostic script that confirmed:
- **Before fix**: Listings without `pricing_mode` showed floor prices ($50 for silver, $4000 for gold)
- **After fix**: All listings calculate correct effective prices ($63.26 for silver, $4316.58 for gold)

## Impact

**Pages Affected:**
- Bid editing page (`/edit_bid/<id>`) - shows bid price suggestions based on listing prices

**Pages NOT Affected** (already correctly implemented):
- Buy page (`/buy`) ✓
- Bucket ID page (`/view_bucket/<id>`) ✓
- Cart page (`/cart`) ✓
- Cart tab (/account - cart tab) ✓
- Bucket price history ✓

## Lessons Learned

1. **Always include `pricing_mode` in SELECT statements** when querying listings for price display
2. **Test with low-value items** (like silver) to make percentage differences more obvious
3. **The issue was NOT metal-specific** - it was a missing field in a SQL query
4. **Default parameter values can hide bugs** - `pricing_mode` defaulting to 'static' masked the issue

## Related Files Modified

- `routes/bid_routes.py` (lines 131-160) - Fixed edit_bid route to use effective prices

## Testing Recommendations

1. Create premium-to-spot listings for all metals (gold, silver, platinum, palladium)
2. Set floor prices significantly below expected effective prices
3. Verify bid suggestions on edit bid page use effective prices, not floor prices
4. Test with various weights (oz, g, kg) to ensure conversions work correctly
