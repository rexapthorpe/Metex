"""Comprehensive diagnostic for silver pricing issue"""
from database import get_db_connection
from services.pricing_service import get_effective_price
from services.spot_price_service import get_current_spot_prices

conn = get_db_connection()
spot_prices = get_current_spot_prices()

print('='*70)
print('SILVER PRICING DIAGNOSTIC')
print('='*70)

print(f'\nCurrent spot prices:')
print(f'  Silver: ${spot_prices.get("silver")}')
print(f'  Gold: ${spot_prices.get("gold")}')

print(f'\n{"="*70}')
print('ALL PREMIUM-TO-SPOT SILVER LISTINGS:')
print('='*70)

rows = conn.execute('''
    SELECT l.id, l.pricing_mode, l.pricing_metal, l.spot_premium, l.floor_price, l.price_per_coin,
           c.metal, c.weight, c.bucket_id
    FROM listings l
    JOIN categories c ON l.category_id = c.id
    WHERE c.metal = 'Silver'
      AND l.pricing_mode = 'premium_to_spot'
      AND l.active = 1
    ORDER BY c.bucket_id
''').fetchall()

print(f'\nFound {len(rows)} Silver premium-to-spot listings\n')

for r in rows:
    rd = dict(r)

    # Calculate effective price
    eff_price = get_effective_price(rd, spot_prices)

    print(f"Listing {rd['id']} (Bucket {rd['bucket_id']}, {rd['weight']} {rd['metal']})")
    print(f"  pricing_metal: {repr(rd['pricing_metal'])}")
    print(f"  spot_premium: ${rd['spot_premium']}")
    print(f"  floor_price: ${rd['floor_price']}")
    print(f"  price_per_coin: ${rd['price_per_coin']}")
    print(f"  EFFECTIVE PRICE: ${eff_price}")

    if eff_price == rd['floor_price']:
        print(f"  [!] Effective price EQUALS floor price")
    elif eff_price == rd['price_per_coin']:
        print(f"  [!] Effective price EQUALS price_per_coin")
    else:
        print(f"  [OK] Effective price is calculated correctly")

    print()

print('='*70)
print('COMPARISON: PREMIUM-TO-SPOT GOLD LISTINGS:')
print('='*70)

rows = conn.execute('''
    SELECT l.id, l.pricing_mode, l.pricing_metal, l.spot_premium, l.floor_price, l.price_per_coin,
           c.metal, c.weight, c.bucket_id
    FROM listings l
    JOIN categories c ON l.category_id = c.id
    WHERE c.metal = 'Gold'
      AND l.pricing_mode = 'premium_to_spot'
      AND l.active = 1
    ORDER BY c.bucket_id
    LIMIT 3
''').fetchall()

print(f'\nShowing first {min(3, len(rows))} Gold premium-to-spot listings\n')

for r in rows:
    rd = dict(r)

    # Calculate effective price
    eff_price = get_effective_price(rd, spot_prices)

    print(f"Listing {rd['id']} (Bucket {rd['bucket_id']}, {rd['weight']} {rd['metal']})")
    print(f"  pricing_metal: {repr(rd['pricing_metal'])}")
    print(f"  spot_premium: ${rd['spot_premium']}")
    print(f"  floor_price: ${rd['floor_price']}")
    print(f"  EFFECTIVE PRICE: ${eff_price}")

    if eff_price == rd['floor_price']:
        print(f"  [!] Effective price EQUALS floor price")
    else:
        print(f"  [OK] Effective price > floor price")

    print()

conn.close()
