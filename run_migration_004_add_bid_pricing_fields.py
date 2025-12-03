#!/usr/bin/env python3
"""
Migration 004: Add premium-to-spot pricing support to bids table

Adds the following columns to the bids table:
- pricing_mode: 'static' or 'premium_to_spot'
- spot_premium: premium above spot price (for premium_to_spot mode)
- floor_price: minimum price floor (for premium_to_spot mode)
- pricing_metal: which metal's spot price to track (for premium_to_spot mode)

For existing bids, default to static pricing mode.
"""

import sqlite3

def run_migration():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    print("="*80)
    print("MIGRATION 004: Add Premium-to-Spot Pricing Support to Bids Table")
    print("="*80)

    # Check current schema
    print("\n1. Checking current bids table schema...")
    schema = cursor.execute("PRAGMA table_info(bids)").fetchall()
    existing_columns = [col[1] for col in schema]
    print(f"   Existing columns: {', '.join(existing_columns)}")

    # Check if migration is needed
    needs_migration = 'pricing_mode' not in existing_columns

    if not needs_migration:
        print("\n✓ Migration already applied - bids table already has pricing_mode column")
        conn.close()
        return

    print("\n2. Adding new columns for premium-to-spot pricing...")

    try:
        # Add pricing_mode column (default to 'static' for existing bids)
        print("   Adding pricing_mode column...")
        cursor.execute("""
            ALTER TABLE bids
            ADD COLUMN pricing_mode TEXT DEFAULT 'static'
        """)

        # Add spot_premium column
        print("   Adding spot_premium column...")
        cursor.execute("""
            ALTER TABLE bids
            ADD COLUMN spot_premium REAL DEFAULT NULL
        """)

        # Add floor_price column
        print("   Adding floor_price column...")
        cursor.execute("""
            ALTER TABLE bids
            ADD COLUMN floor_price REAL DEFAULT NULL
        """)

        # Add pricing_metal column
        print("   Adding pricing_metal column...")
        cursor.execute("""
            ALTER TABLE bids
            ADD COLUMN pricing_metal TEXT DEFAULT NULL
        """)

        conn.commit()
        print("   ✓ All columns added successfully")

        # Verify the migration
        print("\n3. Verifying migration...")
        new_schema = cursor.execute("PRAGMA table_info(bids)").fetchall()
        new_columns = [col[1] for col in new_schema]
        print(f"   Updated columns: {', '.join(new_columns)}")

        # Count existing bids
        count = cursor.execute("SELECT COUNT(*) FROM bids").fetchone()[0]
        print(f"\n4. Existing bids: {count}")
        if count > 0:
            print(f"   All existing bids defaulted to pricing_mode='static'")

        print("\n" + "="*80)
        print("✓ MIGRATION COMPLETED SUCCESSFULLY")
        print("="*80)
        print("\nThe bids table now supports both static and premium-to-spot bids!")
        print("Premium-to-spot bids will have:")
        print("  - pricing_mode = 'premium_to_spot'")
        print("  - spot_premium = premium above spot price")
        print("  - floor_price = minimum price floor")
        print("  - pricing_metal = metal whose spot price determines bid price")
        print("="*80)

    except Exception as e:
        print(f"\n✗ ERROR during migration: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    run_migration()
