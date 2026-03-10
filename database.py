"""
Database connection module.

In production (DATABASE_URL env var set by Render), connects to PostgreSQL via
psycopg2. Locally, falls back to SQLite at data/database.db.

The psycopg2 wrappers translate ? placeholders to %s and make rows behave like
sqlite3.Row objects so the rest of the codebase is unchanged.
"""
import os
import re
import time
from datetime import datetime, date
from decimal import Decimal

# Render provides DATABASE_URL as postgres://... — normalize to postgresql://.
# If DATABASE_URL is not set, falls back to local SQLite.
DATABASE_URL = os.environ.get('DATABASE_URL', None)
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

IS_POSTGRES = bool(DATABASE_URL)


if IS_POSTGRES:
    import psycopg2
    import psycopg2.extras

    def _translate_placeholders(query):
        """
        Convert SQLite-specific SQL to PostgreSQL-compatible SQL.

        Handles:
          - ? positional placeholders → %s
          - last_insert_rowid() → lastval()
          - datetime('now') → CURRENT_TIMESTAMP
          - sqlite_master table-existence checks → pg_tables equivalent
          - sqlite_sequence resets → no-op SELECT
        """
        # INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL PRIMARY KEY (DDL translation)
        query = re.sub(
            r'\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b',
            'SERIAL PRIMARY KEY', query, flags=re.IGNORECASE,
        )

        # last_insert_rowid() → lastval()
        query = re.sub(r'\blast_insert_rowid\(\)', 'lastval()', query,
                       flags=re.IGNORECASE)

        # datetime('now') → CURRENT_TIMESTAMP  (also matches datetime("now"))
        query = re.sub(r"""datetime\s*\(\s*['"]now['"]\s*\)""",
                       'CURRENT_TIMESTAMP', query, flags=re.IGNORECASE)

        # NULL-safe equality: "col IS ?" (SQLite) → "col IS NOT DISTINCT FROM %s" (PostgreSQL).
        # Must run BEFORE the generic ? → %s substitution.
        query = re.sub(r'\bIS\s+\?', 'IS NOT DISTINCT FROM %s', query,
                       flags=re.IGNORECASE)

        # ? → %s  (do before sqlite_master rewrite so % chars don't double-escape)
        query = re.sub(r'\?', '%s', query)

        # sqlite_master table-existence check → pg_tables (after ? → %s)
        query = re.sub(
            r"SELECT\s+name\s+FROM\s+sqlite_master\s+WHERE\s+type\s*=\s*'table'"
            r"\s+AND\s+name\s*=\s*%s",
            "SELECT tablename AS name FROM pg_tables "
            "WHERE schemaname='public' AND tablename=%s",
            query, flags=re.IGNORECASE,
        )
        query = re.sub(
            r"SELECT\s+name\s+FROM\s+sqlite_master\s+WHERE\s+type\s*=\s*'index'"
            r"\s+AND\s+name\s*=\s*%s",
            "SELECT indexname AS name FROM pg_indexes "
            "WHERE schemaname='public' AND indexname=%s",
            query, flags=re.IGNORECASE,
        )

        # sqlite_sequence resets → no-op (PostgreSQL sequences auto-handle this)
        query = re.sub(
            r"DELETE\s+FROM\s+sqlite_sequence\s+WHERE\s+name\s*=\s*%s",
            "SELECT 1 WHERE FALSE",
            query, flags=re.IGNORECASE,
        )
        query = re.sub(
            r"DELETE\s+FROM\s+sqlite_sequence\s+WHERE\s+name\s+IN\s+\([^)]+\)",
            "SELECT 1 WHERE FALSE",
            query, flags=re.IGNORECASE,
        )
        # sqlite_sequence with a literal string (no placeholder)
        query = re.sub(
            r"DELETE\s+FROM\s+sqlite_sequence\s+WHERE\s+name\s*=\s*'[^']*'",
            "SELECT 1 WHERE FALSE",
            query, flags=re.IGNORECASE,
        )

        return query

    class _PGRow:
        """
        Wraps a psycopg2 RealDictRow to behave like sqlite3.Row:
          - Dict-style access:  row['column_name']
          - Index-style access: row[0]
          - Tuple unpacking:    a, b, c = row
          - Datetime values returned as ISO strings (matches SQLite CURRENT_TIMESTAMP format)
          - Decimal values returned as float (matches SQLite REAL)
        """
        __slots__ = ('_d', '_vals')

        def __init__(self, row_dict):
            self._d = dict(row_dict)
            self._vals = list(row_dict.values())

        def _coerce(self, val):
            """Convert PostgreSQL-specific types to SQLite-equivalent Python types."""
            if isinstance(val, datetime):
                return val.isoformat(sep=' ')
            if isinstance(val, date):
                return val.isoformat()
            if isinstance(val, Decimal):
                return float(val)
            return val

        def __getitem__(self, key):
            if isinstance(key, int):
                return self._coerce(self._vals[key])
            return self._coerce(self._d[key])

        def __iter__(self):
            return (self._coerce(v) for v in self._vals)

        def keys(self):
            return self._d.keys()

        def get(self, key, default=None):
            if key not in self._d:
                return default
            return self._coerce(self._d[key])

        def __contains__(self, key):
            return key in self._d

        def __repr__(self):
            return repr(self._d)

    class _PGCursor:
        """Wraps a psycopg2 RealDictCursor to mimic sqlite3.Cursor."""

        def __init__(self, pg_cursor):
            self._cur = pg_cursor

        def execute(self, query, params=None):
            # Silently ignore SQLite-only PRAGMA statements (no equivalent in PostgreSQL).
            if re.match(r'\s*PRAGMA\b', query, re.IGNORECASE):
                return self
            query = _translate_placeholders(query)
            self._cur.execute(query, params if params is not None else None)
            return self

        def executemany(self, query, params_list):
            query = _translate_placeholders(query)
            self._cur.executemany(query, params_list)
            return self

        def fetchone(self):
            row = self._cur.fetchone()
            return _PGRow(row) if row is not None else None

        def fetchall(self):
            return [_PGRow(r) for r in self._cur.fetchall()]

        def __iter__(self):
            for row in self._cur:
                yield _PGRow(row)

        @property
        def lastrowid(self):
            """Return the ID of the last inserted row via PostgreSQL lastval()."""
            self._cur.execute('SELECT lastval()')
            row = self._cur.fetchone()
            if row is None:
                return None
            # RealDictRow — get the single value
            return list(row.values())[0]

        @property
        def rowcount(self):
            return self._cur.rowcount

        def close(self):
            self._cur.close()

    class _PGConnection:
        """Wraps a psycopg2 connection to mimic sqlite3.Connection."""

        def __init__(self, pg_conn):
            self._conn = pg_conn

        def cursor(self):
            return _PGCursor(
                self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            )

        def execute(self, query, params=None):
            cur = self.cursor()
            cur.execute(query, params)
            return cur

        def commit(self):
            self._conn.commit()

        def rollback(self):
            self._conn.rollback()

        def close(self):
            self._conn.close()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type:
                self.rollback()
            else:
                self.commit()
            self.close()

    def get_db_connection():
        """Return a PostgreSQL connection wrapped to mimic the sqlite3 interface."""
        pg_conn = psycopg2.connect(DATABASE_URL)
        return _PGConnection(pg_conn)

