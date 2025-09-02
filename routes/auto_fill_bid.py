# routes/auto_fill_bid.py 
from database import get_db_connection
from datetime import datetime
import os
import sqlite3

# Correct database path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db_path = os.path.join(BASE_DIR, 'database.db')

def auto_fill_bid(bid_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Fetch bid details including address
        cursor.execute("SELECT category_id, quantity_requested, price_per_coin, buyer_id, delivery_address FROM bids WHERE id = ?", (bid_id,))
        bid = cursor.fetchone()

        if not bid:
            return "❌ Bid not found."

        category_id = bid['category_id']
        quantity_requested = bid['quantity_requested']
        price_limit = bid['price_per_coin']
        buyer_id = bid['buyer_id']
        delivery_address = bid['delivery_address']

        quantity_needed = quantity_requested

        # Find matching listings
        cursor.execute('''
            SELECT id, quantity, price_per_coin, seller_id
            FROM listings
            WHERE category_id = ? AND price_per_coin <= ? AND active = 1
            ORDER BY price_per_coin ASC
        ''', (category_id, price_limit))

        listings = cursor.fetchall()

        if not listings:
            return "❌ No matching listings found to fill your bid."

        # Try to fill
        for listing in listings:
            if quantity_needed <= 0:
                break

            available_quantity = listing['quantity']
            fill_quantity = min(available_quantity, quantity_needed)

            # Update listing quantity
            if available_quantity - fill_quantity == 0:
                cursor.execute('UPDATE listings SET quantity = 0, active = 0 WHERE id = ?', (listing['id'],))
            else:
                cursor.execute('UPDATE listings SET quantity = ? WHERE id = ?', (available_quantity - fill_quantity, listing['id']))

            # Insert into bid_fills table
            cursor.execute('''
                INSERT INTO bid_fills (bid_id, listing_id, quantity_filled, price_at_fill, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (bid_id, listing['id'], fill_quantity, listing['price_per_coin'], datetime.now()))

            # Insert into orders table
            cursor.execute('''
                INSERT INTO orders (listing_id, buyer_id, seller_id, quantity, price_each, status, delivery_address)
                VALUES (?, ?, ?, ?, ?, 'Pending Shipment', ?)
            ''', (
                listing['id'],
                buyer_id,
                listing['seller_id'],
                fill_quantity,
                listing['price_per_coin'],
                delivery_address
            ))

            quantity_needed -= fill_quantity

        # Update the bid record
        filled_quantity = quantity_requested - quantity_needed

        if quantity_needed == 0:
            new_status = "Filled"
            active = 0
        else:
            new_status = "Partially Filled"
            active = 1

        cursor.execute('''
            UPDATE bids
            SET quantity_requested = ?, active = ?, status = ?
            WHERE id = ?
        ''', (quantity_needed, active, new_status, bid_id))

        conn.commit()

        if filled_quantity > 0 and quantity_needed > 0:
            return f"✅ {filled_quantity} units were filled. {quantity_needed} still outstanding."
        elif filled_quantity == 0:
            return f"✅ Your bid was submitted but no items were available to fill it."
        else:
            return f"✅ Your full bid for {filled_quantity} units was filled!"

    except Exception as e:
        conn.rollback()
        return f"❌ Error during auto-filling: {e}"

    finally:
        conn.close()
