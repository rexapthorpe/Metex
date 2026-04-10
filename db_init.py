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


def ensure_feedback_type_column():
    """
    Ensure messages table has a feedback_type column to categorise feedback
    submissions (issue, improvement, praise, other).
    Only populated when message_type='feedback'. NULL for legacy rows.
    """
    try:
        conn = get_db_connection()
        existing = get_table_columns(conn, 'messages')
        if 'feedback_type' not in existing:
            conn.execute("ALTER TABLE messages ADD COLUMN feedback_type TEXT")
            conn.commit()
            print("✅ messages.feedback_type column added")
        conn.close()
    except Exception as e:
        print(f'Error ensuring feedback_type column: {e}')


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



def ensure_orders_placed_from_ip_column():
    """
    Ensure orders table has placed_from_ip column (Phase 1 — transaction evidence).
    Stores the buyer's IP address at the time of checkout submission.
    NULL for bid-accepted orders (no buyer HTTP request at acceptance time).
    Idempotent.
    """
    try:
        conn = get_db_connection()
        existing = get_table_columns(conn, 'orders')
        if 'placed_from_ip' not in existing:
            conn.execute('ALTER TABLE orders ADD COLUMN placed_from_ip TEXT')
            conn.commit()
            print('✅ orders.placed_from_ip column added (Phase 1)')
        conn.close()
    except Exception as e:
        print(f'Error ensuring orders.placed_from_ip column: {e}')


def ensure_transaction_snapshots_table():
    """
    Ensure the transaction_snapshots table exists (Phase 1 — immutable evidence layer).

    Stores a point-in-time snapshot of every purchased order item at the moment of
    order creation.  Future listing edits or deletions cannot erase this record.

    Safe to call multiple times (idempotent via CREATE TABLE IF NOT EXISTS).
    Historical orders (pre-Phase-1) will have no snapshot rows; that is expected.
    """
    try:
        conn = get_db_connection()
        conn.execute(_ddl('''
            CREATE TABLE IF NOT EXISTS transaction_snapshots (
                id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id               INTEGER NOT NULL,
                order_item_id          INTEGER,
                snapshot_at            TEXT NOT NULL,

                listing_id             INTEGER,
                listing_title          TEXT,
                listing_description    TEXT,

                metal                  TEXT,
                product_line           TEXT,
                product_type           TEXT,
                weight                 TEXT,
                year                   TEXT,
                mint                   TEXT,
                purity                 TEXT,
                finish                 TEXT,
                condition_category     TEXT,
                series_variant         TEXT,

                packaging_type         TEXT,
                packaging_notes        TEXT,
                condition_notes        TEXT,

                photo_filenames        TEXT,

                quantity               INTEGER,
                price_each             REAL,
                pricing_mode           TEXT,
                spot_price_at_purchase REAL,

                seller_id              INTEGER,
                seller_username        TEXT,
                seller_email           TEXT,

                buyer_id               INTEGER,
                buyer_username         TEXT,
                buyer_email            TEXT,

                payment_intent_id      TEXT,

                FOREIGN KEY (order_id) REFERENCES orders(id)
            )
        '''))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f'Error ensuring transaction_snapshots table: {e}')


def ensure_refunds_table():
    """
    Ensure the refunds table exists (Phase 3 — admin-issued refund records).
    Every admin-triggered dispute refund writes a row here for auditability and reporting.
    Safe to call multiple times (idempotent via CREATE TABLE IF NOT EXISTS).
    """
    try:
        conn = get_db_connection()
        conn.execute(_ddl('''
            CREATE TABLE IF NOT EXISTS refunds (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                dispute_id          INTEGER,
                order_id            INTEGER NOT NULL,
                order_item_id       INTEGER,
                buyer_id            INTEGER NOT NULL,
                seller_id           INTEGER,
                amount              REAL NOT NULL,
                provider_refund_id  TEXT,
                issued_by_admin_id  INTEGER NOT NULL,
                issued_at           TEXT NOT NULL,
                note                TEXT,
                FOREIGN KEY (dispute_id) REFERENCES disputes(id),
                FOREIGN KEY (order_id)   REFERENCES orders(id)
            )
        '''))
        conn.commit()
        conn.close()
        print('✅ refunds table ensured (Phase 3)')
    except Exception as e:
        print(f'Error ensuring refunds table: {e}')


