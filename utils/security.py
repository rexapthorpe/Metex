"""
Security utilities for Metex application.

Provides:
- Secure token generation for password resets
- Authorization helpers to prevent IDOR attacks
- Input validation utilities
- Session management helpers
"""
import secrets
import hashlib
import hmac
import time
from functools import wraps
from typing import Optional, Tuple, Any
from flask import session, request, jsonify, abort, g
from database import get_db_connection


# ============================================================================
# Token Generation (Password Reset, Email Verification)
# ============================================================================

def generate_secure_token(length: int = 32) -> str:
    """
    Generate a cryptographically secure random token.

    Args:
        length: Number of bytes (token will be 2x this in hex chars)

    Returns:
        Hex-encoded random token
    """
    return secrets.token_hex(length)


def hash_token(token: str) -> str:
    """
    Hash a token for secure storage.

    We store hashed tokens in the database so that even if the DB is
    compromised, the actual tokens cannot be recovered.

    Args:
        token: The plaintext token

    Returns:
        SHA-256 hash of the token
    """
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def generate_password_reset_token() -> Tuple[str, str]:
    """
    Generate a password reset token pair.

    Returns:
        Tuple of (plaintext_token, hashed_token)
        - Send plaintext_token to user via email
        - Store hashed_token in database
    """
    token = generate_secure_token(32)
    token_hash = hash_token(token)
    return token, token_hash


def verify_reset_token(provided_token: str, stored_hash: str) -> bool:
    """
    Verify a password reset token.

    Uses constant-time comparison to prevent timing attacks.

    Args:
        provided_token: Token provided by user
        stored_hash: Hash stored in database

    Returns:
        True if token is valid
    """
    provided_hash = hash_token(provided_token)
    return hmac.compare_digest(provided_hash, stored_hash)


# ============================================================================
# Authorization Helpers (IDOR Protection)
# ============================================================================

class AuthorizationError(Exception):
    """Raised when a user attempts unauthorized access."""
    pass


def get_current_user_id() -> Optional[int]:
    """Get the current logged-in user's ID from session."""
    return session.get('user_id')


