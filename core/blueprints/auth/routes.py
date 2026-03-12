"""
Auth Routes

Authentication routes: login, logout, register, password reset.

Security features:
- Secure password hashing with pbkdf2:sha256
- Session regeneration on login (prevents session fixation)
- One-time, time-limited password reset tokens
- Audit logging for security events
- Rate limiting on authentication endpoints
"""

from flask import render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db_connection
from datetime import datetime, timedelta
import sqlite3
import smtplib
import os
import config

from . import auth_bp

# Import security utilities
from utils.security import (
    generate_password_reset_token,
    verify_reset_token,
    hash_token,
    set_session_user,
    invalidate_session,
    sanitize_string
)

# Import audit logging (optional - graceful fallback if not available)
try:
    from services.audit_service import (
        log_login_success,
        log_login_failed,
        log_logout,
        log_registration,
        log_password_reset_request,
        log_password_reset_success,
        log_password_reset_failed
    )
    AUDIT_ENABLED = True
except ImportError:
    AUDIT_ENABLED = False

# Import rate limiting (optional - graceful fallback if not available)
try:
    from utils.rate_limit import (
        limit_login,
        limit_registration,
        limit_password_reset
    )
    RATE_LIMIT_ENABLED = True
except ImportError:
    RATE_LIMIT_ENABLED = False
    # Define no-op decorators if rate limiting not available
    def limit_login(f): return f
    def limit_registration(f): return f
    def limit_password_reset(f): return f


# Password reset token expiry (in hours)
PASSWORD_RESET_EXPIRY_HOURS = int(os.getenv('PASSWORD_RESET_TOKEN_EXPIRY_HOURS', '1'))


