# Email Notification Issue - Summary & Solution

## Problem

**Issue**: Users are not receiving email notifications when bids are accepted.

**Error**:
```
[EMAIL ERROR] Failed to send email: (535, b'5.7.8 Username and Password not accepted.
For more information, go to https://support.google.com/mail/?p=BadCredentials')
```

## Root Cause

The application is trying to send emails using **placeholder Gmail credentials** instead of real ones:

**Current Configuration** (from `config.py`):
```python
EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS', 'your.email@gmail.com')  # ← Placeholder!
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', 'your_app_password_here')  # ← Placeholder!
```

**Why This Happens**:
1. No `.env` file exists in the project
2. The application falls back to placeholder values from `config.py`
3. Gmail rejects these invalid credentials

## Current System Status

✅ **In-App Notifications**: WORKING
- Stored in database
- Displayed in notification bell icon
- Users can see them in the interface

❌ **Email Notifications**: NOT WORKING
- Gmail credentials not configured
- Emails fail to send
- Error is caught and logged (doesn't break the app)

## Solution: Configure Gmail Credentials

### Quick Setup (5 minutes)

1. **Get a Gmail App Password**:
   - Go to https://myaccount.google.com/apppasswords
   - Enable 2FA if not already enabled
   - Create App Password for "Mail" → "Other (Custom name)"
   - Name it "Metals Exchange App"
   - Copy the 16-character password

2. **Create `.env` file**:
   ```bash
   cd C:\Users\rex.apthorpe\OneDrive - West Point\Desktop\MetalsExchangeApp\Metex
   copy .env.example .env
   ```

3. **Edit `.env` with your credentials**:
   ```env
   EMAIL_ADDRESS=your.actual.email@gmail.com
   EMAIL_PASSWORD=abcd efgh ijkl mnop
   ```
   (Replace with your real email and the App Password you just created)

4. **Restart the application**:
   - Stop Flask (Ctrl+C)
   - Start it again: `python app.py`

### Verify It Works

Run the test:
```bash
python test_email_setup.py
```

## How Email Notifications Work

### Bid Filled Email Flow:

1. **Seller accepts bid** (clicks "Yes, accept" in confirmation modal)
2. **Order is created** in database (status: "Pending Shipment")
3. **In-app notification created** for buyer
4. **Email service called** (`services/email_service.py`)
   - Connects to Gmail SMTP (smtp.gmail.com:465)
   - Uses credentials from `.env` file
   - Sends HTML email using template (`templates/emails/bid_filled.html`)
5. **Buyer receives email** with:
   - Subject: "🎉 Your Bid Has Been Filled!"
   - Details: item, quantity, price, total
   - Link to Orders page

### Listing Sold Email Flow:

Same process but:
- Triggered when buyer purchases from listing
- Email sent to **seller** (not buyer)
- Subject: "💰 Your Listing Has Been Sold!"
- Link to Sold tab

## Files Involved

### Configuration:
- `config.py` - Loads EMAIL_ADDRESS and EMAIL_PASSWORD from environment
- `.env` - Contains actual credentials (YOU NEED TO CREATE THIS)
- `.env.example` - Template showing required format

### Email Services:
- `services/email_service.py` - Handles SMTP connection and sending
- `services/notification_service.py` - Creates both in-app and email notifications
- `templates/emails/bid_filled.html` - Email template for bid filled
- `templates/emails/listing_sold.html` - Email template for listing sold

### Routes That Send Notifications:
- `routes/bid_routes.py` → `accept_bid()` - Sends bid filled notification
- `routes/buy_routes.py` → checkout routes - Sends listing sold notification

## Why In-App Notifications Work But Email Doesn't

**In-App Notifications**:
- Only require database access
- No external services needed
- Always work regardless of email configuration

**Email Notifications**:
- Require Gmail SMTP access
- Need valid credentials
- Wrapped in try-except so failure doesn't break the app
- Fail silently if credentials are invalid

## Security Note

⚠️ **NEVER commit `.env` to git!**

The `.env` file contains your Gmail App Password and should be kept secret. Make sure your `.gitignore` includes:
```
.env
*.env
```

## Alternative: Development Mode (No Email)

If you don't want to set up email for development, you can disable email sending:

**Option 1**: Modify `services/email_service.py`:
```python
def send_html_email(to_email, subject, template_name, **template_vars):
    # Skip email in development
    if config.EMAIL_ADDRESS == 'your.email@gmail.com':
        print(f"[DEV MODE] Would send email: {subject} to {to_email}")
        return True  # Pretend it worked

    # ... rest of function
```

**Option 2**: Set fake but valid-looking credentials in `.env`:
```env
EMAIL_ADDRESS=dev@localhost.com
EMAIL_PASSWORD=dev_password
```
(Emails will still fail but won't show "BadCredentials" error)

## Complete Setup Instructions

See `EMAIL_SETUP_GUIDE.md` for step-by-step instructions with screenshots and troubleshooting tips.

## Summary

- **Problem**: No `.env` file with Gmail credentials
- **Impact**: Email notifications don't send (in-app notifications still work)
- **Solution**: Create `.env` file with Gmail App Password
- **Time**: 5 minutes to set up
- **Files Created**: `.env.example`, `EMAIL_SETUP_GUIDE.md`, `test_email_setup.py`
