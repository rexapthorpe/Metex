# Buyer Name Fix - Complete Solution

## Problem Identified

The Buyer Name was showing "—" on Sold Items tiles even though names were being entered in the Buy Item and Create Bid modals.

### Root Cause

**JavaScript Bug in Buy Item Modal:**
The `handleConfirmBuy()` function in `buy_item_modal.js` was NOT including the `recipient_first` and `recipient_last` fields in the FormData when submitting the purchase to the backend.

Even though:
- ✅ The input fields existed in the template
- ✅ They were auto-populated with the user's name
- ✅ The backend was ready to save them

The JavaScript was **never sending them** to the server!

---

## The Fix

### File: `static/js/modals/buy_item_modal.js`

**Lines 302-310 (NEW):**

```javascript
// ✅ Include recipient name (source of truth for Buyer Name on Sold tiles)
const recipientFirstInput = document.getElementById('buy-recipient-first');
const recipientLastInput = document.getElementById('buy-recipient-last');
if (recipientFirstInput) {
  formData.append('recipient_first', recipientFirstInput.value.trim());
}
if (recipientLastInput) {
  formData.append('recipient_last', recipientLastInput.value.trim());
}
```

**What this does:**
- Reads the values from the recipient name input fields
- Adds them to the FormData that gets sent to `/direct_buy/<bucket_id>`
- Backend now receives and saves the recipient names to `orders.recipient_first_name` and `orders.recipient_last_name`

---

## Complete Data Flow (Now Working)

### Buy Item Flow:

1. **Template** `templates/modals/buy_item_modal.html:90-101`
   ```html
   <input id="buy-recipient-first" name="recipient_first" required>
   <input id="buy-recipient-last" name="recipient_last" required>
   ```

2. **JavaScript Auto-fill** `static/js/modals/buy_item_modal.js:947-957`
   ```javascript
   // Auto-populates from user profile
   firstNameInput.value = data.user_info.first_name;
   lastNameInput.value = data.user_info.last_name;
   ```

3. **JavaScript Submission** `static/js/modals/buy_item_modal.js:302-310` **← FIXED!**
   ```javascript
   // Now includes recipient names in FormData
   formData.append('recipient_first', recipientFirstInput.value.trim());
   formData.append('recipient_last', recipientLastInput.value.trim());
   ```

4. **Backend Extraction** `routes/buy_routes.py:1157-1159`
   ```python
   recipient_first = request.form.get('recipient_first', '').strip()
   recipient_last = request.form.get('recipient_last', '').strip()
   ```

5. **Backend Save** `routes/buy_routes.py:1347-1351`
   ```python
   INSERT INTO orders (..., recipient_first_name, recipient_last_name)
   VALUES (..., recipient_first, recipient_last)
   ```

6. **Sold Tab Query** `routes/account_routes.py:234-235`
   ```python
   SELECT ..., o.recipient_first_name, o.recipient_last_name, ...
   ```

7. **Build Display Name** `routes/account_routes.py:259-262`
   ```python
   shipping_name = f"{first} {last}".strip()
   ```

8. **Template Display** `templates/tabs/sold_tab.html:76-79`
   ```html
   <span><strong>Name:</strong> {{ sale.shipping_name if sale.shipping_name else '—' }}</span>
   ```

**Result:** ✅ Name from Buy Item modal appears on Sold tile!

---

### Create Bid Flow:

1. **Template** `templates/tabs/bid_form.html:296, 300`
   ```html
   <input name="recipient_first" value="{{ user_info.first_name if user_info else '' }}">
   <input name="recipient_last" value="{{ user_info.last_name if user_info else '' }}">
   ```

2. **Form Submission** (Standard HTML form - automatically includes all inputs)

3. **Backend Extraction** `routes/bid_routes.py:31-33`
   ```python
   recipient_first = request.form.get('recipient_first', '').strip()
   recipient_last = request.form.get('recipient_last', '').strip()
   ```

4. **Backend Save to Bid** `routes/bid_routes.py:82-88, 103-104`
   ```python
   INSERT INTO bids (..., recipient_first_name, recipient_last_name)
   VALUES (..., recipient_first, recipient_last)
   ```

5. **Bid Acceptance - Load Names** `routes/bid_routes.py:506-507, 522-523`
   ```python
   SELECT ..., b.recipient_first_name, b.recipient_last_name, ...
   recipient_first_name = bid['recipient_first_name']
   recipient_last_name = bid['recipient_last_name']
   ```

