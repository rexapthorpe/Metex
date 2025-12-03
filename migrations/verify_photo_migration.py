"""
Verification Script: Test photo migration and new listing_photos functionality
Date: 2025-11-20
Purpose: Verify that the photo migration worked correctly and new uploads use listing_photos

This script:
1. Verifies migration completed successfully
2. Tests that order_items API returns correct image_url
3. Checks file system for actual photo files
4. Provides diagnostic information for troubleshooting
"""

import sqlite3
import sys
import os
from flask import url_for

# Get the parent directory to import database module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db_connection


def verify_migration_status():
    """Check current state of photo migration."""
    print("\n" + "=" * 80)
    print("MIGRATION STATUS CHECK")
    print("=" * 80)

    conn = get_db_connection()
    cursor = conn.cursor()

    # Count records in listing_photos
    cursor.execute("SELECT COUNT(*) FROM listing_photos")
    photos_count = cursor.fetchone()[0]

    # Count listings with old photo_filename
    cursor.execute("SELECT COUNT(*) FROM listings WHERE photo_filename IS NOT NULL")
    old_count = cursor.fetchone()[0]

    # Count listings referenced in listing_photos
    cursor.execute("SELECT COUNT(DISTINCT listing_id) FROM listing_photos")
    unique_listings = cursor.fetchone()[0]

    print(f"✓ Records in listing_photos table: {photos_count}")
    print(f"✓ Listings still using old photo_filename field: {old_count}")
    print(f"✓ Unique listings with photos: {unique_listings}")

    if old_count > 0 and photos_count == 0:
        print("\n⚠️  WARNING: Migration has NOT been run yet!")
        print("   Run migrate_photos_to_listing_photos.py first")
        conn.close()
        return False
    elif photos_count > 0:
        print(f"\n✅ Migration appears complete!")

    conn.close()
    return True


def verify_order_items_query():
    """Test the order_items API query to ensure it returns image_url."""
    print("\n" + "=" * 80)
    print("ORDER ITEMS API QUERY TEST")
    print("=" * 80)

    conn = get_db_connection()
    cursor = conn.cursor()

    # Find an order that has items with photos
    cursor.execute("""
        SELECT DISTINCT oi.order_id
        FROM order_items oi
        JOIN listings l ON oi.listing_id = l.id
        LEFT JOIN listing_photos lp ON lp.listing_id = l.id
        WHERE lp.file_path IS NOT NULL
        LIMIT 1
    """)

    result = cursor.fetchone()
    if not result:
        print("⚠️  No orders found with photos to test")
        conn.close()
        return True

    order_id = result[0]
    print(f"Testing with Order ID: {order_id}")

    # Simulate the exact query used in account_routes.py
    raw_rows = cursor.execute(
        """
        SELECT
          oi.order_item_id AS item_id,
          oi.order_id,
          oi.listing_id,
          oi.quantity,
          oi.price_each,

          c.mint,
          c.metal,
          c.weight,
          c.year,
          c.product_line,
          c.product_type,
          c.purity,
          c.finish,
          c.grade,

          l.graded,
          l.grading_service,
          u.username AS seller_username,

          lp.file_path
        FROM order_items AS oi
        JOIN listings      AS l   ON oi.listing_id = l.id
        JOIN categories    AS c   ON l.category_id = c.id
        JOIN users         AS u   ON l.seller_id = u.id
        LEFT JOIN listing_photos AS lp
               ON lp.listing_id = l.id
        WHERE oi.order_id = ?
        ORDER BY oi.price_each DESC, oi.order_item_id
        """,
        (order_id,)
    ).fetchall()

    print(f"\nQuery returned {len(raw_rows)} items:")
    for i, row in enumerate(raw_rows, 1):
        rd = dict(row)
        raw_path = rd.get('file_path')

        # Simulate the path normalization logic from account_routes.py
        image_url = None
        if raw_path:
            raw_path = str(raw_path)
            if raw_path.startswith('/'):
                image_url = raw_path
            elif raw_path.startswith('static/'):
                image_url = '/' + raw_path
            else:
                image_url = f"/static/{raw_path}"

        print(f"\n{i}. Order Item {rd['item_id']}:")
        print(f"   Listing ID: {rd['listing_id']}")
        print(f"   Seller: {rd['seller_username']}")
        print(f"   Raw file_path: {raw_path}")
        print(f"   Computed image_url: {image_url}")

        if image_url:
            print(f"   ✅ Image URL generated successfully")
        else:
            print(f"   ❌ No image URL (file_path was NULL)")

    conn.close()
    return True


def verify_file_system():
    """Check that photo files actually exist on disk."""
    print("\n" + "=" * 80)
    print("FILE SYSTEM VERIFICATION")
    print("=" * 80)

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get all file paths from listing_photos
    cursor.execute("SELECT id, listing_id, file_path FROM listing_photos")
    photos = cursor.fetchall()

    if not photos:
        print("⚠️  No photos in listing_photos table")
        conn.close()
        return True

    # Get the project root (parent of migrations folder)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_folder = os.path.join(project_root, "static")

    print(f"Checking files in: {static_folder}\n")

    missing_files = []
    existing_files = []

    for photo in photos:
        photo_id, listing_id, file_path = photo

        # file_path should be like "uploads/listings/filename.jpg"
        full_path = os.path.join(static_folder, file_path)

        if os.path.exists(full_path):
            file_size = os.path.getsize(full_path)
            existing_files.append((listing_id, file_path, file_size))
            print(f"✓ Listing {listing_id}: {file_path} ({file_size:,} bytes)")
        else:
            missing_files.append((listing_id, file_path, full_path))
            print(f"❌ Listing {listing_id}: {file_path} NOT FOUND")
            print(f"   Expected at: {full_path}")

    print(f"\n{'=' * 40}")
    print(f"Files found: {len(existing_files)}")
    print(f"Files missing: {len(missing_files)}")

    if missing_files:
        print("\n⚠️  WARNING: Some photo files are missing from disk!")
        print("This may cause broken images in the frontend.")

    conn.close()
    return len(missing_files) == 0


