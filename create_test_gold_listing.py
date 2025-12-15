"""Create a test gold premium-to-spot listing for comparison"""
from database import get_db_connection
from utils.category_manager import get_or_create_category
from services.pricing_service import get_effective_price

# Create category
cat_spec = {
    'metal': 'Gold',
    'product_line': 'Bullion',
    'product_type': 'Coin',
    'weight': '1 oz',
    'purity': '0.9999',
    'mint': 'Test Mint',
    'year': '2024',
    'finish': 'Brilliant Uncirculated',
    'grade': 'Ungraded'
}

conn = get_db_connection()
cat_id = get_or_create_category(conn, cat_spec)

# Create listing with premium-to-spot pricing
# Current gold spot: ~$4216.58/oz
# Premium: $100.00
# Floor: $4000.00
# Expected effective price: $4316.58 (spot + premium)

spot_gold = 4216.58
premium = 100.0
floor = 4000.0
expected_price = spot_gold + premium

print(f'Creating test Gold listing:')
print(f'  Category ID: {cat_id}')
print(f'  Current gold spot: ${spot_gold}/oz')
print(f'  Premium: ${premium}')
print(f'  Floor: ${floor}')
print(f'  Expected effective price: ${expected_price}')

conn.execute('''
    INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, pricing_mode, spot_premium, floor_price, pricing_metal, active)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
''', (cat_id, 2, 10, floor, 'premium_to_spot', premium, floor, 'Gold', 1))

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
