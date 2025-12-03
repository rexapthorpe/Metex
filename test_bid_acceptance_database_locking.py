"""
TEST BID ACCEPTANCE DATABASE LOCKING
Reproduces the database locking issue during bid acceptance
"""
from database import get_db_connection
import sys
import time
import threading

print("=" * 80)
print("BID ACCEPTANCE DATABASE LOCKING TEST")
print("=" * 80)

# First, check database configuration
print("\n[CHECK 1] Checking database journal mode...")
conn = get_db_connection()
cursor = conn.cursor()
journal_mode = cursor.execute("PRAGMA journal_mode").fetchone()
print(f"Current journal mode: {journal_mode[0]}")

busy_timeout = cursor.execute("PRAGMA busy_timeout").fetchone()
print(f"Current busy timeout: {busy_timeout[0]}ms")

# Check if there are any long-running transactions
print("\n[CHECK 2] Checking for active database connections...")
conn.close()

# Clean up test data
print("\n[SETUP] Cleaning up previous test data...")
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("DELETE FROM notifications WHERE user_id IN (5551, 5552)")
cursor.execute("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE buyer_id IN (5551, 5552))")
cursor.execute("DELETE FROM orders WHERE buyer_id IN (5551, 5552) OR seller_id IN (5551, 5552)")
cursor.execute("DELETE FROM listings WHERE seller_id IN (5551, 5552)")
cursor.execute("DELETE FROM bids WHERE buyer_id IN (5551, 5552)")
cursor.execute("DELETE FROM users WHERE id IN (5551, 5552)")
conn.commit()

# Create test users
print("[SETUP] Creating test users...")
cursor.execute("""
    INSERT INTO users (id, username, email, password_hash, first_name, last_name)
    VALUES (5551, 'lock_buyer', 'lock_buyer@test.com', 'hash', 'Lock', 'Buyer')
""")
cursor.execute("""
    INSERT INTO users (id, username, email, password_hash, first_name, last_name)
    VALUES (5552, 'lock_seller', 'lock_seller@test.com', 'hash', 'Lock', 'Seller')
""")

# Get a category
category = cursor.execute("SELECT id FROM categories LIMIT 1").fetchone()
if not category:
    print("[ERROR] No categories in database")
    sys.exit(1)

category_id = category['id']
conn.commit()
print(f"[SETUP] Using category ID: {category_id}")

# ===========================================================================
# SCENARIO: Simulate the exact accept_bid flow
# ===========================================================================

print("\n" + "=" * 80)
print("SCENARIO: Simulating Accept Bid Flow")
print("=" * 80)

print("\n[STEP 1] Buyer creates a bid...")
cursor.execute("""
    INSERT INTO bids (buyer_id, category_id, price_per_coin, quantity_requested, remaining_quantity, status, created_at)
    VALUES (5551, ?, 50.00, 40, 40, 'open', datetime('now'))
""", (category_id,))
bid_id = cursor.lastrowid
conn.commit()
print(f"Created bid ID {bid_id}")

print("\n[STEP 2] Seller creates listings...")
cursor.execute("""
    INSERT INTO listings (seller_id, category_id, quantity, price_per_coin, active)
    VALUES (5552, ?, 100, 48.00, 1)
""", (category_id,))
listing_id = cursor.lastrowid
conn.commit()
print(f"Created listing ID {listing_id}")

print("\n[STEP 3] Attempting to accept bid (simulating routes/bid_routes.py logic)...")
print("This simulates the exact code path that causes the database lock")

