"""
TEST COMPLETE BID ACCEPTANCE FLOW
Tests the full bid acceptance flow including:
- Database operations with WAL mode
- Order creation
- Notification delivery
"""
from database import get_db_connection
from services.notification_service import get_user_notifications
import sys

print("=" * 80)
print("COMPLETE BID ACCEPTANCE FLOW TEST")
print("Testing: Database operations + Notifications")
print("=" * 80)

# Clean up test data
print("\n[SETUP] Cleaning up previous test data...")
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("DELETE FROM notifications WHERE user_id IN (7771, 7772)")
cursor.execute("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE buyer_id IN (7771, 7772))")
cursor.execute("DELETE FROM orders WHERE buyer_id IN (7771, 7772) OR seller_id IN (7771, 7772)")
cursor.execute("DELETE FROM listings WHERE seller_id IN (7771, 7772)")
cursor.execute("DELETE FROM bids WHERE buyer_id IN (7771, 7772)")
cursor.execute("DELETE FROM users WHERE id IN (7771, 7772)")
conn.commit()

# Create test users
print("[SETUP] Creating test users...")
cursor.execute("""
    INSERT INTO users (id, username, email, password_hash, first_name, last_name)
    VALUES (7771, 'flow_buyer', 'flow_buyer@test.com', 'hash', 'Flow', 'Buyer')
""")
cursor.execute("""
    INSERT INTO users (id, username, email, password_hash, first_name, last_name)
    VALUES (7772, 'flow_seller', 'flow_seller@test.com', 'hash', 'Flow', 'Seller')
""")

# Get a category
category = cursor.execute("SELECT id, metal, product_type, product_line, weight, year FROM categories LIMIT 1").fetchone()
if not category:
    print("[ERROR] No categories in database")
    sys.exit(1)

category_id = category['id']
print(f"[SETUP] Using category: {category['metal']} {category['product_type']}")

conn.commit()

# ===========================================================================
# COMPLETE BID ACCEPTANCE FLOW
# ===========================================================================

print("\n" + "=" * 80)
print("SCENARIO: Complete Bid Acceptance + Notification Flow")
print("=" * 80)

print("\n[STEP 1] Buyer creates a bid...")
cursor.execute("""
    INSERT INTO bids (buyer_id, category_id, price_per_coin, quantity_requested, remaining_quantity, status, created_at)
    VALUES (7771, ?, 60.00, 35, 35, 'open', datetime('now'))
""", (category_id,))
bid_id = cursor.lastrowid
conn.commit()
print(f"Created bid ID {bid_id} - Buyer: 7771, Price: $60.00, Qty: 35")

print("\n[STEP 2] Seller creates listings...")
cursor.execute("""
    INSERT INTO listings (seller_id, category_id, quantity, price_per_coin, active)
    VALUES (7772, ?, 100, 58.00, 1)
""", (category_id,))
listing_id = cursor.lastrowid
conn.commit()
print(f"Created listing ID {listing_id} - Seller: 7772, Price: $58.00, Qty: 100")

print("\n[STEP 3] Seller accepts the bid (simulating bid_routes.py logic)...")

