"""
Test script to verify bid modal address changes
- Confirmation modal: Has privacy message
- Success modal: Shows formatted address
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
    Test that confirmation modal has privacy message
    """
    print_section("TEST 1: Confirmation Modal - Privacy Message")

    try:
        with open('templates/modals/bid_confirm_modal.html', 'r', encoding='utf-8') as f:
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
        with open('templates/modals/bid_confirm_modal.html', 'r', encoding='utf-8') as f:
            content = f.read()

        print("\n" + "-" * 80)
        print("VALIDATION: Address Section in Success Modal")
        print("-" * 80)

        # Check for Delivery Address section
        if 'Delivery Address' not in content:
            print("❌ 'Delivery Address' heading not found")
            return False
        print("✓ 'Delivery Address' heading found")

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
            if f'id="{field_id}"' in content:
                print(f"✓ {label}: {field_id} found")
            else:
                print(f"❌ {label}: {field_id} NOT FOUND")
                all_found = False

        if not all_found:
            return False

        # Check that fields are initially hidden
        hidden_count = content.count('style="display: none;"')
        if hidden_count < 5:
            print(f"⚠️  Only {hidden_count} address fields are hidden (expected 5+)")
        else:
            print(f"✓ Address fields are hidden by default ({hidden_count} hidden elements)")

        print("\n✅ TEST 2 PASSED: Success modal has address fields!")
        return True

    except Exception as e:
        print(f"\n❌ TEST 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_javascript_address_parsing():
    """
    Test that JavaScript parses and displays address
    """
    print_section("TEST 3: JavaScript - Address Parsing")

    try:
        with open('static/js/modals/bid_confirm_modal.js', 'r', encoding='utf-8') as f:
            content = f.read()

        print("\n" + "-" * 80)
        print("VALIDATION: Address Parsing Logic")
        print("-" * 80)

        # Check for deliveryAddress parameter
        if 'data.deliveryAddress' not in content:
            print("❌ data.deliveryAddress not found")
            return False
        print("✓ data.deliveryAddress found")

        # Check for address parsing
        if 'split(\'•\')' not in content:
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

        print("\n✅ TEST 3 PASSED: JavaScript has address parsing!")
        return True

    except Exception as e:
        print(f"\n❌ TEST 3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_javascript_address_construction():
    """
    Test that JavaScript constructs deliveryAddress for success modal
    """
    print_section("TEST 4: JavaScript - Address Construction")

    try:
        with open('static/js/modals/bid_modal.js', 'r', encoding='utf-8') as f:
            content = f.read()

        print("\n" + "-" * 80)
        print("VALIDATION: Delivery Address Construction")
        print("-" * 80)

        # Check for address extraction from form
        address_fields = [
            'address_line1',
            'address_line2',
            'city',
            'state',
            'zip_code'
        ]

        all_found = True
        for field in address_fields:
            if f"formData.get('{field}')" in content:
                print(f"✓ Extracts {field} from form")
            else:
                print(f"❌ Does NOT extract {field} from form")
                all_found = False

        if not all_found:
            return False

        # Check for address construction
        if 'deliveryAddress = addressLine1' in content or "deliveryAddress = '';" in content:
            print("✓ Constructs deliveryAddress variable")
        else:
            print("❌ deliveryAddress construction not found")
            return False

        # Check for adding to bidData
        if 'deliveryAddress: deliveryAddress' in content:
            print("✓ Adds deliveryAddress to bidData")
        else:
            print("❌ deliveryAddress NOT added to bidData")
            return False

        print("\n✅ TEST 4 PASSED: JavaScript constructs deliveryAddress!")
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
        with open('static/css/modals/bid_confirm_modal.css', 'r', encoding='utf-8') as f:
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
            r'\.privacy-notice \{[^}]+\}',
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
    print_section("Bid Modal Address Changes - Verification")

    # Run tests
    test1_passed = test_confirmation_modal_privacy_message()
    test2_passed = test_success_modal_address_fields()
    test3_passed = test_javascript_address_parsing()
    test4_passed = test_javascript_address_construction()
    test5_passed = test_css_privacy_notice()

    # Final Summary
    print_section("TEST RESULTS")

    if all([test1_passed, test2_passed, test3_passed, test4_passed, test5_passed]):
        print("✅ All tests passed successfully!")
        print("\n" + "=" * 80)
        print("CHANGES VERIFIED:")
        print("-" * 80)
        print("✓ Confirmation modal has privacy message")
        print("✓ Success modal has address section (5 fields)")
        print("✓ JavaScript parses address from data")
        print("✓ JavaScript constructs address from form")
        print("✓ CSS styles privacy notice")
        print("=" * 80)
        print("\nEXPECTED BEHAVIOR:")
        print("-" * 80)
        print("CONFIRMATION MODAL (before submitting bid):")
        print("  • Shows bid details (price, quantity, etc.)")
        print("  • Shows privacy message with lock icon")
        print("  • Message: 'Your delivery address is hidden until your")
        print("    bid is accepted for the purpose of protecting user privacy'")
        print("  • NO address details shown")
        print("")
        print("SUCCESS MODAL (after bid placed successfully):")
        print("  • Shows bid summary")
        print("  • Shows Delivery Address section with:")
        print("    - Address Line 1: e.g., '123 Main Street'")
        print("    - Address Line 2: e.g., 'Apt 6D' (if provided)")
        print("    - City: e.g., 'Brooklyn'")
        print("    - State: e.g., 'NY'")
        print("    - ZIP Code: e.g., '12345'")
        print("  • Format matches sold items display")
        print("-" * 80)
        print("\nMANUAL TEST STEPS:")
        print("-" * 80)
        print("1. Navigate to a bucket page")
        print("2. Click 'Create a Bid' button")
        print("3. Fill out bid form with address")
        print("4. Click 'Submit Bid'")
        print("5. CONFIRMATION MODAL appears:")
        print("   → Verify privacy message shows (no address)")
        print("6. Click 'Confirm Bid'")
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
            print("  ✗ JavaScript address parsing test failed")
        if not test4_passed:
            print("  ✗ JavaScript address construction test failed")
        if not test5_passed:
            print("  ✗ CSS privacy notice test failed")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
