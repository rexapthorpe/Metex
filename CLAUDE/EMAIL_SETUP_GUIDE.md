# Email Notification Setup Guide

## Overview

Your application sends email notifications when:
- A buyer's bid is accepted (filled)
- A seller's listing is sold

Currently, email notifications are **not working** because Gmail credentials are not configured.

## Current Issue

**Error Message**:
```
[EMAIL ERROR] Failed to send email: (535, b'5.7.8 Username and Password not accepted')
```

**Cause**: No `.env` file exists with valid Gmail credentials. The system is using placeholder values from `config.py`.

## Solution: Set Up Gmail App Password

### Step 1: Create a Gmail App Password

**Important**: You CANNOT use your regular Gmail password. You must create an "App Password".

1. **Go to your Google Account**: https://myaccount.google.com/

2. **Enable 2-Factor Authentication** (required for App Passwords):
   - Go to Security → 2-Step Verification
   - Follow the prompts to enable 2FA

3. **Create an App Password**:
   - Go to Security → 2-Step Verification → App passwords
   - Or visit directly: https://myaccount.google.com/apppasswords
   - Select "Mail" and "Other (Custom name)"
   - Name it "Metals Exchange App"
   - Click "Generate"
   - **Copy the 16-character password** (you won't be able to see it again!)

### Step 2: Create `.env` File

1. **Copy the example file**:
   ```bash
   cd C:\Users\rex.apthorpe\OneDrive - West Point\Desktop\MetalsExchangeApp\Metex
   copy .env.example .env
   ```

2. **Edit `.env` file** and replace the placeholder values:
   ```env
   # Flask Session Security
   SECRET_KEY=your-random-secret-key-here

   # Email Configuration
   EMAIL_ADDRESS=your.actual.email@gmail.com
   EMAIL_PASSWORD=abcd efgh ijkl mnop
   ```

   Replace:
   - `your.actual.email@gmail.com` with your Gmail address
   - `abcd efgh ijkl mnop` with the 16-character App Password (spaces are optional)

3. **Generate a secret key**:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Copy the output and use it for `SECRET_KEY`

### Step 3: Restart Your Application

After saving the `.env` file:
1. Stop the Flask app (Ctrl+C)
2. Restart it: `python app.py`

The `.env` file will be automatically loaded by `python-dotenv`.

### Step 4: Test Email Notifications

Run the test to verify emails are working:
```bash
python test_email_notifications.py
```

## Alternative: Development Mode (Console Logging)

If you don't want to set up email during development, you can modify the email service to just log emails instead of sending them.

**File**: `services/email_service.py`

Add at the top of `send_html_email()`:
```python
def send_html_email(to_email, subject, template_name, **template_vars):
    """Send an HTML email using a Jinja2 template"""
    from_email = config.EMAIL_ADDRESS
    from_password = config.EMAIL_PASSWORD

    # DEVELOPMENT MODE: Just log emails instead of sending
    if config.EMAIL_ADDRESS == 'your.email@gmail.com':
        print(f"[EMAIL DEV MODE] Would send '{subject}' to {to_email}")
        print(f"[EMAIL DEV MODE] Template: {template_name}")
        print(f"[EMAIL DEV MODE] Variables: {template_vars}")
        return True  # Pretend it worked

    # ... rest of the function
```

## Troubleshooting

### Error: "Username and Password not accepted"
- ✓ Make sure you're using an **App Password**, not your regular Gmail password
- ✓ Check that 2-Factor Authentication is enabled on your Google Account
- ✓ Verify the email address in `.env` matches the Gmail account that created the App Password
- ✓ Make sure there are no extra spaces in the `.env` file

### Error: "No such file or directory: .env"
- ✓ Make sure `.env` is in the same directory as `app.py`
- ✓ The file should be named exactly `.env` (not `.env.txt`)
- ✓ Run `dir` in your project directory to verify the file exists

### Emails still not sending
- ✓ Restart the Flask application after creating `.env`
- ✓ Check that `python-dotenv` is installed: `pip install python-dotenv`
- ✓ Verify the `.env` file is being loaded: Add `print(config.EMAIL_ADDRESS)` to `app.py`

## Security Notes

⚠️ **IMPORTANT**: Never commit `.env` to git! Your `.gitignore` should include:
```
.env
*.env
```

The `.env` file contains sensitive credentials and should never be shared or committed to version control.

## Current Status

- ✅ In-app notifications: **Working** (stored in database, shown in notification bell)
- ❌ Email notifications: **Not working** (requires Gmail setup)

Once you complete the setup above, both notification types will work!
