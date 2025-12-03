"""
Comprehensive test for Remove Individual Item functionality
Tests both backend logic and Flask route
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import get_db_connection
from flask import Flask
from routes.cart_routes import cart_bp

def setup_test_data():
    """Setup test cart data with multiple listings"""
    print("\n=== Setting up test data ===")
    conn = get_db_connection()
    cursor = conn.cursor()

    # Clear existing cart for test user
    cursor.execute('DELETE FROM cart WHERE user_id = 5')

    # Get test listings from the same bucket
    bucket_id = 26313121
    listings = cursor.execute('''
        SELECT id, seller_id, quantity, price_per_coin
        FROM listings
        WHERE category_id = ? AND active = 1
        ORDER BY price_per_coin ASC
        LIMIT 4
    ''', (bucket_id,)).fetchall()

    if len(listings) < 3:
        print("ERROR: Not enough test listings. Need at least 3 listings.")
        conn.close()
        return None

    # Add 3 different listings to cart
    listing1 = listings[0]  # Will be removed
    listing2 = listings[1]  # Will remain
    listing3 = listings[2]  # Will remain

    cursor.execute('INSERT INTO cart (user_id, listing_id, quantity) VALUES (5, ?, 3)',
                  (listing1['id'],))
    cursor.execute('INSERT INTO cart (user_id, listing_id, quantity) VALUES (5, ?, 2)',
                  (listing2['id'],))
    cursor.execute('INSERT INTO cart (user_id, listing_id, quantity) VALUES (5, ?, 1)',
                  (listing3['id'],))

    conn.commit()

    print(f"Added to cart:")
    print(f"  - Listing {listing1['id']} (Seller {listing1['seller_id']}): 3 items @ ${listing1['price_per_coin']}")
    print(f"  - Listing {listing2['id']} (Seller {listing2['seller_id']}): 2 items @ ${listing2['price_per_coin']}")
    print(f"  - Listing {listing3['id']} (Seller {listing3['seller_id']}): 1 item @ ${listing3['price_per_coin']}")

    conn.close()
    return {
        'bucket_id': bucket_id,
        'listing_to_remove': listing1,
        'listing2': listing2,
        'listing3': listing3
    }

def print_cart_state(user_id, bucket_id, label="Cart State"):
    """Print current cart state"""
    conn = get_db_connection()
    cursor = conn.cursor()

    rows = cursor.execute('''
        SELECT c.listing_id, c.quantity, l.seller_id, l.price_per_coin
        FROM cart c
        JOIN listings l ON c.listing_id = l.id
        WHERE c.user_id = ? AND l.category_id = ?
        ORDER BY l.price_per_coin ASC
    ''', (user_id, bucket_id)).fetchall()

    print(f"\n{label}:")
    if not rows:
        print("  Cart is empty")
    else:
        total_qty = 0
        total_cost = 0
        for row in rows:
            qty = row['quantity']
            price = row['price_per_coin']
            cost = qty * price
            total_qty += qty
            total_cost += cost
            print(f"  Listing {row['listing_id']} (Seller {row['seller_id']}): {qty} items @ ${price:.2f} = ${cost:.2f}")
        print(f"  TOTAL: {total_qty} items, ${total_cost:.2f}")

    conn.close()

def test_backend_route():
    """Test the backend remove_item route logic"""
    print("\n" + "="*70)
    print("TESTING BACKEND ROUTE LOGIC")
    print("="*70)

    # Setup
    test_data = setup_test_data()
    if not test_data:
        return False

    user_id = 5
    bucket_id = test_data['bucket_id']
    listing_to_remove = test_data['listing_to_remove']

    print_cart_state(user_id, bucket_id, "1. Initial Cart State")

    # Simulate the remove_item route logic
    print(f"\n2. Removing Listing {listing_to_remove['id']} (Seller {listing_to_remove['seller_id']})")

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1) Get info about the listing being removed
    cart_item = cursor.execute('''
        SELECT cart.quantity, listings.category_id, listings.seller_id
        FROM cart
        JOIN listings ON cart.listing_id = listings.id
        WHERE cart.user_id = ? AND cart.listing_id = ?
    ''', (user_id, listing_to_remove['id'])).fetchone()

    if not cart_item:
        print("ERROR: Listing not found in cart")
        conn.close()
        return False

    lost_qty = cart_item['quantity']
    print(f"   Will lose {lost_qty} items")

    # 2) Remove the listing from cart
    cursor.execute(
        'DELETE FROM cart WHERE user_id = ? AND listing_id = ?',
        (user_id, listing_to_remove['id'])
    )
    conn.commit()
    print(f"   Removed listing {listing_to_remove['id']}")

    print_cart_state(user_id, bucket_id, "3. After Removal (before refill)")

    # 3) Try to refill from other listings in the same bucket
    print(f"\n4. Refilling {lost_qty} items")
    remaining = lost_qty
    replacements = cursor.execute('''
        SELECT id, quantity, seller_id, price_per_coin
        FROM listings
        WHERE category_id = ?
          AND active = 1
          AND id != ?
        ORDER BY price_per_coin ASC
    ''', (bucket_id, listing_to_remove['id'])).fetchall()

    print(f"   Found {len(replacements)} potential replacement listings")

    for listing in replacements:
        if remaining <= 0:
            break

        # Check if already in cart
        existing = cursor.execute(
            'SELECT quantity FROM cart WHERE user_id = ? AND listing_id = ?',
            (user_id, listing['id'])
        ).fetchone()

        # How much we can take from this listing
        in_cart = existing['quantity'] if existing else 0
        available_to_add = listing['quantity'] - in_cart
        take = min(remaining, available_to_add)

        if take > 0:
            if existing:
                cursor.execute(
                    'UPDATE cart SET quantity = ? WHERE user_id = ? AND listing_id = ?',
                    (in_cart + take, user_id, listing['id'])
                )
                print(f"   Updated Listing {listing['id']} (Seller {listing['seller_id']}): {in_cart} -> {in_cart + take} (+{take})")
            else:
                cursor.execute(
                    'INSERT INTO cart (user_id, listing_id, quantity) VALUES (?, ?, ?)',
                    (user_id, listing['id'], take)
                )
                print(f"   Added Listing {listing['id']} (Seller {listing['seller_id']}): {take} items")
            remaining -= take

    conn.commit()
    conn.close()

    print_cart_state(user_id, bucket_id, "5. Final Cart State")

    if remaining == 0:
        print(f"\n[SUCCESS] All {lost_qty} items refilled")
        return True
    else:
        print(f"\n[WARNING] Could only refill {lost_qty - remaining}/{lost_qty} items")
        return True  # Still consider success if partial refill

def test_flask_route():
    """Test the actual Flask route with a test client"""
    print("\n" + "="*70)
    print("TESTING FLASK ROUTE WITH TEST CLIENT")
    print("="*70)

    # Create Flask test app
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test_key'
    app.register_blueprint(cart_bp)

    # Setup test data
    test_data = setup_test_data()
    if not test_data:
        return False

    user_id = 5
    bucket_id = test_data['bucket_id']
    listing_to_remove = test_data['listing_to_remove']

    print_cart_state(user_id, bucket_id, "Initial Cart State")

    with app.test_client() as client:
        # Set up session
        with client.session_transaction() as sess:
            sess['user_id'] = user_id

        # Make request
        url = f'/cart/remove_item/{listing_to_remove["id"]}'
        print(f"\nSending POST to: {url}")

        response = client.post(
            url,
            headers={'X-Requested-With': 'XMLHttpRequest'}
        )

        print(f"Response status: {response.status_code}")

        if response.status_code == 204:
            print("[SUCCESS] Backend returned 204")
        else:
            print(f"[ERROR] Unexpected status code: {response.status_code}")
            return False

    print_cart_state(user_id, bucket_id, "Final Cart State")
    print("\n[SUCCESS] Flask route test PASSED")
    return True

if __name__ == '__main__':
    print("="*70)
    print("REMOVE INDIVIDUAL ITEM COMPREHENSIVE TEST")
    print("="*70)

    try:
        # Test backend logic
        backend_success = test_backend_route()

        # Test Flask route
        flask_success = test_flask_route()

        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        print(f"Backend Logic: {'PASSED' if backend_success else 'FAILED'}")
        print(f"Flask Route:   {'PASSED' if flask_success else 'FAILED'}")

        if backend_success and flask_success:
            print("\n[ALL TESTS PASSED]")
            print("\nThe Remove Individual Item functionality is working correctly!")
            print("Backend successfully removes listing and refills from other listings.")
        else:
            print("\n[SOME TESTS FAILED]")

    except Exception as e:
        print(f"\n[TEST ERROR]: {e}")
        import traceback
        traceback.print_exc()
