"""
Fix modal JavaScript files to use scoped queries instead of document.getElementById
This prevents duplicate ID conflicts when multiple modals are on the same page.
"""

import re
import os

# Files to fix
modal_files = [
    'static/js/modals/bid_confirm_modal.js',
    'static/js/modals/buy_item_modal.js',
    'static/js/modals/checkout_modals.js',
    'static/js/modals/edit_listing_confirmation_modals.js',
    'static/js/modals/sell_listing_modals.js'
]

# Modal ID mappings (function name pattern -> modal ID)
modal_mappings = {
    r'function\s+openBidSuccessModal': 'bidSuccessModal',
    r'function\s+openBuyItemSuccessModal': 'buyItemSuccessModal',
    r'function\s+openCheckoutSuccessModal': 'checkoutSuccessModal',
    r'function\s+openEditListingSuccessModal': 'editListingSuccessModal',
    r'function\s+openSellListingSuccessModal': 'sellListingSuccessModal',
}

def fix_file(filepath):
    """Fix a single modal JavaScript file"""
    if not os.path.exists(filepath):
        print(f"  File not found: {filepath}")
        return False

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content
    changes_made = False

    # For each success modal function
    for func_pattern, modal_id in modal_mappings.items():
        # Find the function
        func_match = re.search(func_pattern, content)
        if not func_match:
            continue

        # Find the function body (find matching braces)
        func_start = func_match.start()

        # Check if modal variable is already defined
        if f"getElementById('{modal_id}')" not in content[func_start:func_start+1000]:
            continue

        print(f"  Found function for {modal_id}")

        # Find where the modal variable is defined
        modal_var_pattern = rf"const\s+modal\s*=\s*document\.getElementById\('{modal_id}'\)"
        modal_var_match = re.search(modal_var_pattern, content[func_start:])

        if not modal_var_match:
            continue

        # Find the end of this function (simplified: find next 'function' or end of file)
        next_func = re.search(r'\nfunction\s+', content[func_start + 100:])
        func_end = (func_start + 100 + next_func.start()) if next_func else len(content)

        function_body = content[func_start:func_end]

        # Replace document.getElementById with modal.querySelector in this function body
        # Match: document.getElementById('success-...')
        def replace_get_by_id(match):
            element_id = match.group(1)
            return f"modal.querySelector('#{element_id}')"

        modified_body = re.sub(
            r"document\.getElementById\('(success-[^']+)'\)",
            replace_get_by_id,
            function_body
        )

        if modified_body != function_body:
            content = content[:func_start] + modified_body + content[func_end:]
            changes_made = True
            print(f"    Scoped queries in {func_pattern}")

    # Write back if changes were made
    if changes_made:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  FIXED: {filepath}")
        return True
    else:
        print(f"  No changes needed: {filepath}")
        return False

def main():
    print("Fixing modal scoping issues...\n")

    fixed_count = 0
    for filepath in modal_files:
        print(f"Processing: {filepath}")
        if fix_file(filepath):
            fixed_count += 1
        print()

    print(f"\nFixed {fixed_count} out of {len(modal_files)} files")

if __name__ == '__main__':
    main()
