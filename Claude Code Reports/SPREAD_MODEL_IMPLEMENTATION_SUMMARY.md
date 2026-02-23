# Spread Model Autofill Implementation - Complete Summary

## Overview

Implemented a comprehensive spread model for bid-listing matching that works for all combinations of fixed and variable pricing:
- Fixed bid ↔ Fixed listing
- Fixed bid ↔ Variable listing
- Variable bid ↔ Fixed listing
- Variable bid ↔ Variable listing

## Pricing Model

### Fixed Pricing
- **Fixed Listing**: Effective price = fixed price (listing.price_per_coin)
- **Fixed Bid**: Effective price = fixed price (bid.price_per_coin)

### Variable Pricing
- **Variable Listing**:
  - Raw price = spot_price + listing.premium_to_spot
  - Effective price = max(raw_price, listing.floor_price)
  - Never goes below floor price

- **Variable Bid**:
  - Raw price = spot_price + bid.premium_to_spot
  - Effective price = min(raw_price, bid.ceiling_price)
  - Never goes above ceiling price

## Matching Rule

```
Match if and only if: bid_effective_price >= listing_effective_price
```

Works for ALL 4 combinations.

## Execution Pricing (The Spread Model)

When a bid fills a listing:

- **Buyer pays**: `bid_effective_price` per unit
- **Seller receives**: `listing_effective_price` per unit
- **Metex spread**: `bid_effective_price - listing_effective_price` per unit (always >= 0)

### Example
- Bid effective price: $1,100
- Listing effective price: $1,000
- Buyer pays: $1,100 ✓
- Seller receives: $1,000 ✓
- Metex keeps: $100 ✓

## Code Changes

### 1. Database Migration
**File**: `migrations/009_add_seller_price_to_order_items.sql`

Added `seller_price_each` column to `order_items` table:
- `price_each` = what buyer pays (bid effective price)
- `seller_price_each` = what seller receives (listing effective price)

Backfilled existing records with `price_each` for backwards compatibility.

### 2. Pricing Service Helpers
**File**: `services/pricing_service.py` (lines 488-591)

#### `can_bid_fill_listing(bid, listing, spot_prices=None)`
Determines if a bid can fill a listing.

**Returns**:
```python
{
    'can_fill': bool,
    'bid_effective_price': float,
    'listing_effective_price': float,
    'spread': float
}
```

**Logic**:
1. Calculate bid effective price using `get_effective_bid_price()`
2. Calculate listing effective price using `get_effective_price()`
3. Match if bid_effective >= listing_effective
4. Return spread = bid_effective - listing_effective

#### `calculate_trade_prices(bid, listing, quantity, spot_prices=None)`
Calculates execution prices for a trade.

**Returns**:
```python
{
    'buyer_unit_price': float,      # Per unit buyer pays
    'seller_unit_price': float,     # Per unit seller receives
    'spread_unit': float,            # Per unit spread
    'buyer_total': float,            # Total buyer pays
    'seller_total': float,           # Total seller receives
    'spread_total': float            # Total Metex keeps
}
```

### 3. Autofill Logic Updates
**File**: `routes/bid_routes.py` (lines 1126-1216)

**Imports** (lines 7-12):
```python
from services.pricing_service import (
    get_effective_price,
    get_effective_bid_price,
    can_bid_fill_listing,
    calculate_trade_prices
)
```

**Matching Logic** (lines 1126-1150):
```python
# Check if bid can fill this listing (works for all 4 combinations)
pricing_info = can_bid_fill_listing(bid_dict, listing_dict, spot_prices=spot_prices)

if pricing_info['can_fill']:
    # Store pricing info on the listing for later use
    listing_dict['bid_effective_price'] = pricing_info['bid_effective_price']
    listing_dict['listing_effective_price'] = pricing_info['listing_effective_price']
    listing_dict['spread'] = pricing_info['spread']
    matched_listings.append(listing_dict)
```

