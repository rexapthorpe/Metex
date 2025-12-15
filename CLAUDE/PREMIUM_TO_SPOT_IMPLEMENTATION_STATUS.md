# Premium-to-Spot Pricing Implementation Status

## Overview

This document tracks the implementation progress of the dual-mode pricing system (static and premium-to-spot) for the Metex bullion marketplace.

**Implementation Started:** Session Date
**Last Updated:** 2025-11-29

---

## ✅ COMPLETED - Phase 1: Foundation & Infrastructure

### 1. Database Schema (Migration 007)

**Status:** ✅ COMPLETE

**Files Created:**
- `migrations/007_add_premium_to_spot_pricing.sql`
- `run_migration_007.py`

**Schema Changes:**

#### New Tables:
```sql
-- spot_prices: Caches live metal prices from MetalpriceAPI
CREATE TABLE spot_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metal TEXT NOT NULL UNIQUE,
    price_usd_per_oz REAL NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source TEXT DEFAULT 'metalpriceapi'
);

-- price_locks: Temporary price guarantees during checkout
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

#### Modified Tables:
```sql
-- listings: Added dual pricing mode support
ALTER TABLE listings ADD COLUMN pricing_mode TEXT DEFAULT 'static';
ALTER TABLE listings ADD COLUMN spot_premium REAL DEFAULT 0;
ALTER TABLE listings ADD COLUMN floor_price REAL DEFAULT 0;
ALTER TABLE listings ADD COLUMN pricing_metal TEXT;

-- order_items: Preserves pricing snapshot at purchase
ALTER TABLE order_items ADD COLUMN price_at_purchase REAL;
ALTER TABLE order_items ADD COLUMN pricing_mode_at_purchase TEXT;
ALTER TABLE order_items ADD COLUMN spot_price_at_purchase REAL;
```

**Migration Result:**
- All existing listings backfilled to `pricing_mode = 'static'`
- All existing order_items backfilled with pricing snapshots
- Seed data: 4 spot prices (gold, silver, platinum, palladium)

---

### 2. Core Services

**Status:** ✅ COMPLETE

#### A. Spot Price Service (`services/spot_price_service.py`)

**Purpose:** Fetches and caches live metal spot prices from MetalpriceAPI

**Key Functions:**
- `get_current_spot_prices()` - Returns dict of {metal: price_per_oz}, uses cache if fresh
- `fetch_spot_prices_from_api()` - Fetches fresh data from MetalpriceAPI
- `save_spot_prices_to_cache()` - Stores prices in database
- `get_cached_spot_prices()` - Retrieves cached prices
- `is_cache_fresh()` - Checks if cache is within TTL (default 5 minutes)
- `get_spot_price(metal)` - Get price for a specific metal
- `refresh_spot_prices()` - Manual refresh trigger
- `get_spot_price_age()` - Get cache age in minutes

**Features:**
- 5-minute cache TTL (configurable via SPOT_PRICE_CACHE_TTL_MINUTES)
- Graceful degradation: Falls back to stale cache if API fails
- Logging for debugging
- Supports: gold, silver, platinum, palladium

**API Integration:**
- Base URL: https://api.metalpriceapi.com/v1
- Endpoint: /latest
- API Key: Loaded from .env (METALPRICE_API_KEY)

---

#### B. Pricing Service (`services/pricing_service.py`)

**Purpose:** Centralized pricing logic - SINGLE SOURCE OF TRUTH for "what is the price of this listing right now"

**Key Functions:**
- `get_effective_price(listing, spot_prices=None)` - **Core function**: Calculates price based on mode
- `get_listing_with_effective_price(listing_id)` - Returns listing with computed effective price
- `create_price_lock(listing_id, user_id, lock_duration_seconds=10)` - Creates temporary price guarantee
- `get_active_price_lock(listing_id, user_id)` - Retrieves active lock if exists
- `cleanup_expired_price_locks()` - Removes expired locks
- `get_price_for_order_item(order_item)` - Determines price (locked or current)
- `get_listings_with_effective_prices(...)` - Batch pricing calculation

**Pricing Logic:**

```python
# Static Mode
if pricing_mode == 'static':
    return listing['price_per_coin']

