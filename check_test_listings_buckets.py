"""Check bucket IDs and pricing details for test listings"""
from database import get_db_connection

conn = get_db_connection()

print('Test Listings Info:')
for lid in [10130, 10131]:
    row = conn.execute('''
        SELECT l.id, l.pricing_mode, l.price_per_coin, l.spot_premium, l.floor_price, l.pricing_metal,
               c.bucket_id, c.metal, c.weight
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.id = ?
    ''', (lid,)).fetchone()

    if row:
        r = dict(row)
        print(f"\nListing {r['id']} - {r['metal']} {r['weight']}")
        print(f"  Bucket ID: {r['bucket_id']}")
        print(f"  pricing_metal: '{r['pricing_metal']}'")
        print(f"  mode: {r['pricing_mode']}, premium: ${r['spot_premium']}, floor: ${r['price_per_coin']}")

conn.close()
