# Pricing Mode Cards - Vertical Stack Update

## Change Summary

Updated the pricing mode cards to stack **vertically** instead of displaying side-by-side.

---

## Before (Side-by-Side):

```
┌─────────────────────┐  ┌─────────────────────┐
│  $  | Fixed Price   │  │ 📈 | Premium to Spot │
│       Set exact     │  │       Track market  │
└─────────────────────┘  └─────────────────────┘
```

---

## After (Stacked Vertically):

```
┌─────────────────────────────────┐
│  $  | Fixed Price                │
│       Set exact price            │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│ 📈 | Premium to Spot             │
│       Track market               │
└─────────────────────────────────┘
```

---

## CSS Change

**File:** `static/css/sell.css`

**Before:**
```css
.pricing-mode-cards {
  display: grid;
  grid-template-columns: repeat(2, 1fr);  /* Side-by-side */
  gap: 1rem;
  margin-bottom: 1.5rem;
  max-width: 700px;
}
```

**After:**
```css
.pricing-mode-cards {
  display: grid;
  grid-template-columns: 1fr;  /* Stacked vertically */
  gap: 1rem;
  margin-bottom: 1.5rem;
  max-width: 700px;
}
```

---

## Benefits

✅ **Better alignment** - Cards align properly with other form elements
✅ **Consistent layout** - All sections now use vertical stacking
✅ **Easier to scan** - Users read top-to-bottom naturally
✅ **More space for content** - Each card has full width available
✅ **Professional appearance** - Matches common form design patterns

---

## Visual Layout

### Full Pricing Section:

```
Pricing Mode
├── [Fixed Price Card - Full Width]
├── [Premium to Spot Card - Full Width]
└── Fields Container
    ├── Price Per Unit (for Fixed Price)
    └── OR
        ├── Pricing Metal
        ├── Premium Above Spot  } 3-column grid
        └── Floor Price
```

---

## Test File

**Created:** `test_pricing_stacked.html`

**To test:**
```bash
open test_pricing_stacked.html
```

**Features:**
- Shows stacked pricing cards
- Toggle functionality works
- Displays window width
- Visual confirmation of the change

---

## Responsive Behavior

**All screen sizes:** Cards stack vertically
- Desktop: Single column, max-width 700px, centered
- Tablet: Single column, max-width 700px, centered
- Mobile: Single column, full width

**Note:** The premium fields grid (3 columns) still collapses to single column on mobile.

---

## Impact

### Files Modified:
1. `static/css/sell.css` - Line ~428-434

### Lines Changed:
- 1 line (changed `repeat(2, 1fr)` to `1fr`)
- Removed redundant media query rule

### Backward Compatibility:
✅ Fully compatible - no JavaScript changes needed
✅ No template changes required
✅ Existing functionality preserved

---

## Status

✅ **Complete** - Pricing cards now stack vertically for better alignment

**Last Updated:** January 2, 2026
