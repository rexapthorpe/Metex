"""
Automatic cleanup script - no confirmation needed
Removes orphaned categories and optimizes database
"""
import sqlite3
import time
from database import get_db_connection

print("="*60)
print("CATEGORY CLEANUP SCRIPT (AUTO)")
print("="*60)

conn = get_db_connection()
cursor = conn.cursor()

# 1. Count total categories
total = cursor.execute('SELECT COUNT(*) FROM categories').fetchone()[0]
print(f"\n1. Current category count: {total:,}")

# 2. Count categories in use
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
    exit(0)

# 3. Delete orphaned categories
print(f"\nDeleting {orphaned:,} orphaned categories...")
start = time.time()

cursor.execute('''
    DELETE FROM categories
    WHERE id NOT IN (SELECT DISTINCT category_id FROM listings)
''')

deleted = cursor.rowcount
elapsed = time.time() - start
print(f"Deleted {deleted:,} categories in {elapsed:.2f} seconds")

# 4. Vacuum
print("\nVacuuming database...")
start = time.time()
conn.commit()
cursor.execute('VACUUM')
elapsed = time.time() - start
print(f"Vacuumed in {elapsed:.2f} seconds")

# 5. Verify
final_count = cursor.execute('SELECT COUNT(*) FROM categories').fetchone()[0]
print(f"\nFinal category count: {final_count:,}")

# 6. Create indexes
print("\nCreating indexes...")
indexes = [
    'CREATE INDEX IF NOT EXISTS idx_categories_metal ON categories(metal)',
    'CREATE INDEX IF NOT EXISTS idx_categories_product_line ON categories(product_line)',
    'CREATE INDEX IF NOT EXISTS idx_categories_product_type ON categories(product_type)',
    'CREATE INDEX IF NOT EXISTS idx_categories_weight ON categories(weight)',
    'CREATE INDEX IF NOT EXISTS idx_categories_purity ON categories(purity)',
    'CREATE INDEX IF NOT EXISTS idx_categories_mint ON categories(mint)',
    'CREATE INDEX IF NOT EXISTS idx_categories_year ON categories(year)',
    'CREATE INDEX IF NOT EXISTS idx_categories_finish ON categories(finish)',
    'CREATE INDEX IF NOT EXISTS idx_categories_grade ON categories(grade)',
]

for sql in indexes:
    cursor.execute(sql)
    print("  Created index")

conn.commit()
conn.close()

print("\n" + "="*60)
print("CLEANUP COMPLETE!")
print("="*60)
print(f"Reduced from {total:,} to {final_count:,} categories")
