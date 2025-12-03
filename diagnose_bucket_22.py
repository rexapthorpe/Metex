"""
Diagnostic script to investigate bucket 22 issue
"""

from database import get_db_connection

def diagnose_bucket(bucket_id=22):
    """Diagnose what's happening with bucket 22"""
    print("\n" + "="*70)
    print(f"DIAGNOSING BUCKET {bucket_id}")
    print("="*70 + "\n")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get bucket/category info
    print("1. BUCKET INFORMATION:")
    print("-" * 70)
    category = cursor.execute('''
        SELECT * FROM categories WHERE bucket_id = ? LIMIT 1
    ''', (bucket_id,)).fetchone()

    if category:
        print(f"  Metal: {category['metal']}")
        print(f"  Product Type: {category['product_type']}")
        print(f"  Category ID: {category['id']}")
        print(f"  Bucket ID: {category['bucket_id']}")
    else:
        print(f"  ERROR: No category found for bucket_id={bucket_id}")
        conn.close()
        return

    # Get ALL listings for this bucket
    print(f"\n2. ALL LISTINGS IN BUCKET {bucket_id}:")
    print("-" * 70)
    all_listings = cursor.execute('''
        SELECT l.id, l.category_id, l.seller_id, l.quantity, l.price_per_coin,
               l.active, l.graded, l.grading_service,
               u.username as seller_name
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        JOIN users u ON l.seller_id = u.id
        WHERE c.bucket_id = ?
    ''', (bucket_id,)).fetchall()

    if all_listings:
        print(f"  Found {len(all_listings)} total listings:")
        for listing in all_listings:
            active_status = "ACTIVE" if listing['active'] else "INACTIVE"
            graded_status = f"Graded({listing['grading_service']})" if listing['graded'] else "Ungraded"
            print(f"    - Listing {listing['id']}: seller={listing['seller_name']}(id={listing['seller_id']}), "
                  f"qty={listing['quantity']}, price=${listing['price_per_coin']:.2f}, "
                  f"{active_status}, {graded_status}")
    else:
        print(f"  No listings found for bucket {bucket_id}")
        conn.close()
        return

    # Get active listings only
    print(f"\n3. ACTIVE LISTINGS (active=1, quantity>0):")
    print("-" * 70)
    active_listings = cursor.execute('''
        SELECT l.id, l.seller_id, l.quantity, l.price_per_coin, l.graded, l.grading_service,
               u.username as seller_name
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        JOIN users u ON l.seller_id = u.id
        WHERE c.bucket_id = ? AND l.active = 1 AND l.quantity > 0
    ''', (bucket_id,)).fetchall()

    if active_listings:
        print(f"  Found {len(active_listings)} active listings:")
        for listing in active_listings:
            print(f"    - Listing {listing['id']}: seller={listing['seller_name']}(id={listing['seller_id']}), "
                  f"qty={listing['quantity']}, price=${listing['price_per_coin']:.2f}")
    else:
        print(f"  No active listings with quantity > 0")

    # Test query WITH the fix for different users
    print(f"\n4. TESTING QUERY WITH FIX:")
    print("-" * 70)

    # Get a list of unique seller IDs
    seller_ids = list(set([l['seller_id'] for l in all_listings]))

    for test_user_id in seller_ids[:3]:  # Test with first 3 sellers
        print(f"\n  Testing as user_id={test_user_id}:")

        query = '''
            SELECT l.id, l.seller_id, l.quantity, l.price_per_coin
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE c.bucket_id = ? AND l.active = 1 AND l.quantity > 0
        '''
        params = [bucket_id]

        # Exclude user's own listings
        if test_user_id:
            query += ' AND l.seller_id != ?'
            params.append(test_user_id)

        query += ' ORDER BY l.price_per_coin ASC'

        results = cursor.execute(query, params).fetchall()

        if results:
            print(f"    Found {len(results)} eligible listings:")
            for r in results:
                print(f"      - Listing {r['id']}: seller_id={r['seller_id']}, "
                      f"qty={r['quantity']}, price=${r['price_per_coin']:.2f}")
        else:
            print(f"    No eligible listings (user may be the only seller)")

    # Check if all listings belong to one seller
    print(f"\n5. SELLER ANALYSIS:")
    print("-" * 70)
    seller_counts = {}
    for listing in active_listings:
        seller_id = listing['seller_id']
        seller_name = listing['seller_name']
        if seller_id not in seller_counts:
            seller_counts[seller_id] = {'name': seller_name, 'count': 0, 'total_qty': 0}
        seller_counts[seller_id]['count'] += 1
        seller_counts[seller_id]['total_qty'] += listing['quantity']

    if seller_counts:
        print(f"  Active listings by seller:")
        for seller_id, info in seller_counts.items():
            print(f"    - {info['name']} (id={seller_id}): {info['count']} listings, {info['total_qty']} total units")

        if len(seller_counts) == 1:
            print(f"\n  WARNING: All active listings belong to ONE seller!")
            print(f"  If that seller tries to buy, they'll get 'No matching listings' error")
    else:
        print(f"  No active sellers")

    conn.close()

if __name__ == '__main__':
    diagnose_bucket(22)