**Price Storage** (lines 1176-1185):
```python
# SPREAD MODEL:
# - Buyer pays: bid effective price
# - Seller receives: listing effective price
# - Metex keeps: bid effective - listing effective
seller_fills[seller_id].append({
    'listing_id': listing['id'],
    'quantity': fill_qty,
    'buyer_price_each': listing['bid_effective_price'],      # What buyer pays
    'seller_price_each': listing['listing_effective_price']  # What seller receives
})
```

**Order Creation** (lines 1205-1216):
```python
# Create order_items with BOTH buyer and seller prices
for item in items:
    cursor.execute('''
        INSERT INTO order_items (order_id, listing_id, quantity, price_each, seller_price_each)
        VALUES (?, ?, ?, ?, ?)
    ''', (
        order_id,
        item['listing_id'],
        item['quantity'],
        item['buyer_price_each'],   # What buyer pays
        item['seller_price_each']   # What seller receives
    ))
```

### 4. Display Logic Updates

#### Sold Items (Seller View)
**File**: `routes/account_routes.py` (line 275)

```python
COALESCE(oi.seller_price_each, oi.price_each) AS price_each,
```

Sellers see what they **receive** (seller_price_each).
Falls back to price_each for old orders created before spread model.

#### Orders (Buyer View)
**File**: `routes/account_routes.py` (line 95)

```python
SUM(oi.quantity*oi.price_each)*1.0/SUM(oi.quantity) AS price_each,
```

Buyers see what they **pay** (price_each) - no changes needed.

## Test Results

All 6 test scenarios passed:

### Scenario A: Fixed ↔ Fixed
- Listing: $1,000 (fixed)
- Bid: $1,100 (fixed)
- ✓ Match: Buyer pays $1,100, Seller gets $1,000, Spread $100

### Scenario B: Fixed Bid ↔ Variable Listing
- Spot: $1,900
- Listing: premium -$800, floor $1,050 → Effective: $1,100
- Bid: $1,150 (fixed)
- ✓ Match: Buyer pays $1,150, Seller gets $1,100, Spread $50

### Scenario C: Variable Bid ↔ Fixed Listing
- Spot: $1,900
- Bid: premium -$800, ceiling $1,200 → Effective: $1,100
- Listing: $1,050 (fixed)
- ✓ Match: Buyer pays $1,100, Seller gets $1,050, Spread $50

### Scenario D: Variable ↔ Variable
- Spot: $1,900
- Bid: premium -$700, ceiling $1,250 → Effective: $1,200
- Listing: premium -$900, floor $950 → Effective: $1,000
- ✓ Match: Buyer pays $1,200, Seller gets $1,000, Spread $200

### Scenario D Variant: Variable ↔ Variable (Higher Floor)
- Spot: $1,900
- Bid: premium -$700, ceiling $1,250 → Effective: $1,200
- Listing: premium -$900, floor $1,150 → Effective: $1,150
- ✓ Match: Buyer pays $1,200, Seller gets $1,150, Spread $50

### Scenario: No Match
- Listing: $1,200 (fixed)
- Bid: $1,000 (fixed)
- ✓ Correctly rejected (bid too low)

## Edge Cases Handled

1. **Spot Price Source**: Uses current spot price from `spot_prices` service at time of fill
2. **Rounding**: All prices rounded to 2 decimal places
3. **Quantity**: Supports partial fills, spread applied per unit then multiplied
4. **Fixed-Only Behavior**: Works as expected (buyer pays bid, seller gets listing, spread = difference)
5. **Backwards Compatibility**: Old orders display correctly using COALESCE fallback

## Verification

Run the comprehensive test:
```bash
python test_spread_model_autofill.py
```

Expected output: All 6 tests pass with correct pricing calculations.

## Summary

The spread model is now fully implemented and working correctly. All four pricing combinations (fixed/variable bid × fixed/variable listing) match correctly, and the system properly:
- Stores both buyer and seller prices separately
- Displays correct prices in Sold Items (seller view) and Orders (buyer view)
- Calculates and captures the spread for Metex

No breaking changes to existing functionality - all non-autofill paths continue to work as before.
