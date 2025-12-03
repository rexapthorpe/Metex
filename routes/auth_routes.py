# routes/auth_routes.py

from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db_connection
import sqlite3
import smtplib
import hashlib
import config

auth_bp = Blueprint('auth', __name__)

# --- Google Login Routes ---

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']

        password_hash = generate_password_hash(password)
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
            conn.execute(
                'INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)',
                (username, password_hash, email)
            )
            conn.commit()

            user = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
            session['user_id'] = user['id']

            guest_cart = session.pop('guest_cart', [])
            for item in guest_cart:
                existing = conn.execute(
                    'SELECT quantity FROM cart WHERE user_id = ? AND listing_id = ?',
                    (user['id'], item['listing_id'])
                ).fetchone()

                if existing:
                    new_qty = existing['quantity'] + item['quantity']
                    conn.execute(
                        'UPDATE cart SET quantity = ? WHERE user_id = ? AND listing_id = ?',
                        (new_qty, user['id'], item['listing_id'])
                    )
                else:
                    conn.execute(
                        'INSERT INTO cart (user_id, listing_id, quantity) VALUES (?, ?, ?)',
                        (user['id'], item['listing_id'], item['quantity'])
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
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT id, password_hash FROM users WHERE username = ?', (username,)).fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']

            guest_cart = session.pop('guest_cart', [])
            for item in guest_cart:
                existing = conn.execute(
                    'SELECT quantity FROM cart WHERE user_id = ? AND listing_id = ?',
                    (user['id'], item['listing_id'])
                ).fetchone()

                if existing:
                    new_qty = existing['quantity'] + item['quantity']
                    conn.execute(
                        'UPDATE cart SET quantity = ? WHERE user_id = ? AND listing_id = ?',
                        (new_qty, user['id'], item['listing_id'])
                    )
                else:
                    conn.execute(
                        'INSERT INTO cart (user_id, listing_id, quantity) VALUES (?, ?, ?)',
                        (user['id'], item['listing_id'], item['quantity'])
                    )

            conn.commit()
            conn.close()

            # Check if request is AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.accept_json:
                return jsonify({'success': True, 'redirect': url_for('buy.buy')})
            return redirect(url_for('buy.buy'))
        else:
            conn.close()
            # Check if request is AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.accept_json:
                return jsonify({'success': False, 'message': 'Invalid username or password'})
            return "Invalid username or password."

    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('buy.buy'))

# --- Password Reset Routes ---

@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']

        conn = get_db_connection()
        user = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()

        if user:
            reset_token = hashlib.sha256((str(user['id']) + 'your_secret_key_here').encode()).hexdigest()
            reset_link = f'http://127.0.0.1:5000/reset_password/{user["id"]}/{reset_token}'
            send_reset_email(email, reset_link)
            return "Password reset link has been sent to your email."
        else:
            return "No account with that email was found."

    return render_template('forgot_password.html')

@auth_bp.route('/reset_password/<int:user_id>/<token>', methods=['GET', 'POST'])
def reset_password(user_id, token):
    expected_token = hashlib.sha256((str(user_id) + 'your_secret_key_here').encode()).hexdigest()

    if token != expected_token:
        return "Invalid or expired reset link."

    if request.method == 'POST':
        new_password = request.form['password']
        new_password_hash = generate_password_hash(new_password)

        conn = get_db_connection()
        conn.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_password_hash, user_id))
        conn.commit()
        conn.close()

        return redirect(url_for('auth.login'))

    return render_template('reset_password.html')

# --- Helper to Send Email ---

def send_reset_email(to_email, reset_link):
    from_email = config.EMAIL_ADDRESS
    from_password = config.EMAIL_PASSWORD

    subject = 'Password Reset Request'
    body = f'Click this link to reset your password:\n\n{reset_link}'

    email_text = f"""
From: {from_email}
To: {to_email}
Subject: {subject}

{body}
"""

    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(from_email, from_password)
        server.sendmail(from_email, to_email, email_text)
        server.close()
        print(f"✅ Password reset email sent to {to_email}")
    except Exception as e:
        print(f"❌ Failed to send password reset email to {to_email}: {e}")
