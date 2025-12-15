import sqlite3

conn = sqlite3.connect('marketplace.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get table schema
cursor.execute('PRAGMA table_info(categories)')
columns = cursor.fetchall()

if not columns:
    print("No columns found or table doesn't exist!")
else:
    print(f"Found {len(columns)} columns in categories table:")
    print("-" * 80)
    for col in columns:
        print(f"  Column #{col['cid']}: {col['name']} ({col['type']})")

conn.close()
