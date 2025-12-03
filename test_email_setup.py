"""
TEST EMAIL SETUP
Verifies that email notifications are configured correctly
"""
import config

print("=" * 80)
print("EMAIL CONFIGURATION TEST")
print("=" * 80)

print("\n[CHECK 1] Checking email configuration...")
print(f"EMAIL_ADDRESS: {config.EMAIL_ADDRESS}")
print(f"EMAIL_PASSWORD: {'*' * len(config.EMAIL_PASSWORD) if config.EMAIL_PASSWORD else 'NOT SET'}")

# Check if using placeholder values
if config.EMAIL_ADDRESS == 'your.email@gmail.com':
    print("\n❌ [FAIL] Email is not configured!")
    print("   You are using the placeholder email address.")
    print("\n   To fix this:")
    print("   1. Copy .env.example to .env")
    print("   2. Follow EMAIL_SETUP_GUIDE.md to get a Gmail App Password")
    print("   3. Edit .env and add your real Gmail credentials")
    print("   4. Restart the application")
    print("\n   See EMAIL_SETUP_GUIDE.md for detailed instructions.")
elif '@' not in config.EMAIL_ADDRESS:
    print("\n❌ [FAIL] Invalid email address format!")
    print(f"   EMAIL_ADDRESS = '{config.EMAIL_ADDRESS}'")
elif config.EMAIL_PASSWORD == 'your_app_password_here':
    print("\n❌ [FAIL] Email password is not configured!")
    print("   You are using the placeholder password.")
    print("\n   To fix this:")
    print("   1. Follow EMAIL_SETUP_GUIDE.md to create a Gmail App Password")
    print("   2. Edit .env and replace EMAIL_PASSWORD with your App Password")
    print("   3. Restart the application")
else:
    print("\n✓ [OK] Email configuration looks valid!")
    print(f"   Using email: {config.EMAIL_ADDRESS}")
    print(f"   Password is set (length: {len(config.EMAIL_PASSWORD)} characters)")

    # Try to send a test email
    print("\n[CHECK 2] Testing email delivery...")
    print("Would you like to send a test email? (y/n): ")

    try:
        response = input().strip().lower()
        if response == 'y':
            from services.email_service import send_html_email

            test_email = config.EMAIL_ADDRESS  # Send to yourself
            print(f"\nSending test email to {test_email}...")

            # Create a simple test template inline
            from jinja2 import Template
            test_template = Template("""
            <html>
            <body>
                <h1>Test Email</h1>
                <p>Hello {{ username }},</p>
                <p>This is a test email from your Metals Exchange App.</p>
                <p>If you're reading this, email notifications are working correctly!</p>
            </body>
            </html>
            """)

            # We'll need to modify send_html_email to accept template content
            # For now, just try the basic function
            try:
                from services.notification_service import notify_bid_filled
                # Send a mock bid filled notification to yourself
                result = notify_bid_filled(
                    buyer_id=1,  # Assuming user 1 exists
                    order_id=999,
                    bid_id=999,
                    item_description="Test Item (Email Test)",
                    quantity_filled=1,
                    price_per_unit=100.00,
                    total_amount=100.00,
                    is_partial=False,
                    remaining_quantity=0
                )

                if result:
                    print("\n✓ [SUCCESS] Test email sent successfully!")
                    print(f"   Check your inbox at {test_email}")
                else:
                    print("\n❌ [FAIL] Failed to send test email")
                    print("   Check the error message above for details")

            except Exception as e:
                print(f"\n❌ [ERROR] Exception while sending test email: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("\nSkipping test email send.")

    except KeyboardInterrupt:
        print("\n\nTest cancelled.")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
