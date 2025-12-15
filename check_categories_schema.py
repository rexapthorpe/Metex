import sqlite3

conn = sqlite3.connect('marketplace.db')
cursor = conn.cursor()

# Get table schema
cursor.execute('PRAGMA table_info(categories)')
columns = cursor.fetchall()

print("Categories table columns:")
print("-" * 60)
for col in columns:
    cid, name, dtype, notnull, default, pk = col
    print(f"{name:25s} {dtype:15s} {'NOT NULL' if notnull else ''}")

# Check if condition_category and series_variant exist
col_names = [col[1] for col in columns]
has_condition_category = 'condition_category' in col_names
has_series_variant = 'series_variant' in col_names

print("\n" + "=" * 60)
print(f"Has condition_category: {has_condition_category}")
print(f"Has series_variant: {has_series_variant}")

# If they exist, check a sample bucket
if has_condition_category and has_series_variant:
    print("\nSample buckets with these fields:")
    print("-" * 60)
    cursor.execute('''
        SELECT bucket_id, metal, product_type, condition_category, series_variant
        FROM categories
        WHERE condition_category IS NOT NULL OR series_variant IS NOT NULL
        LIMIT 5
    ''')
    sample_buckets = cursor.fetchall()
    if sample_buckets:
        for bucket in sample_buckets:
            print(f"Bucket {bucket[0]}: {bucket[1]} {bucket[2]} | CC: {bucket[3]} | SV: {bucket[4]}")
    else:
        print("No buckets have condition_category or series_variant set.")

conn.close()
