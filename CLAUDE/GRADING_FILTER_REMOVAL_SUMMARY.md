# Grading Filter Removal - Complete Summary

## Overview
Removed the old "Require 3rd Party Grading" dropdown/filter from the Bucket ID page, keeping only the new "Add Third-Party Grading Service" toggle (buyer add-on feature).

## Problem
The Bucket ID page had two grading-related controls:
1. **OLD**: "Require 3rd Party Grading" dropdown - A filter to show only graded listings
2. **NEW**: "Add Third-Party Grading Service" toggle - A buyer add-on service

This was confusing and the old filter was no longer needed.

## Solution
Completely removed the old grading filter while preserving the new buyer add-on toggle.

## Files Modified

### 1. `templates/view_bucket.html`

#### Removed Grading Filter Section (Lines 274-307)
**Deleted:**
```html
<!-- ===================== Grading filter tile (collapsible) ===================== -->
<section class="grading-tile" id="gradingTile" aria-label="Require 3rd Party Grading">
  <div class="soft grading-kicker">Filter for professionally graded items</div>
  <button type="button" id="gradingToggleBtn" class="btn grading-toggle-btn" aria-expanded="false" aria-controls="gradingPanel">
    Require 3rd Party Grading?
    <span class="chev" aria-hidden="true">▸</span>
  </button>

  <div id="gradingPanel" class="grading-panel" hidden>
    <div class="grading-rows">
      <div class="grading-row">
        <div class="glabel">Any Grader</div>
        <label class="toggle">
          <input type="checkbox" id="switchAny" autocomplete="off" {% if graded_only and any_grader %}checked{% endif %}>
          <span class="slider"></span>
        </label>
      </div>
      <div class="grading-row">
        <div class="glabel">PCGS</div>
        <label class="toggle">
          <input type="checkbox" id="switchPCGS" autocomplete="off" {% if graded_only and pcgs %}checked{% endif %}>
          <span class="slider"></span>
        </label>
      </div>
      <div class="grading-row">
        <div class="glabel">NGC</div>
        <label class="toggle">
          <input type="checkbox" id="switchNGC" autocomplete="off" {% if graded_only and ngc %}checked{% endif %}>
          <span class="slider"></span>
        </label>
      </div>
    </div>
  </div>
</section>
```

#### Removed Hidden Grading Filter Inputs (Lines 412-415)
**Deleted:**
```html
<!-- Hidden grading inputs updated by JS -->
<input type="hidden" id="gradedOnlyInput" name="graded_only" value="{{ 1 if graded_only else 0 }}">
<input type="hidden" id="anyGraderInput" name="any_grader" value="{{ 1 if graded_only and any_grader else 0 }}">
<input type="hidden" id="pcgsInput" name="pcgs" value="{{ 1 if graded_only and pcgs else 0 }}">
<input type="hidden" id="ngcInput" name="ngc" value="{{ 1 if graded_only and ngc else 0 }}">
```

#### Removed Grading Filter from Buy Form (Lines 446-449)
**Before:**
```html
<form method="POST" action="{{ url_for('checkout.checkout') }}" class="action-buttons">
  <input type="hidden" name="bucket_id" value="{{ bucket['bucket_id'] }}">
  <input type="hidden" name="quantity" id="buyQuantityInput">
  <input type="hidden" name="third_party_grading" id="buyTPG">
  <!-- forward grading too (harmless if checkout ignores) -->
  <input type="hidden" name="graded_only" id="buyGradedOnly">
  <input type="hidden" name="any_grader" id="buyAnyGrader">
  <input type="hidden" name="pcgs" id="buyPcgs">
  <input type="hidden" name="ngc" id="buyNgc">
  <!-- Random Year mode -->
  <input type="hidden" name="random_year" id="buyRandomYear" value="{{ '1' if random_year else '0' }}">
  <button type="submit" class="btn buy-btn" onclick="syncQuantityAndTPG('buyQuantityInput', 'buyTPG')">Buy Item</button>
</form>
```

