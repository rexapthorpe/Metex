"""
Rate limiting configuration for Metex application.

Uses Flask-Limiter to protect against:
- Brute force login attacks
- Registration spam
- Password reset email spam
- API abuse
- Message/notification spam
"""
import os
from flask import request, jsonify
from functools import wraps

# Rate limiter instance - initialized in create_app
limiter = None


def init_rate_limiter(app):
    """
    Initialize the rate limiter with the Flask app.

    Call this in create_app() after app is created.

    Supports Redis for production (distributed rate limiting) with
    automatic fallback to in-memory storage for local development.

    Args:
        app: Flask application instance
    """
    global limiter

    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address
    except ImportError:
        # Flask-Limiter not installed - provide stub
        app.logger.warning("Flask-Limiter not installed. Rate limiting disabled.")
        return None

    # Get storage URL from environment
    # Production should use Redis: redis://localhost:6379 or redis://:password@host:port/0
    # Development defaults to memory://
    storage_url = os.getenv('RATELIMIT_STORAGE_URL', 'memory://')

    # Try Redis if configured, fall back to memory
    actual_storage = storage_url
    if storage_url.startswith('redis://'):
        try:
            import redis
            # Test Redis connection
            redis_url = storage_url
            client = redis.from_url(redis_url, socket_timeout=2)
            client.ping()
            app.logger.info(f"Rate limiting using Redis: {redis_url.split('@')[-1] if '@' in redis_url else redis_url}")
        except Exception as e:
            app.logger.warning(f"Redis unavailable ({e}), falling back to memory storage")
            actual_storage = 'memory://'

    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        storage_uri=actual_storage,
        default_limits=["200 per hour", "50 per minute"],
        # Don't count successful responses against limits for some endpoints
        default_limits_deduct_when=lambda response: response.status_code >= 400
    )

    # Custom error handler for rate limit exceeded
    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        # Log rate limit event
        try:
            from services.audit_service import log_rate_limit_exceeded
            log_rate_limit_exceeded(request.endpoint or 'unknown', str(e.description) if hasattr(e, 'description') else 'unknown')
        except ImportError:
            pass

        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'error': 'rate_limit',
                'message': 'Too many requests. Please wait before trying again.',
                'retry_after': 60
            }), 429
        return '''
        <!DOCTYPE html>
        <html>
        <head><title>Too Many Requests</title></head>
        <body>
            <h1>Too Many Requests (429)</h1>
            <p>You have made too many requests. Please wait a minute and try again.</p>
            <p><a href="javascript:history.back()">Go Back</a></p>
        </body>
        </html>
        ''', 429

    app.logger.info("Rate limiting initialized")
    return limiter


def get_limiter():
    """Get the rate limiter instance."""
    return limiter


# ============================================================================
# Rate Limit Decorators - Use these directly on route functions
# ============================================================================

def rate_limit(limit_string):
    """
    Generic rate limit decorator.

    Args:
        limit_string: Rate limit string, e.g., "5 per minute;20 per hour"

    Usage:
        @app.route('/login', methods=['POST'])
        @rate_limit("5 per minute;20 per hour")
        def login():
            pass
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            return f(*args, **kwargs)

        # If limiter is initialized, apply the limit
        if limiter is not None:
            return limiter.limit(limit_string)(decorated_function)
        return decorated_function
    return decorator


def rate_limit_deferred(limit_string):
    """
    Rate limit decorator that defers limiter lookup until request time.
    Use this when decorating functions before limiter is initialized.

    Args:
        limit_string: Rate limit string, e.g., "5 per minute"
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if limiter is not None:
                # Apply rate limit at request time
                @limiter.limit(limit_string)
                @wraps(f)
                def limited(*args, **kwargs):
                    return f(*args, **kwargs)
                return limited(*args, **kwargs)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ============================================================================
# Specific Rate Limit Decorators (for common use cases)
# ============================================================================

# Login: 5 attempts per minute, 20 per hour
limit_login = rate_limit_deferred("5 per minute;20 per hour")

# Registration: 3 per hour
limit_registration = rate_limit_deferred("3 per hour")

# Password reset: 3 per hour
limit_password_reset = rate_limit_deferred("3 per hour")

# Message sending: 30 per minute
limit_message_send = rate_limit_deferred("30 per minute")

# Listing creation: 20 per hour
limit_listing_create = rate_limit_deferred("20 per hour")

# Bid submission: 30 per hour
limit_bid_submit = rate_limit_deferred("30 per hour")

# Report submission: 10 per hour
limit_report_submit = rate_limit_deferred("10 per hour")

# Checkout/purchase: 10 per hour
limit_checkout = rate_limit_deferred("10 per hour")


# ============================================================================
# Rate Limit by User (requires authentication)
# ============================================================================

def get_user_key():
    """Get rate limit key based on user ID (for authenticated endpoints)."""
    from flask import session
    user_id = session.get('user_id')
    if user_id:
        return f"user:{user_id}"
    # Fall back to IP for unauthenticated requests
    return request.remote_addr


def rate_limit_by_user(limit_string):
    """
    Decorator to rate limit by user ID instead of IP.

    Args:
        limit_string: Rate limit string, e.g., "10 per minute"
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if limiter is not None:
                @limiter.limit(limit_string, key_func=get_user_key)
                @wraps(f)
                def limited(*args, **kwargs):
                    return f(*args, **kwargs)
                return limited(*args, **kwargs)
            return f(*args, **kwargs)
        return decorated_function
    return decorator
