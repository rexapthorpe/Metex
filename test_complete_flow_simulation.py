"""
COMPLETE FLOW SIMULATION TEST
Simulates the exact user flows for buying items and accepting bids
to identify where notifications fail
"""

from database import get_db_connection
from services.notification_service import get_user_notifications
import sys

print("=" * 80)
print("COMPLETE FLOW SIMULATION - NOTIFICATION DEBUGGING")
print("=" * 80)

# Setup test environment
conn = get_db_connection()
cursor = conn.cursor()

# Clean up previous test data
print("\n[SETUP] Cleaning up previous test data...")
cursor.execute("DELETE FROM notifications WHERE user_id IN (8881, 8882)")
cursor.execute("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE buyer_id IN (8881, 8882))")
cursor.execute("DELETE FROM orders WHERE buyer_id IN (8881, 8882) OR buyer_id IN (8881, 8882)")
cursor.execute("DELETE FROM cart WHERE user_id IN (8881, 8882)")
cursor.execute("DELETE FROM listings WHERE seller_id IN (8881, 8882)")
cursor.execute("DELETE FROM bids WHERE buyer_id IN (8881, 8882)")
cursor.execute("DELETE FROM addresses WHERE user_id IN (8881, 8882)")
cursor.execute("DELETE FROM users WHERE id IN (8881, 8882)")
conn.commit()

# Create test users
print("[SETUP] Creating test users...")
cursor.execute("""
    INSERT INTO users (id, username, email, password_hash, first_name, last_name)
    VALUES (8881, 'flow_seller', 'seller_flow@test.com', 'hash', 'Flow', 'Seller')
""")
cursor.execute("""
    INSERT INTO users (id, username, email, password_hash, first_name, last_name)
    VALUES (8882, 'flow_buyer', 'buyer_flow@test.com', 'hash', 'Flow', 'Buyer')
""")

# Create address for buyer
cursor.execute("""
    INSERT INTO addresses (user_id, street, street_line2, city, state, zip_code, country, name)
    VALUES (8882, '123 Buyer St', 'Apt 5', 'Buyer City', 'NY', '12345', 'USA', 'Home')
""")

# Get a real category
category = cursor.execute("SELECT id, metal, product_type, weight, year FROM categories LIMIT 1").fetchone()
if not category:
    print("[ERROR] No categories in database")
    sys.exit(1)

category_id = category['id']
print(f"[SETUP] Using category: {category['metal']} {category['product_type']}")

conn.commit()

# ===========================================================================
# SCENARIO 1: BUYER PURCHASES FROM SELLER'S LISTING (CHECKOUT FLOW)
# ===========================================================================

print("\n" + "=" * 80)
print("SCENARIO 1: Buyer Purchases from Seller's Listing")
print("=" * 80)

print("\n[STEP 1] Seller creates a listing...")
cursor.execute("""
    INSERT INTO listings (seller_id, category_id, quantity, price_per_coin, active)
    VALUES (8881, ?, 50, 45.00, 1)
""", (category_id,))
listing_id = cursor.lastrowid
conn.commit()
print(f"Created listing ID {listing_id} - Seller: 8881, Price: $45.00, Qty: 50")

print("\n[STEP 2] Buyer adds item to cart...")
cursor.execute("""
    INSERT INTO cart (user_id, listing_id, quantity)
    VALUES (8882, ?, 10)
""", (listing_id,))
conn.commit()
print(f"Added 10 units to buyer's cart")

print("\n[STEP 3] Simulating checkout process...")
print("This simulates what happens when buyer clicks 'Confirm Order'")

# Get cart items (simulating checkout_routes.py logic)
cart_items = cursor.execute("""
    SELECT cart.listing_id, cart.quantity, listings.price_per_coin, listings.seller_id,
           listings.category_id, categories.metal, categories.product_type
    FROM cart
    JOIN listings ON cart.listing_id = listings.id
    JOIN categories ON listings.category_id = categories.id
    WHERE cart.user_id = ?
""", (8882,)).fetchall()

if not cart_items:
    print("[ERROR] No cart items found")
    sys.exit(1)

print(f"Found {len(cart_items)} item(s) in cart")

# Get buyer's address
address = cursor.execute(
    "SELECT street, street_line2, city, state, zip_code FROM addresses WHERE user_id = ? LIMIT 1",
    (8882,)
).fetchone()

shipping_address = f"{address['street']}"
if address['street_line2']:
    shipping_address += f" • {address['street_line2']}"
shipping_address += f" • {address['city']}, {address['state']} {address['zip_code']}"

print(f"Shipping to: {shipping_address}")

# Create order
total_price = sum(item['quantity'] * item['price_per_coin'] for item in cart_items)
cursor.execute("""
    INSERT INTO orders (buyer_id, total_price, shipping_address, status, created_at)
    VALUES (?, ?, ?, 'Pending Shipment', datetime('now'))
""", (8882, total_price, shipping_address))
order_id = cursor.lastrowid
conn.commit()