**After:**
```html
<form method="POST" action="{{ url_for('checkout.checkout') }}" class="action-buttons">
  <input type="hidden" name="bucket_id" value="{{ bucket['bucket_id'] }}">
  <input type="hidden" name="quantity" id="buyQuantityInput">
  <input type="hidden" name="third_party_grading" id="buyTPG">
  <!-- Random Year mode -->
  <input type="hidden" name="random_year" id="buyRandomYear" value="{{ '1' if random_year else '0' }}">
  <button type="submit" class="btn buy-btn" onclick="syncQuantityAndTPG('buyQuantityInput', 'buyTPG')">Buy Item</button>
</form>
```

#### Removed Grading Filter from Cart Form (Lines 464-467)
**Before:**
```html
<form method="POST" action="{{ url_for('buy.auto_fill_bucket_purchase', bucket_id=bucket['bucket_id']) }}" class="action-buttons">
  <input type="hidden" name="quantity_to_buy" id="cartQuantityInput">
  <input type="hidden" name="third_party_grading" id="cartTPG">
  <input type="hidden" name="graded_only" id="cartGradedOnly">
  <input type="hidden" name="any_grader" id="cartAnyGrader">
  <input type="hidden" name="pcgs" id="cartPcgs">
  <input type="hidden" name="ngc" id="cartNgc">
  <button type="submit" class="btn add-cart-btn" onclick="syncQuantityAndTPG('cartQuantityInput', 'cartTPG')">Add to Cart</button>
</form>
```

**After:**
```html
<form method="POST" action="{{ url_for('buy.auto_fill_bucket_purchase', bucket_id=bucket['bucket_id']) }}" class="action-buttons">
  <input type="hidden" name="quantity_to_buy" id="cartQuantityInput">
  <input type="hidden" name="third_party_grading" id="cartTPG">
  <button type="submit" class="btn add-cart-btn" onclick="syncQuantityAndTPG('cartQuantityInput', 'cartTPG')">Add to Cart</button>
</form>
```

#### Kept: New Grading Add-On Toggle
**Preserved (Lines 396-406):**
```html
<!-- Third-Party Grading Add-On (buyer-side service) -->
<div class="tpg-addon-row" style="margin-top: 16px; padding: 12px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; display: flex; align-items: center; justify-content: space-between;">
  <div style="flex: 1;">
    <div style="font-weight: 600; font-size: 14px; color: #111827; margin-bottom: 4px;">Add Third-Party Grading Service</div>
    <div style="font-size: 13px; color: #6b7280;">Professional authentication and grading (+$30/item)</div>
  </div>
  <label class="toggle" style="margin-left: 16px;">
    <input type="checkbox" id="tpgToggle" autocomplete="off">
    <span class="slider"></span>
  </label>
</div>
```

### 2. `static/js/view_bucket.js`

#### Removed Entire Grading Filter Function (Lines 270-428)
**Deleted:**
- `initGradingTile()` function
- Panel toggle/collapse logic
- Switch event handlers (switchAny, switchPCGS, switchNGC)
- Availability refresh logic with grading filters
- Mutually exclusive toggle handling

**Impact:** JavaScript no longer manages grading filter state or updates availability based on grading filters.

### 3. `routes/buy_routes.py`

#### Removed Grading Filter Parameters from `view_bucket()` (Lines 294-299)
**Before:**
```python
images = []

# --- grading filter flags from query (default: nothing selected) ---
graded_only = request.args.get('graded_only') == '1'
any_grader  = request.args.get('any_grader') == '1'
pcgs        = request.args.get('pcgs') == '1'
ngc         = request.args.get('ngc') == '1'
grading_filter_applied = graded_only and (any_grader or pcgs or ngc)

# --- packaging filter from query ---
packaging_filter = request.args.get('packaging_filter', '').strip()
```

**After:**
```python
images = []

# --- packaging filter from query ---
packaging_filter = request.args.get('packaging_filter', '').strip()
```

#### Removed Grading Filter from Listings Query (Lines 362-371)
**Before:**
```python
# Apply packaging filter to visible listings if specified
if packaging_filter:
    listings_query += ' AND l.packaging_type = ?'
    listings_params.append(packaging_filter)

if grading_filter_applied:
    listings_query += ' AND l.graded = 1'
    if not any_grader:
        services = []
        if pcgs: services.append("'PCGS'")
        if ngc:  services.append("'NGC'")
        if services:
            listings_query += f" AND l.grading_service IN ({', '.join(services)})"
        else:
            listings = []
if 'listings' not in locals():
    listings_raw = conn.execute(listings_query, listings_params).fetchall()
```

