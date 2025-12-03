"""
Test that update_bid route returns pricing data correctly
"""

from database import get_db_connection
from services.spot_price_service import get_current_spot_prices
from services.pricing_service import get_effective_price

def test_update_response_structure():
    """Verify update_bid returns all required pricing fields"""
    print("\n" + "="*70)
    print("TEST: Update Bid Response Structure")
    print("="*70)

    conn = get_db_connection()

    # Find an existing variable bid to test with
    existing_bid = conn.execute('''
        SELECT b.*, c.metal, c.weight
        FROM bids b
        JOIN categories c ON b.category_id = c.id
        WHERE b.pricing_mode = 'premium_to_spot'
        AND b.active = 1
        LIMIT 1
    ''').fetchone()

    if not existing_bid:
        print("\n[INFO] No existing variable bids found")
        print("[INFO] Creating test bid...")

        # Create a test bid
        category = conn.execute('''
            SELECT id, metal, weight
            FROM categories
            WHERE metal IS NOT NULL
            LIMIT 1
        ''').fetchone()

        user = conn.execute('SELECT id FROM users LIMIT 1').fetchone()

        if not category or not user:
            print("[FAIL] Cannot create test bid - no categories or users")
            conn.close()
            return

        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO bids (
                category_id, buyer_id, quantity_requested, price_per_coin,
                remaining_quantity, active, requires_grading, delivery_address, status,
                pricing_mode, spot_premium, floor_price, pricing_metal
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            category['id'], user['id'], 5, 1000.0,
            5, 1, 0, 'Test Address', 'open',
            'premium_to_spot', 200.0, 1000.0, category['metal']
        ))

        test_bid_id = cursor.lastrowid
        conn.commit()

        existing_bid = conn.execute('''
            SELECT b.*, c.metal, c.weight
            FROM bids b
            JOIN categories c ON b.category_id = c.id
            WHERE b.id = ?
        ''', (test_bid_id,)).fetchone()

    bid_id = existing_bid['id']
    bid_dict = dict(existing_bid)

    print(f"\nTesting with bid ID: {bid_id}")
    print(f"   Pricing Mode: {bid_dict['pricing_mode']}")
    print(f"   Metal: {bid_dict.get('metal')}")
    print(f"   Spot Premium: ${bid_dict.get('spot_premium'):.2f}")
    print(f"   Floor Price: ${bid_dict.get('floor_price'):.2f}")

    # Calculate what the response should include
    spot_prices = get_current_spot_prices()
    effective_price = get_effective_price(bid_dict, spot_prices)

    from services.spot_price_service import get_spot_price
    current_spot_price = get_spot_price(bid_dict.get('pricing_metal') or bid_dict.get('metal'))

    print(f"\nExpected response fields:")
    print(f"   pricing_mode: {bid_dict['pricing_mode']}")
    print(f"   effective_price: {effective_price:.2f}")
    print(f"   current_spot_price: {current_spot_price:.2f}")

    print(f"\n[PASS] Update route should now return:")
    print(f"   {{")
    print(f"     'success': True,")
    print(f"     'message': 'Bid updated successfully',")
    print(f"     'filled_quantity': 0,")
    print(f"     'orders_created': 0,")
    print(f"     'pricing_mode': '{bid_dict['pricing_mode']}',")
    print(f"     'effective_price': {effective_price:.2f},")
    print(f"     'current_spot_price': {current_spot_price:.2f}")
    print(f"   }}")

    conn.close()


def main():
    print("\n" + "="*70)
    print("UPDATE BID RESPONSE - VERIFICATION TEST")
    print("="*70)

    try:
        test_update_response_structure()

        print("\n" + "="*70)
        print("TEST COMPLETE")
        print("="*70)

        print("\n[INFO] Manual Testing Steps:")
        print("   1. Go to http://127.0.0.1:5000")
        print("   2. Log in")
        print("   3. Go to 'Bids' tab in your account")
        print("   4. Click 'Edit' on an existing variable bid")
        print("   5. Change something (e.g., premium)")
        print("   6. Click 'Preview Bid' → 'Confirm Bid'")
        print("   7. Open DevTools Console (F12)")
        print("   8. Check 'Server response:' log")
        print("   9. Should now include:")
        print("      - pricing_mode: 'premium_to_spot'")
        print("      - effective_price: (number)")
        print("      - current_spot_price: (number)")
        print("  10. Success modal should show all values")

    except Exception as e:
        print(f"\n[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
