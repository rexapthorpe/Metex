"""
Comprehensive Test: Variable Bid Ceiling Price Refactoring

This test verifies that the refactoring from floor_price to ceiling_price
for variable bids is complete and working correctly.

Tests:
1. Database migration completed
2. Forms use ceiling_price
3. Routes handle ceiling_price
4. Pricing service calculates effective bid price with ceiling
5. Auto-matching respects ceiling
6. Modals display ceiling_price correctly
"""

import sys
import io
import sqlite3
import os

# Fix encoding for Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(BASE_DIR, 'database.db')

def print_section(title):
    """Print a section header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def test_database_schema():
    """Test that database has ceiling_price column"""
    print_section("TEST 1: Database Schema")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(bids)")
        columns = {col[1]: col[2] for col in cursor.fetchall()}

        if 'ceiling_price' not in columns:
            print("ERROR: ceiling_price column not found in bids table")
            return False
        print("  SUCCESS: ceiling_price column exists")
        print(f"    Type: {columns['ceiling_price']}")

        # Check for data
        cursor.execute("SELECT COUNT(*) FROM bids WHERE ceiling_price IS NOT NULL")
        count = cursor.fetchone()[0]
        print(f"    {count} bids have ceiling_price set")

        conn.close()
        return True

    except Exception as e:
        print(f"  ERROR: {e}")
        conn.close()
        return False


def test_forms():
    """Test that forms use ceiling_price terminology"""
    print_section("TEST 2: Bid Form Labels")

    try:
        with open('templates/tabs/bid_form.html', 'r', encoding='utf-8') as f:
            content = f.read()

        checks = [
            ('No Higher Than (Max Price)', 'Max price label found'),
            ('bid-ceiling-price', 'ceiling price input ID found'),
            ('bid_ceiling_price', 'ceiling price input name found'),
            ('Maximum price ceiling', 'ceiling hint text found'),
            ("won't auto-fill if spot + premium exceeds", 'correct ceiling behavior description'),
        ]

        all_passed = True
        for check_str, desc in checks:
            if check_str in content:
                print(f"  SUCCESS: {desc}")
            else:
                print(f"  ERROR: {desc} NOT FOUND")
                all_passed = False

        # Check that old floor terminology is gone
        if 'No Lower Than (Price Floor)' in content:
            print("  ERROR: Old floor price label still present!")
            all_passed = False
        else:
            print("  SUCCESS: Old floor price label removed")

        return all_passed

    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def test_routes():
    """Test that routes use ceiling_price"""
    print_section("TEST 3: Route Logic")

    try:
        with open('routes/bid_routes.py', 'r', encoding='utf-8') as f:
            content = f.read()

        checks = [
            ('bid_ceiling_price', 'extracts ceiling_price from form'),
            ('ceiling_price_str', 'has ceiling_price variable'),
            ('ceiling_price = float', 'parses ceiling_price'),
            ('ceiling_price,', 'passes ceiling_price to database'),
            ('get_effective_bid_price', 'uses bid pricing function'),
        ]

        all_passed = True
        for check_str, desc in checks:
            count = content.count(check_str)
            if count > 0:
                print(f"  SUCCESS: {desc} ({count} occurrences)")
            else:
                print(f"  ERROR: {desc} NOT FOUND")
                all_passed = False

        # Check validation message
        if 'Max price (ceiling) must be greater than zero' in content:
            print("  SUCCESS: Correct validation message")
        else:
            print("  WARNING: Validation message not updated")

        return all_passed

    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def test_pricing_service():
    """Test that pricing service has bid ceiling logic"""
    print_section("TEST 4: Pricing Service")

    try:
        with open('services/pricing_service.py', 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for get_effective_bid_price function
        if 'def get_effective_bid_price(' not in content:
            print("  ERROR: get_effective_bid_price function not found")
            return False
        print("  SUCCESS: get_effective_bid_price function exists")

        # Check for ceiling logic
        if 'ceiling_price = bid.get' in content:
            print("  SUCCESS: Extracts ceiling_price from bid")
        else:
            print("  ERROR: Does not extract ceiling_price")
            return False

        if 'min(computed_price, ceiling_price)' in content:
            print("  SUCCESS: Enforces ceiling with min()")
        else:
            print("  ERROR: Does not enforce ceiling correctly")
            return False

        # Check comment explains difference
        if 'capped at ceiling_price (maximum)' in content:
            print("  SUCCESS: Documentation explains ceiling")
        else:
            print("  WARNING: Missing documentation")

        return True

    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def test_auto_matching():
    """Test that auto-matching uses effective bid price"""
    print_section("TEST 5: Auto-Matching Logic")

    try:
        with open('routes/bid_routes.py', 'r', encoding='utf-8') as f:
            content = f.read()

        # Find auto_match_bid_to_listings function
        if 'def auto_match_bid_to_listings(' not in content:
            print("  ERROR: auto_match_bid_to_listings function not found")
            return False
        print("  SUCCESS: auto_match_bid_to_listings function exists")

        # Extract function
        func_start = content.find('def auto_match_bid_to_listings(')
        func_end = content.find('\ndef ', func_start + 1)
        if func_end == -1:
            func_end = len(content)
        func_content = content[func_start:func_end]

        # Check for effective price calculation
        if 'get_effective_bid_price(' in func_content:
            print("  SUCCESS: Calculates effective bid price")
        else:
            print("  ERROR: Does not calculate effective bid price")
            return False

        if 'c.metal, c.weight' in func_content:
            print("  SUCCESS: Joins with categories to get metal and weight")
        else:
            print("  ERROR: Missing metal/weight data for price calculation")
            return False

        if 'effective_bid_price = get_effective_bid_price(bid_dict)' in func_content:
            print("  SUCCESS: Stores effective bid price")
        else:
            print("  WARNING: Variable name might be different")

        return True

    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def test_modals():
    """Test that modals display ceiling_price"""
    print_section("TEST 6: Modal Templates")

    try:
        with open('templates/modals/bid_confirm_modal.html', 'r', encoding='utf-8') as f:
            content = f.read()

        checks = [
            ('Max Price (Ceiling)', 'confirmation modal has ceiling label'),
            ('bid-confirm-ceiling', 'confirmation modal has ceiling element'),
            ('success-bid-ceiling', 'success modal has ceiling element'),
            ('success-ceiling-row', 'success modal has ceiling row'),
        ]

        all_passed = True
        for check_str, desc in checks:
            if check_str in content:
                print(f"  SUCCESS: {desc}")
            else:
                print(f"  ERROR: {desc} NOT FOUND")
                all_passed = False

        # Check old floor terminology is gone
        if 'Floor Price (Minimum)' in content:
            print("  ERROR: Old floor price label still in modal!")
            all_passed = False
        else:
            print("  SUCCESS: Old floor price label removed from modal")

        return all_passed

    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def test_javascript():
    """Test that JavaScript uses ceiling_price"""
    print_section("TEST 7: JavaScript Files")

    all_passed = True

    for js_file in ['static/js/modals/bid_modal.js', 'static/js/modals/bid_confirm_modal.js']:
        try:
            with open(js_file, 'r', encoding='utf-8') as f:
                content = f.read()

            print(f"\n  Checking {js_file}:")

            if 'bid-ceiling-price' in content:
                print(f"    SUCCESS: Uses bid-ceiling-price ID")
            elif 'bid-floor-price' in content:
                print(f"    ERROR: Still uses bid-floor-price ID")
                all_passed = False

            if 'ceilingPrice' in content:
                print(f"    SUCCESS: Uses ceilingPrice variable")
            elif 'floorPrice' in content:
                print(f"    ERROR: Still uses floorPrice variable")
                all_passed = False

        except Exception as e:
            print(f"    ERROR: {e}")
            all_passed = False

    return all_passed


def main():
    print_section("Variable Bid Ceiling Price - Complete Verification")

    # Run all tests
    results = {
        'Database Schema': test_database_schema(),
        'Bid Forms': test_forms(),
        'Route Logic': test_routes(),
        'Pricing Service': test_pricing_service(),
        'Auto-Matching': test_auto_matching(),
        'Modal Templates': test_modals(),
        'JavaScript Files': test_javascript(),
    }

    # Print summary
    print_section("TEST SUMMARY")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "PASS" if result else "FAIL"
        symbol = "✓" if result else "✗"
        print(f"  {symbol} {test_name}: {status}")

    print(f"\n{passed}/{total} tests passed\n")

    if passed == total:
        print("=" * 80)
        print("SUCCESS: All refactoring completed correctly!")
        print("=" * 80)
        print("\nSummary of Changes:")
        print("  - Database: floor_price -> ceiling_price")
        print("  - Forms: 'No Lower Than (Floor)' -> 'No Higher Than (Max Price)'")
        print("  - Routes: Extracts and validates ceiling_price")
        print("  - Pricing: get_effective_bid_price enforces ceiling with min()")
        print("  - Auto-matching: Uses effective bid price for matching")
        print("  - Modals: Display 'Max Price (Ceiling)'")
        print("  - JavaScript: Updated to use ceiling terminology")
        print("\nExpected Behavior:")
        print("  - Variable bids set a MAXIMUM price (ceiling)")
        print("  - Effective price = min(spot + premium, ceiling)")
        print("  - Bids only auto-fill when listing price <= effective bid price")
        print("  - User sees clear 'Max Price' labels throughout UI")
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
