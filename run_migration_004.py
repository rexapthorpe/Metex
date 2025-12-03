"""
Run migration 004: Create notifications table
"""
import sqlite3
from database import get_db_connection

def run_migration():
    conn = get_db_connection()
    cursor = conn.cursor()

    print("Running migration 004: Create notifications table...")

    with open('migrations/004_create_notifications_table.sql', 'r') as f:
        migration_sql = f.read()

    # Execute the entire script at once (SQLite executescript handles multiple statements)
    try:
        cursor.executescript(migration_sql)
        print("[OK] Executed migration script")
    except sqlite3.Error as e:
        print(f"[ERROR] {e}")
        conn.rollback()
        conn.close()
        return

    conn.commit()
    conn.close()

    print("\n[SUCCESS] Migration 004 completed successfully!")
    print("Notifications table created with indexes.")

if __name__ == '__main__':
    run_migration()
