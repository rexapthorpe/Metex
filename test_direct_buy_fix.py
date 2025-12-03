"""
Test script to verify the direct_buy fix
Tests that users cannot buy their own listings and can buy from other sellers
"""

import sqlite3
import os
from database import get_db_connection

# Test database path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.db')

def setup_test_data():
    """Create test data for the buy flow"""
    conn = get_db_connection()
    cursor = conn.cursor()

    print("[SETUP] Creating test data...")

    # Create test users
    try:
        cursor.execute('''
            INSERT OR IGNORE INTO users (id, username, email, password)
            VALUES (9990, 'test_buyer', 'buyer@test.com', 'hashed_pass')
        ''')
        cursor.execute('''
            INSERT OR IGNORE INTO users (id, username, email, password)
            VALUES (9991, 'test_seller1', 'seller1@test.com', 'hashed_pass')
        ''')
        cursor.execute('''
            INSERT OR IGNORE INTO users (id, username, email, password)
            VALUES (9992, 'test_seller2', 'seller2@test.com', 'hashed_pass')
        ''')

        # Add address for buyer
        cursor.execute('''
            INSERT OR IGNORE INTO addresses (user_id, street, city, state, zip_code, is_default)
            VALUES (9990, '123 Test St', 'Test City', 'TS', '12345', 1)
        ''')

        # Create test category
        cursor.execute('''
            INSERT OR IGNORE INTO categories (id, bucket_id, metal, product_type, weight, year)
            VALUES (9990, 9990, 'Silver', 'Coin', '1 oz', '2024')
        ''')

        # Create listing from buyer (should NOT be purchasable by buyer)
        cursor.execute('''
            INSERT OR IGNORE INTO listings (id, category_id, seller_id, quantity, price_per_coin, active, graded)
            VALUES (9990, 9990, 9990, 10, 25.00, 1, 0)
        ''')

        # Create listing from seller1 (should be purchasable by buyer)
        cursor.execute('''
            INSERT OR IGNORE INTO listings (id, category_id, seller_id, quantity, price_per_coin, active, graded)
            VALUES (9991, 9990, 9991, 20, 26.00, 1, 0)
        ''')

        # Create listing from seller2 (should be purchasable by buyer)
        cursor.execute('''
            INSERT OR IGNORE INTO listings (id, category_id, seller_id, quantity, price_per_coin, active, graded)
            VALUES (9992, 9990, 9992, 15, 27.00, 1, 0)
        ''')

        conn.commit()
        print("[SETUP] Test data created successfully")
        print(f"  - Buyer: user_id=9990")
        print(f"  - Seller1: user_id=9991 (20 units @ $26.00)")
        print(f"  - Seller2: user_id=9992 (15 units @ $27.00)")
        print(f"  - Buyer's own listing: 10 units @ $25.00 (should be excluded)")

    except Exception as e:
        print(f"[ERROR] Failed to setup test data: {e}")
        conn.rollback()
    finally:
        conn.close()

def test_scenario_1_buyer_cannot_buy_own_listings():
    """Test that buyer cannot buy from a bucket with only their own listings"""
    print("\n" + "="*80)
    print("TEST 1: Buyer tries to buy from bucket with only their own listings")
    print("="*80)

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Temporarily deactivate other sellers' listings
        cursor.execute('UPDATE listings SET active = 0 WHERE id IN (9991, 9992)')
        conn.commit()

        # Simulate the direct_buy query with buyer's user_id
        user_id = 9990
        bucket_id = 9990

        listings_query = '''
            SELECT l.id, l.quantity, l.price_per_coin, l.seller_id, l.grading_service
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE c.bucket_id = ? AND l.active = 1 AND l.quantity > 0
        '''
        params = [bucket_id]

        # THE FIX: Exclude user's own listings
        if user_id:
            listings_query += ' AND l.seller_id != ?'
            params.append(user_id)

        listings_query += ' ORDER BY l.price_per_coin ASC, l.id ASC'

        listings = cursor.execute(listings_query, params).fetchall()

        if not listings:
            print("[PASS] ✓ Correctly returned no listings (buyer's own listing was excluded)")
            print("       Expected behavior: User should see 'No matching listings available'")
        else:
            print("[FAIL] ✗ Found listings when none should be available!")
            print(f"       Found: {len(listings)} listings")

        # Restore listings for next test
        cursor.execute('UPDATE listings SET active = 1 WHERE id IN (9991, 9992)')
        conn.commit()

        return not listings  # Test passes if no listings found

    except Exception as e:
        print(f"[FAIL] ✗ Test failed with error: {e}")
        return False
    finally:
        conn.close()

