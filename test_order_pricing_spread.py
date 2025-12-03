"""
Test: Order Pricing with Spread Capture

Verifies that autofilled orders are created at the BID's effective price (not the listing's price),
allowing the platform to capture the spread between bid and ask prices.

Example:
- Bid effective price: $1400 (buyer willing to pay)
- Listing effective price: $1000 (seller asking)
- Order should show: $1400 (buyer pays their bid price)
- Platform captures: $400 spread
"""

import sqlite3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes.bid_routes import auto_match_bid_to_listings

TEST_DB = 'test_order_pricing.db'


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
            price_usd_per_oz REAL NOT NULL
        )
    ''')

    # Insert test data
    cursor.execute("INSERT INTO users (id, username, email) VALUES (1, 'buyer1', 'buyer1@test.com')")
    cursor.execute("INSERT INTO users (id, username, email) VALUES (2, 'seller1', 'seller1@test.com')")
    cursor.execute('''
        INSERT INTO categories (id, metal, product_type, product_line, weight, year)
        VALUES (1, 'silver', 'Coin', 'American Silver Eagle', 1.0, 2024)
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
# TEST 1: Fixed Bid ($1400) vs Fixed Listing ($1000) - Capture $400 Spread
# ============================================================================
def test_fixed_bid_vs_fixed_listing_spread():
    print_test_header("Fixed Bid ($1400) vs Fixed Listing ($1000) - Capture $400 Spread")

    conn = setup_test_db()
    cursor = conn.cursor()

    # Create listing at $1000 (seller asking price)
    cursor.execute('''
        INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, pricing_mode, active)
        VALUES (1, 2, 5, 1000.00, 'static', 1)
    ''')

    # Create bid at $1400 (buyer willing to pay)
    cursor.execute('''
        INSERT INTO bids (category_id, buyer_id, quantity_requested, remaining_quantity,
                         price_per_coin, pricing_mode, delivery_address, active, status)
        VALUES (1, 1, 5, 5, 1400.00, 'static', '123 Main St', 1, 'Open')
    ''')
    bid_id = cursor.lastrowid

    # Test autofill
    result = auto_match_bid_to_listings(bid_id, cursor)
    conn.commit()

    # Verify order was created with BID's price ($1400), not listing's price ($1000)
    order_items = cursor.execute('''
        SELECT price_each, quantity FROM order_items
    ''').fetchall()

    if order_items:
        order_price = order_items[0]['price_each']
        order_qty = order_items[0]['quantity']
        expected_price = 1400.00
        spread = expected_price - 1000.00  # $400 spread

        passed = abs(order_price - expected_price) < 0.01 and order_qty == 5

        print_result(
            "Order created at bid's price (capturing spread)",
            passed,
            f"Bid: ${expected_price:.2f}, Listing: $1000.00, Order Price: ${order_price:.2f}, Spread: ${spread:.2f}"
        )
    else:
        print_result("Order created at bid's price (capturing spread)", False, "No order items found")
        passed = False

    conn.close()
    cleanup_test_db()
    return passed


# ============================================================================
# TEST 2: Variable Bid vs Fixed Listing - With Spread
# ============================================================================
def test_variable_bid_vs_fixed_listing_spread():
    print_test_header("Variable Bid (effective=$35) vs Fixed Listing ($32) - Capture $3 Spread")

    conn = setup_test_db()
    cursor = conn.cursor()

    # Create listing at $32
    cursor.execute('''
        INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, pricing_mode, active)
        VALUES (1, 2, 5, 32.00, 'static', 1)
    ''')

    # Create variable bid: spot($30) + premium($5) = $35
    cursor.execute('''
        INSERT INTO bids (category_id, buyer_id, quantity_requested, remaining_quantity,
                         price_per_coin, pricing_mode, spot_premium, ceiling_price, pricing_metal,
                         delivery_address, active, status)
        VALUES (1, 1, 5, 5, NULL, 'premium_to_spot', 5.00, NULL, 'silver', '123 Main St', 1, 'Open')
    ''')
    bid_id = cursor.lastrowid

    # Test autofill
    result = auto_match_bid_to_listings(bid_id, cursor)
    conn.commit()

    # Verify order price
    order_items = cursor.execute('SELECT price_each, quantity FROM order_items').fetchall()

    if order_items:
        order_price = order_items[0]['price_each']
        expected_price = 35.00  # spot($30) + premium($5)
        spread = expected_price - 32.00  # $3 spread

        passed = abs(order_price - expected_price) < 0.01

        print_result(
            "Order created at bid's effective price",
            passed,
            f"Bid effective: ${expected_price:.2f}, Listing: $32.00, Order: ${order_price:.2f}, Spread: ${spread:.2f}"
        )
    else:
        print_result("Order created at bid's effective price", False, "No order items found")
        passed = False

    conn.close()
    cleanup_test_db()
    return passed


