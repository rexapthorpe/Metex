# Premium-to-Spot Implementation - Session Progress

**Session Date:** 2025-11-29
**Current Status:** ~45% Complete

---

## ✅ COMPLETED THIS SESSION

### Phase 1: Infrastructure (100% Complete)

1. **Database Migration 007**
   - Created `spot_prices` table for caching live metal prices
   - Created `price_locks` table for checkout price guarantees
   - Added pricing mode columns to `listings` (pricing_mode, spot_premium, floor_price, pricing_metal)
   - Added pricing snapshot columns to `order_items` (price_at_purchase, pricing_mode_at_purchase, spot_price_at_purchase)
   - Migration executed successfully
   - All existing data backfilled

2. **Core Services**
   - `services/spot_price_service.py` - MetalpriceAPI integration with 5-min caching
   - `services/pricing_service.py` - Centralized pricing logic
   - Supports both static and premium-to-spot modes
   - Floor price enforcement
   - 10-second price lock mechanism
   - Weight conversion utilities

3. **Configuration**
   - Updated `config.py` with pricing variables
   - Created `.env` file with API key: `8dc91bf48c4415ff9af31933620821a9`

4. **API Endpoints** (`routes/api_routes.py`)
   - `GET /api/spot-prices` - Fetch current spot prices
   - `POST /api/spot-prices/refresh` - Manual refresh
   - `POST /api/price-lock/create` - Create price lock during checkout
   - `GET /api/price-lock/get/<listing_id>` - Check active locks

5. **Sell Routes** (`routes/sell_routes.py`)
   - Updated to accept `pricing_mode` parameter
   - Validation for both static and premium-to-spot modes
   - INSERT statement updated to save all pricing fields
   - Proper error handling for invalid inputs

---

## 🚧 IN PROGRESS

- Sell page UI (template and JavaScript) - 0% complete

---

## ⏳ REMAINING WORK

### Critical Path (Required for Functional System)

**1. Sell Page UI** (Priority: CRITICAL)
- Update `templates/sell.html` with pricing mode radio buttons
- Add premium-to-spot form fields (premium, floor, pricing metal)
- Show/hide fields based on selected mode
- Update `static/js/sell.js` for validation and price preview
- **Estimated effort:** 2-3 hours

**2. Buy Routes & Display** (Priority: CRITICAL)
- Update `routes/buy_routes.py` to use `get_effective_price()`
- Replace manual price calculations with pricing service
- Add pricing mode badges to `templates/buy.html`
- Update bucket aggregation logic
- **Estimated effort:** 2-3 hours

**3. Cart Routes & Display** (Priority: CRITICAL)
- Update `routes/cart_routes.py` to recalculate dynamic prices
- Add price change warnings to `templates/view_cart.html`
- Update cart totals to use effective prices
- **Estimated effort:** 2 hours

**4. Checkout with Price Lock** (Priority: CRITICAL)
- Update `routes/checkout_routes.py` to create price locks
- Implement lock validation before order confirmation
- Add countdown timer to `templates/checkout.html`
- Update `static/js/checkout.js` for timer logic
- Store locked prices in `order_items.price_at_purchase`
- **Estimated effort:** 3-4 hours

**5. Portfolio Dual Value Tracking** (Priority: HIGH)
- Update `routes/portfolio_routes.py` to track cost basis vs current value
- Modify portfolio value calculation for dynamic items
- Add dynamic indicators to `templates/tabs/portfolio_tab.html`
- Update `static/js/tabs/portfolio_tab.js` for live value display
- **Estimated effort:** 2-3 hours

### Supporting Features (Nice to Have)

**6. UI/UX Polish** (Priority: MEDIUM)
- Add professional error messages
- Add helper text and tooltips
- Consistent badge styling
- Loading states for price updates
- **Estimated effort:** 1-2 hours

**7. Testing** (Priority: MEDIUM)
- Unit tests for pricing services
- Integration tests for checkout flow
- Manual end-to-end testing
- **Estimated effort:** 2-3 hours

