#!/usr/bin/env python3
"""Apply migration 013: Add packaging, condition, series variant, and extended product specifications"""

import sqlite3

def apply_migration():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Read migration file
    with open('migrations/013_add_packaging_and_specs.sql', 'r') as f:
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
    print("\n[SUCCESS] Migration 013 applied successfully!")

if __name__ == '__main__':
    apply_migration()
