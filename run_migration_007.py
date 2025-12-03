"""
Migration Runner for 007: Premium-to-Spot Pricing System

Applies database schema changes to support dual pricing modes:
- Static pricing (existing functionality)
- Premium-to-spot pricing (new dynamic pricing based on live metal prices)
"""

import sqlite3
import os

def run_migration():
    """Execute migration 007"""

    # Path to database
    db_path = 'database.db'

    # Path to migration SQL file
    migration_path = 'migrations/007_add_premium_to_spot_pricing.sql'

    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at {db_path}")
        return False

    if not os.path.exists(migration_path):
        print(f"ERROR: Migration file not found at {migration_path}")
        return False

    print("=" * 70)
    print("  RUNNING MIGRATION 007: Premium-to-Spot Pricing System")
    print("=" * 70)
    print()

    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Read migration SQL
        with open(migration_path, 'r') as f:
            migration_sql = f.read()

        # Execute migration
        print("Applying schema changes...")
        cursor.executescript(migration_sql)
        conn.commit()

        print("[SUCCESS] Migration applied successfully!")
        print()

        # Verify new tables were created
        print("Verifying new tables...")

        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name IN ('spot_prices', 'price_locks')
            ORDER BY name
        """)
        tables = cursor.fetchall()

        if len(tables) == 2:
            print(f"  [OK] spot_prices table created")
            print(f"  [OK] price_locks table created")
        else:
            print(f"  WARNING: Expected 2 tables, found {len(tables)}")

        # Verify listings table columns were added
        print()
        print("Verifying listings table modifications...")

        cursor.execute("PRAGMA table_info(listings)")
        columns = cursor.fetchall()
        column_names = [col['name'] for col in columns]

        expected_columns = ['pricing_mode', 'spot_premium', 'floor_price', 'pricing_metal']
        for col in expected_columns:
            if col in column_names:
                print(f"  [OK] listings.{col} column added")
            else:
                print(f"  [FAIL] listings.{col} column NOT found")

        # Verify order_items table columns were added
        print()
        print("Verifying order_items table modifications...")

        cursor.execute("PRAGMA table_info(order_items)")
        columns = cursor.fetchall()
        column_names = [col['name'] for col in columns]

        expected_columns = ['price_at_purchase', 'pricing_mode_at_purchase', 'spot_price_at_purchase']
        for col in expected_columns:
            if col in column_names:
                print(f"  [OK] order_items.{col} column added")
            else:
                print(f"  [FAIL] order_items.{col} column NOT found")

        # Check spot_prices seed data
        print()
        print("Verifying spot_prices seed data...")

        cursor.execute("SELECT metal, price_usd_per_oz FROM spot_prices ORDER BY metal")
        spot_prices = cursor.fetchall()

        if len(spot_prices) >= 4:
            print(f"  [OK] {len(spot_prices)} spot price records seeded:")
            for row in spot_prices:
                print(f"    - {row['metal']}: ${row['price_usd_per_oz']:.2f}/oz")
        else:
            print(f"  WARNING: Expected at least 4 spot price records, found {len(spot_prices)}")

        # Check existing listings backfill
        print()
        print("Verifying existing listings backfill...")

        cursor.execute("""
            SELECT COUNT(*) as count
            FROM listings
            WHERE pricing_mode = 'static'
        """)
        static_count = cursor.fetchone()['count']

        print(f"  [OK] {static_count} existing listings set to 'static' mode")

        # Check existing order_items backfill
        print()
        print("Verifying existing order_items backfill...")

        cursor.execute("""
            SELECT COUNT(*) as count
            FROM order_items
            WHERE price_at_purchase IS NOT NULL
              AND pricing_mode_at_purchase = 'static'
        """)
        backfilled_count = cursor.fetchone()['count']

        print(f"  [OK] {backfilled_count} existing order items backfilled with pricing data")

        conn.close()

        print()
        print("=" * 70)
        print("  MIGRATION 007 COMPLETED SUCCESSFULLY!")
        print("=" * 70)
        print()
        print("Next steps:")
        print("  1. Restart the Flask application to load new schema")
        print("  2. Verify spot price service is fetching live data")
        print("  3. Test creating listings in both pricing modes")
        print()

        return True

    except sqlite3.Error as e:
        print()
        print("=" * 70)
        print("  MIGRATION FAILED!")
        print("=" * 70)
        print(f"Error: {e}")
        print()
        print("The database may be in an inconsistent state.")
        print("Please review the error and consider restoring from backup.")

        if conn:
            conn.close()

        return False

if __name__ == '__main__':
    success = run_migration()
    exit(0 if success else 1)