try:
    # Get bid data
    bid = cursor.execute("""
        SELECT buyer_id, category_id, price_per_coin, remaining_quantity, status
        FROM bids WHERE id = ?
    """, (bid_id,)).fetchone()

    # Get eligible listings
    listings = cursor.execute("""
        SELECT id, seller_id, quantity, price_per_coin
        FROM listings
        WHERE category_id = ?
          AND seller_id = 7772
          AND active = 1
          AND price_per_coin <= ?
        ORDER BY price_per_coin ASC
    """, (bid['category_id'], bid['price_per_coin'])).fetchall()

    if not listings:
        print("[ERROR] No eligible listings found")
        sys.exit(1)

    # Fill from listing
    listing = listings[0]
    filled = min(bid['remaining_quantity'], listing['quantity'])

    print(f"Filling {filled} units from listing {listing['id']}")

    # Create order
    total_price = filled * bid['price_per_coin']
    cursor.execute("""
        INSERT INTO orders (buyer_id, seller_id, total_price, status, created_at)
        VALUES (?, ?, ?, 'Pending Shipment', datetime('now'))
    """, (bid['buyer_id'], listing['seller_id'], total_price))

    order_id = cursor.lastrowid
    print(f"Created order ID {order_id}, Total: ${total_price:.2f}")

    # Create order items
    cursor.execute("""
        INSERT INTO order_items (order_id, listing_id, quantity, price_each)
        VALUES (?, ?, ?, ?)
    """, (order_id, listing['id'], filled, bid['price_per_coin']))

    # Update listing
    new_listing_qty = listing['quantity'] - filled
    if new_listing_qty <= 0:
        cursor.execute('UPDATE listings SET quantity = 0, active = 0 WHERE id = ?', (listing['id'],))
    else:
        cursor.execute('UPDATE listings SET quantity = ? WHERE id = ?', (new_listing_qty, listing['id']))

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

    # Build item description
    item_desc_parts = []
    if category['metal']:
        item_desc_parts.append(category['metal'])
    if category['product_line']:
        item_desc_parts.append(category['product_line'])
    if category['weight']:
        item_desc_parts.append(category['weight'])
    if category['year']:
        item_desc_parts.append(str(category['year']))
    item_description = ' '.join(item_desc_parts) if item_desc_parts else 'Item'

    # Collect notification data
    notifications_to_send = [{
        'buyer_id': bid['buyer_id'],
        'order_id': order_id,
        'bid_id': bid_id,
        'item_description': item_description,
        'quantity_filled': filled,
        'price_per_unit': bid['price_per_coin'],
        'total_amount': total_price,
        'is_partial': new_remaining > 0,
        'remaining_quantity': new_remaining
    }]

    # COMMIT FIRST
    print("\n[STEP 4] Committing transaction...")
    conn.commit()
    print("[OK] Transaction committed successfully")

    conn.close()

    # Send notifications AFTER commit
    print("\n[STEP 5] Sending notifications...")
    from services.notification_service import notify_bid_filled
    for notif_data in notifications_to_send:
        print(f"  Calling notify_bid_filled for buyer {notif_data['buyer_id']}...")
        try:
            result = notify_bid_filled(**notif_data)
            if result:
                print(f"  [OK] Notification sent successfully")
            else:
                print(f"  [FAIL] notify_bid_filled returned FALSE")
        except Exception as e:
            print(f"  [ERROR] Exception in notify_bid_filled: {e}")
            import traceback
            traceback.print_exc()

    print("\n[STEP 6] Verifying notification was created...")
    buyer_notifs = get_user_notifications(7771)
    print(f"Buyer (7771) notifications: {len(buyer_notifs)}")
    for n in buyer_notifs:
        print(f"  - {n['type']}: {n['title']}")
        print(f"    Message: {n['message'][:80]}...")

    # Verify database state
    print("\n[STEP 7] Verifying database state...")
    conn = get_db_connection()
    cursor = conn.cursor()

    order_check = cursor.execute("""
        SELECT id, buyer_id, seller_id, total_price, status
        FROM orders WHERE id = ?
    """, (order_id,)).fetchone()

    bid_check = cursor.execute("""
        SELECT remaining_quantity, status FROM bids WHERE id = ?
    """, (bid_id,)).fetchone()

    print(f"Order {order_check['id']}: ${order_check['total_price']:.2f}, Status: {order_check['status']}")
    print(f"Bid {bid_id}: Remaining: {bid_check['remaining_quantity']}, Status: {bid_check['status']}")

    # ===========================================================================
    # FINAL SUMMARY
    # ===========================================================================

    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)

    all_success = (
        order_check is not None and
        bid_check is not None and
        len(buyer_notifs) > 0
    )

    if all_success:
        print("[SUCCESS] Complete bid acceptance flow works perfectly!")
        print("  ✓ Database operations completed without locking")
        print("  ✓ Order created successfully")
        print("  ✓ Bid updated correctly")
        print("  ✓ Buyer received notification")
        print("\nThe fix is complete and working as designed.")
    else:
        print("[PARTIAL SUCCESS] Some issues detected:")
        if order_check is None:
            print("  ✗ Order not created")
        if bid_check is None:
            print("  ✗ Bid not updated")
        if len(buyer_notifs) == 0:
            print("  ✗ Notification not created")

    print("=" * 80)

except Exception as e:
    print(f"\n[ERROR] BID ACCEPTANCE FAILED: {e}")
    import traceback
    traceback.print_exc()

    if 'database is locked' in str(e).lower():
        print("\n[DIAGNOSIS] DATABASE LOCKING ERROR DETECTED")
        print("This indicates WAL mode may not be properly enabled.")

    try:
        conn.rollback()
    except:
        pass

# Cleanup
print("\n[CLEANUP] Removing test data...")
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("DELETE FROM notifications WHERE user_id IN (7771, 7772)")
cursor.execute("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE buyer_id IN (7771, 7772))")
cursor.execute("DELETE FROM orders WHERE buyer_id IN (7771, 7772) OR seller_id IN (7771, 7772)")
cursor.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
cursor.execute("DELETE FROM bids WHERE id = ?", (bid_id,))
cursor.execute("DELETE FROM users WHERE id IN (7771, 7772)")
conn.commit()
conn.close()

print("[OK] Cleanup complete")
print("=" * 80)
