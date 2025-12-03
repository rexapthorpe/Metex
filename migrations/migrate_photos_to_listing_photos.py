"""
Migration Script: Move photo_filename data to listing_photos table
Date: 2025-11-20
Purpose: Migrate existing listing photos from listings.photo_filename to the listing_photos table

This script:
1. Reads all listings with photo_filename values
2. Creates corresponding entries in listing_photos table
3. Preserves all relationships (listing_id, uploader_id from seller_id)
4. Validates the migration before committing
5. Provides rollback capability
"""

import sqlite3
import sys
import os
from datetime import datetime

# Get the parent directory to import database module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db_connection


def validate_migration_prerequisites():
    """Check that the database is in the expected state before migration."""
    conn = get_db_connection()
    cursor = conn.cursor()

    print("=" * 80)
    print("VALIDATING MIGRATION PREREQUISITES")
    print("=" * 80)

    # Check if listing_photos table exists
    cursor.execute("""
        SELECT sql FROM sqlite_master
        WHERE type='table' AND name='listing_photos'
    """)
    result = cursor.fetchone()
    if not result:
        print("❌ ERROR: listing_photos table does not exist!")
        conn.close()
        return False
    print("✓ listing_photos table exists")

    # Check current state
    cursor.execute("SELECT COUNT(*) FROM listing_photos")
    existing_count = cursor.fetchone()[0]
    print(f"✓ Current rows in listing_photos: {existing_count}")

    cursor.execute("SELECT COUNT(*) FROM listings WHERE photo_filename IS NOT NULL")
    source_count = cursor.fetchone()[0]
    print(f"✓ Listings with photo_filename: {source_count}")

    if source_count == 0:
        print("⚠️  WARNING: No listings have photo_filename. Nothing to migrate.")
        conn.close()
        return False

    conn.close()
    return True


def preview_migration():
    """Show what will be migrated."""
    conn = get_db_connection()
    cursor = conn.cursor()

    print("\n" + "=" * 80)
    print("MIGRATION PREVIEW")
    print("=" * 80)

    cursor.execute("""
        SELECT
            l.id AS listing_id,
            l.seller_id AS uploader_id,
            l.photo_filename,
            'static/uploads/listings/' || l.photo_filename AS full_path
        FROM listings l
        WHERE l.photo_filename IS NOT NULL
        ORDER BY l.id
    """)

    rows = cursor.fetchall()
    print(f"\nWill migrate {len(rows)} photo records:\n")

    for i, row in enumerate(rows, 1):
        print(f"{i}. Listing ID: {row['listing_id']}")
        print(f"   Uploader ID: {row['uploader_id']}")
        print(f"   Photo Filename: {row['photo_filename']}")
        print(f"   Full Path: {row['full_path']}")
        print()

    conn.close()
    return len(rows)


