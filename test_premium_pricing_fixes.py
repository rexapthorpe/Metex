#!/usr/bin/env python3
"""
Test script to verify premium-to-spot pricing fixes in bid and listing modals
Tests both static and premium-to-spot listings
"""

import requests
import json
from urllib.parse import urljoin

BASE_URL = "http://127.0.0.1:5000"
session = requests.Session()

def print_section(title):
    """Print a formatted section header"""
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)

def print_result(test_name, passed, details=""):
    """Print test result"""
    status = "[PASS]" if passed else "[FAIL]"
    print(f"{status}: {test_name}")
    if details:
        print(f"   Details: {details}")

def login(username="rex", password="test"):
    """Log in to the application"""
    print_section(f"Logging in as {username}")
    resp = session.post(
        urljoin(BASE_URL, "/login"),
        data={"username": username, "password": password},
        allow_redirects=False
    )
    success = resp.status_code in [200, 302]
    print_result(f"Login as {username}", success, f"Status: {resp.status_code}")
    return success

def test_create_bid_modal_static():
    """Test 1: Create bid modal on static listing (Bucket 100000001)"""
    print_section("TEST 1: Create Bid Modal on Static Listing")

    bucket_id = 100000001
    url = urljoin(BASE_URL, f"/bids/form/{bucket_id}")

    try:
        resp = session.get(url, headers={"X-Requested-With": "XMLHttpRequest"})

        # Check response status
        if resp.status_code != 200:
            print_result("Load bid form", False, f"Status {resp.status_code}: {resp.text[:200]}")
            return False

        html = resp.text

        # Check that form loaded
        form_loaded = 'id="bid-form"' in html
        print_result("Form HTML contains bid-form", form_loaded)

        # Check that NO pricing notice is shown (static listing)
        no_pricing_notice = 'Dynamic Pricing - Premium to Spot' not in html
        print_result("No premium pricing notice (static listing)", no_pricing_notice)

        # Check that form has essential fields
        has_quantity = 'name="bid_quantity"' in html
        has_price = 'name="bid_price"' in html
        has_address = 'id="addr-line1"' in html

        print_result("Has quantity field", has_quantity)
        print_result("Has price field", has_price)
        print_result("Has address fields", has_address)

        overall = form_loaded and no_pricing_notice and has_quantity and has_price and has_address
        print_result("OVERALL TEST 1", overall)
        return overall

    except Exception as e:
        print_result("Create bid modal (static)", False, f"Exception: {str(e)}")
        return False

def test_create_bid_modal_premium():
    """Test 2: Create bid modal on premium-to-spot listing (Bucket 100000008)"""
    print_section("TEST 2: Create Bid Modal on Premium-to-Spot Listing")

    bucket_id = 100000008
    url = urljoin(BASE_URL, f"/bids/form/{bucket_id}")

    try:
        resp = session.get(url, headers={"X-Requested-With": "XMLHttpRequest"})

        # Check response status
        if resp.status_code != 200:
            print_result("Load bid form", False, f"Status {resp.status_code}: {resp.text[:200]}")
            return False

        html = resp.text

        # Check that form loaded
        form_loaded = 'id="bid-form"' in html
        print_result("Form HTML contains bid-form", form_loaded)

        # Check that pricing notice IS shown (premium-to-spot listing)
        has_pricing_notice = 'Dynamic Pricing - Premium to Spot' in html
        print_result("Shows premium pricing notice", has_pricing_notice)

        # Check pricing details are displayed
        has_premium = 'Premium:' in html and '+$' in html
        has_floor = 'Floor Price:' in html
        has_effective = 'Current Effective Price:' in html

        print_result("Shows premium amount", has_premium)
        print_result("Shows floor price", has_floor)
        print_result("Shows effective price", has_effective)

        # Check that form still has essential fields
        has_quantity = 'name="bid_quantity"' in html
        has_price = 'name="bid_price"' in html

        print_result("Has quantity field", has_quantity)
        print_result("Has price field", has_price)

        overall = (form_loaded and has_pricing_notice and has_premium and
                  has_floor and has_effective and has_quantity and has_price)
        print_result("OVERALL TEST 2", overall)
        return overall

    except Exception as e:
        print_result("Create bid modal (premium)", False, f"Exception: {str(e)}")
        return False

