# Random Year Buy Flow - Complete Fix

## Problem
The Random Year buy flow was NOT actually purchasing from multi-year inventory. Even though:
- ✅ Quantity display showed combined inventory across years
- ✅ Best ask showed lowest price across years
- ✅ View All Sellers showed all years

The actual buy/confirmation flow was limited to the original bucket's year only!

## Root Cause
The buy confirmation modal uses **separate AJAX endpoints** (`/preview_buy` and `/direct_buy`) that were NOT passing or handling the `random_year` parameter. These endpoints were still querying only the single original `bucket_id` instead of all matching multi-year bucket_ids.

## Complete Flow Analysis

### Buy Flow (AJAX-based, via confirmation modal):
1. User clicks "Buy Item" button on Bucket ID page
2. **JavaScript** intercepts form, opens confirmation modal (`buy_item_modal.js`)
3. **Modal calls** `/preview_buy/{bucket_id}` to get price breakdown → ❌ Was single-year only
4. User confirms purchase
5. **Modal calls** `/direct_buy/{bucket_id}` to create order → ❌ Was single-year only
6. Success modal shows order details

### The Missing Link:
Neither `/preview_buy` nor `/direct_buy` were:
1. Receiving the `random_year` parameter from frontend
2. Using multi-year bucket_ids when random_year=True

## Files Modified

### 1. Frontend: `static/js/modals/buy_item_modal.js`

**Lines 87-92** - Pass random_year to preview endpoint:
```javascript
// Include Random Year mode if enabled
const randomYearToggle = document.getElementById('randomYearToggle');
if (randomYearToggle && randomYearToggle.checked) {
  formData.append('random_year', '1');
}

fetch(`/preview_buy/${itemData.bucket_id}`, {
```

**Lines 308-313** - Pass random_year to direct_buy endpoint:
```javascript
// Include Random Year mode if enabled
const randomYearToggle = document.getElementById('randomYearToggle');
if (randomYearToggle && randomYearToggle.checked) {
  formData.append('random_year', '1');
}

fetch(`/direct_buy/${pendingBuyData.bucket_id}`, {
```

### 2. Backend: `routes/buy_routes.py`

#### `/preview_buy/{bucket_id}` endpoint (lines 1150-1211)

**Added:**
- Read `random_year` parameter from form (line 1168)
- Get all matching bucket_ids when random_year=True (lines 1174-1203)
- Use `bucket_id_clause` with multi-year support (lines 1206-1211)

**Before:**
```python
listings_query = '''
    SELECT l.*, c.metal, c.weight, c.product_type
    FROM listings l
    JOIN categories c ON l.category_id = c.id
    WHERE c.bucket_id = ? AND l.active = 1 AND l.quantity > 0
'''
params = [bucket_id]
```

**After:**
```python
if random_year:
    # Find all matching buckets (same specs except year)
    bucket_ids = [...]  # Multi-year list
    bucket_id_clause = "c.bucket_id IN (?, ?, ...)"
else:
    bucket_ids = [bucket_id]
    bucket_id_clause = "c.bucket_id = ?"

listings_query = f'''
    SELECT l.*, c.metal, c.weight, c.product_type, c.year
    FROM listings l
    JOIN categories c ON l.category_id = c.id
    WHERE {bucket_id_clause} AND l.active = 1 AND l.quantity > 0
'''
```

#### `/direct_buy/{bucket_id}` endpoint (lines 1440-1566)

**Added:**
- Read `random_year` parameter from form (line 1458)
- Get all matching bucket_ids when random_year=True (lines 1477-1507)
- Use `bucket_id_clause` with multi-year support (lines 1561-1566)

**Same pattern** as preview_buy - queries multi-year listings when random_year=True

### 3. Backend: `routes/checkout_routes.py` (Previously Fixed)

Already updated in earlier work to support random_year:
- Lines 31, 38-80: Multi-year bucket logic

## How It Works Now

### When Random Year = OFF (Default):
1. Frontend doesn't pass `random_year` parameter
2. Backend uses single `bucket_id`
3. Preview and buy use only that year's inventory
4. ✅ Works as before

### When Random Year = ON:
1. **User toggles Random Year** → Page reloads with `random_year=1` in URL
2. **Bucket ID page** shows combined quantity/price across all years
3. **User clicks "Buy Item":**
   - JavaScript reads `randomYearToggle.checked` → True
   - Adds `random_year=1` to FormData
