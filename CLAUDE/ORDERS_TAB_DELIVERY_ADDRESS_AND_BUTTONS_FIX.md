# Orders Tab Delivery Address Modal Fix and Button Layout Reorganization

## Summary

Fixed the delivery address modal to correctly display addresses, implemented a 24-hour restriction window for address changes with countdown timer, added warning messages, and reorganized order tile buttons into a two-row grid layout.

## Changes Implemented

### 1. Fixed Delivery Address Display

**Problem:** Modal showed "No delivery address set for this order" even though addresses were correctly shown in checkout.

**Root Cause:** Orders are created with `shipping_address` field at checkout, but the order queries were only selecting `delivery_address` field (which is null for new orders).

**Solution:**

**Backend:** `routes/account_routes.py` (lines 97, 134)

Updated both pending and completed order queries to use COALESCE:

```sql
COALESCE(o.delivery_address, o.shipping_address) AS delivery_address
```

This prioritizes `delivery_address` (user-changed address) but falls back to `shipping_address` (original checkout address) if not set.

**JavaScript:** `static/js/tabs/orders_tab.js` (lines 87-93)

Improved address parsing to handle both plain text and comma-separated addresses:

```javascript
if (typeof deliveryAddress === 'string') {
  // Plain text address - split by newline or comma
  const lines = deliveryAddress.includes('\n') ? deliveryAddress.split('\n') : deliveryAddress.split(',');
  addressDisplay.innerHTML = lines.map(line =>
    `<div>${line.trim()}</div>`
  ).join('');
}
```

### 2. Implemented 24-Hour Address Change Restriction

**Requirements:**
- Allow address changes only within 24 hours of order creation
- Show countdown timer indicating time remaining
- Disable all controls after 24 hours with clear message

**Implementation:**

**Modal Template:** `templates/modals/order_delivery_address_modal.html` (lines 13-24)

Added countdown section and warning banner:

```html
<!-- Countdown/Warning Section -->
<div id="addressChangeCountdown" class="countdown-section">
  <!-- Populated by JavaScript -->
</div>

<!-- Warning Banner (shown after address change) -->
<div id="addressChangeWarning" class="address-warning-banner" style="display: none;">
  <i class="fas fa-exclamation-triangle"></i>
  <div>
    <strong>Address Change Notice:</strong> Because this change was made after your order was confirmed...
  </div>
</div>
```

Added IDs to sections that need to be hidden after 24 hours (lines 34, 43):
- `savedAddressesSection`
- `addAddressSection`

**JavaScript:** `static/js/tabs/orders_tab.js`

**Function Updates:**

1. **openOrderDeliveryAddressModal()** (line 71) - Now accepts `orderDate` parameter:

```javascript
function openOrderDeliveryAddressModal(orderId, deliveryAddressJson, orderDate) {
  // Calculate time remaining for address changes (24 hours from order creation)
  const orderCreatedAt = new Date(orderDate);
  const now = new Date();
  const hoursElapsed = (now - orderCreatedAt) / (1000 * 60 * 60);
  const canChangeAddress = hoursElapsed < 24;

  // Update countdown timer and enable/disable controls
  updateCountdownTimer(orderCreatedAt, canChangeAddress);
  loadSavedAddresses(canChangeAddress);
```

2. **New function: updateCountdownTimer()** (lines 132-171):