@auth_bp.route('/register', methods=['GET', 'POST'])
@limit_registration
def register():
    if request.method == 'POST':
        # Sanitize inputs
        username = sanitize_string(request.form.get('username', ''), max_length=50)
        password = request.form.get('password', '')
        email = sanitize_string(request.form.get('email', ''), max_length=255).lower()

        # Basic validation
        if not username or len(username) < 3:
            error_msg = 'Username must be at least 3 characters.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': error_msg, 'field': 'username'})
            return error_msg

        if not password or len(password) < 8:
            error_msg = 'Password must be at least 8 characters.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': error_msg, 'field': 'password'})
            return error_msg

        if not email or '@' not in email:
            error_msg = 'Please enter a valid email address.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': error_msg, 'field': 'email'})
            return error_msg

        password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        conn = get_db_connection()

        # Check if username already exists
        existing_username = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if existing_username:
            conn.close()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': 'This username is already taken. Please choose a different username.', 'field': 'username'})
            return "Username already exists."

        # Check if email already exists
        existing_email = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        if existing_email:
            conn.close()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': 'This email is already associated with an account. Please sign in or use a different email.', 'field': 'email'})
            return "Email already exists."

        try:
            # SECURITY FIX: Only store password hash, not duplicate in 'password' column
            # The 'password' column stores the hash for backward compatibility
            conn.execute(
                'INSERT INTO users (username, password, password_hash, email) VALUES (?, ?, ?, ?)',
                (username, password_hash, password_hash, email)
            )
            conn.commit()

            user = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
            user_id = user['id']

            # SECURITY: Use secure session setup (regenerates session ID)
            set_session_user(user_id, username)

            # Log registration for audit
            if AUDIT_ENABLED:
                log_registration(user_id, username, email)

            # Merge guest cart — preserve grading preference per line item
            guest_cart = session.pop('guest_cart', [])
            for item in guest_cart:
                tpg = int(item.get('third_party_grading_requested', 0) or 0)
                grading_pref = 'ANY' if tpg else 'NONE'
                existing = conn.execute(
                    'SELECT id, quantity FROM cart WHERE user_id = ? AND listing_id = ? AND third_party_grading_requested = ?',
                    (user_id, item['listing_id'], tpg)
                ).fetchone()

                if existing:
                    new_qty = existing['quantity'] + item['quantity']
                    conn.execute(
                        'UPDATE cart SET quantity = ? WHERE id = ?',
                        (new_qty, existing['id'])
                    )
                else:
                    conn.execute(
                        'INSERT INTO cart (user_id, listing_id, quantity, third_party_grading_requested, grading_preference) VALUES (?, ?, ?, ?, ?)',
                        (user_id, item['listing_id'], item['quantity'], tpg, grading_pref)
                    )

            conn.commit()
            conn.close()

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': True, 'redirect': url_for('buy.buy')})
            return redirect(url_for('buy.buy'))

        except sqlite3.IntegrityError:
            conn.close()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': 'Username or email already exists.'})
            return "Username or email already exists."

    return render_template('register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
@limit_login
def login():
    if request.method == 'POST':
        username = sanitize_string(request.form.get('username', ''), max_length=50)
        password = request.form.get('password', '')

        conn = get_db_connection()
        user = conn.execute(
            'SELECT id, username, password_hash, is_banned, is_frozen FROM users WHERE username = ?',
            (username,)
        ).fetchone()

        if user and check_password_hash(user['password_hash'], password):
            # Check if user is banned
            if user['is_banned']:
                conn.close()
                if AUDIT_ENABLED:
                    log_login_failed(username, 'account_banned')
                error_msg = 'Your account has been suspended. Please contact support.'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'message': error_msg})
                return error_msg

            user_id = user['id']

            # SECURITY: Clear existing session and create new one (prevents session fixation)
            guest_cart = session.get('guest_cart', [])  # Save before clearing
            set_session_user(user_id, user['username'])

            # Log successful login
            if AUDIT_ENABLED:
                log_login_success(user_id, username)

            # Merge guest cart after session setup — preserve grading preference per line item
            for item in guest_cart:
                tpg = int(item.get('third_party_grading_requested', 0) or 0)
                grading_pref = 'ANY' if tpg else 'NONE'
                existing = conn.execute(
                    'SELECT id, quantity FROM cart WHERE user_id = ? AND listing_id = ? AND third_party_grading_requested = ?',
                    (user_id, item['listing_id'], tpg)
                ).fetchone()

                if existing:
                    new_qty = existing['quantity'] + item['quantity']
                    conn.execute(
                        'UPDATE cart SET quantity = ? WHERE id = ?',
                        (new_qty, existing['id'])
                    )
                else:
                    conn.execute(
                        'INSERT INTO cart (user_id, listing_id, quantity, third_party_grading_requested, grading_preference) VALUES (?, ?, ?, ?, ?)',
                        (user_id, item['listing_id'], item['quantity'], tpg, grading_pref)
                    )

            conn.commit()
            conn.close()

            # Check if request is AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.accept_json:
                return jsonify({'success': True, 'redirect': url_for('buy.buy')})
            return redirect(url_for('buy.buy'))
        else:
            conn.close()
            # Log failed login attempt
            if AUDIT_ENABLED:
                log_login_failed(username, 'invalid_credentials')

            # Check if request is AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.accept_json:
                return jsonify({'success': False, 'message': 'Invalid username or password'})
            return "Invalid username or password."

    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    user_id = session.get('user_id')

    # Log logout before clearing session
    if AUDIT_ENABLED and user_id:
        log_logout(user_id)

    # SECURITY: Properly invalidate session
    invalidate_session()

    return redirect(url_for('buy.buy'))


# --- Password Reset Routes ---

