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


def ensure_system_settings_table():
    """
    Ensure the system_settings table exists.
    Creates it on first run if missing.
    """
    try:
        conn = get_db_connection()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS system_settings (
                key        TEXT PRIMARY KEY,
                value      TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f'Error ensuring system_settings table: {e}')


def ensure_order_items_audit_columns():
    """
    Ensure order_items has columns for auditing the spot price used at checkout.

    Columns added (idempotent):
        spot_as_of_used    TEXT NULL  — ISO-8601 timestamp of the snapshot used
        spot_source_used   TEXT NULL  — 'metalpriceapi' | 'metals_live' | ...
        spot_premium_used  REAL NULL  — listing's spot_premium at purchase time
        weight_used        REAL NULL  — listing's weight at purchase time

    The existing nullable columns spot_price_at_purchase and
    pricing_mode_at_purchase are already in the schema and are populated by
    create_order(); this function only adds the four new fields.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(order_items)")
        existing = {col[1] for col in cursor.fetchall()}

        new_cols = [
            ("spot_as_of_used",   "TEXT"),
            ("spot_source_used",  "TEXT"),
            ("spot_premium_used", "REAL"),
            ("weight_used",       "REAL"),
        ]
        added = []
        for col_name, col_type in new_cols:
            if col_name not in existing:
                cursor.execute(
                    f"ALTER TABLE order_items ADD COLUMN {col_name} {col_type}"
                )
                added.append(col_name)

        if added:
            conn.commit()
            print(f"✅ order_items audit columns added: {added}")

        conn.close()
    except Exception as e:
        print(f"Error ensuring order_items audit columns: {e}")


def ensure_security_audit_log_table():
    """Ensure the security_audit_log table exists with all required columns."""
    try:
        conn = get_db_connection()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS security_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                user_id INTEGER,
                target_user_id INTEGER,
                target_resource_type TEXT,
                target_resource_id TEXT,
                ip_address TEXT,
                user_agent TEXT,
                request_path TEXT,
                request_method TEXT,
                details TEXT,
                severity TEXT DEFAULT 'INFO',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

        # Add any columns that may be missing from pre-migration tables
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(security_audit_log)")
        existing = {col[1] for col in cursor.fetchall()}
        added = []
        for col_name, col_def in [
            ('target_user_id', 'INTEGER'),
            ('target_resource_type', 'TEXT'),
            ('target_resource_id', 'TEXT'),
            ('user_agent', 'TEXT'),
            ('request_path', 'TEXT'),
            ('request_method', 'TEXT'),
            ('severity', "TEXT DEFAULT 'INFO'"),
        ]:
            if col_name not in existing:
                cursor.execute(f'ALTER TABLE security_audit_log ADD COLUMN {col_name} {col_def}')
                added.append(col_name)
        if added:
            conn.commit()
            print(f'✅ security_audit_log columns added: {added}')
        conn.close()
    except Exception as e:
        print(f'Error ensuring security_audit_log table: {e}')


def ensure_payment_methods_table():
    """Ensure the payment_methods table exists."""
    try:
        conn = get_db_connection()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS payment_methods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                card_type TEXT NOT NULL,
                last_four TEXT NOT NULL,
                expiry_month INTEGER NOT NULL,
                expiry_year INTEGER NOT NULL,
                cardholder_name TEXT,
                is_default INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f'Error ensuring payment_methods table: {e}')


def ensure_cancellation_columns():
    """
    Ensure orders table has canceled_at and cancellation_reason columns.
    Used by cancellation_routes.py when an order is canceled.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(orders)")
        existing = {col[1] for col in cursor.fetchall()}
        added = []
        for col_name, col_def in [
            ('canceled_at', 'TIMESTAMP'),
            ('cancellation_reason', 'TEXT'),
        ]:
            if col_name not in existing:
                cursor.execute(f'ALTER TABLE orders ADD COLUMN {col_name} {col_def}')
                added.append(col_name)
        if added:
            conn.commit()
            print(f'✅ orders columns added: {added}')
        conn.close()
    except Exception as e:
        print(f'Error ensuring cancellation columns: {e}')


def ensure_user_status_columns():
    """
    Ensure users table has is_banned, is_frozen, and freeze_reason columns.
    These are read by the login route and throughout the admin panel.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users)")
        existing = {col[1] for col in cursor.fetchall()}
        added = []
        for col_name, col_def in [
            ('is_banned', 'INTEGER DEFAULT 0'),
            ('is_frozen', 'INTEGER DEFAULT 0'),
            ('freeze_reason', 'TEXT'),
        ]:
            if col_name not in existing:
                cursor.execute(f'ALTER TABLE users ADD COLUMN {col_name} {col_def}')
                added.append(col_name)
        if added:
            conn.commit()
            print(f'✅ users status columns added: {added}')
        conn.close()
    except Exception as e:
        print(f'Error ensuring user status columns: {e}')


def ensure_listing_photo_columns():
    """
    Ensure listings table has photo_filename and listing_title columns
    (added during photo upload migration).
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(listings)")
        existing = {col[1] for col in cursor.fetchall()}
        added = []
        for col_name, col_def in [
            ('photo_filename', 'TEXT'),
            ('listing_title', 'TEXT'),
        ]:
            if col_name not in existing:
                cursor.execute(f'ALTER TABLE listings ADD COLUMN {col_name} {col_def}')
                added.append(col_name)
        if added:
            conn.commit()
            print(f'✅ listings columns added: {added}')
        conn.close()
    except Exception as e:
        print(f'Error ensuring listing photo columns: {e}')


def ensure_notification_settings_table():
    """
    Ensure the notification_settings table exists (migration 025).
    Stores per-user, per-type notification opt-in/opt-out preferences.
    """
    try:
        conn = get_db_connection()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS notification_settings (
                user_id           INTEGER NOT NULL,
                notification_type TEXT    NOT NULL,
                enabled           INTEGER NOT NULL DEFAULT 1,
                updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, notification_type),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f'Error ensuring notification_settings table: {e}')


def init_database():
    """
    Run all database initialization checks
    Call this function during app startup
    """
    ensure_admin_column()
    ensure_user_status_columns()
    ensure_password_reset_tokens_table()
    ensure_system_settings_table()
    ensure_order_items_audit_columns()
    ensure_cancellation_columns()
    ensure_listing_photo_columns()
    ensure_notification_settings_table()
    ensure_security_audit_log_table()
    ensure_payment_methods_table()