```javascript
function updateCountdownTimer(orderCreatedAt, canChangeAddress) {
  const countdownElement = document.getElementById('addressChangeCountdown');
  const savedAddressesSection = document.getElementById('savedAddressesSection');
  const addAddressSection = document.getElementById('addAddressSection');

  if (canChangeAddress) {
    // Calculate and display countdown
    const updateCountdown = () => {
      const now = new Date();
      const deadline = new Date(orderCreatedAt.getTime() + 24 * 60 * 60 * 1000);
      const timeRemaining = deadline - now;

      if (timeRemaining <= 0) {
        countdownElement.innerHTML = '<div class="countdown-expired">Delivery address can no longer be changed for this order.</div>';
        savedAddressesSection.style.display = 'none';
        addAddressSection.style.display = 'none';
        clearInterval(countdownInterval);
      } else {
        const hours = Math.floor(timeRemaining / (1000 * 60 * 60));
        const minutes = Math.floor((timeRemaining % (1000 * 60 * 60)) / (1000 * 60));
        countdownElement.innerHTML = `<div class="countdown-active"><i class="fas fa-clock"></i> Address changes allowed for: ${hours} hours ${minutes} minutes</div>`;
      }
    };

    updateCountdown();
    countdownInterval = setInterval(updateCountdown, 60000); // Update every minute
  } else {
    // Past 24 hours - disable all controls
    countdownElement.innerHTML = '<div class="countdown-expired">Delivery address can no longer be changed for this order.</div>';
    savedAddressesSection.style.display = 'none';
    addAddressSection.style.display = 'none';
  }
}
```

3. **Updated loadSavedAddresses() and renderSavedAddresses()** (lines 173-206):

Now accept `canChangeAddress` parameter and disable address items when past 24 hours:

```javascript
function renderSavedAddresses(canChangeAddress) {
  container.innerHTML = savedAddresses.map(addr => `
    <div class="saved-address-item ${!canChangeAddress ? 'disabled' : ''}" ${canChangeAddress ? `onclick="selectSavedAddress(${addr.id})"` : ''}>
      ...
    </div>
  `).join('');
}
```

4. **Updated closeOrderDeliveryAddressModal()** (lines 261-277):

Clears countdown interval on modal close:

```javascript
function closeOrderDeliveryAddressModal() {
  // Clear countdown interval
  if (countdownInterval) {
    clearInterval(countdownInterval);
    countdownInterval = null;
  }
  // Hide warning banner
  const warningBanner = document.getElementById('addressChangeWarning');
  if (warningBanner) {
    warningBanner.style.display = 'none';
  }
}
```

**Template Updates:** `templates/tabs/orders_tab.html` (lines 84, 190)

Updated button onclick to pass order_date:

```html
onclick="openOrderDeliveryAddressModal({{ order.id }}, '{{ order.delivery_address | tojson | safe }}', '{{ order.order_date }}')"
```

**CSS:** `static/css/modals/order_delivery_address_modal.css` (lines 67-128)

Added styles for countdown and warning elements:

```css
/* Countdown Active State */
.countdown-active {
  background: #eff6ff;
  border: 1px solid #3da6ff;
  border-radius: 8px;
  padding: 12px 16px;
  font-size: 0.9rem;
  color: #1877ff;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Countdown Expired State */
.countdown-expired {
  background: #fef2f2;
  border: 1px solid #fca5a5;
  border-radius: 8px;
  padding: 12px 16px;
  font-size: 0.9rem;
  color: #dc2626;
  font-weight: 500;
}

/* Warning Banner */
.address-warning-banner {
  background: #fef3c7;
  border: 2px solid #f59e0b;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 20px;
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

/* Disabled Address Items */
.saved-address-item.disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background: #f9fafb;
}
```

### 3. Added Warning Message on Address Change

**Location:** `static/js/tabs/orders_tab.js` (lines 208-259)

**Implementation:**

When user selects a new address, the modal:
1. Shows warning banner with notice about potential delivery issues
2. Waits 5 seconds for user to read the warning
3. Automatically closes modal and reloads page

```javascript
function selectSavedAddress(addressId) {
  // Update order delivery address via API
  fetch(`/account/api/orders/${currentOrderId}/delivery-address`, {...})
    .then(data => {
      if (data.success) {
        // Show warning banner
        if (warningBanner) {
          warningBanner.style.display = 'block';
          // Wait 5 seconds, then reload
          setTimeout(() => {
            closeOrderDeliveryAddressModal();
            location.reload();
          }, 5000);
        }
      }
    });
}
```

**Warning Message:**

> "**Address Change Notice:** Because this change was made after your order was confirmed, there is a possibility the new address will not take effect. Please monitor tracking updates to verify the delivery destination."

### 4. Reorganized Buttons into Two-Row Grid

**Layout Specification:**

```
Top row:    Sellers | Items | Rate | Add to Portfolio
Bottom row: (blank) | Message | Track | Delivery Address
```

