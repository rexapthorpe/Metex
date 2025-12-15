# Random Year Display Fixes - Complete Implementation

## Summary
Fixed the final two Random Year mode display issues:
1. Buy congratulations modal now shows "Random" for year
2. Orders tab tiles now show "Random" for multi-year orders

## Problem Description

### Issue 1: Buy Congratulations Modal
**Problem:** After completing a Random Year purchase, the success modal showed the original bucket's year instead of "Random".

**Expected:** Success modal should display Year = "Random" when the purchase was made in Random Year mode.

### Issue 2: Orders Tab Tiles
**Problem:** Orders tab tiles for random-year purchases were showing the minimum year from the order items instead of "Random".

**Expected:** When an order contains items from multiple years (random-year purchase), the tile should display Year = "Random".

## Files Modified

### 1. `routes/buy_routes.py` (Lines 1672-1674)

**Change:** Update `bucket_dict` year to "Random" when random_year mode is active

```python
# Get category/bucket info for notifications
bucket_row = cursor.execute('SELECT * FROM categories WHERE bucket_id = ? LIMIT 1', (bucket_id,)).fetchone()
bucket_dict = dict(bucket_row) if bucket_row else {}

# Update year display for Random Year purchases
if random_year:
    bucket_dict['year'] = 'Random'
```

**Impact:** The `bucket_dict` is returned in the `/direct_buy` response and used by the buy success modal to populate item specifications. Setting year to "Random" ensures the modal displays correctly.

**Data Flow:**
1. User completes Random Year purchase
2. `/direct_buy` endpoint processes order
3. Backend sets `bucket_dict['year'] = 'Random'`
4. Response JSON includes bucket with year="Random"
5. `buy_item_modal.js` calls `openBuyItemSuccessModal(orderData)`
6. Modal displays specs from `orderData.bucket.year` → shows "Random" ✓

### 2. `routes/account_routes.py` (Lines 148, 190, 133-135)

**Changes:**

#### A. Added year_count to pending orders query (Line 148)
```sql
SELECT
  ...
  MIN(c.year) AS year,
  COUNT(DISTINCT c.year) AS year_count,  -- NEW
  ...
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
JOIN listings l ON oi.listing_id = l.id
JOIN categories c ON l.category_id = c.id
WHERE o.buyer_id = ?
  AND o.status IN ('Pending','Pending Shipment','Awaiting Shipment','Awaiting Delivery')
GROUP BY o.id, o.status, o.created_at, o.delivery_address, o.shipping_address
```

#### B. Added year_count to completed orders query (Line 190)
```sql
-- Same pattern as pending orders
COUNT(DISTINCT c.year) AS year_count
```

#### C. Updated attach_sellers helper function (Lines 133-135)
```python
def attach_sellers(order_rows):
    out = []
    for row in order_rows:
        order = dict(row)
        seller_rows = conn.execute(
            """SELECT DISTINCT u.username
               FROM order_items oi
               JOIN listings l  ON oi.listing_id = l.id
               JOIN users u     ON l.seller_id = u.id
              WHERE oi.order_id = ?
            """, (order['id'],)
        ).fetchall()
        order['sellers'] = [r['username'] for r in seller_rows]

        # Set year to "Random" if order has items from multiple years
        if order.get('year_count', 1) > 1:
            order['year'] = 'Random'

        out.append(order)
    return out
```

**Impact:**
- SQL queries now count distinct years per order
- Python code checks if `year_count > 1` and sets year to "Random"
- Orders tab tiles display "Random" for multi-year orders ✓

## How It Works

### Single-Year Orders (Normal Behavior)
1. User purchases from a specific year bucket (Random Year OFF)
2. Backend creates order with items from that year only
3. SQL: `MIN(c.year) = actual_year`, `COUNT(DISTINCT c.year) = 1`
4. Python: `year_count = 1`, so year remains unchanged
5. Orders tab tile shows actual year (e.g., "2024")