# ============================================================================
# TEST 3: Fixed Bid vs Variable Listing - With Spread
# ============================================================================
def test_fixed_bid_vs_variable_listing_spread():
    print_test_header("Fixed Bid ($40) vs Variable Listing (effective=$32) - Capture $8 Spread")

    conn = setup_test_db()
    cursor = conn.cursor()

    # Create variable listing: spot($30) + premium($2) = $32
    cursor.execute('''
        INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, pricing_mode,
                            spot_premium, floor_price, pricing_metal, active)
        VALUES (1, 2, 5, NULL, 'premium_to_spot', 2.00, 30.00, 'silver', 1)
    ''')

    # Create fixed bid at $40
    cursor.execute('''
        INSERT INTO bids (category_id, buyer_id, quantity_requested, remaining_quantity,
                         price_per_coin, pricing_mode, delivery_address, active, status)
        VALUES (1, 1, 5, 5, 40.00, 'static', '123 Main St', 1, 'Open')
    ''')
    bid_id = cursor.lastrowid

    # Test autofill
    result = auto_match_bid_to_listings(bid_id, cursor)
    conn.commit()

    # Verify order price
    order_items = cursor.execute('SELECT price_each, quantity FROM order_items').fetchall()

    if order_items:
        order_price = order_items[0]['price_each']
        expected_price = 40.00  # bid price
        listing_effective = 32.00  # spot($30) + premium($2)
        spread = expected_price - listing_effective  # $8 spread

        passed = abs(order_price - expected_price) < 0.01

        print_result(
            "Order created at bid's price",
            passed,
            f"Bid: ${expected_price:.2f}, Listing effective: ${listing_effective:.2f}, Order: ${order_price:.2f}, Spread: ${spread:.2f}"
        )
    else:
        print_result("Order created at bid's price", False, "No order items found")
        passed = False

    conn.close()
    cleanup_test_db()
    return passed


# ============================================================================
# TEST 4: Variable Bid vs Variable Listing - With Spread
# ============================================================================
def test_variable_vs_variable_spread():
    print_test_header("Variable Bid (effective=$38) vs Variable Listing (effective=$32) - Capture $6 Spread")

    conn = setup_test_db()
    cursor = conn.cursor()

    # Create variable listing: spot($30) + premium($2) = $32
    cursor.execute('''
        INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, pricing_mode,
                            spot_premium, floor_price, pricing_metal, active)
        VALUES (1, 2, 5, NULL, 'premium_to_spot', 2.00, 30.00, 'silver', 1)
    ''')

    # Create variable bid: spot($30) + premium($8) = $38
    cursor.execute('''
        INSERT INTO bids (category_id, buyer_id, quantity_requested, remaining_quantity,
                         price_per_coin, pricing_mode, spot_premium, ceiling_price, pricing_metal,
                         delivery_address, active, status)
        VALUES (1, 1, 5, 5, NULL, 'premium_to_spot', 8.00, NULL, 'silver', '123 Main St', 1, 'Open')
    ''')
    bid_id = cursor.lastrowid

    # Test autofill
    result = auto_match_bid_to_listings(bid_id, cursor)
    conn.commit()

    # Verify order price
    order_items = cursor.execute('SELECT price_each, quantity FROM order_items').fetchall()

    if order_items:
        order_price = order_items[0]['price_each']
        bid_effective = 38.00  # spot($30) + premium($8)
        listing_effective = 32.00  # spot($30) + premium($2)
        spread = bid_effective - listing_effective  # $6 spread

        passed = abs(order_price - bid_effective) < 0.01

        print_result(
            "Order created at bid's effective price",
            passed,
            f"Bid effective: ${bid_effective:.2f}, Listing effective: ${listing_effective:.2f}, Order: ${order_price:.2f}, Spread: ${spread:.2f}"
        )
    else:
        print_result("Order created at bid's effective price", False, "No order items found")
        passed = False

    conn.close()
    cleanup_test_db()
    return passed


