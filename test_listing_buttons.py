"""
Test the View and Cancel buttons on listing tiles
"""

from database import get_db_connection
import sqlite3

def test_listing_buttons():
    """Test that both View and Cancel buttons work correctly"""

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row

    print("=" * 70)
    print("TESTING LISTING TILE BUTTONS")
    print("=" * 70)

    # Get an active listing
    listing = conn.execute('''
        SELECT l.id as listing_id, c.bucket_id, c.id as category_id
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.active = 1 AND l.quantity > 0
        LIMIT 1
    ''').fetchone()

    if not listing:
        print("\n[ERROR] No active listings found!")
        conn.close()
        return

    listing_id = listing['listing_id']
    bucket_id = listing['bucket_id']
    category_id = listing['category_id']

    print(f"\n1. Testing with Listing {listing_id}")
    print(f"   - bucket_id: {bucket_id}")
    print(f"   - category_id: {category_id}")

    # Test 1: View Button - check if bucket page would work
    print(f"\n2. Testing View Button functionality...")
    print(f"   View button would navigate to: /bucket/{bucket_id}")

    # The view_bucket route currently queries: SELECT * FROM categories WHERE id = ?
    # This is WRONG - it should query WHERE bucket_id = ?
    wrong_query = conn.execute(
        'SELECT * FROM categories WHERE id = ?',
        (bucket_id,)
    ).fetchone()

    if wrong_query:
        print(f"   [ISSUE] Wrong query (WHERE id = {bucket_id}) found a category!")
        print(f"           This is incorrect - bucket_id {bucket_id} is not a category id")
    else:
        print(f"   [ERROR] Wrong query (WHERE id = {bucket_id}) returns nothing")
        print(f"           View button would fail - page not found!")

    # The CORRECT query should be:
    correct_query = conn.execute(
        'SELECT * FROM categories WHERE bucket_id = ? LIMIT 1',
        (bucket_id,)
    ).fetchone()

    if correct_query:
        print(f"   [OK] Correct query (WHERE bucket_id = {bucket_id}) found category {correct_query['id']}")
        print(f"        View button SHOULD use this query")
    else:
        print(f"   [ERROR] No categories with bucket_id = {bucket_id}")

    # Test 2: Cancel Button - check if route exists
    print(f"\n3. Testing Cancel Button functionality...")
    print(f"   Cancel button calls: openCancelModal({listing_id})")
    print(f"   Modal fetches from: /listings/cancel_listing_confirmation_modal/{listing_id}")
    print(f"   Confirm sends POST to: /listings/cancel_listing/{listing_id}")

    # Check if the cancel route would work
    can_cancel = conn.execute(
        'SELECT id FROM listings WHERE id = ?',
        (listing_id,)
    ).fetchone()

    if can_cancel:
        print(f"   [OK] Listing {listing_id} exists - cancel route would work")
    else:
        print(f"   [ERROR] Listing {listing_id} not found")

    print("\n" + "=" * 70)
    print("ISSUES FOUND:")
    print("1. View Button: Route queries 'WHERE id = ?' instead of 'WHERE bucket_id = ?'")
    print("2. Need to verify Cancel Button JavaScript is properly loaded")
    print("=" * 70)

    conn.close()

if __name__ == '__main__':
    test_listing_buttons()
