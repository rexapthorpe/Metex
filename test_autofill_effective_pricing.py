"""
Comprehensive Test Suite for Autofill with Effective Pricing

This test verifies that the autofill matching logic correctly:
1. Calculates effective prices for both bids and listings
2. Uses ceilings and floors as blockers, not price setters
3. Only matches when effective prices overlap
4. Works correctly for all combinations of fixed/variable pricing
"""

import sqlite3
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.pricing_service import get_effective_price, get_effective_bid_price
from services.spot_price_service import get_current_spot_prices
from routes.bid_routes import auto_match_bid_to_listings

# Test database
TEST_DB = 'test_autofill.db'


def setup_test_db():
    """Create a clean test database with categories, users, and spot prices"""
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
        CREATE TABLE categories (
            id INTEGER PRIMARY KEY,
            metal TEXT NOT NULL,
            product_type TEXT,
            product_line TEXT,
            weight REAL,
            year INTEGER
        )
    ''')

    cursor.execute('''
        CREATE TABLE bids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            buyer_id INTEGER NOT NULL,
            quantity_requested INTEGER NOT NULL,
            remaining_quantity INTEGER NOT NULL,
            quantity_fulfilled INTEGER DEFAULT 0,
            price_per_coin REAL,
            pricing_mode TEXT DEFAULT 'static',
            spot_premium REAL DEFAULT 0,
            ceiling_price REAL,
            pricing_metal TEXT,
            delivery_address TEXT,
            requires_grading INTEGER DEFAULT 0,
            preferred_grader TEXT,
            active INTEGER DEFAULT 1,
            status TEXT DEFAULT 'Open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories(id),
            FOREIGN KEY (buyer_id) REFERENCES users(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            seller_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            price_per_coin REAL,
            pricing_mode TEXT DEFAULT 'static',
            spot_premium REAL DEFAULT 0,
            floor_price REAL,
            pricing_metal TEXT,
            graded INTEGER DEFAULT 0,
            grading_service TEXT,
            photo_filename TEXT,
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories(id),
            FOREIGN KEY (seller_id) REFERENCES users(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            buyer_id INTEGER NOT NULL,
            total_price REAL NOT NULL,
            shipping_address TEXT,
            status TEXT DEFAULT 'Pending Shipment',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (buyer_id) REFERENCES users(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            listing_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            price_each REAL NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (listing_id) REFERENCES listings(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE spot_prices (
            id INTEGER PRIMARY KEY,
            metal TEXT UNIQUE NOT NULL,
            price_usd_per_oz REAL NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Insert test users
    cursor.execute("INSERT INTO users (id, username, email) VALUES (1, 'buyer1', 'buyer1@test.com')")
    cursor.execute("INSERT INTO users (id, username, email) VALUES (2, 'seller1', 'seller1@test.com')")
    cursor.execute("INSERT INTO users (id, username, email) VALUES (3, 'seller2', 'seller2@test.com')")

    # Insert test category (1 oz Silver Eagle)
    cursor.execute('''
        INSERT INTO categories (id, metal, product_type, product_line, weight, year)
        VALUES (1, 'silver', 'Coin', 'American Silver Eagle', 1.0, 2024)
    ''')

    # Insert spot prices
    cursor.execute("INSERT INTO spot_prices (metal, price_usd_per_oz) VALUES ('silver', 30.00)")
    cursor.execute("INSERT INTO spot_prices (metal, price_usd_per_oz) VALUES ('gold', 2000.00)")

    conn.commit()
    return conn


def cleanup_test_db():
    """Remove test database"""
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


def print_test_header(test_name):
    """Print formatted test header"""
    print("\n" + "=" * 80)
    print(f"TEST: {test_name}")
    print("=" * 80)


def print_result(test_name, passed, details=""):
    """Print test result"""
    status = "[PASS]" if passed else "[FAIL]"
    print(f"{status}: {test_name}")
    if details:
        print(f"    {details}")


# ============================================================================
# TEST 1: Fixed Bid vs Fixed Listing - Should Match
# ============================================================================
def test_fixed_bid_fixed_listing_match():
    print_test_header("Fixed Bid ($35) vs Fixed Listing ($33) - Should Match")

    conn = setup_test_db()
    cursor = conn.cursor()

    # Create fixed listing at $33
    cursor.execute('''
        INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, pricing_mode, active)
        VALUES (1, 2, 10, 33.00, 'static', 1)
    ''')

    # Create fixed bid at $35
    cursor.execute('''
        INSERT INTO bids (category_id, buyer_id, quantity_requested, remaining_quantity,
                         price_per_coin, pricing_mode, delivery_address, active, status)
        VALUES (1, 1, 5, 5, 35.00, 'static', '123 Main St', 1, 'Open')
    ''')
    bid_id = cursor.lastrowid

    # Test autofill
    result = auto_match_bid_to_listings(bid_id, cursor)
    conn.commit()

    # Verify match occurred
    bid = cursor.execute('SELECT * FROM bids WHERE id = ?', (bid_id,)).fetchone()
    orders = cursor.execute('SELECT * FROM orders WHERE buyer_id = 1').fetchall()

    passed = (
        result['filled_quantity'] == 5 and
        result['orders_created'] == 1 and
        bid['status'] == 'Filled'
    )

    print_result(
        "Fixed bid at $35 should match fixed listing at $33",
        passed,
        f"Filled: {result['filled_quantity']}/5, Orders: {result['orders_created']}, Status: {bid['status']}"
    )

    conn.close()
    cleanup_test_db()
    return passed


# ============================================================================
# TEST 2: Fixed Bid vs Fixed Listing - Should NOT Match
# ============================================================================
def test_fixed_bid_fixed_listing_no_match():
    print_test_header("Fixed Bid ($30) vs Fixed Listing ($33) - Should NOT Match")

    conn = setup_test_db()
    cursor = conn.cursor()

    # Create fixed listing at $33
    cursor.execute('''
        INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, pricing_mode, active)
        VALUES (1, 2, 10, 33.00, 'static', 1)
    ''')

    # Create fixed bid at $30 (too low)
    cursor.execute('''
        INSERT INTO bids (category_id, buyer_id, quantity_requested, remaining_quantity,
                         price_per_coin, pricing_mode, delivery_address, active, status)
        VALUES (1, 1, 5, 5, 30.00, 'static', '123 Main St', 1, 'Open')
    ''')
    bid_id = cursor.lastrowid

    # Test autofill
    result = auto_match_bid_to_listings(bid_id, cursor)
    conn.commit()

    # Verify NO match occurred
    bid = cursor.execute('SELECT * FROM bids WHERE id = ?', (bid_id,)).fetchone()

    passed = (
        result['filled_quantity'] == 0 and
        result['orders_created'] == 0 and
        bid['status'] == 'Open'
    )

    print_result(
        "Fixed bid at $30 should NOT match fixed listing at $33",
        passed,
        f"Filled: {result['filled_quantity']}/5, Orders: {result['orders_created']}, Status: {bid['status']}"
    )

    conn.close()
    cleanup_test_db()
    return passed


# ============================================================================
# TEST 3: Variable Bid (with ceiling) vs Fixed Listing
# ============================================================================
def test_variable_bid_ceiling_blocks_match():
    print_test_header("Variable Bid (spot+$5=$35, ceiling=$32) vs Fixed Listing ($33) - Should NOT Match")

    conn = setup_test_db()
    cursor = conn.cursor()

    # Create fixed listing at $33
    cursor.execute('''
        INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, pricing_mode, active)
        VALUES (1, 2, 10, 33.00, 'static', 1)
    ''')

    # Create variable bid: spot($30) + premium($5) = $35, but ceiling = $32
    # Effective bid price should be $32 (capped at ceiling)
    cursor.execute('''
        INSERT INTO bids (category_id, buyer_id, quantity_requested, remaining_quantity,
                         price_per_coin, pricing_mode, spot_premium, ceiling_price, pricing_metal,
                         delivery_address, active, status)
        VALUES (1, 1, 5, 5, NULL, 'premium_to_spot', 5.00, 32.00, 'silver', '123 Main St', 1, 'Open')
    ''')
    bid_id = cursor.lastrowid

    # Test autofill
    result = auto_match_bid_to_listings(bid_id, cursor)
    conn.commit()

    # Verify NO match (effective bid $32 < listing $33)
    bid = cursor.execute('SELECT * FROM bids WHERE id = ?', (bid_id,)).fetchone()

    passed = (
        result['filled_quantity'] == 0 and
        result['orders_created'] == 0 and
        bid['status'] == 'Open'
    )

    print_result(
        "Variable bid with ceiling should NOT match when ceiling < listing price",
        passed,
        f"Effective bid: $32 (capped at ceiling), Listing: $33 | Filled: {result['filled_quantity']}/5"
    )

    conn.close()
    cleanup_test_db()
    return passed


# ============================================================================
# TEST 4: Variable Bid (no ceiling blocking) vs Fixed Listing - Should Match
# ============================================================================
def test_variable_bid_no_ceiling_block():
    print_test_header("Variable Bid (spot+$5=$35, ceiling=$40) vs Fixed Listing ($33) - Should Match")

    conn = setup_test_db()
    cursor = conn.cursor()

    # Create fixed listing at $33
    cursor.execute('''
        INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, pricing_mode, active)
        VALUES (1, 2, 10, 33.00, 'static', 1)
    ''')

    # Create variable bid: spot($30) + premium($5) = $35, ceiling = $40
    # Effective bid price should be $35 (not capped)
    cursor.execute('''
        INSERT INTO bids (category_id, buyer_id, quantity_requested, remaining_quantity,
                         price_per_coin, pricing_mode, spot_premium, ceiling_price, pricing_metal,
                         delivery_address, active, status)
        VALUES (1, 1, 5, 5, NULL, 'premium_to_spot', 5.00, 40.00, 'silver', '123 Main St', 1, 'Open')
    ''')
    bid_id = cursor.lastrowid

    # Test autofill
    result = auto_match_bid_to_listings(bid_id, cursor)
    conn.commit()

    # Verify match (effective bid $35 > listing $33)
    bid = cursor.execute('SELECT * FROM bids WHERE id = ?', (bid_id,)).fetchone()

    passed = (
        result['filled_quantity'] == 5 and
        result['orders_created'] == 1 and
        bid['status'] == 'Filled'
    )

    print_result(
        "Variable bid should match when effective price > listing price",
        passed,
        f"Effective bid: $35, Listing: $33 | Filled: {result['filled_quantity']}/5"
    )

    conn.close()
    cleanup_test_db()
    return passed


# ============================================================================
# TEST 5: Fixed Bid vs Variable Listing (floor blocks)
# ============================================================================
def test_fixed_bid_vs_variable_listing_floor_blocks():
    print_test_header("Fixed Bid ($33) vs Variable Listing (spot+$2=$32, floor=$35) - Should NOT Match")

    conn = setup_test_db()
    cursor = conn.cursor()

    # Create variable listing: spot($30) + premium($2) = $32, but floor = $35
    # Effective listing price should be $35 (floor enforced)
    cursor.execute('''
        INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, pricing_mode,
                            spot_premium, floor_price, pricing_metal, active)
        VALUES (1, 2, 10, NULL, 'premium_to_spot', 2.00, 35.00, 'silver', 1)
    ''')

    # Create fixed bid at $33
    cursor.execute('''
        INSERT INTO bids (category_id, buyer_id, quantity_requested, remaining_quantity,
                         price_per_coin, pricing_mode, delivery_address, active, status)
        VALUES (1, 1, 5, 5, 33.00, 'static', '123 Main St', 1, 'Open')
    ''')
    bid_id = cursor.lastrowid

    # Test autofill
    result = auto_match_bid_to_listings(bid_id, cursor)
    conn.commit()

    # Verify NO match (bid $33 < effective listing $35)
    bid = cursor.execute('SELECT * FROM bids WHERE id = ?', (bid_id,)).fetchone()

    passed = (
        result['filled_quantity'] == 0 and
        result['orders_created'] == 0 and
        bid['status'] == 'Open'
    )

    print_result(
        "Fixed bid should NOT match variable listing when floor makes it too expensive",
        passed,
        f"Bid: $33, Effective listing: $35 (floor enforced) | Filled: {result['filled_quantity']}/5"
    )

    conn.close()
    cleanup_test_db()
    return passed


# ============================================================================
# TEST 6: Fixed Bid vs Variable Listing (no floor blocking) - Should Match
# ============================================================================
def test_fixed_bid_vs_variable_listing_no_floor_block():
    print_test_header("Fixed Bid ($35) vs Variable Listing (spot+$2=$32, floor=$30) - Should Match")

    conn = setup_test_db()
    cursor = conn.cursor()

    # Create variable listing: spot($30) + premium($2) = $32, floor = $30
    # Effective listing price should be $32 (computed price > floor)
    cursor.execute('''
        INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, pricing_mode,
                            spot_premium, floor_price, pricing_metal, active)
        VALUES (1, 2, 10, NULL, 'premium_to_spot', 2.00, 30.00, 'silver', 1)
    ''')

    # Create fixed bid at $35
    cursor.execute('''
        INSERT INTO bids (category_id, buyer_id, quantity_requested, remaining_quantity,
                         price_per_coin, pricing_mode, delivery_address, active, status)
        VALUES (1, 1, 5, 5, 35.00, 'static', '123 Main St', 1, 'Open')
    ''')
    bid_id = cursor.lastrowid

    # Test autofill
    result = auto_match_bid_to_listings(bid_id, cursor)
    conn.commit()

    # Verify match (bid $35 > effective listing $32)
    bid = cursor.execute('SELECT * FROM bids WHERE id = ?', (bid_id,)).fetchone()

    passed = (
        result['filled_quantity'] == 5 and
        result['orders_created'] == 1 and
        bid['status'] == 'Filled'
    )

    print_result(
        "Fixed bid should match variable listing when effective prices overlap",
        passed,
        f"Bid: $35, Effective listing: $32 | Filled: {result['filled_quantity']}/5"
    )

    conn.close()
    cleanup_test_db()
    return passed


# ============================================================================
# TEST 7: Variable Bid vs Variable Listing - Both Blocked by Ceiling/Floor
# ============================================================================
def test_variable_vs_variable_both_blocked():
    print_test_header("Variable Bid (ceiling=$32) vs Variable Listing (floor=$35) - Should NOT Match")

    conn = setup_test_db()
    cursor = conn.cursor()

    # Create variable listing: spot+$5=$35, floor=$35
    # Effective listing price = $35
    cursor.execute('''
        INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, pricing_mode,
                            spot_premium, floor_price, pricing_metal, active)
        VALUES (1, 2, 10, NULL, 'premium_to_spot', 5.00, 35.00, 'silver', 1)
    ''')

    # Create variable bid: spot+$5=$35, ceiling=$32
    # Effective bid price = $32 (capped at ceiling)
    cursor.execute('''
        INSERT INTO bids (category_id, buyer_id, quantity_requested, remaining_quantity,
                         price_per_coin, pricing_mode, spot_premium, ceiling_price, pricing_metal,
                         delivery_address, active, status)
        VALUES (1, 1, 5, 5, NULL, 'premium_to_spot', 5.00, 32.00, 'silver', '123 Main St', 1, 'Open')
    ''')
    bid_id = cursor.lastrowid

    # Test autofill
    result = auto_match_bid_to_listings(bid_id, cursor)
    conn.commit()

    # Verify NO match (effective bid $32 < effective listing $35)
    bid = cursor.execute('SELECT * FROM bids WHERE id = ?', (bid_id,)).fetchone()

    passed = (
        result['filled_quantity'] == 0 and
        result['orders_created'] == 0 and
        bid['status'] == 'Open'
    )

    print_result(
        "Variable bid and listing should NOT match when ceiling/floor prevent overlap",
        passed,
        f"Effective bid: $32 (ceiling), Effective listing: $35 (floor) | Filled: {result['filled_quantity']}/5"
    )

    conn.close()
    cleanup_test_db()
    return passed


# ============================================================================
# TEST 8: Variable Bid vs Variable Listing - Should Match
# ============================================================================
def test_variable_vs_variable_match():
    print_test_header("Variable Bid (spot+$5=$35, ceiling=$40) vs Variable Listing (spot+$2=$32, floor=$30) - Should Match")

    conn = setup_test_db()
    cursor = conn.cursor()

    # Create variable listing: spot+$2=$32, floor=$30
    # Effective listing price = $32
    cursor.execute('''
        INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, pricing_mode,
                            spot_premium, floor_price, pricing_metal, active)
        VALUES (1, 2, 10, NULL, 'premium_to_spot', 2.00, 30.00, 'silver', 1)
    ''')

    # Create variable bid: spot+$5=$35, ceiling=$40
    # Effective bid price = $35
    cursor.execute('''
        INSERT INTO bids (category_id, buyer_id, quantity_requested, remaining_quantity,
                         price_per_coin, pricing_mode, spot_premium, ceiling_price, pricing_metal,
                         delivery_address, active, status)
        VALUES (1, 1, 5, 5, NULL, 'premium_to_spot', 5.00, 40.00, 'silver', '123 Main St', 1, 'Open')
    ''')
    bid_id = cursor.lastrowid

    # Test autofill
    result = auto_match_bid_to_listings(bid_id, cursor)
    conn.commit()

    # Verify match (effective bid $35 > effective listing $32)
    bid = cursor.execute('SELECT * FROM bids WHERE id = ?', (bid_id,)).fetchone()
    order_items = cursor.execute('''
        SELECT oi.price_each
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.id
        WHERE o.buyer_id = 1
    ''').fetchall()

    # Transaction should occur at listing's effective price ($32)
    transaction_price = order_items[0]['price_each'] if order_items else 0

    passed = (
        result['filled_quantity'] == 5 and
        result['orders_created'] == 1 and
        bid['status'] == 'Filled' and
        abs(transaction_price - 32.00) < 0.01  # Transaction at listing price
    )

    print_result(
        "Variable bid and listing should match when effective prices overlap",
        passed,
        f"Effective bid: $35, Effective listing: $32, Transaction: ${transaction_price:.2f} | Filled: {result['filled_quantity']}/5"
    )

    conn.close()
    cleanup_test_db()
    return passed


# ============================================================================
# TEST 9: Multiple Listings - Match Only Valid Ones
# ============================================================================
def test_multiple_listings_selective_match():
    print_test_header("Bid should match ONLY listings with valid effective prices")

    conn = setup_test_db()
    cursor = conn.cursor()

    # Create listings with different effective prices
    # Listing 1: Fixed $30 (should match)
    cursor.execute('''
        INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, pricing_mode, active)
        VALUES (1, 2, 3, 30.00, 'static', 1)
    ''')

    # Listing 2: Variable spot+$2=$32 (should match)
    cursor.execute('''
        INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, pricing_mode,
                            spot_premium, floor_price, pricing_metal, active)
        VALUES (1, 2, 3, NULL, 'premium_to_spot', 2.00, 30.00, 'silver', 1)
    ''')

    # Listing 3: Variable spot+$1=$31, floor=$36 (should NOT match - floor too high)
    cursor.execute('''
        INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, pricing_mode,
                            spot_premium, floor_price, pricing_metal, active)
        VALUES (1, 2, 3, NULL, 'premium_to_spot', 1.00, 36.00, 'silver', 1)
    ''')

    # Listing 4: Fixed $38 (should NOT match - too expensive)
    cursor.execute('''
        INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, pricing_mode, active)
        VALUES (1, 2, 3, 38.00, 'static', 1)
    ''')

    # Create fixed bid at $35
    cursor.execute('''
        INSERT INTO bids (category_id, buyer_id, quantity_requested, remaining_quantity,
                         price_per_coin, pricing_mode, delivery_address, active, status)
        VALUES (1, 1, 10, 10, 35.00, 'static', '123 Main St', 1, 'Open')
    ''')
    bid_id = cursor.lastrowid

    # Test autofill
    result = auto_match_bid_to_listings(bid_id, cursor)
    conn.commit()

    # Should match only listings 1 and 2 (6 coins total)
    bid = cursor.execute('SELECT * FROM bids WHERE id = ?', (bid_id,)).fetchone()

    # Check which listings were used
    listing1 = cursor.execute('SELECT quantity FROM listings WHERE id = 1').fetchone()
    listing2 = cursor.execute('SELECT quantity FROM listings WHERE id = 2').fetchone()
    listing3 = cursor.execute('SELECT quantity FROM listings WHERE id = 3').fetchone()
    listing4 = cursor.execute('SELECT quantity FROM listings WHERE id = 4').fetchone()

    passed = (
        result['filled_quantity'] == 6 and  # Only 6 from valid listings
        listing1['quantity'] == 0 and  # Listing 1 fully consumed
        listing2['quantity'] == 0 and  # Listing 2 fully consumed
        listing3['quantity'] == 3 and  # Listing 3 NOT touched
        listing4['quantity'] == 3 and  # Listing 4 NOT touched
        bid['remaining_quantity'] == 4  # 4 still unfilled
    )

    print_result(
        "Bid should selectively match only listings with valid effective prices",
        passed,
        f"Filled: {result['filled_quantity']}/10, L1: {listing1['quantity']}, L2: {listing2['quantity']}, L3: {listing3['quantity']}, L4: {listing4['quantity']}"
    )

    conn.close()
    cleanup_test_db()
    return passed


# ============================================================================
# RUN ALL TESTS
# ============================================================================
def run_all_tests():
    """Run all test cases and report results"""
    print("\n" + "=" * 80)
    print("AUTOFILL EFFECTIVE PRICING TEST SUITE")
    print("=" * 80)
    print("\nSpot Prices: Silver = $30/oz, Gold = $2000/oz")
    print("\nTesting autofill logic with:")
    print("  - Fixed and variable pricing modes")
    print("  - Ceiling prices (max for bids)")
    print("  - Floor prices (min for listings)")
    print("  - Multiple listing combinations")

    tests = [
        ("Test 1", test_fixed_bid_fixed_listing_match),
        ("Test 2", test_fixed_bid_fixed_listing_no_match),
        ("Test 3", test_variable_bid_ceiling_blocks_match),
        ("Test 4", test_variable_bid_no_ceiling_block),
        ("Test 5", test_fixed_bid_vs_variable_listing_floor_blocks),
        ("Test 6", test_fixed_bid_vs_variable_listing_no_floor_block),
        ("Test 7", test_variable_vs_variable_both_blocked),
        ("Test 8", test_variable_vs_variable_match),
        ("Test 9", test_multiple_listings_selective_match),
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
