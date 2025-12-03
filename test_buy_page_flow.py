"""
Test the complete flow from buy page to bucket page
Simulates what happens when a user clicks an item
"""

from database import get_db_connection
import sqlite3

def test_buy_page_to_bucket_flow():
    """Simulate clicking an item on the buy page"""

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row

    print("=" * 70)
    print("TESTING: BUY PAGE TO BUCKET PAGE FLOW")
    print("=" * 70)

    # Step 1: Simulate the buy page query (what data does buy page show?)
    print("\n1. SIMULATING BUY PAGE QUERY")
    print("-" * 70)

    buy_page_query = '''
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
        LIMIT 5
    '''

    buy_items = conn.execute(buy_page_query).fetchall()

    print(f"Buy page shows {len(buy_items)} items:")
    for item in buy_items:
        print(f"\n   Item:")
        print(f"      category_id: {item['category_id']}")
        print(f"      bucket_id: {item['bucket_id']}")
        print(f"      {item['metal']} {item['product_type']}")
        print(f"      Price: ${item['lowest_price']}")

    if not buy_items:
        print("\n[ERROR] No items on buy page!")
        conn.close()
        return False

    # Step 2: Simulate clicking on first item
    print("\n\n2. SIMULATING USER CLICK ON FIRST ITEM")
    print("-" * 70)

    first_item = buy_items[0]

    # The question is: what ID does the tile link to?
    # It should link to the bucket_id, not category_id

    print(f"\nItem clicked:")
    print(f"   category_id: {first_item['category_id']}")
    print(f"   bucket_id: {first_item['bucket_id']}")

    # Step 3: Try accessing bucket by bucket_id (correct way)
    print(f"\n\n3. TESTING: Access bucket page using bucket_id = {first_item['bucket_id']}")
    print("-" * 70)

    bucket_by_bucket_id = conn.execute(
        'SELECT * FROM categories WHERE bucket_id = ? LIMIT 1',
        (first_item['bucket_id'],)
    ).fetchone()

    if bucket_by_bucket_id:
        print(f"   [OK] Found bucket using bucket_id")
        print(f"        Category ID: {bucket_by_bucket_id['id']}")
        print(f"        Bucket ID: {bucket_by_bucket_id['bucket_id']}")
        print(f"        {bucket_by_bucket_id['metal']} {bucket_by_bucket_id['product_type']}")
    else:
        print(f"   [ERROR] No bucket found with bucket_id = {first_item['bucket_id']}")

    # Step 4: Try accessing bucket by category_id (wrong way, but might be what's happening)
    print(f"\n\n4. TESTING: Access bucket page using category_id = {first_item['category_id']}")
    print("-" * 70)

    bucket_by_category_id = conn.execute(
        'SELECT * FROM categories WHERE bucket_id = ? LIMIT 1',
        (first_item['category_id'],)
    ).fetchone()

    if bucket_by_category_id:
        print(f"   [WRONG] Found bucket using category_id as bucket_id")
        print(f"        This would be incorrect!")
    else:
        print(f"   [EXPECTED] No bucket found with bucket_id = {first_item['category_id']}")
        print(f"        This is correct - category_id should not be used as bucket_id")

    # Step 5: Check what the template should be using
    print(f"\n\n5. CHECKING: What should the template link to?")
    print("-" * 70)

    print(f"\n   The buy page tile should link to:")
    print(f"   /bucket/{first_item['bucket_id']}")
    print(f"\n   NOT to:")
    print(f"   /bucket/{first_item['category_id']}")

    # Step 6: Test all items on buy page
    print(f"\n\n6. TESTING ALL BUY PAGE ITEMS")
    print("-" * 70)

    all_pass = True
    for i, item in enumerate(buy_items):
        bucket = conn.execute(
            'SELECT * FROM categories WHERE bucket_id = ? LIMIT 1',
            (item['bucket_id'],)
        ).fetchone()

        if bucket:
            print(f"   [OK] Item {i+1}: bucket_id {item['bucket_id']} -> Found bucket")
        else:
            print(f"   [ERROR] Item {i+1}: bucket_id {item['bucket_id']} -> NO BUCKET FOUND!")
            all_pass = False

    conn.close()

    print("\n" + "=" * 70)
    print("DIAGNOSIS")
    print("=" * 70)

    if all_pass:
        print("\n✅ All bucket_ids from buy page can be accessed")
        print("\nThe issue might be:")
        print("1. Template is using wrong field (category_id instead of bucket_id)")
        print("2. OR there's a JavaScript/routing issue")
        print("\nNeed to check buy.html template!")
    else:
        print("\n❌ Some bucket_ids cannot be accessed")
        print("\nThe database might have inconsistent bucket_id values")

    print("=" * 70)

    return all_pass

if __name__ == '__main__':
    test_buy_page_to_bucket_flow()
