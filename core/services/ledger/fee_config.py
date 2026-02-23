"""
Ledger Fee Configuration

Methods for getting and updating fee configuration.
"""

from typing import Tuple
import database
from services.ledger_constants import (
    DEFAULT_PLATFORM_FEE_TYPE, DEFAULT_PLATFORM_FEE_VALUE, FeeType
)
from .exceptions import BucketFeeConfigError


def get_db_connection():
    """Get database connection - wrapper for late binding in tests"""
    return database.get_db_connection()


def get_fee_config(config_key: str = 'default_platform_fee') -> Tuple[str, float]:
    """
    Get fee configuration from database or return defaults.

    Returns:
        Tuple of (fee_type, fee_value)
    """
    conn = get_db_connection()
    try:
        result = conn.execute('''
            SELECT fee_type, fee_value FROM fee_config
            WHERE config_key = ? AND active = 1
        ''', (config_key,)).fetchone()

        if result:
            return result['fee_type'], result['fee_value']
        return DEFAULT_PLATFORM_FEE_TYPE.value, DEFAULT_PLATFORM_FEE_VALUE
    finally:
        conn.close()


def get_bucket_fee_config(bucket_id: int, conn=None) -> Tuple[str, float]:
    """
    Get fee configuration for a specific bucket.

    Priority:
    1. Bucket-level fee (platform_fee_type/platform_fee_value on categories table)
    2. Global default (fee_config table)

    Args:
        bucket_id: The bucket ID to look up fees for
        conn: Optional existing database connection

    Returns:
        Tuple of (fee_type, fee_value)

    Raises:
        BucketFeeConfigError: If no valid fee configuration is found
    """
    close_conn = False
    if conn is None:
        conn = get_db_connection()
        close_conn = True

    try:
        # Try to get bucket-level fee config
        bucket_fee = conn.execute('''
            SELECT platform_fee_type, platform_fee_value
            FROM categories
            WHERE bucket_id = ?
              AND platform_fee_type IS NOT NULL
              AND platform_fee_value IS NOT NULL
            LIMIT 1
        ''', (bucket_id,)).fetchone()

        if bucket_fee:
            fee_type = bucket_fee['platform_fee_type']
            fee_value = bucket_fee['platform_fee_value']

            # Validate fee configuration
            if fee_type not in ('percent', 'flat'):
                raise BucketFeeConfigError(
                    f"Invalid fee_type '{fee_type}' for bucket {bucket_id}. "
                    f"Must be 'percent' or 'flat'."
                )
            if fee_value < 0:
                raise BucketFeeConfigError(
                    f"Invalid fee_value '{fee_value}' for bucket {bucket_id}. "
                    f"Must be >= 0."
                )

            # Log in dev that we're using bucket fee
            import os
            if os.environ.get('FLASK_ENV') == 'development':
                print(f"[LedgerService] Using bucket fee for bucket_id={bucket_id}: "
                      f"{fee_type}={fee_value}")

            return fee_type, float(fee_value)

        # Fall back to global default
        global_fee = conn.execute('''
            SELECT fee_type, fee_value FROM fee_config
            WHERE config_key = 'default_platform_fee' AND active = 1
        ''').fetchone()

        if global_fee:
            # Log in dev that we're using fallback
            import os
            if os.environ.get('FLASK_ENV') == 'development':
                print(f"[LedgerService] No bucket fee for bucket_id={bucket_id}, "
                      f"using global default: {global_fee['fee_type']}={global_fee['fee_value']}")
            return global_fee['fee_type'], float(global_fee['fee_value'])

        # If no fee config at all, raise deterministic error
        raise BucketFeeConfigError(
            f"No fee configuration found for bucket {bucket_id} and no global default configured. "
            f"Please configure a fee before checkout."
        )

    finally:
        if close_conn:
            conn.close()


def update_bucket_fee(
    bucket_id: int,
    fee_type: str,
    fee_value: float,
    admin_id: int
) -> bool:
    """
    Update the platform fee configuration for a bucket.

    This only affects FUTURE orders. Existing orders retain their snapshotted fees.

    Args:
        bucket_id: The bucket ID to update
        fee_type: 'percent' or 'flat'
        fee_value: The fee percentage or flat amount
        admin_id: The admin user making the change

    Returns:
        True if update succeeded

    Raises:
        ValueError: If fee_type or fee_value is invalid
    """
    if fee_type not in ('percent', 'flat'):
        raise ValueError(f"Invalid fee_type '{fee_type}'. Must be 'percent' or 'flat'.")
    if fee_value < 0:
        raise ValueError(f"Invalid fee_value '{fee_value}'. Must be >= 0.")

    conn = get_db_connection()
    try:
        # Get old values for logging
        old_config = conn.execute('''
            SELECT platform_fee_type, platform_fee_value
            FROM categories
            WHERE bucket_id = ?
            LIMIT 1
        ''', (bucket_id,)).fetchone()

        old_fee_type = old_config['platform_fee_type'] if old_config else None
        old_fee_value = old_config['platform_fee_value'] if old_config else None

        # Update all categories with this bucket_id
        conn.execute('''
            UPDATE categories
            SET platform_fee_type = ?,
                platform_fee_value = ?,
                fee_updated_at = CURRENT_TIMESTAMP
            WHERE bucket_id = ?
        ''', (fee_type, fee_value, bucket_id))

        # Log the event in bucket_fee_events table (create if needed)
        try:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS bucket_fee_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bucket_id INTEGER NOT NULL,
                    old_fee_type TEXT,
                    old_fee_value REAL,
                    new_fee_type TEXT NOT NULL,
                    new_fee_value REAL NOT NULL,
                    admin_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (admin_id) REFERENCES users(id)
                )
            ''')

            conn.execute('''
                INSERT INTO bucket_fee_events
                (bucket_id, old_fee_type, old_fee_value, new_fee_type, new_fee_value, admin_id)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (bucket_id, old_fee_type, old_fee_value, fee_type, fee_value, admin_id))
        except Exception as e:
            print(f"[LedgerService] Warning: Failed to log bucket fee event: {e}")

        conn.commit()

        print(f"[LedgerService] Updated bucket {bucket_id} fee: "
              f"{old_fee_type}={old_fee_value} -> {fee_type}={fee_value} "
              f"by admin_id={admin_id}")

        return True

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def calculate_fee(gross_amount: float, fee_type: str, fee_value: float) -> float:
    """
    Calculate fee amount based on fee type and value.

    Args:
        gross_amount: The gross transaction amount
        fee_type: 'percent' or 'flat'
        fee_value: The fee percentage or flat amount

    Returns:
        The calculated fee amount (rounded to 2 decimal places)
    """
    if fee_type == FeeType.PERCENT.value or fee_type == 'percent':
        return round(gross_amount * (fee_value / 100), 2)
    elif fee_type == FeeType.FLAT.value or fee_type == 'flat':
        return round(fee_value, 2)
    return 0.0
