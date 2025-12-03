"""
Test that the account page query works correctly with photo_path fix
"""
from database import get_db_connection

print("=" * 70)
print("ACCOUNT PAGE QUERY TEST")
print("=" * 70)

# Get a test user
conn = get_db_connection()

# Find a user who has listings
user = conn.execute("""
    SELECT DISTINCT l.seller_id, u.username
    FROM listings l
    JOIN users u ON l.seller_id = u.id
    WHERE l.active = 1 AND l.quantity > 0
    LIMIT 1
""").fetchone()

if not user:
    print("\n[INFO] No users with active listings found")
    print("Creating test data would require more setup")
    conn.close()
    exit(0)

user_id = user['seller_id']
username = user['username']

print(f"\nTesting with user: {username} (ID: {user_id})")

# Test the query from account_routes.py
try:
    print("\n[TEST] Running account page active listings query...")
    active_listings_raw = conn.execute(
        """SELECT l.id   AS listing_id,
                l.quantity,
                l.price_per_coin,
                l.pricing_mode,
                l.spot_premium,
                l.floor_price,
                l.pricing_metal,
                lp.file_path AS photo_path,
                l.graded,
                l.grading_service,
                c.id AS category_id,
                c.bucket_id,
                c.metal, c.product_type,
                c.special_designation,
                c.weight, c.mint, c.year, c.finish, c.grade,
                c.purity, c.product_line, c.coin_series
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        LEFT JOIN listing_photos lp ON lp.listing_id = l.id
        WHERE l.seller_id = ?
            AND l.active = 1
            AND l.quantity > 0
        """, (user_id,)
    ).fetchall()

    print(f"[PASS] Query executed successfully!")
    print(f"[INFO] Found {len(active_listings_raw)} active listings")

    # Test calculating effective price
    from services.pricing_service import get_effective_price
    from services.spot_price_service import get_current_spot_prices

    spot_prices = get_current_spot_prices()
    active_listings = []

    for listing in active_listings_raw:
        listing_dict = dict(listing)
        # Calculate effective price if variable pricing
        if listing_dict.get('pricing_mode') == 'premium_to_spot':
            listing_dict['effective_price'] = get_effective_price(listing_dict, spot_prices)
        else:
            listing_dict['effective_price'] = listing_dict.get('price_per_coin', 0)
        active_listings.append(listing_dict)

    print(f"[PASS] Effective prices calculated successfully!")

    # Display sample listing info
    if active_listings:
        print(f"\n[INFO] Sample listing details:")
        sample = active_listings[0]
        print(f"  Listing ID: {sample.get('listing_id')}")
        print(f"  Metal: {sample.get('metal')}")
        print(f"  Product: {sample.get('product_type')}")
        print(f"  Quantity: {sample.get('quantity')}")
        print(f"  Pricing Mode: {sample.get('pricing_mode', 'static')}")

        if sample.get('pricing_mode') == 'premium_to_spot':
            print(f"  Spot Premium: ${sample.get('spot_premium', 0):.2f}")
            print(f"  Floor Price: ${sample.get('floor_price', 0):.2f}")
            print(f"  Effective Price: ${sample.get('effective_price', 0):.2f}")
        else:
            print(f"  Price Per Coin: ${sample.get('price_per_coin', 0):.2f}")

        photo_path = sample.get('photo_path')
        if photo_path:
            print(f"  Photo Path: {photo_path}")
        else:
            print(f"  Photo Path: (none)")

    print("\n" + "=" * 70)
    print("TEST RESULT: PASS")
    print("=" * 70)
    print("\n[SUCCESS] Account page query works correctly!")
    print("The account page should now load without errors.")

except Exception as e:
    print(f"\n[FAIL] Query failed with error:")
    print(f"  {type(e).__name__}: {e}")

    import traceback
    print("\nFull traceback:")
    traceback.print_exc()

    print("\n" + "=" * 70)
    print("TEST RESULT: FAIL")
    print("=" * 70)

finally:
    conn.close()
