"""
Database initialization and schema checks
Ensures required columns exist before the app starts
"""
import sqlite3
from database import get_db_connection


def ensure_admin_column():
    """
    Ensure the is_admin column exists in the users table.
    If it doesn't exist, add it with a default value of 0.

    This is a safety check that runs on app startup to prevent crashes
    if the migration hasn't been run yet.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if is_admin column exists
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'is_admin' not in columns:
            print('\n⚠️  is_admin column missing - adding it now...')

            # Add the column
            cursor.execute('ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0')

            # Create index for performance
            try:
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_is_admin ON users(is_admin)')
            except sqlite3.OperationalError:
                # Index might already exist, ignore
                pass

            conn.commit()
            print('✅ is_admin column added successfully!')
            print('   All existing users default to is_admin=0 (non-admin)')
            print('   Use: flask make-admin user@email.com to promote users\n')

        conn.close()

    except Exception as e:
        print(f'❌ Error checking/adding is_admin column: {e}')
        # Don't crash the app - the auth_utils functions will handle missing column gracefully


def ensure_password_reset_tokens_table():
    """
    Ensure the password_reset_tokens table exists.
    Creates it on first run if missing.
    """
    try:
        conn = get_db_connection()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                ip_address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f'Error ensuring password_reset_tokens table: {e}')


def init_database():
    """
    Run all database initialization checks
    Call this function during app startup
    """
    ensure_admin_column()
    ensure_password_reset_tokens_table()
