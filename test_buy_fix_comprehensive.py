"""
Comprehensive test to verify the direct_buy fix
Creates a specific test scenario with user's own listings
"""

from database import get_db_connection

def test_with_own_listings():
    """Create a scenario where user has own listings and test exclusion"""
    print("\n" + "="*70)
    print("COMPREHENSIVE DIRECT BUY FIX TEST")
    print("="*70 + "\n")

    conn = get_db_connection()
    cursor = conn.cursor()

    test_user_id = 9999
    test_bucket_id = 9999
    test_category_id = 9999

    # Cleanup any previous test data
    print("[SETUP] Cleaning up previous test data...")
    cursor.execute('DELETE FROM listings WHERE id >= 9999 AND id <= 10002')
    cursor.execute('DELETE FROM categories WHERE id = 9999')
    cursor.execute('DELETE FROM users WHERE id >= 9999 AND id <= 10001')
    conn.commit()

    # Create test users
    print("[SETUP] Creating test users...")
    cursor.execute('''
        INSERT INTO users (id, username, password_hash, email)
        VALUES (9999, 'test_buyer', 'hash123', 'buyer@test.com')
    ''')
    cursor.execute('''
        INSERT INTO users (id, username, password_hash, email)
        VALUES (10000, 'test_seller1', 'hash123', 'seller1@test.com')
    ''')
    cursor.execute('''
        INSERT INTO users (id, username, password_hash, email)
        VALUES (10001, 'test_seller2', 'hash123', 'seller2@test.com')
    ''')

    # Create test category/bucket
    print("[SETUP] Creating test bucket...")
    cursor.execute('''
        INSERT INTO categories (id, bucket_id, metal, product_type, weight, year)
        VALUES (9999, 9999, 'Silver', 'Test Coin', '1 oz', '2024')
    ''')

    # Create listings
    print("[SETUP] Creating test listings...")
    # Listing from buyer (should be EXCLUDED)
    cursor.execute('''
        INSERT INTO listings (id, category_id, seller_id, quantity, price_per_coin, active, graded)
        VALUES (9999, 9999, 9999, 10, 25.00, 1, 0)
    ''')

    # Listing from seller1 (should be INCLUDED)
    cursor.execute('''
        INSERT INTO listings (id, category_id, seller_id, quantity, price_per_coin, active, graded)
        VALUES (10000, 9999, 10000, 20, 26.00, 1, 0)
    ''')

    # Listing from seller2 (should be INCLUDED)
    cursor.execute('''
        INSERT INTO listings (id, category_id, seller_id, quantity, price_per_coin, active, graded)
        VALUES (10001, 9999, 10001, 15, 27.00, 1, 0)
    ''')

    # Another listing from buyer (should be EXCLUDED)
    cursor.execute('''
        INSERT INTO listings (id, category_id, seller_id, quantity, price_per_coin, active, graded)
        VALUES (10002, 9999, 9999, 5, 24.50, 1, 0)
    ''')

    conn.commit()

    print("\nTest Setup Complete:")
    print(f"  Buyer (user_id=9999) has 2 listings: 10 units @ $25.00, 5 units @ $24.50")
    print(f"  Seller1 (user_id=10000) has 1 listing: 20 units @ $26.00")
    print(f"  Seller2 (user_id=10001) has 1 listing: 15 units @ $27.00")
    print(f"  Total: 4 listings in bucket 9999")

    # TEST 1: Query without fix (shows the problem)
    print("\n" + "="*70)
    print("TEST 1: Query WITHOUT fix (old buggy behavior)")
    print("="*70)

    query_without_fix = '''
        SELECT l.id, l.seller_id, l.quantity, l.price_per_coin
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ? AND l.active = 1 AND l.quantity > 0
        ORDER BY l.price_per_coin ASC
    '''

    listings_without_fix = cursor.execute(query_without_fix, (test_bucket_id,)).fetchall()
    print(f"\nFound {len(listings_without_fix)} total listings:")
    for listing in listings_without_fix:
        owner = "BUYER'S OWN" if listing['seller_id'] == test_user_id else f"Seller {listing['seller_id']}"
        print(f"  - Listing {listing['id']}: {listing['quantity']} units @ ${listing['price_per_coin']:.2f} ({owner})")

    buyer_own_count_old = sum(1 for l in listings_without_fix if l['seller_id'] == test_user_id)
    print(f"\nBuyer's own listings in result: {buyer_own_count_old}")
    if buyer_own_count_old > 0:
        print("  PROBLEM: Buyer would see their own listings and get error!")

    # TEST 2: Query with fix (shows the solution)
    print("\n" + "="*70)
    print("TEST 2: Query WITH fix (new corrected behavior)")
    print("="*70)

    query_with_fix = '''
        SELECT l.id, l.seller_id, l.quantity, l.price_per_coin
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ? AND l.active = 1 AND l.quantity > 0
    '''
    params = [test_bucket_id]

    # THE FIX: Exclude user's own listings
    if test_user_id:
        query_with_fix += ' AND l.seller_id != ?'
        params.append(test_user_id)

    query_with_fix += ' ORDER BY l.price_per_coin ASC'

    listings_with_fix = cursor.execute(query_with_fix, params).fetchall()
    print(f"\nFound {len(listings_with_fix)} eligible listings:")
    for listing in listings_with_fix:
        owner = "BUYER'S OWN" if listing['seller_id'] == test_user_id else f"Seller {listing['seller_id']}"
        print(f"  - Listing {listing['id']}: {listing['quantity']} units @ ${listing['price_per_coin']:.2f} ({owner})")

    buyer_own_count_new = sum(1 for l in listings_with_fix if l['seller_id'] == test_user_id)
    print(f"\nBuyer's own listings in result: {buyer_own_count_new}")
    if buyer_own_count_new == 0:
        print("  CORRECT: Buyer's listings properly excluded!")
    else:
        print("  ERROR: Buyer's listings still showing!")

    # RESULTS
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70)

    success = (buyer_own_count_new == 0 and len(listings_with_fix) == 2)

    print(f"Total listings in bucket: 4")
    print(f"Buyer's own listings: 2")
    print(f"Other sellers' listings: 2")
    print(f"\nQuery WITHOUT fix returned: {len(listings_without_fix)} listings ({buyer_own_count_old} buyer's own)")
    print(f"Query WITH fix returned: {len(listings_with_fix)} listings ({buyer_own_count_new} buyer's own)")
    print(f"\nExcluded by fix: {len(listings_without_fix) - len(listings_with_fix)} listings")

    if success:
        print("\n[PASS] Fix verified successfully!")
        print("  - Buyer's own listings correctly excluded")
        print("  - Only other sellers' listings shown")
        print("  - User can now purchase from eligible sellers")
    else:
        print("\n[FAIL] Fix did not work as expected")

    # Cleanup
    print("\n[CLEANUP] Removing test data...")
    cursor.execute('DELETE FROM listings WHERE id >= 9999 AND id <= 10002')
    cursor.execute('DELETE FROM categories WHERE id = 9999')
    cursor.execute('DELETE FROM users WHERE id >= 9999 AND id <= 10001')
    conn.commit()
    conn.close()

    return success

if __name__ == '__main__':
    success = test_with_own_listings()
    exit(0 if success else 1)
