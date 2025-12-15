"""Test what the buy route would return for test listings"""
from database import get_db_connection
from services.pricing_service import get_effective_price

conn = get_db_connection()

print('Testing Buy route pricing calculation:')
print()

for listing_id in [10130, 10131]:
    listing = conn.execute('''
        SELECT l.*, c.metal, c.weight
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.id = ?
    ''', (listing_id,)).fetchone()

    if listing:
        ld = dict(listing)
        eff = get_effective_price(ld)

        print(f'Listing {listing_id} ({ld["metal"]} {ld["weight"]}):')
        print(f'  price_per_coin (floor): ${ld["price_per_coin"]}')
        print(f'  pricing_mode: {ld["pricing_mode"]}')
        print(f'  spot_premium: ${ld["spot_premium"]}')
        print(f'  effective_price: ${eff}')
        print()

conn.close()