def ensure_disputes_table():
    """
    Ensure the disputes table exists (Phase 2 — dispute data model).
    Stores one row per dispute opened by a buyer against an order.
    order_item_id is nullable: Phase 2 disputes are opened at order level from the buyer UI.
    Safe to call multiple times (idempotent via CREATE TABLE IF NOT EXISTS).
    """
    try:
        conn = get_db_connection()
        conn.execute(_ddl('''
            CREATE TABLE IF NOT EXISTS disputes (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id            INTEGER NOT NULL,
                order_item_id       INTEGER,
                opened_by_user_id   INTEGER NOT NULL,
                buyer_id            INTEGER NOT NULL,
                seller_id           INTEGER,
                dispute_type        TEXT NOT NULL,
                status              TEXT NOT NULL DEFAULT 'open',
                description         TEXT NOT NULL,
                opened_at           TEXT NOT NULL,
                resolved_at         TEXT,
                resolved_by_admin_id INTEGER,
                resolution_note     TEXT,
                refund_amount       REAL,
                stripe_refund_id    TEXT,
                FOREIGN KEY (order_id) REFERENCES orders(id)
            )
        '''))
        conn.commit()
        conn.close()
        print('✅ disputes table ensured (Phase 2)')
    except Exception as e:
        print(f'Error ensuring disputes table: {e}')


def ensure_dispute_evidence_table():
    """
    Ensure the dispute_evidence table exists (Phase 2 — evidence collection).
    Safe to call multiple times (idempotent via CREATE TABLE IF NOT EXISTS).
    """
    try:
        conn = get_db_connection()
        conn.execute(_ddl('''
            CREATE TABLE IF NOT EXISTS dispute_evidence (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                dispute_id          INTEGER NOT NULL,
                submitted_by_user_id INTEGER NOT NULL,
                actor_type          TEXT NOT NULL,
                evidence_type       TEXT NOT NULL,
                file_path           TEXT,
                note                TEXT,
                submitted_at        TEXT NOT NULL,
                FOREIGN KEY (dispute_id) REFERENCES disputes(id)
            )
        '''))
        conn.commit()
        conn.close()
        print('✅ dispute_evidence table ensured (Phase 2)')
    except Exception as e:
        print(f'Error ensuring dispute_evidence table: {e}')


def ensure_dispute_timeline_table():
    """
    Ensure the dispute_timeline table exists (Phase 2 — audit trail).
    Records every state change, evidence submission, and message in a dispute.
    Safe to call multiple times (idempotent via CREATE TABLE IF NOT EXISTS).
    """
    try:
        conn = get_db_connection()
        conn.execute(_ddl('''
            CREATE TABLE IF NOT EXISTS dispute_timeline (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                dispute_id  INTEGER NOT NULL,
                actor_type  TEXT NOT NULL,
                actor_id    INTEGER NOT NULL,
                event_type  TEXT NOT NULL,
                note        TEXT,
                created_at  TEXT NOT NULL,
                FOREIGN KEY (dispute_id) REFERENCES disputes(id)
            )
        '''))
        conn.commit()
        conn.close()
        print('✅ dispute_timeline table ensured (Phase 2)')
    except Exception as e:
        print(f'Error ensuring dispute_timeline table: {e}')


def ensure_user_risk_profile_table():
    """
    Ensure the user_risk_profile table exists (Phase 4 — risk monitoring).
    One row per user; upserted on relevant events.
    Safe to call multiple times (idempotent via CREATE TABLE IF NOT EXISTS).
    """
    try:
        conn = get_db_connection()
        conn.execute(_ddl('''
            CREATE TABLE IF NOT EXISTS user_risk_profile (
                user_id                         INTEGER PRIMARY KEY,
                risk_score                      INTEGER NOT NULL DEFAULT 0,
                manual_risk_flag                TEXT NOT NULL DEFAULT 'none',
                manual_flag_reason              TEXT,
                manual_flagged_at               TEXT,
                manual_flagged_by_admin_id      INTEGER,
                total_disputes_as_buyer         INTEGER NOT NULL DEFAULT 0,
                disputes_upheld_buyer           INTEGER NOT NULL DEFAULT 0,
                disputes_denied_buyer           INTEGER NOT NULL DEFAULT 0,
                total_disputes_as_seller        INTEGER NOT NULL DEFAULT 0,
                disputes_upheld_against_seller  INTEGER NOT NULL DEFAULT 0,
                total_orders_bought             INTEGER NOT NULL DEFAULT 0,
                total_orders_sold               INTEGER NOT NULL DEFAULT 0,
                refunds_issued_count            INTEGER NOT NULL DEFAULT 0,
                refunds_issued_amount           REAL NOT NULL DEFAULT 0,
                last_login_ip                   TEXT,
                last_login_at                   TEXT,
                account_created_ip              TEXT,
                notes                           TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        '''))
        conn.commit()
        conn.close()
        print('✅ user_risk_profile table ensured (Phase 4)')
    except Exception as e:
        print(f'Error ensuring user_risk_profile table: {e}')