print(f"Created order ID {order_id}, Total: ${total_price:.2f}")

# Process each item and collect notification data
print("\n[STEP 4] Processing order items...")
notifications_to_send = []
for item in cart_items:
    print(f"\n  Processing listing {item['listing_id']}...")

    # Create order item
    cursor.execute("""
        INSERT INTO order_items (order_id, listing_id, quantity, price_each)
        VALUES (?, ?, ?, ?)
    """, (order_id, item['listing_id'], item['quantity'], item['price_per_coin']))

    # Get current listing quantity
    listing_info = cursor.execute("""
        SELECT quantity, seller_id FROM listings WHERE id = ?
    """, (item['listing_id'],)).fetchone()

    old_quantity = listing_info['quantity']
    new_quantity = old_quantity - item['quantity']

    print(f"  Listing quantity: {old_quantity} -> {new_quantity}")

    # Update listing
    if new_quantity <= 0:
        cursor.execute('UPDATE listings SET quantity = 0, active = 0 WHERE id = ?', (item['listing_id'],))
    else:
        cursor.execute('UPDATE listings SET quantity = ? WHERE id = ?', (new_quantity, item['listing_id']))

    # Collect notification data (will send AFTER commit)
    item_description = f"{item['metal']} {item['product_type']}"
    is_partial = new_quantity > 0

    print(f"  Item description: '{item_description}'")
    print(f"  Is partial: {is_partial}")
    print(f"  Collecting notification data for seller {item['seller_id']}...")

    notifications_to_send.append({
        'seller_id': item['seller_id'],
        'order_id': order_id,
        'listing_id': item['listing_id'],
        'item_description': item_description,
        'quantity_sold': item['quantity'],
        'price_per_unit': item['price_per_coin'],
        'total_amount': item['quantity'] * item['price_per_coin'],
        'shipping_address': shipping_address,
        'is_partial': is_partial,
        'remaining_quantity': new_quantity if is_partial else 0
    })

# Clear cart
cursor.execute('DELETE FROM cart WHERE user_id = ?', (8882,))
conn.commit()

# Send notifications AFTER commit (avoids database locking)
print("\n[STEP 5] Sending notifications...")
from services.notification_service import notify_listing_sold
for notif_data in notifications_to_send:
    print(f"  Calling notify_listing_sold for seller {notif_data['seller_id']}...")
    try:
        result = notify_listing_sold(**notif_data)
        if result:
            print(f"  [OK] notify_listing_sold returned TRUE")
        else:
            print(f"  [FAIL] notify_listing_sold returned FALSE")
    except Exception as e:
        print(f"  [ERROR] EXCEPTION in notify_listing_sold: {e}")
        import traceback
        traceback.print_exc()

print("\n[STEP 6] Checking if notification was created...")
seller_notifs = get_user_notifications(8881)  # Seller should have notification
print(f"Seller (8881) notifications: {len(seller_notifs)}")
for n in seller_notifs:
    print(f"  - {n['type']}: {n['title']}")

if len(seller_notifs) == 0:
    print("  [FAIL] NO NOTIFICATION CREATED FOR SELLER!")
    print("  This is the bug - notification should have been created")
else:
    print("  [OK] Notification created successfully!")

# ===========================================================================
# SCENARIO 2: SELLER ACCEPTS BUYER'S BID
# ===========================================================================

print("\n\n" + "=" * 80)
print("SCENARIO 2: Seller Accepts Buyer's Bid")
print("=" * 80)

print("\n[STEP 1] Buyer creates a bid...")
cursor.execute("""
    INSERT INTO bids (buyer_id, category_id, price_per_coin, quantity_requested, remaining_quantity, status, created_at)
    VALUES (8882, ?, 46.00, 20, 20, 'open', datetime('now'))
""", (category_id,))
bid_id = cursor.lastrowid
conn.commit()
print(f"Created bid ID {bid_id} - Buyer: 8882, Price: $46.00, Qty: 20")

print("\n[STEP 2] Seller has a listing that can fill the bid...")
cursor.execute("""
    INSERT INTO listings (seller_id, category_id, quantity, price_per_coin, active)
    VALUES (8881, ?, 100, 45.00, 1)
""", (category_id,))
listing_id2 = cursor.lastrowid
conn.commit()
print(f"Created listing ID {listing_id2} - Seller: 8881")

print("\n[STEP 3] Simulating bid acceptance...")
print("This simulates what happens when seller clicks 'Accept Bid'")

# Get bid info
bid = cursor.execute("SELECT * FROM bids WHERE id = ?", (bid_id,)).fetchone()
print(f"Bid details: {bid['quantity_requested']} units @ ${bid['price_per_coin']} each")

# Create order for bid
buyer_address = cursor.execute(
    "SELECT street, street_line2, city, state, zip_code FROM addresses WHERE user_id = ? LIMIT 1",
    (bid['buyer_id'],)
).fetchone()

