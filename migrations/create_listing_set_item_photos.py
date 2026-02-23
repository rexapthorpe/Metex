#!/usr/bin/env python3
"""
Migration: Create listing_set_item_photos table

This migration adds support for multiple photos per set item (up to 3 photos).
Previously, listing_set_items only had a single photo_path column.
Now each set item can have 1-3 photos stored in a separate table.

Usage:
    python migrations/create_listing_set_item_photos.py
"""

import sqlite3
import sys
import os

# Add parent directory to path to import database module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db_connection


def run_migration():
    """Create listing_set_item_photos table for multi-photo support"""
    conn = get_db_connection()
    cursor = conn.cursor()

    print("=" * 70)
    print("MIGRATION: Create listing_set_item_photos table")
    print("=" * 70)

    try:
        # Check if table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='listing_set_item_photos'
        """)

        if cursor.fetchone():
            print("\n✓ Table 'listing_set_item_photos' already exists - skipping")
            return True

        # Create the table
        print("\nCreating listing_set_item_photos table...")
        cursor.execute("""
            CREATE TABLE listing_set_item_photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                set_item_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                position_index INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (set_item_id) REFERENCES listing_set_items(id) ON DELETE CASCADE
            )
        """)

        # Create index for efficient lookups
        print("Creating index on set_item_id...")
        cursor.execute("""
            CREATE INDEX idx_set_item_photos_set_item
            ON listing_set_item_photos(set_item_id)
        """)

        # Create index for ordering
        cursor.execute("""
            CREATE INDEX idx_set_item_photos_position
            ON listing_set_item_photos(set_item_id, position_index)
        """)

        conn.commit()

        print("\n✓ Successfully created listing_set_item_photos table")
        print("✓ Created index idx_set_item_photos_set_item")
        print("✓ Created index idx_set_item_photos_position")
        print("\nMigration completed successfully!")

        return True

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()


if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)
