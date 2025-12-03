"""
Test script to verify Sell form validation fix
Checks that:
1. item_photo field no longer has 'required' attribute in HTML
2. JavaScript validation still checks for photo
3. Form can be submitted without browser blocking
"""

import re

def test_item_photo_not_required():
    """Test that item_photo field does not have required attribute"""
    print("\n" + "="*60)
    print("TEST 1: Verify item_photo field does not have 'required'")
    print("="*60)

    with open('templates/sell.html', 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the item_photo input element
    photo_input_pattern = r'<input[^>]*name="item_photo"[^>]*>'
    match = re.search(photo_input_pattern, content, re.DOTALL)

    if match:
        photo_input = match.group(0)
        print(f"\nFound item_photo input:\n{photo_input}\n")

        # Check if 'required' attribute is present
        has_required = 'required' in photo_input.lower()
        has_display_none = 'display: none' in photo_input or 'display:none' in photo_input

        if has_required:
            print("[FAIL]: item_photo still has 'required' attribute")
            print("        This will cause 'invalid form control not focusable' error")
            return False
        else:
            print("[PASS]: item_photo does NOT have 'required' attribute")

        if has_display_none:
            print("[PASS]: item_photo is hidden (display: none)")
        else:
            print("[WARN]: item_photo might not be hidden")

        return True
    else:
        print("[FAIL]: Could not find item_photo input in sell.html")
        return False

def test_javascript_validation_includes_photo():
    """Test that JavaScript validation still checks for photo"""
    print("\n" + "="*60)
    print("TEST 2: Verify JavaScript validation includes item_photo")
    print("="*60)

    with open('static/js/modals/field_validation_modal.js', 'r', encoding='utf-8') as f:
        content = f.read()

    # Check if item_photo is in base required fields
    has_item_photo = "'item_photo'" in content or '"item_photo"' in content

    # Check if file input validation exists
    has_file_validation = "field.type === 'file'" in content
    has_files_check = "field.files" in content and "field.files.length" in content

    print(f"\nChecking field_validation_modal.js...")

    if has_item_photo:
        print("[PASS]: 'item_photo' found in validation script")
    else:
        print("[FAIL]: 'item_photo' NOT found in validation script")
        return False

    if has_file_validation:
        print("[PASS]: File input validation logic exists")
    else:
        print("[FAIL]: File input validation logic NOT found")
        return False

    if has_files_check:
        print("[PASS]: File count check exists (field.files.length)")
    else:
        print("[FAIL]: File count check NOT found")
        return False

    return True

def test_pricing_mode_validation():
    """Test that pricing mode validation is correct"""
    print("\n" + "="*60)
    print("TEST 3: Verify pricing mode-aware validation")
    print("="*60)

    with open('static/js/modals/field_validation_modal.js', 'r', encoding='utf-8') as f:
        content = f.read()

    print(f"\nChecking field_validation_modal.js...")

    # Check for pricing mode detection
    has_static_radio_check = "pricing_mode_static" in content
    has_premium_radio_check = "pricing_mode_premium" in content

    # Check for conditional field requirements
    has_price_per_coin_push = "requiredFields.push('price_per_coin')" in content
    has_spot_premium_push = "requiredFields.push('spot_premium')" in content
    has_floor_price_push = "requiredFields.push('floor_price')" in content

    if has_static_radio_check and has_premium_radio_check:
        print("[PASS]: Pricing mode radio button checks exist")
    else:
        print("[FAIL]: Pricing mode detection NOT found")
        return False

    if has_price_per_coin_push:
        print("[PASS]: Conditional price_per_coin validation exists")
    else:
        print("[FAIL]: price_per_coin conditional validation NOT found")
        return False

    if has_spot_premium_push and has_floor_price_push:
        print("[PASS]: Conditional premium-to-spot validation exists")
    else:
        print("[FAIL]: Premium-to-spot conditional validation NOT found")
        return False

    return True

def test_form_interception():
    """Test that form submission is properly intercepted"""
    print("\n" + "="*60)
    print("TEST 4: Verify form submission interception")
    print("="*60)

    with open('static/js/modals/sell_listing_modals.js', 'r', encoding='utf-8') as f:
        content = f.read()

    print(f"\nChecking sell_listing_modals.js...")

    # Check for form interception
    has_submit_listener = "addEventListener('submit'" in content
    has_prevent_default = "e.preventDefault()" in content
    has_validation_call = "validateSellForm" in content
    has_modal_opening = "openSellConfirmModal" in content

    if has_submit_listener:
        print("[PASS]: Form submit event listener exists")
    else:
        print("[FAIL]: Form submit listener NOT found")
        return False

    if has_prevent_default:
        print("[PASS]: preventDefault() call exists")
    else:
        print("[FAIL]: preventDefault() NOT found")
        return False

    if has_validation_call:
        print("[PASS]: validateSellForm() call exists")
    else:
        print("[FAIL]: validateSellForm() call NOT found")
        return False

    if has_modal_opening:
        print("[PASS]: openSellConfirmModal() call exists")
    else:
        print("[FAIL]: openSellConfirmModal() call NOT found")
        return False

    return True

def run_all_tests():
    """Run all validation tests"""
    print("\n" + "="*70)
    print("SELL FORM VALIDATION FIX - VERIFICATION TESTS")
    print("="*70)

    results = []

    # Run tests
    results.append(("Item photo not required", test_item_photo_not_required()))
    results.append(("JavaScript validates photo", test_javascript_validation_includes_photo()))
    results.append(("Pricing mode validation", test_pricing_mode_validation()))
    results.append(("Form interception", test_form_interception()))

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n[SUCCESS] ALL TESTS PASSED - Sell form validation fix is complete!")
        print("\nNext steps:")
        print("1. Navigate to http://127.0.0.1:5000/sell")
        print("2. Test static listing creation")
        print("3. Test premium-to-spot listing creation")
        print("4. Verify no console errors appear")
        print("5. Confirm confirmation modal appears")
        print("6. Verify listings can be created successfully")
    else:
        print("\n[ERROR] SOME TESTS FAILED - Please review the failures above")

    return passed == total

if __name__ == "__main__":
    import os
    import sys

    # Change to Metex directory
    metex_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(metex_dir)

    success = run_all_tests()
    sys.exit(0 if success else 1)
