"""
System Settings Service

Provides read/write access to the system_settings table.
Used for persisted admin-configurable settings like the spot snapshot interval.

Table: system_settings(key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMP)
"""

import database as _db_module


SPOT_SNAPSHOT_INTERVAL_KEY = "spot_snapshot_interval_minutes"
SPOT_SNAPSHOT_INTERVAL_DEFAULT = 10
SPOT_SNAPSHOT_INTERVAL_MIN = 1
SPOT_SNAPSHOT_INTERVAL_MAX = 120


def _get_conn():
    return _db_module.get_db_connection()


def get_setting(key, default=None):
    """Return the string value for a setting key, or default if not set."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT value FROM system_settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_setting(key, value):
    """Upsert a setting value."""
    from datetime import datetime
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO system_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, str(value), datetime.now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def get_spot_snapshot_interval() -> int:
    """
    Return the current snapshot interval in minutes.
    Falls back to SPOT_SNAPSHOT_INTERVAL_DEFAULT if unset.
    Always returns a value within [MIN, MAX].
    """
    raw = get_setting(SPOT_SNAPSHOT_INTERVAL_KEY)
    if raw is None:
        return SPOT_SNAPSHOT_INTERVAL_DEFAULT
    try:
        val = int(raw)
    except (ValueError, TypeError):
        return SPOT_SNAPSHOT_INTERVAL_DEFAULT
    return max(SPOT_SNAPSHOT_INTERVAL_MIN, min(SPOT_SNAPSHOT_INTERVAL_MAX, val))


def set_spot_snapshot_interval(minutes) -> int:
    """
    Set the snapshot interval, clamping to [MIN, MAX].
    Returns the clamped value that was saved.
    """
    try:
        val = int(minutes)
    except (ValueError, TypeError):
        val = SPOT_SNAPSHOT_INTERVAL_DEFAULT
    clamped = max(SPOT_SNAPSHOT_INTERVAL_MIN, min(SPOT_SNAPSHOT_INTERVAL_MAX, val))
    set_setting(SPOT_SNAPSHOT_INTERVAL_KEY, str(clamped))
    return clamped


# ---------------------------------------------------------------------------
# Checkout spot staleness settings
# ---------------------------------------------------------------------------

CHECKOUT_SPOT_MAX_AGE_KEY = "spot_max_age_seconds_checkout"
CHECKOUT_SPOT_MAX_AGE_DEFAULT = 120
CHECKOUT_SPOT_MAX_AGE_MIN = 30
CHECKOUT_SPOT_MAX_AGE_MAX = 600

CHECKOUT_SPOT_REFRESH_TIMEOUT_KEY = "spot_refresh_timeout_seconds"
CHECKOUT_SPOT_REFRESH_TIMEOUT_DEFAULT = 10
CHECKOUT_SPOT_REFRESH_TIMEOUT_MIN = 3
CHECKOUT_SPOT_REFRESH_TIMEOUT_MAX = 30


def get_checkout_spot_max_age() -> int:
    """
    Return max acceptable snapshot age (seconds) at checkout.
    Defaults to CHECKOUT_SPOT_MAX_AGE_DEFAULT if unset.
    Always clamped to [MIN, MAX].
    """
    raw = get_setting(CHECKOUT_SPOT_MAX_AGE_KEY)
    if raw is None:
        return CHECKOUT_SPOT_MAX_AGE_DEFAULT
    try:
        val = int(raw)
    except (ValueError, TypeError):
        return CHECKOUT_SPOT_MAX_AGE_DEFAULT
    return max(CHECKOUT_SPOT_MAX_AGE_MIN, min(CHECKOUT_SPOT_MAX_AGE_MAX, val))


def set_checkout_spot_max_age(seconds) -> int:
    """Set checkout spot max-age, clamped to [MIN, MAX]. Returns saved value."""
    try:
        val = int(seconds)
    except (ValueError, TypeError):
        val = CHECKOUT_SPOT_MAX_AGE_DEFAULT
    clamped = max(CHECKOUT_SPOT_MAX_AGE_MIN, min(CHECKOUT_SPOT_MAX_AGE_MAX, val))
    set_setting(CHECKOUT_SPOT_MAX_AGE_KEY, str(clamped))
    return clamped


def get_checkout_spot_refresh_timeout() -> int:
    """
    Return max seconds to wait for a concurrent refresh at checkout.
    Defaults to CHECKOUT_SPOT_REFRESH_TIMEOUT_DEFAULT if unset.
    Always clamped to [MIN, MAX].
    """
    raw = get_setting(CHECKOUT_SPOT_REFRESH_TIMEOUT_KEY)
    if raw is None:
        return CHECKOUT_SPOT_REFRESH_TIMEOUT_DEFAULT
    try:
        val = int(raw)
    except (ValueError, TypeError):
        return CHECKOUT_SPOT_REFRESH_TIMEOUT_DEFAULT
    return max(CHECKOUT_SPOT_REFRESH_TIMEOUT_MIN, min(CHECKOUT_SPOT_REFRESH_TIMEOUT_MAX, val))


def set_checkout_spot_refresh_timeout(seconds) -> int:
    """Set checkout spot refresh timeout, clamped to [MIN, MAX]. Returns saved value."""
    try:
        val = int(seconds)
    except (ValueError, TypeError):
        val = CHECKOUT_SPOT_REFRESH_TIMEOUT_DEFAULT
    clamped = max(CHECKOUT_SPOT_REFRESH_TIMEOUT_MIN, min(CHECKOUT_SPOT_REFRESH_TIMEOUT_MAX, val))
    set_setting(CHECKOUT_SPOT_REFRESH_TIMEOUT_KEY, str(clamped))
    return clamped
