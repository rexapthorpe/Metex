# routes/auto_fill_bid.py
from database import get_db_connection
from datetime import datetime
import os
import sqlite3
from services.notification_service import notify_bid_filled, notify_listing_sold

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

            # Get the order_id that was just created
            order_id = cursor.lastrowid

            # Get category details for notification
            cursor.execute('''
                SELECT metal, product_type
                FROM categories
                WHERE id = ?
            ''', (category_id,))
            category_info = cursor.fetchone()

            if category_info:
                try:
                    item_description = f"{category_info['metal']} {category_info['product_type']}"

                    # Calculate remaining quantities for partial fill detection
                    bid_remaining = quantity_requested - (quantity_requested - quantity_needed + fill_quantity)
                    listing_remaining = available_quantity - fill_quantity

                    # Notify buyer (bid filled)
                    notify_bid_filled(
                        buyer_id=buyer_id,
                        order_id=order_id,
                        bid_id=bid_id,
                        item_description=item_description,
                        quantity_filled=fill_quantity,
                        price_per_unit=listing['price_per_coin'],
                        total_amount=fill_quantity * listing['price_per_coin'],
                        is_partial=(quantity_needed > 0),  # Bid still has remaining quantity
                        remaining_quantity=quantity_needed
                    )

                    # Notify seller (listing sold)
                    notify_listing_sold(
                        seller_id=listing['seller_id'],
                        order_id=order_id,
                        listing_id=listing['id'],
                        item_description=item_description,
                        quantity_sold=fill_quantity,
                        price_per_unit=listing['price_per_coin'],
                        total_amount=fill_quantity * listing['price_per_coin'],
                        shipping_address=delivery_address,
                        is_partial=(listing_remaining > 0),  # Listing still has remaining quantity
                        remaining_quantity=listing_remaining
                    )
                except Exception as e:
                    print(f"[AUTO_FILL_BID] Failed to send notification: {e}")

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
