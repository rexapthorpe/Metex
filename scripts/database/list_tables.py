#!/usr/bin/env python3
"""Quick script to list all tables in the marketplace database."""

import sqlite3

conn = sqlite3.connect('marketplace.db')
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
tables = cursor.fetchall()

print("Tables in marketplace.db:")
print("=" * 50)
for table in tables:
    print(f"  {table[0]}")

conn.close()
