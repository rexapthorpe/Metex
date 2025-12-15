"""Diagnose portfolio chart data issue"""
from database import get_db_connection
from services.portfolio_service import get_user_holdings, calculate_portfolio_value, get_portfolio_history

# Test with a known user ID (you'll need to replace this with an actual user ID)
print("=" * 70)
print("PORTFOLIO CHART DIAGNOSTIC")
print("=" * 70)

conn = get_db_connection()

# Get a user with orders
users_with_orders = conn.execute("""
    SELECT DISTINCT o.buyer_id, u.email, COUNT(oi.order_item_id) as item_count
    FROM orders o
    JOIN users u ON o.buyer_id = u.id
    JOIN order_items oi ON o.id = oi.order_id
    GROUP BY o.buyer_id
    LIMIT 5
""").fetchall()

print(f"\nFound {len(users_with_orders)} users with orders\n")

if not users_with_orders:
    print("No users with orders found!")
    conn.close()
    exit()

# Test with the first user
test_user = users_with_orders[0]
user_id = test_user['buyer_id']
user_email = test_user['email']
item_count = test_user['item_count']

print(f"Testing with user: {user_email} (ID: {user_id}, {item_count} items)")
print("=" * 70)

# Test get_user_holdings
print("\n1. Testing get_user_holdings()...")
holdings = get_user_holdings(user_id)
print(f"   Holdings count: {len(holdings)}")
if holdings:
    print(f"   First holding: {holdings[0]['metal']} {holdings[0]['product_type']}")
    print(f"   Purchase price: ${holdings[0]['purchase_price']}")
    print(f"   Current market price: ${holdings[0].get('current_market_price', 'None')}")

# Test calculate_portfolio_value
print("\n2. Testing calculate_portfolio_value()...")
portfolio_value = calculate_portfolio_value(user_id)
print(f"   Total value: ${portfolio_value['total_value']}")
print(f"   Cost basis: ${portfolio_value['cost_basis']}")
print(f"   Gain/Loss: ${portfolio_value['gain_loss']}")
print(f"   Holdings count: {portfolio_value['holdings_count']}")

# Test get_portfolio_history for different time ranges
time_ranges = ['1d', '1w', '1m']
for time_range in time_ranges:
    print(f"\n3. Testing get_portfolio_history(range='{time_range}')...")

    # Map range to days
    range_map = {'1d': 1, '1w': 7, '1m': 30}
    days = range_map[time_range]

    history = get_portfolio_history(user_id, days)
    print(f"   History points: {len(history)}")

    if history:
        # Show first, middle, and last points
        print(f"   First point: {history[0]['snapshot_date'][:10]} - Value: ${history[0]['total_value']}, Cost: ${history[0]['total_cost_basis']}")
        if len(history) > 2:
            mid = len(history) // 2
            print(f"   Middle point: {history[mid]['snapshot_date'][:10]} - Value: ${history[mid]['total_value']}, Cost: ${history[mid]['total_cost_basis']}")
        print(f"   Last point: {history[-1]['snapshot_date'][:10]} - Value: ${history[-1]['total_value']}, Cost: ${history[-1]['total_cost_basis']}")

        # Check if all values are zero
        all_zero = all(h['total_value'] == 0 for h in history)
        if all_zero:
            print("   [!] WARNING: All history values are ZERO!")
        else:
            print("   [OK] History contains non-zero values")

conn.close()

print("\n" + "=" * 70)
print("DIAGNOSTIC COMPLETE")
print("=" * 70)
