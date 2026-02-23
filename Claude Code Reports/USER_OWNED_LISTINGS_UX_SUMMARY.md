# User-Owned Listings UX Implementation Summary

## Overview
Adjusted how user-owned listings interact with pricing and add-to-cart flow on Metex. Bucket price displays now always include user's own listings in best ask calculation, but users are prevented from buying their own listings with proper UX feedback.

## Changes Implemented

### 1. Bucket Price Display - Always Includes User Listings

#### Buy Page (routes/buy_routes.py:48-138)
**Changed:** Removed user exclusion filter from listings query for best ask calculation

**Before:**
```python
# Exclude current user's own listings if logged in
if user_id:
    where_clauses.append('l.seller_id != ?')
    params.append(user_id)
```

**After:**
```python
# DO NOT exclude user's own listings - we need them for best ask calculation
# Track all listings and non-user listings separately for edge case handling
```

**Aggregation logic:** Now tracks both total availability and whether all listings are user-owned:
```python
bucket_data[bucket_id] = {
    'lowest_price': listing['effective_price'],
    'total_available': listing['quantity'],
    'has_non_user_listings': not is_user_listing,
    'total_non_user_available': 0 if is_user_listing else listing['quantity']
}
```

#### Bucket ID Page (routes/buy_routes.py:189-264)
**Changed:** Separate queries for best ask calculation vs. detailed listings display

**Implementation:**
- `all_listings_query`: Gets ALL listings including user's own for best ask price
- `listings_query`: Excludes user's own for detailed view (sellers list, etc.)
- Availability calculated from ALL listings
- Tracks `all_listings_are_users` flag for edge case handling

### 2. Cart-Fill Logic - Detects Skipped User Listings

#### Auto-Fill Cart Route (routes/buy_routes.py:577-641)
**Added:** Detection and notification when user listings are skipped

**Implementation:**
```python
user_listings_skipped = False  # Track if we skipped any user listings

for listing in listings:
    if user_id and listing['seller_id'] == user_id:
        user_listings_skipped = True  # Mark that we skipped a user listing
        continue  # skip own listings
    # ... rest of cart-fill logic ...

# Store flag in session to trigger modal on next page load
if user_listings_skipped and total_filled > 0:
    session['show_own_listings_skipped_modal'] = True
```

**Behavior:**
- Existing skip logic (lines 582-584) remains unchanged
- Only sets flag when:
  1. At least one user listing was skipped
  2. At least one non-user listing was successfully added
- Modal shown on cart page after redirect

### 3. Modal Notification - "Own Listings Skipped"

#### Modal Template (templates/modals/own_listings_skipped_modal.html)
```html
<div id="ownListingsSkippedModal" class="modal">
    <div class="modal-content confirmation-modal">
        <div class="modal-header">
            <h2>Your Own Listings Were Skipped</h2>
        </div>
        <div class="modal-body">
            <p class="modal-message">
                You have active listings in this item. Your own listings were skipped
                and the next lowest-priced listings were added to your cart instead.
            </p>
        </div>
        <div class="modal-footer">
            <button type="button" class="btn btn-primary" id="ownListingsSkippedOkBtn">OK</button>
        </div>
    </div>
</div>
```

#### Modal JavaScript (static/js/modals/own_listings_skipped_modal.js)
**Features:**
- Auto-triggers when `window.showOwnListingsSkippedModal === true`
- OK button closes modal
- Background click closes modal
- Escape key closes modal
- Session flag consumed on page load (session.pop)

#### Cart Page Integration (templates/view_cart.html)
**Added:**
```jinja
{% include 'modals/own_listings_skipped_modal.html' %}

<script>
  window.showOwnListingsSkippedModal = {{ 'true' if session.pop('show_own_listings_skipped_modal', False) else 'false' }};
</script>

<script defer src="{{ url_for('static', filename='js/modals/own_listings_skipped_modal.js') }}"></script>
```

