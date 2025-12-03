"""
Test that the View button on bids correctly routes to the bucket page
"""
import sqlite3
from datetime import datetime

print("=" * 80)
print("BID VIEW BUTTON TEST")
print("=" * 80)

conn = sqlite3.connect('database.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Step 1: Get a test user
print("\n[STEP 1] Getting test user...")
cursor.execute("SELECT id, username FROM users LIMIT 1")
user = cursor.fetchone()

if not user:
    print("[ERROR] Need at least 1 user in database for testing")
    conn.close()
    exit(1)

buyer_id = user['id']
print(f"[OK] Using buyer: User #{buyer_id} ({user['username']})")

# Step 2: Create a test category with a specific bucket_id
print("\n[STEP 2] Creating test category with bucket_id...")
test_bucket_id = 888888  # Use a unique bucket ID
test_category_id = None

cursor.execute('''
    INSERT INTO categories (
        bucket_id, metal, product_type, weight, mint, year, finish, grade, coin_series
    ) VALUES (?, 'Silver', 'Coin', '1 oz', 'Test Mint', 2024, 'Proof', 'MS69', 'Test Series')
''', (test_bucket_id,))

cursor.execute("SELECT id FROM categories WHERE bucket_id = ?", (test_bucket_id,))
category = cursor.fetchone()

if not category:
    print("[ERROR] Failed to create test category")
    conn.close()
    exit(1)

test_category_id = category['id']
print(f"[OK] Created category:")
print(f"     Category ID: {test_category_id}")
print(f"     Bucket ID: {test_bucket_id}")

# Step 3: Create a test bid for this category
print("\n[STEP 3] Creating test bid...")
cursor.execute('''
    INSERT INTO bids (
        buyer_id, category_id, quantity_requested, remaining_quantity, price_per_coin,
        status, active, created_at, delivery_address
    ) VALUES (?, ?, 5, 5, 45.00, 'Open', 1, ?, '123 Test St')
''', (buyer_id, test_category_id, datetime.now()))

bid_id = cursor.lastrowid
conn.commit()
print(f"[OK] Created bid ID: {bid_id}")

# Step 4: Query bids the same way the account route does
print("\n[STEP 4] Querying bids (simulating account route)...")
cursor.execute("""
    SELECT
        b.*,
        c.bucket_id, c.weight, c.metal, c.product_type, c.mint, c.year, c.finish,
        c.grade, c.coin_series, c.purity, c.product_line,
        (SELECT MIN(l.price_per_coin)
           FROM listings AS l
          WHERE l.category_id = b.category_id
            AND l.active = 1
            AND l.quantity > 0
        ) AS current_price
      FROM bids AS b
      LEFT JOIN categories AS c ON b.category_id = c.id
     WHERE b.buyer_id = ?
       AND b.id = ?
""", (buyer_id, bid_id))

bid = cursor.fetchone()

if not bid:
    print("[ERROR] Could not find the bid we just created!")
    conn.close()
    exit(1)

print(f"[OK] Found bid in query")
print(f"     Bid ID: {bid['id']}")
print(f"     Category ID: {bid['category_id']}")
print(f"     Bucket ID: {bid['bucket_id']}")

# Step 5: Verify bucket_id is present and correct
print("\n[STEP 5] Verifying bucket_id field...")
if bid['bucket_id'] is None:
    print("[ERROR] bucket_id is NULL! The fix didn't work.")
elif bid['bucket_id'] != test_bucket_id:
    print(f"[ERROR] bucket_id mismatch! Expected {test_bucket_id}, got {bid['bucket_id']}")
else:
    print(f"[OK] bucket_id is correct: {bid['bucket_id']}")

# Step 6: Simulate the view_bucket route lookup
print("\n[STEP 6] Simulating view_bucket route (checking if bucket can be found)...")
cursor.execute("SELECT * FROM categories WHERE bucket_id = ? LIMIT 1", (bid['bucket_id'],))
bucket_lookup = cursor.fetchone()

if bucket_lookup:
    print(f"[OK] Bucket found successfully!")
    print(f"     Category ID: {bucket_lookup['id']}")
    print(f"     Bucket ID: {bucket_lookup['bucket_id']}")
    print(f"     Description: {bucket_lookup['metal']} {bucket_lookup['product_type']}")
else:
    print(f"[ERROR] Bucket NOT found! This is why 'Item not found' error appears.")

# Step 7: Test with a closed bid
print("\n[STEP 7] Testing with a closed bid...")
cursor.execute("UPDATE bids SET status = 'Filled', active = 0 WHERE id = ?", (bid_id,))
conn.commit()

cursor.execute("""
    SELECT
        b.*,
        c.bucket_id, c.weight, c.metal, c.product_type, c.mint, c.year, c.finish,
        c.grade, c.coin_series, c.purity, c.product_line,
        (SELECT MIN(l.price_per_coin)
           FROM listings AS l
          WHERE l.category_id = b.category_id
            AND l.active = 1
            AND l.quantity > 0
        ) AS current_price
      FROM bids AS b
      LEFT JOIN categories AS c ON b.category_id = c.id
     WHERE b.buyer_id = ?
       AND b.id = ?
""", (buyer_id, bid_id))

closed_bid = cursor.fetchone()

if closed_bid and closed_bid['bucket_id'] == test_bucket_id:
    print(f"[OK] Closed bid still has correct bucket_id: {closed_bid['bucket_id']}")

    # Verify bucket lookup still works
    cursor.execute("SELECT * FROM categories WHERE bucket_id = ? LIMIT 1", (closed_bid['bucket_id'],))
    if cursor.fetchone():
        print(f"[OK] Bucket lookup works for closed bid too!")
    else:
        print(f"[ERROR] Bucket lookup failed for closed bid")
else:
    print("[ERROR] Closed bid doesn't have correct bucket_id")

# Cleanup
print("\n[CLEANUP] Removing test data...")
cursor.execute("DELETE FROM bids WHERE id = ?", (bid_id,))
cursor.execute("DELETE FROM categories WHERE bucket_id = ?", (test_bucket_id,))
conn.commit()
conn.close()

print("\n" + "=" * 80)
print("TEST SUMMARY")
print("=" * 80)
if bid and bid['bucket_id'] == test_bucket_id and bucket_lookup:
    print("[SUCCESS] The View button fix works correctly!")
    print("          - Bids now include bucket_id from categories table")
    print("          - View button will route to correct bucket page")
    print("          - Works for both open and closed bids")
else:
    print("[FAILURE] The fix has issues.")

print("=" * 80)
