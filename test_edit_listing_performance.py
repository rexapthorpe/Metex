"""
Test script to measure edit_listing modal loading performance
"""
import time
import sqlite3
from database import get_db_connection
from routes.category_options import get_dropdown_options
from jinja2 import Environment, FileSystemLoader

# Set up Jinja2 environment
env = Environment(loader=FileSystemLoader('templates'))

def test_edit_listing_performance():
    print("=" * 60)
    print("TESTING EDIT LISTING MODAL PERFORMANCE")
    print("=" * 60)

    total_start = time.time()

    # 1. Test database query for listing
    query_start = time.time()
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        listing = conn.execute(
            '''
            SELECT
                l.id          AS listing_id,
                l.quantity,
                l.price_per_coin,
                l.graded      AS graded,
                l.grading_service,
                lp.file_path  AS photo_path,
                c.id          AS category_id,
                c.metal,
                c.product_line,
                c.product_type,
                c.purity,
                c.weight,
                c.mint,
                c.year,
                c.finish,
                c.grade
            FROM listings l
            JOIN categories c       ON l.category_id = c.id
            LEFT JOIN listing_photos lp ON lp.listing_id = l.id
            WHERE l.id = ? AND l.seller_id = ?
            LIMIT 1
            ''',
            (1, 1)  # Test with listing ID 1, user ID 1
        ).fetchone()
    query_time = time.time() - query_start
    print(f"\n1. Listing Query: {query_time:.4f}s")

    if not listing:
        print("ERROR: No listing found with ID 1 for user 1")
        # Try to find any listing
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            any_listing = conn.execute('SELECT id, seller_id FROM listings LIMIT 1').fetchone()
            if any_listing:
                print(f"   Found listing ID {any_listing['id']} with seller {any_listing['seller_id']}")
                print("   Retrying with this listing...")
                listing = conn.execute(
                    '''
                    SELECT
                        l.id          AS listing_id,
                        l.quantity,
                        l.price_per_coin,
                        l.graded      AS graded,
                        l.grading_service,
                        lp.file_path  AS photo_path,
                        c.id          AS category_id,
                        c.metal,
                        c.product_line,
                        c.product_type,
                        c.purity,
                        c.weight,
                        c.mint,
                        c.year,
                        c.finish,
                        c.grade
                    FROM listings l
                    JOIN categories c       ON l.category_id = c.id
                    LEFT JOIN listing_photos lp ON lp.listing_id = l.id
                    WHERE l.id = ?
                    ''',
                    (any_listing['id'],)
                ).fetchone()

    # 2. Test dropdown options loading
    options_start = time.time()
    options = get_dropdown_options()
    options_time = time.time() - options_start
    print(f"2. Dropdown Options: {options_time:.4f}s")

    # Print option counts
    print("   Dropdown counts:")
    for key, values in options.items():
        print(f"   - {key}: {len(values)} options")

    # 3. Test template rendering
    template_start = time.time()
    template = env.get_template('modals/edit_listing_modal.html')
    grading_services = ['PCGS', 'NGC', 'ANACS', 'ICG']

    html = template.render(
        listing=listing,
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
        grading_services=grading_services
    )
    template_time = time.time() - template_start
    print(f"3. Template Rendering: {template_time:.4f}s")
    print(f"   HTML size: {len(html):,} characters")

    # Total time
    total_time = time.time() - total_start
    print(f"\n{'='*60}")
    print(f"TOTAL TIME: {total_time:.4f}s")
    print(f"{'='*60}")

    # Identify bottleneck
    slowest = max(
        [('Query', query_time), ('Dropdown Options', options_time), ('Template Render', template_time)],
        key=lambda x: x[1]
    )
    print(f"\nBOTTLENECK: {slowest[0]} ({slowest[1]:.4f}s)")

    # Performance threshold
    if total_time > 0.5:
        print(f"\n⚠ WARNING: Total time {total_time:.4f}s exceeds 0.5s threshold")
    else:
        print(f"\n✓ PASS: Total time {total_time:.4f}s is acceptable")

    return {
        'query_time': query_time,
        'options_time': options_time,
        'template_time': template_time,
        'total_time': total_time,
        'html_size': len(html)
    }

if __name__ == '__main__':
    test_edit_listing_performance()
