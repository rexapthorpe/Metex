"""
Comprehensive test for edit listing flow to identify why listings disappear
"""

from database import get_db_connection
import sqlite3

def test_edit_listing_flow():
    """Simulate the complete edit listing flow"""

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row

    print("=" * 70)
    print("TESTING EDIT LISTING FLOW")
    print("=" * 70)

    # Step 1: Find an active listing
    print("\n1. Finding active listings...")
    active_listings = conn.execute('''
        SELECT l.id, l.quantity, l.active, l.seller_id, l.category_id,
               c.bucket_id, c.metal, c.product_type
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.active = 1 AND l.quantity > 0
    ''').fetchall()

    print(f"   Found {len(active_listings)} active listings")
    for listing in active_listings:
        print(f"   - Listing {listing['id']}: qty={listing['quantity']}, "
              f"active={listing['active']}, seller={listing['seller_id']}, "
              f"category={listing['category_id']}, bucket={listing['bucket_id']}")

    if not active_listings:
        print("\n   ERROR: No active listings found to test!")
        conn.close()
        return

    # Use the first listing for testing
    test_listing = active_listings[0]
    listing_id = test_listing['id']
    seller_id = test_listing['seller_id']
    original_qty = test_listing['quantity']
    original_category = test_listing['category_id']

    print(f"\n2. Testing with Listing {listing_id}")
    print(f"   Original: qty={original_qty}, category={original_category}, active={test_listing['active']}")

    # Step 2: Check the account page query (how listings are displayed)
    print("\n3. Testing account page query (before edit)...")
    account_listings = conn.execute(
        """SELECT l.id   AS listing_id,
                l.quantity,
                l.price_per_coin,
                l.graded,
                l.grading_service,
                l.active,
                c.id AS category_id,
                c.bucket_id,
                c.metal, c.product_type
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.seller_id = ?
            AND l.active = 1
            AND l.quantity > 0
        """, (seller_id,)
    ).fetchall()

    print(f"   Account page shows {len(account_listings)} listings for seller {seller_id}")
    for listing in account_listings:
        print(f"   - Listing {listing['listing_id']}: qty={listing['quantity']}, "
              f"active={listing['active']}, bucket_id={listing['bucket_id']}")

    # Step 3: Simulate editing the listing (change quantity slightly)
    new_quantity = original_qty + 1
    print(f"\n4. Simulating edit: changing quantity from {original_qty} to {new_quantity}")

    conn.execute(
        '''
        UPDATE listings
           SET quantity = ?,
               active = 1
         WHERE id = ?
        ''',
        (new_quantity, listing_id)
    )
    conn.commit()

    # Step 4: Check if listing is still in database
    print("\n5. Checking listing in database after edit...")
    updated_listing = conn.execute(
        'SELECT id, quantity, active FROM listings WHERE id = ?',
        (listing_id,)
    ).fetchone()

    if updated_listing:
        print(f"   [OK] Listing {listing_id} found in DB: qty={updated_listing['quantity']}, active={updated_listing['active']}")
    else:
        print(f"   [ERROR] Listing {listing_id} NOT FOUND in database!")

    # Step 5: Check if listing appears in account page query
    print("\n6. Testing account page query (after edit)...")
    account_listings_after = conn.execute(
        """SELECT l.id   AS listing_id,
                l.quantity,
                l.price_per_coin,
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

    print(f"   Account page shows {len(account_listings_after)} listings for seller {seller_id}")

    found_in_account_query = False
    for listing in account_listings_after:
        print(f"   - Listing {listing['listing_id']}: qty={listing['quantity']}, active={listing['active']}")
        if listing['listing_id'] == listing_id:
            found_in_account_query = True

    if found_in_account_query:
        print(f"   [OK] Listing {listing_id} appears in account page query")
    else:
        print(f"   [ERROR] Listing {listing_id} DOES NOT appear in account page query!")
        print(f"   Investigating why...")

        # Debug: Check the listing's current state
        debug_listing = conn.execute(
            '''SELECT l.*, c.bucket_id
               FROM listings l
               LEFT JOIN categories c ON l.category_id = c.id
               WHERE l.id = ?''',
            (listing_id,)
        ).fetchone()

        if debug_listing:
            print(f"   Listing details:")
            print(f"     - ID: {debug_listing['id']}")
            print(f"     - Quantity: {debug_listing['quantity']}")
            print(f"     - Active: {debug_listing['active']}")
            print(f"     - Seller ID: {debug_listing['seller_id']}")
            print(f"     - Category ID: {debug_listing['category_id']}")
            print(f"     - Bucket ID: {debug_listing['bucket_id']}")

            print(f"\n   Checking each WHERE clause condition:")
            print(f"     - seller_id = {seller_id}? {debug_listing['seller_id'] == seller_id}")
            print(f"     - active = 1? {debug_listing['active'] == 1}")
            print(f"     - quantity > 0? {debug_listing['quantity'] > 0}")

            if debug_listing['bucket_id'] is None:
                print(f"     [ISSUE] bucket_id is NULL!")

    # Rollback the test change
    print("\n7. Rolling back test changes...")
    conn.execute(
        'UPDATE listings SET quantity = ? WHERE id = ?',
        (original_qty, listing_id)
    )
    conn.commit()

    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)

    conn.close()

if __name__ == '__main__':
    test_edit_listing_flow()
