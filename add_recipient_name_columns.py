#!/usr/bin/env python3
"""
Add recipient_first_name and recipient_last_name columns to bids and orders tables.

These columns store the name entered in the Create Bid modal, which is the
source of truth for the Buyer Name shown on Sold items tiles.
"""

import sqlite3

def main():
    print("\n[INFO] Adding recipient name columns to database...")

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Check and add columns to bids table
    print("\n[BIDS TABLE]")
    cursor.execute("PRAGMA table_info(bids)")
    bid_columns = [col[1] for col in cursor.fetchall()]

    if 'recipient_first_name' not in bid_columns:
        cursor.execute("ALTER TABLE bids ADD COLUMN recipient_first_name TEXT")
        print("  [OK] Added recipient_first_name column")
    else:
        print("  [EXISTS] recipient_first_name already exists")

    if 'recipient_last_name' not in bid_columns:
        cursor.execute("ALTER TABLE bids ADD COLUMN recipient_last_name TEXT")
        print("  [OK] Added recipient_last_name column")
    else:
        print("  [EXISTS] recipient_last_name already exists")

    # Check and add columns to orders table
    print("\n[ORDERS TABLE]")
    cursor.execute("PRAGMA table_info(orders)")
    order_columns = [col[1] for col in cursor.fetchall()]

    if 'recipient_first_name' not in order_columns:
        cursor.execute("ALTER TABLE orders ADD COLUMN recipient_first_name TEXT")
        print("  [OK] Added recipient_first_name column")
    else:
        print("  [EXISTS] recipient_first_name already exists")

    if 'recipient_last_name' not in order_columns:
        cursor.execute("ALTER TABLE orders ADD COLUMN recipient_last_name TEXT")
        print("  [OK] Added recipient_last_name column")
    else:
        print("  [EXISTS] recipient_last_name already exists")

    conn.commit()
    conn.close()

    print("\n[SUCCESS] Database schema updated!")
    print("\nThese columns will store the name entered in the Create Bid modal,")
    print("which is the source of truth for Buyer Name on Sold items tiles.\n")

if __name__ == '__main__':
    main()