def ensure_user_risk_events_table():
    """
    Ensure the user_risk_events table exists (Phase 4 — risk audit trail).
    Every score recalculation and flag change writes a row here.
    Safe to call multiple times (idempotent via CREATE TABLE IF NOT EXISTS).
    """
    try:
        conn = get_db_connection()
        conn.execute(_ddl('''
            CREATE TABLE IF NOT EXISTS user_risk_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                event_type      TEXT NOT NULL,
                triggered_by    TEXT NOT NULL,
                old_score       INTEGER,
                new_score       INTEGER,
                old_flag        TEXT,
                new_flag        TEXT,
                note            TEXT,
                created_at      TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        '''))
        conn.commit()
        conn.close()
        print('✅ user_risk_events table ensured (Phase 4)')
    except Exception as e:
        print(f'Error ensuring user_risk_events table: {e}')


def ensure_tax_columns():
    """
    Ensure orders table has tax_amount and tax_rate columns (migration 031).
    tax_amount: dollar amount of tax applied to the subtotal.
    tax_rate:   rate at time of checkout (e.g. 0.0825 for 8.25%), locked for history.
    Both default to 0.0 so pre-migration orders are unaffected. Idempotent.
    """
    try:
        conn = get_db_connection()
        existing = get_table_columns(conn, 'orders')
        if 'tax_amount' not in existing:
            conn.execute('ALTER TABLE orders ADD COLUMN tax_amount REAL NOT NULL DEFAULT 0.0')
            conn.commit()
            print('✅ orders.tax_amount column added (migration 031)')
        if 'tax_rate' not in existing:
            conn.execute('ALTER TABLE orders ADD COLUMN tax_rate REAL NOT NULL DEFAULT 0.0')
            conn.commit()
            print('✅ orders.tax_rate column added (migration 031)')
        conn.close()
    except Exception as e:
        print(f'Error ensuring tax columns: {e}')


def ensure_buyer_card_fee_column():
    """
    Ensure orders table has buyer_card_fee column (migration 030).
    Stores the card processing fee charged to the buyer (2.99% + $0.30).
    Zero for ACH payments. Idempotent.
    """
    try:
        conn = get_db_connection()
        existing = get_table_columns(conn, 'orders')
        if 'buyer_card_fee' not in existing:
            conn.execute('ALTER TABLE orders ADD COLUMN buyer_card_fee NUMERIC(10,2) NOT NULL DEFAULT 0')
            conn.commit()
            print('✅ orders.buyer_card_fee column added (migration 030)')
        conn.close()
    except Exception as e:
        print(f'Error ensuring buyer_card_fee column: {e}')


