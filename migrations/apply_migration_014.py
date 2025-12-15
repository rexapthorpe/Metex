#!/usr/bin/env python3
"""
Apply migration 014: Add third-party grading fields to order_items
"""
import sqlite3

def apply_migration():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    try:
        # Read and execute migration SQL
        with open('migrations/014_add_third_party_grading_to_order_items.sql', 'r') as f:
            migration_sql = f.read()

        # Split by semicolon and execute each statement
        statements = [s.strip() for s in migration_sql.split(';') if s.strip() and not s.strip().startswith('--')]

        for statement in statements:
            if statement:
                cursor.execute(statement)
                print(f"[OK] Executed: {statement[:60]}...")

        conn.commit()
        print("\n[OK] Migration 014 applied successfully!")

        # Verify columns were added
        cursor.execute("PRAGMA table_info(order_items)")
        columns = cursor.fetchall()
        grading_columns = [col for col in columns if 'grading' in col[1] or 'third_party' in col[1]]

        print("\nGrading-related columns in order_items:")
        for col in grading_columns:
            print(f"  - {col[1]} ({col[2]})")

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Error applying migration: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    apply_migration()