bid_shipping = f"{buyer_address['street']}"
if buyer_address['street_line2']:
    bid_shipping += f" • {buyer_address['street_line2']}"
bid_shipping += f" • {buyer_address['city']}, {buyer_address['state']} {buyer_address['zip_code']}"

cursor.execute("""
    INSERT INTO orders (buyer_id, total_price, shipping_address, status, created_at)
    VALUES (?, ?, ?, 'Pending Shipment', datetime('now'))
""", (bid['buyer_id'], bid['quantity_requested'] * bid['price_per_coin'], bid_shipping))
order_id2 = cursor.lastrowid

# Create order item
cursor.execute("""
    INSERT INTO order_items (order_id, listing_id, quantity, price_each)
    VALUES (?, ?, ?, ?)
""", (order_id2, listing_id2, bid['quantity_requested'], bid['price_per_coin']))

# Update listing
cursor.execute("""
    UPDATE listings SET quantity = quantity - ? WHERE id = ?
""", (bid['quantity_requested'], listing_id2))

# Update bid status
cursor.execute("UPDATE bids SET status = 'filled' WHERE id = ?", (bid_id,))

conn.commit()

print(f"Created order ID {order_id2} for accepted bid")

# THIS IS WHERE THE NOTIFICATION SHOULD BE CREATED
print(f"\n[STEP 4] Calling notify_bid_filled for buyer {bid['buyer_id']}...")

try:
    from services.notification_service import notify_bid_filled

    # Build item description
    item_desc_parts = []
    if category['metal']:
        item_desc_parts.append(category['metal'])
    if category['weight']:
        item_desc_parts.append(category['weight'])
    if category['year']:
        item_desc_parts.append(str(category['year']))
    item_description = ' '.join(item_desc_parts) if item_desc_parts else 'Item'

    print(f"Item description: '{item_description}'")
    print(f"Calling notify_bid_filled()...")

    result = notify_bid_filled(
        buyer_id=bid['buyer_id'],
        order_id=order_id2,
        bid_id=bid_id,
        item_description=item_description,
        quantity_filled=bid['quantity_requested'],
        price_per_unit=bid['price_per_coin'],
        total_amount=bid['quantity_requested'] * bid['price_per_coin'],
        is_partial=False,
        remaining_quantity=0
    )

    if result:
        print(f"[OK] notify_bid_filled returned TRUE")
    else:
        print(f"[FAIL] notify_bid_filled returned FALSE")

except Exception as e:
    print(f"[ERROR] EXCEPTION in notify_bid_filled: {e}")
    import traceback
    traceback.print_exc()

print("\n[STEP 5] Checking if notification was created...")
buyer_notifs = get_user_notifications(8882)  # Buyer should have notification
print(f"Buyer (8882) notifications: {len(buyer_notifs)}")
for n in buyer_notifs:
    print(f"  - {n['type']}: {n['title']}")

if len(buyer_notifs) == 0:
    print("  [FAIL] NO NOTIFICATION CREATED FOR BUYER!")
    print("  This is the bug - notification should have been created")
else:
    print("  [OK] Notification created successfully!")

# ===========================================================================
# FINAL SUMMARY
# ===========================================================================

print("\n" + "=" * 80)
print("FINAL SUMMARY")
print("=" * 80)

all_seller_notifs = get_user_notifications(8881)
all_buyer_notifs = get_user_notifications(8882)

print(f"\nSeller (8881) total notifications: {len(all_seller_notifs)}")
print(f"Buyer (8882) total notifications: {len(all_buyer_notifs)}")

print("\n" + "=" * 80)
if len(all_seller_notifs) > 0 and len(all_buyer_notifs) > 0:
    print("[SUCCESS] Both scenarios created notifications correctly!")
    print("  The notification system is working as expected.")
elif len(all_seller_notifs) > 0:
    print("[PARTIAL] Listing sold notifications work, but bid filled notifications don't")
elif len(all_buyer_notifs) > 0:
    print("[PARTIAL] Bid filled notifications work, but listing sold notifications don't")
else:
    print("[FAILURE] No notifications were created in either scenario")
    print("  This indicates the notification calls are failing or not being reached")
print("=" * 80)

# Cleanup
print("\n[CLEANUP] Removing test data...")
cursor.execute("DELETE FROM notifications WHERE user_id IN (8881, 8882)")
cursor.execute("DELETE FROM order_items WHERE order_id IN (?, ?)", (order_id, order_id2))
cursor.execute("DELETE FROM orders WHERE id IN (?, ?)", (order_id, order_id2))
cursor.execute("DELETE FROM listings WHERE id IN (?, ?)", (listing_id, listing_id2))
cursor.execute("DELETE FROM bids WHERE id = ?", (bid_id,))
cursor.execute("DELETE FROM addresses WHERE user_id IN (8881, 8882)")
cursor.execute("DELETE FROM users WHERE id IN (8881, 8882)")
conn.commit()
conn.close()

print("[OK] Cleanup complete")
print("=" * 80)
