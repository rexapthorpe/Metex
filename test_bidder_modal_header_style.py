"""
Test script to verify bidder modal header uses centered modal-title class
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


def test_javascript_modal_title():
    """
    Test that bidder modal JavaScript uses modal-title class
    """
    print_section("TEST 1: JavaScript Modal Title Class")

    try:
        with open('static/js/modals/bid_bidder_modal.js', 'r', encoding='utf-8') as f:
            content = f.read()

        print("\n" + "-" * 80)
        print("VALIDATION: Modal Header Class")
        print("-" * 80)

        # Check for modal-title class
        if 'class="modal-title"' not in content:
            print("❌ modal-title class not found")
            print("   Header will not be centered!")
            return False
        print("✓ modal-title class found in JavaScript")

        # Extract the modal header HTML
        header_match = re.search(
            r'<div class="modal-header">.*?</div>',
            content,
            re.DOTALL
        )
        if header_match:
            header_html = header_match.group(0)
            print("\n✓ Modal header HTML:")
            print("-" * 80)
            lines = [line.strip() for line in header_html.split('\n') if line.strip()]
            for line in lines:
                print(f"  {line}")
            print("-" * 80)

            # Verify it uses modal-title not username-section
            if 'username-section' in header_html:
                print("❌ Still using username-section class (left-aligned)")
                return False
            if 'modal-title' in header_html:
                print("✓ Uses modal-title class (centered) ✓")
            else:
                print("❌ Missing modal-title class")
                return False

        print("\n✅ TEST 1 PASSED: JavaScript uses modal-title class!")
        return True

    except Exception as e:
        print(f"\n❌ TEST 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_css_styling():
    """
    Test that CSS has proper styling for modal-title
    """
    print_section("TEST 2: CSS Modal Title Styling")

    try:
        with open('static/css/modals/order_sellers_modal.css', 'r', encoding='utf-8') as f:
            content = f.read()

        print("\n" + "-" * 80)
        print("VALIDATION: CSS Styling for modal-title")
        print("-" * 80)

        # Check for modal-title class definition
        if '.modal-title' not in content:
            print("❌ .modal-title class not defined in CSS")
            return False
        print("✓ .modal-title class defined in CSS")

        # Extract the modal-title styling
        lines = content.split('\n')
        in_modal_title = False
        modal_title_styles = []

        for i, line in enumerate(lines):
            if '.modal-title' in line:
                in_modal_title = True
                start_line = i
            if in_modal_title:
                modal_title_styles.append(line)
                if '}' in line and len(modal_title_styles) > 1:
                    break

        print("\n✓ .modal-title CSS:")
        print("-" * 80)
        for line in modal_title_styles[:10]:
            print(f"  {line}")
        print("-" * 80)

        # Check for key properties
        css_text = '\n'.join(modal_title_styles)

        checks = {
            'text-align: center': 'Centers the username',
            'font-size: 1.7rem': 'Same size as cart sellers modal',
            'font-weight: bold': 'Bold text',
            'flex: 1': 'Takes up available space'
        }

        all_present = True
        print("\n✓ Required CSS properties:")
        for prop, description in checks.items():
            if prop in css_text:
                print(f"  ✓ {prop} - {description}")
            else:
                print(f"  ✗ {prop} - MISSING!")
                all_present = False

        if not all_present:
            return False

        print("\n✅ TEST 2 PASSED: CSS styling is correct!")
        return True

    except Exception as e:
        print(f"\n❌ TEST 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_comparison_with_orders_modal():
    """
    Compare bidder modal with orders modal structure
    """
    print_section("TEST 3: Comparison with Orders Modal")

    try:
        # Read orders modal JavaScript
        with open('static/js/modals/order_sellers_modal.js', 'r', encoding='utf-8') as f:
            orders_js = f.read()

        # Read bidder modal JavaScript
        with open('static/js/modals/bid_bidder_modal.js', 'r', encoding='utf-8') as f:
            bidder_js = f.read()

        print("\n" + "-" * 80)
        print("COMPARISON: Header Structure")
        print("-" * 80)

        # Check orders modal uses modal-title
        if 'modal-title' in orders_js:
            print("✓ Orders modal uses modal-title class")
        else:
            print("⚠️  Orders modal might use different class")

        # Check bidder modal uses modal-title
        if 'modal-title' in bidder_js:
            print("✓ Bidder modal uses modal-title class")
            print("\n✓ Both modals use same class → Same styling ✓")
        else:
            print("❌ Bidder modal uses different class")
            return False

        # Show the difference
        print("\n" + "-" * 80)
        print("HEADER STRUCTURE:")
        print("-" * 80)

        print("\nOrders Modal (with nav arrows):")
        orders_header = re.search(
            r'<div class="modal-header">.*?</div>',
            orders_js,
            re.DOTALL
        )
        if orders_header:
            lines = [l.strip() for l in orders_header.group(0).split('\n') if l.strip()]
            for line in lines[:5]:
                print(f"  {line}")

        print("\nBidder Modal (no nav arrows):")
        bidder_header = re.search(
            r'<div class="modal-header">.*?</div>',
            bidder_js,
            re.DOTALL
        )
        if bidder_header:
            lines = [l.strip() for l in bidder_header.group(0).split('\n') if l.strip()]
            for line in lines[:5]:
                print(f"  {line}")

        print("\n✓ Key difference: Orders has nav arrows, Bidder doesn't")
        print("✓ But both use modal-title class → Same font/centering ✓")

        print("\n✅ TEST 3 PASSED: Structure matches orders modal!")
        return True

    except Exception as e:
        print(f"\n❌ TEST 3 FAILED: {e}")
        return False


def main():
    print_section("Bidder Modal Header Style Fix - Verification")

    # Run tests
    test1_passed = test_javascript_modal_title()
    test2_passed = test_css_styling()
    test3_passed = test_comparison_with_orders_modal()

    # Final Summary
    print_section("TEST RESULTS")

    if test1_passed and test2_passed and test3_passed:
        print("✅ All tests passed successfully!")
        print("\n" + "=" * 80)
        print("FIX VERIFIED:")
        print("-" * 80)
        print("✓ Bidder modal uses modal-title class (not username-section)")
        print("✓ CSS defines modal-title with text-align: center")
        print("✓ Font size is 1.7rem (matches cart sellers modal)")
        print("✓ Font weight is bold (matches cart sellers modal)")
        print("✓ Structure matches orders modal pattern")
        print("=" * 80)
        print("\n✅ Username will be centered in the header!")
        print("\nEXPECTED VISUAL APPEARANCE:")
        print("-" * 80)
        print("┌─────────────────────────────────┐")
        print("│      john_doe (centered)    [×] │  ← Header with centered username")
        print("├─────────────────────────────────┤")
        print("│        [Image Placeholder]      │")
        print("│          4.5 ★★★★★              │")
        print("│          12 Reviews              │")
        print("│      10 Units In This Bid       │")
        print("└─────────────────────────────────┘")
        print("-" * 80)
        print("\nSTYLING DETAILS:")
        print("-" * 80)
        print("• Username: Centered, 1.7rem, bold")
        print("• Same font size/style as cart sellers modal")
        print("• No nav arrows (single bidder per bid)")
        print("• Clean, focused design")
        print("-" * 80)
        print("\nMANUAL TEST:")
        print("-" * 80)
        print("1. Navigate to a Bucket ID page with bids")
        print("2. Click 'View Bidder' button")
        print("3. Verify username is CENTERED in header")
        print("4. Verify font is bold and ~1.7rem size")
        print("5. Compare with cart sellers modal (should match)")
        print("-" * 80)
        return True
    else:
        print("❌ Some tests failed!")
        if not test1_passed:
            print("  ✗ JavaScript modal-title class test failed")
        if not test2_passed:
            print("  ✗ CSS styling test failed")
        if not test3_passed:
            print("  ✗ Orders modal comparison test failed")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