def migrate_refunds_dispute_id_nullable():
    """
    Make refunds.dispute_id nullable (migration 031).
    Direct ledger refunds (issued without a dispute) need dispute_id = NULL.
    Was originally created as NOT NULL (dispute-only flow).
    """
    try:
        conn = get_db_connection()
        if IS_POSTGRES:
            try:
                conn.execute('ALTER TABLE refunds ALTER COLUMN dispute_id DROP NOT NULL')
                conn.commit()
                print('✅ refunds.dispute_id made nullable (migration 031)')
            except Exception:
                conn.rollback()
                # Already nullable — no-op
        else:
            # SQLite: inspect via PRAGMA table_info; column 3 is 'notnull' flag
            rows = conn.execute("PRAGMA table_info(refunds)").fetchall()
            dispute_notnull = None
            for row in rows:
                if row[1] == 'dispute_id':
                    dispute_notnull = row[3]
                    break
            if dispute_notnull == 1:
                # Recreate table with nullable dispute_id
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS refunds_migrated (
                        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                        dispute_id          INTEGER,
                        order_id            INTEGER NOT NULL,
                        order_item_id       INTEGER,
                        buyer_id            INTEGER NOT NULL,
                        seller_id           INTEGER,
                        amount              REAL NOT NULL,
                        provider_refund_id  TEXT,
                        issued_by_admin_id  INTEGER NOT NULL,
                        issued_at           TEXT NOT NULL,
                        note                TEXT,
                        FOREIGN KEY (order_id) REFERENCES orders(id)
                    )
                ''')
                conn.execute('INSERT INTO refunds_migrated SELECT * FROM refunds')
                conn.execute('DROP TABLE refunds')
                conn.execute('ALTER TABLE refunds_migrated RENAME TO refunds')
                conn.commit()
                print('✅ refunds.dispute_id made nullable (migration 031)')
            else:
                print('ℹ️  refunds.dispute_id already nullable (skip)')
        conn.close()
    except Exception as e:
        print(f'Error in migrate_refunds_dispute_id_nullable: {e}')


def backfill_missing_refund_records():
    """
    One-time backfill (migration 032): insert a refunds row for any order that was
    refunded via refund_buyer_stripe() before the INSERT was added to that function.
    Idempotent — skips orders that already have a refunds row.
    """
    try:
        conn = get_db_connection()
        # Find any admin user to attribute backfilled rows to
        admin_row = conn.execute(
            "SELECT id FROM users WHERE is_admin = 1 ORDER BY id LIMIT 1"
        ).fetchone()
        fallback_admin_id = admin_row['id'] if admin_row else 0

        orders = conn.execute(
            """SELECT o.id AS order_id, o.buyer_id, o.refund_amount,
                      o.stripe_refund_id, o.refunded_at, o.refund_reason
               FROM orders o
               WHERE o.refund_status IN ('refunded', 'partially_refunded')
                 AND NOT EXISTS (
                       SELECT 1 FROM refunds r WHERE r.order_id = o.id
                 )"""
        ).fetchall()

        inserted = 0
        for row in orders:
            # Resolve seller_id: use the single seller if only one, else NULL
            payout_rows = conn.execute(
                "SELECT DISTINCT seller_id FROM order_payouts WHERE order_id = ?",
                (row['order_id'],)
            ).fetchall()
            seller_id = payout_rows[0]['seller_id'] if len(payout_rows) == 1 else None

            conn.execute(
                """INSERT INTO refunds
                       (dispute_id, order_id, order_item_id, buyer_id, seller_id,
                        amount, provider_refund_id, issued_by_admin_id, issued_at, note)
                   VALUES (NULL, ?, NULL, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row['order_id'],
                    row['buyer_id'],
                    seller_id,
                    row['refund_amount'] or 0,
                    row['stripe_refund_id'],
                    fallback_admin_id,
                    row['refunded_at'] or '',
                    row['refund_reason'] or '',
                ),
            )
            inserted += 1

        conn.commit()
        conn.close()
        if inserted:
            print(f'✅ Backfilled {inserted} missing refund record(s) into refunds table (migration 032)')
    except Exception as e:
        print(f'Error in backfill_missing_refund_records: {e}')


def ensure_bucket_image_tables():
    """
    Ensure the three bucket image catalog tables exist.
    Safe to run multiple times (CREATE TABLE IF NOT EXISTS).
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(_ddl("""
            CREATE TABLE IF NOT EXISTS standard_buckets (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                slug               TEXT NOT NULL UNIQUE,
                title              TEXT NOT NULL,
                metal              TEXT NOT NULL,
                form               TEXT NOT NULL DEFAULT 'coin',
                weight             TEXT,
                weight_oz          REAL,
                denomination       TEXT,
                mint               TEXT,
                product_family     TEXT,
                product_series     TEXT,
                year_policy        TEXT NOT NULL DEFAULT 'fixed',
                year               TEXT,
                purity             TEXT,
                finish             TEXT,
                variant            TEXT,
                category_bucket_id INTEGER,
                active             INTEGER NOT NULL DEFAULT 1,
                created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        cursor.execute(_ddl("""
            CREATE TABLE IF NOT EXISTS bucket_image_assets (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                standard_bucket_id   INTEGER NOT NULL,
                source_name          TEXT NOT NULL,
                source_type          TEXT NOT NULL DEFAULT 'unknown',
                source_priority      INTEGER NOT NULL DEFAULT 99,
                source_page_url      TEXT,
                original_image_url   TEXT,
                storage_key          TEXT UNIQUE,
                local_path           TEXT,
                web_path             TEXT,
                thumb_path           TEXT,
                checksum             TEXT,
                width                INTEGER,
                height               INTEGER,
                mime_type            TEXT,
                file_size            INTEGER,
                attribution_text     TEXT,
                license_type         TEXT,
                rights_note          TEXT,
                usage_allowed        INTEGER NOT NULL DEFAULT 1,
                confidence_score     REAL NOT NULL DEFAULT 0.0,
                status               TEXT NOT NULL DEFAULT 'pending',
                is_primary_candidate INTEGER NOT NULL DEFAULT 0,
                ingestion_run_id     INTEGER,
                matched_title        TEXT,
                matched_weight       TEXT,
                matched_mint         TEXT,
                matched_year         TEXT,
                matched_series       TEXT,
                match_warnings       TEXT,
                raw_source_title     TEXT,
                raw_source_metadata  TEXT,
                created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_at          TIMESTAMP,
                reviewed_by          INTEGER,
                FOREIGN KEY (standard_bucket_id) REFERENCES standard_buckets(id)
            )
        """))

        cursor.execute(_ddl("""
            CREATE TABLE IF NOT EXISTS bucket_image_ingestion_runs (
                id                       INTEGER PRIMARY KEY AUTOINCREMENT,
                standard_bucket_id       INTEGER,
                source_name              TEXT,
                source_url               TEXT,
                status                   TEXT NOT NULL DEFAULT 'running',
                images_found             INTEGER NOT NULL DEFAULT 0,
                images_ingested          INTEGER NOT NULL DEFAULT 0,
                images_skipped_duplicate INTEGER NOT NULL DEFAULT 0,
                error_message            TEXT,
                triggered_by             INTEGER,
                started_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at             TIMESTAMP,
                FOREIGN KEY (standard_bucket_id) REFERENCES standard_buckets(id),
                FOREIGN KEY (triggered_by) REFERENCES users(id)
            )
        """))

        # Indexes (CREATE INDEX IF NOT EXISTS works for both SQLite and Postgres)
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS idx_sb_slug ON standard_buckets(slug)",
            "CREATE INDEX IF NOT EXISTS idx_sb_cat_bucket ON standard_buckets(category_bucket_id)",
            "CREATE INDEX IF NOT EXISTS idx_sb_active ON standard_buckets(active)",
            "CREATE INDEX IF NOT EXISTS idx_bia_bucket ON bucket_image_assets(standard_bucket_id)",
            "CREATE INDEX IF NOT EXISTS idx_bia_status ON bucket_image_assets(status)",
            "CREATE INDEX IF NOT EXISTS idx_bia_checksum ON bucket_image_assets(checksum)",
            "CREATE INDEX IF NOT EXISTS idx_biir_bucket ON bucket_image_ingestion_runs(standard_bucket_id)",
        ]:
            try:
                cursor.execute(idx_sql)
            except Exception:
                pass  # Index may already exist under a different backend

        conn.commit()
        conn.close()
    except Exception as e:
        print(f'Error in ensure_bucket_image_tables: {e}')


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
    ensure_feedback_type_column()
    migrate_default_fee_to_5pct()
    ensure_stripe_customer_id_column()
    ensure_orders_placed_from_ip_column()
    ensure_transaction_snapshots_table()
    ensure_disputes_table()
    ensure_dispute_evidence_table()
    ensure_dispute_timeline_table()
    ensure_refunds_table()
    migrate_refunds_dispute_id_nullable()
    backfill_missing_refund_records()
    ensure_user_risk_profile_table()
    ensure_user_risk_events_table()
    ensure_buyer_card_fee_column()
    ensure_tax_columns()
    ensure_bucket_image_tables()