def test_edit_listing_modal_static():
    """Test 5: Edit listing modal for static listing (ID 10019)"""
    print_section("TEST 5: Edit Listing Modal - Static Listing")

    listing_id = 10019
    url = urljoin(BASE_URL, f"/listings/edit_listing/{listing_id}")

    try:
        resp = session.get(url, headers={"X-Requested-With": "XMLHttpRequest"})

        if resp.status_code != 200:
            print_result("Load edit listing modal", False, f"Status {resp.status_code}: {resp.text[:200]}")
            return False

        html = resp.text

        # Check modal loaded
        modal_loaded = f'id="editListingForm-{listing_id}"' in html
        print_result("Modal HTML loaded", modal_loaded)

        # Check pricing mode selector exists
        has_mode_selector = f'name="pricing_mode"' in html
        print_result("Has pricing mode selector", has_mode_selector)

        # Check static pricing fields exist
        has_static_price = 'name="price_per_coin"' in html
        print_result("Has static price field", has_static_price)

        # Check premium fields exist (should be hidden by default for static)
        has_premium_fields = 'name="spot_premium"' in html and 'name="floor_price"' in html
        print_result("Has premium pricing fields (hidden)", has_premium_fields)

        overall = modal_loaded and has_mode_selector and has_static_price and has_premium_fields
        print_result("OVERALL TEST 5", overall)
        return overall

    except Exception as e:
        print_result("Edit listing modal (static)", False, f"Exception: {str(e)}")
        return False

def test_edit_listing_modal_premium():
    """Test 6: Edit listing modal for premium-to-spot listing (ID 10067)"""
    print_section("TEST 6: Edit Listing Modal - Premium-to-Spot Listing")

    listing_id = 10067
    url = urljoin(BASE_URL, f"/listings/edit_listing/{listing_id}")

    try:
        resp = session.get(url, headers={"X-Requested-With": "XMLHttpRequest"})

        if resp.status_code != 200:
            print_result("Load edit listing modal", False, f"Status {resp.status_code}: {resp.text[:200]}")
            return False

        html = resp.text

        # Check modal loaded
        modal_loaded = f'id="editListingForm-{listing_id}"' in html
        print_result("Modal HTML loaded", modal_loaded)

        # Check pricing mode selector exists and is set to premium_to_spot
        has_mode_selector = f'name="pricing_mode"' in html
        is_premium_selected = 'value="premium_to_spot"' in html and 'selected' in html
        print_result("Has pricing mode selector", has_mode_selector)
        print_result("Premium-to-spot mode is selected", is_premium_selected)

        # Check premium fields exist and have values
        has_premium_field = 'name="spot_premium"' in html
        has_floor_field = 'name="floor_price"' in html
        has_pricing_metal = 'name="pricing_metal"' in html

        print_result("Has spot premium field", has_premium_field)
        print_result("Has floor price field", has_floor_field)
        print_result("Has pricing metal field", has_pricing_metal)

        # Check that values are populated (30.00 premium, 60.00 floor for listing 10067)
        has_premium_value = '30.00' in html or '30' in html
        has_floor_value = '60.00' in html or '60' in html

        print_result("Premium value populated", has_premium_value)
        print_result("Floor value populated", has_floor_value)

        overall = (modal_loaded and has_mode_selector and has_premium_field and
                  has_floor_field and has_pricing_metal)
        print_result("OVERALL TEST 6", overall)
        return overall

    except Exception as e:
        print_result("Edit listing modal (premium)", False, f"Exception: {str(e)}")
        return False

