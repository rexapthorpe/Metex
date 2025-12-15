"""
Cleanup Script: Wipe All Bucket-Related Data

Purpose:
  - Remove all buckets, listings, bids, and related data
  - Preserve users, addresses, orders, messages, and app structure
  - Keep category catalog definitions intact

Safe to run multiple times (idempotent).
"""

from database import get_db_connection


def cleanup_buckets():
    """Safely delete all bucket-related data in the correct order"""

    conn = get_db_connection()
    cursor = conn.cursor()

    print("=" * 70)
    print("BUCKET DATA CLEANUP")
    print("=" * 70)
    print("\nThis will DELETE all buckets, listings, bids, and related data.")
    print("Users, addresses, orders, and messages will NOT be affected.")
    print()

    # Count records before deletion
    print("Current data counts:")
    print("-" * 70)

    tables_to_check = [
        ('price_locks', 'Price Locks'),
        ('listing_photos', 'Listing Photos'),
        ('bids', 'Bids'),
        ('listings', 'Listings'),
        ('bucket_price_history', 'Bucket Price History'),
        ('category_price_snapshots', 'Category Price Snapshots'),
        ('categories', 'Categories/Buckets')
    ]

    for table, label in tables_to_check:
        try:
            count = cursor.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            print(f"  {label:.<30} {count:>6} records")
        except Exception as e:
            print(f"  {label:.<30} (table not found or error)")

    print()

    # Confirm deletion
    response = input("Proceed with deletion? (yes/no): ").strip().lower()
    if response != 'yes':
        print("\nCleanup cancelled.")
        conn.close()
        return

    print("\nStarting cleanup...")
    print("-" * 70)

    try:
        # Step 1: Delete price_locks (depends on listings)
        print("\n1. Deleting price locks...")
        cursor.execute('DELETE FROM price_locks')
        deleted = cursor.rowcount
        print(f"   [OK] Deleted {deleted} price locks")

        # Step 2: Delete listing_photos (depends on listings)
        print("\n2. Deleting listing photos...")
        cursor.execute('DELETE FROM listing_photos')
        deleted = cursor.rowcount
        print(f"   [OK] Deleted {deleted} listing photos")

        # Step 3: Delete bids (depends on categories)
        print("\n3. Deleting bids...")
        cursor.execute('DELETE FROM bids')
        deleted = cursor.rowcount
        print(f"   [OK] Deleted {deleted} bids")

        # Step 4: Delete bid_fills (if any reference bids)
        print("\n4. Deleting bid fills...")
        cursor.execute('DELETE FROM bid_fills')
        deleted = cursor.rowcount
        print(f"   [OK] Deleted {deleted} bid fills")

        # Step 5: Delete listings (depends on categories)
        print("\n5. Deleting listings...")
        cursor.execute('DELETE FROM listings')
        deleted = cursor.rowcount
        print(f"   [OK] Deleted {deleted} listings")

        # Step 6: Delete bucket_price_history (depends on bucket_id)
        print("\n6. Deleting bucket price history...")
        cursor.execute('DELETE FROM bucket_price_history')
        deleted = cursor.rowcount
        print(f"   [OK] Deleted {deleted} price history records")

        # Step 7: Delete category_price_snapshots (depends on categories)
        print("\n7. Deleting category price snapshots...")
        cursor.execute('DELETE FROM category_price_snapshots')
        deleted = cursor.rowcount
        print(f"   [OK] Deleted {deleted} price snapshots")

        # Step 8: Delete categories (the main bucket table)
        print("\n8. Deleting categories/buckets...")
        cursor.execute('DELETE FROM categories')
        deleted = cursor.rowcount
        print(f"   [OK] Deleted {deleted} categories/buckets")

        # Step 9: Reset the autoincrement sequences
        print("\n9. Resetting ID sequences...")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('categories', 'listings', 'bids', 'bucket_price_history')")
        print("   [OK] Reset autoincrement sequences")

        # Commit all changes
        conn.commit()
        print("\n" + "=" * 70)
        print("CLEANUP COMPLETE")
        print("=" * 70)
        print("\nAll bucket-related data has been deleted.")
        print("Users, addresses, orders, and messages remain intact.")
        print("The app is ready to accept new listings and buckets.")

    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] {e}")
        print("Changes have been rolled back.")

    finally:
        conn.close()


def verify_cleanup():
    """Verify that bucket data is cleared and other data is preserved"""

    conn = get_db_connection()
    cursor = conn.cursor()

    print("\n" + "=" * 70)
    print("VERIFICATION")
    print("=" * 70)

    # Check bucket-related tables (should be 0)
    print("\nBucket-related tables (should be empty):")
    bucket_tables = [
        'categories',
        'listings',
        'bids',
        'bucket_price_history',
        'price_locks',
        'listing_photos'
    ]

    all_clean = True
    for table in bucket_tables:
        try:
            count = cursor.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            status = "[OK]" if count == 0 else "[X]"
            print(f"  {status} {table:.<30} {count:>6} records")
            if count > 0:
                all_clean = False
        except Exception as e:
            print(f"  [?] {table:.<30} (error checking)")

    # Check preserved tables (should have data if existed before)
    print("\nPreserved tables (should NOT be empty if had data):")
    preserved_tables = [
        'users',
        'addresses',
        'orders',
        'messages'
    ]

    for table in preserved_tables:
        try:
            count = cursor.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            print(f"  [OK] {table:.<30} {count:>6} records")
        except Exception as e:
            print(f"  [?] {table:.<30} (error checking)")

    conn.close()

    if all_clean:
        print("\n[OK] All bucket data successfully cleared!")
    else:
        print("\n[WARNING] Some bucket data may remain")

    print("=" * 70)


if __name__ == '__main__':
    cleanup_buckets()
    verify_cleanup()
