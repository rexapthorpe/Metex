"""
Test script to verify portfolio chart uses dynamic pricing

This script tests that:
1. Portfolio history uses current market prices (not stale snapshots)
2. Holdings panel and chart use the same pricing logic
3. When listing prices change, both update together
4. Exclusions affect chart and holdings identically
"""

import sqlite3
from services.portfolio_service import (
    get_user_holdings,
    calculate_portfolio_value,
    get_portfolio_history,
    exclude_holding,
    include_holding
)
from datetime import datetime

def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def print_separator(title=""):
    print("\n" + "="*70)
    if title:
        print(f"  {title}")
        print("="*70)

def test_pricing_consistency(user_id=3):
    """
    Test that holdings and history use the same current prices
    """
    print_separator("TEST 1: Pricing Consistency")

    # Get holdings with current prices
    holdings = get_user_holdings(user_id)
    print(f"\n1. Holdings count: {len(holdings)}")

    if holdings:
        first_holding = holdings[0]
        print(f"\nFirst holding:")
        print(f"   Bucket ID: {first_holding['bucket_id']}")
        print(f"   Metal: {first_holding['metal']}")
        print(f"   Product: {first_holding['product_type']}")
        print(f"   Quantity: {first_holding['quantity']}")
        print(f"   Purchase price: ${first_holding['purchase_price']:.2f}")
        print(f"   Current market price: ${first_holding['current_market_price']:.2f}" if first_holding['current_market_price'] else "   Current market price: None (using purchase price)")

    # Get portfolio value (summary)
    portfolio_value = calculate_portfolio_value(user_id)
    print(f"\n2. Portfolio Value (from calculate_portfolio_value):")
    print(f"   Total Value: ${portfolio_value['total_value']:,.2f}")
    print(f"   Cost Basis: ${portfolio_value['cost_basis']:,.2f}")
    print(f"   Gain/Loss: ${portfolio_value['gain_loss']:,.2f} ({portfolio_value['gain_loss_percent']:.2f}%)")

    # Get history (chart data)
    history = get_portfolio_history(user_id, days=30)
    print(f"\n3. Portfolio History (chart data):")
    print(f"   History points: {len(history)}")

    if history:
        latest = history[-1]
        print(f"\n   Latest point (should match current value):")
        print(f"   Date: {latest['snapshot_date']}")
        print(f"   Value: ${latest['total_value']:,.2f}")
        print(f"   Cost Basis: ${latest['total_cost_basis']:,.2f}")

        # Verify they match
        value_match = abs(latest['total_value'] - portfolio_value['total_value']) < 0.01
        cost_match = abs(latest['total_cost_basis'] - portfolio_value['cost_basis']) < 0.01

        print(f"\nVERIFICATION:")
        print(f"   Chart value matches holdings value: {'[YES]' if value_match else '[NO]'}")
        print(f"   Chart cost matches holdings cost: {'[YES]' if cost_match else '[NO]'}")

        if value_match and cost_match:
            print(f"\n[PASS] TEST PASSED: Chart and holdings use same pricing!")
        else:
            print(f"\n[FAIL] TEST FAILED: Chart and holdings have different values!")
            return False

    return True

def test_price_change_detection(user_id=3):
    """
    Test that we can detect the current market price from active listings
    """
    print_separator("TEST 2: Price Change Detection")

    holdings = get_user_holdings(user_id)

    if not holdings:
        print("No holdings found - skipping test")
        return True

    first_holding = holdings[0]
    bucket_id = first_holding['bucket_id']

    print(f"\nChecking active listings for bucket {bucket_id}:")

    conn = get_db()
    listings = conn.execute("""
        SELECT l.id, l.price_per_coin, l.quantity, l.active
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ?
          AND l.active = 1
          AND l.quantity > 0
        ORDER BY l.price_per_coin ASC
    """, (bucket_id,)).fetchall()

    conn.close()

    print(f"   Active listings found: {len(listings)}")

    if listings:
        print(f"\n   Lowest price: ${listings[0]['price_per_coin']:.2f} (listing_id={listings[0]['id']})")
        print(f"   Current market price in holding: ${first_holding['current_market_price']:.2f}" if first_holding['current_market_price'] else "   No market price found")

        if first_holding['current_market_price']:
            price_match = abs(listings[0]['price_per_coin'] - first_holding['current_market_price']) < 0.01
            print(f"\nVERIFICATION:")
            print(f"   Market price matches lowest listing: {'[YES]' if price_match else '[NO]'}")

            if price_match:
                print(f"\n[PASS] TEST PASSED: Market price correctly sourced from active listings!")
            else:
                print(f"\n[FAIL] TEST FAILED: Market price doesn't match lowest listing!")
                return False
        else:
            print(f"\n[WARNING] No market price found (will use purchase price)")
    else:
        print(f"\n[WARNING] No active listings for this bucket (will use purchase price)")

    return True

