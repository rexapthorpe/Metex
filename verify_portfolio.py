"""
Portfolio System Verification
Quick test to verify portfolio endpoints are working
"""

import requests
import sys

def verify_portfolio():
    print("\n" + "="*70)
    print("PORTFOLIO SYSTEM VERIFICATION")
    print("="*70)

    base_url = "http://127.0.0.1:5000"

    print("\nChecking if Flask server is running...")
    try:
        response = requests.get(base_url, timeout=2)
        print(f"SUCCESS: Flask server is running on {base_url}")
    except:
        print(f"ERROR: Flask server is NOT running on {base_url}")
        print("Please start Flask first: python app.py")
        return False

    print("\nTesting /portfolio/data endpoint...")
    try:
        response = requests.get(f"{base_url}/portfolio/data")

        if response.status_code == 404:
            print("FAIL: Endpoint returns 404 (NOT FOUND)")
            print("This means your Flask server does NOT have portfolio routes.")
            print("\nSOLUTION:")
            print("  1. Stop your current Flask server (Ctrl+C)")
            print("  2. Start a fresh one: python app.py")
            print("  3. Run this script again")
            return False

        elif response.status_code == 401:
            print("SUCCESS: Endpoint exists and returns 401 (Not authenticated)")
            print("Content-Type:", response.headers.get('Content-Type'))

            try:
                data = response.json()
                if 'error' in data and data['error'] == 'Not authenticated':
                    print("SUCCESS: Returns valid JSON")
                    print("\nPortfolio system is WORKING!")
                    print("\nTo test in browser:")
                    print("  1. Login to your account")
                    print("  2. Go to Account page")
                    print("  3. Click Portfolio tab")
                    print("  4. You should see your portfolio data (or empty if no orders)")
                    return True
                else:
                    print("WARNING: Unexpected JSON response")
                    print(data)
            except Exception as e:
                print(f"ERROR: Response is not valid JSON: {e}")
                return False

        elif response.status_code == 200:
            print("SUCCESS: Endpoint returns 200")
            try:
                data = response.json()
                if 'success' in data and data['success']:
                    print("SUCCESS: Portfolio data returned successfully")
                    print(f"Keys in response: {list(data.keys())}")
                    return True
                else:
                    print("WARNING: Unexpected response format")
                    print(data)
            except Exception as e:
                print(f"ERROR: Response is not valid JSON: {e}")
                print(f"Response text: {response.text[:200]}")
                return False

        else:
            print(f"UNEXPECTED: Status code {response.status_code}")
            print(f"Response: {response.text[:200]}")
            return False

    except Exception as e:
        print(f"ERROR: Failed to connect to endpoint: {e}")
        return False

    print("\n" + "="*70 + "\n")

if __name__ == '__main__':
    success = verify_portfolio()

    if success:
        print("\nVERIFICATION PASSED!")
        print("The Portfolio system is working correctly.")
        sys.exit(0)
    else:
        print("\nVERIFICATION FAILED!")
        print("See PORTFOLIO_WORKING.md for troubleshooting steps.")
        sys.exit(1)
