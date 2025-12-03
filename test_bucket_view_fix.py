"""
Test the fix for view_bucket route to properly query by bucket_id
"""

from database import get_db_connection
import sqlite3

def test_bucket_view_queries():
    """Test that bucket view queries work correctly with bucket_id"""

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row

    print("=" * 70)
    print("TESTING BUCKET VIEW QUERY FIX")
    print("=" * 70)

    # Get a bucket_id that has listings
    test_listing = conn.execute('''
        SELECT l.id, c.bucket_id, c.id as category_id, l.seller_id
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.active = 1 AND l.quantity > 0
        LIMIT 1
    ''').fetchone()

    if not test_listing:
        print("\n[ERROR] No active listings found for testing!")
        conn.close()
        return False

    bucket_id = test_listing['bucket_id']
    seller_id = test_listing['seller_id']

    print(f"\n1. Testing with bucket_id: {bucket_id}")
    print(f"   (has category_id: {test_listing['category_id']})")

    # Test: Get all categories in this bucket
    print(f"\n2. Finding all categories in bucket {bucket_id}...")
    categories = conn.execute(
        'SELECT id FROM categories WHERE bucket_id = ?',
        (bucket_id,)
    ).fetchall()
    category_ids = [row['id'] for row in categories]
    print(f"   Found {len(category_ids)} categories: {category_ids}")

    # Test: WRONG query (current implementation)
    print(f"\n3. Testing WRONG query (WHERE category_id = {bucket_id})...")
    wrong_listings = conn.execute(
        'SELECT * FROM listings WHERE category_id = ? AND active = 1',
        (bucket_id,)
    ).fetchall()
    print(f"   Result: {len(wrong_listings)} listings found")
    if len(wrong_listings) == 0:
        print("   [ERROR] This is why we get 'Item not found'!")

    # Test: CORRECT query using JOIN
    print(f"\n4. Testing CORRECT query (JOIN with categories)...")
    correct_listings = conn.execute('''
        SELECT l.*
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ? AND l.active = 1
    ''', (bucket_id,)).fetchall()
    print(f"   Result: {len(correct_listings)} listings found")

    # Test: Filter out current user's listings
    print(f"\n5. Testing user filter (exclude seller {seller_id})...")
    filtered_listings = conn.execute('''
        SELECT l.*
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ? AND l.active = 1 AND l.seller_id != ?
    ''', (bucket_id, seller_id)).fetchall()
    print(f"   Result: {len(filtered_listings)} listings available to buy")

    if len(filtered_listings) == 0 and len(correct_listings) > 0:
        print(f"   [OK] User is the only seller - page should show 'no listings available'")

    # Test: Availability query
    print(f"\n6. Testing availability query...")
    availability = conn.execute('''
        SELECT MIN(l.price_per_coin) AS lowest_price,
               SUM(l.quantity) AS total_available
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ? AND l.active = 1
    ''', (bucket_id,)).fetchone()
    print(f"   Lowest price: ${availability['lowest_price']}")
    print(f"   Total available: {availability['total_available']}")

    # Test: Bids query
    print(f"\n7. Testing bids query...")
    bids = conn.execute('''
        SELECT b.*, u.username AS buyer_name
        FROM bids b
        JOIN users u ON b.buyer_id = u.id
        JOIN categories c ON b.category_id = c.id
        WHERE c.bucket_id = ? AND b.active = 1
    ''', (bucket_id,)).fetchall()
    print(f"   Result: {len(bids)} active bids found")

    # Test: Sellers query
    print(f"\n8. Testing sellers query...")
    sellers = conn.execute('''
        SELECT
          u.id AS seller_id,
          u.username AS username,
          MIN(l.price_per_coin) AS lowest_price,
          SUM(l.quantity) AS total_qty
        FROM listings AS l
        JOIN categories c ON l.category_id = c.id
        JOIN users AS u ON u.id = l.seller_id
        WHERE c.bucket_id = ? AND l.active = 1 AND l.quantity > 0
        GROUP BY u.id, u.username
        ORDER BY lowest_price ASC
    ''', (bucket_id,)).fetchall()
    print(f"   Result: {len(sellers)} sellers found")
    for seller in sellers:
        print(f"      - {seller['username']}: {seller['total_qty']} @ ${seller['lowest_price']}")

    conn.close()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Wrong query (category_id = bucket_id): {len(wrong_listings)} results")
    print(f"Correct query (JOIN with categories):  {len(correct_listings)} results")
    print(f"Available to buy (excluding user):     {len(filtered_listings)} results")
    print("\nFix: All queries must JOIN with categories table using bucket_id")
    print("=" * 70)

    return True

if __name__ == '__main__':
    test_bucket_view_queries()