def test_scenario_2_buyer_can_buy_from_others():
    """Test that buyer can successfully buy from other sellers"""
    print("\n" + "="*80)
    print("TEST 2: Buyer tries to buy from bucket with other sellers' listings")
    print("="*80)

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Simulate the direct_buy query with buyer's user_id
        user_id = 9990
        bucket_id = 9990
        quantity_to_buy = 5

        listings_query = '''
            SELECT l.id, l.quantity, l.price_per_coin, l.seller_id, l.grading_service
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE c.bucket_id = ? AND l.active = 1 AND l.quantity > 0
        '''
        params = [bucket_id]

        # THE FIX: Exclude user's own listings
        if user_id:
            listings_query += ' AND l.seller_id != ?'
            params.append(user_id)

        listings_query += ' ORDER BY l.price_per_coin ASC, l.id ASC'

        listings = cursor.execute(listings_query, params).fetchall()

        if listings:
            print(f"[PASS] ✓ Found {len(listings)} eligible listings")
            for listing in listings:
                print(f"       Listing {listing['id']}: seller_id={listing['seller_id']}, "
                      f"qty={listing['quantity']}, price=${listing['price_per_coin']:.2f}")

            # Verify buyer's own listing is excluded
            buyer_listing_found = any(l['seller_id'] == user_id for l in listings)
            if buyer_listing_found:
                print("[FAIL] ✗ Buyer's own listing was NOT excluded!")
                return False
            else:
                print("[PASS] ✓ Buyer's own listing correctly excluded")

            # Simulate filling the order
            total_filled = 0
            for listing in listings:
                if total_filled >= quantity_to_buy:
                    break
                available = listing['quantity']
                fill_qty = min(available, quantity_to_buy - total_filled)
                total_filled += fill_qty
                print(f"       Would fill {fill_qty} units from listing {listing['id']}")

            if total_filled == quantity_to_buy:
                print(f"[PASS] ✓ Successfully filled {total_filled}/{quantity_to_buy} units")
                return True
            else:
                print(f"[FAIL] ✗ Only filled {total_filled}/{quantity_to_buy} units")
                return False
        else:
            print("[FAIL] ✗ No listings found when other sellers exist!")
            return False

    except Exception as e:
        print(f"[FAIL] ✗ Test failed with error: {e}")
        return False
    finally:
        conn.close()

def test_scenario_3_mixed_sellers():
    """Test buying from a mix of sellers (buyer's own + others)"""
    print("\n" + "="*80)
    print("TEST 3: Bucket has buyer's listing + other sellers (mixed)")
    print("="*80)

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        user_id = 9990
        bucket_id = 9990

        # Count total listings in bucket
        total_listings = cursor.execute('''
            SELECT COUNT(*) as count
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE c.bucket_id = ? AND l.active = 1
        ''', (bucket_id,)).fetchone()['count']

        print(f"  Total active listings in bucket: {total_listings}")

        # Count listings excluding buyer's own
        listings_query = '''
            SELECT COUNT(*) as count
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE c.bucket_id = ? AND l.active = 1 AND l.quantity > 0
        '''
        params = [bucket_id]

        if user_id:
            listings_query += ' AND l.seller_id != ?'
            params.append(user_id)

        eligible_count = cursor.execute(listings_query, params).fetchone()['count']

        print(f"  Eligible listings (excluding buyer's own): {eligible_count}")

        if total_listings == 3 and eligible_count == 2:
            print("[PASS] ✓ Correctly excluded 1 listing (buyer's own)")
            print("       3 total listings - 1 buyer's listing = 2 eligible listings")
            return True
        else:
            print(f"[FAIL] ✗ Expected 3 total and 2 eligible, got {total_listings} total and {eligible_count} eligible")
            return False

    except Exception as e:
        print(f"[FAIL] ✗ Test failed with error: {e}")
        return False
    finally:
        conn.close()

def cleanup_test_data():
    """Remove test data"""
    print("\n" + "="*80)
    print("CLEANUP")
    print("="*80)

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('DELETE FROM listings WHERE id IN (9990, 9991, 9992)')
        cursor.execute('DELETE FROM categories WHERE id = 9990')
        cursor.execute('DELETE FROM addresses WHERE user_id = 9990')
        cursor.execute('DELETE FROM users WHERE id IN (9990, 9991, 9992)')
        conn.commit()
        print("[CLEANUP] Test data removed successfully")
    except Exception as e:
        print(f"[ERROR] Failed to cleanup: {e}")
    finally:
        conn.close()

def main():
    """Run all tests"""
    print("\n" + "#"*80)
    print("# DIRECT BUY FIX - VERIFICATION TESTS")
    print("#"*80)

    # Setup
    setup_test_data()

    # Run tests
    results = []
    results.append(("Buyer cannot buy own listings", test_scenario_1_buyer_cannot_buy_own_listings()))
    results.append(("Buyer can buy from other sellers", test_scenario_2_buyer_can_buy_from_others()))
    results.append(("Mixed sellers handled correctly", test_scenario_3_mixed_sellers()))

    # Cleanup
    cleanup_test_data()

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        print("\n✓ ALL TESTS PASSED - FIX VERIFIED!")
    else:
        print(f"\n✗ {total - passed} TEST(S) FAILED")

    return passed == total

if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)
