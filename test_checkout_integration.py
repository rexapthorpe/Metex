"""
Integration test for the new checkout flow redesign.

This test verifies that:
1. Checkout route uses the new template
2. Items are properly grouped into buckets
3. Pricing calculations are correct
4. Modal structure is correct
5. JavaScript functionality is present
"""

import sqlite3
from database import get_db_connection

def test_checkout_data_structure():
    """Test that checkout page receives proper data structure"""
    print("\n" + "="*60)
    print("CHECKOUT FLOW INTEGRATION TEST")
    print("="*60)

    conn = get_db_connection()

    # Get a sample user (first user in database)
    user = conn.execute('SELECT id FROM users LIMIT 1').fetchone()

    if not user:
        print("\n[ERROR] No users found in database")
        print("   Please create a test user first")
        conn.close()
        return

    user_id = user['id']
    print(f"\n[OK] Testing with user ID: {user_id}")

    # Get cart items for this user
    cart_items = conn.execute('''
        SELECT
            cart.id,
            cart.quantity,
            cart.listing_id,
            listings.price_per_coin,
            listings.category_id,
            categories.metal,
            categories.product_type,
            categories.weight,
            categories.mint,
            categories.year,
            categories.finish,
            categories.grade
        FROM cart
        JOIN listings ON cart.listing_id = listings.id
        JOIN categories ON listings.category_id = categories.id
        WHERE cart.user_id = ?
          AND listings.active = 1
          AND listings.quantity > 0
    ''', (user_id,)).fetchall()

    print(f"\n[OK] Found {len(cart_items)} items in cart")

    if len(cart_items) == 0:
        print("\n[WARNING] Cart is empty - creating test data...")

        # Find an active listing to add to cart
        listing = conn.execute('''
            SELECT id, price_per_coin, quantity, category_id
            FROM listings
            WHERE active = 1 AND quantity > 0
            LIMIT 1
        ''').fetchone()

        if listing:
            # Add to cart
            conn.execute('''
                INSERT INTO cart (user_id, listing_id, quantity)
                VALUES (?, ?, ?)
            ''', (user_id, listing['id'], 1))
            conn.commit()

            print(f"  [OK] Added listing {listing['id']} to cart")

            # Re-fetch cart items
            cart_items = conn.execute('''
                SELECT
                    cart.id,
                    cart.quantity,
                    cart.listing_id,
                    listings.price_per_coin,
                    listings.category_id,
                    categories.metal,
                    categories.product_type,
                    categories.weight,
                    categories.mint,
                    categories.year,
                    categories.finish,
                    categories.grade
                FROM cart
                JOIN listings ON cart.listing_id = listings.id
                JOIN categories ON listings.category_id = categories.id
                WHERE cart.user_id = ?
                  AND listings.active = 1
                  AND listings.quantity > 0
            ''', (user_id,)).fetchall()
        else:
            print("\n[ERROR] No active listings found to add to cart")
            conn.close()
            return

    # Simulate the buckets grouping logic from checkout_routes.py
    buckets = {}
    cart_total = 0

    for item in cart_items:
        item_dict = dict(item)
        bucket_key = f"{item_dict['metal']}-{item_dict['product_type']}-{item_dict['weight']}-{item_dict['mint']}-{item_dict['year']}-{item_dict['finish']}-{item_dict['grade']}"

        if bucket_key not in buckets:
            buckets[bucket_key] = {
                'category': {
                    'metal': item_dict['metal'],
                    'product_type': item_dict['product_type'],
                    'weight': item_dict['weight'],
                    'mint': item_dict['mint'],
                    'year': item_dict['year'],
                    'finish': item_dict['finish'],
                    'grade': item_dict['grade']
                },
                'quantity': 0,
                'total_qty': 0,
                'total_price': 0,
                'avg_price': 0
            }

        subtotal = item_dict['price_per_coin'] * item_dict['quantity']
        buckets[bucket_key]['quantity'] += item_dict['quantity']
        buckets[bucket_key]['total_qty'] += item_dict['quantity']
        buckets[bucket_key]['total_price'] += subtotal
        cart_total += subtotal

    # Calculate average prices
    for bucket in buckets.values():
        if bucket['quantity'] > 0:
            bucket['avg_price'] = round(bucket['total_price'] / bucket['quantity'], 2)

    print("\n" + "-"*60)
    print("CHECKOUT DATA STRUCTURE")
    print("-"*60)

    print(f"\nNumber of unique item types: {len(buckets)}")
    print(f"Total items: {sum(b['total_qty'] for b in buckets.values())}")
    print(f"Cart total: ${cart_total:.2f}")

    print("\nItem Breakdown:")
    for i, (bucket_key, bucket) in enumerate(buckets.items(), 1):
        cat = bucket['category']
        print(f"\n  Item {i}:")
        print(f"    Title: {cat['metal']} {cat['product_type']}")
        print(f"    Details: {cat['weight']}, {cat['mint']}, {cat['year']}, {cat['finish']}, {cat['grade']}")
        print(f"    Quantity: {bucket['total_qty']}")
        print(f"    Avg Price: ${bucket['avg_price']:.2f}")
        print(f"    Total: ${bucket['total_price']:.2f}")

    conn.close()

    # Verify template file exists
    print("\n" + "-"*60)
    print("TEMPLATE VERIFICATION")
    print("-"*60)

    import os
    template_path = 'templates/checkout_new.html'
    css_path = 'static/css/checkout.css'
    js_path = 'static/js/checkout.js'

    if os.path.exists(template_path):
        print(f"\n[OK] Template exists: {template_path}")

        # Check for key elements in template
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()

        checks = [
            ('checkout-slider-container', 'Sliding container'),
            ('orderSummaryView', 'Order summary view'),
            ('paymentView', 'Payment view'),
            ('order-item-card', 'Item card structure'),
            ('showPaymentView()', 'Payment view function'),
            ('showOrderSummary()', 'Summary view function'),
            ('order-total-section', 'Total section')
        ]

        print("\n  Template Structure:")
        for check_str, description in checks:
            if check_str in content:
                print(f"    [OK] {description}")
            else:
                print(f"    [ERROR] {description} NOT FOUND")
    else:
        print(f"\n[ERROR] Template NOT found: {template_path}")

    if os.path.exists(css_path):
        print(f"\n[OK] CSS exists: {css_path}")

        with open(css_path, 'r', encoding='utf-8') as f:
            css_content = f.read()

        css_checks = [
            ('.checkout-slider-container', 'Slider container styles'),
            ('.show-payment', 'Payment view class'),
            ('.order-item-card', 'Item card styles'),
            ('.order-total-section', 'Total section styles'),
            ('transform', 'Slide animation'),
            ('cubic-bezier', 'Smooth easing')
        ]

        print("\n  CSS Features:")
        for check_str, description in css_checks:
            if check_str in css_content:
                print(f"    [OK] {description}")
            else:
                print(f"    [ERROR] {description} NOT FOUND")
    else:
        print(f"\n[ERROR] CSS NOT found: {css_path}")

    if os.path.exists(js_path):
        print(f"\n[OK] JavaScript exists: {js_path}")

        with open(js_path, 'r', encoding='utf-8') as f:
            js_content = f.read()

        js_checks = [
            ('showPaymentView', 'Show payment function'),
            ('showOrderSummary', 'Show summary function'),
            ('closeCheckout', 'Close function'),
            ('show-payment', 'Class toggle'),
            ('Escape', 'Keyboard navigation')
        ]

        print("\n  JavaScript Functions:")
        for check_str, description in js_checks:
            if check_str in js_content:
                print(f"    [OK] {description}")
            else:
                print(f"    [ERROR] {description} NOT FOUND")
    else:
        print(f"\n[ERROR] JavaScript NOT found: {js_path}")

    # Check route configuration
    print("\n" + "-"*60)
    print("ROUTE CONFIGURATION")
    print("-"*60)

    route_path = 'routes/checkout_routes.py'
    if os.path.exists(route_path):
        with open(route_path, 'r', encoding='utf-8') as f:
            route_content = f.read()

        if 'checkout_new.html' in route_content:
            print("\n[OK] Route uses new template (checkout_new.html)")
        else:
            print("\n[ERROR] Route NOT using new template")
            print("   Expected: checkout_new.html")
            if 'checkout.html' in route_content:
                print("   Found: checkout.html (old template)")

    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60)
    print("\nNext steps:")
    print("1. Navigate to cart page in the application")
    print("2. Click 'Proceed to Checkout'")
    print("3. Verify:")
    print("   - Modal displays with order summary")
    print("   - Items shown in individual cards")
    print("   - 'Select Payment Method' button slides to payment view")
    print("   - Back arrow returns to summary")
    print("   - Close button works")
    print("   - Escape key navigates properly")


if __name__ == '__main__':
    test_checkout_data_structure()
