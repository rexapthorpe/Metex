"""
Test: Bucket Page Pricing Fix

Verifies that the bucket page loads correctly without crashes after creating
different types of bids (fixed, variable with ceiling, variable without ceiling).

This test addresses the bug where calling get_effective_price() on bids (instead
of get_effective_bid_price()) caused TypeError crashes.
"""

import sqlite3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.pricing_service import get_effective_price, get_effective_bid_price

TEST_DB = 'test_bucket_pricing.db'


def setup_test_db():
    """Create a clean test database"""
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

    conn = sqlite3.connect(TEST_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Create tables
    cursor.execute('''
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE buckets (
            id INTEGER PRIMARY KEY,
            metal TEXT NOT NULL,
            product_type TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE categories (
            id INTEGER PRIMARY KEY,
            bucket_id INTEGER NOT NULL,
            metal TEXT NOT NULL,
            product_type TEXT,
            product_line TEXT,
            weight REAL,
            year INTEGER,
            FOREIGN KEY (bucket_id) REFERENCES buckets(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE bids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            buyer_id INTEGER NOT NULL,
            quantity_requested INTEGER NOT NULL,
            remaining_quantity INTEGER NOT NULL,
            price_per_coin REAL,
            pricing_mode TEXT DEFAULT 'static',
            spot_premium REAL DEFAULT 0,
            ceiling_price REAL,
            pricing_metal TEXT,
            active INTEGER DEFAULT 1,
            status TEXT DEFAULT 'Open',
            FOREIGN KEY (category_id) REFERENCES categories(id),
            FOREIGN KEY (buyer_id) REFERENCES users(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE spot_prices (
            id INTEGER PRIMARY KEY,
            metal TEXT UNIQUE NOT NULL,
            price_usd_per_oz REAL NOT NULL
        )
    ''')

    # Insert test data
    cursor.execute("INSERT INTO users (id, username, email) VALUES (1, 'buyer1', 'buyer1@test.com')")
    cursor.execute("INSERT INTO buckets (id, metal, product_type) VALUES (1, 'silver', 'Coin')")
    cursor.execute('''
        INSERT INTO categories (id, bucket_id, metal, product_type, product_line, weight, year)
        VALUES (1, 1, 'silver', 'Coin', 'American Silver Eagle', 1.0, 2024)
    ''')
    cursor.execute("INSERT INTO spot_prices (metal, price_usd_per_oz) VALUES ('silver', 30.00)")

    conn.commit()
    return conn


def cleanup_test_db():
    """Remove test database"""
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


def print_test_header(test_name):
    print("\n" + "=" * 80)
    print(f"TEST: {test_name}")
    print("=" * 80)


def print_result(test_name, passed, details=""):
    status = "[PASS]" if passed else "[FAIL]"
    print(f"{status}: {test_name}")
    if details:
        print(f"    {details}")


# ============================================================================
# TEST 1: Fixed Bid - get_effective_bid_price should work
# ============================================================================
def test_fixed_bid():
    print_test_header("Fixed Bid - Calculate Effective Price")

    conn = setup_test_db()
    cursor = conn.cursor()

    # Create fixed bid at $35
    cursor.execute('''
        INSERT INTO bids (category_id, buyer_id, quantity_requested, remaining_quantity,
                         price_per_coin, pricing_mode, active, status)
        VALUES (1, 1, 5, 5, 35.00, 'static', 1, 'Open')
    ''')
    bid_id = cursor.lastrowid

    # Fetch bid with all fields (simulating view_bucket query)
    bid_row = cursor.execute('''
        SELECT b.*, c.metal, c.weight, c.product_type
        FROM bids b
        JOIN categories c ON b.category_id = c.id
        WHERE b.id = ?
    ''', (bid_id,)).fetchone()

    try:
        bid_dict = dict(bid_row)
        effective_price = get_effective_bid_price(bid_dict)

        passed = effective_price == 35.00
        print_result(
            "Fixed bid effective price calculation",
            passed,
            f"Expected: $35.00, Got: ${effective_price:.2f}"
        )
    except Exception as e:
        print_result("Fixed bid effective price calculation", False, f"Error: {e}")
        passed = False

    conn.close()
    cleanup_test_db()
    return passed


# ============================================================================
# TEST 2: Variable Bid with Ceiling
# ============================================================================
def test_variable_bid_with_ceiling():
    print_test_header("Variable Bid with Ceiling - Calculate Effective Price")

    conn = setup_test_db()
    cursor = conn.cursor()

    # Create variable bid: spot($30) + premium($5) = $35, ceiling = $32
    # Effective price should be $32 (capped at ceiling)
    cursor.execute('''
        INSERT INTO bids (category_id, buyer_id, quantity_requested, remaining_quantity,
                         price_per_coin, pricing_mode, spot_premium, ceiling_price, pricing_metal,
                         active, status)
        VALUES (1, 1, 5, 5, NULL, 'premium_to_spot', 5.00, 32.00, 'silver', 1, 'Open')
    ''')
    bid_id = cursor.lastrowid

    # Fetch bid with all fields
    bid_row = cursor.execute('''
        SELECT b.*, c.metal, c.weight, c.product_type
        FROM bids b
        JOIN categories c ON b.category_id = c.id
        WHERE b.id = ?
    ''', (bid_id,)).fetchone()

    # Fetch spot prices
    spot_prices_rows = cursor.execute('SELECT metal, price_usd_per_oz FROM spot_prices').fetchall()
    spot_prices = {row['metal'].lower(): row['price_usd_per_oz'] for row in spot_prices_rows}

    try:
        bid_dict = dict(bid_row)
        effective_price = get_effective_bid_price(bid_dict, spot_prices=spot_prices)

        passed = abs(effective_price - 32.00) < 0.01  # Should be capped at ceiling
        print_result(
            "Variable bid with ceiling effective price calculation",
            passed,
            f"Expected: $32.00 (ceiling), Got: ${effective_price:.2f}"
        )
    except Exception as e:
        print_result("Variable bid with ceiling effective price calculation", False, f"Error: {e}")
        passed = False

    conn.close()
    cleanup_test_db()
    return passed


# ============================================================================
# TEST 3: Variable Bid without Ceiling
# ============================================================================
def test_variable_bid_without_ceiling():
    print_test_header("Variable Bid without Ceiling - Calculate Effective Price")

    conn = setup_test_db()
    cursor = conn.cursor()

    # Create variable bid: spot($30) + premium($5) = $35, no ceiling
    # Effective price should be $35
    cursor.execute('''
        INSERT INTO bids (category_id, buyer_id, quantity_requested, remaining_quantity,
                         price_per_coin, pricing_mode, spot_premium, ceiling_price, pricing_metal,
                         active, status)
        VALUES (1, 1, 5, 5, NULL, 'premium_to_spot', 5.00, NULL, 'silver', 1, 'Open')
    ''')
    bid_id = cursor.lastrowid

    # Fetch bid with all fields
    bid_row = cursor.execute('''
        SELECT b.*, c.metal, c.weight, c.product_type
        FROM bids b
        JOIN categories c ON b.category_id = c.id
        WHERE b.id = ?
    ''', (bid_id,)).fetchone()

    # Fetch spot prices
    spot_prices_rows = cursor.execute('SELECT metal, price_usd_per_oz FROM spot_prices').fetchall()
    spot_prices = {row['metal'].lower(): row['price_usd_per_oz'] for row in spot_prices_rows}

    try:
        bid_dict = dict(bid_row)
        effective_price = get_effective_bid_price(bid_dict, spot_prices=spot_prices)

        # spot($30) + premium($5) = $35
        passed = abs(effective_price - 35.00) < 0.01
        print_result(
            "Variable bid without ceiling effective price calculation",
            passed,
            f"Expected: $35.00 (spot + premium), Got: ${effective_price:.2f}"
        )
    except Exception as e:
        print_result("Variable bid without ceiling effective price calculation", False, f"Error: {e}")
        passed = False

    conn.close()
    cleanup_test_db()
    return passed


# ============================================================================
# TEST 4: Variable Bid with Ceiling = 0 (unset)
# ============================================================================
def test_variable_bid_zero_ceiling():
    print_test_header("Variable Bid with Ceiling = 0 - Calculate Effective Price")

    conn = setup_test_db()
    cursor = conn.cursor()

    # Create variable bid: spot($30) + premium($3) = $33, ceiling = 0 (unset)
    # Effective price should be $33
    cursor.execute('''
        INSERT INTO bids (category_id, buyer_id, quantity_requested, remaining_quantity,
                         price_per_coin, pricing_mode, spot_premium, ceiling_price, pricing_metal,
                         active, status)
        VALUES (1, 1, 5, 5, NULL, 'premium_to_spot', 3.00, 0.0, 'silver', 1, 'Open')
    ''')
    bid_id = cursor.lastrowid

    # Fetch bid with all fields
    bid_row = cursor.execute('''
        SELECT b.*, c.metal, c.weight, c.product_type
        FROM bids b
        JOIN categories c ON b.category_id = c.id
        WHERE b.id = ?
    ''', (bid_id,)).fetchone()

    # Fetch spot prices
    spot_prices_rows = cursor.execute('SELECT metal, price_usd_per_oz FROM spot_prices').fetchall()
    spot_prices = {row['metal'].lower(): row['price_usd_per_oz'] for row in spot_prices_rows}

    try:
        bid_dict = dict(bid_row)
        effective_price = get_effective_bid_price(bid_dict, spot_prices=spot_prices)

        # spot($30) + premium($3) = $33 (ceiling=0 means no ceiling)
        passed = abs(effective_price - 33.00) < 0.01
        print_result(
            "Variable bid with ceiling = 0 effective price calculation",
            passed,
            f"Expected: $33.00 (spot + premium, no ceiling), Got: ${effective_price:.2f}"
        )
    except Exception as e:
        print_result("Variable bid with ceiling = 0 effective price calculation", False, f"Error: {e}")
        passed = False

    conn.close()
    cleanup_test_db()
    return passed


# ============================================================================
# TEST 5: Multiple Bids - Simulating Bucket Page Load
# ============================================================================
def test_multiple_bids_bucket_page():
    print_test_header("Multiple Bids - Simulating Bucket Page Load")

    conn = setup_test_db()
    cursor = conn.cursor()

    # Create multiple different types of bids
    # Bid 1: Fixed at $35
    cursor.execute('''
        INSERT INTO bids (category_id, buyer_id, quantity_requested, remaining_quantity,
                         price_per_coin, pricing_mode, active, status)
        VALUES (1, 1, 5, 5, 35.00, 'static', 1, 'Open')
    ''')

    # Bid 2: Variable with ceiling
    cursor.execute('''
        INSERT INTO bids (category_id, buyer_id, quantity_requested, remaining_quantity,
                         price_per_coin, pricing_mode, spot_premium, ceiling_price, pricing_metal,
                         active, status)
        VALUES (1, 1, 3, 3, NULL, 'premium_to_spot', 5.00, 32.00, 'silver', 1, 'Open')
    ''')

    # Bid 3: Variable without ceiling
    cursor.execute('''
        INSERT INTO bids (category_id, buyer_id, quantity_requested, remaining_quantity,
                         price_per_coin, pricing_mode, spot_premium, ceiling_price, pricing_metal,
                         active, status)
        VALUES (1, 1, 2, 2, NULL, 'premium_to_spot', 3.00, NULL, 'silver', 1, 'Open')
    ''')

    # Fetch spot prices
    spot_prices_rows = cursor.execute('SELECT metal, price_usd_per_oz FROM spot_prices').fetchall()
    spot_prices = {row['metal'].lower(): row['price_usd_per_oz'] for row in spot_prices_rows}

    # Simulate bucket page query
    bids_rows = cursor.execute('''
        SELECT b.*, c.metal, c.weight, c.product_type
        FROM bids b
        JOIN categories c ON b.category_id = c.id
        WHERE c.bucket_id = 1 AND b.active = 1
        ORDER BY b.price_per_coin DESC
    ''').fetchall()

    try:
        bids = []
        for bid in bids_rows:
            bid_dict = dict(bid)
            # This is what view_bucket does now (after the fix)
            bid_dict['effective_price'] = get_effective_bid_price(bid_dict, spot_prices=spot_prices)
            bids.append(bid_dict)

        # Verify all bids were processed successfully
        passed = len(bids) == 3

        if passed:
            # Verify effective prices are correct
            # Bid 1: $35 (fixed)
            # Bid 2: $32 (variable with ceiling)
            # Bid 3: $33 (variable without ceiling: 30+3)
            expected_prices = [35.00, 32.00, 33.00]
            actual_prices = [bid['effective_price'] for bid in bids]

            prices_correct = all(
                abs(actual - expected) < 0.01
                for actual, expected in zip(sorted(actual_prices, reverse=True), sorted(expected_prices, reverse=True))
            )

            passed = passed and prices_correct

            print_result(
                "Multiple bids processed without errors",
                passed,
                f"Processed {len(bids)} bids with effective prices: {[f'${p:.2f}' for p in sorted(actual_prices, reverse=True)]}"
            )
        else:
            print_result(
                "Multiple bids processed without errors",
                False,
                f"Expected 3 bids, got {len(bids)}"
            )

    except Exception as e:
        print_result("Multiple bids processed without errors", False, f"Error: {e}")
        import traceback
        traceback.print_exc()
        passed = False

    conn.close()
    cleanup_test_db()
    return passed


# ============================================================================
# RUN ALL TESTS
# ============================================================================
def run_all_tests():
    """Run all test cases and report results"""
    print("\n" + "=" * 80)
    print("BUCKET PAGE PRICING FIX TEST SUITE")
    print("=" * 80)
    print("\nTesting that bucket page loads correctly with different bid types:")
    print("  - Fixed bids")
    print("  - Variable bids with ceiling")
    print("  - Variable bids without ceiling")
    print("  - Multiple bids on same page")

    tests = [
        ("Test 1", test_fixed_bid),
        ("Test 2", test_variable_bid_with_ceiling),
        ("Test 3", test_variable_bid_without_ceiling),
        ("Test 4", test_variable_bid_zero_ceiling),
        ("Test 5", test_multiple_bids_bucket_page),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"[ERROR] in {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    total = len(results)
    passed = sum(1 for _, p in results if p)
    failed = total - passed

    for name, p in results:
        status = "[PASS]" if p else "[FAIL]"
        print(f"{status}: {name}")

    print("\n" + "-" * 80)
    print(f"Total: {total} | Passed: {passed} | Failed: {failed}")
    print("=" * 80)

    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