---

## 📋 DETAILED REMAINING TASKS

### Task 1: Sell Page UI

**File:** `templates/sell.html`

Add after the price_per_coin field:

```html
<!-- Pricing Mode Selection -->
<div class="form-group">
    <label for="pricing_mode">Pricing Mode:</label>
    <div class="pricing-mode-options">
        <label class="radio-option">
            <input type="radio" name="pricing_mode" value="static" id="pricing_mode_static" checked>
            <span>Fixed Price</span>
            <small>Set a fixed USD price per coin</small>
        </label>
        <label class="radio-option">
            <input type="radio" name="pricing_mode" value="premium_to_spot" id="pricing_mode_premium">
            <span>Premium to Spot</span>
            <small>Price based on live spot + premium</small>
        </label>
    </div>
</div>

<!-- Static Price Field (existing, show by default) -->
<div class="form-group" id="static_price_group">
    <label for="price_per_coin">Price Per Coin ($):</label>
    <input type="number" step="0.01" name="price_per_coin" id="price_per_coin">
</div>

<!-- Premium-to-Spot Fields (hidden by default) -->
<div id="premium_to_spot_fields" style="display: none;">
    <div class="form-group">
        <label for="spot_premium">Premium Above Spot ($):</label>
        <input type="number" step="0.01" name="spot_premium" id="spot_premium" placeholder="e.g., 100.00">
        <small>Amount to add above the current spot price</small>
    </div>

    <div class="form-group">
        <label for="floor_price">Floor Price ($):</label>
        <input type="number" step="0.01" name="floor_price" id="floor_price" placeholder="e.g., 2000.00">
        <small>Minimum price - protects against spot price drops</small>
    </div>

    <div class="form-group">
        <label for="pricing_metal">Pricing Metal:</label>
        <select name="pricing_metal" id="pricing_metal">
            <option value="">Use category metal</option>
            <option value="gold">Gold</option>
            <option value="silver">Silver</option>
            <option value="platinum">Platinum</option>
            <option value="palladium">Palladium</option>
        </select>
        <small>Which metal's spot price to use (defaults to category metal)</small>
    </div>

    <div class="price-preview" id="price_preview" style="display: none;">
        <strong>Current Preview Price:</strong>
        <span class="preview-amount">$0.00</span>
        <small>Based on current spot: <span class="spot-price">$0.00</span>/oz</small>
    </div>
</div>
```

**File:** `static/js/sell.js`

Add price mode toggle logic:

```javascript
// Toggle between pricing modes
document.querySelectorAll('input[name="pricing_mode"]').forEach(radio => {
    radio.addEventListener('change', function() {
        const staticGroup = document.getElementById('static_price_group');
        const premiumFields = document.getElementById('premium_to_spot_fields');

        if (this.value === 'static') {
            staticGroup.style.display = 'block';
            premiumFields.style.display = 'none';
            document.getElementById('price_per_coin').required = true;
            document.getElementById('spot_premium').required = false;
            document.getElementById('floor_price').required = false;
        } else {
            staticGroup.style.display = 'none';
            premiumFields.style.display = 'block';
            document.getElementById('price_per_coin').required = false;
            document.getElementById('spot_premium').required = true;
            document.getElementById('floor_price').required = true;

            // Load spot prices for preview
            loadSpotPricesForPreview();
        }
    });
});

// Load spot prices and update preview
async function loadSpotPricesForPreview() {
    try {
        const response = await fetch('/api/spot-prices');
        const data = await response.json();

        if (data.success) {
            window.spotPrices = data.prices;
            updatePricePreview();
        }
    } catch (error) {
        console.error('Error loading spot prices:', error);
    }
}

// Update price preview when inputs change
['spot_premium', 'floor_price', 'pricing_metal', 'weight', 'metal'].forEach(fieldId => {
    const field = document.getElementById(fieldId);
    if (field) {
        field.addEventListener('input', updatePricePreview);
        field.addEventListener('change', updatePricePreview);
    }
});

function updatePricePreview() {
    if (!window.spotPrices) return;

    const metal = document.getElementById('pricing_metal').value || document.getElementById('metal').value;
    const weight = parseFloat(document.getElementById('weight').value) || 1.0;
    const premium = parseFloat(document.getElementById('spot_premium').value) || 0;
    const floor = parseFloat(document.getElementById('floor_price').value) || 0;

    const spotPrice = window.spotPrices[metal.toLowerCase()];

    if (spotPrice) {
        const computedPrice = (spotPrice * weight) + premium;
        const effectivePrice = Math.max(computedPrice, floor);

        document.querySelector('.preview-amount').textContent = `$${effectivePrice.toFixed(2)}`;
        document.querySelector('.spot-price').textContent = `$${spotPrice.toFixed(2)}`;
        document.getElementById('price_preview').style.display = 'block';
    }
}
```

