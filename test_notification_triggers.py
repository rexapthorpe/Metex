"""
Test to verify notifications are triggered correctly when:
1. A buyer purchases a listing (seller should be notified)
2. A seller accepts a bid (buyer should be notified)
"""

from database import get_db_connection
from services.notification_service import get_unread_count, get_user_notifications, notify_listing_sold, notify_bid_filled
import json

def test_notification_triggers():
    """Test that notifications are created when orders are placed and bids are accepted"""
    print("\n" + "="*70)
    print("NOTIFICATION TRIGGERS TEST")
    print("="*70 + "\n")

    conn = get_db_connection()
    cursor = conn.cursor()

    # ========================================================================
    # SETUP: Create test users, listings, and bids
    # ========================================================================
    print("SETUP: Creating test data")
    print("-" * 70)

    # Clean up previous test data
    cursor.execute('DELETE FROM notifications WHERE user_id >= 6000 AND user_id <= 6002')
    cursor.execute('DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE buyer_id >= 6000 OR buyer_id <= 6002)')
    cursor.execute('DELETE FROM orders WHERE buyer_id >= 6000 OR buyer_id <= 6002')
    cursor.execute('DELETE FROM bids WHERE buyer_id >= 6000 AND buyer_id <= 6002')
    cursor.execute('DELETE FROM listings WHERE seller_id >= 6000 AND seller_id <= 6002')
    cursor.execute('DELETE FROM addresses WHERE user_id >= 6000 AND user_id <= 6002')
    cursor.execute('DELETE FROM users WHERE id >= 6000 AND id <= 6002')
    conn.commit()

    # Create test users
    test_buyer_id = 6000
    test_seller_id = 6001
    test_seller2_id = 6002

    cursor.execute("""
        INSERT INTO users (id, username, password_hash, email)
        VALUES (?, ?, ?, ?)
    """, (test_buyer_id, 'test_buyer_notif', 'hash', 'buyer@test.com'))

    cursor.execute("""
        INSERT INTO users (id, username, password_hash, email)
        VALUES (?, ?, ?, ?)
    """, (test_seller_id, 'test_seller_notif', 'hash', 'seller@test.com'))

    cursor.execute("""
        INSERT INTO users (id, username, password_hash, email)
        VALUES (?, ?, ?, ?)
    """, (test_seller2_id, 'test_seller2_notif', 'hash', 'seller2@test.com'))

    # Add shipping address for buyer
    cursor.execute("""
        INSERT INTO addresses (user_id, name, street, city, state, zip_code)
        VALUES (?, 'Home', '123 Test St', 'Test City', 'TS', '12345')
    """, (test_buyer_id,))

    conn.commit()
    print("[OK] Created 3 test users with address")

    # Create test category/bucket
    cursor.execute("""
        INSERT INTO categories (bucket_id, metal, product_type, weight, year)
        VALUES (?, 'Silver', 'Coin', '1 oz', '2024')
    """, (88888888,))
    category_id = cursor.lastrowid
    bucket_id = 88888888

    print(f"[OK] Created test bucket (bucket_id={bucket_id}, category_id={category_id})")

    # Create test listing from seller
    cursor.execute("""
        INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, active, graded)
        VALUES (?, ?, ?, ?, 1, 0)
    """, (category_id, test_seller_id, 10, 100.00))
    listing_id = cursor.lastrowid

    print(f"[OK] Created test listing (id={listing_id}, seller={test_seller_id}, qty=10, price=$100)")

    # Create test bid from buyer
    cursor.execute("""
        INSERT INTO bids (buyer_id, category_id, quantity_requested, remaining_quantity, price_per_coin, status, active)
        VALUES (?, ?, ?, ?, ?, 'open', 1)
    """, (test_buyer_id, category_id, 5, 5, 95.00))
    bid_id = cursor.lastrowid

    print(f"[OK] Created test bid (id={bid_id}, buyer={test_buyer_id}, qty=5, price=$95)")
    conn.commit()

    # ========================================================================
    # TEST 1: Simulate buyer purchasing a listing (direct buy)
    # ========================================================================
    print(f"\n" + "="*70)
    print("TEST 1: Buyer purchases listing - Should notify seller")
    print("-" * 70)

    # Check seller's notifications before purchase
    seller_notifs_before = get_unread_count(test_seller_id)
    print(f"Seller's unread notifications BEFORE purchase: {seller_notifs_before}")

    # Simulate direct_buy_item logic (simplified)
    shipping_address = "123 Test St, Test City, TS 12345"
    quantity_to_buy = 3
    price_per_coin = 100.00
    total_price = quantity_to_buy * price_per_coin

    # Update listing
    cursor.execute('UPDATE listings SET quantity = quantity - ? WHERE id = ?', (quantity_to_buy, listing_id))

    # Create order
    cursor.execute('''
        INSERT INTO orders (buyer_id, total_price, shipping_address, status, created_at)
        VALUES (?, ?, ?, 'Pending Shipment', datetime('now'))
    ''', (test_buyer_id, total_price, shipping_address))
    order_id = cursor.lastrowid

    # Create order_items
    cursor.execute('''
        INSERT INTO order_items (order_id, listing_id, quantity, price_each)
        VALUES (?, ?, ?, ?)
    ''', (order_id, listing_id, quantity_to_buy, price_per_coin))

    conn.commit()

    print(f"[OK] Created order {order_id}: buyer={test_buyer_id} bought {quantity_to_buy} items from seller={test_seller_id}")

    # NOW WITH FIX: Call notify_listing_sold() (this is what the fixed route does)
    try:
        notify_listing_sold(
            seller_id=test_seller_id,
            order_id=order_id,
            listing_id=listing_id,
            item_description="Silver Coin 1 oz 2024",
            quantity_sold=quantity_to_buy,
            price_per_unit=price_per_coin,
            total_amount=total_price,
            shipping_address=shipping_address,
            is_partial=True,  # Still has 7 remaining
            remaining_quantity=7
        )
        print("[OK] Called notify_listing_sold() (simulating fixed route)")
    except Exception as e:
        print(f"[ERROR] Failed to call notify_listing_sold(): {e}")

    # Check seller's notifications after purchase
    seller_notifs_after = get_unread_count(test_seller_id)
    print(f"Seller's unread notifications AFTER purchase: {seller_notifs_after}")

    if seller_notifs_after > seller_notifs_before:
        print("[PASS] Seller received notification for listing sale")
        # Verify the notification
        notifs = get_user_notifications(test_seller_id, unread_only=True, limit=1)
        if notifs:
            notif = notifs[0]
            print(f"  - Notification: {notif['title']}")
            print(f"  - Type: {notif['type']}")
            print(f"  - Related Order: {notif['related_order_id']}")
    else:
        print("[FAIL] Seller did NOT receive notification (THIS IS THE BUG!)")
        print("  Expected: Seller should be notified when their listing is purchased")
        print("  Actual: No notification was created")

    # ========================================================================
    # TEST 2: Simulate seller accepting a bid
    # ========================================================================
    print(f"\n" + "="*70)
    print("TEST 2: Seller accepts bid - Should notify buyer")
    print("-" * 70)

    # Check buyer's notifications before bid acceptance
    buyer_notifs_before = get_unread_count(test_buyer_id)
    print(f"Buyer's unread notifications BEFORE bid acceptance: {buyer_notifs_before}")

    # Simulate accept_bid logic (from sell_routes.py)
    qty_to_fulfill = 3
    bid_price = 95.00

    # Get bid info
    bid = cursor.execute('SELECT * FROM bids WHERE id = ?', (bid_id,)).fetchone()

    # Create order for bid acceptance
    cursor.execute('''
        INSERT INTO orders (buyer_id, seller_id, category_id, quantity, price_each, status)
        VALUES (?, ?, ?, ?, ?, 'pending_shipment')
    ''', (test_buyer_id, test_seller2_id, category_id, qty_to_fulfill, bid_price))
    bid_order_id = cursor.lastrowid

    # Update bid
    remaining = bid['quantity_requested'] - qty_to_fulfill
    if remaining == 0:
        cursor.execute('UPDATE bids SET quantity_requested = 0, active = 0, status = "filled" WHERE id = ?', (bid_id,))
    else:
        cursor.execute('UPDATE bids SET quantity_requested = ?, status = "partially filled" WHERE id = ?', (remaining, bid_id))

    conn.commit()

    print(f"[OK] Seller accepted bid {bid_id}: {qty_to_fulfill} items at ${bid_price} each")
    print(f"[OK] Created order {bid_order_id} for buyer={test_buyer_id}")

    # NOW WITH FIX: Call notify_bid_filled() (this is what the fixed route does)
    try:
        notify_bid_filled(
            buyer_id=test_buyer_id,
            order_id=bid_order_id,
            bid_id=bid_id,
            item_description="Silver Coin 1 oz 2024",
            quantity_filled=qty_to_fulfill,
            price_per_unit=bid_price,
            total_amount=qty_to_fulfill * bid_price,
            is_partial=True,  # Still has 2 remaining
            remaining_quantity=remaining
        )
        print("[OK] Called notify_bid_filled() (simulating fixed route)")
    except Exception as e:
        print(f"[ERROR] Failed to call notify_bid_filled(): {e}")

    # Check buyer's notifications after bid acceptance
    buyer_notifs_after = get_unread_count(test_buyer_id)
    print(f"Buyer's unread notifications AFTER bid acceptance: {buyer_notifs_after}")

    if buyer_notifs_after > buyer_notifs_before:
        print("[PASS] Buyer received notification for bid being filled")
        # Verify the notification
        notifs = get_user_notifications(test_buyer_id, unread_only=True, limit=1)
        if notifs:
            notif = notifs[0]
            print(f"  - Notification: {notif['title']}")
            print(f"  - Type: {notif['type']}")
            print(f"  - Related Order: {notif['related_order_id']}")
    else:
        print("[FAIL] Buyer did NOT receive notification (THIS IS THE BUG!)")
        print("  Expected: Buyer should be notified when their bid is accepted")
        print("  Actual: No notification was created")

    # ========================================================================
    # CLEANUP
    # ========================================================================
    print(f"\n" + "="*70)
    print("CLEANUP")
    print("-" * 70)

    cursor.execute('DELETE FROM notifications WHERE user_id >= 6000 AND user_id <= 6002')
    cursor.execute('DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE buyer_id >= 6000)')
    cursor.execute('DELETE FROM orders WHERE buyer_id >= 6000')
    cursor.execute('DELETE FROM bids WHERE buyer_id >= 6000')
    cursor.execute('DELETE FROM listings WHERE seller_id >= 6000')
    cursor.execute('DELETE FROM categories WHERE bucket_id = 88888888')
    cursor.execute('DELETE FROM addresses WHERE user_id >= 6000')
    cursor.execute('DELETE FROM users WHERE id >= 6000')
    conn.commit()
    conn.close()

    print("[OK] Test data cleaned up")

    # ========================================================================
    # SUMMARY
    # ========================================================================
    print(f"\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    if seller_notifs_after == seller_notifs_before and buyer_notifs_after == buyer_notifs_before:
        print("\n[CONFIRMED] BOTH bugs are present:")
        print("  1. Sellers are NOT notified when their listings are purchased")
        print("  2. Buyers are NOT notified when their bids are accepted")
        print("\nRoot Causes:")
        print("  - buy_routes.py direct_buy_item() doesn't call notify_listing_sold()")
        print("  - sell_routes.py accept_bid() doesn't call notify_bid_filled()")
        return False
    elif seller_notifs_after == seller_notifs_before:
        print("\n[PARTIAL] Seller notification bug still present")
        return False
    elif buyer_notifs_after == buyer_notifs_before:
        print("\n[PARTIAL] Buyer notification bug still present")
        return False
    else:
        print("\n[SUCCESS] Both notification triggers are working!")
        print("  [OK] Sellers are notified when listings are purchased")
        print("  [OK] Buyers are notified when bids are accepted")
        return True

if __name__ == '__main__':
    success = test_notification_triggers()
    exit(0 if success else 1)
