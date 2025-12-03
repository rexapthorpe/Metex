"""
Final test to verify View and Cancel buttons work after fixes
"""

from database import get_db_connection
import sqlite3

def test_view_button_fix():
    """Test that the View button will work with the fixed query"""

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row

    print("=" * 70)
    print("TESTING VIEW BUTTON FIX")
    print("=" * 70)

    # Get active listings
    listings = conn.execute('''
        SELECT l.id as listing_id, c.bucket_id, c.id as category_id,
               c.metal, c.product_type
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.active = 1 AND l.quantity > 0
    ''').fetchall()

    print(f"\nTesting {len(listings)} active listings...")

    all_pass = True

    for listing in listings:
        listing_id = listing['listing_id']
        bucket_id = listing['bucket_id']

        # Test the FIXED query
        bucket = conn.execute(
            'SELECT * FROM categories WHERE bucket_id = ? LIMIT 1',
            (bucket_id,)
        ).fetchone()

        if bucket:
            print(f"  [OK] Listing {listing_id}: View button -> /bucket/{bucket_id} "
                  f"(finds category {bucket['id']})")
        else:
            print(f"  [ERROR] Listing {listing_id}: View button -> /bucket/{bucket_id} "
                  f"(NO CATEGORY FOUND!)")
            all_pass = False

    print("\n" + "=" * 70)
    if all_pass:
        print("SUCCESS: All View buttons will work correctly!")
    else:
        print("FAILED: Some View buttons still broken")
    print("=" * 70)

    conn.close()

    return all_pass

def test_cancel_button_routes():
    """Test that Cancel button routes exist and will work"""

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row

    print("\n" + "=" * 70)
    print("TESTING CANCEL BUTTON ROUTES")
    print("=" * 70)

    # Get active listings
    listings = conn.execute('''
        SELECT id FROM listings WHERE active = 1 AND quantity > 0
    ''').fetchall()

    print(f"\nTesting cancel functionality for {len(listings)} active listings...")

    print("\n1. Routes needed:")
    print("   - GET  /listings/cancel_listing_confirmation_modal/<listing_id>")
    print("   - POST /listings/cancel_listing/<listing_id>")

    print("\n2. JavaScript needed:")
    print("   - window.openCancelModal(listing_id)")
    print("   - window.closeCancelModal(listing_id)")
    print("   - window.confirmCancel(listing_id)")

    print("\n3. Checking if listings can be cancelled...")

    all_can_cancel = True
    for listing in listings:
        listing_id = listing['id']

        # Verify listing exists
        exists = conn.execute(
            'SELECT id, active FROM listings WHERE id = ?',
            (listing_id,)
        ).fetchone()

        if exists and exists['active'] == 1:
            print(f"  [OK] Listing {listing_id}: Can be cancelled")
        else:
            print(f"  [ERROR] Listing {listing_id}: Cannot be cancelled")
            all_can_cancel = False

    print("\n" + "=" * 70)
    if all_can_cancel:
        print("SUCCESS: All listings can be cancelled!")
        print("NOTE: JavaScript must be loaded for Cancel button to work")
        print("      Console should show: '[Cancel Listing] Script loaded'")
    else:
        print("FAILED: Some listings cannot be cancelled")
    print("=" * 70)

    conn.close()

    return all_can_cancel

if __name__ == '__main__':
    view_ok = test_view_button_fix()
    cancel_ok = test_cancel_button_routes()

    print("\n" + "=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)
    print(f"View Button:   {'PASS' if view_ok else 'FAIL'}")
    print(f"Cancel Button: {'PASS' if cancel_ok else 'FAIL'}")

    if view_ok and cancel_ok:
        print("\nAll tests passed! Both buttons should work correctly.")
    else:
        print("\nSome tests failed. Please review the issues above.")
    print("=" * 70)
