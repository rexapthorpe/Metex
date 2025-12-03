#!/usr/bin/env python3
"""Run database migration to create account details tables"""

import sqlite3

# Connect to database
conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# Read and execute migration SQL
with open('migrations/002_create_account_details_tables.sql', 'r') as f:
    migration_sql = f.read()

# Execute each statement
cursor.executescript(migration_sql)

conn.commit()
conn.close()

print("[OK] Migration 002 completed: Created addresses and notification_preferences tables")
