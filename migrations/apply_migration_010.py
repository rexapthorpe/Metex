#!/usr/bin/env python3
"""Apply migration 010: Add isolated and set listings support"""

import sqlite3

def apply_migration():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Read migration file
    with open('migrations/010_add_isolated_and_set_listings.sql', 'r') as f:
        migration_sql = f.read()

    # Split by statement and execute each one
    statements = [s.strip() for s in migration_sql.split(';') if s.strip() and not s.strip().startswith('--')]

    for statement in statements:
        if statement:
            try:
                cursor.execute(statement)
                print(f"[OK] Executed: {statement[:60]}...")
            except Exception as e:
                print(f"[ERROR] Error on statement: {statement[:60]}...")
                print(f"  Error: {e}")

    conn.commit()
    conn.close()
    print("\n[SUCCESS] Migration 010 applied successfully!")

if __name__ == '__main__':
    apply_migration()