else:
    import sqlite3

    def get_db_connection():
        """Return a SQLite connection (local development)."""
        conn = sqlite3.connect('data/database.db', timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=30000')
        return conn


def get_table_columns(conn, table_name):
    """
    Return a set of column names for the given table.
    Works on both SQLite (PRAGMA table_info) and PostgreSQL (information_schema).
    """
    if IS_POSTGRES:
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
            (table_name,)
        ).fetchall()
        return {row['column_name'] for row in rows}
    else:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {row[1] for row in rows}


def execute_with_retry(cursor, query, params=None, max_retries=3, initial_delay=0.1):
    """
    Execute a query with retry logic for SQLite lock contention.
    In PostgreSQL mode, lock contention is handled by the server; this is a
    thin passthrough.
    """
    if IS_POSTGRES:
        if params:
            return cursor.execute(query, params)
        return cursor.execute(query)

    import sqlite3 as _sqlite3
    delay = initial_delay
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            if params:
                return cursor.execute(query, params)
            else:
                return cursor.execute(query)
        except _sqlite3.OperationalError as e:
            if 'database is locked' in str(e).lower():
                last_error = e
                if attempt < max_retries:
                    time.sleep(delay)
                    delay *= 2
                else:
                    raise
            else:
                raise

    if last_error:
        raise last_error
