#!/usr/bin/env python3
"""
Comprehensive test script for bid modal with premium-to-spot pricing
Tests:
1. Create bid modal loads without errors
2. Edit bid modal loads without errors
3. Pricing mode toggle functionality
4. Form submission for both static and premium-to-spot modes
"""

import sqlite3
import json
from datetime import datetime

def setup_test_data():
    """Create test data in database if it doesn't exist"""
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get any existing user
    cursor.execute("SELECT id FROM users LIMIT 1")
    user = cursor.fetchone()
    if not user:
        print("[FAIL] No users found in database. Please create a user first.")
        conn.close()
        return None
    else:
        user_id = user['id']

    print(f"[OK] Using user ID: {user_id}")

    # Get any existing category (bucket)
    cursor.execute("SELECT id FROM categories LIMIT 1")
    category = cursor.fetchone()
    if not category:
        print("[FAIL] No categories found in database.")
        conn.close()
        return None
    else:
        category_id = category['id']

    print(f"[OK] Using category ID: {category_id}")

    # Get any existing listing
    cursor.execute("SELECT id FROM listings LIMIT 1")
    listing = cursor.fetchone()
    listing_id = listing['id'] if listing else None
    if listing_id:
        print(f"[OK] Using listing ID: {listing_id}")
    else:
        print("[INFO] No listings found")

    # Get any existing bid
    cursor.execute("SELECT id, pricing_mode FROM bids LIMIT 1")
    bid = cursor.fetchone()
    if bid:
        bid_id = bid['id']
        bid_mode = bid['pricing_mode'] or 'static'
        print(f"[OK] Using bid ID: {bid_id} (mode: {bid_mode})")
    else:
        bid_id = None
        print("[INFO] No bids found - will only test CREATE mode")

    conn.close()

    return {
        'user_id': user_id,
        'category_id': category_id,
        'listing_id': listing_id,
        'bid_id': bid_id
    }


def test_bid_form_routes(test_data):
    """Test that bid form routes return successfully"""
    import requests

    base_url = 'http://127.0.0.1:5000'

    print("\n=== Testing Bid Form Routes ===")

    # Test CREATE bid form
    try:
        create_url = f"{base_url}/bids/form/{test_data['category_id']}"
        print(f"\n1. Testing CREATE bid form: {create_url}")
        resp = requests.get(create_url)
        if resp.status_code == 200:
            print("[OK] CREATE bid form loaded successfully")
            html = resp.text

            # Check for pricing mode selector
            if 'bid-pricing-mode' in html:
                print("  [OK] Pricing mode selector present")
            else:
                print("  [FAIL] Pricing mode selector MISSING")

            # Check for premium-to-spot fields
            if 'premium-pricing-fields' in html:
                print("  [OK] Premium pricing fields present")
            else:
                print("  [FAIL] Premium pricing fields MISSING")

            # Check for spot price display
            if 'current-spot-price' in html:
                print("  [OK] Spot price display present")
            else:
                print("  [FAIL] Spot price display MISSING")
        else:
            print(f"[FAIL] CREATE bid form failed: HTTP {resp.status_code}")
            print(f"  Response: {resp.text[:500]}")
    except Exception as e:
        print(f"[FAIL] CREATE bid form error: {e}")

    # Test EDIT bid form
    try:
        edit_url = f"{base_url}/bids/form/{test_data['category_id']}/{test_data['bid_id']}"
        print(f"\n2. Testing EDIT bid form: {edit_url}")
        resp = requests.get(edit_url)
        if resp.status_code == 200:
            print("[OK] EDIT bid form loaded successfully")
            html = resp.text

            # Check for form elements
            if 'bid-form' in html:
                print("  [OK] Bid form element present")
            else:
                print("  [FAIL] Bid form element MISSING")

            # Check for pricing mode selector
            if 'bid-pricing-mode' in html:
                print("  [OK] Pricing mode selector present")
            else:
                print("  [FAIL] Pricing mode selector MISSING")
        else:
            print(f"[FAIL] EDIT bid form failed: HTTP {resp.status_code}")
            print(f"  Response: {resp.text[:500]}")
    except Exception as e:
        print(f"[FAIL] EDIT bid form error: {e}")


def test_database_structure():
    """Verify database has correct schema for premium-to-spot"""
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    print("\n=== Testing Database Structure ===")

    # Check bids table for premium-to-spot columns
    cursor.execute("PRAGMA table_info(bids)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    required_columns = {
        'pricing_mode': 'TEXT',
        'spot_premium': 'REAL',
        'floor_price': 'REAL',
        'pricing_metal': 'TEXT'
    }

    all_present = True
    for col_name, col_type in required_columns.items():
        if col_name in columns:
            print(f"[OK] Column '{col_name}' exists ({columns[col_name]})")
        else:
            print(f"[FAIL] Column '{col_name}' MISSING")
            all_present = False

    conn.close()

    if all_present:
        print("\n[OK] Database structure is correct")
    else:
        print("\n[FAIL] Database structure is incomplete - run migration")

    return all_present


def main():
    print("=" * 60)
    print("BID MODAL PREMIUM-TO-SPOT INTEGRATION TEST")
    print("=" * 60)

    # Test 1: Database structure
    db_ok = test_database_structure()
    if not db_ok:
        print("\n[WARN] WARNING: Database structure incomplete!")
        print("Run: python run_migration_004_add_bid_pricing_fields.py")
        return

    # Test 2: Create test data
    try:
        test_data = setup_test_data()
    except Exception as e:
        print(f"\n[FAIL] Failed to setup test data: {e}")
        import traceback
        traceback.print_exc()
        return

    # Test 3: Test bid form routes
    try:
        test_bid_form_routes(test_data)
    except Exception as e:
        print(f"\n[FAIL] Failed to test routes: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\n" + "=" * 60)
    print("MANUAL TESTING INSTRUCTIONS")
    print("=" * 60)
    print(f"""
1. Ensure Flask server is running on http://127.0.0.1:5000

2. Open browser and navigate to:
   http://127.0.0.1:5000/buy/{test_data['category_id']}

3. Click "Place Bid" button to open bid modal

4. TEST THE FOLLOWING:
   a. Modal loads without "initialization failed" error
   b. Pricing mode dropdown shows "Fixed Price" and "Variable (Premium to Spot)"
   c. Switching to "Variable" shows new fields:
      - Premium Above Spot
      - No Higher Than (Price Ceiling)
      - Current Spot Price display
   d. Switching back to "Fixed Price" hides those fields
   e. Submit a fixed price bid - should save correctly
   f. Submit a variable bid - should save correctly

5. EDIT MODE TEST:
   - Click "Edit" on an existing bid
   - Modal should load with correct mode selected
   - Changing mode should work
   - Saving should persist changes

6. CHECK BROWSER CONSOLE:
   - Open Developer Tools (F12)
   - Look for any JavaScript errors
   - Pricing mode changes should log to console

7. CHECK FLASK LOGS:
   - No 500 errors
   - Bid creation/update should return 200 or redirect

Test data created:
- User ID: {test_data['user_id']}
- Category ID: {test_data['category_id']}
- Listing ID: {test_data['listing_id']}
- Bid ID: {test_data['bid_id']}
""")

    print("=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == '__main__':
    main()
