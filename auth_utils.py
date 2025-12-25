"""
Authentication and authorization utilities
"""
from functools import wraps
from flask import session, redirect, url_for, flash, render_template
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
                'SELECT is_admin FROM users WHERE id = ?',
                (session['user_id'],)
            )
            user = cursor.fetchone()
            conn.close()

            if not user or not user['is_admin']:
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
