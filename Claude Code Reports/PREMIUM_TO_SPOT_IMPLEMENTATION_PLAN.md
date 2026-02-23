# Premium-to-Spot Pricing System - Implementation Plan

## Overview
This document outlines the complete implementation of a dual-mode pricing system for the Metex bullion marketplace, supporting both static pricing and dynamic premium-to-spot pricing based on live metal spot prices.

## Architecture Components

### 1. Data Model Changes

#### New Tables

**`spot_prices`** - Cache for live metal spot prices
```sql
CREATE TABLE spot_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metal TEXT NOT NULL UNIQUE,  -- 'gold', 'silver', 'platinum', 'palladium'
    price_usd_per_oz REAL NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source TEXT DEFAULT 'metalpriceapi'
);
```

**`price_locks`** - Temporary price locks during checkout
```sql
CREATE TABLE price_locks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    locked_price REAL NOT NULL,
    spot_price_at_lock REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    FOREIGN KEY (listing_id) REFERENCES listings(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

#### Modified Tables

**`listings`** - Add pricing mode fields
```sql
ALTER TABLE listings ADD COLUMN pricing_mode TEXT DEFAULT 'static' CHECK(pricing_mode IN ('static', 'premium_to_spot'));
ALTER TABLE listings ADD COLUMN spot_premium REAL DEFAULT 0;
ALTER TABLE listings ADD COLUMN floor_price REAL DEFAULT 0;
ALTER TABLE listings ADD COLUMN pricing_metal TEXT;  -- Override category metal if needed
```

**`order_items`** - Store price snapshot at purchase
```sql
ALTER TABLE order_items ADD COLUMN price_at_purchase REAL;
ALTER TABLE order_items ADD COLUMN pricing_mode_at_purchase TEXT;
ALTER TABLE order_items ADD COLUMN spot_price_at_purchase REAL;
```

### 2. Configuration

**`.env`** file additions:
```
METALPRICE_API_KEY=8dc91bf48c4415ff9af31933620821a9
METALPRICE_API_URL=https://api.metalpriceapi.com/v1
SPOT_PRICE_CACHE_TTL_SECONDS=300
PRICE_LOCK_DURATION_SECONDS=10
```

**`config.py`** additions:
```python
import os
from dotenv import load_dotenv

load_dotenv()

# Existing config...
SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key')

# New pricing config
METALPRICE_API_KEY = os.getenv('METALPRICE_API_KEY')
METALPRICE_API_URL = os.getenv('METALPRICE_API_URL', 'https://api.metalpriceapi.com/v1')
SPOT_PRICE_CACHE_TTL_SECONDS = int(os.getenv('SPOT_PRICE_CACHE_TTL_SECONDS', '300'))
PRICE_LOCK_DURATION_SECONDS = int(os.getenv('PRICE_LOCK_DURATION_SECONDS', '10'))
```

### 3. Core Services

#### `services/spot_price_service.py`
Handles fetching and caching live spot prices from MetalpriceAPI.

**Key Functions:**
- `get_current_spot_prices()` - Returns dict of current spot prices with caching
- `fetch_spot_prices_from_api()` - Fetches fresh data from API
- `update_spot_price_cache()` - Updates database cache
- `get_spot_price_for_metal(metal)` - Returns current price for specific metal

**Features:**
- 5-minute cache TTL (configurable)
- Graceful degradation if API unavailable
- Logging for debugging
- Error handling with fallback to last known values

#### `services/pricing_service.py`
Centralized pricing logic for all listing price calculations.

**Key Functions:**
- `get_effective_price(listing, spot_prices=None)` - Main price calculation
- `calculate_premium_to_spot_price(listing, spot_price)` - Spot + premium with floor
- `get_listing_with_price(listing_id)` - Returns listing with computed price
- `get_listings_with_prices(listing_ids)` - Batch price calculation
- `create_price_lock(listing_id, user_id)` - Create 10-second price lock
- `get_active_price_lock(listing_id, user_id)` - Check for existing lock
- `validate_price_lock(lock_id)` - Verify lock is still valid

**Logic Flow:**
```python
def get_effective_price(listing, spot_prices=None):
    if listing['pricing_mode'] == 'static':
        return listing['price_per_coin']
    elif listing['pricing_mode'] == 'premium_to_spot':
        if not spot_prices:
            spot_prices = get_current_spot_prices()

        metal = listing.get('pricing_metal') or listing['metal']
        spot_price = spot_prices.get(metal.lower())

        if not spot_price:
            # Fallback to static price or error
            return listing['price_per_coin'] or listing['floor_price']

        # Calculate: spot price per oz * weight + premium
        weight_oz = convert_to_ounces(listing)
        computed_price = (spot_price * weight_oz) + listing['spot_premium']

        # Apply floor
        return max(computed_price, listing['floor_price'])
