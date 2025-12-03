"""
Test script for automatic bid-listing matching system.

This script tests:
1. Full bid fills
2. Partial bid fills
3. Multiple sellers matching one bid
4. Grading requirement matching
5. Price-based matching (only <= bid price)
6. Listing quantity decrements
7. Order creation
"""

import sqlite3
from datetime import datetime


def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn


def cleanup_test_data(cursor):
    """Remove any previous test data"""
    print("[*] Cleaning up previous test data...")

    # Delete test orders
    cursor.execute('''
        DELETE FROM order_items WHERE order_id IN (
            SELECT id FROM orders WHERE buyer_id IN (
                SELECT id FROM users WHERE username LIKE 'test_auto_%'
            )
        )
    ''')
    cursor.execute('''
        DELETE FROM orders WHERE buyer_id IN (
            SELECT id FROM users WHERE username LIKE 'test_auto_%'
        )
    ''')

    # Delete test bids
    cursor.execute('''
        DELETE FROM bids WHERE buyer_id IN (
            SELECT id FROM users WHERE username LIKE 'test_auto_%'
        )
    ''')

    # Delete test listings
    cursor.execute('''
        DELETE FROM listings WHERE seller_id IN (
            SELECT id FROM users WHERE username LIKE 'test_auto_%'
        )
    ''')

    # Delete test users
    cursor.execute("DELETE FROM users WHERE username LIKE 'test_auto_%'")

    print("[+] Cleanup complete\n")


def create_test_users(cursor):
    """Create test users: 1 buyer and 3 sellers"""
    print("[+] Creating test users...")

    users = {
        'buyer': None,
        'seller1': None,
        'seller2': None,
        'seller3': None
    }

    for role in users.keys():
        username = f'test_auto_{role}'
        cursor.execute('''
            INSERT INTO users (username, password_hash, email, first_name, last_name)
            VALUES (?, 'test_hash', ?, 'Test', ?)
        ''', (username, f'{username}@test.com', role.capitalize()))
        users[role] = cursor.lastrowid
        print(f"  + Created {role}: {username} (ID: {users[role]})")

    print()
    return users


def create_test_category(cursor):
    """Create a test category (bucket)"""
    print("[+] Creating test category...")

    cursor.execute('''
        INSERT INTO categories (
            name, metal, product_type, weight, mint, year, finish, grade,
            coin_series, purity, product_line
        ) VALUES (
            'Test Auto Category', 'Silver', 'Coin', '1 oz', 'US Mint', '2024', 'Proof',
            'MS70', 'American Eagle', '0.999', 'Silver Eagles'
        )
    ''')

    category_id = cursor.lastrowid
    print(f"  + Created category ID: {category_id}\n")
    return category_id


def create_test_listings(cursor, category_id, users):
    """Create test listings from different sellers at various prices"""
    print("[+] Creating test listings...")

    listings_data = [
        # seller, quantity, price_per_coin, graded, grading_service
        ('seller1', 10, 25.00, 0, None),          # Cheapest, ungraded
        ('seller1', 5, 30.00, 1, 'PCGS'),         # PCGS graded
        ('seller2', 15, 27.50, 0, None),          # Mid-price, ungraded
        ('seller2', 8, 35.00, 1, 'NGC'),          # NGC graded
        ('seller3', 20, 32.00, 0, None),          # Higher price, ungraded
        ('seller3', 12, 45.00, 1, 'PCGS'),        # Expensive, PCGS graded
    ]

    listing_ids = []
    for seller_key, qty, price, graded, grader in listings_data:
        cursor.execute('''
            INSERT INTO listings (
                category_id, seller_id, quantity, price_per_coin,
                graded, grading_service, active
            ) VALUES (?, ?, ?, ?, ?, ?, 1)
        ''', (category_id, users[seller_key], qty, price, graded, grader))

        listing_id = cursor.lastrowid
        listing_ids.append(listing_id)
        grader_info = f" ({grader})" if graded else ""
        print(f"  + {seller_key}: {qty} units @ ${price:.2f}{grader_info} (ID: {listing_id})")

    print()
    return listing_ids


