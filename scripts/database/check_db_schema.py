from database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Get table schema
cursor.execute('PRAGMA table_info(categories)')
columns = cursor.fetchall()

print(f"Found {len(columns)} columns in categories table:")
print("-" * 80)
for col in columns:
    print(f"  {col['name']:25s} {col['type']:15s}")

# Check if condition_category and series_variant exist
col_names = [col['name'] for col in columns]
has_condition_category = 'condition_category' in col_names
has_series_variant = 'series_variant' in col_names

print("\n" + "=" * 80)
print(f"Has condition_category: {has_condition_category}")
print(f"Has series_variant: {has_series_variant}")

conn.close()
