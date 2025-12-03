"""
Test Portfolio Endpoint
Verifies /portfolio/data returns valid JSON
"""

import requests
import json

print("\n" + "="*60)
print("TESTING PORTFOLIO ENDPOINT")
print("="*60)

# Test 1: Check if endpoint exists
print("\nTest 1: Checking if /portfolio/data endpoint responds...")
try:
    response = requests.get('http://127.0.0.1:5000/portfolio/data')
    print(f"Status Code: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type', 'Not set')}")

    if response.status_code == 401:
        print("✓ Endpoint exists (returns 401 - authentication required)")
        print("  This is expected when not logged in")
    elif response.status_code == 200:
        print("✓ Endpoint exists and returns 200")
        try:
            data = response.json()
            print(f"✓ Response is valid JSON")
            print(f"  Keys in response: {list(data.keys())}")
        except:
            print("✗ Response is not valid JSON")
            print(f"  Response text: {response.text[:200]}")
    elif response.status_code == 404:
        print("✗ Endpoint NOT FOUND (404)")
        print(f"  Response: {response.text[:500]}")
    else:
        print(f"? Unexpected status code: {response.status_code}")
        print(f"  Response: {response.text[:500]}")
except Exception as e:
    print(f"✗ Error connecting to endpoint: {e}")

# Test 2: Check if portfolio routes are registered
print("\nTest 2: Checking Flask route registration...")
try:
    from app import app
    portfolio_routes = [str(rule) for rule in app.url_map.iter_rules() if 'portfolio' in str(rule)]
    print(f"✓ Found {len(portfolio_routes)} portfolio routes:")
    for route in portfolio_routes:
        print(f"  - {route}")
except Exception as e:
    print(f"✗ Error checking routes: {e}")

# Test 3: Direct database query test
print("\nTest 3: Testing database connection and queries...")
try:
    from services.portfolio_service import calculate_portfolio_value, get_user_holdings
    import sqlite3

    # Get first user
    conn = sqlite3.connect('metex.db')
    conn.row_factory = sqlite3.Row
    user = conn.execute("SELECT id, username FROM users LIMIT 1").fetchone()

    if user:
        user_id = user['id']
        print(f"✓ Testing with user: {user['username']} (ID: {user_id})")

        # Test holdings
        holdings = get_user_holdings(user_id)
        print(f"✓ Holdings query returned {len(holdings)} items")

        # Test portfolio value
        portfolio_value = calculate_portfolio_value(user_id)
        print(f"✓ Portfolio value calculation:")
        print(f"  Total Value: ${portfolio_value['total_value']:.2f}")
        print(f"  Cost Basis: ${portfolio_value['cost_basis']:.2f}")
        print(f"  Holdings Count: {portfolio_value['holdings_count']}")
    else:
        print("✗ No users found in database")

    conn.close()
except Exception as e:
    print(f"✗ Database query error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
print("TEST COMPLETE")
print("="*60 + "\n")
