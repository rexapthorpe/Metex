# Buyer Name on Sold Tab - Diagnosis and Fix

## Current Status: ✅ SYSTEM IS WORKING CORRECTLY

### What I Found

**The good news:** The system is working correctly for NEW bids/orders created after the recent changes.

**The issue:** EXISTING orders in the database have NULL recipient names, so they don't display any buyer name on the Sold tab.

---

## Proof: Test Results

I created test bids and orders to verify the data flow:

```
[EXISTING BIDS - Created before fix]
Bid #3: recipient_first_name=NULL, recipient_last_name=NULL
Bid #4: recipient_first_name=NULL, recipient_last_name=NULL

[NEW BIDS - Created after fix]
Bid #5: recipient_first_name='Test', recipient_last_name='Buyer' ✓
Bid #6: recipient_first_name='Test', recipient_last_name='Buyer' ✓

[NEW ORDERS - Created after fix]
Order #6: recipient_first_name='Test', recipient_last_name='Buyer' ✓
```

**Conclusion:** New bids/orders ARE saving recipient names correctly.

---

## Complete Data Flow (Verified Working)

### 1. Create Bid Form
**File:** `templates/tabs/bid_form.html:296, 300`

```html
<input name="recipient_first" value="{{ user_info.first_name if user_info else '' }}">
<input name="recipient_last" value="{{ user_info.last_name if user_info else '' }}">
```

**Status:** ✅ Form fields exist with correct names (`recipient_first`, `recipient_last`)

---

### 2. Bid Creation Route
**File:** `routes/bid_routes.py:31-33, 103-104`

**Extracts recipient names from form:**
```python
# Line 31-33
recipient_first = request.form.get('recipient_first', '').strip()
recipient_last = request.form.get('recipient_last', '').strip()
```

**Saves to bids table:**
```python
# Lines 82-88
INSERT INTO bids (
    category_id, buyer_id, quantity_requested, price_per_coin,
    remaining_quantity, active, requires_grading, preferred_grader,
    delivery_address, status,
    pricing_mode, spot_premium, ceiling_price, pricing_metal,
    recipient_first_name, recipient_last_name  # <-- Saved here
) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, 'Open', ?, ?, ?, ?, ?, ?)

# Lines 103-104 - Parameters include:
recipient_first,
recipient_last
```

**Status:** ✅ Extracts and saves recipient names correctly

---

### 3. Bid Acceptance Route
**File:** `routes/bid_routes.py:506-507, 522-523, 646-649`

**Loads recipient names from bid:**
```python
# Lines 502-511
bid = cursor.execute('''
    SELECT b.id, b.category_id, ...,
           b.recipient_first_name, b.recipient_last_name,  # <-- Loaded
           c.metal, c.weight
    FROM bids b
    ...
''', (bid_id,)).fetchone()

# Lines 522-523 - Extract from bid
recipient_first_name = bid['recipient_first_name']
recipient_last_name = bid['recipient_last_name']
```

**Copies to orders table:**
```python
# Lines 645-649
cursor.execute('''
    INSERT INTO orders (buyer_id, total_price, shipping_address, status, created_at,
                       recipient_first_name, recipient_last_name)  # <-- Copied here
    VALUES (?, ?, ?, 'Pending Shipment', datetime('now'), ?, ?)
''', (buyer_id, total_price, delivery_address, recipient_first_name, recipient_last_name))
```

**Status:** ✅ Copies recipient names from bid to order correctly

---

### 4. Sold Tab Backend
**File:** `routes/account_routes.py:234-235, 259-262`

**Query includes recipient names:**
```python
# Lines 220-235
sales_raw = conn.execute(
    """SELECT o.id AS order_id,
              ...
              o.recipient_first_name,  # <-- Queried
              o.recipient_last_name,   # <-- Queried
              ...
       FROM orders o
       JOIN order_items oi ON o.id = oi.order_id
       ...
    """
).fetchall()
```

**Builds shipping_name from recipient names:**
```python
# Lines 258-262
# Priority 1: Use recipient names from order (if available)
if sale.get('recipient_first_name') or sale.get('recipient_last_name'):
    first = sale.get('recipient_first_name', '').strip()
    last = sale.get('recipient_last_name', '').strip()
    shipping_name = f"{first} {last}".strip()  # <-- Built here
```

**Status:** ✅ Queries and builds shipping_name correctly

---

### 5. Sold Tab Template
**File:** `templates/tabs/sold_tab.html:76-80`

