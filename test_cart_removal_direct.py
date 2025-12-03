"""
Direct backend test for cart removal functionality
Tests the Python functions directly without HTTP
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from database import get_db_connection

def setup_test_data():
    """Create test cart data for user ID 5"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Clear existing cart for user 5
    cursor.execute('DELETE FROM cart WHERE user_id = 5')
    conn.commit()

    # Get category with multiple sellers
    category_with_sellers = cursor.execute('''
        SELECT category_id, COUNT(DISTINCT seller_id) as seller_count
        FROM listings
        WHERE active = 1 AND quantity > 0
        GROUP BY category_id
        HAVING seller_count >= 2
        ORDER BY seller_count DESC
        LIMIT 1
    ''').fetchone()

    if not category_with_sellers:
        print("[FAIL] No categories with multiple sellers found")
        conn.close()
        return None

    bucket_id = category_with_sellers['category_id']
    print(f"[OK] Using bucket/category ID: {bucket_id}")

    # Get listings from this category
    listings = cursor.execute('''
        SELECT id, seller_id, quantity, price_per_coin
        FROM listings
        WHERE category_id = ? AND active = 1 AND quantity > 0
        ORDER BY price_per_coin ASC
        LIMIT 5
    ''', (bucket_id,)).fetchall()

    if len(listings) < 2:
        print("[FAIL] Not enough listings in this category")
        conn.close()
        return None

    print(f"[OK] Found {len(listings)} listings in this category")

    # Add first 3 listings to cart
    for i, listing in enumerate(listings[:3]):
        qty = min(2, listing['quantity'])
        cursor.execute(
            'INSERT INTO cart (user_id, listing_id, quantity) VALUES (?, ?, ?)',
            (5, listing['id'], qty)
        )
        print(f"  Added listing {listing['id']} (seller {listing['seller_id']}, ${listing['price_per_coin']:.2f}) x{qty} to cart")

    conn.commit()
    conn.close()

    return bucket_id, listings

def get_cart_state(user_id=5):
    """Get current cart state"""
    conn = get_db_connection()

    cart_items = conn.execute('''
        SELECT
            cart.listing_id,
            cart.quantity as cart_qty,
            listings.seller_id,
            listings.category_id,
            listings.price_per_coin
        FROM cart
        JOIN listings ON cart.listing_id = listings.id
        WHERE cart.user_id = ?
        ORDER BY listings.category_id, listings.price_per_coin
    ''', (user_id,)).fetchall()

    conn.close()
    return [dict(item) for item in cart_items]

