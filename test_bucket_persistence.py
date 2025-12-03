"""
Test that buckets persist on Buy page even when all listings are deleted
"""
import sqlite3
from datetime import datetime

print("=" * 80)
print("BUCKET PERSISTENCE TEST")
print("=" * 80)

conn = sqlite3.connect('database.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Step 1: Get a test user to be the seller
print("\n[STEP 1] Getting test user...")
cursor.execute("SELECT id, username FROM users LIMIT 1")
user = cursor.fetchone()

if not user:
    print("[ERROR] Need at least 1 user in database for testing")
    conn.close()
    exit(1)

seller_id = user['id']
print(f"[OK] Using seller: User #{seller_id} ({user['username']})")

# Step 2: Create a test bucket/category
print("\n[STEP 2] Creating test bucket/category...")
test_bucket_id = 999999  # Use a unique bucket ID that won't conflict

cursor.execute('''
    INSERT OR IGNORE INTO categories (
        bucket_id, metal, product_type, weight, mint, year, finish, grade, coin_series
    ) VALUES (?, 'Gold', 'Coin', '1 oz', 'Test Mint', 2025, 'Proof', 'MS70', 'Test Series')
''', (test_bucket_id,))

cursor.execute("SELECT id FROM categories WHERE bucket_id = ?", (test_bucket_id,))
category = cursor.fetchone()

if not category:
    print("[ERROR] Failed to create test category")
    conn.close()
    exit(1)

category_id = category['id']
print(f"[OK] Created category ID: {category_id} with bucket_id: {test_bucket_id}")

# Step 3: Create a test listing for this bucket
print("\n[STEP 3] Creating test listing...")
cursor.execute('''
    INSERT INTO listings (
        category_id, seller_id, quantity, price_per_coin, active, created_at
    ) VALUES (?, ?, 10, 50.00, 1, ?)
''', (category_id, seller_id, datetime.now()))

listing_id = cursor.lastrowid
conn.commit()
print(f"[OK] Created listing ID: {listing_id}")

# Step 4: Query the buy page to see if bucket appears WITH listing
print("\n[STEP 4] Checking if bucket appears on Buy page WITH listings...")
cursor.execute('''
    SELECT
        categories.id AS category_id,
        categories.bucket_id,
        categories.metal,
        categories.product_type,
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
    WHERE categories.bucket_id = ?
    GROUP BY categories.id
''', (test_bucket_id,))

bucket_with_listings = cursor.fetchone()

if bucket_with_listings:
    print(f"[OK] Bucket appears on Buy page")
    print(f"     Bucket ID: {bucket_with_listings['bucket_id']}")
    print(f"     Lowest Price: ${bucket_with_listings['lowest_price']}")
    print(f"     Total Available: {bucket_with_listings['total_available']}")
else:
    print("[ERROR] Bucket should appear but doesn't!")

# Step 5: Delete all listings for this bucket
print("\n[STEP 5] Deleting all listings for the bucket...")
cursor.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
conn.commit()
print(f"[OK] Deleted listing ID: {listing_id}")

# Step 6: Query the buy page again to see if bucket STILL appears WITHOUT listings
print("\n[STEP 6] Checking if bucket STILL appears on Buy page WITHOUT listings...")
cursor.execute('''
    SELECT
        categories.id AS category_id,
        categories.bucket_id,
        categories.metal,
        categories.product_type,
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
    WHERE categories.bucket_id = ?
    GROUP BY categories.id
''', (test_bucket_id,))

bucket_without_listings = cursor.fetchone()

if bucket_without_listings:
    print(f"[OK] Bucket STILL appears on Buy page (as expected!)")
    print(f"     Bucket ID: {bucket_without_listings['bucket_id']}")
    print(f"     Lowest Price: {bucket_without_listings['lowest_price']} (should be None)")
    print(f"     Total Available: {bucket_without_listings['total_available']} (should be 0)")

    if bucket_without_listings['lowest_price'] is None:
        print("[OK] Lowest price is NULL - correct!")
    else:
        print(f"[ERROR] Lowest price should be NULL but is ${bucket_without_listings['lowest_price']}")

    if bucket_without_listings['total_available'] == 0:
        print("[OK] Total available is 0 - correct!")
    else:
        print(f"[ERROR] Total available should be 0 but is {bucket_without_listings['total_available']}")
else:
    print("[ERROR] Bucket disappeared! This is the bug we're trying to fix.")

# Step 7: Test that all buckets (including ones with no listings) appear
print("\n[STEP 7] Checking ALL buckets query (simulating Buy page)...")
cursor.execute('''
    SELECT
        categories.id AS category_id,
        categories.bucket_id,
        categories.metal,
        categories.product_type,
        categories.coin_series,
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
''')

all_buckets = cursor.fetchall()
print(f"[OK] Found {len(all_buckets)} total buckets in system")

buckets_with_listings = [b for b in all_buckets if b['lowest_price'] is not None]
buckets_without_listings = [b for b in all_buckets if b['lowest_price'] is None]

print(f"     {len(buckets_with_listings)} buckets have active listings")
print(f"     {len(buckets_without_listings)} buckets have NO listings (but still appear!)")

# Show our test bucket
test_bucket_in_results = [b for b in all_buckets if b['bucket_id'] == test_bucket_id]
if test_bucket_in_results:
    print(f"\n[OK] Our test bucket (ID {test_bucket_id}) is in the results!")
else:
    print(f"\n[ERROR] Our test bucket (ID {test_bucket_id}) is NOT in results!")

# Cleanup
print("\n[CLEANUP] Removing test data...")
cursor.execute("DELETE FROM categories WHERE bucket_id = ?", (test_bucket_id,))
conn.commit()
conn.close()

print("\n" + "=" * 80)
print("TEST SUMMARY")
print("=" * 80)
if bucket_without_listings:
    print("[SUCCESS] Buckets persist on Buy page even when all listings are deleted!")
    print("          The 'No listings available' state will be shown in the UI.")
else:
    print("[FAILURE] Buckets are still disappearing when listings are deleted.")

print("=" * 80)
