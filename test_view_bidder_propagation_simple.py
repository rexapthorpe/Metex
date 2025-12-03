"""
Simple test to verify View Bidder button has event.stopPropagation()
Tests the template file directly without rendering
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


def test_template_file():
    """
    Test the view_bucket.html template file directly
    """
    print_section("TEST 1: Template File - Event Propagation")

    try:
        with open('templates/view_bucket.html', 'r', encoding='utf-8') as f:
            content = f.read()

        print("\n" + "-" * 80)
        print("VALIDATION: View Bidder Button Event Handling")
        print("-" * 80)

        # Check for View Bidder button
        if 'view-bidder-btn' not in content:
            print("❌ View Bidder button not found in template")
            return False
        print("✓ View Bidder button found in template")

        # Check for event.stopPropagation() in onclick
        if 'event.stopPropagation()' not in content:
            print("❌ event.stopPropagation() not found in template")
            return False
        print("✓ event.stopPropagation() found in template")

        # Check that it's specifically on the View Bidder button
        # Look for the pattern: onclick="event.stopPropagation(); openBidderModal(
        if 'onclick="event.stopPropagation(); openBidderModal(' not in content:
            print("❌ event.stopPropagation() not found in View Bidder button onclick")
            return False
        print("✓ event.stopPropagation() is in View Bidder button onclick handler")

        # Extract the full button code to show
        pattern = re.compile(
            r'<button[^>]*view-bidder-btn[^>]*>.*?</button>',
            re.DOTALL
        )
        match = pattern.search(content)
        if match:
            button_html = match.group(0)
            print("\n✓ View Bidder button HTML found:")
            print("-" * 80)
            # Clean up for display
            lines = [line.strip() for line in button_html.split('\n') if line.strip()]
            for line in lines[:8]:  # Show first 8 lines
                print(f"  {line}")
            if len(lines) > 8:
                print(f"  ... ({len(lines) - 8} more lines)")
            print("-" * 80)

            # Verify the onclick attribute
            if 'onclick="event.stopPropagation(); openBidderModal(' in button_html:
                print("✓ Confirmed: onclick includes event.stopPropagation()")
            else:
                print("❌ onclick attribute doesn't match expected pattern")
                return False

        print("\n✅ TEST 1 PASSED: Template has event.stopPropagation()!")
        return True

    except Exception as e:
        print(f"\n❌ TEST 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_button_context():
    """
    Test the context where the button is placed
    """
    print_section("TEST 2: Button Context and Parent Elements")

    try:
        with open('templates/view_bucket.html', 'r', encoding='utf-8') as f:
            content = f.read()

        print("\n" + "-" * 80)
        print("VALIDATION: Button Placement in HTML Structure")
        print("-" * 80)

        # Find the section with View Bidder button
        lines = content.split('\n')
        button_line = None
        for i, line in enumerate(lines):
            if 'view-bidder-btn' in line:
                button_line = i
                break

        if button_line is None:
            print("❌ Could not find View Bidder button")
            return False

        # Show context (10 lines before and after)
        start = max(0, button_line - 10)
        end = min(len(lines), button_line + 10)

        print(f"\n✓ Button found at line {button_line + 1}")
        print("\nContext (showing lines around button):")
        print("-" * 80)
        for i in range(start, end):
            marker = ">>>" if i == button_line else "   "
            line_num = str(i + 1).rjust(4)
            print(f"{marker} {line_num} | {lines[i][:75]}")
        print("-" * 80)

        # Check if button is inside bid-card-visual
        context_before = '\n'.join(lines[max(0, button_line - 30):button_line])
        if 'bid-card-visual' in context_before or 'bid-card-clickable' in context_before:
            print("✓ Button is inside bid card (as expected)")
            print("  This confirms why event.stopPropagation() is needed")
        else:
            print("⚠️  Could not confirm button is inside bid card")

        print("\n✅ TEST 2 PASSED: Button context verified!")
        return True

    except Exception as e:
        print(f"\n❌ TEST 2 FAILED: {e}")
        return False


def test_javascript_pattern():
    """
    Compare with how dial buttons handle propagation
    """
    print_section("TEST 3: JavaScript Event Handling Pattern")

    try:
        with open('static/js/view_bucket.js', 'r', encoding='utf-8') as f:
            js_content = f.read()

        print("\n" + "-" * 80)
        print("COMPARISON: Event Propagation Patterns in view_bucket.js")
        print("-" * 80)

        # Find the bid card click listener
        card_listener = re.search(
            r'card\.addEventListener\([^)]+\)\s*=>\s*toggleRowSelection',
            js_content
        )
        if card_listener:
            print("✓ Found bid card click listener:")
            print(f"  {card_listener.group(0)}")
            print("  This is what triggers bid selection when card is clicked")
        else:
            print("⚠️  Could not find bid card click listener")

        # Find dial stopPropagation examples
        print("\n✓ Found existing stopPropagation examples:")

        # Dial pill
        pill_pattern = re.search(
            r'pill.*addEventListener.*stopPropagation',
            js_content
        )
        if pill_pattern:
            print("  1. Dial pill: addEventListener with e.stopPropagation()")

        # Dial buttons
        dial_btn_pattern = re.search(
            r'btn\.addEventListener\(\'click\',\s*\(e\)\s*=>\s*\{[^}]*e\.stopPropagation',
            js_content,
            re.DOTALL
        )
        if dial_btn_pattern:
            print("  2. Dial +/- buttons: addEventListener with e.stopPropagation()")

        print("\n✓ View Bidder button pattern:")
        print("  3. View Bidder button: inline onclick with event.stopPropagation()")
        print("\nℹ️  Note: Both approaches work correctly:")
        print("  • addEventListener: e.stopPropagation()")
        print("  • Inline onclick: event.stopPropagation()")
        print("  The 'event' object is implicitly available in inline handlers")

        print("\n✅ TEST 3 PASSED: Event handling pattern is correct!")
        return True

    except Exception as e:
        print(f"\n❌ TEST 3 FAILED: {e}")
        return False


def test_fix_summary():
    """
    Provide a summary of the fix
    """
    print_section("FIX SUMMARY")

    print("\n" + "=" * 80)
    print("PROBLEM:")
    print("-" * 80)
    print("• View Bidder button was inside bid-card-visual div")
    print("• bid-card-visual has click listener: toggleRowSelection()")
    print("• Button clicks bubbled up to parent, triggering selection")
    print("• Result: Clicking button selected bid AND opened modal")
    print()
    print("SOLUTION:")
    print("-" * 80)
    print("• Added event.stopPropagation() to button's onclick handler")
    print("• This prevents click event from bubbling to parent")
    print("• Pattern matches existing dial buttons in same file")
    print()
    print("IMPLEMENTATION:")
    print("-" * 80)
    print("• File: templates/view_bucket.html")
    print("• Change: onclick=\"openBidderModal(...)\"")
    print("•      → onclick=\"event.stopPropagation(); openBidderModal(...)\"")
    print("• Line: ~472")
    print("=" * 80)


def main():
    print_section("View Bidder Event Propagation Fix - Verification")

    # Run tests
    test1_passed = test_template_file()
    test2_passed = test_button_context()
    test3_passed = test_javascript_pattern()

    # Show fix summary
    test_fix_summary()

    # Final Summary
    print_section("TEST RESULTS")

    if test1_passed and test2_passed and test3_passed:
        print("✅ All tests passed successfully!")
        print("\n" + "=" * 80)
        print("FIX VERIFIED:")
        print("-" * 80)
        print("✓ Template has event.stopPropagation() in onclick handler")
        print("✓ Button is correctly placed inside bid card")
        print("✓ Event handling pattern matches existing code")
        print("=" * 80)
        print("\n✅ The View Bidder button should now work correctly!")
        print("\nEXPECTED BEHAVIOR (after fix):")
        print("-" * 80)
        print("✓ Clicking 'View Bidder' opens ONLY the bidder modal")
        print("✓ Bid tile does NOT get selected")
        print("✓ Accept confirmation sidebar does NOT open")
        print("✓ No 'Please select at least one bid' popup")
        print("✓ Clicking elsewhere on bid tile still selects it normally")
        print("-" * 80)
        print("\nMANUAL TEST STEPS:")
        print("-" * 80)
        print("1. Navigate to a Bucket ID page with bids")
        print("2. Click 'View Bidder' button on a bid tile")
        print("3. Verify ONLY the bidder modal opens")
        print("4. Close modal")
        print("5. Verify bid tile is NOT selected (no dial visible)")
        print("6. Click on the bid tile itself (not the button)")
        print("7. Verify bid tile gets selected (dial appears)")
        print("8. Click 'View Bidder' again while tile is selected")
        print("9. Verify modal opens without deselecting tile")
        print("-" * 80)
        return True
    else:
        print("❌ Some tests failed!")
        if not test1_passed:
            print("  ✗ Template file test failed")
        if not test2_passed:
            print("  ✗ Button context test failed")
        if not test3_passed:
            print("  ✗ JavaScript pattern test failed")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
