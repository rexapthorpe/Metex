#!/usr/bin/env python3
"""
Debug what data is passed to the Sold tab template.
"""

import sqlite3

conn = sqlite3.connect('database.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("\n" + "="*70)
print("SOLD TAB DATA DEBUG")
print("="*70)

# Get first user (seller)
user = cursor.execute("SELECT id, username FROM users LIMIT 1").fetchone()
if not user:
    print("\n[ERROR] No users found!")
    conn.close()
    exit(1)

user_id = user['id']
print(f"\n[USER] Checking sold items for User #{user_id} ({user['username']})")

# Run the exact query from account_routes.py
print(f"\n[QUERY] Running Sold tab query...")
sales_raw = conn.execute(
    """SELECT o.id AS order_id,
              c.metal, c.product_type, c.weight, c.mint, c.year,
              c.finish, c.grade, c.purity, c.product_line, c.coin_series,
              c.special_designation,
              oi.quantity,
              l.price_per_coin AS price_each,
              l.graded,
              l.grading_service,
              u.username AS buyer_username,
              u.first_name AS buyer_first_name,
              u.last_name AS buyer_last_name,
              o.shipping_address AS shipping_address,
              o.shipping_address AS delivery_address,
              o.recipient_first_name,
              o.recipient_last_name,
              o.status,
              o.created_at AS order_date,
              (SELECT 1 FROM ratings r
                 WHERE r.order_id = o.id
                   AND r.rater_id = ?
              ) AS already_rated
       FROM orders o
       JOIN order_items oi ON o.id = oi.order_id
       JOIN listings l     ON oi.listing_id = l.id
       JOIN categories c   ON l.category_id = c.id
       JOIN users u        ON o.buyer_id = u.id
      WHERE l.seller_id = ?
      ORDER BY o.created_at DESC
    """, (user_id, user_id)
).fetchall()

if not sales_raw:
    print("  [RESULT] No sold items found!")
    print("\n[ANALYSIS] Possible reasons:")
    print("  1. No orders exist in database")
    print("  2. No order_items linking orders to listings")
    print("  3. No listings for this seller")
    print("  4. Orders exist but for different sellers")

    # Check each table
    print("\n[CHECKING TABLES]")
    orders_count = cursor.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    print(f"  orders table: {orders_count} records")

    order_items_count = cursor.execute("SELECT COUNT(*) FROM order_items").fetchone()[0]
    print(f"  order_items table: {order_items_count} records")

    listings_count = cursor.execute("SELECT COUNT(*) FROM listings WHERE seller_id = ?", (user_id,)).fetchone()[0]
    print(f"  listings for seller #{user_id}: {listings_count} records")

    conn.close()
    exit(1)

print(f"  [RESULT] Found {len(sales_raw)} sold item(s)")

# Process sales data (simulate what account_routes.py does)
print(f"\n[PROCESSING] Building shipping_name for each sale...")
sales = []
for i, sale_row in enumerate(sales_raw, 1):
    sale = dict(sale_row)

    print(f"\n  --- Sale #{i} (Order #{sale['order_id']}) ---")
    print(f"  recipient_first_name: '{sale.get('recipient_first_name')}'")
    print(f"  recipient_last_name: '{sale.get('recipient_last_name')}'")
    print(f"  buyer_first_name: '{sale.get('buyer_first_name')}'")
    print(f"  buyer_last_name: '{sale.get('buyer_last_name')}'")

    # Priority 1: Use recipient names from order (if available)
    if sale.get('recipient_first_name') or sale.get('recipient_last_name'):
        first = (sale.get('recipient_first_name') or '').strip()
        last = (sale.get('recipient_last_name') or '').strip()
        shipping_name = f"{first} {last}".strip()
        print(f"  Built shipping_name from order: '{shipping_name}'")
    else:
        # Priority 2: Parse from delivery_address (backward compatibility)
        shipping_name = None
        if sale.get('delivery_address'):
            parts = sale['delivery_address'].split('•')

            if len(parts) >= 4:
                shipping_name = parts[0].strip()
                print(f"  Parsed shipping_name from address (4+ parts): '{shipping_name}'")
            elif len(parts) == 3:
                first_part = parts[0].strip()
                if ' ' in first_part and (not first_part or not first_part[0].isdigit()):
                    shipping_name = first_part
                    print(f"  Parsed shipping_name from address (3 parts): '{shipping_name}'")
                else:
                    print(f"  Address has 3 parts but first part doesn't look like a name")
            else:
                print(f"  Address has {len(parts)} parts - not parsing name")
        else:
            print(f"  No delivery_address")

    sale['shipping_name'] = shipping_name

    # Check what would display in template
    if shipping_name:
        print(f"  [TEMPLATE] Name WOULD display: '{shipping_name}'")
    else:
        print(f"  [TEMPLATE] Name would NOT display (empty/None)")

    print(f"  Username: {sale['buyer_username']}")
    print(f"  Order Date: {sale['order_date']}")

    sales.append(sale)

print("\n" + "="*70)
print(f"SUMMARY: {len(sales)} sold items with following names:")
for i, sale in enumerate(sales, 1):
    name_display = sale['shipping_name'] if sale['shipping_name'] else "[NO NAME]"
    print(f"  {i}. Order #{sale['order_id']}: {name_display}")
print("="*70 + "\n")

conn.close()
