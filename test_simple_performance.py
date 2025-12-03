"""
Simple performance test - just measure dropdown options loading
"""
import time
import sys

# Test 1: How long does it take to load dropdown options?
print("Testing dropdown options loading...")
start = time.time()

from routes.category_options import get_dropdown_options

options = get_dropdown_options()
load_time = time.time() - start

print(f"✓ Dropdown options loaded in {load_time:.4f}s")
print("\nOption counts:")
for key, values in options.items():
    print(f"  - {key}: {len(values)} options")

# Test 2: How long does template rendering take with these options?
print("\n" + "="*60)
print("Testing template rendering...")
from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader('templates'))
template = env.get_template('modals/edit_listing_modal.html')

# Create dummy listing data
dummy_listing = {
    'listing_id': 1,
    'quantity': 10,
    'price_per_coin': 25.50,
    'graded': 1,
    'grading_service': 'PCGS',
    'photo_path': None,
    'metal': 'Gold',
    'product_line': 'American Eagle',
    'product_type': 'Coin',
    'purity': '.9999',
    'weight': '1 oz',
    'mint': 'US Mint',
    'year': '2025',
    'finish': 'Proof',
    'grade': 'MS-70'
}

start = time.time()
html = template.render(
    listing=dummy_listing,
    metals=options['metals'],
    product_lines=options['product_lines'],
    product_types=options['product_types'],
    special_designations=[],
    purities=options['purities'],
    weights=options['weights'],
    mints=options['mints'],
    years=options['years'],
    finishes=options['finishes'],
    grades=options['grades'],
    grading_services=['PCGS', 'NGC', 'ANACS', 'ICG']
)
render_time = time.time() - start

print(f"✓ Template rendered in {render_time:.4f}s")
print(f"  HTML size: {len(html):,} characters ({len(html)/1024:.1f} KB)")

# Count datalist options in the HTML
datalist_count = html.count('<option value=')
print(f"  Total <option> elements: {datalist_count:,}")

# Total
total = load_time + render_time
print("\n" + "="*60)
print(f"TOTAL: {total:.4f}s")
print("="*60)

if total > 0.5:
    print(f"\n⚠ SLOW: {total:.4f}s > 0.5s threshold")
    print("\nBottleneck analysis:")
    if render_time > load_time:
        print(f"  • Template rendering is slow ({render_time:.4f}s)")
        print(f"    - {datalist_count} option elements is too many")
        print(f"    - Consider lazy-loading dropdowns via JavaScript")
    else:
        print(f"  • Dropdown loading is slow ({load_time:.4f}s)")
        print(f"    - Consider caching or reducing DB queries")
else:
    print(f"\n✓ FAST: {total:.4f}s is acceptable")
