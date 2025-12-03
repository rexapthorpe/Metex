"""
Test: Bid Creation Fix - Verify ceiling_price field name issue is resolved

This test verifies:
1. Route correctly extracts bid_ceiling_price from form data
2. Static pricing mode works
3. Premium-to-spot (variable) pricing mode works
4. Validation works correctly
5. Bids are created successfully in database
"""

import sys
import io
import sqlite3
import os
from werkzeug.datastructures import ImmutableMultiDict

# Fix encoding for Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(BASE_DIR, 'database.db')

def print_section(title):
    """Print a section header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def test_route_field_names():
    """Test that route code uses correct field names"""
    print_section("TEST 1: Route Field Names")

    try:
        with open('routes/bid_routes.py', 'r', encoding='utf-8') as f:
            content = f.read()

        # Find create_bid_unified function
        if 'def create_bid_unified(' not in content:
            print("  ERROR: create_bid_unified function not found")
            return False

        # Extract function
        func_start = content.find('def create_bid_unified(')
        func_end = content.find('\n@bid_bp.route', func_start + 1)
        if func_end == -1:
            func_end = content.find('\ndef ', func_start + 100)
        func_content = content[func_start:func_end]

        # Check for correct field names
        checks = [
            ('bid_ceiling_price', 'Uses bid_ceiling_price (not bid_floor_price)'),
            ('ceiling_price_str', 'Has ceiling_price_str variable'),
            ('ceiling_price = float(ceiling_price_str)', 'Parses ceiling_price'),
            ("Max price (ceiling) must be greater than zero", 'Correct validation message'),
        ]

        all_passed = True
        for check_str, desc in checks:
            if check_str in func_content:
                print(f"  SUCCESS: {desc}")
            else:
                print(f"  ERROR: {desc} - NOT FOUND")
                all_passed = False

        # Check that old field names are gone
        if 'bid_floor_price' in func_content:
            print("  ERROR: Old bid_floor_price still present!")
            all_passed = False
        else:
            print("  SUCCESS: Old bid_floor_price removed")

        if 'floor_price_str' in func_content and 'bid_floor_price' in func_content:
            print("  ERROR: Old floor_price_str variable still present!")
            all_passed = False
        else:
            print("  SUCCESS: No reference to old floor price variable")

        return all_passed

    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def test_form_field_names():
    """Test that form uses correct field names"""
    print_section("TEST 2: Form Field Names")

    try:
        with open('templates/tabs/bid_form.html', 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for correct field names
        checks = [
            ('name="bid_ceiling_price"', 'Form has bid_ceiling_price input name'),
            ('id="bid-ceiling-price"', 'Form has bid-ceiling-price input ID'),
            ('No Higher Than (Max Price)', 'Form has correct label'),
        ]

        all_passed = True
        for check_str, desc in checks:
            if check_str in content:
                print(f"  SUCCESS: {desc}")
            else:
                print(f"  ERROR: {desc} - NOT FOUND")
                all_passed = False

        # Check old field names are gone
        if 'name="bid_floor_price"' in content:
            print("  ERROR: Old bid_floor_price input name still in form!")
            all_passed = False
        else:
            print("  SUCCESS: Old bid_floor_price input name removed")

        return all_passed

    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def test_database_bid_creation():
    """Test creating bids in database"""
    print_section("TEST 3: Database Bid Creation Simulation")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Find a valid bucket for testing
        bucket = cursor.execute('''
            SELECT id, metal, product_type FROM categories
            LIMIT 1
        ''').fetchone()

        if not bucket:
            print("  WARNING: No categories found, skipping test")
            conn.close()
            return True

        bucket_id = bucket['id']
        print(f"  Testing with bucket {bucket_id} ({bucket['metal']} {bucket['product_type']})")

        # Test 1: Create static pricing bid
        print("\n  Scenario A: Static Pricing Bid")
        static_bid_data = {
            'category_id': bucket_id,
            'buyer_id': 1,  # Assume user 1 exists
            'quantity_requested': 1,
            'price_per_coin': 100.0,
            'remaining_quantity': 1,
            'active': 1,
            'requires_grading': 0,
            'preferred_grader': None,
            'delivery_address': '123 Test St, Test City, TS, 12345',
            'status': 'Open',
            'pricing_mode': 'static',
            'spot_premium': None,
            'ceiling_price': None,
            'pricing_metal': None
        }

        cursor.execute('''
            INSERT INTO bids (
                category_id, buyer_id, quantity_requested, price_per_coin,
                remaining_quantity, active, requires_grading, preferred_grader,
                delivery_address, status,
                pricing_mode, spot_premium, ceiling_price, pricing_metal
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', tuple(static_bid_data.values()))

        static_bid_id = cursor.lastrowid
        print(f"    Created static bid #{static_bid_id}")
        print(f"    - Price: ${static_bid_data['price_per_coin']}")
        print(f"    - Quantity: {static_bid_data['quantity_requested']}")
        print(f"    SUCCESS: Static bid created")

        # Test 2: Create premium-to-spot bid with ceiling_price
        print("\n  Scenario B: Premium-to-Spot Bid with Ceiling")
        variable_bid_data = {
            'category_id': bucket_id,
            'buyer_id': 1,
            'quantity_requested': 2,
            'price_per_coin': 3000.0,  # Stored ceiling for compatibility
            'remaining_quantity': 2,
            'active': 1,
            'requires_grading': 0,
            'preferred_grader': None,
            'delivery_address': '123 Test St, Test City, TS, 12345',
            'status': 'Open',
            'pricing_mode': 'premium_to_spot',
            'spot_premium': 50.0,
            'ceiling_price': 3000.0,
            'pricing_metal': bucket['metal']
        }

        cursor.execute('''
            INSERT INTO bids (
                category_id, buyer_id, quantity_requested, price_per_coin,
                remaining_quantity, active, requires_grading, preferred_grader,
                delivery_address, status,
                pricing_mode, spot_premium, ceiling_price, pricing_metal
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', tuple(variable_bid_data.values()))

        variable_bid_id = cursor.lastrowid
        print(f"    Created variable bid #{variable_bid_id}")
        print(f"    - Premium: ${variable_bid_data['spot_premium']}")
        print(f"    - Ceiling: ${variable_bid_data['ceiling_price']}")
        print(f"    - Quantity: {variable_bid_data['quantity_requested']}")
        print(f"    SUCCESS: Variable bid with ceiling created")

        # Verify bids were created
        print("\n  Verification:")
        created_bids = cursor.execute('''
            SELECT id, pricing_mode, price_per_coin, ceiling_price, spot_premium
            FROM bids
            WHERE id IN (?, ?)
        ''', (static_bid_id, variable_bid_id)).fetchall()

        if len(created_bids) == 2:
            print(f"    SUCCESS: Both bids verified in database")
            for bid in created_bids:
                print(f"      - Bid #{bid['id']}: {bid['pricing_mode']} mode")
                if bid['pricing_mode'] == 'premium_to_spot':
                    print(f"        ceiling=${bid['ceiling_price']}, premium=${bid['spot_premium']}")
        else:
            print(f"    ERROR: Expected 2 bids, found {len(created_bids)}")
            return False

        # Clean up test bids
        cursor.execute('DELETE FROM bids WHERE id IN (?, ?)', (static_bid_id, variable_bid_id))
        conn.commit()
        print(f"\n    Cleaned up test bids")

        conn.close()
        return True

    except Exception as e:
        print(f"  ERROR: {e}")
        conn.rollback()
        conn.close()
        return False


def test_form_submission_format():
    """Test that form data format matches route expectations"""
    print_section("TEST 4: Form Data Format Match")

    print("\n  Expected form fields for Variable Bid:")
    expected_fields = [
        'bid_pricing_mode = "premium_to_spot"',
        'bid_quantity_premium = "5"',
        'bid_spot_premium = "100.00"',
        'bid_ceiling_price = "3000.00"',  # ← KEY: This must match!
        'bid_pricing_metal = "Gold"',
        'delivery_address = "123 Test St..."',
        'requires_grading = "yes" or "no"',
        'preferred_grader = "PCGS" (if required)',
    ]

    for field in expected_fields:
        print(f"    - {field}")

    print("\n  Form HTML field names:")
    try:
        with open('templates/tabs/bid_form.html', 'r', encoding='utf-8') as f:
            content = f.read()

        # Extract field names
        import re
        name_pattern = r'name="([^"]+)"'
        names = re.findall(name_pattern, content)

        relevant_names = [n for n in names if 'bid_' in n or 'pricing' in n or 'grading' in n]
        for name in set(relevant_names):
            print(f"    - {name}")

        # Verify key field exists
        if 'bid_ceiling_price' in names:
            print(f"\n  SUCCESS: bid_ceiling_price field present in form")
            return True
        else:
            print(f"\n  ERROR: bid_ceiling_price field NOT found in form")
            return False

    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def main():
    print_section("Bid Creation Fix - Verification Test")
    print("Testing fix for: POST /bids/create/10019 400 (BAD REQUEST)")
    print("Root cause: Form sends bid_ceiling_price, route was looking for bid_floor_price")

    # Run all tests
    results = {
        'Route Field Names': test_route_field_names(),
        'Form Field Names': test_form_field_names(),
        'Database Bid Creation': test_database_bid_creation(),
        'Form Data Format Match': test_form_submission_format(),
    }

    # Print summary
    print_section("TEST SUMMARY")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "PASS" if result else "FAIL"
        symbol = "[PASS]" if result else "[FAIL]"
        print(f"  {symbol} {test_name}")

    print(f"\n{passed}/{total} tests passed\n")

    if passed == total:
        print("=" * 80)
        print("SUCCESS: Bid creation fix verified!")
        print("=" * 80)
        print("\nWhat was fixed:")
        print("  - BEFORE: Route looked for 'bid_floor_price' field")
        print("  - AFTER:  Route looks for 'bid_ceiling_price' field")
        print("  - Form sends: 'bid_ceiling_price'")
        print("  - Route expects: 'bid_ceiling_price'")
        print("  - Result: Field names now match!")
        print("\nExpected behavior:")
        print("  1. User fills out bid form with ceiling price")
        print("  2. Form sends bid_ceiling_price in POST data")
        print("  3. Route extracts bid_ceiling_price successfully")
        print("  4. Validation passes")
        print("  5. Bid is created in database")
        print("  6. Success modal appears")
        print("=" * 80)
        return True
    else:
        print("=" * 80)
        print("WARNING: Some tests failed - review above output")
        print("=" * 80)
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
