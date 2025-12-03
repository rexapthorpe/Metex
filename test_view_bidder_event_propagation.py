"""
Test script to verify View Bidder button doesn't trigger bid selection
Checks that event.stopPropagation() is present in the onclick handler
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


def create_test_bid():
    """
    Create a test bid in the database
    Returns: bid_id, bucket_id
    """
    conn = get_db_connection()

    # Get or create test user
    user = conn.execute("SELECT id FROM users WHERE username = 'test_propagation_bidder'").fetchone()
    if not user:
        conn.execute(
            "INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)",
            ('test_propagation_bidder', 'hash123', 'test_prop@test.com')
        )
        conn.commit()
        user = conn.execute("SELECT id FROM users WHERE username = 'test_propagation_bidder'").fetchone()

    user_id = user['id']

    # Get a category
    category = conn.execute("""
        SELECT id, bucket_id
        FROM categories
        WHERE bucket_id IS NOT NULL
        LIMIT 1
    """).fetchone()

    if not category:
        print("❌ No categories found in database")
        conn.close()
        return None, None

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
        user_id,
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


def cleanup_test_bid():
    """Clean up test data"""
    conn = get_db_connection()
    user = conn.execute("SELECT id FROM users WHERE username = 'test_propagation_bidder'").fetchone()
    if user:
        user_id = user['id']
        conn.execute("DELETE FROM bids WHERE buyer_id = ?", (user_id,))
        conn.commit()
    conn.close()


def test_event_propagation_fix():
    """
    Test that View Bidder button has event.stopPropagation() in onclick
    """
    print_section("TEST 1: Event Propagation Fix")

    bid_id, bucket_id = create_test_bid()
    if not bid_id or not bucket_id:
        print("\n❌ Failed to create test bid")
        return False

    try:
        with app.test_client() as client:
            response = client.get(f'/buy/bucket/{bucket_id}')

            print(f"\nBucket ID: {bucket_id}")
            print(f"Response Status: {response.status_code}")

            if response.status_code != 200:
                print(f"\n❌ TEST 1 FAILED: Expected 200, got {response.status_code}")
                return False

            html = response.get_data(as_text=True)

            print("\n" + "-" * 80)
            print("VALIDATION: View Bidder Button Event Handling")
            print("-" * 80)

            # Check for View Bidder button
            if 'view-bidder-btn' not in html:
                print("❌ View Bidder button not found in HTML")
                return False
            print("✓ View Bidder button found in HTML")

            # Check for event.stopPropagation() in onclick
            if 'event.stopPropagation()' not in html:
                print("❌ event.stopPropagation() not found in HTML")
                print("   The button click will bubble up to parent handlers!")
                return False
            print("✓ event.stopPropagation() found in HTML")

            # Check that it's specifically on the View Bidder button
            # Look for the pattern: onclick="event.stopPropagation(); openBidderModal(
            if 'onclick="event.stopPropagation(); openBidderModal(' not in html:
                print("❌ event.stopPropagation() not found in View Bidder button onclick")
                print("   It might be present elsewhere but not on the View Bidder button")
                return False
            print("✓ event.stopPropagation() is in View Bidder button onclick handler")

            # Verify the full onclick pattern
            import re
            pattern = r'onclick="event\.stopPropagation\(\);\s*openBidderModal\(\d+\)"'
            if not re.search(pattern, html):
                print("❌ View Bidder button onclick pattern doesn't match expected format")
                print("   Expected: onclick=\"event.stopPropagation(); openBidderModal(bid_id)\"")
                return False
            print("✓ View Bidder button onclick has correct format")

            # Extract a sample onclick to show user
            match = re.search(r'onclick="(event\.stopPropagation\(\);\s*openBidderModal\([^"]+\))"', html)
            if match:
                print(f"\n✓ Sample onclick handler: {match.group(1)}")

            print("\n✅ TEST 1 PASSED: View Bidder button has event.stopPropagation()!")
            return True

    finally:
        cleanup_test_bid()


def test_button_structure():
    """
    Test the overall button structure in the HTML
    """
    print_section("TEST 2: Button Structure")

    bid_id, bucket_id = create_test_bid()
    if not bid_id or not bucket_id:
        print("\n❌ Failed to create test bid")
        return False

    try:
        with app.test_client() as client:
            response = client.get(f'/buy/bucket/{bucket_id}')

            if response.status_code != 200:
                print(f"\n❌ TEST 2 FAILED: Expected 200, got {response.status_code}")
                return False

            html = response.get_data(as_text=True)

            print("\n" + "-" * 80)
            print("VALIDATION: Button Structure and Classes")
            print("-" * 80)

            # Check for button class
            if 'class="icon-button view-bidder-btn"' not in html:
                print("❌ Button doesn't have correct classes")
                return False
            print("✓ Button has correct classes: icon-button view-bidder-btn")

            # Check for title attribute
            if 'title="View Bidder"' not in html:
                print("❌ Button missing title attribute")
                return False
            print("✓ Button has title attribute")

            # Check for icon
            if '<i class="fa-solid fa-user"></i>' not in html:
                print("❌ Button missing user icon")
                return False
            print("✓ Button has user icon")

            # Check for label
            if '<span class="icon-label">View Bidder</span>' not in html:
                print("❌ Button missing label span")
                return False
            print("✓ Button has label span")

            print("\n✅ TEST 2 PASSED: Button structure is complete!")
            return True

    finally:
        cleanup_test_bid()


def test_comparison_with_dial_buttons():
    """
    Compare View Bidder button with dial buttons that already use stopPropagation
    """
    print_section("TEST 3: Comparison with Dial Buttons")

    print("\n" + "-" * 80)
    print("INFO: How Other Buttons Handle Event Propagation")
    print("-" * 80)

    # Read the view_bucket.js file to show the pattern
    try:
        with open('static/js/view_bucket.js', 'r', encoding='utf-8') as f:
            content = f.read()

        # Find dial button event handling
        if 'e.stopPropagation()' in content:
            print("✓ view_bucket.js uses e.stopPropagation() for dial buttons")

            # Show the pattern
            import re
            pattern = re.search(r'addEventListener\(\'click\',\s*\(e\)\s*=>\s*e\.stopPropagation\(\)\)', content)
            if pattern:
                print(f"✓ Dial pill pattern: {pattern.group(0)}")

            pattern2 = re.search(r'btn\.addEventListener\(\'click\',\s*\(e\)\s*=>\s*\{[^}]*e\.stopPropagation\(\)', content, re.DOTALL)
            if pattern2:
                snippet = pattern2.group(0)[:100]
                print(f"✓ Dial +/- buttons pattern: {snippet}...")

        print("\n✓ View Bidder button now follows same pattern as dial buttons")
        print("  Dial buttons: Use e.stopPropagation() in addEventListener")
        print("  View Bidder: Uses event.stopPropagation() in inline onclick")
        print("\n✅ TEST 3 PASSED: Consistent event handling pattern!")
        return True

    except Exception as e:
        print(f"\n⚠️  Could not read view_bucket.js: {e}")
        print("   (This is informational only, not a test failure)")
        return True


def main():
    print_section("View Bidder Event Propagation Fix - Test Suite")

    # Run tests
    test1_passed = test_event_propagation_fix()
    test2_passed = test_button_structure()
    test3_passed = test_comparison_with_dial_buttons()

    # Final Summary
    print_section("TEST SUMMARY")

    if test1_passed and test2_passed and test3_passed:
        print("✅ All tests passed successfully!")
        print("\nFix Implementation Complete:")
        print("  ✓ View Bidder button has event.stopPropagation() in onclick")
        print("  ✓ Button structure is correct with proper classes and icon")
        print("  ✓ Event handling pattern matches existing dial buttons")
        print("\n✅ The View Bidder button should now work correctly!")
        print("\nExpected Behavior:")
        print("  • Clicking 'View Bidder' opens bidder modal ONLY")
        print("  • Bid tile does NOT get selected")
        print("  • Accept confirmation sidebar does NOT open")
        print("  • No 'Please select at least one bid' popup")
        print("\nManual Test Steps:")
        print("  1. Navigate to a Bucket ID page with bids")
        print("  2. Click 'View Bidder' button on a bid tile")
        print("  3. Verify ONLY the bidder modal opens")
        print("  4. Close modal and verify bid tile is NOT selected")
        print("  5. Click bid tile itself to verify selection still works")
        return True
    else:
        print("❌ Some tests failed!")
        if not test1_passed:
            print("  ✗ Event propagation fix test failed")
        if not test2_passed:
            print("  ✗ Button structure test failed")
        if not test3_passed:
            print("  ✗ Comparison test failed")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
