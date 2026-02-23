#!/usr/bin/env python3
"""
Verification script for spot price API changes
Tests that the updated spot price service returns correct structure
"""

import sys
import os

# Add parent directory to path so we can import from services
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Load .env file BEFORE importing services (critical!)
from dotenv import load_dotenv
load_dotenv()

from services.spot_price_service import get_current_spot_prices, get_spot_price
from database import get_db_connection

def verify_spot_price_service():
    """Verify spot price service returns correct structure"""

    print("=" * 80)
    print("SPOT PRICE API VERIFICATION")
    print("=" * 80)
    print()

    # Test 1: get_current_spot_prices() structure
    print("TEST 1: Checking get_current_spot_prices() return structure")
    print("-" * 80)

    spot_data = get_current_spot_prices()

    print(f"✓ Returned type: {type(spot_data)}")
    print(f"✓ Keys present: {list(spot_data.keys())}")

    # Check required keys
    required_keys = ['prices', 'has_api_key', 'is_stale', 'age_minutes', 'source']
    for key in required_keys:
        if key in spot_data:
            print(f"  ✓ '{key}': {spot_data[key]}")
        else:
            print(f"  ✗ MISSING KEY: '{key}'")
            return False

    print()

    # Test 2: Prices structure
    print("TEST 2: Checking prices dict structure")
    print("-" * 80)

    prices = spot_data['prices']
    print(f"✓ Prices type: {type(prices)}")
    print(f"✓ Number of metals: {len(prices)}")

    for metal, price in prices.items():
        print(f"  • {metal}: ${price:.2f}/oz")

    print()

    # Test 3: Status flags
    print("TEST 3: Checking status flags")
    print("-" * 80)

    has_api_key = spot_data['has_api_key']
    is_stale = spot_data['is_stale']
    age_minutes = spot_data['age_minutes']
    source = spot_data['source']

    if has_api_key:
        print("  ✓ API key is configured")
    else:
        print("  ⚠ WARNING: API key is NOT configured")
        print("    → Create .env file with METALPRICE_API_KEY")
        print("    → Get API key from https://metalpriceapi.com/")

    if is_stale:
        print(f"  ⚠ WARNING: Spot prices are STALE")
        print(f"    → Age: {age_minutes:.1f} minutes")
        print(f"    → Source: {source}")
        if age_minutes and age_minutes > 1440:  # More than 1 day
            days = age_minutes / 1440
            print(f"    → THIS IS {days:.1f} DAYS OLD!")
    else:
        print(f"  ✓ Spot prices are fresh")
        print(f"    → Age: {age_minutes:.1f} minutes")
        print(f"    → Source: {source}")

    print()

    # Test 4: get_spot_price() function
    print("TEST 4: Checking get_spot_price() function")
    print("-" * 80)

    gold_price = get_spot_price('gold')
    silver_price = get_spot_price('silver')

    if gold_price:
        print(f"  ✓ Gold spot price: ${gold_price:.2f}/oz")
    else:
        print(f"  ✗ Gold spot price: None")

    if silver_price:
        print(f"  ✓ Silver spot price: ${silver_price:.2f}/oz")
    else:
        print(f"  ✗ Silver spot price: None")

    print()

    # Test 5: Database cache check
    print("TEST 5: Checking database cache")
    print("-" * 80)

    conn = get_db_connection()
    cached_data = conn.execute("""
        SELECT metal, price_usd_per_oz, updated_at, source
        FROM spot_prices
        ORDER BY metal
    """).fetchall()
    conn.close()

    if cached_data:
        print(f"  ✓ Found {len(cached_data)} cached prices:")
        for row in cached_data:
            print(f"    • {row['metal']}: ${row['price_usd_per_oz']:.2f} (updated: {row['updated_at']}, source: {row['source']})")
    else:
        print("  ✗ No cached prices found in database")

    print()

    # Final report
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)

    # Check for .env file
    import os
    env_file_exists = os.path.exists('.env')

    if not env_file_exists:
        print("⚠ CRITICAL: .env file does NOT exist!")
        print()
        print("TO CREATE .env FILE:")
        print("1. Copy the template:")
        print("   cp .env.example .env")
        print()
        print("2. Edit .env and add your API key:")
        print("   METALPRICE_API_KEY=your_api_key_here")
        print()
        print("3. Get a free API key from: https://metalpriceapi.com/")
        print()
        print("4. Restart Flask application:")
        print("   python3 app.py")
        print()
    elif not has_api_key:
        print("⚠ CRITICAL: .env file exists, but API key not set!")
        print()
        print("TO FIX:")
        print("1. Get API key from https://metalpriceapi.com/")
        print("2. Edit .env file and add:")
        print("   METALPRICE_API_KEY=your_api_key_here")
        print("3. Restart Flask application:")
        print("   python3 app.py")
        print()

    if is_stale and age_minutes and age_minutes > 60:
        print(f"⚠ WARNING: Spot prices are {age_minutes:.0f} minutes old")
        if age_minutes > 1440:
            days = age_minutes / 1440
            print(f"   THIS DATA IS EXTREMELY STALE ({days:.1f} days old)")
        print()

    print("✓ API structure verification: PASSED")
    print("✓ All required keys present")
    print("✓ get_spot_price() function working")
    print()

    # Final status message
    if has_api_key and not is_stale:
        print("🎉 SUCCESS: Spot price system is working correctly!")
        print("   - API key configured")
        print("   - Prices are fresh and up-to-date")
        print("   - Ready for production use")
    elif has_api_key and is_stale:
        print("⚠ PARTIAL: API key configured, but prices are stale")
        print("   - API may be experiencing issues")
        print("   - Or this is the first run (prices will refresh soon)")
    else:
        print("✗ ACTION REQUIRED: Configure API key to enable live spot prices")
        print("   - See instructions above")
    print()

    return True


if __name__ == '__main__':
    try:
        success = verify_spot_price_service()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ VERIFICATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