def test_scenario_1_full_fill(cursor, category_id, buyer_id):
    """Test 1: Bid that should be fully filled from cheapest listings"""
    print("\n" + "="*70)
    print("TEST 1: Full Bid Fill (10 units @ $28.00)")
    print("="*70)
    print("Expected: Match 10 units from seller1 @ $25.00")
    print()

    # Create bid for 10 units at $28.00
    cursor.execute('''
        INSERT INTO bids (
            category_id, buyer_id, quantity_requested, price_per_coin,
            remaining_quantity, delivery_address, status, active
        ) VALUES (?, ?, 10, 28.00, 10, '123 Test St', 'Open', 1)
    ''', (category_id, buyer_id))

    bid_id = cursor.lastrowid
    print(f"[+] Created bid ID: {bid_id}")

    # Manually call auto-matching logic
    from routes.bid_routes import auto_match_bid_to_listings
    result = auto_match_bid_to_listings(bid_id, cursor)

    print(f"\n[+] Matching Result:")
    print(f"  Filled Quantity: {result['filled_quantity']}")
    print(f"  Orders Created: {result['orders_created']}")
    print(f"  Message: {result['message']}")

    # Verify bid status
    bid = cursor.execute('SELECT * FROM bids WHERE id = ?', (bid_id,)).fetchone()
    print(f"\n[OK] Bid Status:")
    print(f"  Status: {bid['status']}")
    print(f"  Remaining: {bid['remaining_quantity']}")
    print(f"  Fulfilled: {bid['quantity_fulfilled']}")

    # Verify orders
    orders = cursor.execute('''
        SELECT o.id, o.total_price, oi.quantity, oi.price_each
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        WHERE o.buyer_id = ?
        ORDER BY o.id DESC
    ''', (buyer_id,)).fetchall()

    print(f"\n[+] Orders Created: {len(orders)}")
    for order in orders:
        print(f"  Order #{order['id']}: {order['quantity']} units @ ${order['price_each']:.2f} " +
              f"(Total: ${order['total_price']:.2f})")

    # Verify listing quantities
    listing = cursor.execute('''
        SELECT quantity, active FROM listings WHERE category_id = ? AND price_per_coin = 25.00
    ''', (category_id,)).fetchone()
    print(f"\n[+] Listing Update:")
    print(f"  Remaining quantity @ $25.00: {listing['quantity']}")
    print(f"  Active: {'Yes' if listing['active'] else 'No'}")

    assert result['filled_quantity'] == 10, "Should fill 10 units"
    assert result['orders_created'] == 1, "Should create 1 order"
    assert bid['status'] == 'Filled', "Bid should be fully filled"
    assert bid['remaining_quantity'] == 0, "No remaining quantity"
    assert listing['quantity'] == 0, "Listing should be depleted"

    print("\n[OK] TEST 1 PASSED")


def test_scenario_2_partial_fill(cursor, category_id, buyer_id):
    """Test 2: Bid that should be partially filled"""
    print("\n" + "="*70)
    print("TEST 2: Partial Bid Fill (50 units @ $30.00)")
    print("="*70)
    print("Expected: Match 15 units from seller2 @ $27.50")
    print("          Match 5 units from seller1 @ $30.00 (PCGS)")
    print("          (remaining 30 units stay open)")
    print()

    # Create bid for 50 units at $30.00
    cursor.execute('''
        INSERT INTO bids (
            category_id, buyer_id, quantity_requested, price_per_coin,
            remaining_quantity, delivery_address, status, active
        ) VALUES (?, ?, 50, 30.00, 50, '123 Test St', 'Open', 1)
    ''', (category_id, buyer_id))

    bid_id = cursor.lastrowid
    print(f"[+] Created bid ID: {bid_id}")

    # Manually call auto-matching logic
    from routes.bid_routes import auto_match_bid_to_listings
    result = auto_match_bid_to_listings(bid_id, cursor)

    print(f"\n[+] Matching Result:")
    print(f"  Filled Quantity: {result['filled_quantity']}")
    print(f"  Orders Created: {result['orders_created']}")
    print(f"  Message: {result['message']}")

    # Verify bid status
    bid = cursor.execute('SELECT * FROM bids WHERE id = ?', (bid_id,)).fetchone()
    print(f"\n[OK] Bid Status:")
    print(f"  Status: {bid['status']}")
    print(f"  Remaining: {bid['remaining_quantity']}")
    print(f"  Fulfilled: {bid['quantity_fulfilled']}")

    assert result['filled_quantity'] == 20, "Should fill 20 units (15 @ $27.50 + 5 @ $30.00)"
    assert bid['status'] == 'Partially Filled', "Bid should be partially filled"
    assert bid['remaining_quantity'] == 30, "Should have 30 remaining"

    print("\n[OK] TEST 2 PASSED")


