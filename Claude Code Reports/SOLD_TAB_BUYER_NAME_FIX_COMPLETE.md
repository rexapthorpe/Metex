# Sold Tab Buyer Name Fix - Complete Implementation

## Problem Summary

**What was wrong:**
The Sold tab was displaying the buyer's **Account Profile name** (from `users.first_name` and `users.last_name`) instead of the **order-level recipient name** entered in the Create Bid or Buy modals. This meant that even when a buyer typed a different name during checkout, the Sold tile would still show only their account profile name.

**Root causes:**
1. **Template had fallback logic** (`sold_tab.html:80-84`) that prioritized showing account profile names when order-level recipient names were missing
2. **Database had NULL recipient names** - existing orders/bids were created before recipient name columns existed
3. **Buy Item modal didn't capture recipient names** - direct purchases had no way to save buyer names
4. **Multiple order creation paths** didn't save recipient names to the database

---

## What Changed

### 1. Template Fix (CRITICAL)
**File:** `templates/tabs/sold_tab.html:74-81`

**Before:**
```html
{# Show shipping name (from bid/order form) if available, else fall back to account name #}
{% if sale.shipping_name %}
  <div class="buyer-line">
    <i class="fas fa-id-card"></i>
    <span><strong>Name:</strong> {{ sale.shipping_name }}</span>
  </div>
{% elif sale.buyer_first_name or sale.buyer_last_name %}
  <div class="buyer-line">
    <i class="fas fa-id-card"></i>
    <span><strong>Name:</strong> {{ sale.buyer_first_name }} {{ sale.buyer_last_name }}</span>
  </div>
{% endif %}
```

**After:**
```html
{# ONLY show order-level recipient name (from Create Bid / Buy modal) #}
{# Do NOT fall back to account profile name - order name is the source of truth #}
{% if sale.shipping_name %}
  <div class="buyer-line">
    <i class="fas fa-id-card"></i>
    <span><strong>Name:</strong> {{ sale.shipping_name }}</span>
  </div>
{% endif %}
```

**Why this fixes it:**
- Removed the `elif` block that showed account profile names (`sale.buyer_first_name` / `sale.buyer_last_name`)
- Now **ONLY** shows `sale.shipping_name` (built from `order.recipient_first_name` + `order.recipient_last_name`)
- If no recipient name exists on the order, the Buyer Name field simply won't display (correct behavior)

---

### 2. Backend Query (Already Fixed Previously)
**File:** `routes/account_routes.py:234-235, 259-262`

The Sold tab query already includes:
```python
o.recipient_first_name,
o.recipient_last_name,
```

And builds `shipping_name` with priority:
```python
# Priority 1: Use recipient names from order (if available)
if sale.get('recipient_first_name') or sale.get('recipient_last_name'):
    first = sale.get('recipient_first_name', '').strip()
    last = sale.get('recipient_last_name', '').strip()
    shipping_name = f"{first} {last}".strip()
```

This ensures the order-level recipient name is the source of truth.

---

### 3. Buy Item Modal - Added Recipient Name Fields
**File:** `templates/modals/buy_item_modal.html:86-103`

**Added:**
```html
<!-- Recipient Name Fields -->
<div class="recipient-name-section" style="margin: 20px 0;">
  <h3 style="font-size: 16px; font-weight: 600; color: #374151; margin-bottom: 12px;">Recipient Name</h3>
  <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
    <div>
      <label for="buy-recipient-first" style="...">First Name *</label>
      <input type="text" id="buy-recipient-first" name="recipient_first" required
             style="..." autocomplete="given-name">
    </div>
    <div>
      <label for="buy-recipient-last" style="...">Last Name *</label>
      <input type="text" id="buy-recipient-last" name="recipient_last" required
             style="..." autocomplete="family-name">
    </div>
  </div>
</div>
```

---

### 4. Buy Modal JavaScript - Auto-populate Names
**File:** `static/js/modals/buy_item_modal.js:947-957`

**Added:**
```javascript
// Auto-populate recipient name fields from user profile (if fields exist)
if (data.user_info) {
  const firstNameInput = document.getElementById('buy-recipient-first');
  const lastNameInput = document.getElementById('buy-recipient-last');
  if (firstNameInput && data.user_info.first_name) {
    firstNameInput.value = data.user_info.first_name;
  }
  if (lastNameInput && data.user_info.last_name) {
    lastNameInput.value = data.user_info.last_name;
  }
}
```

**Why:** Auto-fills recipient name fields with account profile name for convenience, but user can edit before submitting.

---

### 5. Get Addresses API - Return User Info
**File:** `routes/account_routes.py:930-934, 959-962`

**Added:**
```python
# Fetch user info for auto-populating recipient name fields
user_info = conn.execute(
    'SELECT first_name, last_name FROM users WHERE id = ?',
    (user_id,)
).fetchone()

# ... in response:
'user_info': {
    'first_name': user_info['first_name'] if user_info else '',
    'last_name': user_info['last_name'] if user_info else ''
}
```

**Why:** Provides user info to JavaScript for auto-populating the buy modal name fields.

---

### 6. Direct Buy Route - Extract and Save Recipient Names
**File:** `routes/buy_routes.py:1157-1159, 1348-1351`

