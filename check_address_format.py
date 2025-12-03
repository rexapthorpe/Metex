"""
Check address format in bids table and sample data
"""
import sqlite3

conn = sqlite3.connect('database.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("=" * 80)
print("BIDS TABLE SCHEMA - ADDRESS FIELD")
print("=" * 80)

# Get table schema
schema = cursor.execute("PRAGMA table_info(bids)").fetchall()
for col in schema:
    if 'address' in col['name'].lower():
        print(f"\nColumn: {col['name']}")
        print(f"  Type: {col['type']}")
        print(f"  Not Null: {col['notnull']}")
        print(f"  Default: {col['dflt_value']}")

print("\n" + "=" * 80)
print("SAMPLE BID DATA - DELIVERY ADDRESS")
print("=" * 80)

# Get sample bids with delivery addresses
bids = cursor.execute("""
    SELECT bids.id, bids.buyer_id, bids.delivery_address,
           users.username as buyer_name
    FROM bids
    JOIN users ON bids.buyer_id = users.id
    WHERE bids.delivery_address IS NOT NULL
    AND bids.delivery_address != ''
    LIMIT 5
""").fetchall()

if bids:
    for bid in bids:
        print(f"\nBid ID: {bid['id']}")
        print(f"Buyer: {bid['buyer_name']}")
        print(f"Address Type: {type(bid['delivery_address'])}")
        print(f"Address Value: {repr(bid['delivery_address'])}")
        print(f"Address Length: {len(bid['delivery_address']) if bid['delivery_address'] else 0}")
else:
    print("\nNo bids with delivery addresses found")

print("\n" + "=" * 80)
print("ALL BIDS - DELIVERY ADDRESS SUMMARY")
print("=" * 80)

summary = cursor.execute("""
    SELECT
        COUNT(*) as total_bids,
        COUNT(delivery_address) as bids_with_address,
        COUNT(CASE WHEN delivery_address IS NULL OR delivery_address = '' THEN 1 END) as bids_without_address
    FROM bids
""").fetchone()

print(f"\nTotal Bids: {summary['total_bids']}")
print(f"Bids with Address: {summary['bids_with_address']}")
print(f"Bids without Address: {summary['bids_without_address']}")

conn.close()
print("\n" + "=" * 80)