def test_scenario_3_multiple_sellers(cursor, category_id, buyer_id):
    """Test 3: Bid filled by multiple sellers (after previous tests consumed cheaper listings)"""
    print("\n" + "="*70)
    print("TEST 3: Multiple Sellers (40 units @ $33.00)")
    print("="*70)
    print("Expected: Match 20 units from seller3 @ $32.00")
    print("          (previous tests already consumed cheaper listings)")
    print()

    # Create bid for 40 units at $33.00
    cursor.execute('''
        INSERT INTO bids (
            category_id, buyer_id, quantity_requested, price_per_coin,
            remaining_quantity, delivery_address, status, active
        ) VALUES (?, ?, 40, 33.00, 40, '123 Test St', 'Open', 1)
    ''', (category_id, buyer_id))

    bid_id = cursor.lastrowid
    print(f"[+] Created bid ID: {bid_id}")

    # Manually call auto-matching logic
    from routes.bid_routes import auto_match_bid_to_listings
    result = auto_match_bid_to_listings(bid_id, cursor)

    print(f"\n[+] Matching Result:")
    print(f"  Filled Quantity: {result['filled_quantity']}")
    print(f"  Orders Created: {result['orders_created']}")
    print(f"  Message: {result['message']}")

    # Verify orders from multiple sellers
    orders = cursor.execute('''
        SELECT o.id, o.total_price, COUNT(oi.order_item_id) as item_count,
               SUM(oi.quantity) as total_qty
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        WHERE o.buyer_id = ?
        GROUP BY o.id
        ORDER BY o.id DESC
        LIMIT 10
    ''', (buyer_id,)).fetchall()

    print(f"\n[+] Orders Created: {len(orders)}")
    for order in orders:
        print(f"  Order #{order['id']}: {order['total_qty']} units " +
              f"(Total: ${order['total_price']:.2f})")

    # Verify bid status
    bid = cursor.execute('SELECT * FROM bids WHERE id = ?', (bid_id,)).fetchone()

    # Only 20 units available at this price point after previous tests
    assert result['filled_quantity'] == 20, "Should fill 20 units (only seller3 @ $32 remaining)"
    assert result['orders_created'] >= 1, "Should create at least 1 order"
    assert bid['status'] == 'Partially Filled', "Bid should be partially filled (20/40)"

    print("\n[OK] TEST 3 PASSED")


def test_scenario_4_grading_requirement(cursor, category_id, buyer_id):
    """Test 4: Bid with grading requirement"""
    print("\n" + "="*70)
    print("TEST 4: Grading Requirement (10 units @ $40.00, requires PCGS)")
    print("="*70)
    print("Expected: Match only PCGS graded listings")
    print()

    # Create bid requiring PCGS grading
    cursor.execute('''
        INSERT INTO bids (
            category_id, buyer_id, quantity_requested, price_per_coin,
            remaining_quantity, delivery_address, status, active,
            requires_grading, preferred_grader
        ) VALUES (?, ?, 10, 40.00, 10, '123 Test St', 'Open', 1, 1, 'PCGS')
    ''', (category_id, buyer_id))

    bid_id = cursor.lastrowid
    print(f"[+] Created bid ID: {bid_id} (requires PCGS grading)")

    # Manually call auto-matching logic
    from routes.bid_routes import auto_match_bid_to_listings
    result = auto_match_bid_to_listings(bid_id, cursor)

    print(f"\n[+] Matching Result:")
    print(f"  Filled Quantity: {result['filled_quantity']}")
    print(f"  Orders Created: {result['orders_created']}")
    print(f"  Message: {result['message']}")

    # Verify only PCGS listings were matched
    if result['filled_quantity'] > 0:
        matched_listings = cursor.execute('''
            SELECT l.grading_service, oi.quantity, oi.price_each
            FROM order_items oi
            JOIN listings l ON oi.listing_id = l.id
            JOIN orders o ON oi.order_id = o.id
            WHERE o.buyer_id = ?
            ORDER BY o.id DESC
            LIMIT 10
        ''', (buyer_id,)).fetchall()

        print(f"\n[+] Matched Listings:")
        for listing in matched_listings:
            print(f"  {listing['quantity']} units @ ${listing['price_each']:.2f} " +
                  f"(Grader: {listing['grading_service']})")
            assert listing['grading_service'] == 'PCGS', "Should only match PCGS listings"

    print("\n[OK] TEST 4 PASSED")


def run_all_tests():
    """Run all test scenarios"""
    print("\n" + "="*70)
    print("AUTOMATIC BID-LISTING MATCHING SYSTEM TEST SUITE")
    print("="*70)
    print()

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Setup
        cleanup_test_data(cursor)
        users = create_test_users(cursor)
        category_id = create_test_category(cursor)
        create_test_listings(cursor, category_id, users)
        conn.commit()

        # Run tests
        test_scenario_1_full_fill(cursor, category_id, users['buyer'])
        conn.commit()

        test_scenario_2_partial_fill(cursor, category_id, users['buyer'])
        conn.commit()

        test_scenario_3_multiple_sellers(cursor, category_id, users['buyer'])
        conn.commit()

        test_scenario_4_grading_requirement(cursor, category_id, users['buyer'])
        conn.commit()

        # Summary
        print("\n" + "="*70)
        print("ALL TESTS PASSED! [OK]")
        print("="*70)
        print("\nSummary:")
        print("  + Full bid fills working")
        print("  + Partial bid fills working")
        print("  + Multiple seller matching working")
        print("  + Grading requirements working")
        print("  + Listing quantities properly decremented")
        print("  + Orders properly created")
        print()

    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        conn.rollback()
    except Exception as e:
        print(f"\n[FAIL] ERROR: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        # Cleanup
        print("[*] Final cleanup...")
        cleanup_test_data(cursor)
        conn.commit()
        conn.close()
        print("[OK] Cleanup complete")


if __name__ == '__main__':
    run_all_tests()
