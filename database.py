import sqlite3
import time

def get_db_connection():
    """
    Creates a database connection with optimizations for concurrent access.

    Features:
    - WAL mode: Allows concurrent reads and writes
    - 30 second timeout: Gives operations time to complete
    - Row factory: Returns rows as dict-like objects
    """
    # Increased timeout to 30 seconds to handle concurrent database access
    # This prevents "database is locked" errors when multiple connections exist
    conn = sqlite3.connect('database.db', timeout=30.0)
    conn.row_factory = sqlite3.Row

    # Enable WAL mode for better concurrent access
    # WAL mode allows readers to access the database while a writer is active
    conn.execute('PRAGMA journal_mode=WAL')

    # Set busy timeout at the connection level as well
    conn.execute('PRAGMA busy_timeout=30000')

    return conn


def execute_with_retry(cursor, query, params=None, max_retries=3, initial_delay=0.1):
    """
    Execute a database query with retry logic for handling locked database.

    Args:
        cursor: Database cursor
        query: SQL query string
        params: Query parameters (optional)
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds before first retry (default: 0.1)

    Returns:
        Cursor result from execute()

    Raises:
        sqlite3.OperationalError: If database remains locked after all retries
    """
    delay = initial_delay
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            if params:
                return cursor.execute(query, params)
            else:
                return cursor.execute(query)
        except sqlite3.OperationalError as e:
            if 'database is locked' in str(e).lower():
                last_error = e
                if attempt < max_retries:
                    # Exponential backoff with jitter
                    time.sleep(delay)
                    delay *= 2  # Double the delay for next attempt
                else:
                    # All retries exhausted
                    raise e
            else:
                # Not a locking error, re-raise immediately
                raise e

    # Should never reach here, but just in case
    if last_error:
        raise last_error
