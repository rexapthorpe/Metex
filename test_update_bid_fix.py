"""
Test that the update_bid route now has all required imports
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Verify that all necessary imports are present"""
    print("\n" + "="*70)
    print("TEST: Checking update_bid route imports")
    print("="*70)

    try:
        # Import the route module
        from routes import bid_routes

        # Check if get_effective_price is available
        if hasattr(bid_routes, 'get_effective_price'):
            print("\n[PASS] get_effective_price is imported")
        else:
            print("\n[FAIL] get_effective_price is NOT imported")
            return False

        # Check if get_spot_price is available
        if hasattr(bid_routes, 'get_spot_price'):
            print("[PASS] get_spot_price is imported")
        else:
            print("[FAIL] get_spot_price is NOT imported")
            return False

        print("\n" + "="*70)
        print("RESULT: All required imports are present!")
        print("="*70)

        print("\n[PASS] The update_bid route should now work correctly")
        print("\nManual testing steps:")
        print("1. Go to http://127.0.0.1:5000")
        print("2. Log in to your account")
        print("3. Navigate to 'Bids' tab")
        print("4. Click 'Edit' on an existing variable (premium-to-spot) bid")
        print("5. Change a value (e.g., increase the premium by $10)")
        print("6. Click 'Preview Bid'")
        print("7. Click 'Confirm Bid'")
        print("8. Success modal should now display:")
        print("   - Current Spot Price: (actual value, not '—')")
        print("   - Current Effective Bid Price: (calculated value, not '—')")
        print("   - Total Bid Value: (calculated total, not '—')")

        return True

    except Exception as e:
        print(f"\n[FAIL] Error importing: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)