@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
@limit_password_reset
def forgot_password():
    """
    Handle password reset requests.

    SECURITY: Uses secure, one-time-use, time-limited tokens stored hashed in DB.
    """
    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        username = sanitize_string(request.form.get('username', ''), max_length=50)
        email = sanitize_string(request.form.get('email', ''), max_length=255).lower()

        if not username:
            if is_ajax:
                return jsonify({'success': False, 'error': 'Please enter your username.'})
            return "Please enter your username."

        if not email:
            if is_ajax:
                return jsonify({'success': False, 'error': 'Please enter an email address.'})
            return "Please enter an email address."

        conn = get_db_connection()
        # Verify both username AND email match the same account
        user = conn.execute(
            'SELECT id, email FROM users WHERE username = ? AND email = ?',
            (username, email)
        ).fetchone()

        user_found = user is not None

        # Log the request for audit (before revealing if user exists)
        if AUDIT_ENABLED:
            log_password_reset_request(email, user_found)

        if user:
            try:
                # SECURITY FIX: Generate secure random token
                plaintext_token, token_hash = generate_password_reset_token()

                # Set expiration time
                expires_at = datetime.utcnow() + timedelta(hours=PASSWORD_RESET_EXPIRY_HOURS)

                # Delete any existing unused tokens for this user
                conn.execute(
                    'DELETE FROM password_reset_tokens WHERE user_id = ? AND used_at IS NULL',
                    (user['id'],)
                )

                # Store the hashed token (never store plaintext)
                conn.execute('''
                    INSERT INTO password_reset_tokens (user_id, token_hash, expires_at, ip_address)
                    VALUES (?, ?, ?, ?)
                ''', (user['id'], token_hash, expires_at.isoformat(), request.remote_addr))
                conn.commit()

                # Build reset link with plaintext token (user receives this)
                reset_link = f'{request.scheme}://{request.host}/reset_password/{plaintext_token}'
                send_reset_email(email, reset_link)
                conn.close()

                if is_ajax:
                    return jsonify({'success': True, 'message': 'Password reset link has been sent to your email.'})
                return "Password reset link has been sent to your email."

            except Exception as e:
                conn.close()
                print(f"Password reset failed: {e}")
                if is_ajax:
                    return jsonify({'success': False, 'error': 'Failed to send email. Please try again later.'})
                return "Failed to send email. Please try again later."
        else:
            conn.close()
            # SECURITY: Don't reveal whether user exists (time-based enumeration protection)
            # Return same message whether user exists or not
            if is_ajax:
                return jsonify({'success': False, 'error': 'The username and email do not match any account.'})
            return "The username and email do not match any account."

    return render_template('forgot_password.html')


@auth_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """
    Handle password reset with secure token.

    SECURITY:
    - Token is looked up by hash (never stored in plaintext)
    - Token must not be expired
    - Token can only be used once
    """
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    # Validate token format (should be hex string)
    if not token or len(token) != 64:
        if is_ajax:
            return jsonify({'success': False, 'error': 'Invalid reset link.'})
        return redirect(url_for('auth.login'))

    # Hash the provided token to look it up
    token_hash = hash_token(token)

    conn = get_db_connection()

    # Find the token record
    token_record = conn.execute('''
        SELECT id, user_id, expires_at, used_at
        FROM password_reset_tokens
        WHERE token_hash = ?
    ''', (token_hash,)).fetchone()

    if not token_record:
        conn.close()
        if AUDIT_ENABLED:
            log_password_reset_failed(None, 'invalid_token')
        if is_ajax:
            return jsonify({'success': False, 'error': 'Invalid or expired reset link.'})
        return redirect(url_for('auth.login'))

    # Check if token has been used
    if token_record['used_at']:
        conn.close()
        if AUDIT_ENABLED:
            log_password_reset_failed(token_record['user_id'], 'token_already_used')
        if is_ajax:
            return jsonify({'success': False, 'error': 'This reset link has already been used.'})
        return redirect(url_for('auth.login'))

    # Check if token has expired
    expires_at = datetime.fromisoformat(token_record['expires_at'])
    if datetime.utcnow() > expires_at:
        conn.close()
        if AUDIT_ENABLED:
            log_password_reset_failed(token_record['user_id'], 'token_expired')
        if is_ajax:
            return jsonify({'success': False, 'error': 'This reset link has expired. Please request a new one.'})
        return redirect(url_for('auth.login'))

    user_id = token_record['user_id']

    if request.method == 'POST':
        new_password = request.form.get('password', '')

        if not new_password:
            conn.close()
            if is_ajax:
                return jsonify({'success': False, 'error': 'Please enter a password.'})
            return "Please enter a password."

        if len(new_password) < 8:
            conn.close()
            if is_ajax:
                return jsonify({'success': False, 'error': 'Password must be at least 8 characters.'})
            return "Password must be at least 8 characters."

        # Hash the new password
        new_password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')

        # Update password
        conn.execute(
            'UPDATE users SET password = ?, password_hash = ? WHERE id = ?',
            (new_password_hash, new_password_hash, user_id)
        )

        # Mark token as used (one-time use)
        conn.execute(
            'UPDATE password_reset_tokens SET used_at = ? WHERE id = ?',
            (datetime.utcnow().isoformat(), token_record['id'])
        )

        conn.commit()
        conn.close()

        # Log successful reset
        if AUDIT_ENABLED:
            log_password_reset_success(user_id)

        if is_ajax:
            return jsonify({'success': True, 'message': 'Password reset successfully!'})
        return redirect(url_for('auth.login'))

    conn.close()
    return render_template('reset_password.html')