def perform_migration(dry_run=False):
    """
    Migrate photo_filename data to listing_photos table.

    Args:
        dry_run: If True, show what would happen without committing changes
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    print("\n" + "=" * 80)
    if dry_run:
        print("DRY RUN MODE - No changes will be committed")
    else:
        print("PERFORMING MIGRATION")
    print("=" * 80 + "\n")

    try:
        # Get all listings with photos
        cursor.execute("""
            SELECT
                l.id AS listing_id,
                l.seller_id AS uploader_id,
                l.photo_filename
            FROM listings l
            WHERE l.photo_filename IS NOT NULL
            ORDER BY l.id
        """)

        listings_to_migrate = cursor.fetchall()
        migrated_count = 0
        skipped_count = 0

        for listing in listings_to_migrate:
            listing_id = listing['listing_id']
            uploader_id = listing['uploader_id']
            photo_filename = listing['photo_filename']

            # Check if this listing already has an entry in listing_photos
            cursor.execute("""
                SELECT id FROM listing_photos
                WHERE listing_id = ?
            """, (listing_id,))

            existing = cursor.fetchone()

            if existing:
                print(f"⚠️  Skipping Listing {listing_id} - already has entry in listing_photos")
                skipped_count += 1
                continue

            # Build the file_path (consistent with how uploads are stored)
            # Photos are stored in static/uploads/listings/
            file_path = f"uploads/listings/{photo_filename}"

            if not dry_run:
                cursor.execute("""
                    INSERT INTO listing_photos (listing_id, uploader_id, file_path)
                    VALUES (?, ?, ?)
                """, (listing_id, uploader_id, file_path))

                print(f"✓ Migrated Listing {listing_id}: {file_path}")
            else:
                print(f"[DRY RUN] Would migrate Listing {listing_id}: {file_path}")

            migrated_count += 1

        if not dry_run:
            conn.commit()
            print(f"\n✅ Migration completed successfully!")
        else:
            conn.rollback()
            print(f"\n✅ Dry run completed!")

        print(f"   - Migrated: {migrated_count}")
        print(f"   - Skipped (already migrated): {skipped_count}")

        conn.close()
        return True

    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"\n❌ Migration failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def validate_migration():
    """Validate that the migration was successful."""
    conn = get_db_connection()
    cursor = conn.cursor()

    print("\n" + "=" * 80)
    print("VALIDATING MIGRATION RESULTS")
    print("=" * 80)

    # Count listings with photo_filename
    cursor.execute("SELECT COUNT(*) FROM listings WHERE photo_filename IS NOT NULL")
    source_count = cursor.fetchone()[0]

    # Count listing_photos entries
    cursor.execute("SELECT COUNT(*) FROM listing_photos")
    target_count = cursor.fetchone()[0]

    print(f"Listings with photo_filename: {source_count}")
    print(f"Rows in listing_photos table: {target_count}")

    # Check for orphaned records
    cursor.execute("""
        SELECT COUNT(*) FROM listing_photos lp
        LEFT JOIN listings l ON lp.listing_id = l.id
        WHERE l.id IS NULL
    """)
    orphaned = cursor.fetchone()[0]

    if orphaned > 0:
        print(f"⚠️  WARNING: {orphaned} orphaned records in listing_photos!")
    else:
        print("✓ No orphaned records")

    # Verify actual file paths match
    cursor.execute("""
        SELECT
            l.id,
            l.photo_filename,
            lp.file_path
        FROM listings l
        JOIN listing_photos lp ON l.id = lp.listing_id
        WHERE l.photo_filename IS NOT NULL
    """)

    mismatches = []
    for row in cursor.fetchall():
        expected_path = f"uploads/listings/{row['photo_filename']}"
        if row['file_path'] != expected_path:
            mismatches.append({
                'listing_id': row['id'],
                'expected': expected_path,
                'actual': row['file_path']
            })

    if mismatches:
        print(f"\n⚠️  WARNING: {len(mismatches)} path mismatches found:")
        for m in mismatches:
            print(f"   Listing {m['listing_id']}: expected '{m['expected']}', got '{m['actual']}'")
    else:
        print("✓ All file paths match expected format")

    # Sample verification
    print("\n" + "=" * 80)
    print("SAMPLE MIGRATED RECORDS")
    print("=" * 80)
    cursor.execute("""
        SELECT
            lp.id,
            lp.listing_id,
            lp.uploader_id,
            lp.file_path,
            l.photo_filename
        FROM listing_photos lp
        JOIN listings l ON lp.listing_id = l.id
        LIMIT 5
    """)

    for row in cursor.fetchall():
        print(f"\nListing Photos ID: {row['id']}")
        print(f"  Listing ID: {row['listing_id']}")
        print(f"  Uploader ID: {row['uploader_id']}")
        print(f"  File Path: {row['file_path']}")
        print(f"  Original photo_filename: {row['photo_filename']}")

    conn.close()

    if target_count >= source_count and orphaned == 0 and len(mismatches) == 0:
        print("\n✅ Migration validation PASSED!")
        return True
    else:
        print("\n⚠️  Migration validation completed with warnings")
        return False


def create_backup():
    """Create a backup SQL dump of current state."""
    print("\n" + "=" * 80)
    print("CREATING BACKUP")
    print("=" * 80)

    backup_filename = f"backup_before_migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
    backup_path = os.path.join(os.path.dirname(__file__), backup_filename)

    try:
        conn = get_db_connection()

        with open(backup_path, 'w') as f:
            for line in conn.iterdump():
                # Only backup listings and listing_photos tables
                if 'listings' in line.lower() or 'listing_photos' in line.lower():
                    f.write(f'{line}\n')

        conn.close()
        print(f"✓ Backup created: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"❌ Failed to create backup: {str(e)}")
        return None


def main():
    """Main migration workflow."""
    print("\n" + "=" * 80)
    print("PHOTO MIGRATION SCRIPT")
    print("Migrating listings.photo_filename → listing_photos table")
    print("=" * 80)

    # Step 1: Validate prerequisites
    if not validate_migration_prerequisites():
        print("\n❌ Prerequisites not met. Exiting.")
        return False

    # Step 2: Preview what will be migrated
    count = preview_migration()

    if count == 0:
        print("\nNothing to migrate. Exiting.")
        return True

    # Step 3: Confirm with user
    print("\n" + "=" * 80)
    response = input(f"\nReady to migrate {count} records. Continue? (yes/no): ").strip().lower()

    if response not in ['yes', 'y']:
        print("Migration cancelled by user.")
        return False

    # Step 4: Create backup
    backup_path = create_backup()
    if not backup_path:
        response = input("\nBackup failed. Continue anyway? (yes/no): ").strip().lower()
        if response not in ['yes', 'y']:
            print("Migration cancelled.")
            return False

    # Step 5: Dry run first
    print("\n" + "=" * 80)
    print("Running DRY RUN first...")
    print("=" * 80)
    perform_migration(dry_run=True)

    response = input("\nDry run complete. Proceed with actual migration? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("Migration cancelled by user.")
        return False

    # Step 6: Perform actual migration
    success = perform_migration(dry_run=False)

    if not success:
        print("\n❌ Migration failed!")
        if backup_path:
            print(f"You can restore from backup: {backup_path}")
        return False

    # Step 7: Validate results
    validate_migration()

    print("\n" + "=" * 80)
    print("MIGRATION COMPLETE!")
    print("=" * 80)
    print("\nNext steps:")
    print("1. Review the validation results above")
    print("2. Update sell_routes.py to use listing_photos table")
    print("3. Test creating new listings with photos")
    print("4. Test viewing order items modal with photos")
    if backup_path:
        print(f"5. Backup saved at: {backup_path}")

    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Migration interrupted by user!")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