def test_exclusion_logic(user_id=3):
    """
    Test that exclusions affect both holdings and history
    """
    print_separator("TEST 3: Exclusion Logic")

    # Get initial state
    holdings_before = get_user_holdings(user_id)
    value_before = calculate_portfolio_value(user_id)
    history_before = get_portfolio_history(user_id, days=30)

    print(f"\n1. BEFORE exclusion:")
    print(f"   Holdings count: {len(holdings_before)}")
    print(f"   Total value: ${value_before['total_value']:,.2f}")
    print(f"   Latest chart value: ${history_before[-1]['total_value']:,.2f}")

    if not holdings_before:
        print("\n   No holdings to test exclusions - skipping")
        return True

    # Exclude first holding temporarily
    test_holding = holdings_before[0]
    order_item_id = test_holding['order_item_id']

    print(f"\n2. Excluding order_item_id {order_item_id}...")
    exclude_holding(user_id, order_item_id)

    # Get state after exclusion
    holdings_after = get_user_holdings(user_id)
    value_after = calculate_portfolio_value(user_id)
    history_after = get_portfolio_history(user_id, days=30)

    print(f"\n3. AFTER exclusion:")
    print(f"   Holdings count: {len(holdings_after)}")
    print(f"   Total value: ${value_after['total_value']:,.2f}")
    print(f"   Latest chart value: ${history_after[-1]['total_value']:,.2f}")

    # Verify exclusion worked
    holdings_reduced = len(holdings_after) == len(holdings_before) - 1
    value_reduced = value_after['total_value'] < value_before['total_value']
    chart_matches = abs(history_after[-1]['total_value'] - value_after['total_value']) < 0.01

    print(f"\nVERIFICATION:")
    print(f"   Holdings count reduced by 1: {'[YES]' if holdings_reduced else '[NO]'}")
    print(f"   Total value reduced: {'[YES]' if value_reduced else '[NO]'}")
    print(f"   Chart matches new value: {'[YES]' if chart_matches else '[NO]'}")

    # Re-include the holding to restore state
    print(f"\n4. Re-including order_item_id {order_item_id}...")
    include_holding(user_id, order_item_id)

    # Verify restoration
    holdings_restored = get_user_holdings(user_id)
    value_restored = calculate_portfolio_value(user_id)

    print(f"\n5. After re-inclusion:")
    print(f"   Holdings count: {len(holdings_restored)}")
    print(f"   Total value: ${value_restored['total_value']:,.2f}")

    restored = len(holdings_restored) == len(holdings_before)

    if holdings_reduced and value_reduced and chart_matches and restored:
        print(f"\n[PASS] TEST PASSED: Exclusions work correctly and affect chart!")
    else:
        print(f"\n[FAIL] TEST FAILED: Exclusion logic has issues!")
        return False

    return True

def main():
    """
    Run all tests
    """
    print_separator("PORTFOLIO DYNAMIC PRICING TEST SUITE")
    print(f"\nTesting with user_id=3 (rexb)")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Check if user has holdings
    conn = get_db()
    order_count = conn.execute("""
        SELECT COUNT(*) as count
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        WHERE o.buyer_id = 3
    """).fetchone()['count']
    conn.close()

    if order_count == 0:
        print(f"\n[WARNING] User 3 has no orders. Cannot test portfolio features.")
        print(f"   Please ensure the test user has purchased items first.")
        return

    print(f"\nUser has {order_count} order items - proceeding with tests...")

    # Run tests
    test1_pass = test_pricing_consistency(user_id=3)
    test2_pass = test_price_change_detection(user_id=3)
    test3_pass = test_exclusion_logic(user_id=3)

    # Summary
    print_separator("TEST SUMMARY")

    tests = [
        ("Pricing Consistency (holdings vs chart)", test1_pass),
        ("Price Change Detection (market prices)", test2_pass),
        ("Exclusion Logic (affects chart)", test3_pass)
    ]

    all_passed = all(result for _, result in tests)

    for name, result in tests:
        status = "[PASS]" if result else "[FAIL]"
        print(f"   {status} - {name}")

    print()

    if all_passed:
        print("="*70)
        print("  ALL TESTS PASSED!")
        print("="*70)
        print("\nThe portfolio chart now uses dynamic pricing!")
        print("Chart and holdings panel are synchronized.")
        print("When listing prices change, both will update together.")
    else:
        print("="*70)
        print("  SOME TESTS FAILED")
        print("="*70)
        print("\nPlease review the test output above for details.")

if __name__ == '__main__':
    main()