Bottom row is right-aligned so "Delivery Address" aligns vertically with "Add to Portfolio".

**Template Changes:** `templates/tabs/orders_tab.html`

**Pending Orders** (lines 38-94):

```html
<div class="order-footer">
  <div class="order-date-display">{{ order.formatted_order_date }}</div>

  <div class="order-buttons-grid">
    <!-- Top row: Sellers, Items, Rate, Add to Portfolio -->
    <button class="order-btn" onclick="openOrderSellerPopup({{ order.id }})">
      <i class="fa-solid fa-user"></i>
      <span>Sellers</span>
    </button>

    <button class="order-btn" onclick="openOrderItemsPopup({{ order.id }})">
      <i class="fa-solid fa-list"></i>
      <span>Items</span>
    </button>

    <button class="order-btn" onclick="openRateModal({{ order.id }}, 'seller')">
      <i class="fas fa-star"></i>
      <span>Rate</span>
    </button>

    <button class="order-btn {% if order.excluded_count == 0 %}portfolio-btn-disabled{% endif %}"
            onclick="toggleOrderPortfolio({{ order.id }}, {{ order.excluded_count }})"
            {% if order.excluded_count == 0 %}disabled{% endif %}>
      <i class="fas fa-chart-pie"></i>
      <span>Add to portfolio</span>
    </button>

    <!-- Bottom row: (blank), Message, Track, Delivery Address -->
    <div class="order-btn-spacer"></div>

    <button class="order-btn" onclick="openMessageModal({{ order.id }}, 'seller')">
      <i class="fas fa-envelope"></i>
      <span>Message</span>
    </button>

    <button class="order-btn" onclick="addTrackingNumber({{ order.id }})">
      <i class="fas fa-box"></i>
      <span>Track</span>
    </button>

    <button class="order-btn"
            onclick="openOrderDeliveryAddressModal({{ order.id }}, '{{ order.delivery_address | tojson | safe }}', '{{ order.order_date }}')">
      <i class="fas fa-map-marker-alt"></i>
      <span>Delivery Address</span>
    </button>
  </div>
</div>
```

**Completed Orders** (lines 139-195): Same structure

**CSS Changes:** `static/css/tabs/orders_tab.css` (lines 121-152)

```css
/* Footer: full width with date on left, button grid on right */
.orders-tab .order-footer {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-top: 12px;
}

/* Order date display (bottom-left) */
.orders-tab .order-date-display {
  font-size: 0.9rem;
  color: #666;
  font-weight: 500;
  padding-top: 6px;
}

/* Button grid: 2 rows x 4 columns, right-aligned */
.orders-tab .order-buttons-grid {
  display: grid;
  grid-template-columns: repeat(4, auto);
  grid-template-rows: repeat(2, auto);
  gap: 6px 8px;
  align-items: center;
  justify-content: end;
}

/* Spacer for blank space in bottom row */
.orders-tab .order-btn-spacer {
  grid-column: 1;
  grid-row: 2;
}
```

## Files Modified

### Backend
1. `routes/account_routes.py`
   - Updated pending orders query (line 97)
   - Updated completed orders query (line 134)

### Templates
1. `templates/tabs/orders_tab.html`
   - Reorganized pending orders buttons (lines 38-94)
   - Reorganized completed orders buttons (lines 139-195)
   - Updated delivery address button onclick (lines 84, 190)

2. `templates/modals/order_delivery_address_modal.html`
   - Added countdown section (lines 13-16)
   - Added warning banner (lines 18-24)
   - Added IDs to sections for show/hide logic (lines 34, 43)

### Frontend
1. `static/js/tabs/orders_tab.js`
   - Updated openOrderDeliveryAddressModal() (lines 71-130)
   - Added updateCountdownTimer() (lines 132-171)
   - Updated loadSavedAddresses() (lines 173-185)
   - Updated renderSavedAddresses() (lines 187-206)
   - Updated selectSavedAddress() (lines 208-259)
   - Updated closeOrderDeliveryAddressModal() (lines 261-277)

