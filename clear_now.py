#!/usr/bin/env python3
"""Clear all marketplace data from database.db RIGHT NOW"""

import sqlite3

print("\n[INFO] Connecting to database.db...")

conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
tables = [row[0] for row in cursor.fetchall()]

print(f"[INFO] Found {len(tables)} tables\n")

# Tables to preserve
preserve = {'users', 'addresses', 'user_preferences'}

# Disable FK constraints
cursor.execute('PRAGMA foreign_keys = OFF')

total = 0

for table in tables:
    if table in preserve:
        print(f"   [SKIP] {table} (preserved)")
        continue

    try:
        count = cursor.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        if count > 0:
            cursor.execute(f'DELETE FROM {table}')
            cursor.execute(f"DELETE FROM sqlite_sequence WHERE name = '{table}'")
            total += count
            print(f"   [DELETED] {table}: {count:,} records")
        else:
            print(f"   [EMPTY] {table}: 0 records")
    except Exception as e:
        print(f"   [ERROR] {table}: {e}")

# Re-enable FK
cursor.execute('PRAGMA foreign_keys = ON')

conn.commit()
conn.close()

print(f"\n[SUCCESS] Deleted {total:,} total records!")
print("[DONE] All marketplace data cleared.\n")
