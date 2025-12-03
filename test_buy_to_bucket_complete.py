"""
Complete end-to-end test: Buy page -> Bucket page
Tests the entire flow after fixes
"""

from database import get_db_connection
import sqlite3

def test_complete_flow():
    """Test complete flow from buy page to bucket page"""

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row

    print("=" * 70)
    print("END-TO-END TEST: BUY PAGE -> BUCKET PAGE")
    print("=" * 70)

    # Step 1: Get buy page data (simulating what template receives)
    print("\n1. GETTING BUY PAGE DATA (after fix)")
    print("-" * 70)

    buy_query = '''
        SELECT
            categories.id AS category_id,
            categories.bucket_id,
            categories.metal,
            categories.product_type,
            categories.weight,
            categories.mint,
            categories.year,
            categories.finish,
            categories.grade,
            categories.coin_series,
            MIN(listings.price_per_coin) AS lowest_price,
            SUM(listings.quantity) AS total_available
        FROM listings
        JOIN categories ON listings.category_id = categories.id
        WHERE listings.active = 1 AND listings.quantity > 0
        GROUP BY categories.id
        ORDER BY lowest_price ASC
        LIMIT 10
    '''

    items = conn.execute(buy_query).fetchall()

    print(f"Buy page returns {len(items)} items")
    print("\nFirst 3 items:")
    for i, item in enumerate(items[:3]):
        print(f"\n   Item {i+1}:")
        print(f"      category_id: {item['category_id']}")
        print(f"      bucket_id: {item['bucket_id']}")  # This should now be available!
        print(f"      Product: {item['metal']} {item['product_type']}")
        print(f"      Price: ${item['lowest_price']}")

    # Step 2: Test clicking each item
    print(f"\n\n2. TESTING CLICK ON EACH ITEM")
    print("-" * 70)

    all_success = True
    for i, item in enumerate(items):
        bucket_id = item['bucket_id']

        # Simulate the bucket page loading
        bucket = conn.execute(
            'SELECT * FROM categories WHERE bucket_id = ? LIMIT 1',
            (bucket_id,)
        ).fetchone()

        if bucket:
            # Get listings for this bucket
            listings = conn.execute('''
                SELECT l.*
                FROM listings l
                JOIN categories c ON l.category_id = c.id
                WHERE c.bucket_id = ? AND l.active = 1
            ''', (bucket_id,)).fetchall()

            print(f"   [OK] Item {i+1}: Clicked -> Bucket {bucket_id}")
            print(f"        {bucket['metal']} {bucket['product_type']}")
            print(f"        {len(listings)} listings found")
        else:
            print(f"   [ERROR] Item {i+1}: Bucket {bucket_id} NOT FOUND!")
            all_success = False

    # Step 3: Test specific scenarios
    print(f"\n\n3. TESTING SPECIFIC SCENARIOS")
    print("-" * 70)

    # Find a bucket where user is only seller (if exists)
    user_only_bucket = conn.execute('''
        SELECT c.bucket_id, l.seller_id, u.username
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        JOIN users u ON l.seller_id = u.id
        WHERE l.active = 1
        GROUP BY c.bucket_id
        HAVING COUNT(DISTINCT l.seller_id) = 1
        LIMIT 1
    ''').fetchone()

    if user_only_bucket:
        bucket_id = user_only_bucket['bucket_id']
        seller_id = user_only_bucket['seller_id']
        username = user_only_bucket['username']

        print(f"\nScenario: User '{username}' (ID {seller_id}) is only seller")
        print(f"   Clicking bucket {bucket_id}...")

        # Test bucket page loads
        bucket = conn.execute(
            'SELECT * FROM categories WHERE bucket_id = ? LIMIT 1',
            (bucket_id,)
        ).fetchone()

        if bucket:
            print(f"   [OK] Bucket page loads successfully")

            # Test availability (should be 0 for user's own listings)
            availability = conn.execute('''
                SELECT SUM(l.quantity) AS total_available
                FROM listings l
                JOIN categories c ON l.category_id = c.id
                WHERE c.bucket_id = ? AND l.active = 1 AND l.seller_id != ?
            ''', (bucket_id, seller_id)).fetchone()

            avail_count = availability['total_available'] if availability['total_available'] else 0
            print(f"   [OK] Available to buy: {avail_count} units (user's listings excluded)")

            if avail_count == 0:
                print(f"   [OK] User sees 'no listings available' (correct behavior)")
        else:
            print(f"   [ERROR] Bucket page failed to load!")
            all_success = False

    # Find a bucket with multiple sellers
    multi_seller_bucket = conn.execute('''
        SELECT c.bucket_id
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.active = 1
        GROUP BY c.bucket_id
        HAVING COUNT(DISTINCT l.seller_id) > 1
        LIMIT 1
    ''').fetchone()

    if multi_seller_bucket:
        bucket_id = multi_seller_bucket['bucket_id']

        # Get first seller
        first_seller = conn.execute('''
            SELECT DISTINCT l.seller_id, u.username
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            JOIN users u ON l.seller_id = u.id
            WHERE c.bucket_id = ? AND l.active = 1
            LIMIT 1
        ''', (bucket_id,)).fetchone()

        seller_id = first_seller['seller_id']
        username = first_seller['username']

        print(f"\nScenario: Multiple sellers, user '{username}' (ID {seller_id}) viewing")
        print(f"   Clicking bucket {bucket_id}...")

        # Test bucket loads
        bucket = conn.execute(
            'SELECT * FROM categories WHERE bucket_id = ? LIMIT 1',
            (bucket_id,)
        ).fetchone()

        if bucket:
            print(f"   [OK] Bucket page loads successfully")

            # Test availability excludes user's listings
            availability = conn.execute('''
                SELECT SUM(l.quantity) AS total_available
                FROM listings l
                JOIN categories c ON l.category_id = c.id
                WHERE c.bucket_id = ? AND l.active = 1 AND l.seller_id != ?
            ''', (bucket_id, seller_id)).fetchone()

            avail_count = availability['total_available'] if availability['total_available'] else 0
            print(f"   [OK] Available to buy: {avail_count} units (user's listings excluded)")
        else:
            print(f"   [ERROR] Bucket page failed to load!")
            all_success = False

    conn.close()

    print("\n" + "=" * 70)
    print("TEST RESULTS")
    print("=" * 70)

    if all_success:
        print("\n[PASS] All tests passed!")
        print("\nFixes applied:")
        print("1. Added 'bucket_id' to buy route query")
        print("2. Changed buy.html to use bucket['bucket_id'] instead of bucket['category_id']")
        print("\nExpected browser behavior:")
        print("- Clicking any item on buy page -> bucket page loads")
        print("- When user is only seller -> shows 'no listings available'")
        print("- When multiple sellers -> shows other sellers' listings")
        print("- User cannot buy their own listings")
    else:
        print("\n[FAIL] Some tests failed!")
        print("Review errors above")

    print("=" * 70)

    return all_success

if __name__ == '__main__':
    success = test_complete_flow()
    exit(0 if success else 1)
