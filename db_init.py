"""
Database initialization and schema checks
Ensures required columns exist before the app starts
"""
from database import get_db_connection, get_table_columns, IS_POSTGRES


def _ddl(sql):
    """Translate SQLite-specific DDL to PostgreSQL when IS_POSTGRES is True."""
    if IS_POSTGRES:
        sql = sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
    return sql


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

        columns = get_table_columns(conn, 'users')

        if 'is_admin' not in columns:
            print('\n⚠️  is_admin column missing - adding it now...')

            # Add the column
            cursor.execute('ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0')

            # Create index for performance
            try:
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_is_admin ON users(is_admin)')
            except Exception:
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
        conn.execute(_ddl('''
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
        '''))
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
        existing = get_table_columns(conn, 'order_items')

        new_cols = [
            ("spot_as_of_used",   "TEXT"),
            ("spot_source_used",  "TEXT"),
            ("spot_premium_used", "REAL"),
            ("weight_used",       "REAL"),
        ]
        added = []
        cursor = conn.cursor()
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
        conn.execute(_ddl('''
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
        '''))
        conn.commit()

        # Add any columns that may be missing from pre-migration tables
        existing = get_table_columns(conn, 'security_audit_log')
        added = []
        cursor = conn.cursor()
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
        conn.execute(_ddl('''
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
        '''))
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
        existing = get_table_columns(conn, 'orders')
        added = []
        cursor = conn.cursor()
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
        existing = get_table_columns(conn, 'users')
        added = []
        cursor = conn.cursor()
        for col_name, col_def in [
            ('is_banned', 'INTEGER DEFAULT 0'),
            ('is_frozen', 'INTEGER DEFAULT 0'),
            ('freeze_reason', 'TEXT'),
            ('bid_payment_strikes', 'INTEGER DEFAULT 0'),
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
        existing = get_table_columns(conn, 'listings')
        added = []
        cursor = conn.cursor()
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


def ensure_ratings_multi_seller_constraint():
    """
    Migrate the ratings unique constraint from (order_id, rater_id) to
    (order_id, rater_id, ratee_id) so buyers can rate each seller
    in a multi-seller order individually.

    Safe to call multiple times (idempotent).
    """
    try:
        conn = get_db_connection()
        if IS_POSTGRES:
            # Drop old 2-column constraint if it exists; new one is added below.
            try:
                conn.execute(
                    "ALTER TABLE ratings DROP CONSTRAINT IF EXISTS ratings_order_id_rater_id_key"
                )
                conn.execute(
                    "ALTER TABLE ratings ADD CONSTRAINT IF NOT EXISTS "
                    "ratings_order_id_rater_id_ratee_id_key "
                    "UNIQUE (order_id, rater_id, ratee_id)"
                )
                conn.commit()
            except Exception:
                conn.rollback()
        else:
            # SQLite: recreate table only when old constraint (without ratee_id) detected.
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='ratings'"
            ).fetchone()
            if row and row['sql'] and 'UNIQUE(order_id, rater_id, ratee_id)' not in row['sql']:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS ratings_new (
                        id        INTEGER PRIMARY KEY AUTOINCREMENT,
                        order_id  INTEGER NOT NULL,
                        rater_id  INTEGER NOT NULL,
                        ratee_id  INTEGER NOT NULL,
                        rating    INTEGER NOT NULL,
                        comment   TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (order_id)  REFERENCES orders(id),
                        FOREIGN KEY (rater_id)  REFERENCES users(id),
                        FOREIGN KEY (ratee_id)  REFERENCES users(id),
                        UNIQUE(order_id, rater_id, ratee_id)
                    )
                ''')
                conn.execute('INSERT INTO ratings_new SELECT * FROM ratings')
                conn.execute('DROP TABLE ratings')
                conn.execute('ALTER TABLE ratings_new RENAME TO ratings')
                conn.commit()
                print('✅ Migrated ratings UNIQUE constraint to (order_id, rater_id, ratee_id)')
        conn.close()
    except Exception as e:
        print(f'Error migrating ratings constraint: {e}')


def ensure_message_type_column():
    """
    Ensure messages table has a message_type column to distinguish
    'support' messages from 'feedback' messages.
    """
    try:
        conn = get_db_connection()
        existing = get_table_columns(conn, 'messages')
        if 'message_type' not in existing:
            conn.execute("ALTER TABLE messages ADD COLUMN message_type TEXT DEFAULT 'support'")
            conn.commit()
            print("✅ messages.message_type column added")
        conn.close()
    except Exception as e:
        print(f'Error ensuring message_type column: {e}')


def ensure_metex_guaranteed_column():
    """
    Ensure the is_metex_guaranteed column exists in the users table.
    Admin-controlled flag that replaces the rating display with a platform badge.
    """
    try:
        conn = get_db_connection()
        existing = get_table_columns(conn, 'users')
        if 'is_metex_guaranteed' not in existing:
            conn.execute('ALTER TABLE users ADD COLUMN is_metex_guaranteed INTEGER DEFAULT 0')
            conn.commit()
            print('✅ users.is_metex_guaranteed column added')
        conn.close()
    except Exception as e:
        print(f'Error ensuring is_metex_guaranteed column: {e}')


def migrate_default_fee_to_5pct():
    """
    One-time migration: update the default_platform_fee row in fee_config
    from the old seeded value (2.5%) to the new default (5.0%).
    Only updates if the current value is still the old 2.5 default.
    """
    try:
        conn = get_db_connection()
        row = conn.execute(
            "SELECT fee_value FROM fee_config WHERE config_key = 'default_platform_fee' AND active = 1"
        ).fetchone()
        if row and float(row['fee_value']) == 2.5:
            conn.execute(
                "UPDATE fee_config SET fee_value = 5.0, updated_at = CURRENT_TIMESTAMP WHERE config_key = 'default_platform_fee'"
            )
            conn.commit()
            print('✅ default_platform_fee updated from 2.5% to 5.0%')
        conn.close()
    except Exception as e:
        print(f'Error migrating default platform fee: {e}')


def ensure_stripe_customer_id_column():
    """
    Ensure users table has stripe_customer_id column (migration 028).
    This is the buyer-facing Stripe Customer ID for saved payment methods.
    Separate from stripe_account_id (seller payouts).
    """
    try:
        conn = get_db_connection()
        existing = get_table_columns(conn, 'users')
        if 'stripe_customer_id' not in existing:
            conn.execute('ALTER TABLE users ADD COLUMN stripe_customer_id TEXT')
            conn.commit()
            print('✅ users.stripe_customer_id column added (migration 028)')
        conn.close()
    except Exception as e:
        print(f'Error ensuring stripe_customer_id column: {e}')


def init_database():
    """
    Run all database initialization checks
    Call this function during app startup
    """
    ensure_admin_column()
    ensure_user_status_columns()
    ensure_metex_guaranteed_column()
    ensure_password_reset_tokens_table()
    ensure_system_settings_table()
    ensure_order_items_audit_columns()
    ensure_cancellation_columns()
    ensure_listing_photo_columns()
    ensure_notification_settings_table()
    ensure_security_audit_log_table()
    ensure_payment_methods_table()
    ensure_ratings_multi_seller_constraint()
    ensure_message_type_column()
    migrate_default_fee_to_5pct()
    ensure_stripe_customer_id_column()
