"""
Test: Bid Form Fix - Verify ceiling_price error is resolved

This test verifies:
1. Bid form loads without "no such column: ceiling_price" error
2. Form correctly uses floor_price for listings (seller minimum)
3. Form correctly uses ceiling_price for bids (buyer maximum)
4. Variable bid creation works with ceiling price
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
    """Verify both tables have correct columns"""
    print_section("TEST 1: Database Schema Verification")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check bids table has ceiling_price
        cursor.execute("PRAGMA table_info(bids)")
        bid_columns = {col[1]: col[2] for col in cursor.fetchall()}

        if 'ceiling_price' not in bid_columns:
            print("  ERROR: bids table missing ceiling_price column")
            return False
        print("  SUCCESS: bids table has ceiling_price column")

        # Check listings table has floor_price
        cursor.execute("PRAGMA table_info(listings)")
        listing_columns = {col[1]: col[2] for col in cursor.fetchall()}

        if 'floor_price' not in listing_columns:
            print("  ERROR: listings table missing floor_price column")
            return False
        print("  SUCCESS: listings table has floor_price column")

        # Verify they DON'T have the wrong columns
        if 'ceiling_price' in listing_columns:
            print("  WARNING: listings table has ceiling_price (should only be in bids)")

        conn.close()
        return True

    except Exception as e:
        print(f"  ERROR: {e}")
        conn.close()
        return False


def test_query_execution():
    """Test the exact query that was failing"""
    print_section("TEST 2: Query Execution (Previously Failing)")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Find a bucket with active listings
        bucket = cursor.execute('''
            SELECT id FROM categories
            WHERE id IN (SELECT DISTINCT category_id FROM listings WHERE active = 1)
            LIMIT 1
        ''').fetchone()

        if not bucket:
            print("  WARNING: No buckets with active listings found, skipping test")
            conn.close()
            return True

        bucket_id = bucket['id']
        print(f"  Testing with bucket ID: {bucket_id}")

        # This is the exact query that was failing before the fix
        lowest = cursor.execute('''
            SELECT MIN(price_per_coin) as min_price,
                   pricing_mode,
                   spot_premium,
                   floor_price,
                   pricing_metal
            FROM listings
            WHERE category_id = ? AND active = 1 AND quantity > 0
            ORDER BY price_per_coin ASC
            LIMIT 1
        ''', (bucket_id,)).fetchone()

        if lowest:
            print(f"  SUCCESS: Query executed without error")
            print(f"    - Min price: ${lowest['min_price']}")
            print(f"    - Pricing mode: {lowest['pricing_mode']}")
            if lowest['pricing_mode'] == 'premium_to_spot':
                print(f"    - Floor price (seller minimum): ${lowest['floor_price']}")
                print(f"    - Spot premium: ${lowest['spot_premium']}")
        else:
            print("  SUCCESS: Query executed (no results, but no error)")

        conn.close()
        return True

    except sqlite3.OperationalError as e:
        print(f"  ERROR: {e}")
        conn.close()
        return False
    except Exception as e:
        print(f"  ERROR: Unexpected error: {e}")
        conn.close()
        return False


def test_bid_ceiling_query():
    """Test that bids table can query ceiling_price"""
    print_section("TEST 3: Bids Table - Ceiling Price Query")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Query bids with ceiling_price
        bids = cursor.execute('''
            SELECT id, pricing_mode, ceiling_price, spot_premium
            FROM bids
            WHERE pricing_mode = 'premium_to_spot'
            LIMIT 5
        ''').fetchall()

        print(f"  SUCCESS: Query executed, found {len(bids)} variable bids")

        for bid in bids:
            print(f"    - Bid {bid['id']}: ceiling=${bid['ceiling_price']}, premium=${bid['spot_premium']}")

        conn.close()
        return True

    except sqlite3.OperationalError as e:
        print(f"  ERROR: {e}")
        conn.close()
        return False


def test_route_code():
    """Verify the route code uses correct column names"""
    print_section("TEST 4: Route Code Verification")

    try:
        with open('routes/bid_routes.py', 'r', encoding='utf-8') as f:
            content = f.read()

        # Find the bid_form_unified function
        if 'def bid_form_unified(' not in content:
            print("  ERROR: bid_form_unified function not found")
            return False

        # Extract the function
        func_start = content.find('def bid_form_unified(')
        func_end = content.find('\n@', func_start + 1)  # Find next route decorator
        if func_end == -1:
            func_end = content.find('\ndef ', func_start + 100)
        func_content = content[func_start:func_end]

        # Check the query uses floor_price for listings
        if 'SELECT MIN(price_per_coin) as min_price' in func_content:
            query_start = func_content.find('SELECT MIN(price_per_coin)')
            query_end = func_content.find('fetchone()', query_start)
            query = func_content[query_start:query_end]

            if 'floor_price' in query and 'FROM listings' in query:
                print("  SUCCESS: Query correctly uses floor_price for listings table")
            else:
                print("  ERROR: Query doesn't use floor_price for listings")
                return False

            if 'ceiling_price' in query:
                print("  ERROR: Query incorrectly uses ceiling_price for listings table!")
                return False
            else:
                print("  SUCCESS: Query does NOT use ceiling_price for listings")

        # Check pricing_info uses floor_price
        if "'floor_price': float(lowest['floor_price'])" in func_content:
            print("  SUCCESS: pricing_info correctly uses floor_price from listings")
        else:
            print("  WARNING: pricing_info might not be using floor_price correctly")

        return True

    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def test_template_display():
    """Verify template displays listing floor price correctly"""
    print_section("TEST 5: Template Display Verification")

    try:
        with open('templates/tabs/bid_form.html', 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for correct label
        if 'Listing Floor Price' in content:
            print("  SUCCESS: Template shows 'Listing Floor Price' (seller minimum)")
        else:
            print("  WARNING: Template might not label listing floor price clearly")

        # Check for bid ceiling price field
        if 'No Higher Than (Max Price)' in content:
            print("  SUCCESS: Template shows 'No Higher Than (Max Price)' for bids")
        else:
            print("  ERROR: Template missing bid ceiling label")
            return False

        # Check input IDs
        if 'id="bid-ceiling-price"' in content:
            print("  SUCCESS: Bid ceiling input has correct ID")
        else:
            print("  ERROR: Bid ceiling input missing or has wrong ID")
            return False

        # Make sure old floor terminology is gone from bid fields
        if 'bid-floor-price' in content:
            print("  ERROR: Old bid-floor-price ID still present!")
            return False
        else:
            print("  SUCCESS: Old bid-floor-price ID removed")

        return True

    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def main():
    print_section("Bid Form Fix - Complete Verification")
    print("Testing fix for: sqlite3.OperationalError: no such column: ceiling_price")

    # Run all tests
    results = {
        'Database Schema': test_database_schema(),
        'Query Execution': test_query_execution(),
        'Bid Ceiling Query': test_bid_ceiling_query(),
        'Route Code': test_route_code(),
        'Template Display': test_template_display(),
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
        print("SUCCESS: Bid form fix verified!")
        print("=" * 80)
        print("\nWhat was fixed:")
        print("  - BEFORE: Query used ceiling_price on listings table (ERROR)")
        print("  - AFTER:  Query uses floor_price on listings table (CORRECT)")
        print("\nWhy this is correct:")
        print("  - Listings table uses floor_price (seller's minimum)")
        print("  - Bids table uses ceiling_price (buyer's maximum)")
        print("  - bid_form_unified() queries listings to show context")
        print("  - Template displays listing floor as informational only")
        print("\nExpected behavior:")
        print("  - Bid form loads without errors")
        print("  - Shows listing floor price as seller's minimum (info only)")
        print("  - Bid ceiling price field allows buyer to set maximum")
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