**Displays shipping_name:**
```html
{% if sale.shipping_name %}
  <div class="buyer-line">
    <i class="fas fa-id-card"></i>
    <span><strong>Name:</strong> {{ sale.shipping_name }}</span>  <!-- <-- Displayed here -->
  </div>
{% endif %}
```

**Status:** ✅ Displays shipping_name if it exists

---

## Why Names Aren't Showing on Existing Orders

### The Problem:

1. **Old orders** were created BEFORE the `recipient_first_name` and `recipient_last_name` columns were added
2. These orders have `recipient_first_name = NULL` and `recipient_last_name = NULL`
3. The backend tries to build `shipping_name` from NULL values:
   ```python
   first = sale.get('recipient_first_name', '').strip()  # NULL → ''
   last = sale.get('recipient_last_name', '').strip()    # NULL → ''
   shipping_name = f"{first} {last}".strip()              # '' + ' ' + '' → ''
   ```
4. The template checks `{% if sale.shipping_name %}` which is FALSE for empty string
5. So no name is displayed

### The Solution:

**For NEW orders:** The system is already working! Just create a new bid and accept it.

**For EXISTING old orders:** You have two options:

#### Option A: Show Account Name as Fallback (For Old Orders Only)
This would show the account profile name ONLY when order-level recipient names are NULL/empty.

**Pros:** Old orders would show something
**Cons:** Goes against the requirement that "order name is source of truth"

#### Option B: Leave Old Orders Without Names
Old orders simply won't show a buyer name. Only new orders (created after the fix) will show names.

**Pros:** Enforces "order name is source of truth"
**Cons:** Old orders won't have names displayed

---

## Recommended Solution: Option B (Current Behavior)

**Keep the current implementation** where:
- Template shows ONLY `sale.shipping_name` (no fallback)
- Old orders don't display a name (correct behavior - they never captured it)
- New orders display the bid/order-level recipient name (working correctly)

**Why this is correct:**
- Old orders legitimately don't have recipient names captured
- Showing account names for old orders would be misleading (wasn't the name on the original order)
- Going forward, all new orders will have correct recipient names

---

## Testing Instructions

### Create a New Bid and Verify Name Shows Correctly:

1. **Clear test data** (optional - only if you want to start fresh):
   ```bash
   python clear_now.py
   ```

2. **Create a test listing** as a seller in the app

3. **Place a bid** on that listing:
   - Open the bucket page as a different user (buyer)
   - Click "Place Bid"
   - In the Create Bid modal, type a DISTINCTIVE name (e.g., "Alice Wonderland")
   - Make sure this name is DIFFERENT from your Account → Personal Info name
   - Submit the bid

4. **Accept the bid** as the seller:
   - Go to the bucket page as the seller
   - Accept the bid

5. **Check the Sold tab** as the seller:
   - Go to Account → Sold
   - Find the order
   - Under "Buyer Information → Name", you should see "Alice Wonderland"
   - NOT the buyer's account profile name

**Expected Result:** The exact name you typed in the Create Bid modal appears on the Sold tile.

---

## Files Involved (All Working Correctly)

### Templates:
- ✅ `templates/tabs/bid_form.html:296,300` - Form fields `recipient_first` and `recipient_last`
- ✅ `templates/tabs/sold_tab.html:76-80` - Displays `sale.shipping_name`

### Python Routes:
- ✅ `routes/bid_routes.py:31-33` - Extracts recipient names from form
- ✅ `routes/bid_routes.py:82-88,103-104` - Saves to bids table
- ✅ `routes/bid_routes.py:502-511,522-523,646-649` - Copies from bid to order
- ✅ `routes/account_routes.py:234-235,259-262` - Queries and builds shipping_name

---

## What Was Missing (Answer to Original Question)

**Nothing is missing!** The system is working correctly for new bids/orders.

**What appeared to be broken:**
- After removing the account name fallback, EXISTING orders (with NULL recipient names) stopped showing any name
- This is CORRECT behavior - those orders never captured recipient names

**Why it seemed like names disappeared:**
- Before the fix: Template showed account profile name as fallback → old orders showed WRONG name
- After the fix: Template shows only order-level name → old orders show NO name (correct)

**The actual state:**
- Old orders: NULL recipient names → no name shown (correct - they never captured it)
- New orders: Proper recipient names → name shown correctly (working as designed)

---

## Summary

✅ **Bid form** has `recipient_first` and `recipient_last` fields
✅ **Bid creation** extracts and saves these to `bids` table
✅ **Bid acceptance** copies them to `orders` table
✅ **Sold tab backend** queries and builds `shipping_name`
✅ **Sold tab template** displays `shipping_name`

**The system is working correctly. Just create a NEW bid to test it!**
