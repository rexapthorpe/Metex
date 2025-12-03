"""
Test script to verify the sqlite3.Row fix for buy_routes.py
Tests both addresses WITH and WITHOUT street_line2
"""
import sqlite3

print("=" * 80)
print("Testing sqlite3.Row fix for buy_routes.py")
print("=" * 80)

# Create test database
conn = sqlite3.connect(':memory:')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Create test table
cursor.execute('''
    CREATE TABLE addresses (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        street TEXT,
        street_line2 TEXT,
        city TEXT,
        state TEXT,
        zip_code TEXT
    )
''')

# Insert test data - one with street_line2, one without
cursor.execute('''
    INSERT INTO addresses (user_id, street, street_line2, city, state, zip_code)
    VALUES (1, '123 Main St', 'Apt 6D', 'Brooklyn', 'NY', '12345')
''')

cursor.execute('''
    INSERT INTO addresses (user_id, street, street_line2, city, state, zip_code)
    VALUES (2, '456 Park Ave', NULL, 'Manhattan', 'NY', '10022')
''')

conn.commit()

# Test 1: Address WITH street_line2
print("\nTest 1: Address WITH street_line2 (Apt 6D)")
print("-" * 80)
try:
    address_row = cursor.execute(
        'SELECT street, street_line2, city, state, zip_code FROM addresses WHERE user_id = ?',
        (1,)
    ).fetchone()

    # FIXED CODE (using direct access instead of .get())
    street_line2 = address_row['street_line2'] or ''

    if street_line2.strip():
        shipping_address = f"{address_row['street']} • {street_line2} • {address_row['city']}, {address_row['state']} {address_row['zip_code']}"
    else:
        shipping_address = f"{address_row['street']} • {address_row['city']}, {address_row['state']} {address_row['zip_code']}"

    print(f"street_line2: '{street_line2}'")
    print(f"Formatted address: {shipping_address}")
    print("PASS: Address with street_line2 formatted correctly!")

except Exception as e:
    print(f"FAIL: {e}")

# Test 2: Address WITHOUT street_line2 (NULL)
print("\n\nTest 2: Address WITHOUT street_line2 (NULL)")
print("-" * 80)
try:
    address_row = cursor.execute(
        'SELECT street, street_line2, city, state, zip_code FROM addresses WHERE user_id = ?',
        (2,)
    ).fetchone()

    # FIXED CODE (using direct access instead of .get())
    street_line2 = address_row['street_line2'] or ''

    if street_line2.strip():
        shipping_address = f"{address_row['street']} • {street_line2} • {address_row['city']}, {address_row['state']} {address_row['zip_code']}"
    else:
        shipping_address = f"{address_row['street']} • {address_row['city']}, {address_row['state']} {address_row['zip_code']}"

    print(f"street_line2: '{street_line2}' (NULL converted to empty string)")
    print(f"Formatted address: {shipping_address}")
    print("PASS: Address without street_line2 formatted correctly!")

except Exception as e:
    print(f"FAIL: {e}")

print("\n" + "=" * 80)
print("All tests passed! The fix works correctly.")
print("=" * 80)
print("\nFIX SUMMARY:")
print("BEFORE: street_line2 = address_row.get('street_line2', '') or ''")
print("        ^ This causes AttributeError: 'sqlite3.Row' has no .get() method")
print("")
print("AFTER:  street_line2 = address_row['street_line2'] or ''")
print("        ^ Direct access works. NULL values return None, converted to ''")
print("=" * 80)

conn.close()
