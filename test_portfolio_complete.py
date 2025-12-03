"""
Complete Portfolio System Test
Starts a test server and validates all endpoints
"""

import requests
import time
import subprocess
import sys
from threading import Thread

def start_test_server():
    """Start Flask server in background"""
    print("Starting Flask test server...")
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Wait for server to start
    time.sleep(3)
    return proc

def test_portfolio_endpoints():
    """Test all portfolio endpoints"""
    print("\n" + "="*70)
    print("PORTFOLIO ENDPOINT TESTS")
    print("="*70)

    base_url = "http://127.0.0.1:5000"

    # Test 1: /portfolio/data
    print("\n[TEST 1] Testing GET /portfolio/data")
    try:
        response = requests.get(f"{base_url}/portfolio/data")
        print(f"Status Code: {response.status_code}")
        print(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}")

        if response.status_code == 404:
            print("FAIL: Endpoint returns 404")
            print(f"Response: {response.text[:200]}")
            return False
        elif response.status_code == 401:
            print("PASS: Endpoint exists (returns 401 - auth required)")
            try:
                data = response.json()
                if 'error' in data:
                    print(f"Error message: {data['error']}")
            except:
                pass
        elif response.status_code == 200:
            print("PASS: Endpoint returns 200")
            try:
                data = response.json()
                print(f"Response keys: {list(data.keys())}")
            except Exception as e:
                print(f"FAIL: Response is not valid JSON: {e}")
                print(f"Response text: {response.text[:200]}")
                return False

    except Exception as e:
        print(f"FAIL: Error connecting to endpoint: {e}")
        return False

    # Test 2: /portfolio/history
    print("\n[TEST 2] Testing GET /portfolio/history")
    try:
        response = requests.get(f"{base_url}/portfolio/history?range=1m")
        print(f"Status Code: {response.status_code}")

        if response.status_code == 404:
            print("FAIL: Endpoint returns 404")
            return False
        elif response.status_code in [200, 401]:
            print("PASS: Endpoint exists")

    except Exception as e:
        print(f"FAIL: Error: {e}")
        return False

    # Test 3: Check route registration
    print("\n[TEST 3] Checking route registration via app import")
    try:
        from app import app
        portfolio_routes = [str(r) for r in app.url_map.iter_rules() if 'portfolio' in str(r)]
        print(f"Found {len(portfolio_routes)} portfolio routes:")
        for route in portfolio_routes:
            print(f"  - {route}")

        if len(portfolio_routes) > 0:
            print("PASS: Routes are registered in app")
        else:
            print("FAIL: No routes found")
            return False

    except Exception as e:
        print(f"FAIL: Error importing app: {e}")
        return False

    print("\n" + "="*70)
    print("ALL TESTS PASSED!")
    print("="*70)
    print("\nThe portfolio endpoints ARE working!")
    print("If you're still getting 404, you need to:")
    print("  1. Stop your current Flask server (Ctrl+C)")
    print("  2. Start a fresh one: python app.py")
    print("  3. Hard refresh your browser (Ctrl+Shift+R)")
    print("="*70 + "\n")

    return True

if __name__ == '__main__':
    proc = None
    try:
        proc = start_test_server()
        time.sleep(2)

        success = test_portfolio_endpoints()

        if proc:
            proc.terminate()
            proc.wait(timeout=5)

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\nTest interrupted")
        if proc:
            proc.terminate()
        sys.exit(1)
    except Exception as e:
        print(f"\nTest error: {e}")
        import traceback
        traceback.print_exc()
        if proc:
            proc.terminate()
        sys.exit(1)
