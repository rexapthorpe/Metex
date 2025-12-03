"""
Test script to reproduce and verify fix for sqlite3.Row .get() error
"""
import sqlite3

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

print("=" * 80)
print("Testing sqlite3.Row access methods")
print("=" * 80)

# Test 1: Reproduce the error with .get()
print("\nTest 1: Trying to use .get() method (WILL FAIL)")
print("-" * 80)
try:
    address_row = cursor.execute(
        'SELECT street, street_line2, city, state, zip_code FROM addresses WHERE user_id = ?',
        (1,)
    ).fetchone()

    print(f"Address row type: {type(address_row)}")
    print(f"Address row keys: {address_row.keys()}")

    # This will fail with AttributeError
    street_line2 = address_row.get('street_line2', '') or ''
    print(f"street_line2 using .get(): '{street_line2}'")
    print("✓ .get() method worked (unexpected!)")

except AttributeError as e:
    print(f"✗ AttributeError: {e}")
    print("  This is the error the user is experiencing!")

# Test 2: Correct way - direct access
print("\n\nTest 2: Using direct access (CORRECT METHOD)")
print("-" * 80)
try:
    # Test with address that HAS street_line2
    address_row = cursor.execute(
        'SELECT street, street_line2, city, state, zip_code FROM addresses WHERE user_id = ?',
        (1,)
    ).fetchone()

    street_line2 = address_row['street_line2'] or ''
    print(f"User 1 (with Apt): street_line2 = '{street_line2}'")

    if street_line2.strip():
        shipping_address = f"{address_row['street']} • {street_line2} • {address_row['city']}, {address_row['state']} {address_row['zip_code']}"
    else:
        shipping_address = f"{address_row['street']} • {address_row['city']}, {address_row['state']} {address_row['zip_code']}"

    print(f"Formatted address: {shipping_address}")
    print("✓ Direct access worked!")

except Exception as e:
    print(f"✗ Error: {e}")

# Test 3: Direct access with NULL value
print("\n\nTest 3: Direct access with NULL street_line2")
print("-" * 80)
try:
    # Test with address that does NOT have street_line2 (NULL)
    address_row = cursor.execute(
        'SELECT street, street_line2, city, state, zip_code FROM addresses WHERE user_id = ?',
        (2,)
    ).fetchone()

    street_line2 = address_row['street_line2'] or ''
    print(f"User 2 (no Apt): street_line2 = '{street_line2}' (was NULL)")

    if street_line2.strip():
        shipping_address = f"{address_row['street']} • {street_line2} • {address_row['city']}, {address_row['state']} {address_row['zip_code']}"
    else:
        shipping_address = f"{address_row['street']} • {address_row['city']}, {address_row['state']} {address_row['zip_code']}"

    print(f"Formatted address: {shipping_address}")
    print("✓ Direct access with NULL value worked!")

except Exception as e:
    print(f"✗ Error: {e}")

print("\n" + "=" * 80)
print("Summary:")
print("=" * 80)
print("✗ address_row.get('key', default) - DOES NOT WORK (AttributeError)")
print("✓ address_row['key'] or '' - WORKS (handles None/NULL correctly)")
print("=" * 80)

conn.close()