**Behavior:**
- Modal shown EVERY time user listings are skipped (not just once per session)
- Session flag cleared after being read
- Non-intrusive notification (not a confirmation modal, no action required)

### 4. Edge Case - All Listings Are User-Owned

#### Buy Page Template (templates/buy.html:32-36)
**Added:** Warning indicator when all listings belong to user

```jinja
{% if bucket['lowest_price'] is not none %}
    <p class="price">${{ bucket['lowest_price'] }}</p>
    {% if bucket.get('all_listings_are_users', False) and session.get('user_id') %}
        <p class="price no-listings" style="font-size: 11px; margin-top: 4px; color: #f59e0b;">
            Only your own listings
        </p>
    {% endif %}
{% endif %}
```

**Behavior:**
- Shows bucket price (user's own best ask)
- Displays "Only your own listings" warning in orange

#### Bucket ID Page Template (templates/view_bucket.html:271-314)
**Added:** Conditional rendering based on `all_listings_are_users` flag

**Edge case (all user-owned):**
```jinja
{% if availability.get('all_listings_are_users', False) and session.get('user_id') %}
    <!-- Warning message -->
    <div class="own-listings-message" style="background: #fef3c7; border: 1px solid #f59e0b;">
        <strong>You can't buy your own listing.</strong>
        There are no other sellers for this item.
    </div>

    <!-- Disabled Buy/Add to Cart buttons -->
    <button type="submit" class="btn buy-btn" disabled style="opacity: 0.5; cursor: not-allowed;">
        Buy Item
    </button>
    <button type="submit" class="btn add-cart-btn" disabled style="opacity: 0.5; cursor: not-allowed;">
        Add to Cart
    </button>

    <!-- Bid button still active -->
    <button type="button" class="btn bid-btn" onclick="openBidModal({{ bucket['id'] }})">
        Make a Bid
    </button>
{% else %}
    <!-- Normal case: User can buy -->
    <!-- ... standard Buy/Add to Cart buttons ... -->
{% endif %}
```

**Behavior:**
- Price still displayed (user's own best ask)
- Clear inline message explaining why user can't buy
- Buy Item button disabled
- Add to Cart button disabled
- Make a Bid button remains active (user can still place bids)

## Price History Behavior (Unchanged)

**No changes made to price history logic:**
- `services/bucket_price_history_service.py` - Not modified
- `routes/bucket_routes.py` - Not modified
- Chart continues to count user's listings as part of market best ask
- Price tracking and updates work exactly as before

## Files Modified

### Backend
- `routes/buy_routes.py`:
  - Lines 48-138: Buy page - include user listings in best ask
  - Lines 189-264: Bucket ID page - include user listings in best ask
  - Lines 577-641: Cart-fill - detect and flag skipped user listings

### Frontend Templates
- `templates/buy.html`:
  - Lines 32-36: Show "Only your own listings" indicator

- `templates/view_bucket.html`:
  - Lines 271-314: Edge case handling with disabled buttons and message

- `templates/view_cart.html`:
  - Line 12: Include own listings skipped modal
  - Line 193: Pass session flag to JavaScript
  - Line 202: Load modal JavaScript

### Frontend Assets
- `templates/modals/own_listings_skipped_modal.html` - New modal template
- `static/js/modals/own_listings_skipped_modal.js` - New modal JavaScript

## User Experience Flow

### Scenario 1: User Has Listings, Others Exist Too
1. User views bucket on Buy page → sees true best ask (may be their own)
2. User views Bucket ID page → sees true best ask (may be their own)
3. User clicks "Add to Cart" with quantity 5
4. Backend skips user's listings, fills from next-lowest sellers
5. Redirect to cart page
6. Modal appears: "Your own listings were skipped..."
7. User clicks OK, proceeds with checkout

### Scenario 2: All Listings Are User-Owned
1. User views bucket on Buy page → sees price + "Only your own listings" warning
2. User views Bucket ID page → sees:
   - Their own best ask price displayed
   - Warning message: "You can't buy your own listing. There are no other sellers for this item."
   - Buy Item button disabled (grayed out)
   - Add to Cart button disabled (grayed out)
   - Make a Bid button active (can still bid)
3. If user tries to click disabled buttons → no action (browser prevents)
4. User can only place a bid or navigate away

### Scenario 3: Cart Filled Without Skipping User Listings
1. User has listings at $150
2. Other sellers have listings at $140, $145
3. User adds 10 to cart
4. All 10 filled from $140 and $145 listings (user's not encountered)
5. No modal shown (user listings not skipped)

## Key Design Decisions

### 1. Best Ask Always Includes User Listings
**Rationale:**
- Provides accurate market pricing
- User's own listings ARE part of the market
- Price history already includes them (consistency)
- Transparent: user can see their position in market

### 2. Modal Shown Every Time
**Rationale:**
- User might forget they have listings
- Each transaction is independent
- Clear feedback prevents confusion
- Non-intrusive (informational, not blocking)

### 3. Session Flag for Modal Trigger
**Rationale:**
- Redirect pattern requires state persistence
- Session cleanly carries state across redirect
- `session.pop()` ensures flag consumed once
- No database writes needed

### 4. Bid Button Remains Active
**Rationale:**
- User may want to outbid themselves
- Bidding on own bucket is valid use case
- Only buying/adding to cart is blocked

## Testing Checklist

- [ ] Buy page shows correct best ask including user listings
- [ ] Buy page shows "Only your own listings" when all are user-owned
- [ ] Bucket ID page shows correct best ask including user listings
- [ ] Bucket ID page disables Buy/Add to Cart when all listings are user-owned
- [ ] Bucket ID page shows warning message when all listings are user-owned
- [ ] Bid button remains active even when all listings are user-owned
- [ ] Add to Cart skips user listings and fills from next-lowest
- [ ] Modal appears after redirect when user listings were skipped
- [ ] Modal does NOT appear when cart filled without skipping user listings
- [ ] Modal can be closed with OK button
- [ ] Modal can be closed with background click
- [ ] Modal can be closed with Escape key
- [ ] Modal shows every time user listings are skipped (not just once)
- [ ] Price history chart continues to work correctly (unchanged)

## Backward Compatibility

✅ All changes are backward compatible:
- Guests (not logged in) see no changes
- Users without listings see no changes
- Existing cart-fill logic preserved
- Price history service untouched
- No database schema changes
- No breaking changes to APIs

## Edge Cases Handled

1. **User has no listings** → Normal flow, no changes
2. **All listings are user-owned** → Buttons disabled, clear message
3. **User listings not lowest-priced** → Cart fills without skipping, no modal
4. **User listings are lowest-priced** → Skipped, modal shown
5. **Mixed pricing (user + others)** → User's included in best ask, skipped in cart
6. **Guest user** → Unchanged behavior (no user listings to skip)
7. **Cart partially filled** → Modal only shown if user listings were skipped during fill
8. **Cart completely filled** → Modal only shown if at least one user listing was skipped

## Security Considerations

- User cannot circumvent buy restriction (server-side enforcement)
- Session flags are tamper-resistant (server-controlled)
- No data leakage (user only sees their own listings)
- Disabled buttons are visual + server-enforced (form submission would fail anyway)

## Performance Impact

✅ Minimal performance impact:
- One additional query for all_listings on Bucket ID page (O(n) for n listings)
- Aggregation logic complexity unchanged
- Modal JavaScript lazy-loaded (defer)
- Session writes only when needed
- No database schema changes (no migrations)

## Future Enhancements (Optional)

1. **Analytics**: Track how often users try to buy their own listings
2. **Smart suggestions**: "Want to lower your listing price?" when all are user-owned
3. **Bulk actions**: "Remove all my listings from this bucket" button
4. **Notification**: Email when other sellers undercut user's price
5. **Comparison**: Show user's price vs. best non-user price side-by-side
