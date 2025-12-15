"""
Wipe All Buckets Script
Removes all user-created buckets and their associated data from the dev database
while preserving the schema and system data.
"""

import sqlite3
from datetime import datetime

def wipe_all_buckets():
    """Delete all buckets and related data from the database"""

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    try:
        # Start transaction
        conn.execute('BEGIN TRANSACTION')

        print("=" * 60)
        print("BUCKET WIPE OPERATION")
        print("=" * 60)
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        # === STEP 1: Count records before deletion ===
        print("=== CURRENT DATA COUNTS ===")

        cursor.execute('SELECT COUNT(DISTINCT bucket_id) FROM categories WHERE bucket_id IS NOT NULL')
        bucket_count = cursor.fetchone()[0]
        print(f"Unique buckets: {bucket_count}")

        cursor.execute('SELECT COUNT(*) FROM listings')
        listings_count = cursor.fetchone()[0]
        print(f"Listings: {listings_count}")

        cursor.execute('SELECT COUNT(*) FROM bucket_price_history')
        history_count = cursor.fetchone()[0]
        print(f"Price history records: {history_count}")

        cursor.execute('SELECT COUNT(*) FROM bids')
        bids_count = cursor.fetchone()[0]
        print(f"Bids: {bids_count}")

        cursor.execute('SELECT COUNT(*) FROM bid_fills')
        bid_fills_count = cursor.fetchone()[0]
        print(f"Bid fills: {bid_fills_count}")

        cursor.execute('SELECT COUNT(*) FROM cart')
        cart_count = cursor.fetchone()[0]
        print(f"Cart items: {cart_count}")

        cursor.execute('SELECT COUNT(*) FROM order_items')
        order_items_count = cursor.fetchone()[0]
        print(f"Order items: {order_items_count}")

        cursor.execute('SELECT COUNT(*) FROM orders')
        orders_count = cursor.fetchone()[0]
        print(f"Orders: {orders_count}")

        cursor.execute('SELECT COUNT(*) FROM listing_photos')
        photos_count = cursor.fetchone()[0]
        print(f"Listing photos: {photos_count}")

        cursor.execute('SELECT COUNT(*) FROM category_price_snapshots')
        snapshots_count = cursor.fetchone()[0]
        print(f"Category price snapshots: {snapshots_count}")

        cursor.execute('SELECT COUNT(*) FROM categories WHERE bucket_id IS NOT NULL')
        categories_count = cursor.fetchone()[0]
        print(f"Categories with bucket_id: {categories_count}")

        print()
        print("=" * 60)
        print("DELETING DATA (in dependency order)...")
        print("=" * 60)

        # === STEP 2: Delete in correct order ===

        # 1. Delete bid_fills (depends on bids)
        cursor.execute('DELETE FROM bid_fills')
        deleted = cursor.rowcount
        print(f"[OK] Deleted {deleted} bid_fills")

        # 2. Delete bids (depends on listings)
        cursor.execute('DELETE FROM bids')
        deleted = cursor.rowcount
        print(f"[OK] Deleted {deleted} bids")

        # 3. Delete cart items (depends on listings via category_id)
        # Cart items reference category_id, which will be deleted
        cursor.execute('DELETE FROM cart')
        deleted = cursor.rowcount
        print(f"[OK] Deleted {deleted} cart items")

        # 4. Delete order_items (depends on orders and listings)
        cursor.execute('DELETE FROM order_items')
        deleted = cursor.rowcount
        print(f"[OK] Deleted {deleted} order_items")

        # 5. Delete orders (parent of order_items)
        cursor.execute('DELETE FROM orders')
        deleted = cursor.rowcount
        print(f"[OK] Deleted {deleted} orders")

        # 6. Delete listing_photos (depends on listings)
        cursor.execute('DELETE FROM listing_photos')
        deleted = cursor.rowcount
        print(f"[OK] Deleted {deleted} listing_photos")

        # 7. Delete listings (depends on categories)
        cursor.execute('DELETE FROM listings')
        deleted = cursor.rowcount
        print(f"[OK] Deleted {deleted} listings")

        # 8. Delete bucket_price_history (depends on bucket_id from categories)
        cursor.execute('DELETE FROM bucket_price_history')
        deleted = cursor.rowcount
        print(f"[OK] Deleted {deleted} bucket_price_history records")

        # 9. Delete category_price_snapshots (depends on categories)
        cursor.execute('DELETE FROM category_price_snapshots')
        deleted = cursor.rowcount
        print(f"[OK] Deleted {deleted} category_price_snapshots")

        # 10. Delete categories with bucket_id
        cursor.execute('DELETE FROM categories WHERE bucket_id IS NOT NULL')
        deleted = cursor.rowcount
        print(f"[OK] Deleted {deleted} categories with bucket_id")

        # === STEP 3: Verify deletion ===
        print()
        print("=" * 60)
        print("VERIFICATION (all should be 0)")
        print("=" * 60)

        cursor.execute('SELECT COUNT(DISTINCT bucket_id) FROM categories WHERE bucket_id IS NOT NULL')
        remaining_buckets = cursor.fetchone()[0]
        print(f"Remaining buckets: {remaining_buckets}")

        cursor.execute('SELECT COUNT(*) FROM listings')
        remaining_listings = cursor.fetchone()[0]
        print(f"Remaining listings: {remaining_listings}")

        cursor.execute('SELECT COUNT(*) FROM bucket_price_history')
        remaining_history = cursor.fetchone()[0]
        print(f"Remaining price history: {remaining_history}")

        cursor.execute('SELECT COUNT(*) FROM bids')
        remaining_bids = cursor.fetchone()[0]
        print(f"Remaining bids: {remaining_bids}")

        cursor.execute('SELECT COUNT(*) FROM cart')
        remaining_cart = cursor.fetchone()[0]
        print(f"Remaining cart items: {remaining_cart}")

        cursor.execute('SELECT COUNT(*) FROM orders')
        remaining_orders = cursor.fetchone()[0]
        print(f"Remaining orders: {remaining_orders}")

        # === STEP 4: Commit transaction ===
        conn.commit()

        print()
        print("=" * 60)
        print("[SUCCESS] WIPE COMPLETED SUCCESSFULLY")
        print("=" * 60)
        print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        print("The Buy page should now be empty.")
        print("All bucket-related data has been removed.")
        print("Database schema and system data remain intact.")

    except Exception as e:
        # Rollback on error
        conn.rollback()
        print()
        print("=" * 60)
        print("[ERROR] TRANSACTION ROLLED BACK")
        print("=" * 60)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        conn.close()

if __name__ == '__main__':
    print()
    response = input("This will DELETE ALL buckets and related data. Continue? (yes/no): ")

    if response.lower() == 'yes':
        wipe_all_buckets()
    else:
        print("Operation cancelled.")
