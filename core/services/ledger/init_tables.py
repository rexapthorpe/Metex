"""
Ledger Table Initialization

Function to initialize ledger database tables.
"""

import os
import database


def get_db_connection():
    """Get database connection - wrapper for late binding in tests"""
    return database.get_db_connection()


def init_ledger_tables():
    """
    Initialize ledger tables by running the migration.
    This is idempotent - safe to run multiple times.
    """
    migration_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        'migrations', '021_add_ledger_tables.sql'
    )

    conn = get_db_connection()
    try:
        with open(migration_path, 'r') as f:
            sql = f.read()

        # Execute the migration script
        conn.executescript(sql)
        conn.commit()
        print("[Ledger] Ledger tables initialized successfully")
        return True
    except Exception as e:
        print(f"[Ledger] Error initializing ledger tables: {e}")
        return False
    finally:
        conn.close()
