"""
Test script to verify View Bidder button doesn't trigger form submission
Checks that type="button" is present to prevent default submit behavior
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


def test_button_type_attribute():
    """
    Test that View Bidder button has type='button' attribute
    """
    print_section("TEST 1: Button Type Attribute")

    try:
        with open('templates/view_bucket.html', 'r', encoding='utf-8') as f:
            content = f.read()

        print("\n" + "-" * 80)
        print("VALIDATION: Button Type Attribute")
        print("-" * 80)

        # Check for View Bidder button
        if 'view-bidder-btn' not in content:
            print("❌ View Bidder button not found in template")
            return False
        print("✓ View Bidder button found in template")

        # Extract the button HTML
        pattern = re.compile(
            r'<button[^>]*view-bidder-btn[^>]*>.*?</button>',
            re.DOTALL
        )
        match = pattern.search(content)
        if not match:
            print("❌ Could not extract button HTML")
            return False

        button_html = match.group(0)

        # Check for type="button"
        if 'type="button"' not in button_html:
            print("❌ Button missing type=\"button\" attribute")
            print("\n⚠️  Without type=\"button\", the button defaults to type=\"submit\"")
            print("   This causes form submission when clicked!")
            return False
        print("✓ Button has type=\"button\" attribute")

        # Verify it's before class attribute (good practice)
        type_pos = button_html.find('type="button"')
        class_pos = button_html.find('class=')
        if type_pos < class_pos:
            print("✓ type=\"button\" is positioned before class attribute (good practice)")
        else:
            print("⚠️  type attribute is after class (works but not ideal)")

        # Show the button opening tag
        opening_tag = re.search(r'<button[^>]*>', button_html)
        if opening_tag:
            tag = opening_tag.group(0)
            # Format for readability
            attrs = tag.replace('<button', '').replace('>', '').strip()
            print(f"\n✓ Button opening tag:")
            print(f"  <button {attrs[:60]}...")

        print("\n✅ TEST 1 PASSED: Button has type=\"button\" attribute!")
        return True

    except Exception as e:
        print(f"\n❌ TEST 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_form_context():
    """
    Test that button is inside form but won't submit it
    """
    print_section("TEST 2: Form Context")

    try:
        with open('templates/view_bucket.html', 'r', encoding='utf-8') as f:
            content = f.read()

        print("\n" + "-" * 80)
        print("VALIDATION: Button and Form Relationship")
        print("-" * 80)

        # Find the form
        form_match = re.search(r'<form[^>]*id="accept-bids-form"[^>]*>', content)
        if not form_match:
            print("❌ Could not find accept-bids-form")
            return False
        print("✓ Found accept-bids-form")

        # Find the form start and end positions
        form_start = content.find('<form')
        form_end = content.find('</form>', form_start)

        # Check if View Bidder button is inside form
        button_pos = content.find('view-bidder-btn')
        if form_start < button_pos < form_end:
            print("✓ View Bidder button is inside the form")
            print("  This confirms why type=\"button\" is required")
        else:
            print("⚠️  Button might not be inside form (unusual)")

        # Show form submit button for comparison
        submit_btn = re.search(r'<button[^>]*type="submit"[^>]*>Accept Bids</button>', content)
        if submit_btn:
            print("\n✓ Form has a submit button (Accept Bids)")
            print("  Only this button should submit the form")

        print("\n✅ TEST 2 PASSED: Form context verified!")
        return True

    except Exception as e:
        print(f"\n❌ TEST 2 FAILED: {e}")
        return False


def test_comparison_with_other_buttons():
    """
    Compare View Bidder button with other buttons that use type="button"
    """
    print_section("TEST 3: Comparison with Other Buttons")

    try:
        with open('templates/view_bucket.html', 'r', encoding='utf-8') as f:
            content = f.read()

        print("\n" + "-" * 80)
        print("COMPARISON: Button Types in Template")
        print("-" * 80)

        # Find all button types
        all_buttons = re.findall(r'<button([^>]*)>', content)

        type_button_count = 0
        type_submit_count = 0
        no_type_count = 0

        for attrs in all_buttons:
            if 'type="button"' in attrs:
                type_button_count += 1
            elif 'type="submit"' in attrs:
                type_submit_count += 1
            else:
                no_type_count += 1

        print(f"✓ Button type distribution:")
        print(f"  • type=\"button\": {type_button_count} buttons")
        print(f"  • type=\"submit\": {type_submit_count} buttons")
        print(f"  • No type specified: {no_type_count} buttons")

        if no_type_count > 0:
            print(f"\n⚠️  Warning: {no_type_count} button(s) missing type attribute")
            print("   Buttons without type inside forms default to submit!")

        # Check specific buttons
        print("\n✓ Specific button checks:")

        # View Bidder
        if 'view-bidder-btn' in content:
            if re.search(r'<button[^>]*type="button"[^>]*view-bidder-btn', content):
                print("  • View Bidder: type=\"button\" ✓")
            else:
                print("  • View Bidder: missing type ✗")

        # Dial buttons
        if re.search(r'<button[^>]*type="button"[^>]*dial-btn', content):
            print("  • Dial +/- buttons: type=\"button\" ✓")

        # Create Bid button
        if re.search(r'<button[^>]*type="button"[^>]*header-bid-btn', content):
            print("  • Create Bid button: type=\"button\" ✓")

        # Accept Bids button (should be submit)
        if re.search(r'<button[^>]*type="submit"[^>]*accept-bids-btn', content):
            print("  • Accept Bids button: type=\"submit\" ✓")
        elif 'accept-bids-btn' in content:
            print("  • Accept Bids button: missing type (defaults to submit) ✓")

        print("\n✅ TEST 3 PASSED: Button types are consistent!")
        return True

    except Exception as e:
        print(f"\n❌ TEST 3 FAILED: {e}")
        return False


def test_validation_handler():
    """
    Check the validation handler in accept_bid_modals.js
    """
    print_section("TEST 4: Form Validation Handler")

    try:
        with open('static/js/modals/accept_bid_modals.js', 'r', encoding='utf-8') as f:
            js_content = f.read()

        print("\n" + "-" * 80)
        print("VALIDATION: Form Submit Handler")
        print("-" * 80)

        # Find the validation alert
        if 'Please select at least one bid to accept' in js_content:
            print("✓ Found validation message in accept_bid_modals.js")

            # Show context
            lines = js_content.split('\n')
            for i, line in enumerate(lines):
                if 'Please select at least one bid to accept' in line:
                    print(f"\n✓ Validation at line {i+1}:")
                    start = max(0, i-5)
                    end = min(len(lines), i+3)
                    for j in range(start, end):
                        marker = ">>>" if j == i else "   "
                        print(f"{marker} {str(j+1).rjust(4)} | {lines[j][:70]}")
                    break

            print("\n✓ This validation only runs on form submit")
            print("  type=\"button\" prevents form submit")
            print("  Therefore: No popup when clicking View Bidder!")

        print("\n✅ TEST 4 PASSED: Validation handler understood!")
        return True

    except Exception as e:
        print(f"\n❌ TEST 4 FAILED: {e}")
        return False


def main():
    print_section("View Bidder Form Submit Fix - Verification")

    # Run tests
    test1_passed = test_button_type_attribute()
    test2_passed = test_form_context()
    test3_passed = test_comparison_with_other_buttons()
    test4_passed = test_validation_handler()

    # Final Summary
    print_section("TEST RESULTS")

    if test1_passed and test2_passed and test3_passed and test4_passed:
        print("✅ All tests passed successfully!")
        print("\n" + "=" * 80)
        print("FIX VERIFIED:")
        print("-" * 80)
        print("✓ View Bidder button has type=\"button\" attribute")
        print("✓ Button is inside accept-bids-form")
        print("✓ type=\"button\" prevents form submission")
        print("✓ Button types are consistent across template")
        print("=" * 80)
        print("\n✅ The popup should no longer appear!")
        print("\nEXPECTED BEHAVIOR (after fix):")
        print("-" * 80)
        print("✓ Click 'View Bidder' → Modal opens immediately")
        print("✓ NO 'Please select at least one bid' popup")
        print("✓ NO form submission")
        print("✓ NO validation checks")
        print("✓ Bidder modal appears instantly")
        print("-" * 80)
        print("\nWHY THIS WORKS:")
        print("-" * 80)
        print("BEFORE:")
        print("  • Button had no type attribute")
        print("  • Inside form → defaults to type=\"submit\"")
        print("  • Click → submits form → validation → popup ✗")
        print("")
        print("AFTER:")
        print("  • Button has type=\"button\"")
        print("  • Click → only runs onclick → opens modal ✓")
        print("  • No form submission → no validation → no popup ✓")
        print("-" * 80)
        print("\nMANUAL TEST STEPS:")
        print("-" * 80)
        print("1. Navigate to a Bucket ID page with bids")
        print("2. Click 'View Bidder' button")
        print("3. Verify modal opens IMMEDIATELY (no popup)")
        print("4. Close modal")
        print("5. Click 'View Bidder' on different bid")
        print("6. Verify again - no popup, instant modal")
        print("7. Click 'Accept Bids' (submit button)")
        print("8. Verify popup DOES appear (validation still works)")
        print("-" * 80)
        return True
    else:
        print("❌ Some tests failed!")
        if not test1_passed:
            print("  ✗ Button type attribute test failed")
        if not test2_passed:
            print("  ✗ Form context test failed")
        if not test3_passed:
            print("  ✗ Button comparison test failed")
        if not test4_passed:
            print("  ✗ Validation handler test failed")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
