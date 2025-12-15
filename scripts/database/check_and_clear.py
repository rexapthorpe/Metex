#!/usr/bin/env python3
"""
Check database tables and clear all marketplace data.
"""

import sqlite3
import sys

def main():
    try:
        conn = sqlite3.connect('marketplace.db')
        cursor = conn.cursor()

        # Get all tables in the database
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]

        print(f"\n[INFO] Found {len(tables)} tables in database:\n")
        for table in tables:
            count = cursor.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            print(f"   {table}: {count:,} records")

        print("\n" + "="*60)
        response = input("\nDelete ALL data from ALL tables (except users/addresses/preferences)? (yes/no): ").strip().lower()

        if response not in ['yes', 'y']:
            print("Operation cancelled.")
            return 0

        # Tables to preserve
        preserve_tables = {'users', 'addresses', 'user_preferences', 'sqlite_sequence'}

        # Disable foreign keys
        cursor.execute('PRAGMA foreign_keys = OFF')

        print("\n[CLEARING] Deleting data...\n")

        total_deleted = 0

        # Delete from all tables except preserved ones
        for table in tables:
            if table in preserve_tables:
                print(f"   [SKIP] {table} (preserved)")
                continue

            try:
                count = cursor.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                if count > 0:
                    cursor.execute(f'DELETE FROM {table}')
                    cursor.execute(f"DELETE FROM sqlite_sequence WHERE name = '{table}'")
                    total_deleted += count
                    print(f"   [OK] Cleared {count:,} records from {table}")
                else:
                    print(f"   [EMPTY] {table} was already empty")
            except sqlite3.Error as e:
                print(f"   [ERROR] Error clearing {table}: {e}")

        # Re-enable foreign keys
        cursor.execute('PRAGMA foreign_keys = ON')

        # Commit
        conn.commit()
        conn.close()

        print(f"\n[SUCCESS] Done! Total records deleted: {total_deleted:,}")

        return 0

    except Exception as e:
        print(f"\n[ERROR] {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
