"""
Test script to verify cart removal functionality
"""
import sqlite3
from database import get_db_connection

def test_cart_data():
    """Display current cart data for debugging"""
    conn = get_db_connection()

    # Get cart items with details
    cart_items = conn.execute('''
        SELECT
            cart.listing_id,
            cart.quantity as cart_qty,
            listings.seller_id,
            listings.category_id,
            listings.price_per_coin,
            listings.quantity as listing_qty,
            users.username as seller_username
        FROM cart
        JOIN listings ON cart.listing_id = listings.id
        JOIN users ON listings.seller_id = users.id
        WHERE cart.user_id = 1
        ORDER BY listings.category_id, listings.price_per_coin
    ''').fetchall()

    print("\n=== Current Cart Items (User ID: 1) ===")
    print(f"{'Listing ID':<12} {'Category':<10} {'Seller ID':<10} {'Seller':<15} {'Cart Qty':<10} {'Price':<10}")
    print("=" * 80)

    for item in cart_items:
        print(f"{item['listing_id']:<12} {item['category_id']:<10} {item['seller_id']:<10} {item['seller_username']:<15} {item['cart_qty']:<10} ${item['price_per_coin']:<9.2f}")

    # Group by category
    print("\n=== Cart Summary by Category ===")
    categories = conn.execute('''
        SELECT
            listings.category_id,
            COUNT(DISTINCT listings.seller_id) as num_sellers,
            SUM(cart.quantity) as total_qty,
            COUNT(DISTINCT cart.listing_id) as num_listings
        FROM cart
        JOIN listings ON cart.listing_id = listings.id
        WHERE cart.user_id = 1
        GROUP BY listings.category_id
    ''').fetchall()

    for cat in categories:
        print(f"Category {cat['category_id']}: {cat['num_sellers']} sellers, {cat['num_listings']} listings, {cat['total_qty']} total items")

    conn.close()

if __name__ == '__main__':
    test_cart_data()