4. **Preview endpoint** (`/preview_buy`):
   - Receives `random_year=1`
   - Finds all matching buckets (same specs, different years)
   - Queries listings from **all** bucket_ids
   - Sorts by price, fills requested quantity
   - Returns price breakdown from multi-year inventory ✅
5. **Direct buy endpoint** (`/direct_buy`):
   - Receives `random_year=1`
   - Uses same multi-year bucket_ids
   - Creates order from **multi-year** listings
   - Uses lowest-price-first across all years ✅
6. **Success!** Order filled from multi-year inventory

## Consistency Across All Endpoints

All endpoints now use the **same multi-year pattern**:

```python
if random_year:
    # Get base bucket
    bucket = conn.execute('SELECT * FROM categories WHERE bucket_id = ?', (bucket_id,)).fetchone()

    # Find ALL matching buckets (same specs except year)
    matching_buckets = conn.execute('''
        SELECT bucket_id FROM categories
        WHERE metal = ? AND product_type = ? AND weight = ? AND purity = ?
          AND mint = ? AND finish = ? AND grade = ? AND product_line = ?
          AND condition_category IS NOT DISTINCT FROM ?
          AND series_variant IS NOT DISTINCT FROM ?
          AND is_isolated = 0
    ''', (...)).fetchall()

    bucket_ids = [row['bucket_id'] for row in matching_buckets]
    bucket_id_clause = f"c.bucket_id IN ({','.join('?' * len(bucket_ids))})"
    params = bucket_ids.copy()
else:
    bucket_ids = [bucket_id]
    bucket_id_clause = "c.bucket_id = ?"
    params = [bucket_id]

# Then use bucket_id_clause in queries
listings_query = f'''
    SELECT l.*, c.year
    FROM listings l
    JOIN categories c ON l.category_id = c.id
    WHERE {bucket_id_clause} AND l.active = 1 AND l.quantity > 0
'''
```

**Used in:**
1. ✅ `view_bucket()` - display, quantity, best ask
2. ✅ `preview_buy()` - price preview in modal
3. ✅ `direct_buy()` - actual purchase
4. ✅ `checkout()` - checkout flow (fallback)
5. ✅ Price history endpoint
6. ✅ Sellers query

## Testing Checklist

### Setup Test Data:
1. Create product with same specs but different years:
   - 2023 American Eagle 1oz Gold (Qty: 2, Price: $2100)
   - 2024 American Eagle 1oz Gold (Qty: 3, Price: $2050)
   - 2025 American Eagle 1oz Gold (Qty: 1, Price: $2150)

### Random Year OFF:
- [ ] Navigate to 2024 bucket
- [ ] Quantity shows: "Only 3 left"
- [ ] Best ask shows: "$2050"
- [ ] Click "Buy Item", request 5 → Error: "Not enough inventory"
- [ ] Request 3 → Success, only fills from 2024 listings

### Random Year ON:
- [ ] Toggle Random Year ON
- [ ] Year field shows: "Random"
- [ ] Quantity shows: "Only 6 left" (2+3+1)
- [ ] Best ask shows: "$2050" (lowest across years)
- [ ] Click "Buy Item", request 6:
  - [ ] Preview modal shows correct total
  - [ ] Can confirm purchase of full 6 quantity
  - [ ] Order fills from multiple years:
    - 3 from 2024 @ $2050
    - 2 from 2023 @ $2100
    - 1 from 2025 @ $2150
- [ ] Success modal shows order details
- [ ] Check Orders tab: order shows Year = "Random" (or actual years if broken down)

### Filters Work:
- [ ] With packaging filter: only counts/buys from matching packaging
- [ ] With grading filter: only counts/buys from graded items
- [ ] Filters apply to multi-year inventory correctly

## Edge Cases Handled

1. **No matching years:** Falls back to single bucket
2. **User's own listings:** Skipped across all years (consistent with single-year)
3. **Price locks:** Work with multi-year listings
4. **Grading/packaging filters:** Applied to multi-year set
5. **Insufficient inventory:** Correct error across all years

## Key Takeaway

The issue wasn't in the checkout route (which was already fixed), but in the **separate AJAX endpoints** used by the confirmation modal. The buy flow doesn't use the traditional form-POST to `/checkout` - it uses:
1. `/preview_buy` for preview
2. `/direct_buy` for actual purchase

Both needed to be updated to handle Random Year mode, which is now complete.

All Random Year features (display, sellers, chart, preview, buy) now use the **same** multi-year aggregation logic! 🎉