# --- Helper to Send Email ---

def send_reset_email(to_email, reset_link):
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    from_email = config.EMAIL_ADDRESS
    from_password = config.EMAIL_PASSWORD

    # Create professional HTML email
    subject = 'Reset Your Metex Password'

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f5f5f5;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f5f5f5; padding: 40px 20px;">
            <tr>
                <td align="center">
                    <table width="100%" style="max-width: 500px; background-color: #ffffff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                        <!-- Header -->
                        <tr>
                            <td style="padding: 32px 32px 24px; text-align: center; border-bottom: 1px solid #e5e7eb;">
                                <h1 style="margin: 0; font-size: 24px; font-weight: 700; color: #111827;">Metex</h1>
                            </td>
                        </tr>
                        <!-- Content -->
                        <tr>
                            <td style="padding: 32px;">
                                <h2 style="margin: 0 0 16px; font-size: 20px; font-weight: 600; color: #111827;">Reset Your Password</h2>
                                <p style="margin: 0 0 24px; font-size: 15px; line-height: 1.6; color: #6b7280;">
                                    We received a request to reset your password. Click the button below to create a new password. This link will expire in 24 hours.
                                </p>
                                <a href="{reset_link}" style="display: inline-block; padding: 14px 32px; background-color: #3da6ff; color: #ffffff; text-decoration: none; font-size: 15px; font-weight: 600; border-radius: 8px;">
                                    Reset Password
                                </a>
                                <p style="margin: 24px 0 0; font-size: 13px; line-height: 1.6; color: #9ca3af;">
                                    If you didn't request this, you can safely ignore this email. Your password will remain unchanged.
                                </p>
                            </td>
                        </tr>
                        <!-- Footer -->
                        <tr>
                            <td style="padding: 24px 32px; background-color: #f9fafb; border-top: 1px solid #e5e7eb; border-radius: 0 0 12px 12px;">
                                <p style="margin: 0; font-size: 12px; color: #9ca3af; text-align: center;">
                                    This is an automated message from Metex. Please do not reply to this email.
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    plain_body = f"""Reset Your Metex Password

We received a request to reset your password. Click the link below to create a new password:

{reset_link}

This link will expire in 24 hours.

If you didn't request this, you can safely ignore this email. Your password will remain unchanged.

- The Metex Team
"""

    # Create MIME message
    msg = MIMEMultipart('alternative')
    msg['From'] = f'Metex <{from_email}>'
    msg['To'] = to_email
    msg['Subject'] = subject

    # Attach both plain text and HTML versions
    msg.attach(MIMEText(plain_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))

    try:
        print(f"Attempting to send password reset email to {to_email}")
        print(f"Using sender: {from_email}")
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(from_email, from_password)
        server.sendmail(from_email, to_email, msg.as_string())
        server.close()
        print(f"Password reset email sent to {to_email}")
        return True
    except Exception as e:
        print(f"Failed to send password reset email to {to_email}: {e}")
        raise e  # Re-raise so the route can handle it
