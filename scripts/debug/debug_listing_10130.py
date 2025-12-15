"""Deep debug of listing 10130 pricing calculation"""
from database import get_db_connection
from services.spot_price_service import get_current_spot_prices
import re

# Get listing data
conn = get_db_connection()
listing = conn.execute('''
    SELECT l.*, c.metal, c.weight
    FROM listings l
    JOIN categories c ON l.category_id = c.id
    WHERE l.id = 10130
''').fetchone()
conn.close()

ld = dict(listing)
spot_prices = get_current_spot_prices()

print('='*70)
print('DETAILED PRICING CALCULATION FOR LISTING 10130')
print('='*70)

print('\n1. Listing Fields:')
for k in ['id', 'pricing_mode', 'pricing_metal', 'metal', 'weight', 'spot_premium', 'floor_price', 'price_per_coin']:
    print(f'   {k}: {repr(ld.get(k))}')

print('\n2. Spot Prices:')
print(f'   {spot_prices}')

# Manual calculation following get_effective_price logic
print('\n3. Manual Calculation:')

pricing_mode = ld.get('pricing_mode', 'static')
print(f'   pricing_mode: {repr(pricing_mode)}')

if pricing_mode == 'premium_to_spot':
    print('   Mode is premium_to_spot, calculating...')

    # Get pricing metal
    pricing_metal = ld.get('pricing_metal') or ld.get('metal')
    print(f'   pricing_metal resolved to: {repr(pricing_metal)}')

    # Get spot price
    spot_price_per_oz = spot_prices.get(pricing_metal.lower() if pricing_metal else '')
    print(f'   spot_price_per_oz: {spot_price_per_oz}')

    if not spot_price_per_oz:
        print('   ERROR: No spot price found!')
    else:
        # Get weight
        weight = ld.get('weight', 1.0)
        print(f'   weight (raw): {repr(weight)}')

        if isinstance(weight, str):
            match = re.match(r'([0-9.]+)\s*(oz|g|kg|lb)?', weight.strip(), re.IGNORECASE)
            if match:
                weight_value = float(match.group(1))
                weight_unit = match.group(2) or 'oz'
                print(f'   Parsed: weight_value={weight_value}, unit={weight_unit}')

                # Convert to oz if needed
                if weight_unit.lower() == 'oz':
                    weight_oz = weight_value
                else:
                    print(f'   ERROR: Unexpected unit {weight_unit}')
                    weight_oz = weight_value
            else:
                print(f'   ERROR: Could not parse weight')
                weight_oz = 1.0
        else:
            weight_oz = float(weight)

        print(f'   weight_oz: {weight_oz}')

        # Calculate
        spot_premium = ld.get('spot_premium', 0.0)
        print(f'   spot_premium: {spot_premium}')

        computed_price = (spot_price_per_oz * weight_oz) + spot_premium
        print(f'   computed_price: ({spot_price_per_oz} * {weight_oz}) + {spot_premium} = {computed_price}')

        floor_price = ld.get('floor_price', 0.0)
        print(f'   floor_price: {floor_price}')

        effective_price = max(computed_price, floor_price)
        print(f'   effective_price: max({computed_price}, {floor_price}) = {effective_price}')

print('\n4. Calling get_effective_price():')
from services.pricing_service import get_effective_price
result = get_effective_price(ld, spot_prices)
print(f'   Returned: {result}')

if result == effective_price:
    print('\n[OK] Manual calculation matches function result')
else:
    print(f'\n[ERROR] Mismatch! Manual={effective_price}, Function={result}')