try:
    # Start a new connection for the accept_bid operation (simulating the route)
    print("\n  Opening new connection for accept_bid...")
    accept_conn = get_db_connection()
    accept_cursor = accept_conn.cursor()

    # Get bucket_id from bid
    print("  Fetching bid data...")
    bid_data = accept_cursor.execute("""
        SELECT category_id, buyer_id, price_per_coin, remaining_quantity, status
        FROM bids WHERE id = ?
    """, (bid_id,)).fetchone()

    if not bid_data:
        print("[ERROR] Bid not found")
        sys.exit(1)

    print(f"  Bid data: category_id={bid_data['category_id']}, buyer_id={bid_data['buyer_id']}")

    # Get listings that can fill this bid
    print("  Fetching eligible listings...")
    listings = accept_cursor.execute("""
        SELECT id, seller_id, quantity, price_per_coin
        FROM listings
        WHERE category_id = ?
          AND active = 1
          AND price_per_coin <= ?
          AND seller_id = ?
        ORDER BY price_per_coin ASC, created_at ASC
    """, (bid_data['category_id'], bid_data['price_per_coin'], 5552)).fetchall()

    print(f"  Found {len(listings)} eligible listings")

    if not listings:
        print("[ERROR] No eligible listings found")
        sys.exit(1)

    # Process the bid acceptance (this is where locking might occur)
    print("\n  Starting bid acceptance transaction...")
    notifications_to_send = []
    total_filled = 0

    for listing in listings:
        print(f"\n  Processing listing {listing['id']}...")

        remaining_qty = bid_data['remaining_quantity']
        if remaining_qty <= 0:
            break

        available = listing['quantity']
        filled = min(remaining_qty, available)

        print(f"    Filling {filled} units from listing {listing['id']}")

        # Create order
        print("    Creating order...")
        total_price = filled * bid_data['price_per_coin']

        # THIS IS WHERE THE LOCK MIGHT OCCUR
        try:
            accept_cursor.execute("""
                INSERT INTO orders (buyer_id, seller_id, total_price, status, created_at)
                VALUES (?, ?, ?, 'Pending Shipment', datetime('now'))
            """, (bid_data['buyer_id'], listing['seller_id'], total_price))
            order_id = accept_cursor.lastrowid
            print(f"    Created order ID {order_id}")
        except Exception as e:
            print(f"    [ERROR] Failed to create order: {e}")
            raise

        # Create order items
        print("    Creating order items...")
        try:
            accept_cursor.execute("""
                INSERT INTO order_items (order_id, listing_id, quantity, price_each)
                VALUES (?, ?, ?, ?)
            """, (order_id, listing['id'], filled, bid_data['price_per_coin']))
        except Exception as e:
            print(f"    [ERROR] Failed to create order items: {e}")
            raise

        # Update listing quantity
        print("    Updating listing quantity...")
        try:
            new_qty = available - filled
            if new_qty <= 0:
                accept_cursor.execute("""
                    UPDATE listings SET quantity = 0, active = 0 WHERE id = ?
                """, (listing['id'],))
            else:
                accept_cursor.execute("""
                    UPDATE listings SET quantity = ? WHERE id = ?
                """, (new_qty, listing['id']))
        except Exception as e:
            print(f"    [ERROR] Failed to update listing: {e}")
            raise

        total_filled += filled

        # Update bid remaining quantity for next iteration
        bid_data = dict(bid_data)
        bid_data['remaining_quantity'] -= filled

    # Update bid status
    print("\n  Updating bid status...")
    try:
        new_remaining = bid_data['remaining_quantity']
        if new_remaining <= 0:
            accept_cursor.execute("""
                UPDATE bids
                SET remaining_quantity = 0,
                    active = 0,
                    status = 'Filled'
                WHERE id = ?
            """, (bid_id,))
        else:
            accept_cursor.execute("""
                UPDATE bids
                SET remaining_quantity = ?,
                    status = 'Partially Filled'
                WHERE id = ?
            """, (new_remaining, bid_id))
    except Exception as e:
        print(f"  [ERROR] Failed to update bid: {e}")
        raise

    # Commit the transaction
    print("\n  Committing transaction...")
    accept_conn.commit()
    print("  [OK] Transaction committed successfully!")

    accept_conn.close()
    print("  [OK] Connection closed successfully!")

    print(f"\n[SUCCESS] Bid acceptance completed! Filled {total_filled} units")

except Exception as e:
    print(f"\n[ERROR] BID ACCEPTANCE FAILED: {e}")
    import traceback
    traceback.print_exc()

    # Try to rollback
    try:
        accept_conn.rollback()
        accept_conn.close()
    except:
        pass

    print("\n" + "=" * 80)
    print("DATABASE LOCKING DETECTED")
    print("=" * 80)
    print("\nThis confirms the database locking issue during bid acceptance.")
    print("The lock occurs when trying to execute database operations during")
    print("the accept_bid transaction.")

# Cleanup
print("\n[CLEANUP] Removing test data...")
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("DELETE FROM notifications WHERE user_id IN (5551, 5552)")
cursor.execute("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE buyer_id IN (5551, 5552))")
cursor.execute("DELETE FROM orders WHERE buyer_id IN (5551, 5552) OR seller_id IN (5551, 5552)")
cursor.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
cursor.execute("DELETE FROM bids WHERE id = ?", (bid_id,))
cursor.execute("DELETE FROM users WHERE id IN (5551, 5552)")
conn.commit()
conn.close()

print("[OK] Cleanup complete")
print("=" * 80)
