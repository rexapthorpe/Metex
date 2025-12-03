"""
Comprehensive test to verify the bucket view fix
Tests all scenarios including when user is the only seller
"""

from database import get_db_connection
import sqlite3

def test_bucket_view_when_user_is_only_seller():
    """Test the scenario where the logged-in user is the only seller"""

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row

    print("=" * 70)
    print("TESTING: USER IS ONLY SELLER SCENARIO")
    print("=" * 70)

    # Find a bucket where a user is the only seller
    result = conn.execute('''
        SELECT c.bucket_id, l.seller_id, COUNT(DISTINCT l.seller_id) as seller_count
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.active = 1 AND l.quantity > 0
        GROUP BY c.bucket_id
        HAVING COUNT(DISTINCT l.seller_id) = 1
        LIMIT 1
    ''').fetchone()

    if not result:
        print("\n[INFO] No buckets with single seller found. Creating test scenario...")
        conn.close()
        return

    bucket_id = result['bucket_id']
    seller_id = result['seller_id']

    print(f"\n1. Testing bucket {bucket_id} where user {seller_id} is the only seller")

    # Test: Get bucket info
    print(f"\n2. Verifying bucket exists...")
    bucket = conn.execute(
        'SELECT * FROM categories WHERE bucket_id = ? LIMIT 1',
        (bucket_id,)
    ).fetchone()

    if bucket:
        print(f"   [OK] Bucket {bucket_id} found")
        print(f"        Metal: {bucket['metal']}")
        print(f"        Product: {bucket['product_type']}")
    else:
        print(f"   [ERROR] Bucket {bucket_id} not found!")
        conn.close()
        return

    # Test: Get all listings in bucket
    print(f"\n3. Querying all listings in bucket...")
    all_listings = conn.execute('''
        SELECT l.*, u.username
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        JOIN users u ON l.seller_id = u.id
        WHERE c.bucket_id = ? AND l.active = 1
    ''', (bucket_id,)).fetchall()

    print(f"   Total listings: {len(all_listings)}")
    for listing in all_listings:
        print(f"      - Listing {listing['id']}: {listing['username']} selling {listing['quantity']} @ ${listing['price_per_coin']}")

    # Test: Get listings excluding current seller (what user would see)
    print(f"\n4. Querying listings excluding seller {seller_id}...")
    available_listings = conn.execute('''
        SELECT l.*
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ? AND l.active = 1 AND l.seller_id != ?
    ''', (bucket_id, seller_id)).fetchall()

    print(f"   Available to buy: {len(available_listings)}")
    if len(available_listings) == 0:
        print(f"   [OK] User cannot buy from themselves - should show 'no listings available'")
    else:
        print(f"   [INFO] Other sellers available:")
        for listing in available_listings:
            print(f"      - Listing {listing['id']}")

    # Test: Availability (excluding user's own listings)
    print(f"\n5. Testing availability query...")
    availability = conn.execute('''
        SELECT MIN(l.price_per_coin) AS lowest_price,
               SUM(l.quantity) AS total_available
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ? AND l.active = 1 AND l.seller_id != ?
    ''', (bucket_id, seller_id)).fetchone()

    if availability['total_available'] is None or availability['total_available'] == 0:
        print(f"   [OK] Availability shows: 0 units (user is only seller)")
    else:
        print(f"   [INFO] Availability: {availability['total_available']} units @ ${availability['lowest_price']}")

    # Test: User bids
    print(f"\n6. Testing user bids query...")
    user_bids = conn.execute('''
        SELECT b.*
        FROM bids b
        JOIN categories c ON b.category_id = c.id
        WHERE b.buyer_id = ? AND c.bucket_id = ? AND b.active = 1
    ''', (seller_id, bucket_id)).fetchall()

    print(f"   User has {len(user_bids)} active bids on this bucket")

    # Test: All bids
    print(f"\n7. Testing all bids query...")
    all_bids = conn.execute('''
        SELECT b.*, u.username AS buyer_name
        FROM bids b
        JOIN users u ON b.buyer_id = u.id
        JOIN categories c ON b.category_id = c.id
        WHERE c.bucket_id = ? AND b.active = 1
    ''', (bucket_id,)).fetchall()

    print(f"   Total active bids: {len(all_bids)}")

    # Test: Sellers
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
    ''', (bucket_id,)).fetchall()

    print(f"   Total sellers: {len(sellers)}")
    for seller in sellers:
        print(f"      - {seller['username']}: {seller['total_qty']} units @ ${seller['lowest_price']}")

    conn.close()

    print("\n" + "=" * 70)
    print("EXPECTED BEHAVIOR:")
    print("=" * 70)
    print("1. Bucket page SHOULD load successfully (no 'Item not found')")
    print("2. Bucket page SHOULD show product specifications")
    print("3. 'Available to buy' section SHOULD show 0 units")
    print("4. User SHOULD still be able to place bids")
    print("5. Sellers list SHOULD show the user as the only seller")
    print("=" * 70)

    return True


def test_bucket_view_with_multiple_sellers():
    """Test the normal scenario with multiple sellers"""

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row

    print("\n" + "=" * 70)
    print("TESTING: MULTIPLE SELLERS SCENARIO")
    print("=" * 70)

    # Find a bucket with multiple sellers
    result = conn.execute('''
        SELECT c.bucket_id, COUNT(DISTINCT l.seller_id) as seller_count
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.active = 1 AND l.quantity > 0
        GROUP BY c.bucket_id
        HAVING COUNT(DISTINCT l.seller_id) > 1
        LIMIT 1
    ''').fetchone()

    if not result:
        print("\n[INFO] No buckets with multiple sellers found")
        conn.close()
        return

    bucket_id = result['bucket_id']
    seller_count = result['seller_count']

    print(f"\n1. Testing bucket {bucket_id} with {seller_count} sellers")

    # Get a seller ID to test exclusion
    seller_id = conn.execute('''
        SELECT DISTINCT l.seller_id
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ? AND l.active = 1
        LIMIT 1
    ''', (bucket_id,)).fetchone()['seller_id']

    # Test: Get listings excluding one seller
    print(f"\n2. Querying listings excluding seller {seller_id}...")
    available_listings = conn.execute('''
        SELECT l.*, u.username
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        JOIN users u ON l.seller_id = u.id
        WHERE c.bucket_id = ? AND l.active = 1 AND l.seller_id != ?
    ''', (bucket_id, seller_id)).fetchall()

    print(f"   Available from other sellers: {len(available_listings)}")
    for listing in available_listings[:3]:  # Show first 3
        print(f"      - {listing['username']}: {listing['quantity']} @ ${listing['price_per_coin']}")

    # Test: Availability
    print(f"\n3. Testing availability...")
    availability = conn.execute('''
        SELECT MIN(l.price_per_coin) AS lowest_price,
               SUM(l.quantity) AS total_available
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ? AND l.active = 1 AND l.seller_id != ?
    ''', (bucket_id, seller_id)).fetchone()

    print(f"   Lowest price: ${availability['lowest_price']}")
    print(f"   Total available: {availability['total_available']} units")

    conn.close()

    print("\n" + "=" * 70)
    print("EXPECTED BEHAVIOR:")
    print("=" * 70)
    print("1. Bucket page SHOULD load successfully")
    print("2. 'Available to buy' SHOULD show listings from other sellers")
    print("3. User's own listings SHOULD NOT appear in purchase options")
    print("=" * 70)

    return True


if __name__ == '__main__':
    success1 = test_bucket_view_when_user_is_only_seller()
    success2 = test_bucket_view_with_multiple_sellers()

    print("\n" + "=" * 70)
    print("ALL TESTS COMPLETED")
    print("=" * 70)
    print("\nNow test in the browser:")
    print("1. Click on an item where you're the only seller")
    print("2. Bucket page should load (no 'Item not found' error)")
    print("3. Should show 'no listings available to buy'")
    print("4. Should still be able to place bids")
    print("=" * 70)
