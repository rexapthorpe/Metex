"""
TEST CONCURRENT BID ACCEPTANCE WITH WAL MODE
Tests that bid acceptance works even with concurrent database access
"""
from database import get_db_connection
from services.notification_service import get_user_notifications
import sys
import threading
import time

print("=" * 80)
print("CONCURRENT BID ACCEPTANCE TEST")
print("Testing database locking fixes with WAL mode")
print("=" * 80)

# Check WAL mode is enabled
print("\n[CHECK] Verifying WAL mode is enabled...")
conn = get_db_connection()
cursor = conn.cursor()
journal_mode = cursor.execute("PRAGMA journal_mode").fetchone()
print(f"Journal mode: {journal_mode[0]}")

if journal_mode[0].upper() != 'WAL':
    print("[WARNING] WAL mode is NOT enabled! Database locking issues may occur.")
else:
    print("[OK] WAL mode is enabled - concurrent access should work")

busy_timeout = cursor.execute("PRAGMA busy_timeout").fetchone()
print(f"Busy timeout: {busy_timeout[0]}ms")
conn.close()

# Clean up test data
print("\n[SETUP] Cleaning up previous test data...")
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("DELETE FROM notifications WHERE user_id IN (6661, 6662, 6663)")
cursor.execute("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE buyer_id IN (6661, 6662, 6663))")
cursor.execute("DELETE FROM orders WHERE buyer_id IN (6661, 6662, 6663) OR seller_id IN (6661, 6662, 6663)")
cursor.execute("DELETE FROM listings WHERE seller_id IN (6661, 6662, 6663)")
cursor.execute("DELETE FROM bids WHERE buyer_id IN (6661, 6662, 6663)")
cursor.execute("DELETE FROM users WHERE id IN (6661, 6662, 6663)")
conn.commit()

# Create test users
print("[SETUP] Creating test users...")
cursor.execute("""
    INSERT INTO users (id, username, email, password_hash, first_name, last_name)
    VALUES (6661, 'concurrent_buyer1', 'cb1@test.com', 'hash', 'Buyer', 'One')
""")
cursor.execute("""
    INSERT INTO users (id, username, email, password_hash, first_name, last_name)
    VALUES (6662, 'concurrent_buyer2', 'cb2@test.com', 'hash', 'Buyer', 'Two')
""")
cursor.execute("""
    INSERT INTO users (id, username, email, password_hash, first_name, last_name)
    VALUES (6663, 'concurrent_seller', 'cs@test.com', 'hash', 'Concurrent', 'Seller')
""")

# Get a category
category = cursor.execute("SELECT id, metal, product_type FROM categories LIMIT 1").fetchone()
if not category:
    print("[ERROR] No categories in database")
    sys.exit(1)

category_id = category['id']
print(f"[SETUP] Using category: {category['metal']} {category['product_type']}")

# Create bids from both buyers
print("[SETUP] Creating bids from both buyers...")
cursor.execute("""
    INSERT INTO bids (buyer_id, category_id, price_per_coin, quantity_requested, remaining_quantity, status, created_at)
    VALUES (6661, ?, 55.00, 50, 50, 'open', datetime('now'))
""", (category_id,))
bid1_id = cursor.lastrowid

cursor.execute("""
    INSERT INTO bids (buyer_id, category_id, price_per_coin, quantity_requested, remaining_quantity, status, created_at)
    VALUES (6662, ?, 56.00, 50, 50, 'open', datetime('now'))
""", (category_id,))
bid2_id = cursor.lastrowid

# Create seller listings
print("[SETUP] Creating seller listings...")
cursor.execute("""
    INSERT INTO listings (seller_id, category_id, quantity, price_per_coin, active)
    VALUES (6663, ?, 200, 52.00, 1)
""", (category_id,))
listing_id = cursor.lastrowid

conn.commit()
conn.close()

print(f"Created bid1={bid1_id}, bid2={bid2_id}, listing={listing_id}")

# ===========================================================================
# SCENARIO: Simulate concurrent bid acceptance
# ===========================================================================

print("\n" + "=" * 80)
print("SCENARIO: Two concurrent bid acceptances")
print("=" * 80)

errors = []
successes = []

