"""
Test success modal data flow
Check if backend returns effective_price and current_spot_price correctly
"""

import requests
import json
from database import get_db_connection
from services.spot_price_service import get_current_spot_prices
from services.pricing_service import get_effective_price

def test_backend_response():
    """Test that backend returns correct data in JSON response"""
    print("\n" + "="*70)
    print("TEST: Backend Response Data")
    print("="*70)

    # Get a real category to test with (prefer simple weights)
    conn = get_db_connection()
    category = conn.execute('''
        SELECT id, metal, weight
        FROM categories
        WHERE metal IS NOT NULL AND weight NOT LIKE '%kilo%' AND weight NOT LIKE '%gram%'
        LIMIT 1
    ''').fetchone()

    if not category:
        # Fall back to any category
        category = conn.execute('''
            SELECT id, metal, weight
            FROM categories
            WHERE metal IS NOT NULL
            LIMIT 1
        ''').fetchone()

    if not category:
        print("\n[FAIL] No categories found in database")
        conn.close()
        return

    category_id = category['id']
    metal = category['metal']
    weight = category['weight']

    print(f"\nUsing category {category_id}: {metal} {weight}")

    # Get a test user
    user = conn.execute('SELECT id FROM users LIMIT 1').fetchone()
    if not user:
        print("\n[FAIL] No users found in database")
        conn.close()
        return

    user_id = user['id']

    # Get current spot prices
    spot_prices = get_current_spot_prices()
    spot_price = spot_prices.get(metal.lower())

    print(f"\nCurrent {metal} spot price: ${spot_price:.2f}/oz")

    # Simulate a variable bid
    test_premium = 200.00
    test_floor = 1000.00
    test_quantity = 5

    print(f"\nTest bid parameters:")
    print(f"   Spot: ${spot_price:.2f}/oz")
    print(f"   Weight: {weight}")
    print(f"   Premium: ${test_premium:.2f}")
    print(f"   Floor: ${test_floor:.2f}")

    # Now check what a real bid would return
    # Insert a test bid
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO bids (
            category_id, buyer_id, quantity_requested, price_per_coin,
            remaining_quantity, active, requires_grading, preferred_grader,
            delivery_address, status,
            pricing_mode, spot_premium, floor_price, pricing_metal
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        category_id, user_id, test_quantity, test_floor,
        test_quantity, 1, 0, None,
        'Test Address', 'open',
        'premium_to_spot', test_premium, test_floor, metal
    ))

    test_bid_id = cursor.lastrowid
    conn.commit()

    print(f"\nCreated test bid ID: {test_bid_id}")

    # Fetch it back like the route does
    created_bid = conn.execute('''
        SELECT b.*, c.metal, c.weight, c.product_type
        FROM bids b
        JOIN categories c ON b.category_id = c.id
        WHERE b.id = ?
    ''', (test_bid_id,)).fetchone()

    bid_dict = dict(created_bid)

    print(f"\nBid dict fields:")
    print(f"   pricing_mode: {bid_dict.get('pricing_mode')}")
    print(f"   pricing_metal: {bid_dict.get('pricing_metal')}")
    print(f"   spot_premium: {bid_dict.get('spot_premium')}")
    print(f"   floor_price: {bid_dict.get('floor_price')}")
    print(f"   metal: {bid_dict.get('metal')}")
    print(f"   weight: {bid_dict.get('weight')}")

    # Calculate effective price
    effective_price = get_effective_price(bid_dict, spot_prices)

    print(f"\nCalculated effective price: ${effective_price:.2f}")

    # Get spot price like the route does
    from services.spot_price_service import get_spot_price
    current_spot_price = get_spot_price(metal)

    print(f"\nSpot price from get_spot_price(): ${current_spot_price:.2f}")

    # Simulate JSON response
    response_data = {
        'success': True,
        'pricing_mode': 'premium_to_spot',
        'effective_price': effective_price,
        'current_spot_price': current_spot_price
    }

    print(f"\nSimulated JSON response:")
    print(json.dumps(response_data, indent=2))

    # Clean up test bid
    cursor.execute('DELETE FROM bids WHERE id = ?', (test_bid_id,))
    conn.commit()
    conn.close()

    print(f"\n[PASS] Backend would return:")
    print(f"   effective_price: {effective_price} (type: {type(effective_price).__name__})")
    print(f"   current_spot_price: {current_spot_price} (type: {type(current_spot_price).__name__})")


def test_javascript_data_extraction():
    """Test JavaScript data extraction pattern"""
    print("\n" + "="*70)
    print("TEST: JavaScript Data Extraction")
    print("="*70)

    # Simulate server response
    server_response = {
        'success': True,
        'pricing_mode': 'premium_to_spot',
        'effective_price': 4422.77,
        'current_spot_price': 4222.77
    }

    print("\nServer response (JSON):")
    print(json.dumps(server_response, indent=2))

    # Simulate JavaScript extraction (Python equivalent)
    bid_data = {
        'quantity': 5,
        'price': 1000.00,
        'pricingMode': 'premium_to_spot',
        'spotPremium': 200.00,
        'floorPrice': 1000.00,
        'effectivePrice': server_response['effective_price'],
        'currentSpotPrice': server_response['current_spot_price']
    }

    print("\nExtracted bidData object:")
    print(json.dumps(bid_data, indent=2))

    print("\nValue checks:")
    print(f"   effectivePrice != null: {bid_data['effectivePrice'] is not None}")
    print(f"   currentSpotPrice != null: {bid_data['currentSpotPrice'] is not None}")
    print(f"   effectivePrice is number: {isinstance(bid_data['effectivePrice'], (int, float))}")
    print(f"   currentSpotPrice is number: {isinstance(bid_data['currentSpotPrice'], (int, float))}")

    # Simulate modal population
    if bid_data['currentSpotPrice'] is not None:
        spot_text = f"${bid_data['currentSpotPrice']:.2f}"
        print(f"\n[PASS] Spot price would show: {spot_text}")
    else:
        print(f"\n[FAIL] Spot price is None, would show: —")

    if bid_data['effectivePrice'] is not None:
        effective_text = f"${bid_data['effectivePrice']:.2f}"
        total = bid_data['effectivePrice'] * bid_data['quantity']
        total_text = f"${total:.2f}"
        print(f"[PASS] Effective price would show: {effective_text}")
        print(f"[PASS] Total would show: {total_text}")
    else:
        print(f"[FAIL] Effective price is None, would show: —")


def main():
    print("\n" + "="*70)
    print("SUCCESS MODAL DATA FLOW - DIAGNOSTIC TEST")
    print("="*70)

    try:
        test_backend_response()
        test_javascript_data_extraction()

        print("\n" + "="*70)
        print("DIAGNOSIS COMPLETE")
        print("="*70)

        print("\n[INFO] If backend test passed but frontend still shows '—':")
        print("   1. Check browser console for warnings")
        print("   2. Check Network tab to see actual server response")
        print("   3. Check if JavaScript is parsing response correctly")
        print("\n[INFO] Debug steps:")
        print("   1. Open DevTools (F12)")
        print("   2. Go to Console tab")
        print("   3. Create a variable bid")
        print("   4. Look for console.log messages showing:")
        print("      - 'Success modal data:'")
        print("      - 'Server response:'")
        print("      - Warning messages about null values")

    except Exception as e:
        print(f"\n[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
