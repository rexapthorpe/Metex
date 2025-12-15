"""
FAST cleanup - recreate categories table with only active rows
Much faster than DELETE for 26M rows
"""
import sqlite3
import time
from database import get_db_connection

print("="*60)
print("CATEGORY CLEANUP (FAST METHOD)")
print("="*60)

conn = get_db_connection()
cursor = conn.cursor()

# 1. Count current state
total = cursor.execute('SELECT COUNT(*) FROM categories').fetchone()[0]
in_use = cursor.execute('SELECT COUNT(DISTINCT category_id) FROM listings').fetchone()[0]
print(f"\nCurrent: {total:,} categories ({in_use:,} in use)")

# 2. Create new table with only active categories
print("\nCreating new categories table with only active rows...")
start = time.time()

cursor.execute('''
    CREATE TABLE categories_new AS
    SELECT DISTINCT c.*
    FROM categories c
    INNER JOIN listings l ON c.id = l.category_id
''')

elapsed = time.time() - start
new_count = cursor.execute('SELECT COUNT(*) FROM categories_new').fetchone()[0]
print(f"Created new table with {new_count:,} rows in {elapsed:.2f}s")

# 3. Drop old table and rename new one
print("\nReplacing old table...")
cursor.execute('DROP TABLE categories')
cursor.execute('ALTER TABLE categories_new RENAME TO categories')
print("Table replaced")

# 4. Vacuum to reclaim space
print("\nVacuuming database to reclaim space...")
start = time.time()
conn.commit()
cursor.execute('VACUUM')
elapsed = time.time() - start
print(f"Vacuumed in {elapsed:.2f}s")

# 5. Create indexes
print("\nCreating indexes for fast queries...")
indexes = [
    'CREATE INDEX idx_categories_metal ON categories(metal)',
    'CREATE INDEX idx_categories_product_line ON categories(product_line)',
    'CREATE INDEX idx_categories_product_type ON categories(product_type)',
    'CREATE INDEX idx_categories_weight ON categories(weight)',
    'CREATE INDEX idx_categories_purity ON categories(purity)',
    'CREATE INDEX idx_categories_mint ON categories(mint)',
    'CREATE INDEX idx_categories_year ON categories(year)',
    'CREATE INDEX idx_categories_finish ON categories(finish)',
    'CREATE INDEX idx_categories_grade ON categories(grade)',
]

for i, sql in enumerate(indexes, 1):
    cursor.execute(sql)
    print(f"  {i}/9 indexes created")

conn.commit()

# 6. Verify
final = cursor.execute('SELECT COUNT(*) FROM categories').fetchone()[0]
print(f"\nFinal: {final:,} categories")
print(f"Saved: {total - final:,} rows")

conn.close()

print("\n" + "="*60)
print("CLEANUP COMPLETE!")
print("="*60)
print("\nModal should now load instantly!")
