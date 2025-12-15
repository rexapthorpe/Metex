# Cart Item Details and Order Summary Update

## Overview
Updated the cart page and cart tab to display full item description details matching the Orders tab format, and improved the order summary layout to look like a receipt with aligned columns.

## Changes Made

### 1. Backend Updates

**File:** `routes/buy_routes.py` (lines 739-778)

**Added fields to bucket.category:**
- `purity`: Item purity (displays as "--" if missing)
- `product_line`: Product line (displays as "--" if missing)

**Added fields to bucket.listings:**
- `graded`: Boolean indicating if the specific listing is third-party graded
- `grading_service`: The grading service (PCGS or NGC) if graded

These fields were already being fetched by `get_cart_items()` in `utils/cart_utils.py` but weren't being passed through to the templates.

---

### 2. Cart Page Template Updates

**File:** `templates/view_cart.html` (lines 50-74)

**Changed from:**
- Only showing: Mint, Year, Finish, Grade

**Changed to:**
- Full details list matching Orders tab:
  - Metal
  - Product Type
  - Weight
  - Purity (or "--")
  - Mint
  - Year
  - Finish
  - Grade
  - Product Line (or "--")
  - 3rd party graded: Yes (PCGS/NGC) or No (based on actual listing)

**Order Summary:** (lines 139-172)
- Restructured with receipt-style layout
- Labels left-aligned, values right-aligned
- Each bucket shows:
  - Item title
  - Quantity
  - Average Price
  - Subtotal
- Grand Total at bottom with bold styling

---

### 3. Cart Tab Template Updates

**File:** `templates/tabs/cart_tab.html` (lines 16-40)

**Applied same changes as cart page:**
- Full item details list
- Same field order and formatting
- Shows grading status of actual listing added to cart

---

### 4. CSS Updates

**File:** `static/css/view_cart.css`

**Added styles for item details list:** (lines 266-280)
```css
.item-details-list {
  margin-top: 8px;
  line-height: 1.6;
}

.item-details-list div {
  margin: 2px 0;
  font-size: 14px;
}

.item-details-list strong {
  font-weight: 600;
  color: #333;
}
```

**Added receipt-style summary layout:** (lines 226-264)
```css
.summary-line {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 4px 0;
  font-size: 14px;
}

.summary-label {
  text-align: left;
  flex: 1;
}

.summary-value {
  text-align: right;
  font-weight: 500;
}

.summary-grand-total {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 2px solid #333;
  font-size: 16px;
}
```

---

## Key Features

### Full Item Details
- **Consistent with Orders tab:** Cart tiles now show the same comprehensive details as order tiles
- **Missing field handling:** Fields with null/empty values display as "--" instead of being hidden
- **Grading accuracy:** Shows actual grading status of the specific listing added to cart, not just whether the item "requires" grading

### Receipt-Style Order Summary
- **Left column:** All labels (Quantity, Average Price, Subtotal, Total) are left-aligned
- **Right column:** All values (numbers, dollar amounts) are right-aligned
- **Visual hierarchy:** Grand total has heavier border and bold text
- **Clean layout:** Uses flexbox for perfect alignment

---

## Testing Checklist

- [ ] Cart page shows all 10 fields for each item
- [ ] Cart tab shows all 10 fields for each item
- [ ] Missing fields (Purity, Product Line) display as "--"
- [ ] 3rd party graded field shows correct value based on listing
- [ ] Order summary labels are left-aligned
- [ ] Order summary values are right-aligned
- [ ] Grand total is visually distinct
- [ ] Layout works on different screen sizes

---

## Example Display

**Cart Item Tile:**
```
1 oz Gold Eagle

Metal: Gold
Product Type: Eagle
Weight: 1 oz
Purity: .9999
Mint: US Mint
Year: 2024
Finish: Brilliant Uncirculated
Grade: MS-70
Product Line: American Eagle
3rd party graded: Yes (PCGS)
```

**Order Summary:**
```
Order Summary

Gold Eagle
Quantity:              2
Average Price:    $2,450.00
Subtotal:         $4,900.00
---
Total:            $4,900.00

[Proceed to Checkout]
```

All changes are complete and ready for testing!