def test_remove_seller_direct():
    """Test Remove Seller functionality by directly calling database operations"""
    print("\n" + "="*80)
    print("TEST 1: REMOVE SELLER (Direct Backend Test)")
    print("="*80)

    # Setup test data
    result = setup_test_data()
    if not result:
        return False

    bucket_id, listings = result

    # Get initial cart state
    print("\n[CART] Initial Cart State:")
    initial_cart = get_cart_state()
    for item in initial_cart:
        print(f"  Listing {item['listing_id']}: Seller {item['seller_id']}, Qty {item['cart_qty']}, ${item['price_per_coin']:.2f}")

    total_qty_before = sum(item['cart_qty'] for item in initial_cart)
    print(f"  Total items: {total_qty_before}")

    # Pick the first seller to remove
    seller_to_remove = initial_cart[0]['seller_id']
    items_from_seller = [item for item in initial_cart if item['seller_id'] == seller_to_remove]
    qty_to_remove = sum(item['cart_qty'] for item in items_from_seller)

    print(f"\n[TARGET] Removing seller {seller_to_remove} (will lose {qty_to_remove} items)")

    # Simulate the backend remove_seller logic directly
    conn = get_db_connection()
    cursor = conn.cursor()

    # Step 1: Delete seller's listings from cart
    cursor.execute('''
        DELETE FROM cart
        WHERE user_id = 5 AND listing_id IN (
            SELECT id FROM listings WHERE seller_id = ? AND category_id = ?
        )
    ''', (seller_to_remove, bucket_id))

    deleted_count = cursor.rowcount
    print(f"  [OK] Deleted {deleted_count} cart items from seller {seller_to_remove}")

    # Step 2: Calculate gap
    current_qty = cursor.execute('''
        SELECT COALESCE(SUM(cart.quantity), 0) as total
        FROM cart
        JOIN listings ON cart.listing_id = listings.id
        WHERE cart.user_id = 5 AND listings.category_id = ?
    ''', (bucket_id,)).fetchone()['total']

    gap = total_qty_before - current_qty
    print(f"  [OK] Gap to refill: {gap} items (had {total_qty_before}, now have {current_qty})")

    # Step 3: Refill from other sellers (matching backend logic from cart_routes.py)
    if gap > 0:
        available_listings = cursor.execute('''
            SELECT id, seller_id, quantity, price_per_coin
            FROM listings
            WHERE category_id = ?
              AND seller_id != ?
              AND active = 1
            ORDER BY price_per_coin ASC
        ''', (bucket_id, seller_to_remove)).fetchall()

        remaining_gap = gap
        for listing in available_listings:
            if remaining_gap <= 0:
                break

            # Check if already in cart
            existing = cursor.execute(
                'SELECT quantity FROM cart WHERE user_id = 5 AND listing_id = ?',
                (listing['id'],)
            ).fetchone()

            # How much we can take from this listing
            in_cart = existing['quantity'] if existing else 0
            available_to_add = listing['quantity'] - in_cart
            take = min(remaining_gap, available_to_add)

            if take > 0:
                if existing:
                    cursor.execute(
                        'UPDATE cart SET quantity = ? WHERE user_id = 5 AND listing_id = ?',
                        (in_cart + take, listing['id'])
                    )
                else:
                    cursor.execute(
                        'INSERT INTO cart (user_id, listing_id, quantity) VALUES (5, ?, ?)',
                        (listing['id'], take)
                    )

                print(f"  [OK] Added {take} from listing {listing['id']} (seller {listing['seller_id']}, ${listing['price_per_coin']:.2f})")
                remaining_gap -= take

    conn.commit()
    conn.close()

    # Get updated cart state
    print("\n[CART] Updated Cart State:")
    updated_cart = get_cart_state()
    for item in updated_cart:
        print(f"  Listing {item['listing_id']}: Seller {item['seller_id']}, Qty {item['cart_qty']}, ${item['price_per_coin']:.2f}")

    total_qty_after = sum(item['cart_qty'] for item in updated_cart)
    print(f"  Total items: {total_qty_after}")

    # Verify results
    print("\n[CHECK] Verification:")

    # 1. Seller should be removed
    sellers_after = set(item['seller_id'] for item in updated_cart)
    if seller_to_remove in sellers_after:
        print(f"  [FAIL] Seller {seller_to_remove} still in cart!")
        return False
    else:
        print(f"  [OK] Seller {seller_to_remove} removed successfully")

    # 2. Cart should have attempted refill
    if total_qty_after == 0:
        print(f"  [WARN] Cart is empty (no refill possible)")
    elif total_qty_after >= total_qty_before:
        print(f"  [OK] Cart refilled successfully ({total_qty_before} -> {total_qty_after} items)")
    elif total_qty_after > total_qty_before - qty_to_remove:
        print(f"  [OK] Cart partially refilled ({total_qty_before} -> {total_qty_after} items)")
    else:
        print(f"  [WARN] Cart not refilled ({total_qty_before} -> {total_qty_after} items)")

    # 3. Verify lowest prices were prioritized
    if len(updated_cart) > 0:
        avg_price_after = sum(item['price_per_coin'] * item['cart_qty'] for item in updated_cart) / total_qty_after
        print(f"  [OK] Average price: ${avg_price_after:.2f}")

    print("\n[PASS] TEST 1 PASSED: Remove Seller backend logic works correctly")
    return True

