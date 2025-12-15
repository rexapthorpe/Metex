#!/usr/bin/env python3
"""
Check if recipient names are being saved in bids and orders tables.
"""

import sqlite3

conn = sqlite3.connect('database.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("\n" + "="*60)
print("CHECKING RECIPIENT NAMES IN DATABASE")
print("="*60)

# Check bids table
print("\n[BIDS TABLE]")
bids = cursor.execute("""
    SELECT id, buyer_id, recipient_first_name, recipient_last_name,
           CASE
               WHEN recipient_first_name IS NULL THEN 'NULL'
               WHEN recipient_first_name = '' THEN 'EMPTY STRING'
               ELSE recipient_first_name
           END as first_display,
           CASE
               WHEN recipient_last_name IS NULL THEN 'NULL'
               WHEN recipient_last_name = '' THEN 'EMPTY STRING'
               ELSE recipient_last_name
           END as last_display
    FROM bids
    ORDER BY id DESC
    LIMIT 5
""").fetchall()

if bids:
    for bid in bids:
        print(f"  Bid #{bid['id']} (buyer_id={bid['buyer_id']})")
        print(f"    recipient_first_name: {bid['first_display']}")
        print(f"    recipient_last_name:  {bid['last_display']}")
        print()
else:
    print("  No bids found")

# Check orders table
print("\n[ORDERS TABLE]")
orders = cursor.execute("""
    SELECT id, buyer_id, recipient_first_name, recipient_last_name,
           CASE
               WHEN recipient_first_name IS NULL THEN 'NULL'
               WHEN recipient_first_name = '' THEN 'EMPTY STRING'
               ELSE recipient_first_name
           END as first_display,
           CASE
               WHEN recipient_last_name IS NULL THEN 'NULL'
               WHEN recipient_last_name = '' THEN 'EMPTY STRING'
               ELSE recipient_last_name
           END as last_display
    FROM orders
    ORDER BY id DESC
    LIMIT 5
""").fetchall()

if orders:
    for order in orders:
        print(f"  Order #{order['id']} (buyer_id={order['buyer_id']})")
        print(f"    recipient_first_name: {order['first_display']}")
        print(f"    recipient_last_name:  {order['last_display']}")
        print()
else:
    print("  No orders found")

# Check if columns exist
print("\n[SCHEMA CHECK]")
bids_schema = cursor.execute("PRAGMA table_info(bids)").fetchall()
orders_schema = cursor.execute("PRAGMA table_info(orders)").fetchall()

bid_cols = [col[1] for col in bids_schema]
order_cols = [col[1] for col in orders_schema]

print(f"  Bids table has recipient_first_name: {'recipient_first_name' in bid_cols}")
print(f"  Bids table has recipient_last_name: {'recipient_last_name' in bid_cols}")
print(f"  Orders table has recipient_first_name: {'recipient_first_name' in order_cols}")
print(f"  Orders table has recipient_last_name: {'recipient_last_name' in order_cols}")

conn.close()

print("\n" + "="*60)
print("DIAGNOSIS COMPLETE")
print("="*60 + "\n")