### Multi-Year Orders (Random Year Mode)
1. User enables Random Year toggle
2. User purchases from aggregated multi-year inventory
3. Backend creates order with items from multiple years
4. SQL: `MIN(c.year) = lowest_year`, `COUNT(DISTINCT c.year) > 1`
5. Python: `year_count > 1`, so `order['year'] = 'Random'`
6. Orders tab tile shows "Random"

### Order Structure
Important note: Orders are created **per seller**, not per year. This is correct marketplace behavior:
- If Random Year purchase draws from Seller A (2023 & 2024 items): **1 order** showing "Random"
- If Random Year purchase draws from Seller A (2023) and Seller B (2024): **2 orders**, each showing their respective year

This is expected because each seller ships independently.

## Testing Checklist

### Setup Test Data
Create a product with same specs across multiple years:
- 2023 American Eagle 1oz Gold (Seller: Alice, Qty: 2, Price: $2100)
- 2024 American Eagle 1oz Gold (Seller: Alice, Qty: 3, Price: $2050)
- 2025 American Eagle 1oz Gold (Seller: Bob, Qty: 1, Price: $2150)

### Test 1: Random Year Purchase - Single Seller
- [ ] Navigate to 2024 American Eagle bucket
- [ ] Toggle Random Year ON
- [ ] Quantity shows "Only 5 left" (2+3 from Alice)
- [ ] Buy 5 items
- [ ] Success modal shows Year = "Random" ✓
- [ ] Navigate to Orders tab
- [ ] See 1 tile for the order
- [ ] Tile shows Year = "Random" ✓
- [ ] Click "Items" button
- [ ] Modal shows breakdown by price (items grouped by price_each)
- [ ] Each price group shows actual year of items

### Test 2: Random Year Purchase - Multiple Sellers
- [ ] Same setup, but buy 6 items (draws from Alice and Bob)
- [ ] Success modal shows Year = "Random" ✓
- [ ] Navigate to Orders tab
- [ ] See 2 tiles (one for Alice's items, one for Bob's)
- [ ] Alice's tile: Shows Year = "Random" (has 2023 & 2024 items) ✓
- [ ] Bob's tile: Shows Year = "2025" (only has 2025 items)

### Test 3: Normal Purchase (Random Year OFF)
- [ ] Navigate to 2024 American Eagle bucket
- [ ] Ensure Random Year toggle is OFF
- [ ] Buy 3 items
- [ ] Success modal shows Year = "2024"
- [ ] Orders tab tile shows Year = "2024"
- [ ] No "Random" display anywhere

## Edge Cases Handled

1. **year_count is None or missing:** `order.get('year_count', 1)` defaults to 1, so year stays as-is
2. **Single-year orders:** `year_count = 1`, condition fails, year unchanged
3. **Multi-year, multi-seller:** Each order evaluated independently
4. **Order Items modal:** Still shows individual item years (correct - shows detailed breakdown)

## Key Takeaways

### Buy Success Modal
- Uses `bucket_dict['year']` from `/direct_buy` response
- Backend sets this to "Random" when `random_year=True`
- No frontend changes needed (modal already uses bucket.year)

### Orders Tab Tiles
- SQL counts distinct years per order
- Python checks `year_count > 1` and overrides year to "Random"
- Works for both pending and completed orders
- Handles single-seller and multi-seller scenarios correctly

### Data Integrity
- Orders table doesn't store a "year" field directly
- Year is derived from associated listings via categories
- "Random" is purely a display label
- Detailed breakdowns (Order Items modal) still show actual years
- No data loss or ambiguity

## Files Changed Summary

1. **routes/buy_routes.py** - Lines 1672-1674
   - Set `bucket_dict['year'] = 'Random'` for buy success modal

2. **routes/account_routes.py** - Lines 148, 190, 133-135
   - Added `COUNT(DISTINCT c.year)` to orders queries
   - Updated `attach_sellers()` to set year="Random" when year_count > 1

All Random Year features now complete and consistent! 🎉
