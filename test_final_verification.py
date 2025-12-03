"""
Final end-to-end test to verify the fix works
"""

from database import get_db_connection
from utils.category_manager import get_or_create_category
import sqlite3

def test_final_verification():
    """Test complete flow: create category, edit listing, verify it persists"""

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row

    print("=" * 70)
    print("FINAL END-TO-END VERIFICATION TEST")
    print("=" * 70)

    # Step 1: Find an active listing to test
    print("\n1. Finding active listing...")
    listing = conn.execute('''
        SELECT l.id, l.seller_id, l.quantity, l.price_per_coin, l.graded, l.grading_service,
               c.metal, c.product_line, c.product_type, c.weight, c.purity, c.mint, c.year, c.finish, c.grade
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.active = 1 AND l.quantity > 0
        LIMIT 1
    ''').fetchone()

    if not listing:
        print("   [ERROR] No active listings found!")
        conn.close()
        return

    listing_id = listing['id']
    seller_id = listing['seller_id']

    print(f"   Testing with listing {listing_id} (seller {seller_id})")
    print(f"   Original: {listing['year']} {listing['metal']} {listing['product_type']}, Finish: {listing['finish']}")

    # Step 2: Simulate editing with a category change
    print("\n2. Simulating edit (changing finish)...")
    original_finish = listing['finish']
    new_finish = "Proof" if original_finish != "Proof" else "Brilliant Uncirculated"

    print(f"   Changing finish from '{original_finish}' to '{new_finish}'")

    category_spec = {
        'metal': listing['metal'],
        'product_line': listing['product_line'],
        'product_type': listing['product_type'],
        'weight': listing['weight'],
        'purity': listing['purity'],
        'mint': listing['mint'],
        'year': listing['year'],
        'finish': new_finish,  # CHANGED
        'grade': listing['grade']
    }

    # Use the same function the edit route uses
    new_cat_id = get_or_create_category(conn, category_spec)
    print(f"   New category ID: {new_cat_id}")

    # Verify the category exists and has bucket_id
    new_category = conn.execute(
        'SELECT id, bucket_id FROM categories WHERE id = ?',
        (new_cat_id,)
    ).fetchone()

    if not new_category:
        print(f"   [ERROR] Category {new_cat_id} doesn't exist!")
        conn.close()
        return

    if new_category['bucket_id'] is None:
        print(f"   [ERROR] Category {new_cat_id} has NULL bucket_id!")
        conn.close()
        return

    print(f"   [OK] Category {new_cat_id} has bucket_id={new_category['bucket_id']}")

    # Step 3: Update the listing (same as edit route)
    print("\n3. Updating listing...")
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
        (new_cat_id, listing['quantity'], listing['price_per_coin'],
         listing['graded'], listing['grading_service'], listing_id)
    )
    conn.commit()
    print(f"   [OK] Listing {listing_id} updated to category {new_cat_id}")

    # Step 4: Verify listing appears in account page query
    print("\n4. Testing account page query...")
    account_listings = conn.execute(
        """SELECT l.id AS listing_id, c.bucket_id
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.seller_id = ? AND l.active = 1 AND l.quantity > 0
        """, (seller_id,)
    ).fetchall()

    print(f"   Found {len(account_listings)} listings for seller {seller_id}")

    found = False
    for lst in account_listings:
        if lst['listing_id'] == listing_id:
            found = True
            print(f"   [OK] Listing {listing_id} found with bucket_id={lst['bucket_id']}")
            break

    if not found:
        print(f"   [ERROR] Listing {listing_id} NOT FOUND in account page query!")
        conn.close()
        return

    # Step 5: Test that we can edit it again
    print("\n5. Testing second edit (change back to original finish)...")
    category_spec['finish'] = original_finish

    second_cat_id = get_or_create_category(conn, category_spec)
    print(f"   Category ID for original finish: {second_cat_id}")

    conn.execute(
        'UPDATE listings SET category_id = ?, active = 1 WHERE id = ?',
        (second_cat_id, listing_id)
    )
    conn.commit()

    # Verify again
    account_listings_2 = conn.execute(
        """SELECT l.id AS listing_id, c.bucket_id
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.seller_id = ? AND l.active = 1 AND l.quantity > 0
        """, (seller_id,)
    ).fetchall()

    found_again = any(lst['listing_id'] == listing_id for lst in account_listings_2)

    if found_again:
        print(f"   [OK] Listing {listing_id} still appears after second edit")
    else:
        print(f"   [ERROR] Listing {listing_id} disappeared after second edit!")

    print("\n" + "=" * 70)
    if found and found_again:
        print("SUCCESS: All tests passed!")
        print("Listings no longer disappear after editing!")
    else:
        print("FAILED: Listings still disappearing")
    print("=" * 70)

    conn.close()

if __name__ == '__main__':
    test_final_verification()