2. `static/css/tabs/orders_tab.css`
   - Updated footer layout (lines 121-128)
   - Added button grid styles (lines 138-152)

3. `static/css/modals/order_delivery_address_modal.css`
   - Added countdown styles (lines 67-96)
   - Added warning banner styles (lines 98-128)
   - Added disabled address item styles (lines 204-213)

## Testing Checklist

### Delivery Address Display
- [ ] Create new order with delivery address
- [ ] Navigate to Orders tab and click "Delivery Address"
- [ ] Verify modal shows correct address line-by-line
- [ ] Verify address matches what was entered at checkout
- [ ] Test with orders created before this fix (should show shipping_address)
- [ ] Test with orders where address was changed (should show delivery_address)

### 24-Hour Countdown
- [ ] Create order less than 24 hours old
- [ ] Open delivery address modal
- [ ] Verify countdown shows: "Address changes allowed for: X hours Y minutes"
- [ ] Verify countdown updates every minute
- [ ] Verify saved addresses list is enabled and clickable
- [ ] Verify "Add New Address" button is visible

### 24-Hour Restriction
- [ ] Find order more than 24 hours old (or manually set order_date in database)
- [ ] Open delivery address modal
- [ ] Verify message shows: "Delivery address can no longer be changed for this order."
- [ ] Verify saved addresses section is hidden
- [ ] Verify "Add New Address" button is hidden
- [ ] Verify saved address items have disabled styling and are not clickable

### Warning Message
- [ ] Create order less than 24 hours old
- [ ] Open delivery address modal
- [ ] Select a different saved address
- [ ] Verify warning banner appears with yellow/orange styling
- [ ] Verify warning message is clear and professional
- [ ] Verify modal closes and page reloads after 5 seconds
- [ ] Verify address was updated correctly

### Button Grid Layout
- [ ] Navigate to Orders tab
- [ ] Verify buttons are arranged in 2 rows
- [ ] Verify top row has: Sellers, Items, Rate, Add to Portfolio (left to right)
- [ ] Verify bottom row has: (blank space), Message, Track, Delivery Address (left to right)
- [ ] Verify bottom row is right-aligned
- [ ] Verify "Delivery Address" aligns vertically with "Add to Portfolio"
- [ ] Verify all buttons have consistent spacing
- [ ] Verify hover states work correctly
- [ ] Verify disabled portfolio button styling still works
- [ ] Test responsive behavior at different screen widths

### Edge Cases
- [ ] Test with order that has null/empty delivery address
- [ ] Test with very long address text
- [ ] Test with user who has no saved addresses
- [ ] Test countdown when exactly at 23:59 remaining
- [ ] Test countdown when time crosses midnight (new day)
- [ ] Test changing address multiple times within 24 hours
- [ ] Test closing modal while countdown is running
- [ ] Test opening multiple orders' modals (verify countdown clears properly)

## Technical Notes

### Address Storage Strategy

The system uses two fields for flexibility:
- **`shipping_address`**: Original address from checkout (never changes)
- **`delivery_address`**: User-modified address (null by default)

The `COALESCE(o.delivery_address, o.shipping_address)` ensures:
1. If user changes address → shows `delivery_address`
2. If user never changes → shows `shipping_address` (original)
3. Always displays an address if one exists

### Countdown Timer Implementation

- Updates every 60 seconds (60000ms interval)
- Clears interval on modal close to prevent memory leaks
- Calculates remaining time from server-provided `order_date`
- Automatically disables controls when time expires
- Shows hours and minutes for better UX

### Grid Layout

Uses CSS Grid with:
- 4 columns (auto-sized to content)
- 2 rows (auto-sized)
- `justify-content: end` for right alignment
- Spacer div in column 1, row 2 for blank space
- Gap: 6px vertical, 8px horizontal

### Button Text Consistency

Changed portfolio button text from "This item is in my portfolio" to "Add to portfolio" for consistency across both pending and completed orders sections.

## Future Enhancements

- Add email notification when address is changed
- Track address change history (audit log)
- Allow custom restriction window (configurable instead of hardcoded 24 hours)
- Add bulk address update for multiple orders
- Show delivery address on order confirmation email
