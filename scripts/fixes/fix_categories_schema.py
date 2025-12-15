"""
Fix the categories table schema to restore PRIMARY KEY and AUTOINCREMENT
"""

from database import get_db_connection

def fix_categories_schema():
    """Recreate categories table with proper schema"""

    conn = get_db_connection()
    cursor = conn.cursor()

    print("=" * 70)
    print("FIXING CATEGORIES TABLE SCHEMA")
    print("=" * 70)

    # Step 1: Check current schema
    print("\n1. Checking current schema...")
    current_schema = cursor.execute('PRAGMA table_info(categories)').fetchall()
    id_column = [col for col in current_schema if col[1] == 'id'][0]
    print(f"   Current 'id' column: type={id_column[2]}, pk={id_column[5]}")

    if id_column[5] == 0:
        print("   [ISSUE] 'id' is NOT a primary key!")
    else:
        print("   [OK] 'id' is a primary key")
        conn.close()
        return

    # Step 2: Backup existing data
    print("\n2. Backing up existing categories...")
    existing_categories = cursor.execute('SELECT * FROM categories').fetchall()
    print(f"   Found {len(existing_categories)} categories to migrate")

    # Step 3: Drop and recreate table with proper schema
    print("\n3. Recreating table with proper schema...")
    cursor.execute('DROP TABLE categories')

    cursor.execute('''
        CREATE TABLE categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            year TEXT,
            weight TEXT,
            purity TEXT,
            mint TEXT,
            country_of_origin TEXT,
            coin_series TEXT,
            denomination TEXT,
            grade TEXT,
            finish TEXT,
            special_designation TEXT,
            metal TEXT,
            product_type TEXT,
            bucket_id INTEGER,
            product_line TEXT
        )
    ''')

    print("   [OK] Table recreated with proper schema")

    # Step 4: Restore data (SQLite will auto-assign new IDs)
    print("\n4. Restoring categories...")

    # Keep track of old ID -> new ID mapping
    id_mapping = {}

    for old_row in existing_categories:
        old_id = old_row[0]  # Original ID (might be NULL)

        # Insert without ID (let it auto-increment)
        cursor.execute('''
            INSERT INTO categories (
                name, year, weight, purity, mint, country_of_origin,
                coin_series, denomination, grade, finish, special_designation,
                metal, product_type, bucket_id, product_line
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', old_row[1:])  # All columns except ID

        new_id = cursor.lastrowid
        id_mapping[old_id] = new_id

    print(f"   [OK] Restored {len(id_mapping)} categories")

    # Step 5: Update listings to use new category IDs
    print("\n5. Updating listing references...")
    listings = cursor.execute('SELECT id, category_id FROM listings').fetchall()

    updated_count = 0
    for listing_id, old_cat_id in listings:
        if old_cat_id in id_mapping:
            new_cat_id = id_mapping[old_cat_id]
            cursor.execute(
                'UPDATE listings SET category_id = ? WHERE id = ?',
                (new_cat_id, listing_id)
            )
            updated_count += 1
        else:
            print(f"   [WARNING] Listing {listing_id} references unknown category {old_cat_id}")

    print(f"   [OK] Updated {updated_count} listing references")

    # Step 6: Update bids to use new category IDs
    print("\n6. Updating bid references...")
    bids = cursor.execute('SELECT id, category_id FROM bids').fetchall()

    bid_updated_count = 0
    for bid_id, old_cat_id in bids:
        if old_cat_id in id_mapping:
            new_cat_id = id_mapping[old_cat_id]
            cursor.execute(
                'UPDATE bids SET category_id = ? WHERE id = ?',
                (new_cat_id, bid_id)
            )
            bid_updated_count += 1

    print(f"   [OK] Updated {bid_updated_count} bid references")

    # Step 7: Recreate indexes
    print("\n7. Recreating indexes...")
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
        'CREATE INDEX IF NOT EXISTS idx_categories_bucket_id ON categories(bucket_id)'
    ]

    for sql in indexes:
        cursor.execute(sql)

    print(f"   [OK] Created {len(indexes)} indexes")

    conn.commit()

    # Step 8: Verify
    print("\n8. Verifying fix...")
    new_schema = cursor.execute('PRAGMA table_info(categories)').fetchall()
    id_column = [col for col in new_schema if col[1] == 'id'][0]
    print(f"   New 'id' column: type={id_column[2]}, pk={id_column[5]}")

    if id_column[5] > 0:
        print("   [OK] 'id' is now a PRIMARY KEY!")
    else:
        print("   [ERROR] 'id' is still not a primary key")

    # Check for orphaned listings
    orphaned = cursor.execute('''
        SELECT COUNT(*) as cnt
        FROM listings l
        LEFT JOIN categories c ON l.category_id = c.id
        WHERE c.id IS NULL
    ''').fetchone()

    print(f"   Orphaned listings: {orphaned[0]}")

    print("\n" + "=" * 70)
    print("SCHEMA FIX COMPLETE")
    print("=" * 70)

    conn.close()

if __name__ == '__main__':
    fix_categories_schema()