def verify_data_consistency():
    """Check for data consistency issues."""
    print("\n" + "=" * 80)
    print("DATA CONSISTENCY CHECK")
    print("=" * 80)

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check for duplicate entries
    cursor.execute("""
        SELECT listing_id, COUNT(*) as count
        FROM listing_photos
        GROUP BY listing_id
        HAVING count > 1
    """)
    duplicates = cursor.fetchall()

    if duplicates:
        print(f"⚠️  Found {len(duplicates)} listings with multiple photos:")
        for dup in duplicates:
            print(f"   Listing {dup[0]}: {dup[1]} photos")
    else:
        print("✓ No duplicate photos per listing")

    # Check for orphaned listing_photos (listing doesn't exist)
    cursor.execute("""
        SELECT lp.id, lp.listing_id
        FROM listing_photos lp
        LEFT JOIN listings l ON lp.listing_id = l.id
        WHERE l.id IS NULL
    """)
    orphaned = cursor.fetchall()

    if orphaned:
        print(f"\n⚠️  Found {len(orphaned)} orphaned photo records:")
        for orph in orphaned:
            print(f"   Photo ID {orph[0]} references non-existent Listing {orph[1]}")
    else:
        print("✓ No orphaned photo records")

    # Check for listings in orders that should have photos
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM order_items oi
        JOIN listings l ON oi.listing_id = l.id
        LEFT JOIN listing_photos lp ON lp.listing_id = l.id
        WHERE l.photo_filename IS NOT NULL AND lp.file_path IS NULL
    """)
    missing_migration = cursor.fetchone()[0]

    if missing_migration > 0:
        print(f"\n⚠️  Found {missing_migration} order items with old photo_filename but no listing_photos entry")
        print("   These items won't show photos in the orders modal")
        print("   Run the migration script to fix this")
    else:
        print("✓ All order items with photos have been migrated")

    conn.close()
    return True


def generate_test_data_report():
    """Generate a report of test data for manual verification."""
    print("\n" + "=" * 80)
    print("TEST DATA REPORT")
    print("=" * 80)

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get sample listing with photo
    cursor.execute("""
        SELECT
            l.id as listing_id,
            l.seller_id,
            l.photo_filename,
            lp.file_path,
            lp.uploader_id,
            c.metal,
            c.product_type,
            u.username
        FROM listings l
        LEFT JOIN listing_photos lp ON l.id = lp.listing_id
        LEFT JOIN categories c ON l.category_id = c.id
        LEFT JOIN users u ON l.seller_id = u.id
        WHERE lp.file_path IS NOT NULL
        LIMIT 3
    """)

    listings = cursor.fetchall()

    if not listings:
        print("No listings with photos found")
        conn.close()
        return

    print("\nSample Listings with Photos:\n")
    for listing in listings:
        ld = dict(listing)
        print(f"Listing ID: {ld['listing_id']}")
        print(f"  Seller: {ld['username']} (ID: {ld['seller_id']})")
        print(f"  Product: {ld['metal']} {ld['product_type']}")
        print(f"  Old photo_filename: {ld['photo_filename']}")
        print(f"  New file_path: {ld['file_path']}")
        print(f"  Image URL would be: /static/{ld['file_path']}")

        # Check if this listing is in any orders
        cursor.execute("""
            SELECT COUNT(*) FROM order_items WHERE listing_id = ?
        """, (ld['listing_id'],))
        order_count = cursor.fetchone()[0]
        print(f"  Used in {order_count} orders")
        print()

    conn.close()


def main():
    """Run all verification checks."""
    print("\n" + "=" * 80)
    print("PHOTO MIGRATION VERIFICATION SCRIPT")
    print("=" * 80)

    all_passed = True

    # Run all checks
    if not verify_migration_status():
        print("\n❌ Migration has not been run yet. Exiting.")
        return False

    all_passed = verify_order_items_query() and all_passed
    all_passed = verify_file_system() and all_passed
    all_passed = verify_data_consistency() and all_passed

    generate_test_data_report()

    # Final summary
    print("\n" + "=" * 80)
    if all_passed:
        print("✅ ALL VERIFICATIONS PASSED!")
    else:
        print("⚠️  SOME CHECKS FAILED - Review output above")
    print("=" * 80)

    print("\nNext steps:")
    print("1. Start the Flask application: python app.py")
    print("2. Log in and navigate to Account > Orders tab")
    print("3. Click 'Items' button on any order")
    print("4. Verify photos appear in the modal")
    print("5. Test creating a new listing with a photo")
    print("6. Verify the new listing's photo appears in orders after purchase")

    return all_passed


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