# Premium-to-Spot Mode
elif pricing_mode == 'premium_to_spot':
    spot_price_per_oz = get_spot_price(pricing_metal)
    weight_oz = listing['weight']
    computed_price = (spot_price_per_oz * weight_oz) + listing['spot_premium']
    effective_price = max(computed_price, listing['floor_price'])
    return round(effective_price, 2)
```

**Features:**
- Floor price enforcement
- Weight conversion helpers (oz, g, kg, lb)
- 10-second price locks during checkout (configurable)
- Fallback to static/floor price if spot data unavailable

---

### 3. Configuration

**Status:** ✅ COMPLETE

**Files Modified:**
- `config.py` - Added pricing configuration variables
- `.env` - Created with API key and settings

**Configuration Variables:**
```python
# config.py
METALPRICE_API_KEY = os.getenv('METALPRICE_API_KEY')
PRICE_LOCK_DURATION_SECONDS = int(os.getenv('PRICE_LOCK_DURATION_SECONDS', '10'))
SPOT_PRICE_CACHE_TTL_MINUTES = int(os.getenv('SPOT_PRICE_CACHE_TTL_MINUTES', '5'))
```

**.env Contents:**
```
METALPRICE_API_KEY=8dc91bf48c4415ff9af31933620821a9
PRICE_LOCK_DURATION_SECONDS=10
SPOT_PRICE_CACHE_TTL_MINUTES=5
```

---

### 4. API Endpoints

**Status:** ✅ COMPLETE

**Files Modified:**
- `routes/api_routes.py` - Added 4 new endpoints

**New Endpoints:**

#### GET /api/spot-prices
**Purpose:** Fetch current spot prices for all metals
**Returns:**
```json
{
    "success": true,
    "prices": {
        "gold": 2050.25,
        "silver": 24.50,
        "platinum": 950.00,
        "palladium": 1000.00
    },
    "age_minutes": 2.3
}
```

#### POST /api/spot-prices/refresh
**Purpose:** Manually refresh spot prices from API
**Returns:** Updated prices after refresh

#### POST /api/price-lock/create
**Purpose:** Create a temporary price lock during checkout
**Request:**
```json
{
    "listing_id": 123,
    "duration_seconds": 10
}
```
**Returns:**
```json
{
    "success": true,
    "price_lock": {
        "id": 456,
        "listing_id": 123,
        "locked_price": 2150.00,
        "spot_price_at_lock": 2050.00,
        "expires_at": "2025-11-29T12:00:10",
        "duration_seconds": 10
    }
}
```

#### GET /api/price-lock/get/<listing_id>
**Purpose:** Check if user has an active price lock
**Returns:** Lock details or `has_lock: false`

---

## 🚧 IN PROGRESS - Phase 2: Business Logic & Routes

### Status Summary
- **Sell Routes:** Pending - Need to add pricing mode selection UI and handling
- **Buy Routes:** Pending - Need to use centralized pricing service
- **Cart Routes:** Pending - Need to recalculate dynamic prices
- **Checkout Routes:** Pending - Need to implement price lock flow
- **Portfolio Routes:** Pending - Need to track cost basis vs current value

### Next Steps:

1. **Update Sell Routes** (`routes/sell_routes.py`)
   - Add pricing mode parameter handling in listing creation
   - Allow sellers to choose: static vs premium-to-spot
   - For premium-to-spot: Accept spot_premium, floor_price, pricing_metal

2. **Update Buy Routes** (`routes/buy_routes.py`)
   - Replace direct `price_per_coin` usage with `get_effective_price()`
   - Display pricing mode badges (e.g., "🔄 Dynamic Pricing")

3. **Update Cart Routes** (`routes/cart_routes.py`)
   - Recalculate prices for premium-to-spot listings on each page load
   - Show price change warnings if prices updated

4. **Update Checkout Routes** (`routes/checkout_routes.py`)
   - Create price locks for premium-to-spot items
   - Implement 10-second countdown timer
   - Validate locks before order confirmation
   - Store locked prices in order_items.price_at_purchase

5. **Update Portfolio Routes** (`routes/portfolio_routes.py`)
   - Calculate current market value using live spot prices for dynamic items
   - Track cost basis (price_at_purchase) separately
   - Show gains/losses that update with spot prices

---

## ⏳ PENDING - Phase 3: Frontend & UI

### JavaScript Modules

**Pending:** Create `static/js/spot_prices.js`

**Purpose:** Frontend spot price management

**Functionality Needed:**
```javascript
class SpotPriceManager {
    async getCurrentPrices() { /* Fetch from /api/spot-prices */ }
    calculateEffectivePrice(listing, spotPrices) { /* Client-side pricing */ }
    subscribe(callback) { /* Notify on price updates */ }
}
```

---

### Template Updates

#### ⏳ Sell Page (`templates/sell.html`, `static/js/sell.js`)
**Pending:**
- Pricing mode radio buttons (Static / Premium-to-Spot)
- Show/hide premium-to-spot fields based on selection
- Real-time price preview using current spot prices
- Floor price input with validation

**UI Design:**
```
[ Pricing Mode ]
○ Static Price
● Premium-to-Spot