```

### 4. Route Updates

#### `routes/sell_routes.py`
**Changes:**
- Update listing creation/editing to handle pricing mode selection
- Validate premium-to-spot fields
- Store pricing parameters in database

**New Endpoints:**
- None (modify existing)

#### `routes/buy_routes.py`
**Changes:**
- Use `pricing_service.get_effective_price()` for all listing displays
- Show pricing mode indicators
- Pass spot prices to templates

#### `routes/cart_routes.py`
**Changes:**
- Recalculate prices using `pricing_service` when cart is viewed
- Show price update warnings if dynamic prices changed
- Update cart totals with current prices

#### `routes/checkout_routes.py`
**Changes:**
- Implement price lock mechanism for dynamic listings
- Validate locks before order completion
- Store `price_at_purchase`, `pricing_mode_at_purchase`, `spot_price_at_purchase` in order_items
- Handle lock expiration with re-calculation and user notification

**New Endpoints:**
- `POST /checkout/lock-price` - Create price lock for dynamic listing
- `GET /checkout/validate-lock/<lock_id>` - Check if lock is still valid

#### `routes/portfolio_routes.py`
**Changes:**
- Cost basis uses `order_items.price_at_purchase` (locked price)
- Current market value uses `pricing_service.get_effective_price()` (live price)
- Historical charts show cost basis vs current value divergence for dynamic holdings

### 5. Frontend Updates

#### Templates

**`templates/sell.html`** - Listing Creation/Edit Form
- Add pricing mode toggle (radio buttons: Static / Premium to Spot)
- Show/hide relevant fields based on mode
- Static mode: `price_per_coin`
- Premium mode: `spot_premium`, `floor_price`, `pricing_metal` (optional override)
- Helper text explaining each field
- Real-time price preview using current spot data

**`templates/buy.html`** - Browse Listings
- Show pricing mode badge (e.g., "🏷️ Fixed" vs "📈 Live Spot")
- For premium-to-spot listings, show breakdown: "Spot $X + Premium $Y = $Z"
- Tooltip with explanation

**`templates/view_bucket.html`** - Bucket Details
- Show pricing modes for all listings in bucket
- Display price range with mode context

**`templates/view_cart.html`** - Cart
- Show price update warnings for dynamic listings
- Indicate when prices have changed since added to cart
- Refresh button to recalculate

**`templates/checkout.html`** - Checkout Flow
- For dynamic listings, show price lock countdown timer
- Display locked price clearly
- Show re-evaluation UI if lock expires
- Confirm button only active during lock window

**`templates/tabs/portfolio_tab.html`** - Portfolio
- Indicate static vs dynamic holdings
- Show locked cost basis vs current market value
- Highlight gains/losses that change with spot prices
- Add icon/badge for dynamic holdings

#### JavaScript

**`static/js/sell.js`**
- Toggle pricing mode UI
- Fetch current spot prices for preview
- Validate premium-to-spot inputs
- Real-time price calculation preview

**`static/js/checkout.js`**
- Implement price lock countdown timer
- Auto-refresh price when lock expires
- Show modal for price change notification
- Disable checkout during re-evaluation

**`static/js/tabs/portfolio_tab.js`**
- Fetch spot prices periodically
- Update dynamic holdings' current values
- Highlight price changes
- Show gain/loss percentages

**New JavaScript Module: `static/js/spot_prices.js`**
```javascript
// Centralized spot price fetching and caching
class SpotPriceManager {
    constructor() {
        this.cache = {};
        this.lastFetch = null;
        this.cacheTTL = 60000; // 1 minute
    }

    async getCurrentPrices() {
        if (this.isCacheValid()) {
            return this.cache;
        }
        return await this.fetchPrices();
    }

    async fetchPrices() {
        const response = await fetch('/api/spot-prices');
        this.cache = await response.json();
        this.lastFetch = Date.now();
        return this.cache;
    }

    isCacheValid() {
        return this.lastFetch && (Date.now() - this.lastFetch < this.cacheTTL);
    }
}
```

### 6. Migration Script

**`migrations/007_add_premium_to_spot_pricing.sql`**
```sql
-- Create spot_prices table
CREATE TABLE IF NOT EXISTS spot_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metal TEXT NOT NULL UNIQUE,
    price_usd_per_oz REAL NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source TEXT DEFAULT 'metalpriceapi'
);