def test_edit_listing_save_static():
    """Test 7: Save static listing via edit modal"""
    print_section("TEST 7: Save Static Listing Changes")

    listing_id = 10019
    url = urljoin(BASE_URL, f"/listings/edit_listing/{listing_id}")

    try:
        # First, get current listing data
        get_resp = session.get(url, headers={"X-Requested-With": "XMLHttpRequest"})
        if get_resp.status_code != 200:
            print_result("Pre-fetch listing", False, f"Status {get_resp.status_code}")
            return False

        # Submit updated data with changed price
        form_data = {
            'metal': 'Gold',
            'product_line': 'Generic',
            'product_type': 'Bar',
            'weight': '1 oz',
            'purity': '.9999',
            'mint': 'Generic Mint',
            'year': '2025',
            'finish': 'Bullion',
            'grade': 'Ungraded',
            'graded': 'no',
            'quantity': '14',
            'pricing_mode': 'static',
            'price_per_coin': '1050.00',  # Changed from 1000.00
        }

        post_resp = session.post(
            url,
            data=form_data,
            headers={"X-Requested-With": "XMLHttpRequest"}
        )

        # Check response
        save_success = post_resp.status_code in [200, 204]
        print_result("Save request successful", save_success, f"Status: {post_resp.status_code}")

        if not save_success and post_resp.status_code >= 400:
            try:
                error_msg = post_resp.json().get('message', post_resp.text[:200])
                print_result("Error details", False, error_msg)
            except:
                print_result("Error details", False, post_resp.text[:200])
            return False

        # Verify the change persisted in database
        import sqlite3
        conn = sqlite3.connect('database.db')
        row = conn.execute(
            'SELECT price_per_coin, pricing_mode FROM listings WHERE id = ?',
            (listing_id,)
        ).fetchone()
        conn.close()

        if row:
            price, mode = row
            price_updated = abs(price - 1050.00) < 0.01
            mode_correct = mode == 'static' or mode is None

            print_result("Price updated to 1050.00", price_updated, f"Actual: {price}")
            print_result("Pricing mode is static", mode_correct, f"Actual: {mode}")

            overall = save_success and price_updated and mode_correct
        else:
            overall = False
            print_result("Verify in DB", False, "Listing not found")

        print_result("OVERALL TEST 7", overall)
        return overall

    except Exception as e:
        print_result("Save static listing", False, f"Exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_edit_listing_save_premium():
    """Test 8: Save premium-to-spot listing via edit modal"""
    print_section("TEST 8: Save Premium-to-Spot Listing Changes")

    listing_id = 10067
    url = urljoin(BASE_URL, f"/listings/edit_listing/{listing_id}")

    try:
        # First, get current listing data
        get_resp = session.get(url, headers={"X-Requested-With": "XMLHttpRequest"})
        if get_resp.status_code != 200:
            print_result("Pre-fetch listing", False, f"Status {get_resp.status_code}")
            return False

        # Submit updated data with changed premium/floor
        form_data = {
            'metal': 'Silver',
            'product_line': 'Libertad',
            'product_type': 'Coin',
            'weight': '1 oz',
            'purity': '.999',
            'mint': 'Mexican Mint',
            'year': '2024',
            'finish': 'Bullion',
            'grade': 'Ungraded',
            'graded': 'no',
            'quantity': '10',
            'pricing_mode': 'premium_to_spot',
            'pricing_metal': 'silver',
            'spot_premium': '35.00',  # Changed from 30.00
            'floor_price': '65.00',   # Changed from 60.00
        }

        post_resp = session.post(
            url,
            data=form_data,
            headers={"X-Requested-With": "XMLHttpRequest"}
        )

        # Check response
        save_success = post_resp.status_code in [200, 204]
        print_result("Save request successful", save_success, f"Status: {post_resp.status_code}")

        if not save_success and post_resp.status_code >= 400:
            try:
                error_msg = post_resp.json().get('message', post_resp.text[:200])
                print_result("Error details", False, error_msg)
            except:
                print_result("Error details", False, post_resp.text[:200])
            return False

        # Verify the change persisted in database
        import sqlite3
        conn = sqlite3.connect('database.db')
        row = conn.execute(
            'SELECT pricing_mode, spot_premium, floor_price, pricing_metal FROM listings WHERE id = ?',
            (listing_id,)
        ).fetchone()
        conn.close()

        if row:
            mode, premium, floor, metal = row
            mode_correct = mode == 'premium_to_spot'
            premium_updated = abs(premium - 35.00) < 0.01
            floor_updated = abs(floor - 65.00) < 0.01
            metal_correct = metal == 'silver'

            print_result("Pricing mode is premium_to_spot", mode_correct, f"Actual: {mode}")
            print_result("Premium updated to 35.00", premium_updated, f"Actual: {premium}")
            print_result("Floor updated to 65.00", floor_updated, f"Actual: {floor}")
            print_result("Pricing metal is silver", metal_correct, f"Actual: {metal}")

            overall = save_success and mode_correct and premium_updated and floor_updated and metal_correct
        else:
            overall = False
            print_result("Verify in DB", False, "Listing not found")

        print_result("OVERALL TEST 8", overall)
        return overall

    except Exception as e:
        print_result("Save premium listing", False, f"Exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def check_server_logs():
    """Check server for any errors"""
    print_section("Checking Server Logs for Errors")
    print("Please manually check the server terminal for:")
    print("  - No AttributeError exceptions")
    print("  - No 500 Internal Server Error responses")
    print("  - No other exceptions or tracebacks")
    print("\nIf you see any errors, the tests have revealed issues that need fixing.")

def main():
    """Run all tests"""
    print("\n" + "#"*80)
    print("#" + " "*78 + "#")
    print("#  PREMIUM-TO-SPOT PRICING FIXES - COMPREHENSIVE TEST SUITE" + " "*16 + "#")
    print("#" + " "*78 + "#")
    print("#"*80)

    # Login first
    if not login("rex", "test"):
        print("\n❌ Login failed - cannot continue tests")
        return

    # Track results
    results = {}

    # Run all tests
    results["Test 1: Create bid modal - Static"] = test_create_bid_modal_static()
    results["Test 2: Create bid modal - Premium"] = test_create_bid_modal_premium()
    results["Test 5: Edit listing modal - Static"] = test_edit_listing_modal_static()
    results["Test 6: Edit listing modal - Premium"] = test_edit_listing_modal_premium()
    results["Test 7: Save static listing"] = test_edit_listing_save_static()
    results["Test 8: Save premium listing"] = test_edit_listing_save_premium()

    # Check server logs
    check_server_logs()

    # Print summary
    print_section("TEST SUMMARY")
    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test, result in results.items():
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status}: {test}")

    print("\n" + "="*80)
    print(f"OVERALL: {passed}/{total} tests passed")
    if passed == total:
        print("SUCCESS: ALL TESTS PASSED! The fixes are working correctly.")
    else:
        print(f"WARNING: {total - passed} test(s) failed. Please review the output above.")
    print("="*80 + "\n")

    return passed == total

if __name__ == "__main__":
    main()
