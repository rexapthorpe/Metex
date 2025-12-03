"""
Seed script to create test data for cart removal functionality testing
Creates multiple sellers with listings in the same category
"""
from database import get_db_connection
import random

def seed_test_data():
    conn = get_db_connection()
    cursor = conn.cursor()

    # First, let's find or create a category
    # Check if we have any category
    existing_category = cursor.execute('''
        SELECT id FROM categories LIMIT 1
    ''').fetchone()

    if existing_category:
        category_id = existing_category['id']
        print(f"[OK] Using existing category ID: {category_id}")
    else:
        # Create a test category - 2024 1oz Silver American Eagle
        cursor.execute('''
            INSERT INTO categories (metal, product_type, weight, mint, year, finish, grade, coin_series, purity, product_line)
            VALUES ('Silver', 'Coin', '1 oz', 'US Mint', 2024, 'Brilliant Uncirculated', 'Ungraded', 'American Eagle', '.999', 'Bullion')
        ''')
        category_id = cursor.lastrowid
        print(f"[OK] Created new category ID: {category_id}")
        conn.commit()

    # Create 3 test sellers if they don't exist (IDs 10, 11, 12)
    test_sellers = []
    for i in range(10, 13):
        seller = cursor.execute('SELECT id FROM users WHERE id = ?', (i,)).fetchone()
        if not seller:
            cursor.execute('''
                INSERT INTO users (id, username, email, password_hash, first_name, last_name)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (i, f'testseller{i}', f'seller{i}@test.com', 'dummy_hash', f'Seller{i}', f'Test{i}'))
            print(f"[OK] Created test seller user ID: {i}")
        test_sellers.append(i)

    conn.commit()

    # Clear existing listings for this category to start fresh
    cursor.execute('DELETE FROM listings WHERE category_id = ?', (category_id,))
    print(f"[OK] Cleared old listings for category {category_id}")
    conn.commit()

    # Create listings from each seller with different prices
    base_price = 30.00
    for idx, seller_id in enumerate(test_sellers):
        price = base_price + (idx * 2.50)  # $30.00, $32.50, $35.00
        qty = 10

        cursor.execute('''
            INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, graded, active)
            VALUES (?, ?, ?, ?, 0, 1)
        ''', (category_id, seller_id, qty, price))

        listing_id = cursor.lastrowid
        print(f"[OK] Created listing {listing_id}: Seller {seller_id}, ${price:.2f}/coin, {qty} available")

    conn.commit()

    # Verify the data
    print("\n[CHECK] Verification:")
    listings = cursor.execute('''
        SELECT id, seller_id, quantity, price_per_coin
        FROM listings
        WHERE category_id = ? AND active = 1
        ORDER BY price_per_coin ASC
    ''', (category_id,)).fetchall()

    print(f"  Category {category_id} now has {len(listings)} listings:")
    for listing in listings:
        print(f"    Listing {listing['id']}: Seller {listing['seller_id']}, ${listing['price_per_coin']:.2f}, Qty {listing['quantity']}")

    conn.close()
    return category_id

if __name__ == '__main__':
    print("="*80)
    print("CART TEST DATA SEED SCRIPT")
    print("="*80)
    print()
    category_id = seed_test_data()
    print()
    print(f"[SUCCESS] Test data created! Category ID: {category_id}")
    print("You can now run the cart removal tests.")