[ Premium Above Spot ] $____
[ Floor Price (minimum) ] $____
[ Pricing Metal ] [Dropdown: Gold/Silver/etc.]

Live Preview: Current Price = $2,150.00
(Based on: Gold spot $2,050/oz + $100 premium)
```

---

#### ⏳ Buy Page (`templates/buy.html`)
**Pending:**
- Pricing mode badges next to price
- "Price updates with spot market" indicator for dynamic listings
- Spot price reference display

**UI Design:**
```
Price: $2,150.00 [🔄 Dynamic]
└─ Based on current spot: $2,050/oz + $100 premium
```

---

#### ⏳ Cart Page (`templates/view_cart.html`)
**Pending:**
- Price update warnings if dynamic prices changed
- "Prices may change at checkout" notice
- Show pricing mode for each item

**UI Example:**
```
⚠️ 2 items have updated prices based on current spot prices:
   - Gold Eagle: $2,100 → $2,150 (+$50)
```

---

#### ⏳ Checkout Page (`templates/checkout.html`, `static/js/checkout.js`)
**Pending:**
- Price lock countdown timer (10 seconds)
- Lock creation flow
- Re-lock button if timer expires
- Lock expiration handling

**UI Design:**
```
[ Confirm Order ]

Price Lock Active: ⏱️ 8 seconds remaining

Your prices are guaranteed for 8 more seconds.
Complete your purchase now to secure these prices.