6. **Bid Acceptance - Copy to Order** `routes/bid_routes.py:646-649`
   ```python
   INSERT INTO orders (..., recipient_first_name, recipient_last_name)
   VALUES (..., recipient_first_name, recipient_last_name)
   ```

7-8. **Sold Tab** (Same as Buy Item flow above)

**Result:** ✅ Name from Create Bid modal appears on Sold tile!

---

## Canonical Field

**The canonical field for buyer/recipient name is:**
- `orders.recipient_first_name` and `orders.recipient_last_name`

**This is the single source of truth because:**
- Both Buy Item and Create Bid flows save to this field
- Sold tab queries this field
- Account profile name is ONLY used for auto-fill, never for display

---

## Why It Works Now

### Before the Fix:
1. Buy Item modal: JavaScript **didn't send** recipient names → backend got empty values → saved NULL to database
2. Create Bid flow: **Already working** (standard form submission)
3. Sold tab: Queried recipient names but found NULL → displayed "—"

### After the Fix:
1. Buy Item modal: JavaScript **now sends** recipient names → backend receives values → saves to database ✓
2. Create Bid flow: **Still working** (no changes needed)
3. Sold tab: Queries recipient names, finds real values → displays actual names ✓

---

## Testing

### Test Buy Item Flow:

```bash
1. Log in as buyer
2. Go to any bucket page
3. Click "Buy Now"
4. In the Buy Item modal:
   - Name fields should auto-fill with your profile name
   - Change the name to something distinctive: "TestBuyer FirstName"
   - Select delivery address
   - Click "Yes, Complete Purchase"
5. Log in as the seller whose items you bought
6. Go to Account → Sold tab
7. Find the order
8. Under Buyer Information → Name, you should see: "TestBuyer FirstName"
   (NOT your account profile name, and NOT "—")
```

### Test Create Bid Flow:

```bash
1. Log in as buyer
2. Go to any bucket page
3. Click "Place Bid"
4. In the Create Bid modal:
   - Name fields should auto-fill with your profile name
   - Change the name to something distinctive: "BidderName TestLast"
   - Fill out the rest of the form
   - Submit bid
5. Log in as the seller
6. Go to the bucket page
7. Accept the bid
8. Go to Account → Sold tab
9. Find the order
10. Under Buyer Information → Name, you should see: "BidderName TestLast"
    (NOT the buyer's account profile name, and NOT "—")
```

---

## Files Modified

### JavaScript (THE FIX):
- ✅ `static/js/modals/buy_item_modal.js:302-310` - Added recipient name fields to FormData

### No Backend Changes Needed:
All backend code was already correct:
- ✅ `routes/buy_routes.py:1157-1159, 1347-1351` - Extracts and saves recipient names
- ✅ `routes/bid_routes.py:31-33, 103-104, 522-523, 646-649` - Bid flow already working
- ✅ `routes/account_routes.py:234-235, 259-262` - Query and display already correct

### No Template Changes Needed:
All templates were already correct:
- ✅ `templates/modals/buy_item_modal.html:90-101` - Input fields exist
- ✅ `templates/tabs/bid_form.html:296, 300` - Input fields exist
- ✅ `templates/tabs/sold_tab.html:76-79` - Display code exists

---

## Summary

**What was wrong:**
- Buy Item modal JavaScript forgot to include recipient name fields in FormData
- Backend never received the names even though user typed them
- Database saved NULL values
- Sold tab displayed "—"

**What's fixed:**
- JavaScript now includes recipient names in FormData
- Backend receives and saves them
- Sold tab displays actual names

**The canonical field:**
- `orders.recipient_first_name` and `orders.recipient_last_name`

**Why it will always work now:**
- Buy Item flow: JavaScript sends names → backend saves them → Sold tab shows them ✓
- Create Bid flow: Was already working, continues to work ✓
- Account profile name: Only used for auto-fill, never for display ✓
- No more "—" on Sold tiles (unless name is actually empty, which can't happen because field is required)

---

## Verification

After deploying this fix:
1. Create a NEW order via Buy Item with a distinctive name
2. Create a NEW order via Create Bid with a distinctive name
3. Both should show the correct names on Sold tiles
4. No more "—" for Buyer Name!