**After:**
```python
# Apply packaging filter to visible listings if specified
if packaging_filter:
    listings_query += ' AND l.packaging_type = ?'
    listings_params.append(packaging_filter)

# Execute listings query
listings_raw = conn.execute(listings_query, listings_params).fetchall()
```

#### Removed Grading Filter from render_template (Lines 654-657)
**Before:**
```python
return render_template(
    'view_bucket.html',
    bucket=bucket,
    specs=specs,
    images=images,
    listings=listings,
    availability=availability,
    graded_only=graded_only,
    any_grader=any_grader,   # <<< removed
    pcgs=pcgs,               # <<< removed
    ngc=ngc,                 # <<< removed
    packaging_filter=packaging_filter,
    random_year=random_year,
    ...
)
```

**After:**
```python
return render_template(
    'view_bucket.html',
    bucket=bucket,
    specs=specs,
    images=images,
    listings=listings,
    availability=availability,
    packaging_filter=packaging_filter,
    random_year=random_year,
    ...
)
```

#### Removed Grading Filter from `bucket_availability_json()` (Lines 677-701)
**Before:**
```python
@buy_bp.route('/bucket/<int:bucket_id>/availability_json')
def bucket_availability_json(bucket_id):
    conn = get_db_connection()

    graded_only = request.args.get('graded_only') == '1'
    any_grader  = request.args.get('any_grader') == '1'
    pcgs        = request.args.get('pcgs') == '1'
    ngc         = request.args.get('ngc') == '1'

    # Get listings with pricing fields
    query = '''
        SELECT l.*, c.metal, c.weight, c.product_type
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ? AND l.active = 1
    '''
    params = [bucket_id]

    if graded_only:
        query += ' AND l.graded = 1'
        if not any_grader:
            services = []
            if pcgs: services.append("'PCGS'")
            if ngc:  services.append("'NGC'")
            if services:
                query += f" AND l.grading_service IN ({', '.join(services)})"
            else:
                conn.close()
                return {'lowest_price': None, 'total_available': 0}

    listings = conn.execute(query, params).fetchall()
```

**After:**
```python
@buy_bp.route('/bucket/<int:bucket_id>/availability_json')
def bucket_availability_json(bucket_id):
    conn = get_db_connection()

    # Get listings with pricing fields
    query = '''
        SELECT l.*, c.metal, c.weight, c.product_type
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ? AND l.active = 1
    '''
    params = [bucket_id]

    listings = conn.execute(query, params).fetchall()
```

#### Removed Grading Filter from `auto_fill_bucket_purchase()` (Lines 714-736, 780-795)
**Before:**
```python
conn = get_db_connection()
cursor = conn.cursor()

graded_only = request.form.get('graded_only') == '1'
any_grader = request.form.get('any_grader') == '1'
pcgs = request.form.get('pcgs') == '1'
ngc = request.form.get('ngc') == '1'

# TPG (Third-Party Grading) service add-on
third_party_grading = int(request.form.get('third_party_grading', 0))

# Random Year mode and packaging filter
random_year = request.form.get('random_year') == '1'
packaging_filter = request.form.get('packaging_filter', '').strip()

# 🆕 Determine grading preference string
if any_grader:
    grading_preference = 'Any Grader'
elif pcgs:
    grading_preference = 'PCGS'
elif ngc:
    grading_preference = 'NGC'
else:
    grading_preference = None

session['grading_preference'] = grading_preference  # optional: still store for display
```

**After:**
```python
conn = get_db_connection()
cursor = conn.cursor()

# TPG (Third-Party Grading) service add-on
third_party_grading = int(request.form.get('third_party_grading', 0))

# Random Year mode and packaging filter
random_year = request.form.get('random_year') == '1'
packaging_filter = request.form.get('packaging_filter', '').strip()
```

**Also removed grading filter from listings query:**
```python
# Apply packaging filter if specified
if packaging_filter:
    listings_query += ' AND l.packaging_type = ?'
    params.append(packaging_filter)

listings_raw = cursor.execute(listings_query, params).fetchall()
```

### 4. `routes/checkout_routes.py`

