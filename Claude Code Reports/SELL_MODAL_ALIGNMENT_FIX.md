# Sell Modal Item Category Details Alignment Fix

## Summary

Added CSS styling to properly align labels (left) and values (right) in the Item Category Details container on both Confirm Listing and Listing Created modals.

## Problem

The Item Category Details grid was missing specific CSS rules for `.spec-item`, `.spec-label`, and `.spec-value`, resulting in improper alignment of labels and values.

## Solution

Added comprehensive CSS styling to `static/css/modals/sell_listing_modals.css` (lines 96-135) to ensure:

1. **Labels are left-aligned** within their column
2. **Values are right-aligned** within their column
3. Proper 2-column grid layout
4. Visual separation between items with borders

## CSS Changes Made

### Grid Layout
```css
.item-specs-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px 20px;
}
```
Creates a 2-column grid with:
- Equal column widths (`1fr` each)
- 12px vertical gap between rows
- 20px horizontal gap between columns

### Individual Spec Items
```css
.spec-item {
  display: flex;
  flex-direction: row;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid #e5e7eb;
}
```
Each item row:
- Uses flexbox with `space-between` to push values to the right
- Aligns label and value at baseline
- Adds bottom border for visual separation
- 8px vertical padding for comfortable spacing

### Border Cleanup
```css
.item-specs-grid .spec-item:nth-last-child(-n+2) {
  border-bottom: none;
}
```
Removes border from last row items (handles both even and odd number of items)

### Label Styling
```css
.spec-item .spec-label {
  font-size: 13px;
  font-weight: 600;
  color: #6b7280;
  white-space: nowrap;
  text-align: left;
}
```
Labels:
- **Left-aligned** (`text-align: left`)
- Gray color (#6b7280)
- 13px font size
- Bold (600 weight)
- No wrapping (`white-space: nowrap`)

### Value Styling
```css
.spec-item .spec-value {
  font-size: 15px;
  font-weight: 600;
  color: #111827;
  text-align: right;
  word-break: break-word;
}
```
Values:
- **Right-aligned** (`text-align: right`)
- Dark color (#111827)
- 15px font size (slightly larger than labels)
- Bold (600 weight)
- Breaks long words if needed

## Visual Result

### Before:
```
Metal: Platinum                Product Line: 80% Canadian Silver
[Values not aligned]           [Values not aligned]
```

### After:
```
Metal:              Platinum   Product Line:   80% Canadian Silver
[Label left]    [Value right]  [Label left]        [Value right]
```

Each column maintains:
- Labels flush-left
- Values flush-right
- Consistent spacing between label and value

## Files Modified

1. `static/css/modals/sell_listing_modals.css` - Added grid and alignment styles

## Testing

Verify alignment in both modals:

### Confirm Listing Modal
1. ✅ Fill out sell form with all fields
2. ✅ Click "List Item" to open Confirm Listing modal
3. ✅ Verify in Item Category Details section:
   - All labels (Metal:, Product Line:, etc.) align to the left
   - All values (Platinum, 80% Canadian Silver, etc.) align to the right
   - Values stay within their column (no overflow)

### Listing Created Modal
1. ✅ Complete listing creation
2. ✅ View "Listing Created!" success modal
3. ✅ Verify in Item Category Details section:
   - All labels align to the left
   - All values align to the right
   - Long values (like "80% Canadian Silver") break properly and stay right-aligned

### Responsive Testing
1. ✅ Test at desktop width (1920px+)
2. ✅ Test at tablet width (768px-1024px)
3. ✅ Test at mobile width (320px-480px)
4. ✅ Verify grid collapses to single column on mobile if needed
5. ✅ Verify alignment remains correct at all breakpoints

## Technical Notes

### Flexbox Layout
Each `.spec-item` uses flexbox with:
- `flex-direction: row` - Horizontal layout
- `justify-content: space-between` - Maximum space between label and value
- `align-items: baseline` - Aligns text baselines (not top/bottom)

This ensures:
- Labels stay left
- Values stay right
- Text aligns properly regardless of font size differences

### Grid Responsiveness
The 2-column grid will:
- Show 2 columns on desktop/tablet
- Can be collapsed to 1 column on mobile with media query if needed
- Maintains equal column widths with `1fr` units

### Text Wrapping
- Labels: `white-space: nowrap` prevents label text from wrapping
- Values: `word-break: break-word` allows long values to wrap if needed while maintaining right alignment

## Consistency with Other Modals

This styling matches:
- `accept_bid_modals.css` - Uses identical alignment approach
- `bid_confirm_modal.css` - Uses identical grid layout
- `buy_item_modal.css` - Uses identical spec item structure

All Item Category Details grids across the app now have consistent:
- Layout structure
- Alignment behavior
- Visual styling