def require_login(f):
    """
    Decorator to require user authentication.

    Returns 401 for API requests, redirects for page requests.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if _is_api_request():
                return jsonify({'success': False, 'error': 'Authentication required'}), 401
            from flask import redirect, url_for
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def authorize_resource_owner(resource_user_id: int, error_message: str = "Access denied") -> bool:
    """
    Verify current user owns a resource.

    Args:
        resource_user_id: The user_id that owns the resource
        error_message: Custom error message for denial

    Returns:
        True if authorized

    Raises:
        AuthorizationError if not authorized
    """
    current_user = get_current_user_id()
    if current_user is None:
        raise AuthorizationError("Authentication required")
    if current_user != resource_user_id:
        raise AuthorizationError(error_message)
    return True


def authorize_order_participant(order_id: int) -> dict:
    """
    Verify current user is buyer or seller for an order.

    Args:
        order_id: The order to check

    Returns:
        Order dict with role ('buyer' or 'seller')

    Raises:
        AuthorizationError if not a participant
    """
    current_user = get_current_user_id()
    if current_user is None:
        raise AuthorizationError("Authentication required")

    conn = get_db_connection()
    order = conn.execute('''
        SELECT id, buyer_id
        FROM orders WHERE id = ?
    ''', (order_id,)).fetchone()

    if not order:
        conn.close()
        raise AuthorizationError("Order not found")

    if order['buyer_id'] == current_user:
        conn.close()
        return dict(order, role='buyer')

    # Check if user is the seller via order_items → listings
    seller_check = conn.execute('''
        SELECT l.seller_id
        FROM order_items oi
        JOIN listings l ON oi.listing_id = l.id
        WHERE oi.order_id = ? AND l.seller_id = ?
        LIMIT 1
    ''', (order_id, current_user)).fetchone()
    conn.close()

    if seller_check:
        return {**dict(order), 'seller_id': current_user, 'role': 'seller'}

    raise AuthorizationError("You are not a participant in this order")


def authorize_listing_owner(listing_id: int) -> dict:
    """
    Verify current user owns a listing.

    Args:
        listing_id: The listing to check

    Returns:
        Listing dict if authorized

    Raises:
        AuthorizationError if not owner
    """
    current_user = get_current_user_id()
    if current_user is None:
        raise AuthorizationError("Authentication required")

    conn = get_db_connection()
    listing = conn.execute('''
        SELECT * FROM listings WHERE id = ?
    ''', (listing_id,)).fetchone()
    conn.close()

    if not listing:
        raise AuthorizationError("Listing not found")

    if listing['seller_id'] != current_user:
        raise AuthorizationError("You do not own this listing")

    return dict(listing)


def authorize_bid_participant(bid_id: int) -> dict:
    """
    Verify current user is bidder or listing owner for a bid.

    Args:
        bid_id: The bid to check

    Returns:
        Bid dict with role ('bidder' or 'seller')

    Raises:
        AuthorizationError if not a participant
    """
    current_user = get_current_user_id()
    if current_user is None:
        raise AuthorizationError("Authentication required")

    conn = get_db_connection()
    bid = conn.execute('''
        SELECT b.*, l.seller_id as listing_seller_id
        FROM bids b
        JOIN listings l ON b.listing_id = l.id
        WHERE b.id = ?
    ''', (bid_id,)).fetchone()
    conn.close()

    if not bid:
        raise AuthorizationError("Bid not found")

    if bid['bidder_id'] == current_user:
        return dict(bid, role='bidder')
    elif bid['listing_seller_id'] == current_user:
        return dict(bid, role='seller')
    else:
        raise AuthorizationError("You are not a participant in this bid")


def authorize_message_thread(order_id: int, participant_id: int) -> dict:
    """
    Verify current user can access a message thread.

    Args:
        order_id: The order the messages relate to
        participant_id: The other party in the conversation

    Returns:
        Dict with thread info if authorized

    Raises:
        AuthorizationError if not authorized
    """
    current_user = get_current_user_id()
    if current_user is None:
        raise AuthorizationError("Authentication required")

    conn = get_db_connection()
    order = conn.execute('''
        SELECT id, buyer_id, seller_id
        FROM orders WHERE id = ?
    ''', (order_id,)).fetchone()
    conn.close()

    if not order:
        raise AuthorizationError("Order not found")

    # User must be buyer or seller in the order
    if current_user not in (order['buyer_id'], order['seller_id']):
        raise AuthorizationError("You are not a participant in this order")

    # Participant must be the other party
    other_party = order['seller_id'] if current_user == order['buyer_id'] else order['buyer_id']
    if participant_id != other_party:
        raise AuthorizationError("Invalid message recipient")

    return {
        'order_id': order_id,
        'current_user': current_user,
        'other_party': other_party
    }


def authorize_address_owner(address_id: int) -> dict:
    """
    Verify current user owns an address.

    Args:
        address_id: The address to check

    Returns:
        Address dict if authorized

    Raises:
        AuthorizationError if not owner
    """
    current_user = get_current_user_id()
    if current_user is None:
        raise AuthorizationError("Authentication required")

    conn = get_db_connection()
    address = conn.execute('''
        SELECT * FROM addresses WHERE id = ?
    ''', (address_id,)).fetchone()
    conn.close()

    if not address:
        raise AuthorizationError("Address not found")

    if address['user_id'] != current_user:
        raise AuthorizationError("You do not own this address")

    return dict(address)


def authorize_notification_owner(notification_id: int) -> dict:
    """
    Verify current user owns a notification.

    Args:
        notification_id: The notification to check

    Returns:
        Notification dict if authorized

    Raises:
        AuthorizationError if not owner
    """
    current_user = get_current_user_id()
    if current_user is None:
        raise AuthorizationError("Authentication required")

    conn = get_db_connection()
    notification = conn.execute('''
        SELECT * FROM notifications WHERE id = ?
    ''', (notification_id,)).fetchone()
    conn.close()

    if not notification:
        raise AuthorizationError("Notification not found")

    if notification['user_id'] != current_user:
        raise AuthorizationError("You do not own this notification")

    return dict(notification)


def authorize_payment_method_owner(method_id: int) -> dict:
    """
    Verify current user owns a payment method.

    Args:
        method_id: The payment method to check

    Returns:
        Payment method dict if authorized

    Raises:
        AuthorizationError if not owner
    """
    current_user = get_current_user_id()
    if current_user is None:
        raise AuthorizationError("Authentication required")

    conn = get_db_connection()
    method = conn.execute('''
        SELECT * FROM payment_methods WHERE id = ?
    ''', (method_id,)).fetchone()
    conn.close()

    if not method:
        raise AuthorizationError("Payment method not found")

    if method['user_id'] != current_user:
        raise AuthorizationError("You do not own this payment method")

    return dict(method)


def authorize_report_owner(report_id: int) -> dict:
    """
    Verify current user created a report.

    Args:
        report_id: The report to check

    Returns:
        Report dict if authorized

    Raises:
        AuthorizationError if not owner
    """
    current_user = get_current_user_id()
    if current_user is None:
        raise AuthorizationError("Authentication required")

    conn = get_db_connection()
    report = conn.execute('''
        SELECT * FROM reports WHERE id = ?
    ''', (report_id,)).fetchone()
    conn.close()

    if not report:
        raise AuthorizationError("Report not found")

    if report['reporter_id'] != current_user:
        raise AuthorizationError("You do not have access to this report")

    return dict(report)


def authorize_cart_owner_for_bucket(bucket_id: int) -> list:
    """
    Verify current user has items in cart for this bucket.

    Args:
        bucket_id: The bucket/category to check

    Returns:
        List of cart items for this user/bucket

    Raises:
        AuthorizationError if user doesn't have items in this bucket
    """
    current_user = get_current_user_id()
    if current_user is None:
        raise AuthorizationError("Authentication required")

    conn = get_db_connection()
    items = conn.execute('''
        SELECT c.* FROM cart c
        JOIN listings l ON c.listing_id = l.id
        WHERE c.user_id = ? AND l.category_id = ?
    ''', (current_user, bucket_id)).fetchall()
    conn.close()

    if not items:
        raise AuthorizationError("No cart items found for this bucket")

    return [dict(item) for item in items]


def is_admin() -> bool:
    """Check if current user is an admin."""
    user_id = get_current_user_id()
    if not user_id:
        return False

    conn = get_db_connection()
    user = conn.execute(
        'SELECT is_admin FROM users WHERE id = ?', (user_id,)
    ).fetchone()
    conn.close()

    return bool(user and user['is_admin'])


def authorize_admin(f):
    """
    Decorator to require admin access.

    Returns 403 for non-admins.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_admin():
            if _is_api_request():
                return jsonify({'success': False, 'error': 'Admin access required'}), 403
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ============================================================================
# Input Validation
# ============================================================================

