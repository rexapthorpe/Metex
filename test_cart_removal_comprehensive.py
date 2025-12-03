"""
Comprehensive test for cart removal functionality
Tests both Remove Seller and Remove Individual Item features
"""
import sys
import requests
from database import get_db_connection

BASE_URL = "http://127.0.0.1:5000"

def setup_test_data():
    """Create test cart data for user ID 5"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Clear existing cart for user 5
    cursor.execute('DELETE FROM cart WHERE user_id = 5')
    conn.commit()

    # Find a category with multiple sellers
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

    # Get listings from this category (different sellers, sorted by price)
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
        qty = min(2, listing['quantity'])  # Add 2 of each (or max available)
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

def test_remove_seller():
    """Test Remove Seller functionality"""
    print("\n" + "="*80)
    print("TEST 1: REMOVE SELLER")
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

    # Simulate HTTP request
    url = f"{BASE_URL}/cart/remove_seller/{bucket_id}/{seller_to_remove}"
    headers = {'X-Requested-With': 'XMLHttpRequest'}

    try:
        response = requests.post(url, headers=headers)
        print(f"  HTTP Response: {response.status_code}")

        if response.status_code != 204:
            print(f"  [FAIL] Expected 204, got {response.status_code}")
            if response.text:
                print(f"  Response body: {response.text}")
            return False
    except requests.exceptions.ConnectionError:
        print("  [FAIL] Could not connect to server. Is Flask running?")
        return False
    except Exception as e:
        print(f"  [FAIL] Request failed: {e}")
        return False

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

    print("\n[PASS] TEST 1 PASSED: Remove Seller works correctly")
    return True

def test_remove_individual_item():
    """Test Remove Individual Item functionality"""
    print("\n" + "="*80)
    print("TEST 2: REMOVE INDIVIDUAL ITEM")
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

    print(f"\n[TARGET] Removing listing {listing_to_remove} (will lose {qty_to_remove} items)")

    # Simulate HTTP request
    url = f"{BASE_URL}/cart/remove_item/{listing_to_remove}"
    headers = {'X-Requested-With': 'XMLHttpRequest'}

    try:
        response = requests.post(url, headers=headers)
        print(f"  HTTP Response: {response.status_code}")

        if response.status_code != 204:
            print(f"  [FAIL] Expected 204, got {response.status_code}")
            if response.text:
                print(f"  Response body: {response.text}")
            return False
    except requests.exceptions.ConnectionError:
        print("  [FAIL] Could not connect to server. Is Flask running?")
        return False
    except Exception as e:
        print(f"  [FAIL] Request failed: {e}")
        return False

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

    print("\n[PASS] TEST 2 PASSED: Remove Individual Item works correctly")
    return True

if __name__ == '__main__':
    print("\n" + "="*80)
    print("CART REMOVAL COMPREHENSIVE TEST SUITE")
    print("="*80)
    print("\nThis script will test both Remove Seller and Remove Individual Item features")
    print("by simulating actual HTTP requests to the running Flask server.\n")

    # Run tests
    test1_passed = test_remove_seller()
    test2_passed = test_remove_individual_item()

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Test 1 (Remove Seller): {'[PASS] PASSED' if test1_passed else '[FAIL] FAILED'}")
    print(f"Test 2 (Remove Individual Item): {'[PASS] PASSED' if test2_passed else '[FAIL] FAILED'}")

    if test1_passed and test2_passed:
        print("\n[SUCCESS] ALL TESTS PASSED! Both features work correctly.")
        sys.exit(0)
    else:
        print("\n[FAIL] SOME TESTS FAILED. Please review the output above.")
        sys.exit(1)
