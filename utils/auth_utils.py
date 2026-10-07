"""
Authentication and authorization utilities
"""
from functools import wraps
from flask import session, redirect, url_for, flash, render_template, request, current_app, jsonify
from database import get_db_connection
import sqlite3
import sys


def admin_required(f):
    """
    Decorator to require admin access for a route.

    Checks:
    1. User must be logged in (session['user_id'] exists)
    2. User must have is_admin=1 in database

    If not logged in: redirects to login page
    If logged in but not admin: returns 403 forbidden page
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is logged in
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))

        # Check if user is admin
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM users WHERE id = ?',
                (session['user_id'],)
            )
            user = cursor.fetchone()
            conn.close()

            account=dict(user) if user else {}
            if not account.get('is_admin') or account.get('is_banned') or account.get('is_frozen'):
                # User is logged in but not an admin
                return render_template('403.html'), 403
        except sqlite3.OperationalError as e:
            if 'no such column: is_admin' in str(e):
                # Column doesn't exist yet - need to run migration
                print('\n⚠️  WARNING: is_admin column missing from users table', file=sys.stderr)
                print('⚠️  Please run: python run_migration_015.py', file=sys.stderr)
                print('⚠️  Access denied until migration is complete.\n', file=sys.stderr)
                return render_template('403.html'), 403
            else:
                raise

        import os,time
        enforce=current_app.config.get('REQUIRE_ADMIN_REAUTH',os.getenv('FLASK_ENV')=='production' and not current_app.testing)
        if enforce and request.method not in ('GET','HEAD','OPTIONS') and request.endpoint!='admin.reauthenticate':
            authenticated=session.get('authenticated_at',0)
            if not isinstance(authenticated,(int,float)) or not 0<=time.time()-authenticated<=1800:
                return jsonify(error='Please verify your password before this administrator action',error_code='ADMIN_REAUTH_REQUIRED',reauthentication_url=url_for('admin.reauthenticate')),403
        return f(*args, **kwargs)

    return decorated_function


def is_user_admin(user_id):
    """
    Check if a user is an admin.

    Args:
        user_id: The user ID to check

    Returns:
        bool: True if user is admin, False otherwise (or False if column doesn't exist yet)
    """
    if not user_id:
        return False

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT is_admin FROM users WHERE id = ?',
            (user_id,)
        )
        user = cursor.fetchone()
        conn.close()

        return bool(user and user['is_admin'])
    except sqlite3.OperationalError as e:
        if 'no such column: is_admin' in str(e):
            # Column doesn't exist yet - migration not run
            # Return False silently (don't spam logs on every page load)
            return False
        else:
            # Some other error - re-raise
            raise


def is_user_frozen(user_id):
    """
    Check if a user account is frozen.

    Args:
        user_id: The user ID to check

    Returns:
        bool: True if user is frozen, False otherwise
    """
    if not user_id:
        return False

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT is_frozen FROM users WHERE id = ?',
            (user_id,)
        )
        user = cursor.fetchone()
        conn.close()

        return bool(user and user['is_frozen'])
    except sqlite3.OperationalError as e:
        if 'no such column: is_frozen' in str(e):
            return False
        else:
            raise


def frozen_check(f):
    """
    Decorator to check if user account is frozen before allowing action.

    If frozen, returns a JSON error response for AJAX requests,
    or redirects with a flash message for regular requests.
    """
    from flask import request, jsonify

    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')

        if user_id and is_user_frozen(user_id):
            # Check if this is an AJAX/API request
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'error': 'Your account is frozen. Please contact support for assistance.',
                    'frozen': True
                }), 403

            # Regular request - redirect with flash
            flash('Your account is frozen. You cannot perform this action until your account is unfrozen.', 'error')
            return redirect(url_for('account.account'))

        return f(*args, **kwargs)

    return decorated_function
