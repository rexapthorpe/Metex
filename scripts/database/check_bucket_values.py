from database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Check buckets with condition_category or series_variant set
cursor.execute('''
    SELECT bucket_id, metal, product_type, weight, condition_category, series_variant
    FROM categories
    WHERE condition_category IS NOT NULL OR series_variant IS NOT NULL
    LIMIT 10
''')
buckets = cursor.fetchall()

print(f"Found {len(buckets)} buckets with condition_category or series_variant:")
print("-" * 100)
for bucket in buckets:
    print(f"Bucket {bucket['bucket_id']:5d}: {bucket['metal']:8s} {bucket['product_type']:10s} {bucket['weight']:10s} | CC: {bucket['condition_category'] or 'NULL':20s} | SV: {bucket['series_variant'] or 'NULL':20s}")

# Also check total buckets
cursor.execute('SELECT COUNT(*) as total FROM categories')
total = cursor.fetchone()['total']
print(f"\nTotal buckets in database: {total}")

conn.close()
