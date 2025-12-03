"""
Quick test to verify the import fix for get_effective_bid_price in buy_routes.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_import():
    """Test that buy_routes can import and use get_effective_bid_price"""
    print("Testing import fix...")

    try:
        # Import the module
        from routes import buy_routes

        # Verify the function is available
        assert hasattr(buy_routes, 'get_effective_bid_price'), "get_effective_bid_price not found in buy_routes"

        # Verify it's callable
        assert callable(buy_routes.get_effective_bid_price), "get_effective_bid_price is not callable"

        print("[PASS] Import fix successful - get_effective_bid_price is available in buy_routes")
        return True

    except ImportError as e:
        print(f"[FAIL] Import error: {e}")
        return False
    except AssertionError as e:
        print(f"[FAIL] Assertion error: {e}")
        return False
    except Exception as e:
        print(f"[FAIL] Unexpected error: {e}")
        return False


def test_function_signature():
    """Test that the imported function has the correct signature"""
    print("\nTesting function signature...")

    try:
        from services.pricing_service import get_effective_bid_price
        import inspect

        # Get function signature
        sig = inspect.signature(get_effective_bid_price)
        params = list(sig.parameters.keys())

        # Should have 'bid' and optional 'spot_prices' parameters
        assert 'bid' in params, "Missing 'bid' parameter"

        print(f"[PASS] Function signature correct: {sig}")
        return True

    except Exception as e:
        print(f"[FAIL] Error checking signature: {e}")
        return False


if __name__ == '__main__':
    print("=" * 80)
    print("IMPORT FIX VERIFICATION")
    print("=" * 80)

    test1 = test_import()
    test2 = test_function_signature()

    print("\n" + "=" * 80)
    if test1 and test2:
        print("RESULT: All tests passed - Import fix successful!")
        sys.exit(0)
    else:
        print("RESULT: Some tests failed - Please check the errors above")
        sys.exit(1)
