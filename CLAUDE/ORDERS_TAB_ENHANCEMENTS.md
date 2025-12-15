# Orders Tab Enhancements - Account Page

## Summary

Implemented comprehensive enhancements to the Account → Orders tab (buyer view) including grading display, reformatted date/time, portfolio inclusion control, and delivery address management.

## Changes Implemented

### 1. Added "Require 3rd Party Grading" Field

**Location:** `templates/tabs/orders_tab.html` (lines 23-27, 98-102)

Added grading display to item details section for both pending and completed orders:

```html
{% if order.graded %}
  <div><strong>Require 3rd Party Grading:</strong> Yes ({{ order.grading_service }})</div>
{% else %}
  <div><strong>Require 3rd Party Grading:</strong> No</div>
{% endif %}
```

**Backend Changes:** `routes/account_routes.py` (lines 107-108, 144-145)

Added grading fields to order queries:
- `MIN(l.graded) AS graded`
- `MIN(l.grading_service) AS grading_service`

### 2. Reformatted Order Date Display

**Location:** Date moved from order-details to order-footer bottom-left

**Template Changes:** `templates/tabs/orders_tab.html` (lines 39, 134)

```html
<div class="order-date-display">{{ order.formatted_order_date }}</div>
```

**Backend Formatting:** `routes/account_routes.py` (lines 171-176)

Added date formatting to convert timestamps to "2:52 PM, 12 December 2025" format:

```python
from datetime import datetime
for order in pending_orders + completed_orders:
    if order.get('order_date'):
        dt = datetime.fromisoformat(order['order_date'])
        order['formatted_order_date'] = dt.strftime('%I:%M %p, %d %B %Y').lstrip('0')
```

**CSS Styling:** `static/css/tabs/orders_tab.css` (lines 121-135)

