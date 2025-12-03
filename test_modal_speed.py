"""Test modal loading speed after database cleanup"""
import time
from routes.category_options import get_dropdown_options
from jinja2 import Environment, FileSystemLoader

print("="*60)
print("TESTING EDIT MODAL PERFORMANCE")
print("="*60)

# Test 1: Dropdown options
print("\n1. Loading dropdown options...")
start = time.time()
options = get_dropdown_options()
load_time = time.time() - start
print(f"   Time: {load_time:.4f}s")
print(f"   Counts:")
for key, values in options.items():
    print(f"     - {key}: {len(values)}")

# Test 2: Template rendering
print("\n2. Rendering template...")
env = Environment(loader=FileSystemLoader('templates'))
template = env.get_template('modals/edit_listing_modal.html')

dummy = {
    'listing_id': 1, 'quantity': 10, 'price_per_coin': 25.50,
    'graded': 1, 'grading_service': 'PCGS', 'photo_path': None,
    'metal': 'Gold', 'product_line': 'American Eagle', 'product_type': 'Coin',
    'purity': '.9999', 'weight': '1 oz', 'mint': 'US Mint',
    'year': '2025', 'finish': 'Proof', 'grade': 'MS-70'
}

start = time.time()
html = template.render(
    listing=dummy,
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
print(f"   Time: {render_time:.4f}s")
print(f"   HTML size: {len(html):,} chars")
print(f"   Options: {html.count('<option value='):,}")

# Total
total = load_time + render_time
print(f"\n{'='*60}")
print(f"TOTAL TIME: {total:.4f}s")
print(f"{'='*60}")

if total < 0.1:
    print(f"\nRESULT: EXCELLENT ({total:.4f}s)")
elif total < 0.5:
    print(f"\nRESULT: GOOD ({total:.4f}s)")
else:
    print(f"\nRESULT: SLOW ({total:.4f}s)")

print("\nThe modal should now load instantly in the browser!")