def validate_positive_integer(value: Any, field_name: str, max_value: int = 1000000) -> int:
    """
    Validate and convert a value to a positive integer.

    Args:
        value: The value to validate
        field_name: Name of field for error messages
        max_value: Maximum allowed value

    Returns:
        Validated integer

    Raises:
        ValueError with descriptive message
    """
    try:
        int_val = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a valid number")

    if int_val <= 0:
        raise ValueError(f"{field_name} must be positive")

    if int_val > max_value:
        raise ValueError(f"{field_name} exceeds maximum allowed value")

    return int_val


def validate_positive_float(value: Any, field_name: str, max_value: float = 10000000.0) -> float:
    """
    Validate and convert a value to a positive float.

    Args:
        value: The value to validate
        field_name: Name of field for error messages
        max_value: Maximum allowed value

    Returns:
        Validated float

    Raises:
        ValueError with descriptive message
    """
    try:
        float_val = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a valid number")

    if float_val < 0:
        raise ValueError(f"{field_name} cannot be negative")

    if float_val > max_value:
        raise ValueError(f"{field_name} exceeds maximum allowed value")

    return float_val


def sanitize_string(value: str, max_length: int = 1000, strip: bool = True) -> str:
    """
    Sanitize a string input.

    Args:
        value: The string to sanitize
        max_length: Maximum allowed length
        strip: Whether to strip whitespace

    Returns:
        Sanitized string
    """
    if not isinstance(value, str):
        value = str(value)

    if strip:
        value = value.strip()

    if len(value) > max_length:
        value = value[:max_length]

    return value


# ============================================================================
# Session Management
# ============================================================================

def regenerate_session():
    """
    Regenerate the session to prevent session fixation attacks.

    Call this after successful login.
    """
    # Store data we want to preserve
    user_id = session.get('user_id')

    # Clear the session
    session.clear()

    # Restore user data
    if user_id:
        session['user_id'] = user_id

    # Mark session as modified to ensure new session ID
    session.modified = True


def invalidate_session():
    """
    Completely invalidate the current session.

    Call this on logout.
    """
    session.clear()


def set_session_user(user_id: int, username: str = None):
    """
    Set up a new user session after login.

    Regenerates session ID to prevent fixation attacks.

    Args:
        user_id: The authenticated user's ID
        username: Optional username to store
    """
    # Clear any existing session data first
    session.clear()

    # Set new session data
    session['user_id'] = user_id
    if username:
        session['username'] = username

    # Add session version for password change invalidation
    session['session_version'] = int(time.time())

    # Mark as modified
    session.modified = True


# ============================================================================
# Internal Helpers
# ============================================================================

def _is_api_request() -> bool:
    """Check if the current request is an API/AJAX request."""
    return (
        request.is_json or
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
        request.accept_mimetypes.accept_json
    )


# ============================================================================
# Error Handler Decorator
# ============================================================================

def handle_authorization_errors(f):
    """
    Decorator to catch AuthorizationError and return appropriate response.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except AuthorizationError as e:
            if _is_api_request():
                return jsonify({'success': False, 'error': str(e)}), 403
            abort(403)
    return decorated