[Confirm Purchase] [Cancel]
```

---

#### ⏳ Portfolio Page (`templates/tabs/portfolio_tab.html`, `static/js/tabs/portfolio_tab.js`)
**Pending:**
- "Static" vs "Dynamic" indicators on holdings
- Live value updates for dynamic items
- Gains/losses that change with spot prices
- Cost basis vs current value breakdown

**UI Example:**
```
Holdings:
┌─────────────────────────────────────────────┐
│ Gold Eagle (2023) [🔄 Dynamic]             │
│ Qty: 5 | Cost Basis: $10,000               │
│ Current Value: $10,750 (+$750 / +7.5%)     │
│ ↑ Price increased $50 since last update    │
└─────────────────────────────────────────────┘
```

---

## 🧪 PENDING - Phase 4: Testing

### Unit Tests
- [ ] Test spot price service (API fetch, caching, fallbacks)
- [ ] Test pricing service (static vs dynamic calculations, floor enforcement)
- [ ] Test price lock creation and expiration
- [ ] Test weight conversions

### Integration Tests
- [ ] Full checkout flow with price locks
- [ ] Cart price recalculation on page load
- [ ] Portfolio value updates with spot price changes
- [ ] Order creation with pricing snapshots

### End-to-End Tests
- [ ] Seller creates premium-to-spot listing
- [ ] Buyer views listing with dynamic price
- [ ] Buyer adds to cart, price updates
- [ ] Buyer checks out with price lock
- [ ] Order confirms with locked price
- [ ] Portfolio shows correct cost basis and current value

---

## 📊 Implementation Progress

### Overall Status: **40% Complete**

**Completed:**
- ✅ Database schema (100%)
- ✅ Core services (100%)
- ✅ Configuration (100%)
- ✅ API endpoints (100%)

**In Progress:**
- 🚧 Route updates (0%)

**Pending:**
- ⏳ Frontend JavaScript (0%)
- ⏳ Template updates (0%)
- ⏳ Testing (0%)

---

## 🔑 Key Technical Decisions

### 1. Centralized Pricing Logic
**Decision:** All price calculations go through `pricing_service.get_effective_price()`
**Rationale:** Single source of truth prevents inconsistencies

### 2. Database Caching for Spot Prices
**Decision:** Cache in `spot_prices` table with 5-minute TTL
**Rationale:** Reduces API calls, enables fallback if API is down

### 3. Price Locks vs Real-Time Pricing
**Decision:** 10-second price lock window during checkout
**Rationale:** Balances user experience (time to confirm) with market volatility

### 4. Snapshot Pricing on Orders
**Decision:** Store `price_at_purchase`, `pricing_mode_at_purchase`, `spot_price_at_purchase` in order_items
**Rationale:** Preserves historical cost basis for portfolio tracking

### 5. Floor Price Enforcement
**Decision:** `effective_price = max(computed_price, floor_price)`
**Rationale:** Protects sellers from extreme spot price drops

---

## 🚀 Next Actions

### Immediate (Critical Path):
1. Update sell routes to accept pricing mode parameters
2. Update buy routes to use centralized pricing
3. Update cart routes for dynamic price recalculation
4. Update checkout routes for price lock flow
5. Create basic frontend price display (without full UI polish)

### Short-Term:
6. Update portfolio routes for dual value tracking
7. Create spot_prices.js frontend module
8. Add pricing mode UI to sell page
9. Add price lock countdown to checkout

### Medium-Term:
10. Polish all UI/UX elements
11. Add comprehensive error handling
12. Write test suite
13. Performance optimization

---

## 🐛 Known Issues & Limitations

### Current Limitations:
1. **No Historical Spot Prices:** Uses current spot price for all historical portfolio values
   - **Impact:** Portfolio history chart doesn't reflect actual spot prices at past dates
   - **Future Fix:** Create `market_price_history` table with daily snapshots

2. **Weight Assumptions:** Assumes all weights in database are troy ounces
   - **Impact:** Incorrect pricing if weight units are inconsistent
   - **Future Fix:** Add `weight_unit` column to categories table

3. **Single Metal Per Listing:** Each listing can only track one metal for spot pricing
   - **Impact:** Multi-metal coins must choose primary metal
   - **Acceptable:** Most coins are single-metal

### Error Handling:
- **API Failure:** Falls back to cached prices (may be stale)
- **No Spot Price:** Falls back to static price or floor price
- **Expired Lock:** User must re-confirm with new price

---

## 📝 Documentation

### For Sellers:
- How to create a premium-to-spot listing
- Understanding premium and floor price
- How pricing updates work

### For Buyers:
- What dynamic pricing means
- Price lock during checkout
- Why prices may change in cart

### For Developers:
- See: `PREMIUM_TO_SPOT_IMPLEMENTATION_PLAN.md` for full technical spec
- See: This document for current status and next steps

---

## ✅ Verification Checklist

Before marking complete, verify:

### Backend:
- [ ] Spot prices fetch successfully from API
- [ ] Prices cache correctly in database
- [ ] Static listings still work (backward compatibility)
- [ ] Premium-to-spot listings calculate correctly
- [ ] Floor price enforced
- [ ] Price locks create and expire correctly
- [ ] Order snapshots preserve pricing data

### Frontend:
- [ ] Sellers can choose pricing mode
- [ ] Buyers see correct prices
- [ ] Cart prices update when spot changes
- [ ] Checkout price lock works
- [ ] Timer displays correctly
- [ ] Portfolio shows dynamic values

### Data Integrity:
- [ ] All existing listings have pricing_mode='static'
- [ ] All existing orders have pricing snapshots
- [ ] No price calculation errors
- [ ] Database constraints enforced

---

**End of Status Document**
