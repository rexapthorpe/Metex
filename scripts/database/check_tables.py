"""
Check what tables exist in the database
"""
import sqlite3

conn = sqlite3.connect('metex.db')
cursor = conn.cursor()

print("=" * 80)
print("DATABASE TABLES")
print("=" * 80)

tables = cursor.execute("""
    SELECT name FROM sqlite_master
    WHERE type='table'
    ORDER BY name
""").fetchall()

for table in tables:
    print(f"\n{table[0]}")

    # Get column info
    cols = cursor.execute(f"PRAGMA table_info({table[0]})").fetchall()
    for col in cols:
        print(f"  - {col[1]} ({col[2]})")

conn.close()
