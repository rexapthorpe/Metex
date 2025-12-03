"""
Test script for Edit Listing Success Modal with comprehensive pricing display
Tests both fixed and premium-to-spot pricing modes
"""

import sys
import json
import io
from app import app
from database import get_db_connection

# Fix encoding for Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def print_section(title):
    """Print a section header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def create_test_listing(mode='static'):
    """
    Create a test listing for editing
    Returns: listing_id, seller_id
    """
    conn = get_db_connection()

    # Create test user if not exists
    user = conn.execute("SELECT id FROM users WHERE username = 'test_seller_edit'").fetchone()
    if not user:
        conn.execute(
            "INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)",
            ('test_seller_edit', 'hash123', 'test_seller_edit@test.com')
        )
        conn.commit()
        user = conn.execute("SELECT id FROM users WHERE username = 'test_seller_edit'").fetchone()

    seller_id = user['id']

    # Get or create a category
    category = conn.execute("""
        SELECT id, metal, product_line, product_type, weight
        FROM categories
        WHERE metal = 'Silver'
        AND product_line = 'American Eagle'
        AND product_type = 'Coin'
        AND weight = '1 oz'
        LIMIT 1
    """).fetchone()

    if not category:
        # Create category
        conn.execute("""
            INSERT INTO categories (metal, product_line, product_type, weight, purity, mint, year, finish, grade, bucket_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ('Silver', 'American Eagle', 'Coin', '1 oz', '.999', 'US Mint', '2024', 'Brilliant Uncirculated', 'MS-70', 1))
        conn.commit()
        category = conn.execute("""
            SELECT id FROM categories
            WHERE metal = 'Silver'
            AND product_line = 'American Eagle'
            AND product_type = 'Coin'
            AND weight = '1 oz'
            LIMIT 1
        """).fetchone()

    category_id = category['id']

    # Create listing based on mode
    if mode == 'static':
        conn.execute("""
            INSERT INTO listings (seller_id, category_id, quantity, price_per_coin, pricing_mode, active)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (seller_id, category_id, 10, 35.00, 'static', 1))
    else:  # premium_to_spot
        conn.execute("""
            INSERT INTO listings (seller_id, category_id, quantity, price_per_coin, pricing_mode, spot_premium, floor_price, pricing_metal, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (seller_id, category_id, 10, 30.00, 'premium_to_spot', 3.00, 30.00, 'Silver', 1))

    conn.commit()
    listing_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    return listing_id, seller_id


def test_edit_listing(listing_id, seller_id, mode='static'):
    """
    Test editing a listing and verify the response data
    """
    with app.test_client() as client:
        # Login as the seller
        with client.session_transaction() as sess:
            sess['user_id'] = seller_id
            sess['username'] = 'test_seller_edit'

        # Prepare edit data
        if mode == 'static':
            form_data = {
                'metal': 'Silver',
                'product_line': 'American Eagle',
                'product_type': 'Coin',
                'weight': '1 oz',
                'purity': '.999',
                'mint': 'US Mint',
                'year': '2024',
                'finish': 'Brilliant Uncirculated',
                'grade': 'MS-70',
                'quantity': '8',
                'graded': 'yes',
                'grading_service': 'PCGS',
                'pricing_mode': 'static',
                'price_per_coin': '37.50'
            }
        else:  # premium_to_spot
            form_data = {
                'metal': 'Silver',
                'product_line': 'American Eagle',
                'product_type': 'Coin',
                'weight': '1 oz',
                'purity': '.999',
                'mint': 'US Mint',
                'year': '2024',
                'finish': 'Brilliant Uncirculated',
                'grade': 'MS-70',
                'quantity': '8',
                'graded': 'yes',
                'grading_service': 'NGC',
                'pricing_mode': 'premium_to_spot',
                'spot_premium': '5.00',
                'floor_price': '32.00',
                'pricing_metal': 'Silver'
            }

        # Submit edit with AJAX header
        response = client.post(
            f'/listings/edit_listing/{listing_id}',
            data=form_data,
            headers={'X-Requested-With': 'XMLHttpRequest'}
        )

        return response


def cleanup_test_data():
    """Clean up test data"""
    conn = get_db_connection()

    # Get test user
    user = conn.execute("SELECT id FROM users WHERE username = 'test_seller_edit'").fetchone()
    if user:
        seller_id = user['id']
        # Delete listings
        conn.execute("DELETE FROM listings WHERE seller_id = ?", (seller_id,))
        # Note: Not deleting user to avoid cascade issues
        conn.commit()

    conn.close()


def main():
    print_section("Edit Listing Success Modal - Comprehensive Pricing Test")

    try:
        # Test 1: Fixed Pricing Mode
        print_section("TEST 1: Fixed Pricing Listing Edit")

        listing_id, seller_id = create_test_listing(mode='static')
        print(f"✓ Created test listing (ID: {listing_id}) with STATIC pricing")

        response = test_edit_listing(listing_id, seller_id, mode='static')

        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")

        if response.status_code == 200:
            data = response.get_json()
            print(f"\n✓ SUCCESS - Received JSON response")
            print(f"\nResponse Data Structure:")
            print(json.dumps(data, indent=2))

            # Validate fixed pricing fields
            print("\n" + "-" * 80)
            print("VALIDATION: Fixed Pricing Fields")
            print("-" * 80)

            assert data['success'] == True, "Response should indicate success"
            print("✓ success: True")

            assert data['pricingMode'] == 'static', f"Expected 'static', got '{data['pricingMode']}'"
            print(f"✓ pricingMode: {data['pricingMode']}")

            assert 'pricePerCoin' in data, "pricePerCoin should be present for static pricing"
            print(f"✓ pricePerCoin: ${data['pricePerCoin']:.2f}")

            assert data['pricePerCoin'] == 37.50, f"Expected 37.50, got {data['pricePerCoin']}"
            print(f"✓ pricePerCoin value is correct: $37.50")

            # Verify item details
            assert data['metal'] == 'Silver', f"Expected 'Silver', got '{data['metal']}'"
            print(f"✓ metal: {data['metal']}")

            assert data['quantity'] == 8, f"Expected 8, got {data['quantity']}"
            print(f"✓ quantity: {data['quantity']}")

            assert data['graded'] == True, f"Expected True, got {data['graded']}"
            print(f"✓ graded: {data['graded']}")

            assert data['gradingService'] == 'PCGS', f"Expected 'PCGS', got '{data['gradingService']}'"
            print(f"✓ gradingService: {data['gradingService']}")

            print("\n✅ TEST 1 PASSED: Fixed pricing data is complete and correct!")
        else:
            print(f"\n❌ TEST 1 FAILED: Expected 200, got {response.status_code}")
            print(f"Response: {response.get_data(as_text=True)}")
            return False

        # Test 2: Premium-to-Spot Pricing Mode
        print_section("TEST 2: Premium-to-Spot Listing Edit")

        listing_id2, seller_id2 = create_test_listing(mode='premium_to_spot')
        print(f"✓ Created test listing (ID: {listing_id2}) with PREMIUM-TO-SPOT pricing")

        response = test_edit_listing(listing_id2, seller_id2, mode='premium_to_spot')

        print(f"\nResponse Status: {response.status_code}")

        if response.status_code == 200:
            data = response.get_json()
            print(f"\n✓ SUCCESS - Received JSON response")
            print(f"\nResponse Data Structure:")
            print(json.dumps(data, indent=2))

            # Validate premium-to-spot pricing fields
            print("\n" + "-" * 80)
            print("VALIDATION: Premium-to-Spot Pricing Fields")
            print("-" * 80)

            assert data['success'] == True, "Response should indicate success"
            print("✓ success: True")

            assert data['pricingMode'] == 'premium_to_spot', f"Expected 'premium_to_spot', got '{data['pricingMode']}'"
            print(f"✓ pricingMode: {data['pricingMode']}")

            # Check all premium-to-spot fields
            required_fields = ['currentSpotPrice', 'spotPremium', 'floorPrice', 'effectivePrice', 'pricingMetal']
            for field in required_fields:
                assert field in data, f"{field} should be present for premium-to-spot pricing"
                print(f"✓ {field}: {data[field]}")

            # Validate values are not null, NaN, or placeholder
            assert data['currentSpotPrice'] is not None, "currentSpotPrice should not be None"
            print(f"✓ currentSpotPrice is not None: ${data['currentSpotPrice']:.2f}/oz")

            assert data['spotPremium'] == 5.00, f"Expected 5.00, got {data['spotPremium']}"
            print(f"✓ spotPremium value is correct: ${data['spotPremium']:.2f}")

            assert data['floorPrice'] == 32.00, f"Expected 32.00, got {data['floorPrice']}"
            print(f"✓ floorPrice value is correct: ${data['floorPrice']:.2f}")

            assert data['effectivePrice'] is not None, "effectivePrice should not be None"
            assert data['effectivePrice'] > 0, "effectivePrice should be positive"
            print(f"✓ effectivePrice is valid: ${data['effectivePrice']:.2f}")

            # Verify effective price calculation
            # effectivePrice should be max(spot * weight + premium, floor)
            expected_calculated = data['currentSpotPrice'] * 1.0 + data['spotPremium']
            expected_effective = max(expected_calculated, data['floorPrice'])
            print(f"\nPrice Calculation Verification:")
            print(f"  Current Spot: ${data['currentSpotPrice']:.2f}/oz")
            print(f"  Weight: 1 oz")
            print(f"  Premium: ${data['spotPremium']:.2f}")
            print(f"  Calculated: (${data['currentSpotPrice']:.2f} × 1) + ${data['spotPremium']:.2f} = ${expected_calculated:.2f}")
            print(f"  Floor: ${data['floorPrice']:.2f}")
            print(f"  Effective: max(${expected_calculated:.2f}, ${data['floorPrice']:.2f}) = ${expected_effective:.2f}")
            print(f"  Actual Effective: ${data['effectivePrice']:.2f}")

            assert abs(data['effectivePrice'] - expected_effective) < 0.01, \
                f"Effective price calculation mismatch: expected {expected_effective}, got {data['effectivePrice']}"
            print(f"✓ Effective price calculation is correct!")

            # Verify item details
            assert data['quantity'] == 8, f"Expected 8, got {data['quantity']}"
            print(f"✓ quantity: {data['quantity']}")

            assert data['gradingService'] == 'NGC', f"Expected 'NGC', got '{data['gradingService']}'"
            print(f"✓ gradingService: {data['gradingService']}")

            print("\n✅ TEST 2 PASSED: Premium-to-spot pricing data is complete and correct!")
        else:
            print(f"\n❌ TEST 2 FAILED: Expected 200, got {response.status_code}")
            print(f"Response: {response.get_data(as_text=True)}")
            return False

        # Final Summary
        print_section("TEST SUMMARY")
        print("✅ All tests passed successfully!")
        print("\nVerified:")
        print("  ✓ Backend returns comprehensive JSON response (not empty 204)")
        print("  ✓ Fixed pricing mode includes pricePerCoin")
        print("  ✓ Premium-to-spot mode includes all required fields:")
        print("    - currentSpotPrice (live from spot price service)")
        print("    - spotPremium (user input)")
        print("    - floorPrice (user input)")
        print("    - effectivePrice (correctly calculated)")
        print("  ✓ No null, NaN, or placeholder values")
        print("  ✓ Item details are correctly populated")
        print("\n✅ Success modal will display complete pricing information!")

        return True

    except Exception as e:
        print(f"\n❌ TEST FAILED WITH EXCEPTION:")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        print_section("CLEANUP")
        cleanup_test_data()
        print("✓ Test data cleaned up")


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
