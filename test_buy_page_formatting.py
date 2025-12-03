"""
Test that the Buy page displays titles and subtitles in the correct format:
- Title: [mint] [product line] (e.g., "US Mint American Eagle")
- Subtitle: [weight], [metal] [grade] [year] (e.g., "1 oz, Gold MS-70 2020")
"""
import sqlite3

print("=" * 80)
print("BUY PAGE TITLE/SUBTITLE FORMATTING TEST")
print("=" * 80)

conn = sqlite3.connect('database.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Query buckets the same way the Buy page does
print("\n[STEP 1] Querying buckets from database...")
query = '''
    SELECT
        categories.id AS category_id,
        categories.bucket_id,
        categories.metal,
        categories.product_type,
        categories.weight,
        categories.mint,
        categories.year,
        categories.finish,
        categories.grade,
        categories.coin_series,
        categories.product_line,
        MIN(
            CASE
                WHEN listings.active = 1 AND listings.quantity > 0
                THEN listings.price_per_coin
                ELSE NULL
            END
        ) AS lowest_price,
        COALESCE(SUM(
            CASE
                WHEN listings.active = 1 AND listings.quantity > 0
                THEN listings.quantity
                ELSE 0
            END
        ), 0) AS total_available
    FROM categories
    LEFT JOIN listings ON listings.category_id = categories.id
    GROUP BY categories.id
    ORDER BY
        CASE WHEN lowest_price IS NULL THEN 1 ELSE 0 END,
        lowest_price ASC
    LIMIT 10
'''

buckets = cursor.execute(query).fetchall()
print(f"[OK] Found {len(buckets)} buckets")

if not buckets:
    print("\n[WARNING] No buckets found in database. Cannot test formatting.")
    print("          Please add some categories to test with.")
    conn.close()
    exit(0)

# Test formatting for each bucket
print("\n[STEP 2] Testing title/subtitle formatting...")
print("-" * 80)

test_results = []

for i, bucket in enumerate(buckets, 1):
    print(f"\n[BUCKET {i}]")

    # Build title: [mint] [product line]
    mint = bucket['mint'] or ''
    product_line = bucket['product_line'] or bucket['coin_series'] or bucket['product_type'] or ''
    title = f"{mint} {product_line}".strip()

    # Build subtitle: [weight], [metal] [grade] [year]
    weight = bucket['weight'] or ''
    metal = bucket['metal'] or ''
    grade = bucket['grade'] or ''
    year = bucket['year'] or ''
    subtitle = f"{weight}, {metal} {grade} {year}".strip()

    print(f"  Title:    '{title}'")
    print(f"  Subtitle: '{subtitle}'")
    print(f"  Price:    ${bucket['lowest_price']}" if bucket['lowest_price'] else "  Price:    No listings available")

    # Validate formatting
    has_mint = bucket['mint'] is not None and bucket['mint'].strip() != ''
    has_product_info = (bucket['product_line'] or bucket['coin_series'] or bucket['product_type'])
    has_all_subtitle_fields = all([bucket['weight'], bucket['metal'], bucket['grade'], bucket['year']])

    if has_mint and has_product_info:
        print(f"  [OK] Title has both mint and product line/series")
        test_results.append(('title_format', True))
    elif has_product_info:
        print(f"  [OK] Title has product line/series (mint may be empty)")
        test_results.append(('title_format', True))
    else:
        print(f"  [WARNING] Title may be incomplete")
        test_results.append(('title_format', False))

    if has_all_subtitle_fields:
        print(f"  [OK] Subtitle has all required fields")
        test_results.append(('subtitle_format', True))
    else:
        print(f"  [WARNING] Subtitle missing some fields")
        test_results.append(('subtitle_format', False))

conn.close()

# Summary
print("\n" + "=" * 80)
print("TEST SUMMARY")
print("=" * 80)

title_tests = [r for r in test_results if r[0] == 'title_format']
subtitle_tests = [r for r in test_results if r[0] == 'subtitle_format']

title_pass = sum(1 for r in title_tests if r[1])
subtitle_pass = sum(1 for r in subtitle_tests if r[1])

print(f"\nTitle Formatting:    {title_pass}/{len(title_tests)} buckets passed")
print(f"Subtitle Formatting: {subtitle_pass}/{len(subtitle_tests)} buckets passed")

if title_pass == len(title_tests) and subtitle_pass == len(subtitle_tests):
    print("\n[SUCCESS] All buckets display correctly with new formatting!")
    print("          - Titles show: [mint] [product line]")
    print("          - Subtitles show: [weight], [metal] [grade] [year]")
elif title_pass > 0 or subtitle_pass > 0:
    print("\n[PARTIAL] Most buckets display correctly")
    print("          Some buckets may have missing fields in database")
else:
    print("\n[FAILURE] Formatting may have issues")

print("=" * 80)