---

### Task 2: Buy Routes

**File:** `routes/buy_routes.py`

Replace price calculations with:

```python
from services.pricing_service import get_listings_with_effective_prices

# Instead of using listing['price_per_coin'] directly:
listings = get_listings_with_effective_prices(category_id=category_id)

# Each listing now has listing['effective_price']
```

---

### Task 3: Cart Routes

Similar to buy routes - use centralized pricing

---

### Task 4: Checkout Routes

**Key changes:**
1. Create price locks before confirmation
2. Validate locks haven't expired
3. Store `price_at_purchase` with locked price
4. Add countdown timer UI

---

### Task 5: Portfolio Routes

**Key changes:**
1. Cost basis = `order_items.price_at_purchase` (historical)
2. Current value = calculated using `get_effective_price()` for each holding
3. Gains/losses = current value - cost basis

---

## 🎯 RECOMMENDED NEXT STEPS

Due to the substantial remaining work, I recommend:

**Option A: Continue Implementation (Recommended)**
- Complete sell page UI next (1-2 hours)
- Then wire centralized pricing into buy/cart/checkout routes (3-4 hours)
- Add portfolio dual tracking (2-3 hours)
- Polish and test (2-3 hours)
- **Total estimated time:** 8-12 hours of development

**Option B: Phased Approach**
- Phase 1: Complete sell flow first (get premium-to-spot listings working)
- Phase 2: Update buy/display to show dynamic prices correctly
- Phase 3: Add checkout price locks
- Phase 4: Portfolio tracking and polish

**Option C: Minimal Viable Product**
- Skip advanced UI for now
- Focus on backend integration
- Get basic premium-to-spot listings working
- Polish UI later

---

## 💾 WHAT'S SAVED AND READY

All of these are complete and saved:

- `migrations/007_add_premium_to_spot_pricing.sql`
- `run_migration_007.py`
- `services/spot_price_service.py`
- `services/pricing_service.py`
- `config.py` (updated)
- `.env` (created with API key)
- `routes/api_routes.py` (updated)
- `routes/sell_routes.py` (updated)
- `PREMIUM_TO_SPOT_IMPLEMENTATION_PLAN.md`
- `PREMIUM_TO_SPOT_IMPLEMENTATION_STATUS.md`

Database has been migrated successfully.

---

## 🧪 TESTING CHECKLIST (Once Implementation Complete)

- [ ] Static listings still work (backward compatibility)
- [ ] Create premium-to-spot listing with valid inputs
- [ ] Premium-to-spot listing shows correct dynamic price on buy page
- [ ] Price updates when spot changes
- [ ] Floor price enforced when spot drops below floor
- [ ] Price lock works in checkout (10 second timer)
- [ ] Locked price stored in order_items.price_at_purchase
- [ ] Portfolio shows cost basis (fixed) vs current value (dynamic)
- [ ] Gains/losses update with spot price changes
- [ ] Bucket aggregation works with mixed static/dynamic listings
- [ ] Cart recalculates dynamic prices on each load
- [ ] Error handling works (API failures, expired locks, etc.)

---

**End of Progress Report**
