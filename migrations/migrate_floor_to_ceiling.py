"""
Database Migration: Rename floor_price to ceiling_price in bids table

This migration changes the semantics of variable pricing for bids:
- OLD (WRONG): floor_price was a minimum - bid wouldn't trigger below this
- NEW (CORRECT): ceiling_price is a maximum - bid won't auto-fill above this

For bids, a ceiling makes sense because buyers want to set a maximum price they'll pay.
"""

import sqlite3
import sys
import os

# Get database path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db_path = os.path.join(BASE_DIR, 'database.db')

def migrate():
    print("=" * 80)
    print("Database Migration: floor_price -> ceiling_price")
    print("=" * 80)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if ceiling_price column already exists
        cursor.execute("PRAGMA table_info(bids)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'ceiling_price' in columns:
            print("ceiling_price column already exists - migration already applied")
            conn.close()
            return True

        if 'floor_price' not in columns:
            print("ERROR: floor_price column not found - unexpected database state")
            conn.close()
            return False

        print("\n1. Backing up current data...")
        # Get current data
        cursor.execute("SELECT id, floor_price FROM bids WHERE floor_price IS NOT NULL")
        bids_with_floor = cursor.fetchall()
        print(f"   Found {len(bids_with_floor)} bids with floor_price set")

        print("\n2. Renaming floor_price to ceiling_price...")
        # SQLite doesn't support ALTER COLUMN RENAME directly in all versions
        # We need to:
        # a) Add new column
        # b) Copy data
        # c) Drop old column

        # Add ceiling_price column
        cursor.execute("""
            ALTER TABLE bids ADD COLUMN ceiling_price REAL DEFAULT NULL
        """)
        print("   Created ceiling_price column")

        # Copy data from floor_price to ceiling_price
        cursor.execute("""
            UPDATE bids SET ceiling_price = floor_price WHERE floor_price IS NOT NULL
        """)
        print(f"   Copied {len(bids_with_floor)} floor_price values to ceiling_price")

        # Note: In SQLite, we can't easily drop a column without recreating the table
        # For now, we'll leave floor_price as NULL but update the application to use ceiling_price
        # The old column won't hurt anything
        cursor.execute("""
            UPDATE bids SET floor_price = NULL
        """)
        print("   Cleared old floor_price values (column remains for compatibility)")

        conn.commit()

        print("\n3. Verifying migration...")
        cursor.execute("SELECT COUNT(*) FROM bids WHERE ceiling_price IS NOT NULL")
        count = cursor.fetchone()[0]
        print(f"   {count} bids now have ceiling_price set")

        print("\n" + "=" * 80)
        print("Migration completed successfully!")
        print("=" * 80)
        print("\nSummary:")
        print(f"  - Renamed floor_price -> ceiling_price")
        print(f"  - Migrated {len(bids_with_floor)} existing values")
        print(f"  - Old floor_price column cleared (kept for compatibility)")
        print("\nNext steps:")
        print("  - Update application code to use ceiling_price")
        print("  - Update forms to say 'Max Price' instead of 'Floor Price'")
        print("  - Update auto-fill logic to respect ceiling")
        print("=" * 80)

        conn.close()
        return True

    except Exception as e:
        print(f"\nERROR: Migration failed: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        conn.close()
        return False

if __name__ == '__main__':
    success = migrate()
    sys.exit(0 if success else 1)
