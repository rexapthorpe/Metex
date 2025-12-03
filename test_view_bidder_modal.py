"""
Test script for View Bidder modal on Bucket ID page
Tests API endpoint, modal rendering, and integration
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


def create_test_data():
    """
    Create test data: user (bidder), category, bucket, and bid
    Returns: bid_id, bidder_username
    """
    conn = get_db_connection()

    # Create test bidder user
    bidder = conn.execute("SELECT id FROM users WHERE username = 'test_bidder_view'").fetchone()
    if not bidder:
        conn.execute(
            "INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)",
            ('test_bidder_view', 'hash123', 'test_bidder_view@test.com')
        )
        conn.commit()
        bidder = conn.execute("SELECT id FROM users WHERE username = 'test_bidder_view'").fetchone()

    bidder_id = bidder['id']

    # Get or create a category
    category = conn.execute("""
        SELECT id, bucket_id
        FROM categories
        WHERE metal = 'Gold'
        AND product_type = 'Coin'
        AND weight = '1 oz'
        LIMIT 1
    """).fetchone()

    if not category:
        # Create category
        conn.execute("""
            INSERT INTO categories (metal, product_line, product_type, weight, purity, mint, year, finish, grade, bucket_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ('Gold', 'American Eagle', 'Coin', '1 oz', '.9999', 'US Mint', '2024', 'Brilliant Uncirculated', 'MS-70', 1))
        conn.commit()
        category = conn.execute("""
            SELECT id, bucket_id
            FROM categories
            WHERE metal = 'Gold'
            AND product_type = 'Coin'
            AND weight = '1 oz'
            LIMIT 1
        """).fetchone()

    bucket_id = category['bucket_id']

    # Create a test bid (no bucket_id field in bids table)
    conn.execute("""
        INSERT INTO bids (
            buyer_id,
            category_id,
            quantity_requested,
            remaining_quantity,
            price_per_coin,
            pricing_mode,
            requires_grading,
            delivery_address,
            status,
            active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        bidder_id,
        category['id'],
        10,
        10,
        2000.00,
        'static',
        0,
        '123 Test St',
        'open',
        1
    ))
    conn.commit()

    bid_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Add some ratings for the bidder to test rating display
    # (ratee_id is the person being rated - in this case, the bidder as a seller)
    conn.execute("""
        INSERT OR IGNORE INTO ratings (order_id, rater_id, ratee_id, rating, comment, timestamp)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
    """, (999999, 999998, bidder_id, 5, 'Great seller!'))
    conn.commit()

    conn.close()

    return bid_id, 'test_bidder_view', bucket_id


def cleanup_test_data():
    """Clean up test data"""
    conn = get_db_connection()

    # Get test user
    user = conn.execute("SELECT id FROM users WHERE username = 'test_bidder_view'").fetchone()
    if user:
        bidder_id = user['id']
        # Delete bids
        conn.execute("DELETE FROM bids WHERE buyer_id = ?", (bidder_id,))
        # Delete ratings (ratee_id is who was rated, rater_id is who did the rating)
        conn.execute("DELETE FROM ratings WHERE ratee_id = ? OR rater_id = 999998", (bidder_id,))
        conn.commit()

    conn.close()


def test_api_endpoint(bid_id, expected_username):
    """
    Test the /bids/api/bid/<bid_id>/bidder_info endpoint
    """
    print_section("TEST 1: API Endpoint - /bids/api/bid/<bid_id>/bidder_info")

    with app.test_client() as client:
        response = client.get(f'/bids/api/bid/{bid_id}/bidder_info')

        print(f"\nResponse Status: {response.status_code}")

        if response.status_code == 200:
            data = response.get_json()
            print(f"\n✓ SUCCESS - Received JSON response")
            print(f"\nResponse Data:")
            print(json.dumps(data, indent=2))

            # Validate response structure
            print("\n" + "-" * 80)
            print("VALIDATION: Response Structure")
            print("-" * 80)

            required_fields = ['buyer_id', 'username', 'rating', 'num_reviews', 'quantity']
            for field in required_fields:
                assert field in data, f"{field} should be present in response"
                print(f"✓ {field}: {data[field]}")

            # Validate values
            assert data['username'] == expected_username, f"Expected username '{expected_username}', got '{data['username']}'"
            print(f"\n✓ Username matches: {data['username']}")

            assert data['quantity'] == 10, f"Expected quantity 10, got {data['quantity']}"
            print(f"✓ Quantity is correct: {data['quantity']}")

            assert isinstance(data['rating'], (int, float)), "Rating should be numeric"
            print(f"✓ Rating is numeric: {data['rating']}")

            assert isinstance(data['num_reviews'], int), "num_reviews should be integer"
            print(f"✓ num_reviews is integer: {data['num_reviews']}")

            print("\n✅ TEST 1 PASSED: API endpoint returns correct bidder data!")
            return True
        else:
            print(f"\n❌ TEST 1 FAILED: Expected 200, got {response.status_code}")
            print(f"Response: {response.get_data(as_text=True)}")
            return False


def test_modal_integration(bid_id, bucket_id):
    """
    Test that the bucket page includes the modal and button
    """
    print_section("TEST 2: Modal Integration on Bucket Page")

    with app.test_client() as client:
        # Get the bucket page
        response = client.get(f'/buy/bucket/{bucket_id}')

        print(f"\nResponse Status: {response.status_code}")

        if response.status_code == 200:
            html = response.get_data(as_text=True)

            print("\n" + "-" * 80)
            print("VALIDATION: Page Contains Required Elements")
            print("-" * 80)

            # Check for modal
            assert 'bidBidderModal' in html, "Page should include bidBidderModal"
            print("✓ Page includes bidBidderModal element")

            # Check for JS file
            assert 'bid_bidder_modal.js' in html, "Page should include bid_bidder_modal.js script"
            print("✓ Page includes bid_bidder_modal.js script")

            # Check for CSS
            assert 'cart_sellers_modal.css' in html, "Page should include cart_sellers_modal.css (reused for styling)"
            print("✓ Page includes modal CSS")

            # Check for openBidderModal function call
            assert 'openBidderModal' in html, "Page should have openBidderModal function calls"
            print("✓ Page has openBidderModal function calls")

            # Check for View Bidder button structure
            assert 'View Bidder' in html or 'view-bidder-btn' in html, "Page should have View Bidder button"
            print("✓ Page has View Bidder button")

            print("\n✅ TEST 2 PASSED: Modal and button are properly integrated!")
            return True
        else:
            print(f"\n❌ TEST 2 FAILED: Expected 200, got {response.status_code}")
            return False


def main():
    print_section("View Bidder Modal - Comprehensive Test")

    try:
        # Create test data
        print_section("SETUP: Creating Test Data")
        bid_id, bidder_username, bucket_id = create_test_data()
        print(f"✓ Created test bid (ID: {bid_id})")
        print(f"✓ Bidder username: {bidder_username}")
        print(f"✓ Bucket ID: {bucket_id}")

        # Test 1: API Endpoint
        test1_passed = test_api_endpoint(bid_id, bidder_username)

        # Test 2: Modal Integration
        test2_passed = test_modal_integration(bid_id, bucket_id)

        # Final Summary
        print_section("TEST SUMMARY")

        if test1_passed and test2_passed:
            print("✅ All tests passed successfully!")
            print("\nImplementation Complete:")
            print("  ✓ API endpoint returns bidder information")
            print("  ✓ Modal HTML template included in page")
            print("  ✓ Modal JavaScript included in page")
            print("  ✓ View Bidder button added to bid tiles")
            print("  ✓ CSS styling applied")
            print("\n✅ The View Bidder modal is ready to use!")
            print("\nTo test manually:")
            print("  1. Navigate to a Bucket ID page with bids")
            print(f"     Example: http://localhost:5000/buy/bucket/{bucket_id}")
            print("  2. Click the 'View Bidder' button on any bid tile")
            print("  3. Modal should open showing bidder's:")
            print("     - Username")
            print("     - Rating (stars)")
            print("     - Number of reviews")
            print("     - Quantity in the bid")
            return True
        else:
            print("❌ Some tests failed!")
            if not test1_passed:
                print("  ✗ API endpoint test failed")
            if not test2_passed:
                print("  ✗ Modal integration test failed")
            return False

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
