#!/usr/bin/env python3
"""Run database migration to add category lookup index"""

import sqlite3

# Connect to database
conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# Create index for fast category lookups
cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_categories_lookup
    ON categories (metal, product_line, product_type, weight, purity, mint, year, finish, grade)
''')

conn.commit()
conn.close()

print("[OK] Migration completed: Added idx_categories_lookup index to categories table")
print("     This will significantly speed up Edit Listing modal save operations")
