"""
Check the listings table schema to find photo column name
"""
import sqlite3

conn = sqlite3.connect('database.db')
cursor = conn.cursor()

print("=" * 70)
print("LISTINGS TABLE SCHEMA")
print("=" * 70)

# Get table schema
cursor.execute("PRAGMA table_info(listings)")
columns = cursor.fetchall()

print(f"\nTotal columns found: {len(columns)}")
print("\nColumn Information:")
print(f"{'Index':<6} {'Name':<25} {'Type':<15} {'NotNull':<8} {'Default':<15} {'PK'}")
print("-" * 85)

if columns:
    for col in columns:
        idx, name, col_type, not_null, default_val, pk = col
        print(f"{idx:<6} {name:<25} {col_type:<15} {not_null:<8} {str(default_val):<15} {pk}")
else:
    print("ERROR: No columns returned from PRAGMA table_info(listings)")
    print("\nChecking if listings table exists...")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='listings'")
    table_exists = cursor.fetchone()
    if table_exists:
        print("Table 'listings' EXISTS")
    else:
        print("Table 'listings' DOES NOT EXIST")

    print("\nAll tables in database:")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    for table in tables:
        print(f"  - {table[0]}")

print("\n" + "=" * 70)

# Check for photo-related columns
photo_columns = [col for col in columns if 'photo' in col[1].lower() or 'image' in col[1].lower()]

if photo_columns:
    print("PHOTO-RELATED COLUMNS FOUND:")
    for col in photo_columns:
        print(f"  - {col[1]} ({col[2]})")
else:
    print("NO PHOTO-RELATED COLUMNS FOUND")

print("=" * 70)

conn.close()
