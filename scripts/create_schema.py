#!/usr/bin/env python3
"""
Metex Database Schema Creation and Migration Script

This script creates or updates the complete database schema for the Metex peer-to-peer
bullion marketplace. It is safe to run multiple times and will:
- Create missing tables
- Add missing columns to existing tables
- Create all required indexes
- Never delete or overwrite existing data

Usage:
    python create_schema.py

The script will print a detailed log of all changes made.
"""

import sqlite3
import sys
from database import get_db_connection


class SchemaManager:
    """Manages database schema creation and updates"""

    def __init__(self):
        self.conn = None
        self.cursor = None
        self.changes_made = []
        self.errors = []

    def log_change(self, message):
        """Log a change that was made"""
        print(f"  ✓ {message}")
        self.changes_made.append(message)

    def log_skip(self, message):
        """Log something that was skipped (already exists)"""
        print(f"  - {message}")

    def log_error(self, message):
        """Log an error"""
        print(f"  ✗ ERROR: {message}")
        self.errors.append(message)

    def column_exists(self, table_name, column_name):
        """Check if a column exists in a table"""
        try:
            self.cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in self.cursor.fetchall()]
            return column_name in columns
        except sqlite3.OperationalError:
            return False

    def table_exists(self, table_name):
        """Check if a table exists"""
        self.cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        return self.cursor.fetchone() is not None

    def index_exists(self, index_name):
        """Check if an index exists"""
        self.cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            (index_name,)
        )
        return self.cursor.fetchone() is not None

    def add_column(self, table, column, column_def):
        """Add a column to a table if it doesn't exist"""
        if not self.column_exists(table, column):
            try:
                self.cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_def}")
                self.log_change(f"Added column '{column}' to {table}")
                return True
            except sqlite3.OperationalError as e:
                self.log_error(f"Failed to add column '{column}' to {table}: {e}")
                return False
        else:
            self.log_skip(f"Column '{column}' already exists in {table}")
            return False

    def create_index(self, index_name, table, columns):
        """Create an index if it doesn't exist"""
        if not self.index_exists(index_name):
            try:
                self.cursor.execute(f"CREATE INDEX {index_name} ON {table}({columns})")
                self.log_change(f"Created index '{index_name}'")
                return True
            except sqlite3.OperationalError as e:
                self.log_error(f"Failed to create index '{index_name}': {e}")
                return False
        else:
            self.log_skip(f"Index '{index_name}' already exists")
            return False

    def create_users_table(self):
        """Create the users table"""
        print("\n[1/21] Creating USERS table...")

        sql = """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            username TEXT,
            password_hash TEXT,
            is_admin INTEGER DEFAULT 0,
            first_name TEXT,
            last_name TEXT,
            phone TEXT,
            bio TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """

        if not self.table_exists('users'):
            self.cursor.execute(sql)
            self.log_change("Created users table")
        else:
            self.log_skip("Table 'users' already exists")

        # Ensure all columns exist
        self.add_column('users', 'username', 'TEXT')
        self.add_column('users', 'password_hash', 'TEXT')
        self.add_column('users', 'is_admin', 'INTEGER DEFAULT 0')
        self.add_column('users', 'first_name', 'TEXT')
        self.add_column('users', 'last_name', 'TEXT')
        self.add_column('users', 'phone', 'TEXT')
        self.add_column('users', 'bio', 'TEXT')
        self.add_column('users', 'created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')

        # Create indexes
        self.create_index('idx_users_is_admin', 'users', 'is_admin')

    def create_categories_table(self):
        """Create the categories (buckets) table"""
        print("\n[2/21] Creating CATEGORIES table...")

        sql = """
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            year TEXT,
            weight TEXT,
            purity TEXT,
            mint TEXT,
            country_of_origin TEXT,
            coin_series TEXT,
            denomination TEXT,
            grade TEXT,
            finish TEXT,
            special_designation TEXT,
            metal TEXT,
            product_type TEXT,
            bucket_id INTEGER,
            product_line TEXT,
            graded INTEGER DEFAULT 0,
            grading_service TEXT,
            is_isolated INTEGER NOT NULL DEFAULT 0,
            condition_category TEXT CHECK(condition_category IN ('BU', 'AU', 'Circulated', 'Cull', 'Random_Condition', 'None')),
            series_variant TEXT CHECK(series_variant IN ('None', 'First_Strike', 'Early_Releases', 'First_Day_of_Issue', 'Privy', 'MintDirect')),
            platform_fee_type TEXT CHECK(platform_fee_type IN ('percent', 'flat') OR platform_fee_type IS NULL),
            platform_fee_value REAL,
            fee_updated_at TIMESTAMP
        )
        """

        if not self.table_exists('categories'):
            self.cursor.execute(sql)
            self.log_change("Created categories table")
        else:
            self.log_skip("Table 'categories' already exists")

        # Ensure all columns exist
        self.add_column('categories', 'graded', 'INTEGER DEFAULT 0')
        self.add_column('categories', 'grading_service', 'TEXT')
        self.add_column('categories', 'is_isolated', 'INTEGER NOT NULL DEFAULT 0')
        self.add_column('categories', 'condition_category', "TEXT CHECK(condition_category IN ('BU', 'AU', 'Circulated', 'Cull', 'Random_Condition', 'None'))")
        self.add_column('categories', 'series_variant', "TEXT CHECK(series_variant IN ('None', 'First_Strike', 'Early_Releases', 'First_Day_of_Issue', 'Privy', 'MintDirect'))")
        # Bucket-level platform fee configuration
        self.add_column('categories', 'platform_fee_type', "TEXT CHECK(platform_fee_type IN ('percent', 'flat') OR platform_fee_type IS NULL)")
        self.add_column('categories', 'platform_fee_value', 'REAL')
        self.add_column('categories', 'fee_updated_at', 'TIMESTAMP')

        # Create indexes
        self.create_index('idx_categories_lookup', 'categories',
                         'metal, product_line, product_type, weight, purity, mint, year, finish, grade')
        self.create_index('idx_categories_isolated', 'categories', 'is_isolated')
        self.create_index('idx_categories_bucket_id', 'categories', 'bucket_id')

    def create_listings_table(self):
        """Create the listings table"""
        print("\n[3/21] Creating LISTINGS table...")

        sql = """
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            price_per_coin REAL NOT NULL,
            active INTEGER DEFAULT 1,
            name TEXT,
            description TEXT,
            pricing_mode TEXT DEFAULT 'static' CHECK(pricing_mode IN ('static', 'premium_to_spot')),
            spot_premium REAL DEFAULT 0,
            floor_price REAL DEFAULT 0,
            pricing_metal TEXT,
            is_isolated INTEGER NOT NULL DEFAULT 0,
            isolated_type TEXT CHECK(isolated_type IN ('one_of_a_kind', 'set') OR isolated_type IS NULL),
            issue_number INTEGER,
            issue_total INTEGER,
            graded INTEGER DEFAULT 0,
            grading_service TEXT,
            packaging_type TEXT CHECK(packaging_type IN ('Loose', 'Capsule', 'OGP', 'Tube_Full', 'Tube_Partial', 'MonsterBox_Full', 'MonsterBox_Partial', 'Assay_Card')),
            packaging_notes TEXT,
            cert_number TEXT,
            condition_notes TEXT,
            actual_year TEXT,
            image_url TEXT,
            FOREIGN KEY (seller_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
        )
        """

        if not self.table_exists('listings'):
            self.cursor.execute(sql)
            self.log_change("Created listings table")
        else:
            self.log_skip("Table 'listings' already exists")

        # Ensure all columns exist (from various migrations)
        self.add_column('listings', 'name', 'TEXT')
        self.add_column('listings', 'description', 'TEXT')
        self.add_column('listings', 'pricing_mode', "TEXT DEFAULT 'static' CHECK(pricing_mode IN ('static', 'premium_to_spot'))")
        self.add_column('listings', 'spot_premium', 'REAL DEFAULT 0')
        self.add_column('listings', 'floor_price', 'REAL DEFAULT 0')
        self.add_column('listings', 'pricing_metal', 'TEXT')
        self.add_column('listings', 'is_isolated', 'INTEGER NOT NULL DEFAULT 0')
        self.add_column('listings', 'isolated_type', "TEXT CHECK(isolated_type IN ('one_of_a_kind', 'set') OR isolated_type IS NULL)")
        self.add_column('listings', 'issue_number', 'INTEGER')
        self.add_column('listings', 'issue_total', 'INTEGER')
        self.add_column('listings', 'graded', 'INTEGER DEFAULT 0')
        self.add_column('listings', 'grading_service', 'TEXT')
        self.add_column('listings', 'packaging_type', "TEXT CHECK(packaging_type IN ('Loose', 'Capsule', 'OGP', 'Tube_Full', 'Tube_Partial', 'MonsterBox_Full', 'MonsterBox_Partial', 'Assay_Card'))")
        self.add_column('listings', 'packaging_notes', 'TEXT')
        self.add_column('listings', 'cert_number', 'TEXT')
        self.add_column('listings', 'condition_notes', 'TEXT')
        self.add_column('listings', 'actual_year', 'TEXT')
        # Edition numbering for one-of-a-kind listings
        self.add_column('listings', 'edition_number', 'INTEGER')
        self.add_column('listings', 'edition_total', 'INTEGER')

        # Create indexes
        self.create_index('idx_listings_isolated', 'listings', 'is_isolated, isolated_type')
        self.create_index('idx_listings_numismatic', 'listings', 'issue_number, issue_total')

    def create_bids_table(self):
        """Create the bids table"""
        print("\n[4/21] Creating BIDS table...")

        sql = """
        CREATE TABLE IF NOT EXISTS bids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            buyer_id INTEGER NOT NULL,
            quantity_requested INTEGER NOT NULL,
            price_per_coin REAL NOT NULL,
            remaining_quantity INTEGER NOT NULL,
            active INTEGER DEFAULT 1,
            requires_grading INTEGER DEFAULT 0,
            preferred_grader TEXT,
            delivery_address TEXT,
            status TEXT DEFAULT 'Open',
            pricing_mode TEXT DEFAULT 'static' CHECK(pricing_mode IN ('static', 'premium_to_spot')),
            spot_premium REAL,
            ceiling_price REAL,
            pricing_metal TEXT,
            recipient_first_name TEXT,
            recipient_last_name TEXT,
            random_year INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories(id),
            FOREIGN KEY (buyer_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """

        if not self.table_exists('bids'):
            self.cursor.execute(sql)
            self.log_change("Created bids table")
        else:
            self.log_skip("Table 'bids' already exists")

        # Ensure all columns exist
        self.add_column('bids', 'pricing_mode', "TEXT DEFAULT 'static' CHECK(pricing_mode IN ('static', 'premium_to_spot'))")
        self.add_column('bids', 'spot_premium', 'REAL')
        self.add_column('bids', 'ceiling_price', 'REAL')
        self.add_column('bids', 'pricing_metal', 'TEXT')
        self.add_column('bids', 'recipient_first_name', 'TEXT')
        self.add_column('bids', 'recipient_last_name', 'TEXT')
        self.add_column('bids', 'random_year', 'INTEGER DEFAULT 0')

    def create_orders_table(self):
        """Create the orders table"""
        print("\n[5/21] Creating ORDERS table...")

        sql = """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            buyer_id INTEGER NOT NULL,
            total_price REAL,
            shipping_address TEXT,
            delivery_address TEXT,
            status TEXT DEFAULT 'Pending',
            recipient_first_name TEXT,
            recipient_last_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (buyer_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """

        if not self.table_exists('orders'):
            self.cursor.execute(sql)
            self.log_change("Created orders table")
        else:
            self.log_skip("Table 'orders' already exists")

        # Ensure all columns exist
        self.add_column('orders', 'delivery_address', 'TEXT')
        self.add_column('orders', 'recipient_first_name', 'TEXT')
        self.add_column('orders', 'recipient_last_name', 'TEXT')

    def create_order_items_table(self):
        """Create the order_items table"""
        print("\n[6/21] Creating ORDER_ITEMS table...")

        sql = """
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            listing_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            price_each REAL NOT NULL,
            price_at_purchase REAL,
            pricing_mode_at_purchase TEXT,
            spot_price_at_purchase REAL,
            seller_price_each REAL,
            third_party_grading_requested INTEGER DEFAULT 0,
            packaging_type TEXT,
            cert_number TEXT,
            condition_notes TEXT,
            grading_fee_charged REAL DEFAULT 0,
            grading_service TEXT DEFAULT 'PCGS',
            grading_status TEXT DEFAULT 'not_requested',
            seller_tracking_to_grader TEXT,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
            FOREIGN KEY (listing_id) REFERENCES listings(id) ON DELETE CASCADE
        )
        """

        if not self.table_exists('order_items'):
            self.cursor.execute(sql)
            self.log_change("Created order_items table")
        else:
            self.log_skip("Table 'order_items' already exists")

        # Ensure all columns exist (from various migrations)
        self.add_column('order_items', 'price_at_purchase', 'REAL')
        self.add_column('order_items', 'pricing_mode_at_purchase', 'TEXT')
        self.add_column('order_items', 'spot_price_at_purchase', 'REAL')
        self.add_column('order_items', 'seller_price_each', 'REAL')
        self.add_column('order_items', 'third_party_grading_requested', 'INTEGER DEFAULT 0')
        self.add_column('order_items', 'packaging_type', 'TEXT')
        self.add_column('order_items', 'cert_number', 'TEXT')
        self.add_column('order_items', 'condition_notes', 'TEXT')
        self.add_column('order_items', 'grading_fee_charged', 'REAL DEFAULT 0')
        self.add_column('order_items', 'grading_service', "TEXT DEFAULT 'PCGS'")
        self.add_column('order_items', 'grading_status', "TEXT DEFAULT 'not_requested'")
        self.add_column('order_items', 'seller_tracking_to_grader', 'TEXT')

    def create_cart_table(self):
        """Create the cart table"""
        print("\n[7/21] Creating CART table...")

        sql = """
        CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            listing_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            third_party_grading_requested INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (listing_id) REFERENCES listings(id) ON DELETE CASCADE
        )
        """

        if not self.table_exists('cart'):
            self.cursor.execute(sql)
            self.log_change("Created cart table")
        else:
            self.log_skip("Table 'cart' already exists")

        # Ensure all columns exist
        self.add_column('cart', 'third_party_grading_requested', 'INTEGER DEFAULT 0')
        self.add_column('cart', 'grading_preference', "TEXT DEFAULT 'NONE'")

    def create_messages_table(self):
        """Create the messages table"""
        print("\n[8/21] Creating MESSAGES table...")

        sql = """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (sender_id) REFERENCES users(id),
            FOREIGN KEY (receiver_id) REFERENCES users(id)
        )
        """

        if not self.table_exists('messages'):
            self.cursor.execute(sql)
            self.log_change("Created messages table")
        else:
            self.log_skip("Table 'messages' already exists")

    def create_message_reads_table(self):
        """Create the message_reads table for tracking read status"""
        print("\n[9/21] Creating MESSAGE_READS table...")

        sql = """
        CREATE TABLE IF NOT EXISTS message_reads (
            user_id INTEGER NOT NULL,
            participant_id INTEGER NOT NULL,
            order_id INTEGER NOT NULL,
            last_read_ts DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, participant_id, order_id)
        )
        """

        if not self.table_exists('message_reads'):
            self.cursor.execute(sql)
            self.log_change("Created message_reads table")
        else:
            self.log_skip("Table 'message_reads' already exists")

    def create_ratings_table(self):
        """Create the ratings table"""
        print("\n[10/21] Creating RATINGS table...")

        sql = """
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            rater_id INTEGER NOT NULL,
            ratee_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (rater_id) REFERENCES users(id),
            FOREIGN KEY (ratee_id) REFERENCES users(id),
            UNIQUE(order_id, rater_id)
        )
        """

        if not self.table_exists('ratings'):
            self.cursor.execute(sql)
            self.log_change("Created ratings table")
        else:
            self.log_skip("Table 'ratings' already exists")

    def create_addresses_table(self):
        """Create the addresses table"""
        print("\n[11/21] Creating ADDRESSES table...")

        sql = """
        CREATE TABLE IF NOT EXISTS addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            street TEXT NOT NULL,
            city TEXT NOT NULL,
            state TEXT NOT NULL,
            zip_code TEXT NOT NULL,
            country TEXT DEFAULT 'USA',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """

        if not self.table_exists('addresses'):
            self.cursor.execute(sql)
            self.log_change("Created addresses table")
        else:
            self.log_skip("Table 'addresses' already exists")

        # Create index
        self.create_index('idx_addresses_user_id', 'addresses', 'user_id')

    def create_notification_preferences_table(self):
        """Create the notification_preferences table"""
        print("\n[12/21] Creating NOTIFICATION_PREFERENCES table...")

        sql = """
        CREATE TABLE IF NOT EXISTS notification_preferences (
            user_id INTEGER PRIMARY KEY,
            email_orders INTEGER DEFAULT 1,
            email_bids INTEGER DEFAULT 0,
            email_messages INTEGER DEFAULT 0,
            email_promotions INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """

        if not self.table_exists('notification_preferences'):
            self.cursor.execute(sql)
            self.log_change("Created notification_preferences table")
        else:
            self.log_skip("Table 'notification_preferences' already exists")

        # Create index
        self.create_index('idx_notification_prefs_user_id', 'notification_preferences', 'user_id')

    def create_user_preferences_table(self):
        """Create the user_preferences table"""
        print("\n[13/21] Creating USER_PREFERENCES table...")

        sql = """
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id INTEGER PRIMARY KEY,
            email_listing_sold INTEGER DEFAULT 1,
            email_bid_filled INTEGER DEFAULT 1,
            inapp_listing_sold INTEGER DEFAULT 1,
            inapp_bid_filled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """

        if not self.table_exists('user_preferences'):
            self.cursor.execute(sql)
            self.log_change("Created user_preferences table")
        else:
            self.log_skip("Table 'user_preferences' already exists")

        # Create index
        self.create_index('idx_user_preferences_user_id', 'user_preferences', 'user_id')

    def create_portfolio_tables(self):
        """Create the portfolio-related tables"""
        print("\n[14/21] Creating PORTFOLIO tables...")

        # Portfolio exclusions
        sql_exclusions = """
        CREATE TABLE IF NOT EXISTS portfolio_exclusions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            order_item_id INTEGER NOT NULL,
            excluded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (order_item_id) REFERENCES order_items(id) ON DELETE CASCADE,
            UNIQUE(user_id, order_item_id)
        )
        """

        if not self.table_exists('portfolio_exclusions'):
            self.cursor.execute(sql_exclusions)
            self.log_change("Created portfolio_exclusions table")
        else:
            self.log_skip("Table 'portfolio_exclusions' already exists")

        # Portfolio snapshots
        sql_snapshots = """
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            snapshot_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_value REAL NOT NULL,
            total_cost_basis REAL DEFAULT 0,
            snapshot_type TEXT DEFAULT 'auto',
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """

        if not self.table_exists('portfolio_snapshots'):
            self.cursor.execute(sql_snapshots)
            self.log_change("Created portfolio_snapshots table")
        else:
            self.log_skip("Table 'portfolio_snapshots' already exists")

        # Create indexes
        self.create_index('idx_portfolio_exclusions_user', 'portfolio_exclusions', 'user_id')
        self.create_index('idx_portfolio_exclusions_order_item', 'portfolio_exclusions', 'order_item_id')
        self.create_index('idx_portfolio_snapshots_user_date', 'portfolio_snapshots', 'user_id, snapshot_date DESC')

    def create_spot_prices_table(self):
        """Create the spot_prices table"""
        print("\n[15/21] Creating SPOT_PRICES table...")

        sql = """
        CREATE TABLE IF NOT EXISTS spot_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metal TEXT NOT NULL UNIQUE,
            price_usd_per_oz REAL NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source TEXT DEFAULT 'metalpriceapi'
        )
        """

        if not self.table_exists('spot_prices'):
            self.cursor.execute(sql)
            self.log_change("Created spot_prices table")

            # Seed initial spot prices
            self.cursor.execute("""
                INSERT OR IGNORE INTO spot_prices (metal, price_usd_per_oz, source) VALUES
                    ('gold', 2000.00, 'initial_seed'),
                    ('silver', 25.00, 'initial_seed'),
                    ('platinum', 950.00, 'initial_seed'),
                    ('palladium', 1000.00, 'initial_seed')
            """)
            self.log_change("Seeded initial spot prices (will be updated by API)")
        else:
            self.log_skip("Table 'spot_prices' already exists")

        # Create index
        self.create_index('idx_spot_prices_metal', 'spot_prices', 'metal')

    def create_price_locks_table(self):
        """Create the price_locks table"""
        print("\n[16/21] Creating PRICE_LOCKS table...")

        sql = """
        CREATE TABLE IF NOT EXISTS price_locks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            locked_price REAL NOT NULL,
            spot_price_at_lock REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            FOREIGN KEY (listing_id) REFERENCES listings(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """

        if not self.table_exists('price_locks'):
            self.cursor.execute(sql)
            self.log_change("Created price_locks table")
        else:
            self.log_skip("Table 'price_locks' already exists")

        # Create indexes
        self.create_index('idx_price_locks_listing_user', 'price_locks', 'listing_id, user_id')
        self.create_index('idx_price_locks_expires', 'price_locks', 'expires_at')

    def create_bucket_price_history_table(self):
        """Create the bucket_price_history table"""
        print("\n[17/21] Creating BUCKET_PRICE_HISTORY table...")

        sql = """
        CREATE TABLE IF NOT EXISTS bucket_price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bucket_id INTEGER NOT NULL,
            best_ask_price REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bucket_id) REFERENCES categories(bucket_id) ON DELETE CASCADE
        )
        """

        if not self.table_exists('bucket_price_history'):
            self.cursor.execute(sql)
            self.log_change("Created bucket_price_history table")
        else:
            self.log_skip("Table 'bucket_price_history' already exists")

        # Create indexes
        self.create_index('idx_bucket_price_history_bucket_time', 'bucket_price_history', 'bucket_id, timestamp DESC')
        self.create_index('idx_bucket_price_history_timestamp', 'bucket_price_history', 'timestamp')

    def create_listing_photos_table(self):
        """Create the listing_photos table"""
        print("\n[18/21] Creating LISTING_PHOTOS table...")

        sql = """
        CREATE TABLE IF NOT EXISTS listing_photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            uploader_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (listing_id) REFERENCES listings(id) ON DELETE CASCADE,
            FOREIGN KEY (uploader_id) REFERENCES users(id)
        )
        """

        if not self.table_exists('listing_photos'):
            self.cursor.execute(sql)
            self.log_change("Created listing_photos table")
        else:
            self.log_skip("Table 'listing_photos' already exists")

    def create_listing_set_items_table(self):
        """Create the listing_set_items table"""
        print("\n[19/21] Creating LISTING_SET_ITEMS table...")

        sql = """
        CREATE TABLE IF NOT EXISTS listing_set_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER NOT NULL,
            position_index INTEGER NOT NULL DEFAULT 0,
            metal TEXT,
            product_line TEXT,
            product_type TEXT,
            weight TEXT,
            purity TEXT,
            mint TEXT,
            year INTEGER,
            finish TEXT,
            grade TEXT,
            coin_series TEXT,
            special_designation TEXT,
            graded INTEGER DEFAULT 0,
            grading_service TEXT,
            photo_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (listing_id) REFERENCES listings(id) ON DELETE CASCADE
        )
        """

        if not self.table_exists('listing_set_items'):
            self.cursor.execute(sql)
            self.log_change("Created listing_set_items table")
        else:
            self.log_skip("Table 'listing_set_items' already exists")

        # Ensure photo_path column exists (migration 012)
        self.add_column('listing_set_items', 'photo_path', 'TEXT')

        # Ensure edition numbering columns exist (migration 015)
        self.add_column('listing_set_items', 'edition_number', 'INTEGER')
        self.add_column('listing_set_items', 'edition_total', 'INTEGER')

        # Ensure quantity column exists (migration 016)
        self.add_column('listing_set_items', 'quantity', 'INTEGER DEFAULT 1')

        # Ensure packaging columns exist (migration 017)
        self.add_column('listing_set_items', 'packaging_type', 'TEXT')
        self.add_column('listing_set_items', 'packaging_notes', 'TEXT')

        # Ensure item_title and condition_notes columns exist
        self.add_column('listing_set_items', 'item_title', 'TEXT')
        self.add_column('listing_set_items', 'condition_notes', 'TEXT')

        # Create indexes
        self.create_index('idx_set_items_listing', 'listing_set_items', 'listing_id')
        self.create_index('idx_set_items_position', 'listing_set_items', 'listing_id, position_index')

    def create_tracking_table(self):
        """Create the tracking table for order shipment tracking"""
        print("\n[20/21] Creating TRACKING table...")

        sql = """
        CREATE TABLE IF NOT EXISTS tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            carrier TEXT,
            tracking_number TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
        )
        """

        if not self.table_exists('tracking'):
            self.cursor.execute(sql)
            self.log_change("Created tracking table")
        else:
            self.log_skip("Table 'tracking' already exists")

    def create_bid_fills_table(self):
        """Create the bid_fills table for tracking bid fulfillment"""
        print("\n[21/25] Creating BID_FILLS table...")

        sql = """
        CREATE TABLE IF NOT EXISTS bid_fills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bid_id INTEGER NOT NULL,
            listing_id INTEGER NOT NULL,
            quantity_fulfilled INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bid_id) REFERENCES bids(id),
            FOREIGN KEY (listing_id) REFERENCES listings(id)
        )
        """

        if not self.table_exists('bid_fills'):
            self.cursor.execute(sql)
            self.log_change("Created bid_fills table")
        else:
            self.log_skip("Table 'bid_fills' already exists")

    def create_cancellation_requests_table(self):
        """Create the cancellation_requests table"""
        print("\n[22/25] Creating CANCELLATION_REQUESTS table...")

        sql = """
        CREATE TABLE IF NOT EXISTS cancellation_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL UNIQUE,
            buyer_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            additional_details TEXT,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'denied')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
            FOREIGN KEY (buyer_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """

        if not self.table_exists('cancellation_requests'):
            self.cursor.execute(sql)
            self.log_change("Created cancellation_requests table")
        else:
            self.log_skip("Table 'cancellation_requests' already exists")

        # Create indexes
        self.create_index('idx_cancellation_requests_order', 'cancellation_requests', 'order_id')
        self.create_index('idx_cancellation_requests_buyer', 'cancellation_requests', 'buyer_id')
        self.create_index('idx_cancellation_requests_status', 'cancellation_requests', 'status')

    def create_cancellation_seller_responses_table(self):
        """Create the cancellation_seller_responses table"""
        print("\n[23/25] Creating CANCELLATION_SELLER_RESPONSES table...")

        sql = """
        CREATE TABLE IF NOT EXISTS cancellation_seller_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            seller_id INTEGER NOT NULL,
            response TEXT CHECK(response IN ('approved', 'denied')),
            responded_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (request_id) REFERENCES cancellation_requests(id) ON DELETE CASCADE,
            FOREIGN KEY (seller_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(request_id, seller_id)
        )
        """

        if not self.table_exists('cancellation_seller_responses'):
            self.cursor.execute(sql)
            self.log_change("Created cancellation_seller_responses table")
        else:
            self.log_skip("Table 'cancellation_seller_responses' already exists")

        # Create indexes
        self.create_index('idx_cancellation_seller_responses_request', 'cancellation_seller_responses', 'request_id')
        self.create_index('idx_cancellation_seller_responses_seller', 'cancellation_seller_responses', 'seller_id')

    def create_seller_order_tracking_table(self):
        """Create the seller_order_tracking table for per-seller tracking numbers"""
        print("\n[24/25] Creating SELLER_ORDER_TRACKING table...")

        sql = """
        CREATE TABLE IF NOT EXISTS seller_order_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            seller_id INTEGER NOT NULL,
            tracking_number TEXT,
            carrier TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
            FOREIGN KEY (seller_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(order_id, seller_id)
        )
        """

        if not self.table_exists('seller_order_tracking'):
            self.cursor.execute(sql)
            self.log_change("Created seller_order_tracking table")
        else:
            self.log_skip("Table 'seller_order_tracking' already exists")

        # Create indexes
        self.create_index('idx_seller_order_tracking_order', 'seller_order_tracking', 'order_id')
        self.create_index('idx_seller_order_tracking_seller', 'seller_order_tracking', 'seller_id')

    def create_user_cancellation_stats_table(self):
        """Create the user_cancellation_stats table for analytics"""
        print("\n[25/27] Creating USER_CANCELLATION_STATS table...")

        sql = """
        CREATE TABLE IF NOT EXISTS user_cancellation_stats (
            user_id INTEGER PRIMARY KEY,
            canceled_orders_as_buyer INTEGER DEFAULT 0,
            canceled_volume_as_buyer REAL DEFAULT 0,
            canceled_orders_as_seller INTEGER DEFAULT 0,
            canceled_volume_as_seller REAL DEFAULT 0,
            denied_cancellations INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """

        if not self.table_exists('user_cancellation_stats'):
            self.cursor.execute(sql)
            self.log_change("Created user_cancellation_stats table")
        else:
            self.log_skip("Table 'user_cancellation_stats' already exists")

    def create_reports_table(self):
        """Create the reports table for user reports"""
        print("\n[26/27] Creating REPORTS table...")

        sql = """
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_user_id INTEGER NOT NULL,
            reported_user_id INTEGER NOT NULL,
            order_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            comment TEXT,
            status TEXT DEFAULT 'open' CHECK(status IN ('open', 'under_investigation', 'pending_review', 'resolved', 'dismissed')),
            resolution_note TEXT,
            admin_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP,
            resolved_by INTEGER,
            FOREIGN KEY (reporter_user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (reported_user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
            FOREIGN KEY (resolved_by) REFERENCES users(id)
        )
        """

        if not self.table_exists('reports'):
            self.cursor.execute(sql)
            self.log_change("Created reports table")
        else:
            self.log_skip("Table 'reports' already exists")

        # Create indexes
        self.create_index('idx_reports_reporter', 'reports', 'reporter_user_id')
        self.create_index('idx_reports_reported', 'reports', 'reported_user_id')
        self.create_index('idx_reports_order', 'reports', 'order_id')
        self.create_index('idx_reports_status', 'reports', 'status')

    def create_spot_price_snapshots_table(self):
        """Create the spot_price_snapshots time-series table"""
        print("\n[28/28] Creating SPOT_PRICE_SNAPSHOTS table...")

        sql = """
        CREATE TABLE IF NOT EXISTS spot_price_snapshots (
            id         INTEGER   PRIMARY KEY AUTOINCREMENT,
            metal      TEXT      NOT NULL,
            price_usd  REAL      NOT NULL,
            as_of      TIMESTAMP NOT NULL,
            source     TEXT      DEFAULT 'metalpriceapi',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """

        if not self.table_exists('spot_price_snapshots'):
            self.cursor.execute(sql)
            self.log_change("Created spot_price_snapshots table")
        else:
            self.log_skip("Table 'spot_price_snapshots' already exists")

        self.create_index(
            'idx_spot_snapshots_metal_as_of',
            'spot_price_snapshots',
            'metal, as_of DESC'
        )

    def create_report_attachments_table(self):
        """Create the report_attachments table for report photos"""
        print("\n[27/27] Creating REPORT_ATTACHMENTS table...")

        sql = """
        CREATE TABLE IF NOT EXISTS report_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            original_filename TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (report_id) REFERENCES reports(id) ON DELETE CASCADE
        )
        """

        if not self.table_exists('report_attachments'):
            self.cursor.execute(sql)
            self.log_change("Created report_attachments table")
        else:
            self.log_skip("Table 'report_attachments' already exists")

        # Create index
        self.create_index('idx_report_attachments_report', 'report_attachments', 'report_id')

    def run(self):
        """Run the complete schema creation/update process"""
        print("=" * 70)
        print("METEX DATABASE SCHEMA CREATION/UPDATE")
        print("=" * 70)
        print("\nThis script will create missing tables and add missing columns.")
        print("Existing data will NOT be modified or deleted.\n")

        try:
            # Get database connection using project's helper
            self.conn = get_db_connection()
            self.cursor = self.conn.cursor()

            # Create all tables and ensure all columns exist
            self.create_users_table()
            self.create_categories_table()
            self.create_listings_table()
            self.create_bids_table()
            self.create_orders_table()
            self.create_order_items_table()
            self.create_cart_table()
            self.create_messages_table()
            self.create_message_reads_table()
            self.create_ratings_table()
            self.create_addresses_table()
            self.create_notification_preferences_table()
            self.create_user_preferences_table()
            self.create_portfolio_tables()
            self.create_spot_prices_table()
            self.create_price_locks_table()
            self.create_bucket_price_history_table()
            self.create_listing_photos_table()
            self.create_listing_set_items_table()
            self.create_tracking_table()
            self.create_bid_fills_table()
            self.create_cancellation_requests_table()
            self.create_cancellation_seller_responses_table()
            self.create_seller_order_tracking_table()
            self.create_user_cancellation_stats_table()
            self.create_reports_table()
            self.create_report_attachments_table()
            self.create_spot_price_snapshots_table()

            # Add cancellation columns to orders table
            self.add_column('orders', 'canceled_at', 'TIMESTAMP')
            self.add_column('orders', 'cancellation_reason', 'TEXT')

            # Commit all changes
            self.conn.commit()

            # Print summary
            print("\n" + "=" * 70)
            print("SUMMARY")
            print("=" * 70)

            if self.changes_made:
                print(f"\n✓ Successfully made {len(self.changes_made)} change(s):")
                for change in self.changes_made:
                    print(f"  - {change}")
            else:
                print("\n✓ No changes needed - schema is already up to date!")

            if self.errors:
                print(f"\n✗ Encountered {len(self.errors)} error(s):")
                for error in self.errors:
                    print(f"  - {error}")
                print("\nSome operations failed. Please review the errors above.")
                return False
            else:
                print("\n✓ All operations completed successfully!")
                print("\nYour database schema is now complete and ready to use.")
                return True

        except Exception as e:
            print(f"\n✗ FATAL ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False

        finally:
            if self.conn:
                self.conn.close()


def main():
    """Main entry point"""
    manager = SchemaManager()
    success = manager.run()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