#### Removed Grading Filter from `checkout()` (Lines 27-33, 82-95)
**Before:**
```python
if bucket_id:
    # User is buying directly from a bucket (not from cart)
    bucket_id = int(bucket_id)
    graded_only = request.form.get('graded_only') == '1'
    any_grader = request.form.get('any_grader') == '1'
    pcgs = request.form.get('pcgs') == '1'
    ngc = request.form.get('ngc') == '1'
    random_year = request.form.get('random_year') == '1'

    grading_filter_applied = graded_only and (any_grader or pcgs or ngc)
```

**After:**
```python
if bucket_id:
    # User is buying directly from a bucket (not from cart)
    bucket_id = int(bucket_id)
    random_year = request.form.get('random_year') == '1'
```

**Also removed grading filter from listings query:**
```python
# Get listings with pricing fields for effective price calculation
# IMPORTANT: Include ALL listings (including user's own) to detect when they're skipped
query = f'''
    SELECT l.id, l.quantity, l.price_per_coin, l.pricing_mode,
           l.spot_premium, l.floor_price, l.pricing_metal, l.seller_id,
           c.metal, c.weight, c.product_type, c.year
    FROM listings l
    JOIN categories c ON l.category_id = c.id
    WHERE {bucket_id_clause} AND l.active = 1 AND l.quantity > 0
'''

listings_raw = conn.execute(query, params).fetchall()
```

## What Remains

### ✅ Add Third-Party Grading Service Toggle
The new buyer add-on toggle is **fully preserved** and continues to work as before:
- Visible on Bucket ID page
- Adds $30/item grading service fee
- Passes `third_party_grading` parameter to checkout
- Sets `third_party_grading_requested` on cart/order items
- Completely independent from the old filter

### ✅ Other Filters
All other filters remain functional:
- Packaging filter (OGP, Capsule, Tube, etc.)
- Random Year mode toggle
- All filters work correctly with the new TPG add-on

## Testing Checklist

### ✅ Verification Steps
1. **Navigate to any Bucket ID page**
   - [ ] Confirm NO "Require 3rd Party Grading" dropdown visible
   - [ ] Confirm "Add Third-Party Grading Service" toggle IS visible
   - [ ] Confirm packaging filter still works
   - [ ] Confirm Random Year toggle still works

2. **Test Buy Flow**
   - [ ] Click "Buy Item" with TPG toggle OFF → purchase works, no grading fee
   - [ ] Click "Buy Item" with TPG toggle ON → purchase works, includes $30/item fee
   - [ ] Verify no JavaScript errors in console
   - [ ] Verify success modal displays correctly

3. **Test Add to Cart Flow**
   - [ ] Click "Add to Cart" with TPG toggle OFF → adds to cart, no grading fee
   - [ ] Click "Add to Cart" with TPG toggle ON → adds to cart, includes $30/item fee
   - [ ] Verify cart displays correctly
   - [ ] Verify no errors

4. **Test Filters Interaction**
   - [ ] Use packaging filter → shows correct filtered listings
   - [ ] Use Random Year mode → aggregates across years
   - [ ] Use TPG toggle with both filters → works correctly

## Impact Summary

### Removed
- Old "Require 3rd Party Grading" dropdown UI
- All grading filter query parameters (graded_only, any_grader, pcgs, ngc)
- All backend logic that filtered listings by grading status
- All JavaScript that managed grading filter state

### Preserved
- "Add Third-Party Grading Service" buyer add-on toggle
- All TPG add-on functionality (fee calculation, cart/order tracking)
- Packaging filter
- Random Year mode
- All other Bucket ID page features

### Result
- Cleaner, simpler UI with only one grading-related control
- No breaking changes to buyer add-on functionality
- Eliminated confusion between filter and add-on service
- All tests should pass without modifications

## Files Summary

**Modified:**
1. `templates/view_bucket.html` - Removed grading filter UI and form inputs
2. `static/js/view_bucket.js` - Removed grading filter JavaScript
3. `routes/buy_routes.py` - Removed grading filter backend logic (3 functions)
4. `routes/checkout_routes.py` - Removed grading filter from checkout

**No changes needed:**
- Cart routes (didn't use grading filter)
- Order/notification systems (use TPG add-on, not filter)
- Database schema (grading filter was query-only, not stored)