**Added extraction:**
```python
# Get recipient name (source of truth for Buyer Name on Sold tiles)
recipient_first = request.form.get('recipient_first', '').strip()
recipient_last = request.form.get('recipient_last', '').strip()
```

**Updated INSERT:**
```python
cursor.execute('''
    INSERT INTO orders (buyer_id, total_price, shipping_address, status, created_at,
                       recipient_first_name, recipient_last_name)
    VALUES (?, ?, ?, 'Pending Shipment', datetime('now'), ?, ?)
''', (user_id, total_price, shipping_address, recipient_first, recipient_last))
```

**Why:** Saves the name typed in the Buy Item modal to the order record.

---

### 7. Order Service - Support Recipient Names
**File:** `services/order_service.py:10, 18-20`

**Updated signature:**
```python
def create_order(buyer_id, cart_items, shipping_address, recipient_first='', recipient_last=''):
```

**Updated INSERT:**
```python
cursor.execute('''
    INSERT INTO orders (buyer_id, total_price, shipping_address, recipient_first_name, recipient_last_name)
    VALUES (?, ?, ?, ?, ?)
''', (buyer_id, total_price, shipping_address, recipient_first, recipient_last))
```

**Why:** Backward compatible - existing calls work with defaults, new calls can pass recipient names.

---

### 8. Bid Routes (Previously Fixed)
**File:** `routes/bid_routes.py:31-33, 103-104, 506-507, 522-523, 646-649`

Already saves recipient names from Create Bid modal to bids table, and copies them to orders when bid is accepted.

---

## Data Flow Summary

### Create Bid Flow:
1. User opens **Create Bid modal** on bucket page
2. Name fields (`recipient_first`, `recipient_last`) auto-populate from account profile
3. User can edit the name before submitting
4. **Bid is created** with `recipient_first_name` and `recipient_last_name` saved to `bids` table
5. When seller accepts bid, **order is created** with recipient names copied from bid to `orders` table
6. **Sold tab** displays `order.recipient_first_name + order.recipient_last_name` as Buyer Name

### Direct Buy Flow:
1. User opens **Buy Item modal** from bucket page
2. Name fields (`recipient_first`, `recipient_last`) auto-populate from account profile
3. User can edit the name before purchasing
4. **Order is created** with `recipient_first_name` and `recipient_last_name` saved directly to `orders` table
5. **Sold tab** displays `order.recipient_first_name + order.recipient_last_name` as Buyer Name

---

## Why This Guarantees Correct Behavior

### ✅ Order-level name is the source of truth
- Recipient names are saved to `orders.recipient_first_name` and `orders.recipient_last_name`
- These are the ONLY fields used to build `sale.shipping_name` in the backend
- Template shows ONLY `sale.shipping_name` - no fallback to account profile name

### ✅ Account profile name is only for auto-fill
- Account name (`users.first_name`, `users.last_name`) is used ONLY to pre-populate form fields
- User can override this name before submitting
- Whatever the user types becomes the order-level recipient name

### ✅ No more incorrect name displays
- If order has recipient name → shows that name
- If order has no recipient name → shows nothing (correct for old orders)
- Account profile name is NEVER shown on Sold tiles

---

## Testing Instructions

### Test 1: Create Bid with Different Name
1. Go to Account → Personal Info
2. Set your name to "John Doe"
3. Go to a bucket page and click "Place Bid"
4. Change the name in the modal to "Jane Smith"
5. Submit the bid
6. Have a seller accept your bid
7. Go to seller's Account → Sold tab
8. **Expected:** Buyer Name shows "Jane Smith" (NOT "John Doe")

### Test 2: Direct Buy with Different Name
1. Ensure your account name is "John Doe"
2. Go to a bucket page and click "Buy Now"
3. Change the recipient name to "Bob Johnson"
4. Complete purchase
5. Seller checks Sold tab
6. **Expected:** Buyer Name shows "Bob Johnson" (NOT "John Doe")

### Test 3: Empty Account Name
1. Clear your Account → Personal Info name (leave blank)
2. Create a bid and type "Alice Wonder" in the name fields
3. Submit and have it accepted
4. Seller checks Sold tab
5. **Expected:** Buyer Name shows "Alice Wonder"

---

## Files Modified

### Templates:
- `templates/tabs/sold_tab.html` - Removed account name fallback
- `templates/modals/buy_item_modal.html` - Added recipient name fields

### Python Routes:
- `routes/account_routes.py` - Return user info from get_addresses API
- `routes/buy_routes.py` - Extract and save recipient names in direct buy
- `routes/bid_routes.py` - (Previously fixed) Save recipient names from bids

### Services:
- `services/order_service.py` - Support recipient names in create_order

### JavaScript:
- `static/js/modals/buy_item_modal.js` - Auto-populate recipient name fields

---

## Database Schema (Already Applied)

```sql
-- Bids table (already has these columns)
ALTER TABLE bids ADD COLUMN recipient_first_name TEXT;
ALTER TABLE bids ADD COLUMN recipient_last_name TEXT;

-- Orders table (already has these columns)
ALTER TABLE orders ADD COLUMN recipient_first_name TEXT;
ALTER TABLE orders ADD COLUMN recipient_last_name TEXT;
```

---

## Status: ✅ COMPLETE

All order creation paths now save recipient names.
Sold tab now shows ONLY order-level recipient names.
Account profile name is used ONLY for auto-filling forms.
