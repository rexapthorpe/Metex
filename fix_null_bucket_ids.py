"""
Fix NULL bucket_id values in categories table.

Assigns bucket_id to categories based on core attributes:
- Same bucket: metal, product_line, product_type, weight, purity, mint, year
- Different bucket: different finish or grade (variants of same item)
"""

from database import get_db_connection
import sqlite3

def fix_null_bucket_ids():
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Find all categories with NULL bucket_id
    null_categories = cursor.execute('''
        SELECT id, metal, product_line, product_type, weight, purity, mint, year, finish, grade
        FROM categories
        WHERE bucket_id IS NULL
        ORDER BY id
    ''').fetchall()

    print(f"Found {len(null_categories)} categories with NULL bucket_id")

    if not null_categories:
        print("No categories to fix!")
        conn.close()
        return

    # Get the current maximum bucket_id
    max_bucket = cursor.execute('SELECT COALESCE(MAX(bucket_id), 0) AS max_id FROM categories').fetchone()
    next_bucket_id = max_bucket['max_id'] + 1

    print(f"Starting from bucket_id: {next_bucket_id}")

    # Track which core attribute combinations we've seen
    bucket_map = {}  # (metal, product_line, product_type, weight, purity, mint, year) -> bucket_id

    updated_count = 0

    for cat in null_categories:
        # Core attributes that define a bucket
        core_key = (
            cat['metal'],
            cat['product_line'],
            cat['product_type'],
            cat['weight'],
            cat['purity'],
            cat['mint'],
            cat['year']
        )

        # Check if we've already assigned a bucket_id for this core combination
        if core_key in bucket_map:
            bucket_id = bucket_map[core_key]
            print(f"  Category {cat['id']}: Reusing bucket_id {bucket_id} (same core attributes)")
        else:
            # Check if this core combination already exists in the database with a bucket_id
            existing = cursor.execute('''
                SELECT bucket_id FROM categories
                WHERE metal = ? AND product_line = ? AND product_type = ?
                  AND weight = ? AND purity = ? AND mint = ? AND year = ?
                  AND bucket_id IS NOT NULL
                LIMIT 1
            ''', core_key).fetchone()

            if existing:
                bucket_id = existing['bucket_id']
                print(f"  Category {cat['id']}: Using existing bucket_id {bucket_id}")
            else:
                bucket_id = next_bucket_id
                next_bucket_id += 1
                print(f"  Category {cat['id']}: Assigned new bucket_id {bucket_id}")

            bucket_map[core_key] = bucket_id

        # Update the category with the bucket_id
        cursor.execute('''
            UPDATE categories
            SET bucket_id = ?
            WHERE id = ?
        ''', (bucket_id, cat['id']))

        updated_count += 1

    conn.commit()
    print(f"\n✅ Successfully updated {updated_count} categories with bucket_id values")

    # Verify the fix
    remaining_nulls = cursor.execute('SELECT COUNT(*) as cnt FROM categories WHERE bucket_id IS NULL').fetchone()
    print(f"Remaining categories with NULL bucket_id: {remaining_nulls['cnt']}")

    conn.close()

if __name__ == '__main__':
    fix_null_bucket_ids()