def accept_bid_thread(bid_id, thread_name):
    """Simulate accepting a bid in a separate thread"""
    try:
        print(f"\n[{thread_name}] Starting bid acceptance for bid {bid_id}...")

        conn = get_db_connection()
        cursor = conn.cursor()

        # Get bid data
        bid = cursor.execute("""
            SELECT buyer_id, category_id, price_per_coin, remaining_quantity
            FROM bids WHERE id = ?
        """, (bid_id,)).fetchone()

        if not bid:
            errors.append(f"{thread_name}: Bid not found")
            conn.close()
            return

        # Get listings that can fill this bid
        listings = cursor.execute("""
            SELECT id, seller_id, quantity, price_per_coin
            FROM listings
            WHERE category_id = ?
              AND active = 1
              AND price_per_coin <= ?
            ORDER BY price_per_coin ASC
        """, (bid['category_id'], bid['price_per_coin'])).fetchall()

        if not listings:
            errors.append(f"{thread_name}: No eligible listings")
            conn.close()
            return

        # Fill from first listing
        listing = listings[0]
        filled = min(bid['remaining_quantity'], listing['quantity'])

        print(f"[{thread_name}] Filling {filled} units...")

        # Create order (THIS IS WHERE LOCKING USED TO OCCUR)
        total_price = filled * bid['price_per_coin']
        cursor.execute("""
            INSERT INTO orders (buyer_id, seller_id, total_price, status, created_at)
            VALUES (?, ?, ?, 'Pending Shipment', datetime('now'))
        """, (bid['buyer_id'], listing['seller_id'], total_price))

        order_id = cursor.lastrowid
        print(f"[{thread_name}] Created order {order_id}")

        # Create order item
        cursor.execute("""
            INSERT INTO order_items (order_id, listing_id, quantity, price_each)
            VALUES (?, ?, ?, ?)
        """, (order_id, listing['id'], filled, bid['price_per_coin']))

        # Update listing
        new_qty = listing['quantity'] - filled
        if new_qty <= 0:
            cursor.execute("""
                UPDATE listings SET quantity = 0, active = 0 WHERE id = ?
            """, (listing['id'],))
        else:
            cursor.execute("""
                UPDATE listings SET quantity = ? WHERE id = ?
            """, (new_qty, listing['id']))

        # Update bid
        new_remaining = bid['remaining_quantity'] - filled
        if new_remaining <= 0:
            cursor.execute("""
                UPDATE bids SET remaining_quantity = 0, active = 0, status = 'Filled' WHERE id = ?
            """, (bid_id,))
        else:
            cursor.execute("""
                UPDATE bids SET remaining_quantity = ?, status = 'Partially Filled' WHERE id = ?
            """, (new_remaining, bid_id))

        # Commit
        conn.commit()
        conn.close()

        print(f"[{thread_name}] SUCCESS - Committed transaction")
        successes.append(thread_name)

    except Exception as e:
        error_msg = f"{thread_name}: {type(e).__name__}: {e}"
        print(f"[{thread_name}] ERROR: {e}")
        errors.append(error_msg)
        try:
            conn.rollback()
            conn.close()
        except:
            pass

# Create threads to simulate concurrent access
print("\n[TEST] Launching concurrent threads...")
thread1 = threading.Thread(target=accept_bid_thread, args=(bid1_id, "Thread-1"))
thread2 = threading.Thread(target=accept_bid_thread, args=(bid2_id, "Thread-2"))

# Start both threads at nearly the same time
thread1.start()
thread2.start()

# Wait for both to complete
thread1.join()
thread2.join()

print("\n" + "=" * 80)
print("RESULTS")
print("=" * 80)

if errors:
    print(f"\n[ERRORS] {len(errors)} errors occurred:")
    for err in errors:
        print(f"  - {err}")
else:
    print("\n[SUCCESS] No errors!")

if successes:
    print(f"\n[SUCCESSES] {len(successes)} threads succeeded:")
    for succ in successes:
        print(f"  - {succ}")

# Check database state
print("\n[VERIFICATION] Checking database state...")
conn = get_db_connection()
cursor = conn.cursor()

orders = cursor.execute("""
    SELECT id, buyer_id, total_price, status
    FROM orders
    WHERE buyer_id IN (6661, 6662)
    ORDER BY id
""").fetchall()

print(f"\nOrders created: {len(orders)}")
for order in orders:
    print(f"  Order {order['id']}: Buyer {order['buyer_id']}, ${order['total_price']:.2f}, {order['status']}")

bids = cursor.execute("""
    SELECT id, buyer_id, remaining_quantity, status
    FROM bids
    WHERE id IN (?, ?)
    ORDER BY id
""", (bid1_id, bid2_id)).fetchall()

print(f"\nBid statuses:")
for bid in bids:
    print(f"  Bid {bid['id']}: Buyer {bid['buyer_id']}, Remaining: {bid['remaining_quantity']}, Status: {bid['status']}")

# ===========================================================================
# FINAL SUMMARY
# ===========================================================================

print("\n" + "=" * 80)
print("FINAL SUMMARY")
print("=" * 80)

if len(errors) == 0 and len(successes) == 2 and len(orders) == 2:
    print("[SUCCESS] All concurrent operations completed successfully!")
    print("  - Both threads executed without database locking errors")
    print("  - Both orders were created")
    print("  - WAL mode is working correctly")
elif 'database is locked' in str(errors):
    print("[FAILURE] Database locking still occurs!")
    print("  - WAL mode may not be enabled properly")
    print("  - Additional fixes may be needed")
else:
    print("[PARTIAL SUCCESS] Operations completed but with issues:")
    print(f"  - Errors: {len(errors)}")
    print(f"  - Successes: {len(successes)}")

print("=" * 80)

# Cleanup
print("\n[CLEANUP] Removing test data...")
cursor.execute("DELETE FROM notifications WHERE user_id IN (6661, 6662, 6663)")
cursor.execute("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE buyer_id IN (6661, 6662, 6663))")
cursor.execute("DELETE FROM orders WHERE buyer_id IN (6661, 6662, 6663) OR seller_id IN (6661, 6662, 6663)")
cursor.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
cursor.execute("DELETE FROM bids WHERE id IN (?, ?)", (bid1_id, bid2_id))
cursor.execute("DELETE FROM users WHERE id IN (6661, 6662, 6663)")
conn.commit()
conn.close()

print("[OK] Cleanup complete")
print("=" * 80)