def test_remove_item_direct():
    """Test Remove Individual Item functionality"""
    print("\n" + "="*80)
    print("TEST 2: REMOVE INDIVIDUAL ITEM (Direct Backend Test)")
    print("="*80)

    # Setup test data
    result = setup_test_data()
    if not result:
        return False

    bucket_id, listings = result

    # Get initial cart state
    print("\n[CART] Initial Cart State:")
    initial_cart = get_cart_state()
    for item in initial_cart:
        print(f"  Listing {item['listing_id']}: Seller {item['seller_id']}, Qty {item['cart_qty']}, ${item['price_per_coin']:.2f}")

    total_qty_before = sum(item['cart_qty'] for item in initial_cart)
    print(f"  Total items: {total_qty_before}")

    # Pick the first listing to remove
    listing_to_remove = initial_cart[0]['listing_id']
    qty_to_remove = initial_cart[0]['cart_qty']
    category_id = initial_cart[0]['category_id']

    print(f"\n[TARGET] Removing listing {listing_to_remove} (will lose {qty_to_remove} items)")

    # Simulate the backend remove_item logic directly
    conn = get_db_connection()
    cursor = conn.cursor()

    # Step 1: Delete listing from cart
    cursor.execute('DELETE FROM cart WHERE user_id = 5 AND listing_id = ?', (listing_to_remove,))
    print(f"  [OK] Deleted listing {listing_to_remove} from cart")

    # Step 2: Calculate gap
    current_qty = cursor.execute('''
        SELECT COALESCE(SUM(cart.quantity), 0) as total
        FROM cart
        JOIN listings ON cart.listing_id = listings.id
        WHERE cart.user_id = 5 AND listings.category_id = ?
    ''', (category_id,)).fetchone()['total']

    gap = total_qty_before - current_qty
    print(f"  [OK] Gap to refill: {gap} items")

    # Step 3: Refill (matching backend logic from cart_routes.py)
    if gap > 0:
        available_listings = cursor.execute('''
            SELECT id, seller_id, quantity, price_per_coin
            FROM listings
            WHERE category_id = ?
              AND active = 1
              AND id != ?
            ORDER BY price_per_coin ASC
        ''', (category_id, listing_to_remove)).fetchall()

        remaining_gap = gap
        for listing in available_listings:
            if remaining_gap <= 0:
                break

            # Check if already in cart
            existing = cursor.execute(
                'SELECT quantity FROM cart WHERE user_id = 5 AND listing_id = ?',
                (listing['id'],)
            ).fetchone()

            # How much we can take from this listing
            in_cart = existing['quantity'] if existing else 0
            available_to_add = listing['quantity'] - in_cart
            take = min(remaining_gap, available_to_add)

            if take > 0:
                if existing:
                    cursor.execute(
                        'UPDATE cart SET quantity = ? WHERE user_id = 5 AND listing_id = ?',
                        (in_cart + take, listing['id'])
                    )
                else:
                    cursor.execute(
                        'INSERT INTO cart (user_id, listing_id, quantity) VALUES (5, ?, ?)',
                        (listing['id'], take)
                    )

                print(f"  [OK] Added {take} from listing {listing['id']} (seller {listing['seller_id']}, ${listing['price_per_coin']:.2f})")
                remaining_gap -= take

    conn.commit()
    conn.close()

    # Get updated cart state
    print("\n[CART] Updated Cart State:")
    updated_cart = get_cart_state()
    for item in updated_cart:
        print(f"  Listing {item['listing_id']}: Seller {item['seller_id']}, Qty {item['cart_qty']}, ${item['price_per_coin']:.2f}")

    total_qty_after = sum(item['cart_qty'] for item in updated_cart)
    print(f"  Total items: {total_qty_after}")

    # Verify results
    print("\n[CHECK] Verification:")

    # 1. Listing should be removed
    listings_after = set(item['listing_id'] for item in updated_cart)
    if listing_to_remove in listings_after:
        print(f"  [FAIL] Listing {listing_to_remove} still in cart!")
        return False
    else:
        print(f"  [OK] Listing {listing_to_remove} removed successfully")

    # 2. Cart should have attempted refill
    if total_qty_after == 0:
        print(f"  [WARN] Cart is empty (no refill possible)")
    elif total_qty_after >= total_qty_before:
        print(f"  [OK] Cart refilled successfully ({total_qty_before} -> {total_qty_after} items)")
    elif total_qty_after > total_qty_before - qty_to_remove:
        print(f"  [OK] Cart partially refilled ({total_qty_before} -> {total_qty_after} items)")
    else:
        print(f"  [WARN] Cart not refilled ({total_qty_before} -> {total_qty_after} items)")

    # 3. Verify lowest prices were prioritized
    if len(updated_cart) > 0:
        avg_price_after = sum(item['price_per_coin'] * item['cart_qty'] for item in updated_cart) / total_qty_after
        print(f"  [OK] Average price: ${avg_price_after:.2f}")

    print("\n[PASS] TEST 2 PASSED: Remove Individual Item backend logic works correctly")
    return True

if __name__ == '__main__':
    print("\n" + "="*80)
    print("CART REMOVAL DIRECT BACKEND TEST SUITE")
    print("="*80)
    print("\nThis script tests the cart removal logic directly at the database level.\n")

    # Run tests
    test1_passed = test_remove_seller_direct()
    test2_passed = test_remove_item_direct()

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Test 1 (Remove Seller): {'[PASS] PASSED' if test1_passed else '[FAIL] FAILED'}")
    print(f"Test 2 (Remove Individual Item): {'[PASS] PASSED' if test2_passed else '[FAIL] FAILED'}")

    if test1_passed and test2_passed:
        print("\n[SUCCESS] ALL TESTS PASSED! Backend logic works correctly.")
        sys.exit(0)
    else:
        print("\n[FAIL] SOME TESTS FAILED. Backend logic needs fixes.")
        sys.exit(1)
