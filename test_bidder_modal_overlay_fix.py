"""
Test script to verify View Bidder modal displays as proper overlay
Tests HTML structure, CSS inclusion, and modal behavior
"""

import sys
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
    Returns: bid_id, bucket_id
    """
    conn = get_db_connection()

    # Create test bidder user
    bidder = conn.execute("SELECT id FROM users WHERE username = 'test_overlay_bidder'").fetchone()
    if not bidder:
        conn.execute(
            "INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)",
            ('test_overlay_bidder', 'hash123', 'test_overlay@test.com')
        )
        conn.commit()
        bidder = conn.execute("SELECT id FROM users WHERE username = 'test_overlay_bidder'").fetchone()

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

    # Create a test bid
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
    conn.close()

    return bid_id, bucket_id


def cleanup_test_data():
    """Clean up test data"""
    conn = get_db_connection()

    # Get test user
    user = conn.execute("SELECT id FROM users WHERE username = 'test_overlay_bidder'").fetchone()
    if user:
        bidder_id = user['id']
        # Delete bids
        conn.execute("DELETE FROM bids WHERE buyer_id = ?", (bidder_id,))
        conn.commit()

    conn.close()


def test_modal_html_structure(bucket_id):
    """
    Test that the bucket page includes correct modal HTML structure
    """
    print_section("TEST 1: Modal HTML Structure")

    with app.test_client() as client:
        response = client.get(f'/buy/bucket/{bucket_id}')

        print(f"\nResponse Status: {response.status_code}")

        if response.status_code == 200:
            html = response.get_data(as_text=True)

            print("\n" + "-" * 80)
            print("VALIDATION: Modal Structure")
            print("-" * 80)

            # Check for correct modal ID
            assert 'id="bidBidderModal"' in html, "Page should include bidBidderModal element"
            print("✓ Modal has correct ID: bidBidderModal")

            # Check for correct overlay class
            assert 'order-sellers-modal-overlay' in html, "Modal should use order-sellers-modal-overlay class"
            print("✓ Modal uses correct overlay class: order-sellers-modal-overlay")

            # Check for correct content class
            assert 'order-sellers-modal-content' in html, "Modal should use order-sellers-modal-content class"
            print("✓ Modal uses correct content class: order-sellers-modal-content")

            # Check for modal content container
            assert 'bidBidderModalContent' in html, "Page should include bidBidderModalContent container"
            print("✓ Modal has content container")

            print("\n✅ TEST 1 PASSED: Modal HTML structure is correct!")
            return True
        else:
            print(f"\n❌ TEST 1 FAILED: Expected 200, got {response.status_code}")
            return False


def test_css_inclusion(bucket_id):
    """
    Test that the bucket page includes required CSS files
    """
    print_section("TEST 2: CSS File Inclusion")

    with app.test_client() as client:
        response = client.get(f'/buy/bucket/{bucket_id}')

        print(f"\nResponse Status: {response.status_code}")

        if response.status_code == 200:
            html = response.get_data(as_text=True)

            print("\n" + "-" * 80)
            print("VALIDATION: CSS Files")
            print("-" * 80)

            # Check for Orders modal CSS
            assert 'order_sellers_modal.css' in html, "Page should include order_sellers_modal.css"
            print("✓ Page includes order_sellers_modal.css")

            # Check for Cart sellers CSS (for styling consistency)
            assert 'cart_sellers_modal.css' in html, "Page should include cart_sellers_modal.css"
            print("✓ Page includes cart_sellers_modal.css")

            print("\n✅ TEST 2 PASSED: Required CSS files are included!")
            return True
        else:
            print(f"\n❌ TEST 2 FAILED: Expected 200, got {response.status_code}")
            return False


def test_javascript_inclusion(bucket_id):
    """
    Test that the bucket page includes modal JavaScript with cache-busting
    """
    print_section("TEST 3: JavaScript Inclusion")

    with app.test_client() as client:
        response = client.get(f'/buy/bucket/{bucket_id}')

        print(f"\nResponse Status: {response.status_code}")

        if response.status_code == 200:
            html = response.get_data(as_text=True)

            print("\n" + "-" * 80)
            print("VALIDATION: JavaScript Files")
            print("-" * 80)

            # Check for JS file
            assert 'bid_bidder_modal.js' in html, "Page should include bid_bidder_modal.js"
            print("✓ Page includes bid_bidder_modal.js")

            # Check for cache-busting version
            assert 'bid_bidder_modal.js?v=OVERLAY_FIX' in html, "JS should have OVERLAY_FIX version for cache-busting"
            print("✓ JavaScript has cache-busting version: OVERLAY_FIX")

            # Check for openBidderModal function call
            assert 'openBidderModal' in html, "Page should have openBidderModal function calls"
            print("✓ Page has openBidderModal function calls")

            print("\n✅ TEST 3 PASSED: JavaScript is properly included with cache-busting!")
            return True
        else:
            print(f"\n❌ TEST 3 FAILED: Expected 200, got {response.status_code}")
            return False


def test_api_endpoint(bid_id):
    """
    Test the API endpoint still works correctly
    """
    print_section("TEST 4: API Endpoint")

    with app.test_client() as client:
        response = client.get(f'/bids/api/bid/{bid_id}/bidder_info')

        print(f"\nResponse Status: {response.status_code}")

        if response.status_code == 200:
            data = response.get_json()
            print(f"\n✓ API returns JSON data")

            # Validate response structure
            required_fields = ['buyer_id', 'username', 'rating', 'num_reviews', 'quantity']
            for field in required_fields:
                assert field in data, f"{field} should be present in response"

            print(f"\n✅ TEST 4 PASSED: API endpoint works correctly!")
            return True
        else:
            print(f"\n❌ TEST 4 FAILED: Expected 200, got {response.status_code}")
            return False


def main():
    print_section("View Bidder Modal Overlay Fix - Verification Test")

    try:
        # Create test data
        print_section("SETUP: Creating Test Data")
        bid_id, bucket_id = create_test_data()
        print(f"✓ Created test bid (ID: {bid_id})")
        print(f"✓ Bucket ID: {bucket_id}")

        # Run tests
        test1_passed = test_modal_html_structure(bucket_id)
        test2_passed = test_css_inclusion(bucket_id)
        test3_passed = test_javascript_inclusion(bucket_id)
        test4_passed = test_api_endpoint(bid_id)

        # Final Summary
        print_section("TEST SUMMARY")

        if test1_passed and test2_passed and test3_passed and test4_passed:
            print("✅ All tests passed successfully!")
            print("\nFix Implementation Summary:")
            print("  ✓ Modal HTML uses correct overlay classes")
            print("  ✓ order_sellers_modal.css included for overlay styling")
            print("  ✓ JavaScript simplified to match Orders modal pattern")
            print("  ✓ Cache-busting version applied (OVERLAY_FIX)")
            print("  ✓ API endpoint working correctly")
            print("\n✅ The View Bidder modal should now display as a proper overlay!")
            print("\nExpected Behavior:")
            print("  • Modal opens with dark semi-transparent backdrop")
            print("  • Modal content centered in white card")
            print("  • Click outside modal to close")
            print("  • No inline HTML injection")
            print(f"\nManual Test URL: http://localhost:5000/buy/bucket/{bucket_id}")
            print("  1. Click 'View Bidder' button on any bid tile")
            print("  2. Modal should open as overlay (not inline)")
            print("  3. Background should be dark and semi-transparent")
            print("  4. Modal should be centered on screen")
            return True
        else:
            print("❌ Some tests failed!")
            if not test1_passed:
                print("  ✗ Modal HTML structure test failed")
            if not test2_passed:
                print("  ✗ CSS inclusion test failed")
            if not test3_passed:
                print("  ✗ JavaScript inclusion test failed")
            if not test4_passed:
                print("  ✗ API endpoint test failed")
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
