#!/usr/bin/env python3
"""
Test script to verify that sell modal corners have proper border-radius of 20px.
This simulates checking the CSS to ensure both the modal dialog and headers have rounded corners.
"""

import os
import re

def test_border_radius():
    """Test that all modal elements have correct border-radius"""

    print("=" * 70)
    print("SELL MODAL CORNERS VERIFICATION TEST")
    print("=" * 70)
    print()

    css_file = "static/css/modals/sell_listing_modals.css"

    if not os.path.exists(css_file):
        print(f"[ERROR] CSS file not found: {css_file}")
        return False

    with open(css_file, 'r', encoding='utf-8') as f:
        css_content = f.read()

    tests = []
    all_passed = True

    # Test 1: Modal dialog has 20px border-radius
    print("Test 1: Checking .slide-up-modal-dialog border-radius...")
    dialog_pattern = r'\.slide-up-modal-dialog\s*\{[^}]*border-radius:\s*20px\s+20px\s+0\s+0'
    if re.search(dialog_pattern, css_content, re.MULTILINE | re.DOTALL):
        print("  [OK] Modal dialog has border-radius: 20px 20px 0 0")
        tests.append(("Modal Dialog Border-Radius", True))
    else:
        print("  [FAIL] Modal dialog missing border-radius: 20px 20px 0 0")
        tests.append(("Modal Dialog Border-Radius", False))
        all_passed = False

    print()

    # Test 2: Regular modal header has 20px border-radius
    print("Test 2: Checking .modal-header border-radius...")
    header_pattern = r'\.slide-up-modal-dialog\s+\.modal-header\s*\{[^}]*border-radius:\s*20px\s+20px\s+0\s+0'
    if re.search(header_pattern, css_content, re.MULTILINE | re.DOTALL):
        print("  [OK] Modal header has border-radius: 20px 20px 0 0")
        tests.append(("Modal Header Border-Radius", True))
    else:
        print("  [FAIL] Modal header missing border-radius: 20px 20px 0 0")
        tests.append(("Modal Header Border-Radius", False))
        all_passed = False

    print()

    # Test 3: Success header has 20px border-radius
    print("Test 3: Checking .success-header border-radius...")
    success_pattern = r'\.slide-up-modal-dialog\s+\.modal-header\.success-header\s*\{[^}]*border-radius:\s*20px\s+20px\s+0\s+0'
    if re.search(success_pattern, css_content, re.MULTILINE | re.DOTALL):
        print("  [OK] Success header has border-radius: 20px 20px 0 0")
        tests.append(("Success Header Border-Radius", True))
    else:
        print("  [FAIL] Success header missing border-radius: 20px 20px 0 0")
        tests.append(("Success Header Border-Radius", False))
        all_passed = False

    print()

    # Test 4: Responsive modal has 20px border-radius
    print("Test 4: Checking responsive @media border-radius...")
    responsive_pattern = r'@media\s*\([^)]*max-width:\s*768px[^)]*\)[^{]*\{[^}]*\.slide-up-modal-dialog\s*\{[^}]*border-radius:\s*20px\s+20px\s+0\s+0'
    if re.search(responsive_pattern, css_content, re.MULTILINE | re.DOTALL):
        print("  [OK] Responsive modal has border-radius: 20px 20px 0 0")
        tests.append(("Responsive Modal Border-Radius", True))
    else:
        print("  [FAIL] Responsive modal missing border-radius: 20px 20px 0 0")
        tests.append(("Responsive Modal Border-Radius", False))
        all_passed = False

    print()
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    for test_name, passed in tests:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {test_name}")

    print()

    if all_passed:
        print("✓ ALL TESTS PASSED - Modal corners should be rounded!")
        print()
        print("What was fixed:")
        print("1. .slide-up-modal-dialog - border-radius: 20px 20px 0 0")
        print("2. .modal-header - border-radius: 20px 20px 0 0")
        print("3. .success-header - border-radius: 20px 20px 0 0 (clips gradient)")
        print("4. Responsive @media - border-radius: 20px 20px 0 0")
        print()
        print("The success modal's gradient background will now properly clip")
        print("to the rounded corners, eliminating the sharp corner issue!")
        return True
    else:
        print("✗ SOME TESTS FAILED - Please review the fixes")
        return False

if __name__ == "__main__":
    success = test_border_radius()
    exit(0 if success else 1)
