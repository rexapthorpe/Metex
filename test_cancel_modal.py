"""
Test if the cancel modal route is working and returning the correct HTML
"""

import requests

def test_cancel_modal_route():
    """Test the cancel listing confirmation modal route"""

    print("=" * 70)
    print("TESTING CANCEL MODAL ROUTE")
    print("=" * 70)

    # Use a listing ID that exists (from our previous tests we know listing 76 exists)
    listing_id = 76

    url = f"http://127.0.0.1:5000/listings/cancel_listing_confirmation_modal/{listing_id}"

    print(f"\n1. Fetching modal HTML from: {url}")

    try:
        response = requests.get(url, timeout=5)

        print(f"\n2. Response status: {response.status_code}")

        if response.status_code == 200:
            print("   [OK] Route returned successfully")

            html = response.text
            print(f"\n3. Response length: {len(html)} characters")

            # Check for key elements that should be in the modal
            checks = {
                'cancelModalWrapper': 'cancelModalWrapper-' in html,
                'confirmation-modal-content': 'confirmation-modal-content' in html,
                'Cancel Listing?': 'Cancel Listing?' in html,
                'confirmCancel function': f'confirmCancel({listing_id})' in html,
                'closeCancelModal function': f'closeCancelModal({listing_id})' in html,
            }

            print("\n4. Checking modal HTML content:")
            all_pass = True
            for check_name, result in checks.items():
                status = "[OK]" if result else "[MISSING]"
                print(f"   {status} {check_name}")
                if not result:
                    all_pass = False

            if all_pass:
                print("\n" + "=" * 70)
                print("SUCCESS: Modal HTML is correctly structured")
                print("=" * 70)
            else:
                print("\n" + "=" * 70)
                print("ISSUE: Some modal elements are missing")
                print("Modal HTML:")
                print(html)
                print("=" * 70)

        elif response.status_code == 302:
            print("   [REDIRECT] Route redirected (probably to login)")
            print(f"   Location: {response.headers.get('Location')}")
        else:
            print(f"   [ERROR] Route returned status {response.status_code}")
            print(f"   Response: {response.text[:200]}")

    except requests.exceptions.ConnectionError:
        print("   [ERROR] Cannot connect to Flask server")
        print("   Is the server running at http://127.0.0.1:5000?")
    except Exception as e:
        print(f"   [ERROR] {e}")

if __name__ == '__main__':
    test_cancel_modal_route()
