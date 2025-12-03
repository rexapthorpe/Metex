#!/usr/bin/env python3
"""Run database migration to add user profile columns"""

import sqlite3

# Connect to database
conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# Check if columns already exist
cursor.execute('PRAGMA table_info(users)')
columns = [col[1] for col in cursor.fetchall()]

# Add columns that don't exist
if 'first_name' not in columns:
    cursor.execute('ALTER TABLE users ADD COLUMN first_name TEXT')
    print("Added column: first_name")

if 'last_name' not in columns:
    cursor.execute('ALTER TABLE users ADD COLUMN last_name TEXT')
    print("Added column: last_name")

if 'phone' not in columns:
    cursor.execute('ALTER TABLE users ADD COLUMN phone TEXT')
    print("Added column: phone")

if 'bio' not in columns:
    cursor.execute('ALTER TABLE users ADD COLUMN bio TEXT')
    print("Added column: bio")

if 'created_at' not in columns:
    cursor.execute('ALTER TABLE users ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
    print("Added column: created_at")

conn.commit()
conn.close()

print("[OK] Migration 003 completed: Added user profile columns to users table")
