"""Debug portfolio history calculation with detailed output"""
from database import get_db_connection
from datetime import datetime, timedelta

user_id = 4
days = 1  # 1D range

conn = get_db_connection()

# Get all order_items for this user with their purchase dates
all_items = conn.execute("""
    SELECT
        oi.order_item_id,
        oi.quantity,
        oi.price_each AS purchase_price,
        o.created_at AS purchase_date,
        c.bucket_id
    FROM order_items oi
    JOIN orders o ON oi.order_id = o.id
    JOIN listings l ON oi.listing_id = l.id
    JOIN categories c ON l.category_id = c.id
    WHERE o.buyer_id = ?
      AND oi.order_item_id NOT IN (
          SELECT order_item_id
          FROM portfolio_exclusions
          WHERE user_id = ?
      )
    ORDER BY o.created_at ASC
""", (user_id, user_id)).fetchall()

print("=" * 70)
print("PORTFOLIO HISTORY DEBUGGING")
print("=" * 70)

print(f"\nFound {len(all_items)} items for user {user_id}")

if not all_items:
    print("No items found!")
    conn.close()
    exit()

print("\nItem details:")
for item in all_items:
    item_dict = dict(item)
    print(f"  Item {item_dict['order_item_id']}: Qty {item_dict['quantity']}, Price ${item_dict['purchase_price']}")
    print(f"    Purchase date (raw): {item_dict['purchase_date']}")
    purchase_dt = datetime.fromisoformat(item_dict['purchase_date'])
    print(f"    Purchase datetime: {purchase_dt}")
    print()

# Generate time points
start_date = datetime.now() - timedelta(days=days)
now = datetime.now()

print(f"Time range:")
print(f"  Start: {start_date}")
print(f"  Now: {now}")
print()

# Generate time points for 1D (every hour, 24 points)
time_points = []
for i in range(25):  # 25 points (0-24 hours)
    time_points.append(start_date + timedelta(hours=i))

# Ensure last point is exactly now
time_points[-1] = now

# Remove any points beyond now
time_points = sorted([tp for tp in time_points if tp <= now])

print(f"Generated {len(time_points)} time points")
print(f"  First: {time_points[0]}")
print(f"  Last: {time_points[-1]}")
print()

# Calculate value at each time point
print("Calculating portfolio value at each time point:")
print("-" * 70)

for i, time_point in enumerate(time_points):
    is_current = (i == len(time_points) - 1)

    total_value = 0.0
    total_cost = 0.0
    included_items = 0

    for item in all_items:
        item_dict = dict(item)
        purchase_dt = datetime.fromisoformat(item_dict['purchase_date'])

        # Check if item existed at this time point
        if purchase_dt <= time_point:
            included_items += 1
            quantity = item_dict['quantity']
            purchase_price = item_dict['purchase_price']

            total_cost += quantity * purchase_price

            if is_current:
                # For current point, use current market price (simplified - using purchase price)
                total_value += quantity * purchase_price
            else:
                # For historical points, use purchase price
                total_value += quantity * purchase_price

    if i == 0 or i == len(time_points) - 1 or included_items > 0:
        print(f"Point {i}: {time_point}")
        print(f"  Included items: {included_items}")
        print(f"  Total value: ${total_value}")
        print(f"  Total cost: ${total_cost}")

        if included_items == 0:
            print("  [!] NO ITEMS INCLUDED - Value is 0")
            # Debug why items weren't included
            for item in all_items:
                item_dict = dict(item)
                purchase_dt = datetime.fromisoformat(item_dict['purchase_date'])
                print(f"      Item {item_dict['order_item_id']}: purchase_dt ({purchase_dt}) > time_point ({time_point})? {purchase_dt > time_point}")
        print()

conn.close()

print("=" * 70)
print("DEBUG COMPLETE")
print("=" * 70)
