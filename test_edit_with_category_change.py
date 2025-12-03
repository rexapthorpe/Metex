"""
Test edit listing flow with category changes (simulating real edit modal behavior)
"""

from database import get_db_connection
from utils.category_manager import get_or_create_category
import sqlite3

def test_edit_with_category_change():
    """Simulate editing a listing with category change"""

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row

    print("=" * 70)
    print("TESTING EDIT LISTING WITH CATEGORY CHANGE")
    print("=" * 70)

    # Step 1: Find an active listing
    print("\n1. Finding active listings...")
    active_listings = conn.execute('''
        SELECT l.id, l.quantity, l.active, l.seller_id, l.category_id, l.price_per_coin,
               l.graded, l.grading_service,
               c.bucket_id, c.metal, c.product_line, c.product_type, c.weight,
               c.purity, c.mint, c.year, c.finish, c.grade
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.active = 1 AND l.quantity > 0
        LIMIT 1
    ''').fetchone()

    if not active_listings:
        print("   ERROR: No active listings found!")
        conn.close()
        return

    listing_id = active_listings['id']
    seller_id = active_listings['seller_id']
    original_category_id = active_listings['category_id']
    original_bucket_id = active_listings['bucket_id']

    print(f"   Testing with Listing {listing_id}")
    print(f"   Original: category={original_category_id}, bucket={original_bucket_id}")
    print(f"   Metal: {active_listings['metal']}, Type: {active_listings['product_type']}")
    print(f"   Year: {active_listings['year']}, Finish: {active_listings['finish']}")

    # Step 2: Simulate editing with category change (change finish)
    print("\n2. Simulating edit with category change...")
    print(f"   Original finish: {active_listings['finish']}")

    # Change the finish (this should create/reuse a different category)
    new_finish = "Proof" if active_listings['finish'] != "Proof" else "Brilliant Uncirculated"
    print(f"   New finish: {new_finish}")

    category_spec = {
        'metal': active_listings['metal'],
        'product_line': active_listings['product_line'],
        'product_type': active_listings['product_type'],
        'weight': active_listings['weight'],
        'purity': active_listings['purity'],
        'mint': active_listings['mint'],
        'year': active_listings['year'],
        'finish': new_finish,  # CHANGED
        'grade': active_listings['grade']
    }

    new_cat_id = get_or_create_category(conn, category_spec)
    print(f"   New category ID: {new_cat_id}")

    # Get the bucket_id of the new category
    new_category = conn.execute(
        'SELECT id, bucket_id FROM categories WHERE id = ?',
        (new_cat_id,)
    ).fetchone()

    print(f"   New bucket ID: {new_category['bucket_id']}")

    # Simulate the UPDATE query from listings_routes.py
    new_quantity = active_listings['quantity']
    new_price = active_listings['price_per_coin']
    graded = active_listings['graded']
    grading_service = active_listings['grading_service']

    print(f"\n3. Executing UPDATE query...")
    conn.execute(
        '''
        UPDATE listings
           SET category_id     = ?,
               quantity        = ?,
               price_per_coin  = ?,
               graded          = ?,
               grading_service = ?,
               active          = 1
         WHERE id = ?
        ''',
        (new_cat_id, new_quantity, new_price, graded, grading_service, listing_id)
    )
    conn.commit()
    print(f"   UPDATE executed successfully")

    # Step 3: Verify listing is in database
    print(f"\n4. Checking listing in database...")
    updated_listing = conn.execute(
        '''SELECT l.id, l.category_id, l.quantity, l.active, c.bucket_id
           FROM listings l
           LEFT JOIN categories c ON l.category_id = c.id
           WHERE l.id = ?''',
        (listing_id,)
    ).fetchone()

    if updated_listing:
        print(f"   [OK] Listing found:")
        print(f"     - ID: {updated_listing['id']}")
        print(f"     - Category ID: {updated_listing['category_id']}")
        print(f"     - Bucket ID: {updated_listing['bucket_id']}")
        print(f"     - Quantity: {updated_listing['quantity']}")
        print(f"     - Active: {updated_listing['active']}")
    else:
        print(f"   [ERROR] Listing not found in database!")

    # Step 4: Check if it appears in account page query
    print(f"\n5. Testing account page query...")
    account_listings = conn.execute(
        """SELECT l.id   AS listing_id,
                l.quantity,
                l.active,
                c.id AS category_id,
                c.bucket_id
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.seller_id = ?
            AND l.active = 1
            AND l.quantity > 0
        """, (seller_id,)
    ).fetchall()

    print(f"   Account page query returned {len(account_listings)} listings")

    found = False
    for listing in account_listings:
        print(f"   - Listing {listing['listing_id']}: qty={listing['quantity']}, "
              f"active={listing['active']}, bucket_id={listing['bucket_id']}")
        if listing['listing_id'] == listing_id:
            found = True

    if found:
        print(f"   [OK] Listing {listing_id} appears in account page query")
    else:
        print(f"   [ERROR] Listing {listing_id} NOT in account page query!")

    # Step 5: Check if the new category has a bucket_id
    print(f"\n6. Verifying new category has bucket_id...")
    category_check = conn.execute(
        'SELECT id, bucket_id FROM categories WHERE id = ?',
        (new_cat_id,)
    ).fetchone()

    if category_check:
        if category_check['bucket_id'] is not None:
            print(f"   [OK] Category {new_cat_id} has bucket_id={category_check['bucket_id']}")
        else:
            print(f"   [ERROR] Category {new_cat_id} has NULL bucket_id!")
    else:
        print(f"   [ERROR] Category {new_cat_id} not found!")

    # Rollback changes
    print(f"\n7. Rolling back changes...")
    conn.execute(
        'UPDATE listings SET category_id = ? WHERE id = ?',
        (original_category_id, listing_id)
    )
    conn.commit()

    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)

    conn.close()

if __name__ == '__main__':
    test_edit_with_category_change()
