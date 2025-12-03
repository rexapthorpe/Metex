"""
Cleanup script to remove orphaned categories and optimize the database
Problem: 26+ million category rows are causing extreme slowness
Solution: Keep only categories referenced by listings
"""
import sqlite3
from database import get_db_connection

def cleanup_categories():
    print("="*60)
    print("CATEGORY CLEANUP SCRIPT")
    print("="*60)

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Count total categories
    total = cursor.execute('SELECT COUNT(*) FROM categories').fetchone()[0]
    print(f"\n1. Current category count: {total:,}")

    # 2. Count categories actually in use (referenced by listings)
    in_use = cursor.execute('''
        SELECT COUNT(DISTINCT category_id)
        FROM listings
    ''').fetchone()[0]
    print(f"2. Categories in use by listings: {in_use:,}")

    orphaned = total - in_use
    print(f"3. Orphaned categories to delete: {orphaned:,}")

    if orphaned == 0:
        print("\nNo cleanup needed!")
        conn.close()
        return

    # 3. Ask for confirmation
    print(f"\nWARNING: About to delete {orphaned:,} rows from categories table")
    print("This will:")
    print("  - Keep only categories referenced by active listings")
    print("  - Speed up dropdown option loading significantly")
    print("  - Cannot be undone (backup database first if concerned)")

    response = input("\nProceed with cleanup? (yes/no): ").strip().lower()
    if response != 'yes':
        print("Cleanup cancelled.")
        conn.close()
        return

    # 4. Delete orphaned categories
    print("\nDeleting orphaned categories...")
    cursor.execute('''
        DELETE FROM categories
        WHERE id NOT IN (SELECT DISTINCT category_id FROM listings)
    ''')

    deleted = cursor.rowcount
    print(f"Deleted {deleted:,} orphaned categories")

    # 5. Vacuum to reclaim space
    print("\nVacuuming database to reclaim space...")
    conn.commit()
    cursor.execute('VACUUM')
    print("Database vacuumed")

    # 6. Verify final count
    final_count = cursor.execute('SELECT COUNT(*) FROM categories').fetchone()[0]
    print(f"\nFinal category count: {final_count:,}")

    # 7. Create indexes for better performance
    print("\nCreating indexes for better query performance...")

    indexes = [
        ('idx_categories_metal', 'CREATE INDEX IF NOT EXISTS idx_categories_metal ON categories(metal)'),
        ('idx_categories_product_line', 'CREATE INDEX IF NOT EXISTS idx_categories_product_line ON categories(product_line)'),
        ('idx_categories_product_type', 'CREATE INDEX IF NOT EXISTS idx_categories_product_type ON categories(product_type)'),
        ('idx_categories_weight', 'CREATE INDEX IF NOT EXISTS idx_categories_weight ON categories(weight)'),
        ('idx_categories_purity', 'CREATE INDEX IF NOT EXISTS idx_categories_purity ON categories(purity)'),
        ('idx_categories_mint', 'CREATE INDEX IF NOT EXISTS idx_categories_mint ON categories(mint)'),
        ('idx_categories_year', 'CREATE INDEX IF NOT EXISTS idx_categories_year ON categories(year)'),
        ('idx_categories_finish', 'CREATE INDEX IF NOT EXISTS idx_categories_finish ON categories(finish)'),
        ('idx_categories_grade', 'CREATE INDEX IF NOT EXISTS idx_categories_grade ON categories(grade)'),
    ]

    for idx_name, sql in indexes:
        try:
            cursor.execute(sql)
            print(f"  Created {idx_name}")
        except Exception as e:
            print(f"  Warning {idx_name}: {e}")

    conn.commit()
    conn.close()

    print("\n" + "="*60)
    print("CLEANUP COMPLETE!")
    print("="*60)
    print(f"\nReduced categories from {total:,} to {final_count:,}")
    print(f"Saved {total - final_count:,} rows")
    print("\nNext steps:")
    print("  1. Test the edit listing modal - it should load instantly now")
    print("  2. Monitor for any issues with existing listings")

if __name__ == '__main__':
    cleanup_categories()
