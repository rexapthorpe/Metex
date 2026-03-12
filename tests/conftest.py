"""
Shared pytest fixtures for route and integration tests.

These fixtures provide:
- Flask test client with temporary database
- Helper functions for authentication
- Test data factories
"""
import pytest
import sqlite3
import os
import sys
import tempfile
import shutil

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def app():
    """Create and configure a test application instance."""
    from app import app as flask_app

    # Store original database path
    original_db = None

    # Create a temporary directory for test database
    test_dir = tempfile.mkdtemp()
    test_db_path = os.path.join(test_dir, 'test_database.db')

    # Copy the schema from the main database or create fresh
    main_db_path = 'data/database.db'
    if os.path.exists(main_db_path):
        # Copy existing database for schema
        shutil.copy(main_db_path, test_db_path)

    # Configure app for testing
    flask_app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-secret-key',
    })

    # Patch database connection to use test database
    import database
    import core.blueprints.auth.routes as _auth_routes_mod
    original_get_db = database.get_db_connection
    original_auth_get_db = _auth_routes_mod.get_db_connection

    def test_get_db_connection():
        conn = sqlite3.connect(test_db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=30000')
        return conn

    # Patch both the module-level attribute and the auth route's bound reference.
    # core.blueprints.auth.routes does `from database import get_db_connection` at
    # import time, so patching database.get_db_connection alone is insufficient.
    database.get_db_connection = test_get_db_connection
    _auth_routes_mod.get_db_connection = test_get_db_connection

    yield flask_app

    # Cleanup
    database.get_db_connection = original_get_db
    _auth_routes_mod.get_db_connection = original_auth_get_db
    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def client(app):
    """Create a test client for the application."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create a test CLI runner."""
    return app.test_cli_runner()


@pytest.fixture
def auth_client(client):
    """
    Create a test client with a logged-in regular user.

    Returns a tuple of (client, user_id) for use in tests.
    """
    import database

    conn = database.get_db_connection()
    cursor = conn.cursor()

    # Create a test user (password column is NOT NULL in schema)
    cursor.execute("""
        INSERT INTO users (username, email, password, password_hash, is_admin, is_banned, is_frozen)
        VALUES ('testuser', 'test@example.com', 'hashed_password', 'hashed_password', 0, 0, 0)
    """)
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Log in the user by setting session
    with client.session_transaction() as sess:
        sess['user_id'] = user_id
        sess['username'] = 'testuser'

    return client, user_id


@pytest.fixture
def admin_client(client):
    """
    Create a test client with a logged-in admin user.

    Returns a tuple of (client, user_id) for use in tests.
    """
    import database

    conn = database.get_db_connection()
    cursor = conn.cursor()

    # Create an admin user (password column is NOT NULL in schema)
    cursor.execute("""
        INSERT INTO users (username, email, password, password_hash, is_admin, is_banned, is_frozen)
        VALUES ('adminuser', 'admin@example.com', 'hashed_password', 'hashed_password', 1, 0, 0)
    """)
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Log in the admin user by setting session
    with client.session_transaction() as sess:
        sess['user_id'] = user_id
        sess['username'] = 'adminuser'

    return client, user_id


@pytest.fixture
def sample_bucket(client):
    """Create a sample bucket/category for testing."""
    import database

    conn = database.get_db_connection()
    cursor = conn.cursor()

    # Create a test category (bucket)
    cursor.execute("""
        INSERT INTO categories (
            bucket_id, metal, product_type, weight, mint, year,
            product_line, is_isolated, platform_fee_type, platform_fee_value
        )
        VALUES (1, 'Gold', 'Coin', '1 oz', 'US Mint', 2024,
                'American Eagle', 0, 'percent', 2.5)
    """)
    category_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return category_id


@pytest.fixture
def sample_listing(auth_client, sample_bucket):
    """Create a sample listing for testing."""
    import database

    client, user_id = auth_client
    conn = database.get_db_connection()
    cursor = conn.cursor()

    # Create a test listing
    cursor.execute("""
        INSERT INTO listings (
            seller_id, category_id, price_per_coin, quantity, active,
            pricing_mode, spot_premium, floor_price
        )
        VALUES (?, ?, 2500.00, 5, 1, 'static', NULL, NULL)
    """, (user_id, sample_bucket))
    listing_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return listing_id, sample_bucket
