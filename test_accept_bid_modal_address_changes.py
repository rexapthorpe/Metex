"""
Test script to verify accept bid modal address changes
- Confirmation modal: Has privacy message (no address)
- Success modal: Shows formatted address (5 fields)
"""

import sys
import io
import re

# Fix encoding for Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def print_section(title):
    """Print a section header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def test_confirmation_modal_privacy_message():
    """
    Test that confirmation modal has privacy message (no address)
    """
    print_section("TEST 1: Confirmation Modal - Privacy Message")

    try:
        with open('templates/modals/accept_bid_modals.html', 'r', encoding='utf-8') as f:
            content = f.read()

        print("\n" + "-" * 80)
        print("VALIDATION: Privacy Message")
        print("-" * 80)

        # Check for privacy notice
        if 'privacy-notice' not in content:
            print("❌ privacy-notice class not found")
            return False
        print("✓ privacy-notice class found")

        # Check for lock icon
        if 'fa-lock' not in content:
            print("❌ Lock icon not found")
            return False
        print("✓ Lock icon (fa-lock) found")

        # Check for privacy message text
        if 'delivery address is hidden' not in content.lower():
            print("❌ Privacy message text not found")
            return False
        print("✓ Privacy message text found")

        # Check for specific phrase
        if 'protecting user privacy' not in content.lower():
            print("❌ 'protecting user privacy' phrase not found")
            return False
        print("✓ 'protecting user privacy' phrase found")

        # Ensure old address fields in confirmation modal are REMOVED
        # Check that address fields like "confirm-address-line1" are NOT in the HTML
        confirmation_section = content.split('<!-- Accept Bid Success Modal -->')[0]
        if 'id="confirm-address-line1"' in confirmation_section:
            print("❌ Old address fields still present in confirmation modal!")
            return False
        print("✓ Old address fields removed from confirmation modal")

        # Extract and display the privacy notice
        privacy_match = re.search(
            r'<div class="privacy-notice">.*?</div>',
            content,
            re.DOTALL
        )
        if privacy_match:
            privacy_html = privacy_match.group(0)
            print("\n✓ Privacy notice HTML:")
            print("-" * 80)
            lines = [l.strip() for l in privacy_html.split('\n') if l.strip()]
            for line in lines[:5]:
                print(f"  {line}")
            print("-" * 80)

        print("\n✅ TEST 1 PASSED: Privacy message is present!")
        return True

    except Exception as e:
        print(f"\n❌ TEST 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_success_modal_address_fields():
    """
    Test that success modal has address fields
    """
    print_section("TEST 2: Success Modal - Address Fields")

    try:
        with open('templates/modals/accept_bid_modals.html', 'r', encoding='utf-8') as f:
            content = f.read()

        print("\n" + "-" * 80)
        print("VALIDATION: Address Section in Success Modal")
        print("-" * 80)

        # Split to only check success modal section
        success_section = content.split('<!-- Accept Bid Success Modal -->')[1]

        # Check for address fields
        required_fields = [
            ('Address Line 1', 'success-address-line1'),
            ('Address Line 2', 'success-address-line2'),
            ('City', 'success-address-city'),
            ('State', 'success-address-state'),
            ('ZIP Code', 'success-address-zip')
        ]

        all_found = True
        for label, field_id in required_fields:
            if f'id="{field_id}"' in success_section:
                print(f"✓ {label}: {field_id} found")
            else:
                print(f"❌ {label}: {field_id} NOT FOUND")
                all_found = False

        if not all_found:
            return False

        # Check that fields are initially hidden
        hidden_count = success_section.count('style="display: none;"')
        if hidden_count < 5:
            print(f"⚠️  Only {hidden_count} address fields are hidden (expected 5+)")
        else:
            print(f"✓ Address fields are hidden by default ({hidden_count} hidden elements)")

        # Ensure old single-line address is REMOVED
        if 'id="success-delivery-address"' in success_section:
            print("❌ Old single-line address field still present!")
            return False
        print("✓ Old single-line address field removed")

        print("\n✅ TEST 2 PASSED: Success modal has address fields!")
        return True

    except Exception as e:
        print(f"\n❌ TEST 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_javascript_confirmation_no_address():
    """
    Test that JavaScript does NOT populate address in confirmation modal
    """
    print_section("TEST 3: JavaScript - Confirmation Modal No Address")

    try:
        with open('static/js/modals/accept_bid_modals.js', 'r', encoding='utf-8') as f:
            content = f.read()

        print("\n" + "-" * 80)
        print("VALIDATION: No Address Logic in Confirmation Modal")
        print("-" * 80)

        # Find the openAcceptBidConfirmModal function
        confirm_func_match = re.search(
            r'function openAcceptBidConfirmModal\([^)]*\)\s*\{(.*?)\n\}',
            content,
            re.DOTALL
        )

        if not confirm_func_match:
            print("❌ openAcceptBidConfirmModal function not found")
            return False

        confirm_func = confirm_func_match.group(1)

        # Check that address parsing is NOT present
        if 'confirm-address-line1' in confirm_func:
            print("❌ Address parsing still present in confirmation modal function")
            return False
        print("✓ No address parsing in confirmation modal function")

        if 'address.split' in confirm_func:
            print("❌ Address splitting still present in confirmation modal function")
            return False
        print("✓ No address splitting in confirmation modal function")

        print("\n✅ TEST 3 PASSED: Confirmation modal JS has no address logic!")
        return True

    except Exception as e:
        print(f"\n❌ TEST 3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_javascript_success_address_parsing():
    """
    Test that JavaScript parses and displays address in success modal
    """
    print_section("TEST 4: JavaScript - Success Modal Address Parsing")

    try:
        with open('static/js/modals/accept_bid_modals.js', 'r', encoding='utf-8') as f:
            content = f.read()

        print("\n" + "-" * 80)
        print("VALIDATION: Address Parsing Logic in Success Modal")
        print("-" * 80)

        # Check for deliveryAddress or delivery_address parameter
        if 'delivery_address' not in content:
            print("❌ delivery_address not found")
            return False
        print("✓ delivery_address found")

        # Check for address parsing
        if "split('•')" not in content:
            print("❌ Address parsing logic (split('•')) not found")
            return False
        print("✓ Address parsing logic found")

        # Check for address components
        required_vars = ['street', 'street2', 'city', 'state', 'zip']
        all_found = True
        for var in required_vars:
            if f"let {var} = ''" in content:
                print(f"✓ Variable '{var}' declared")
            else:
                print(f"❌ Variable '{var}' NOT found")
                all_found = False

        if not all_found:
            return False

        # Check for address display logic
        if 'success-address-line1-row' not in content:
            print("❌ Address row display logic not found")
            return False
        print("✓ Address row display logic found")

        # Check for flex display assignment
        if "style.display = 'flex'" not in content:
            print("❌ Display flex assignment not found")
            return False
        print("✓ Display flex assignment found")

        print("\n✅ TEST 4 PASSED: JavaScript has address parsing in success modal!")
        return True

    except Exception as e:
        print(f"\n❌ TEST 4 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_css_privacy_notice():
    """
    Test that CSS styles privacy notice
    """
    print_section("TEST 5: CSS - Privacy Notice Styling")

    try:
        with open('static/css/modals/accept_bid_modals.css', 'r', encoding='utf-8') as f:
            content = f.read()

        print("\n" + "-" * 80)
        print("VALIDATION: Privacy Notice CSS")
        print("-" * 80)

        # Check for privacy-notice class
        if '.privacy-notice' not in content:
            print("❌ .privacy-notice CSS class not found")
            return False
        print("✓ .privacy-notice CSS class found")

        # Extract privacy notice CSS
        privacy_css_match = re.search(
            r'/\* Privacy Notice \*/.*?\\.privacy-notice \{[^}]+\}',
            content,
            re.DOTALL
        )
        if privacy_css_match:
            privacy_css = privacy_css_match.group(0)
            print("\n✓ Privacy notice CSS:")
            print("-" * 80)
            for line in privacy_css.split('\n'):
                if line.strip():
                    print(f"  {line}")
            print("-" * 80)

            # Check for key properties
            required_props = ['display: flex', 'background:', 'border:', 'padding:']
            for prop in required_props:
                if prop in privacy_css:
                    print(f"✓ Has {prop}")
                else:
                    print(f"⚠️  Missing {prop}")

        print("\n✅ TEST 5 PASSED: CSS styling is present!")
        return True

    except Exception as e:
        print(f"\n❌ TEST 5 FAILED: {e}")
        return False


def main():
    print_section("Accept Bid Modal Address Changes - Verification")

    # Run tests
    test1_passed = test_confirmation_modal_privacy_message()
    test2_passed = test_success_modal_address_fields()
    test3_passed = test_javascript_confirmation_no_address()
    test4_passed = test_javascript_success_address_parsing()
    test5_passed = test_css_privacy_notice()

    # Final Summary
    print_section("TEST RESULTS")

    if all([test1_passed, test2_passed, test3_passed, test4_passed, test5_passed]):
        print("✅ All tests passed successfully!")
        print("\n" + "=" * 80)
        print("CHANGES VERIFIED:")
        print("-" * 80)
        print("✓ Confirmation modal has privacy message (no address)")
        print("✓ Success modal has address section (5 fields)")
        print("✓ JavaScript does NOT parse address in confirmation")
        print("✓ JavaScript parses address in success modal")
        print("✓ CSS styles privacy notice")
        print("=" * 80)
        print("\nEXPECTED BEHAVIOR:")
        print("-" * 80)
        print("ACCEPT BID CONFIRMATION MODAL (before accepting bid):")
        print("  • Shows bid details (price, quantity, etc.)")
        print("  • Shows item specifications")
        print("  • Shows grading requirement")
        print("  • Shows privacy message with lock icon")
        print("  • Message: 'User's delivery address is hidden until")
        print("    bid is accepted for the purpose of protecting user privacy'")
        print("  • NO address details shown")
        print("")
        print("ACCEPT BID SUCCESS MODAL (after bid accepted successfully):")
        print("  • Shows congratulations message")
        print("  • Shows buyer information with name")
        print("  • Shows Delivery Address with:")
        print("    - Address Line 1: e.g., '123 Main Street'")
        print("    - Address Line 2: e.g., 'Apt 6D' (if provided)")
        print("    - City: e.g., 'Brooklyn'")
        print("    - State: e.g., 'NY'")
        print("    - ZIP Code: e.g., '12345'")
        print("  • Shows transaction details (price, quantity, total)")
        print("  • Shows item details (all specifications)")
        print("  • Shows shipping notice with 4-day deadline")
        print("-" * 80)
        print("\nMANUAL TEST STEPS:")
        print("-" * 80)
        print("1. Navigate to a bucket page that has bids")
        print("2. As a seller, view the bids on your listing")
        print("3. Click 'Accept Bids' button")
        print("4. Select a bid and click 'Accept Selected Bids'")
        print("5. CONFIRMATION MODAL appears:")
        print("   → Verify privacy message shows (no address)")
        print("6. Click 'Yes, Accept Bid'")
        print("7. SUCCESS MODAL appears:")
        print("   → Verify address section shows all 5 fields")
        print("   → Verify address is formatted correctly")
        print("-" * 80)
        return True
    else:
        print("❌ Some tests failed!")
        if not test1_passed:
            print("  ✗ Confirmation modal privacy message test failed")
        if not test2_passed:
            print("  ✗ Success modal address fields test failed")
        if not test3_passed:
            print("  ✗ JavaScript confirmation no address test failed")
        if not test4_passed:
            print("  ✗ JavaScript success address parsing test failed")
        if not test5_passed:
            print("  ✗ CSS privacy notice test failed")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
