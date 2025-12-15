"""
Fix listings that reference deleted categories by recreating the categories
"""

from database import get_db_connection
from utils.category_manager import get_or_create_category
import sqlite3

def fix_orphaned_listings():
    """Find and fix listings that reference deleted categories"""

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row

    print("=" * 70)
    print("FIXING ORPHANED LISTINGS")
    print("=" * 70)

    # Find listings with deleted categories
    orphaned = conn.execute('''
        SELECT l.id as listing_id,
               l.category_id as old_category_id,
               l.seller_id,
               l.quantity,
               l.price_per_coin,
               l.graded,
               l.grading_service
        FROM listings l
        LEFT JOIN categories c ON l.category_id = c.id
        WHERE l.active = 1 AND c.id IS NULL
    ''').fetchall()

    print(f"\nFound {len(orphaned)} listings with deleted categories\n")

    if not orphaned:
        print("No orphaned listings to fix!")
        conn.close()
        return

    # For each orphaned listing, we need to recreate its category
    # But we don't know the original category specs, so we'll use defaults
    print("Note: These listings reference deleted categories.")
    print("We need to assign them to valid categories.")
    print("Using a default category specification for now.\n")

    # Create a default category spec
    default_spec = {
        'metal': 'Gold',
        'product_line': 'American Eagle',
        'product_type': 'Coin',
        'weight': '1 oz',
        'purity': '.999',
        'mint': 'US Mint',
        'year': '2024',
        'finish': 'Brilliant Uncirculated',
        'grade': 'MS-70'
    }

    fixed_count = 0

    for listing in orphaned:
        listing_id = listing['listing_id']
        old_cat_id = listing['old_category_id']

        print(f"Fixing Listing {listing_id} (old category_id={old_cat_id})...")

        # Create/get a valid category
        new_cat_id = get_or_create_category(conn, default_spec)

        # Verify the new category exists
        verify = conn.execute(
            'SELECT id, bucket_id FROM categories WHERE id = ?',
            (new_cat_id,)
        ).fetchone()

        if not verify:
            print(f"  [ERROR] New category {new_cat_id} doesn't exist!")
            continue

        if verify['bucket_id'] is None:
            print(f"  [ERROR] New category {new_cat_id} has NULL bucket_id!")
            continue

        # Update the listing
        conn.execute(
            'UPDATE listings SET category_id = ? WHERE id = ?',
            (new_cat_id, listing_id)
        )

        print(f"  [OK] Updated to category_id={new_cat_id}, bucket_id={verify['bucket_id']}")
        fixed_count += 1

    conn.commit()

    print(f"\n" + "=" * 70)
    print(f"FIXED {fixed_count} ORPHANED LISTINGS")
    print("=" * 70)

    # Verify
    remaining = conn.execute('''
        SELECT COUNT(*) as cnt
        FROM listings l
        LEFT JOIN categories c ON l.category_id = c.id
        WHERE l.active = 1 AND c.id IS NULL
    ''').fetchone()

    print(f"Remaining orphaned listings: {remaining['cnt']}")

    conn.close()

if __name__ == '__main__':
    fix_orphaned_listings()
