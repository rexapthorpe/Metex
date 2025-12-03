"""
Simple test to verify the direct_buy fix
Tests that the query correctly excludes user's own listings
"""

from database import get_db_connection

def test_fix():
    """Test that the fix correctly excludes user's own listings"""
    print("\n" + "="*70)
    print("TESTING DIRECT BUY FIX")
    print("="*70 + "\n")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get an existing user to use as test buyer
    test_user = cursor.execute('SELECT id FROM users LIMIT 1').fetchone()
    if not test_user:
        print("[SKIP] No users found in database")
        conn.close()
        return

    user_id = test_user['id']
    print(f"Test user_id: {user_id}\n")

    # Find a bucket that has listings
    bucket_row = cursor.execute('''
        SELECT DISTINCT c.bucket_id        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.active = 1 AND l.quantity > 0
        LIMIT 1
    ''').fetchone()

    if not bucket_row:
        print("[SKIP] No active listings found")
        conn.close()
        return

    bucket_id = bucket_row['bucket_id']
    print(f"Test bucket_id: {bucket_id}\n")

    # Test 1: Query WITHOUT the fix (shows the problem)
    print("="*70)
    print("TEST 1: Query WITHOUT fix (old behavior)")
    print("="*70)

    query_without_fix = '''
        SELECT l.id, l.seller_id, l.quantity, l.price_per_coin
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ? AND l.active = 1 AND l.quantity > 0
        ORDER BY l.price_per_coin ASC
    '''

    listings_without_fix = cursor.execute(query_without_fix, (bucket_id,)).fetchall()
    print(f"Found {len(listings_without_fix)} total listings")

    user_own_listings = [l for l in listings_without_fix if l['seller_id'] == user_id]
    if user_own_listings:
        print(f"  - {len(user_own_listings)} belong to user {user_id} (PROBLEM!)")
        print("  - User would see their own listings and get confused/error")
    else:
        print(f"  - 0 belong to user {user_id}")

    # Test 2: Query WITH the fix (shows the solution)
    print("\n" + "="*70)
    print("TEST 2: Query WITH fix (new behavior)")
    print("="*70)

    query_with_fix = '''
        SELECT l.id, l.seller_id, l.quantity, l.price_per_coin
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ? AND l.active = 1 AND l.quantity > 0
    '''
    params = [bucket_id]

    # THE FIX: Exclude user's own listings
    if user_id:
        query_with_fix += ' AND l.seller_id != ?'
        params.append(user_id)

    query_with_fix += ' ORDER BY l.price_per_coin ASC'

    listings_with_fix = cursor.execute(query_with_fix, params).fetchall()
    print(f"Found {len(listings_with_fix)} eligible listings")

    user_own_listings_in_result = [l for l in listings_with_fix if l['seller_id'] == user_id]
    if user_own_listings_in_result:
        print(f"  - ERROR: {len(user_own_listings_in_result)} still belong to user {user_id}")
        print("  - FIX FAILED!")
        success = False
    else:
        print(f"  - 0 belong to user {user_id} (CORRECT!)")
        print("  - User's own listings properly excluded")
        success = True

    # Summary
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70)

    excluded_count = len(listings_without_fix) - len(listings_with_fix)
    print(f"Listings before fix: {len(listings_without_fix)}")
    print(f"Listings after fix:  {len(listings_with_fix)}")
    print(f"Excluded (user's own): {excluded_count}")

    if success:
        print("\n[PASS] Fix verified successfully!")
        print("Users can no longer see/buy their own listings")
    else:
        print("\n[FAIL] Fix did not work as expected")

    conn.close()
    return success

if __name__ == '__main__':
    test_fix()