- Updated footer layout to `justify-content: space-between`
- Added date styling (font-size: 0.9rem, color: #666)

### 3. Portfolio Inclusion Button

**Location:** `templates/tabs/orders_tab.html` (lines 74-80, 169-175)

Added portfolio control button with conditional disabled state:

```html
<button
  class="order-btn {% if order.excluded_count == 0 %}portfolio-btn-disabled{% endif %}"
  onclick="toggleOrderPortfolio({{ order.id }}, {{ order.excluded_count }})"
  {% if order.excluded_count == 0 %}disabled{% endif %}>
  <i class="fas fa-chart-pie"></i>
  <span>This item is in my portfolio</span>
</button>
```

**Backend Changes:** `routes/account_routes.py` (lines 113-117, 151-155)

Added portfolio exclusion check to order queries:

```sql
(SELECT COUNT(*) FROM order_items oi2
   JOIN portfolio_exclusions pe ON pe.order_item_id = oi2.order_item_id
  WHERE oi2.order_id = o.id
    AND pe.user_id = ?
) AS excluded_count
```

**JavaScript:** `static/js/tabs/orders_tab.js` (lines 32-64)

Implemented `toggleOrderPortfolio()` function to re-include excluded orders:
- Calls `/account/api/orders/<order_id>/portfolio/include`
- Removes all portfolio_exclusions for order items
- Reloads page on success

**API Route:** `routes/account_routes.py` (lines 1071-1114)

```python
@account_bp.route('/account/api/orders/<int:order_id>/portfolio/include', methods=['POST'])
def include_order_in_portfolio(order_id):
    # Removes all portfolio exclusions for order items in this order
```

**CSS:** `static/css/tabs/orders_tab.css` (lines 153-163)

Added disabled state styling:
- Opacity: 0.5, cursor: not-allowed
- Background: #e5e7eb, color: #9ca3af

### 4. Delivery Address Modal

**Modal Template:** `templates/modals/order_delivery_address_modal.html`

Created comprehensive modal with:
- Current delivery address display (line-by-line format)
- Saved addresses selection list
- "Add New Address" button (reuses existing address modal)

**Modal CSS:** `static/css/modals/order_delivery_address_modal.css`

Styled modal with:
- Rounded card design (border-radius: 20px)
- Professional color scheme matching Metex
- Hover effects on saved addresses
- Responsive layout

**Template Integration:** `templates/account.html` (line 14)

Added modal include:
```html
{% include 'modals/order_delivery_address_modal.html' %}
```

**CSS Link:** `templates/account.html` (line 64)

```html
<link rel="stylesheet" href="{{ url_for('static', filename='css/modals/order_delivery_address_modal.css') }}">
```

**Button:** `templates/tabs/orders_tab.html` (lines 82-87, 177-182)

```html
<button
  class="order-btn"
  onclick="openOrderDeliveryAddressModal({{ order.id }}, '{{ order.delivery_address | tojson | safe }}')">
  <i class="fas fa-map-marker-alt"></i>
  <span>Delivery Address</span>
</button>
```

**JavaScript:** `static/js/tabs/orders_tab.js` (lines 66-217)

Implemented modal functions:
- `openOrderDeliveryAddressModal()` - Opens modal, parses and displays address
- `loadSavedAddresses()` - Fetches saved addresses from API
- `renderSavedAddresses()` - Displays saved addresses list
- `selectSavedAddress()` - Updates order delivery address
- `closeOrderDeliveryAddressModal()` - Closes modal
- `openAddressModalForOrder()` - Opens existing address modal to add new address

**API Routes:** `routes/account_routes.py`

**GET /account/api/addresses** (lines 1043-1068)
```python
def get_saved_addresses():
    # Returns all saved addresses for current user
```

**PUT /account/api/orders/<order_id>/delivery-address** (lines 1117-1183)
```python
def update_order_delivery_address(order_id):
    # Updates order delivery_address field with selected address JSON
```

## Files Modified

### Backend
1. `routes/account_routes.py`
   - Updated pending orders query (lines 91-127)
   - Updated completed orders query (lines 128-166)
   - Added date formatting (lines 171-176)
   - Added 3 new API routes (lines 1043-1183)

### Templates
1. `templates/tabs/orders_tab.html`
   - Added grading display (lines 23-27, 98-102)
   - Moved date to footer (lines 39, 134)
   - Added portfolio button (lines 74-80, 169-175)
   - Added delivery address button (lines 82-87, 177-182)

2. `templates/account.html`
   - Added modal include (line 14)
   - Added CSS link (line 64)

### Frontend
1. `static/css/tabs/orders_tab.css`
   - Updated footer layout (lines 121-128)
   - Added date styling (lines 130-135)
   - Added portfolio button disabled state (lines 153-163)

2. `static/js/tabs/orders_tab.js`
   - Added portfolio toggle function (lines 32-64)
   - Added delivery address modal functions (lines 66-217)

### New Files Created
1. `templates/modals/order_delivery_address_modal.html` - Delivery address modal template
2. `static/css/modals/order_delivery_address_modal.css` - Modal styling

## Testing Checklist

### Grading Display
- [ ] Add graded (PCGS) listing to cart and complete purchase
- [ ] Navigate to Account → Orders tab
- [ ] Verify order shows "Require 3rd Party Grading: Yes (PCGS)"
- [ ] Add ungraded listing and complete purchase
- [ ] Verify order shows "Require 3rd Party Grading: No"
- [ ] Check both pending and completed orders sections

### Date/Time Display
- [ ] Create multiple orders at different times
- [ ] Verify each order shows date in format "2:52 PM, 12 December 2025"
- [ ] Verify date appears bottom-left of order footer
- [ ] Verify date aligns horizontally with buttons
- [ ] Check responsive behavior at different screen widths

### Portfolio Button
- [ ] Create new order (should be included in portfolio by default)
- [ ] Verify portfolio button is greyed out and disabled
- [ ] Navigate to Portfolio tab and exclude the order
- [ ] Return to Orders tab - verify button is now enabled/clickable
- [ ] Click button to re-include order
- [ ] Verify page reloads and button returns to disabled state
- [ ] Verify order reappears in Portfolio tab

### Delivery Address Modal
- [ ] Create order with delivery address set
- [ ] Click "Delivery Address" button
- [ ] Verify modal opens and displays current address
- [ ] Verify saved addresses list loads
- [ ] Select a different saved address
- [ ] Verify modal closes and page reloads
- [ ] Verify delivery address updated (check modal again)
- [ ] Click "Add New Address" button
- [ ] Verify address modal opens for creating new address
- [ ] Create new address and verify it appears in saved list

### Edge Cases
- [ ] Test with order that has no delivery address set
- [ ] Test with user who has no saved addresses
- [ ] Test portfolio button with order containing multiple order_items
- [ ] Test date formatting with orders from different months/years
- [ ] Test modal responsiveness on mobile devices

## Technical Notes

### Portfolio Inclusion Logic

The portfolio inclusion system uses the `portfolio_exclusions` table:
- **Default state:** Orders are included in portfolio (no exclusion records)
- **Excluded state:** Order items have records in `portfolio_exclusions`
- **Button logic:**
  - `excluded_count = 0`: Order fully included → Button disabled (greyed)
  - `excluded_count > 0`: Order excluded → Button enabled → Clicking removes exclusions

### Delivery Address Storage

Delivery addresses are stored as JSON in the `orders.delivery_address` field:

```json
{
  "name": "Home",
  "street": "123 Main St",
  "street_line2": "Apt 4B",
  "city": "New York",
  "state": "NY",
  "zip_code": "10001",
  "country": "USA"
}
```

The JavaScript handles both JSON objects and plain text addresses for backward compatibility.

### Date Formatting

SQLite stores timestamps in ISO format. Backend converts to user-friendly format:
- Input: `2025-12-04 14:52:00`
- Output: `2:52 PM, 12 December 2025`

The `.lstrip('0')` removes leading zero from single-digit hours (e.g., "02:52 PM" → "2:52 PM").

## Related Features

- **Portfolio Tab:** Orders excluded via Portfolio tab will have enabled buttons in Orders tab
- **Account Details Tab:** Saved addresses created here appear in delivery address modal
- **Address Modal:** Reused for adding new addresses from Orders tab

## Future Enhancements

- Add bulk portfolio inclusion/exclusion
- Add delivery address editing directly in modal
- Add order notes/comments field
- Add email notification toggle per order
- Add tracking number display in orders tab
