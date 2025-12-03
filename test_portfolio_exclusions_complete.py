"""
Comprehensive Portfolio Exclusions Test

Tests that excluded items are completely removed from ALL portfolio calculations:
- Current holdings list
- Portfolio value and cost basis
- Historical time-series data (all ranges: 1D, 1W, 1M, 3M, 1Y)
- Allocation by metal

Verifies the requirement: "when a user excludes an item, the system treats it
as if the user never bought it" - no partial adjustments, complete removal.
"""

import sqlite3
from services.portfolio_service import (
    get_user_holdings,
    calculate_portfolio_value,
    get_portfolio_history,
    get_portfolio_allocation,
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

def verify_exact_match(expected, actual, tolerance=0.01):
    """Check if two values match within a small tolerance"""
    return abs(expected - actual) < tolerance

def test_complete_exclusion_removal(user_id=3):
    """
    Test that excluded items are COMPLETELY removed from all calculations
    """
    print_separator("COMPREHENSIVE EXCLUSION TEST")
    print(f"\nTesting with user_id={user_id}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Step 1: Get initial state (before exclusion)
    print_separator("STEP 1: Initial State (Before Exclusion)")

    holdings_before = get_user_holdings(user_id)
    value_before = calculate_portfolio_value(user_id)
    allocation_before = get_portfolio_allocation(user_id)
    history_1m_before = get_portfolio_history(user_id, days=30)
    history_1w_before = get_portfolio_history(user_id, days=7)

    print(f"\nHoldings count: {len(holdings_before)}")
    print(f"Total portfolio value: ${value_before['total_value']:,.2f}")
    print(f"Total cost basis: ${value_before['cost_basis']:,.2f}")
    print(f"Gain/Loss: ${value_before['gain_loss']:,.2f} ({value_before['gain_loss_percent']:.2f}%)")
    print(f"History points (1M): {len(history_1m_before)}")
    print(f"History points (1W): {len(history_1w_before)}")
    print(f"Allocation breakdown:")
    for alloc in allocation_before:
        print(f"  {alloc['metal']}: ${alloc['value']:,.2f} ({alloc['percentage']:.1f}%)")

    if not holdings_before:
        print("\n[ERROR] No holdings found. Cannot test exclusions.")
        print("Please ensure the test user has purchased items first.")
        return False

    # Select first holding to exclude
    test_holding = holdings_before[0]
    order_item_id = test_holding['order_item_id']

    print(f"\n[TARGET] Will exclude order_item_id {order_item_id}:")
    print(f"  Metal: {test_holding['metal']}")
    print(f"  Product: {test_holding['product_type']}")
    print(f"  Quantity: {test_holding['quantity']}")
    print(f"  Purchase price: ${test_holding['purchase_price']:.2f}")
    print(f"  Current price: ${test_holding['current_market_price']:.2f}" if test_holding['current_market_price'] else "  Current price: None")

    # Calculate expected impact of exclusion
    excluded_qty = test_holding['quantity']
    excluded_purchase_price = test_holding['purchase_price']
    excluded_current_price = test_holding['current_market_price'] or excluded_purchase_price

    excluded_cost = excluded_qty * excluded_purchase_price
    excluded_value = excluded_qty * excluded_current_price

    expected_value_after = value_before['total_value'] - excluded_value
    expected_cost_after = value_before['cost_basis'] - excluded_cost

    print(f"\n[EXPECTED IMPACT]")
    print(f"  Item cost basis: ${excluded_cost:,.2f}")
    print(f"  Item current value: ${excluded_value:,.2f}")
    print(f"  Expected portfolio value after exclusion: ${expected_value_after:,.2f}")
    print(f"  Expected cost basis after exclusion: ${expected_cost_after:,.2f}")

    # Step 2: Exclude the holding
    print_separator("STEP 2: Excluding Holding")

    success = exclude_holding(user_id, order_item_id)
    if not success:
        print("[ERROR] Failed to exclude holding!")
        return False

    print(f"[SUCCESS] Excluded order_item_id {order_item_id}")

    # Step 3: Verify exclusion in ALL calculations
    print_separator("STEP 3: Verification After Exclusion")

    # 3a. Holdings list
    holdings_after = get_user_holdings(user_id)
    print(f"\n[TEST 1] Holdings List")
    print(f"  Before: {len(holdings_before)} holdings")
    print(f"  After: {len(holdings_after)} holdings")

    holdings_removed = len(holdings_after) == len(holdings_before) - 1
    print(f"  Holding removed from list: {'[PASS]' if holdings_removed else '[FAIL]'}")

    # Verify the specific holding is not in the list
    excluded_in_list = any(h['order_item_id'] == order_item_id for h in holdings_after)
    print(f"  Excluded item NOT in holdings: {'[PASS]' if not excluded_in_list else '[FAIL]'}")

    # 3b. Portfolio value and cost basis
    value_after = calculate_portfolio_value(user_id)
    print(f"\n[TEST 2] Portfolio Value & Cost Basis")
    print(f"  Total value before: ${value_before['total_value']:,.2f}")
    print(f"  Total value after: ${value_after['total_value']:,.2f}")
    print(f"  Expected after: ${expected_value_after:,.2f}")

    value_matches = verify_exact_match(expected_value_after, value_after['total_value'])
    print(f"  Value decreased by exact amount: {'[PASS]' if value_matches else '[FAIL]'}")

    print(f"\n  Cost basis before: ${value_before['cost_basis']:,.2f}")
    print(f"  Cost basis after: ${value_after['cost_basis']:,.2f}")
    print(f"  Expected after: ${expected_cost_after:,.2f}")

    cost_matches = verify_exact_match(expected_cost_after, value_after['cost_basis'])
    print(f"  Cost decreased by exact amount: {'[PASS]' if cost_matches else '[FAIL]'}")

    # 3c. Historical data (all ranges)
    print(f"\n[TEST 3] Historical Data (All Ranges)")

    history_1d_after = get_portfolio_history(user_id, days=1)
    history_1w_after = get_portfolio_history(user_id, days=7)
    history_1m_after = get_portfolio_history(user_id, days=30)
    history_3m_after = get_portfolio_history(user_id, days=90)
    history_1y_after = get_portfolio_history(user_id, days=365)

    all_history_tests = []

    for range_name, history_data in [
        ("1D", history_1d_after),
        ("1W", history_1w_after),
        ("1M", history_1m_after),
        ("3M", history_3m_after),
        ("1Y", history_1y_after)
    ]:
        if history_data:
            latest = history_data[-1]
            latest_value = latest['total_value']
            latest_cost = latest['total_cost_basis']

            value_ok = verify_exact_match(expected_value_after, latest_value)
            cost_ok = verify_exact_match(expected_cost_after, latest_cost)

            print(f"  {range_name} - Latest value: ${latest_value:,.2f} {'[PASS]' if value_ok else '[FAIL]'}")
            print(f"     Latest cost: ${latest_cost:,.2f} {'[PASS]' if cost_ok else '[FAIL]'}")

            all_history_tests.append(value_ok and cost_ok)
        else:
            print(f"  {range_name} - No history data")
            all_history_tests.append(False)

    # Verify all historical points exclude the item (not just the latest)
    print(f"\n  Verifying ALL historical points exclude the item...")

    all_points_correct = True
    for i, point in enumerate(history_1m_after):
        # Each historical point should be <= expected_value_after
        # (can't be higher since we removed an item)
        if point['total_value'] > expected_value_after + 0.01:  # small tolerance
            print(f"    Point {i}: ${point['total_value']:,.2f} > expected ${expected_value_after:,.2f} [FAIL]")
            all_points_correct = False

    if all_points_correct:
        print(f"  All historical points respect exclusion: [PASS]")
    else:
        print(f"  Some historical points still include excluded item: [FAIL]")

    # 3d. Allocation by metal
    allocation_after = get_portfolio_allocation(user_id)
    print(f"\n[TEST 4] Allocation by Metal")
    print(f"  Before exclusion:")
    for alloc in allocation_before:
        print(f"    {alloc['metal']}: ${alloc['value']:,.2f} ({alloc['percentage']:.1f}%)")

    print(f"  After exclusion:")
    for alloc in allocation_after:
        print(f"    {alloc['metal']}: ${alloc['value']:,.2f} ({alloc['percentage']:.1f}%)")

    # Verify excluded metal's allocation decreased (or disappeared if it was the only item)
    excluded_metal = test_holding['metal']

    before_metal = next((a for a in allocation_before if a['metal'] == excluded_metal), None)
    after_metal = next((a for a in allocation_after if a['metal'] == excluded_metal), None)

    if before_metal:
        expected_metal_value = before_metal['value'] - excluded_value
        if expected_metal_value < 0.01:  # Essentially zero
            metal_ok = after_metal is None
            print(f"  {excluded_metal} removed from allocation: {'[PASS]' if metal_ok else '[FAIL]'}")
        else:
            metal_ok = after_metal and verify_exact_match(expected_metal_value, after_metal['value'])
            print(f"  {excluded_metal} value decreased correctly: {'[PASS]' if metal_ok else '[FAIL]'}")
    else:
        metal_ok = True
        print(f"  Could not find {excluded_metal} in allocation")

    # Step 4: Test re-inclusion
    print_separator("STEP 4: Re-including Holding")

    success = include_holding(user_id, order_item_id)
    if not success:
        print("[ERROR] Failed to re-include holding!")
        return False

    print(f"[SUCCESS] Re-included order_item_id {order_item_id}")

    # Verify restoration
    holdings_restored = get_user_holdings(user_id)
    value_restored = calculate_portfolio_value(user_id)

    print(f"\nAfter re-inclusion:")
    print(f"  Holdings count: {len(holdings_restored)} (original: {len(holdings_before)})")
    print(f"  Portfolio value: ${value_restored['total_value']:,.2f} (original: ${value_before['total_value']:,.2f})")
    print(f"  Cost basis: ${value_restored['cost_basis']:,.2f} (original: ${value_before['cost_basis']:,.2f})")

    restored_ok = (
        len(holdings_restored) == len(holdings_before) and
        verify_exact_match(value_restored['total_value'], value_before['total_value']) and
        verify_exact_match(value_restored['cost_basis'], value_before['cost_basis'])
    )
    print(f"  Values restored correctly: {'[PASS]' if restored_ok else '[FAIL]'}")

    # Summary
    print_separator("TEST SUMMARY")

    tests = [
        ("Holdings list updated", holdings_removed and not excluded_in_list),
        ("Portfolio value decreased exactly", value_matches),
        ("Cost basis decreased exactly", cost_matches),
        ("All historical ranges updated", all(all_history_tests)),
        ("All historical points respect exclusion", all_points_correct),
        ("Allocation updated", metal_ok),
        ("Re-inclusion restored values", restored_ok)
    ]

    all_passed = all(result for _, result in tests)

    for name, result in tests:
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {status} - {name}")

    print()

    if all_passed:
        print("="*70)
        print("  ALL EXCLUSION TESTS PASSED!")
        print("="*70)
        print("\nExcluded items are completely removed from:")
        print("  - Current holdings list")
        print("  - Portfolio value and cost basis")
        print("  - ALL historical time-series data (1D/1W/1M/3M/1Y)")
        print("  - Allocation by metal")
        print("\nThe system correctly treats excluded items 'as if never purchased'.")
    else:
        print("="*70)
        print("  SOME TESTS FAILED")
        print("="*70)
        print("\nPlease review the test output above for details.")
        print("Some calculations may still include excluded items.")

    return all_passed

def main():
    """Run comprehensive exclusion test"""

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
        print("[WARNING] User 3 has no orders. Cannot test exclusions.")
        print("Please ensure the test user has purchased items first.")
        return

    print(f"User has {order_count} order items - proceeding with test...")

    # Run comprehensive test
    test_complete_exclusion_removal(user_id=3)

if __name__ == '__main__':
    main()
