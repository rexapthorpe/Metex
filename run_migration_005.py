"""
Migration runner for creating user_preferences table
Run this script to apply migration 005
"""

from database import get_db_connection

def run_migration():
    """Apply migration 005: Create user_preferences table"""
    conn = get_db_connection()
    cursor = conn.cursor()

    print("Applying migration 005: Create user_preferences table...")

    # Read and execute the migration SQL
    with open('migrations/005_create_user_preferences_table.sql', 'r') as f:
        migration_sql = f.read()

    try:
        cursor.executescript(migration_sql)
        conn.commit()
        print("✅ Migration 005 applied successfully!")

        # Verify table was created
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='user_preferences'
        """)
        if cursor.fetchone():
            print("✅ user_preferences table created")

            # Show table schema
            cursor.execute("PRAGMA table_info(user_preferences)")
            columns = cursor.fetchall()
            print("\nTable schema:")
            for col in columns:
                print(f"  - {col[1]} ({col[2]})")

            print("\n✅ Migration complete! You can now use notification preferences.")
        else:
            print("❌ Error: Table was not created")

    except Exception as e:
        print(f"❌ Error applying migration: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == '__main__':
    run_migration()
