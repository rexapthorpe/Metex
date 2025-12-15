# Notification Settings Feature

## Overview

This feature allows users to control their notification preferences for both email and in-app notifications. Users can independently toggle notifications for listing sales and bid acceptances.

## Features

- **4 Independent Toggles:**
  - Email notifications for listings being sold
  - Email notifications for bids being accepted
  - In-app notifications for listings being sold
  - In-app notifications for bids being accepted

- **Professional UI:**
  - iOS-style toggle switches (matching bucket ID page design)
  - Auto-save functionality (no submit button needed)
  - Visual confirmation when preferences are saved
  - Clean, modern design with proper spacing and typography

- **Smart Defaults:**
  - All notifications enabled by default for new users
  - Existing users without preferences get all notifications enabled
  - Graceful handling when preferences table doesn't exist yet

## Installation

### 1. Run the Database Migration

```bash
python run_migration_005.py
```

This creates the `user_preferences` table with the following columns:
- `user_id` (PRIMARY KEY, foreign key to users)
- `email_listing_sold` (INTEGER, default 1)
- `email_bid_filled` (INTEGER, default 1)
- `inapp_listing_sold` (INTEGER, default 1)
- `inapp_bid_filled` (INTEGER, default 1)
- `created_at` (TIMESTAMP)
- `updated_at` (TIMESTAMP)

### 2. Verify Installation

Run the comprehensive test suite:

```bash
python test_notification_preferences.py
```

This tests:
- Database table creation
- Preference saving and retrieval
- Notification service respecting preferences
- Independent toggle functionality
- Default behavior

## Usage

### For Users

1. Navigate to **Account** page
2. Click **Account Details** tab
3. Select **Notification Settings** from the sidebar
4. Toggle preferences on/off as desired
5. Changes are saved automatically

### For Developers

#### Backend Routes

**Get user preferences:**
```python
GET /account/get_preferences
Returns: {
  "success": true,
  "preferences": {
    "email_listing_sold": 1,
    "email_bid_filled": 1,
    "inapp_listing_sold": 1,
    "inapp_bid_filled": 1
  }
}
```

**Update user preferences:**
```python
POST /account/update_preferences
Content-Type: application/json

{
  "email_listing_sold": true,
  "email_bid_filled": false,
  "inapp_listing_sold": true,
  "inapp_bid_filled": true
}

Returns: {
  "success": true,
  "message": "Preferences updated successfully"
}
```

#### Notification Service

The notification service automatically checks user preferences:

```python
from services.notification_service import notify_bid_filled, notify_listing_sold

# Automatically respects user preferences
notify_bid_filled(
    buyer_id=user_id,
    order_id=order_id,
    bid_id=bid_id,
    item_description="2024 1oz Gold Eagle",
    quantity_filled=5,
    price_per_unit=2100.00,
    total_amount=10500.00
)

notify_listing_sold(
    seller_id=seller_id,
    order_id=order_id,
    listing_id=listing_id,
    item_description="2024 1oz Silver Eagle",
    quantity_sold=10,
    price_per_unit=35.00,
    total_amount=350.00,
    shipping_address="123 Main St..."
)
```

## File Structure

```
Metex/
├── migrations/
│   └── 005_create_user_preferences_table.sql    # Database migration
│
├── routes/
│   └── account_routes.py                        # Added preference routes
│
├── services/
│   └── notification_service.py                  # Updated to check preferences
│
├── templates/
│   ├── account.html                             # Added notifications sidebar item
│   └── tabs/
│       └── account_details_tab.html             # Added notification settings section
│
├── static/
│   ├── css/
│   │   └── tabs/
│   │       └── account_details_tab.css          # Added notification styles
│   └── js/
│       └── tabs/
│           └── account_details_tab.js           # Added toggle handlers
│
├── run_migration_005.py                         # Migration runner
├── test_notification_preferences.py             # Comprehensive tests
└── NOTIFICATION_SETTINGS_FEATURE.md            # This file
```

## Technical Details

### Database Schema

```sql
CREATE TABLE user_preferences (
    user_id INTEGER PRIMARY KEY,
    email_listing_sold INTEGER DEFAULT 1,
    email_bid_filled INTEGER DEFAULT 1,
    inapp_listing_sold INTEGER DEFAULT 1,
    inapp_bid_filled INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

### Toggle Design

The toggles use the same iOS-style design from the bucket ID page:
- 50px wide, 28px tall
- Smooth transitions (180ms)
- Blue (#1877ff) when active
- Gray (#d1d5db) when inactive
- White circular slider that moves 22px

### Auto-Save Behavior

- No submit button required
- Changes saved immediately on toggle
- Visual feedback (green success message) appears for 3 seconds
- AJAX request to `/account/update_preferences`
- Graceful error handling with user-friendly alerts

## Testing

The test suite covers:

1. **Migration & Schema** - Verifies table and columns exist
2. **CRUD Operations** - Tests saving/retrieving preferences
3. **Bid Filled Notifications** - Tests preference enforcement
4. **Listing Sold Notifications** - Tests preference enforcement
5. **Default Behavior** - Tests behavior with no preferences set
6. **Independent Toggles** - Verifies all 4 combinations work

Run tests with:
```bash
python test_notification_preferences.py
```

Expected output:
```
=== Test 1: Database Migration and Table Creation ===
✓ user_preferences table exists
✓ All expected columns exist with correct types
✓ Performance index exists
✅ Test 1 PASSED

... (more tests) ...

🎉 ALL TESTS PASSED! 🎉
```

## Future Enhancements

Potential improvements:
- Add more notification types (messages, order updates, etc.)
- Add notification frequency options (immediate, daily digest, weekly)
- Add quiet hours settings
- Add mobile push notification support
- Add notification preview/test feature

## Support

For issues or questions:
1. Check the test suite for expected behavior
2. Verify migration was run successfully
3. Check browser console for JavaScript errors
4. Check Flask logs for backend errors

## Changelog

### Version 1.0.0 (Initial Release)
- Created user_preferences table
- Implemented 4 notification toggles
- Added auto-save functionality
- Updated notification service
- Created comprehensive test suite