-- Create price_locks table
CREATE TABLE IF NOT EXISTS price_locks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    locked_price REAL NOT NULL,
    spot_price_at_lock REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    FOREIGN KEY (listing_id) REFERENCES listings(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Add pricing columns to listings
ALTER TABLE listings ADD COLUMN pricing_mode TEXT DEFAULT 'static' CHECK(pricing_mode IN ('static', 'premium_to_spot'));
ALTER TABLE listings ADD COLUMN spot_premium REAL DEFAULT 0;
ALTER TABLE listings ADD COLUMN floor_price REAL DEFAULT 0;
ALTER TABLE listings ADD COLUMN pricing_metal TEXT;

-- Add price snapshot columns to order_items
ALTER TABLE order_items ADD COLUMN price_at_purchase REAL;
ALTER TABLE order_items ADD COLUMN pricing_mode_at_purchase TEXT;
ALTER TABLE order_items ADD COLUMN spot_price_at_purchase REAL;

-- Migrate existing data: set all existing listings to static mode
UPDATE listings SET pricing_mode = 'static', floor_price = price_per_coin WHERE pricing_mode IS NULL;

-- Backfill order_items with historical prices (use price_each as price_at_purchase)
UPDATE order_items SET price_at_purchase = price_each, pricing_mode_at_purchase = 'static' WHERE price_at_purchase IS NULL;

-- Create indexes for performance
CREATE INDEX idx_spot_prices_metal ON spot_prices(metal);
CREATE INDEX idx_price_locks_user_listing ON price_locks(user_id, listing_id);
CREATE INDEX idx_price_locks_expires ON price_locks(expires_at);
CREATE INDEX idx_listings_pricing_mode ON listings(pricing_mode);
```

**`run_migration_007.py`**
```python
import sqlite3

conn = sqlite3.connect('database.db')
cursor = conn.cursor()

with open('migrations/007_add_premium_to_spot_pricing.sql', 'r') as f:
    migration_sql = f.read()

cursor.executescript(migration_sql)
conn.commit()
conn.close()

print("Migration 007 completed: Premium-to-spot pricing system installed")
```

### 7. API Endpoints

**`routes/api_routes.py`** - Add new endpoints:

```python
@api_bp.route('/api/spot-prices', methods=['GET'])
def get_spot_prices():
    """Get current spot prices for all metals"""
    from services.spot_price_service import get_current_spot_prices

    try:
        prices = get_current_spot_prices()
        return jsonify({
            'success': True,
            'prices': prices,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@api_bp.route('/api/listing/<int:listing_id>/effective-price', methods=['GET'])
def get_listing_effective_price(listing_id):
    """Get current effective price for a listing"""
    from services.pricing_service import get_listing_with_price

    try:
        listing_with_price = get_listing_with_price(listing_id)
        return jsonify({
            'success': True,
            'listing_id': listing_id,
            'effective_price': listing_with_price['effective_price'],
            'pricing_mode': listing_with_price['pricing_mode']
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404
```

### 8. Testing Strategy

#### Unit Tests (`tests/test_pricing_service.py`)
- Test static pricing returns correct value
- Test premium-to-spot calculation
- Test floor price enforcement
- Test metal conversion (oz, grams, etc.)
- Test price lock creation and expiration

#### Integration Tests (`tests/test_premium_to_spot_flow.py`)
- Create premium-to-spot listing
- Verify price changes with spot updates
- Test checkout with price lock
- Test order completion stores correct snapshot
- Test portfolio shows correct cost basis vs current value

#### End-to-End Scenarios
1. **Static Listing Flow** - Ensure nothing breaks
2. **Premium Listing Creation** - Seller creates listing with $50 premium, $1800 floor
3. **Dynamic Price Display** - Buyer sees price update as spot changes
4. **Checkout with Lock** - 10-second countdown works, price locks, order completes
5. **Lock Expiration** - User waits 11 seconds, sees price re-evaluation
6. **Portfolio Tracking** - Cost basis locked, current value follows spot
7. **API Failure Handling** - MetalpriceAPI down, system degrades gracefully

### 9. Error Handling

#### Spot Price API Failures
**Scenario:** MetalpriceAPI is unreachable or returns error

**Handling:**
- Use last cached spot price from database
- Log error for monitoring
- Show warning to seller: "Unable to fetch live prices, using last known values"
- Allow static listings to continue working normally

**Code:**
```python
def get_current_spot_prices():
    try:
        # Try to fetch fresh prices
        return fetch_spot_prices_from_api()
    except Exception as e:
        logger.error(f"Failed to fetch spot prices: {e}")
        # Fall back to cached prices
        cached = get_cached_spot_prices()
        if cached:
            return cached
        else:
            # No cache available - critical error
            raise Exception("Unable to retrieve spot prices and no cache available")
```

#### Price Lock Expiration
**Scenario:** User takes > 10 seconds to confirm checkout

**Handling:**
- Detect expired lock on checkout attempt
- Fetch new spot prices
- Recalculate price
- Show modal: "Price updated from $X to $Y due to market changes"
- Create new price lock
- Allow user to confirm at new price

#### Missing Price Data
**Scenario:** Listing specifies metal not in spot price cache

**Handling:**
- Check if pricing_metal is valid
- If not, fall back to category metal
- If still missing, use floor_price
- Log warning for admin investigation

### 10. UI/UX Polish

#### Design Patterns

**Pricing Mode Toggle (Sell Page)**
```
[Radio Button] Static Price
  ├─ Price per coin: $____
  └─ (Simple, predictable pricing)

[Radio Button] Premium to Spot ⓘ
  ├─ Premium above spot: $____
  ├─ Floor price: $____
  ├─ Metal: [Auto-detect from category ▼]
  └─ (Price adjusts with live market rates)

  Current estimate: $2,047.50
  (Based on spot: $1,997.50 + premium: $50.00)
```

**Price Display (Buy Page Tile)**
```
Static listing:
  $1,850.00

Dynamic listing:
  $2,047.50 📈
  Spot $1,997.50 + $50.00 premium
```

**Price Lock Countdown (Checkout)**
```
┌─────────────────────────────────────┐
│ Price Locked: $2,047.50             │
│                                     │
│ This price is guaranteed for        │
│ ⏱️ 7 seconds                         │
│                                     │
│ [ Confirm Purchase ]                │
└─────────────────────────────────────┘
```

**Price Re-evaluation (After Lock Expires)**
```
┌─────────────────────────────────────┐
│ Price Updated                       │
│                                     │
│ The market price has changed:       │
│ Was: $2,047.50                      │
│ Now: $2,049.25 (+$1.75)             │
│                                     │
│ [ Cancel ] [ Confirm at New Price ] │
└─────────────────────────────────────┘
```

#### Tooltips

- "Premium to Spot": "Your price automatically adjusts with live precious metal markets. Set a premium above the spot price and a floor to protect against sudden drops."
- "Floor Price": "The minimum price you'll accept, even if spot prices fall."
- "Spot Premium": "The amount added to the current market spot price."

### 11. Implementation Checklist

- [ ] Install python-dotenv: `pip install python-dotenv requests`
- [ ] Create `.env` file with API key
- [ ] Update `config.py` with new settings
- [ ] Create `services/spot_price_service.py`
- [ ] Create `services/pricing_service.py`
- [ ] Create migration script 007
- [ ] Run migration: `python run_migration_007.py`
- [ ] Update `routes/sell_routes.py` for listing creation
- [ ] Update `routes/buy_routes.py` for price display
- [ ] Update `routes/cart_routes.py` for cart recalculation
- [ ] Update `routes/checkout_routes.py` for price locks
- [ ] Update `routes/portfolio_routes.py` for dual value tracking
- [ ] Add API endpoints to `routes/api_routes.py`
- [ ] Update `templates/sell.html` with pricing mode UI
- [ ] Update `templates/buy.html` with price mode badges
- [ ] Update `templates/checkout.html` with lock countdown
- [ ] Update `templates/tabs/portfolio_tab.html` with dynamic indicators
- [ ] Create `static/js/spot_prices.js` module
- [ ] Update `static/js/sell.js` for mode toggle
- [ ] Update `static/js/checkout.js` for countdown timer
- [ ] Update `static/js/tabs/portfolio_tab.js` for live updates
- [ ] Write unit tests
- [ ] Write integration tests
- [ ] Perform end-to-end testing
- [ ] Test API failure scenarios
- [ ] Document system in README

### 12. Performance Considerations

- Spot price cache reduces API calls to 1 per 5 minutes max
- Price locks table should be cleaned periodically (cron job to delete expired locks > 1 hour old)
- Batch price calculations when loading multiple listings
- Index on `listings.pricing_mode` for filtering
- Consider Redis for price caching in production (future enhancement)

### 13. Future Enhancements

- Historical spot price tracking for portfolio performance charts
- Alert notifications when spot prices move significantly
- Seller-defined auto-adjustment rules (e.g., "adjust premium by X% if spot moves Y%")
- Support for more metals (copper, rhodium, etc.)
- Multi-currency support
- GraphQL API for efficient data fetching

## Summary

This implementation provides a robust, professional premium-to-spot pricing system that:
- Maintains backward compatibility with static listings
- Integrates seamlessly with existing architecture
- Provides clear, intuitive UX for sellers and buyers
- Handles edge cases and failures gracefully
- Tracks cost basis and market value separately
- Implements fair price locking during checkout
- Is well-tested and production-ready
