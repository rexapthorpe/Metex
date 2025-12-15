"""
Diagnostic script to identify why the modal isn't appearing
"""

import re

print("=" * 80)
print("MODAL DIAGNOSTIC REPORT")
print("=" * 80)
print()

# 1. Check AJAX selector matches route URL
print("1. CHECKING AJAX SELECTOR vs ACTUAL ROUTE URL")
print("-" * 80)

with open('routes/buy_routes.py', 'r', encoding='utf-8') as f:
    content = f.read()
    route_match = re.search(r"@buy_bp\.route\('([^']+)'.*\n.*def auto_fill_bucket_purchase", content)
    if route_match:
        route_url = route_match.group(1)
        print(f"[OK] Route URL pattern: {route_url}")
        print(f"  Full URL will be: /buy{route_url.replace('<int:bucket_id>', '100000011')}")
    else:
        print("[ERROR] Could not find route definition")

with open('static/js/add_to_cart_ajax.js', 'r', encoding='utf-8') as f:
    content = f.read()
    selector_match = re.search(r'querySelectorAll\(["\']([^"\']+)["\']\)', content)
    if selector_match:
        selector = selector_match.group(1)
        print(f"[OK] AJAX selector: {selector}")

        if 'purchase_from_bucket' in selector:
            print("  [OK] Selector matches route URL pattern")
        else:
            print("  [ERROR] Selector DOES NOT match route URL pattern")
    else:
        print("[ERROR] Could not find selector in AJAX script")

print()

# 2. Check if Buy Item button has skipping logic
print("2. CHECKING BUY ITEM BUTTON ROUTE")
print("-" * 80)

with open('routes/checkout_routes.py', 'r', encoding='utf-8') as f:
    content = f.read()
    if 'user_listings_skipped' in content:
        print("[OK] checkout.checkout has user listings skipping logic")
    else:
        print("[ERROR] checkout.checkout MISSING user listings skipping logic")
        print("  This means 'Buy Item' button doesn't check for user's own listings")

    if 'seller_id' in content and 'user_id' in content:
        # Check if there's a filter excluding user's own listings
        has_filter = 'seller_id !=' in content or 'seller_id <>' in content
        if has_filter:
            print("[OK] checkout.checkout filters out user's own listings")
        else:
            print("[WARN] checkout.checkout might not filter user's own listings")
    else:
        print("[WARN] Could not determine if user listings are filtered")

print()

# 3. Check for window.showOwnListingsSkippedModal overwrite issue
print("3. CHECKING GLOBAL FUNCTION OVERWRITE ISSUE")
print("-" * 80)

with open('static/js/modals/own_listings_skipped_modal.js', 'r', encoding='utf-8') as f:
    content = f.read()
    if 'window.showOwnListingsSkippedModal = showOwnListingsSkippedModal' in content:
        print("[ERROR] FOUND BUG: Modal script overwrites window.showOwnListingsSkippedModal")
        print("  This replaces the boolean flag with the function")
        print("  The check 'if (window.showOwnListingsSkippedModal === true)' will always fail")
    else:
        print("[OK] No global function overwrite found")

print()

# 4. Summary
print("4. SUMMARY OF ISSUES")
print("-" * 80)

issues = []
fixes = []

# Check selector issue
with open('static/js/add_to_cart_ajax.js', 'r', encoding='utf-8') as f:
    if 'auto_fill_bucket_purchase' in f.read():
        issues.append("AJAX selector uses 'auto_fill_bucket_purchase' but route uses 'purchase_from_bucket'")
        fixes.append("Update selector in add_to_cart_ajax.js to 'purchase_from_bucket'")

# Check Buy Item route
with open('routes/checkout_routes.py', 'r', encoding='utf-8') as f:
    if 'user_listings_skipped' not in f.read():
        issues.append("Buy Item button (checkout route) missing user listings skip logic")
        fixes.append("Add user listings filtering and AJAX response to checkout_routes.py")

# Check function overwrite
with open('static/js/modals/own_listings_skipped_modal.js', 'r', encoding='utf-8') as f:
    if 'window.showOwnListingsSkippedModal = showOwnListingsSkippedModal' in f.read():
        issues.append("Modal script overwrites boolean flag with function")
        fixes.append("Rename global functions to avoid overwriting flag (e.g., showOwnListingsSkippedModalFunc)")

if issues:
    print(f"Found {len(issues)} issue(s):")
    for i, issue in enumerate(issues, 1):
        print(f"  {i}. {issue}")
    print()
    print("Recommended fixes:")
    for i, fix in enumerate(fixes, 1):
        print(f"  {i}. {fix}")
else:
    print("[OK] No issues found!")

print()
print("=" * 80)
