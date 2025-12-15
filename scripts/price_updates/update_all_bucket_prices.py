"""
Update prices for all buckets with active listings
Run this to ensure all buckets have at least one price history point
"""

from database import get_db_connection
from services.bucket_price_history_service import update_bucket_price

def update_all_bucket_prices():
    """Update prices for all buckets with active listings"""
    conn = get_db_connection()

    # Get all buckets with active listings
    buckets = conn.execute('''
        SELECT DISTINCT c.bucket_id
        FROM categories c
        JOIN listings l ON l.category_id = c.id
        WHERE l.active = 1 AND l.quantity > 0 AND c.bucket_id IS NOT NULL
        ORDER BY c.bucket_id
    ''').fetchall()

    conn.close()

    print(f"Found {len(buckets)} buckets with active listings")
    print("=" * 60)

    updated_count = 0
    skipped_count = 0

    for bucket in buckets:
        bucket_id = bucket['bucket_id']
        try:
            price = update_bucket_price(bucket_id)
            if price is not None:
                print(f"Bucket {bucket_id}: ${price:.2f}")
                updated_count += 1
            else:
                print(f"Bucket {bucket_id}: No price (skipped)")
                skipped_count += 1
        except Exception as e:
            print(f"Bucket {bucket_id}: ERROR - {e}")
            skipped_count += 1

    print("=" * 60)
    print(f"Updated: {updated_count}")
    print(f"Skipped: {skipped_count}")
    print(f"Total: {len(buckets)}")

if __name__ == '__main__':
    update_all_bucket_prices()