# ============================================================================
# TEST 5: Multiple Listings - All Orders Use Bid Price
# ============================================================================
def test_multiple_listings_same_bid_price():
    print_test_header("Multiple Listings - All Orders Should Use Same Bid Price")

    conn = setup_test_db()
    cursor = conn.cursor()

    # Create 3 listings at different prices
    cursor.execute('''
        INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, pricing_mode, active)
        VALUES (1, 2, 2, 30.00, 'static', 1)
    ''')
    cursor.execute('''
        INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, pricing_mode, active)
        VALUES (1, 2, 2, 32.00, 'static', 1)
    ''')
    cursor.execute('''
        INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, pricing_mode, active)
        VALUES (1, 2, 2, 34.00, 'static', 1)
    ''')

    # Create bid at $40 for 6 items (will match all 3 listings)
    cursor.execute('''
        INSERT INTO bids (category_id, buyer_id, quantity_requested, remaining_quantity,
                         price_per_coin, pricing_mode, delivery_address, active, status)
        VALUES (1, 1, 6, 6, 40.00, 'static', '123 Main St', 1, 'Open')
    ''')
    bid_id = cursor.lastrowid

    # Test autofill
    result = auto_match_bid_to_listings(bid_id, cursor)
    conn.commit()

    # Verify all order items use bid price ($40), not individual listing prices
    order_items = cursor.execute('''
        SELECT price_each, quantity FROM order_items ORDER BY id
    ''').fetchall()

    expected_price = 40.00
    all_correct = True
    total_spread = 0

    if len(order_items) == 3:
        for i, item in enumerate(order_items):
            order_price = item['price_each']
            if abs(order_price - expected_price) >= 0.01:
                all_correct = False

            # Calculate spread for each listing
            listing_prices = [30.00, 32.00, 34.00]
            total_spread += (expected_price - listing_prices[i]) * item['quantity']

        passed = all_correct and abs(result['filled_quantity'] - 6) < 0.01

        print_result(
            "All order items use bid price",
            passed,
            f"All 3 items at ${expected_price:.2f}, Listings: $30/$32/$34, Total Spread Captured: ${total_spread:.2f}"
        )
    else:
        print_result("All order items use bid price", False, f"Expected 3 order items, got {len(order_items)}")
        passed = False

    conn.close()
    cleanup_test_db()
    return passed


# ============================================================================
# TEST 6: Variable Bid with Ceiling - Order Uses Capped Price
# ============================================================================
def test_variable_bid_ceiling_order_price():
    print_test_header("Variable Bid with Ceiling - Order Uses Capped Bid Price")

    conn = setup_test_db()
    cursor = conn.cursor()

    # Create listing at $30
    cursor.execute('''
        INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, pricing_mode, active)
        VALUES (1, 2, 5, 30.00, 'static', 1)
    ''')

    # Create variable bid: spot($30) + premium($8) = $38, but ceiling = $35
    # Effective bid price should be $35 (capped)
    cursor.execute('''
        INSERT INTO bids (category_id, buyer_id, quantity_requested, remaining_quantity,
                         price_per_coin, pricing_mode, spot_premium, ceiling_price, pricing_metal,
                         delivery_address, active, status)
        VALUES (1, 1, 5, 5, NULL, 'premium_to_spot', 8.00, 35.00, 'silver', '123 Main St', 1, 'Open')
    ''')
    bid_id = cursor.lastrowid

    # Test autofill
    result = auto_match_bid_to_listings(bid_id, cursor)
    conn.commit()

    # Verify order uses ceiling price ($35), not uncapped price ($38)
    order_items = cursor.execute('SELECT price_each, quantity FROM order_items').fetchall()

    if order_items:
        order_price = order_items[0]['price_each']
        expected_price = 35.00  # ceiling price
        uncapped_price = 38.00  # spot($30) + premium($8)
        spread = expected_price - 30.00  # $5 spread

        passed = abs(order_price - expected_price) < 0.01

        print_result(
            "Order uses capped bid price (ceiling)",
            passed,
            f"Uncapped: ${uncapped_price:.2f}, Ceiling: ${expected_price:.2f}, Order: ${order_price:.2f}, Spread: ${spread:.2f}"
        )
    else:
        print_result("Order uses capped bid price (ceiling)", False, "No order items found")
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
    print("ORDER PRICING SPREAD CAPTURE TEST SUITE")
    print("=" * 80)
    print("\nTesting that orders are created at BID's effective price (capturing spread):")
    print("  - Fixed bid vs fixed listing")
    print("  - Variable bid vs fixed listing")
    print("  - Fixed bid vs variable listing")
    print("  - Variable bid vs variable listing")
    print("  - Multiple listings with same bid")
    print("  - Variable bid with ceiling")

    tests = [
        ("Test 1", test_fixed_bid_vs_fixed_listing_spread),
        ("Test 2", test_variable_bid_vs_fixed_listing_spread),
        ("Test 3", test_fixed_bid_vs_variable_listing_spread),
        ("Test 4", test_variable_vs_variable_spread),
        ("Test 5", test_multiple_listings_same_bid_price),
        ("Test 6", test_variable_bid_ceiling_order_price),
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
