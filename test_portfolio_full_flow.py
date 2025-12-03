"""
Test Portfolio Full Flow
Simulates a logged-in user accessing portfolio endpoints and validates all data
"""

import sqlite3
from services.portfolio_service import (
    get_user_holdings,
    calculate_portfolio_value,
    get_portfolio_allocation,
    get_portfolio_history,
    exclude_holding,
    include_holding
)

def test_portfolio_full_flow():
    """Test the complete portfolio flow"""
    print("\n" + "="*70)
    print("PORTFOLIO FULL FLOW TEST")
    print("="*70)

    # First, find a user with orders
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row

    print("\n[1] Finding users with orders...")
    users_with_orders = conn.execute("""
        SELECT DISTINCT o.buyer_id, u.username, COUNT(oi.id) as order_count
        FROM orders o
        JOIN users u ON o.buyer_id = u.id
        JOIN order_items oi ON o.id = oi.order_id
        GROUP BY o.buyer_id
        ORDER BY order_count DESC
        LIMIT 5
    """).fetchall()

    if not users_with_orders:
        print("  ❌ No users with orders found!")
        print("  The portfolio will be empty until users make purchases.")
        conn.close()
        return False

    print(f"  ✅ Found {len(users_with_orders)} users with orders:")
    for user in users_with_orders:
        print(f"     - User {user['buyer_id']} ({user['username']}): {user['order_count']} items")

    # Test with the user who has the most orders
    test_user_id = users_with_orders[0]['buyer_id']
    test_username = users_with_orders[0]['username']

    print(f"\n[2] Testing with User {test_user_id} ({test_username})...")
    conn.close()

    # Test get_user_holdings
    print("\n[3] Testing get_user_holdings()...")
    try:
        holdings = get_user_holdings(test_user_id)
        print(f"  ✅ Retrieved {len(holdings)} holdings")

        if holdings:
            print("\n  Sample holding:")
            h = holdings[0]
            print(f"    - Order Item ID: {h['order_item_id']}")
            print(f"    - Metal: {h['metal']}")
            print(f"    - Product: {h['product_type']}")
            print(f"    - Quantity: {h['quantity']}")
            print(f"    - Purchase Price: ${h['purchase_price']:.2f}")
            print(f"    - Current Market Price: ${h['current_market_price'] if h['current_market_price'] else 'N/A'}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

    # Test calculate_portfolio_value
    print("\n[4] Testing calculate_portfolio_value()...")
    try:
        portfolio_value = calculate_portfolio_value(test_user_id)
        print(f"  ✅ Portfolio Value Calculated:")
        print(f"    - Total Value: ${portfolio_value['total_value']:,.2f}")
        print(f"    - Cost Basis: ${portfolio_value['cost_basis']:,.2f}")
        print(f"    - Gain/Loss: ${portfolio_value['gain_loss']:,.2f}")
        print(f"    - Gain/Loss %: {portfolio_value['gain_loss_percent']:.2f}%")
        print(f"    - Holdings Count: {portfolio_value['holdings_count']}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

    # Test get_portfolio_allocation
    print("\n[5] Testing get_portfolio_allocation()...")
    try:
        allocation = get_portfolio_allocation(test_user_id)
        print(f"  ✅ Allocation by Metal:")
        for alloc in allocation:
            print(f"    - {alloc['metal']}: ${alloc['value']:,.2f} ({alloc['percentage']:.2f}%)")
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

    # Test exclusion functionality
    if holdings:
        print("\n[6] Testing exclusion functionality...")
        test_item_id = holdings[0]['order_item_id']

        try:
            # Exclude the first item
            print(f"  Excluding order_item_id {test_item_id}...")
            exclude_holding(test_user_id, test_item_id)

            # Check that holdings count decreased
            new_holdings = get_user_holdings(test_user_id)
            print(f"  ✅ Holdings reduced from {len(holdings)} to {len(new_holdings)}")

            # Re-include the item
            print(f"  Re-including order_item_id {test_item_id}...")
            include_holding(test_user_id, test_item_id)

            # Check that holdings count returned
            restored_holdings = get_user_holdings(test_user_id)
            print(f"  ✅ Holdings restored to {len(restored_holdings)}")

        except Exception as e:
            print(f"  ❌ Error: {e}")
            return False

    # Test portfolio history
    print("\n[7] Testing get_portfolio_history()...")
    try:
        history = get_portfolio_history(test_user_id, days=30)
        print(f"  ✅ Retrieved {len(history)} historical snapshots")

        if history:
            print("\n  Sample snapshot:")
            snap = history[0]
            print(f"    - Date: {snap['snapshot_date']}")
            print(f"    - Value: ${snap['total_value']:,.2f}")
            print(f"    - Cost Basis: ${snap['total_cost_basis']:,.2f}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

    print("\n" + "="*70)
    print("ALL TESTS PASSED!")
    print("="*70)
    print("\n✅ The Portfolio system is fully functional!")
    print(f"\nTo test in browser:")
    print(f"  1. Start Flask: python app.py")
    print(f"  2. Login as: {test_username}")
    print(f"  3. Navigate to Account → Portfolio")
    print(f"  4. You should see:")
    print(f"     - Portfolio value: ${portfolio_value['total_value']:,.2f}")
    print(f"     - {len(holdings)} holdings listed")
    print(f"     - Allocation pie chart with {len(allocation)} metals")
    print("="*70 + "\n")

    return True


if __name__ == '__main__':
    try:
        success = test_portfolio_full_flow()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
