"""Create a test silver premium-to-spot listing to verify pricing"""
from database import get_db_connection
from utils.category_manager import get_or_create_category
from services.pricing_service import get_effective_price

# Create category
cat_spec = {
    'metal': 'Silver',
    'product_line': 'Bullion',
    'product_type': 'Coin',
    'weight': '1 oz',
    'purity': '0.999',
    'mint': 'Test Mint',
    'year': '2024',
    'finish': 'Brilliant Uncirculated',
    'grade': 'Ungraded'
}

conn = get_db_connection()
cat_id = get_or_create_category(conn, cat_spec)

# Create listing with premium-to-spot pricing
# Current silver spot: ~$58.26/oz
# Premium: $5.00
# Floor: $50.00
# Expected effective price: $63.26 (spot + premium)

spot_silver = 58.26
premium = 5.0
floor = 50.0
expected_price = spot_silver + premium

print(f'Creating test Silver listing:')
print(f'  Category ID: {cat_id}')
print(f'  Current silver spot: ${spot_silver}/oz')
print(f'  Premium: ${premium}')
print(f'  Floor: ${floor}')
print(f'  Expected effective price: ${expected_price}')

conn.execute('''
    INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, pricing_mode, spot_premium, floor_price, pricing_metal, active)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
''', (cat_id, 2, 10, floor, 'premium_to_spot', premium, floor, 'Silver', 1))

conn.commit()
listing_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

print(f'  Created listing ID: {listing_id}')

# Verify effective price calculation
listing = conn.execute('''
    SELECT l.*, c.metal, c.weight
    FROM listings l
    JOIN categories c ON l.category_id = c.id
    WHERE l.id = ?
''', (listing_id,)).fetchone()

listing_dict = dict(listing)
calc_price = get_effective_price(listing_dict)

print(f'\nVerification:')
print(f'  Calculated effective price: ${calc_price}')
print(f'  Match expected: {calc_price == expected_price}')

conn.close()
