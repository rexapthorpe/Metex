"""
Test MetalpriceAPI Connection
Verifies API key is configured and live spot prices can be fetched
"""

import os
from dotenv import load_dotenv
from services.spot_price_service import refresh_spot_prices, get_current_spot_prices

# Load environment variables
load_dotenv()

print("="*60)
print("METALPRICE API CONNECTION TEST")
print("="*60)

# Check if API key is loaded
api_key = os.getenv('METALPRICE_API_KEY')
if api_key:
    print(f"\n[OK] API Key loaded: {api_key[:8]}...{api_key[-4:]}")
else:
    print("\n[ERROR] API Key not found in environment variables")
    exit(1)

# Test API connection by refreshing spot prices
print("\n[TEST] Fetching live spot prices from MetalpriceAPI...")
print("-"*60)

success = refresh_spot_prices()

if success:
    print("\n[SUCCESS] Live spot prices fetched successfully!")

    # Display current spot prices
    prices = get_current_spot_prices()
    print("\n" + "="*60)
    print("CURRENT LIVE SPOT PRICES")
    print("="*60)

    for metal, price in prices.items():
        print(f"{metal.capitalize():12s}: ${price:.2f} per troy oz")

    print("="*60)
    print("\n[OPERATIONAL] MetalpriceAPI is fully configured and working!")
    print("\nThe premium-to-spot pricing system is now using LIVE market data.")

else:
    print("\n[ERROR] Failed to fetch live spot prices")
    print("Check API key and internet connection")
    exit(1)
