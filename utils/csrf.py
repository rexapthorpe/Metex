"""
CSRF Protection Module

Provides global CSRF protection using Flask-WTF's CSRFProtect.
Supports both form-based and AJAX/API requests.

Usage:
    from utils.csrf import init_csrf, csrf

    # In create_app():
    init_csrf(app)

    # In templates (forms):
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

    # In AJAX requests:
    headers: { 'X-CSRFToken': getCsrfToken() }
"""
import os
from functools import wraps
from flask import request, jsonify, abort, g, current_app

# CSRF protection instance
csrf = None

# Routes exempt from CSRF (public read-only APIs)
CSRF_EXEMPT_ROUTES = frozenset([
    # Public bucket/listing view APIs (read-only)
    'buy.bucket_view',
    'buy.bucket_availability_json',
    'buy.bucket_sellers_api',
    # Static assets
    'static',
])


def init_csrf(app):
    """
    Initialize CSRF protection for the application.

    Args:
        app: Flask application instance
    """
    global csrf

    try:
        from flask_wtf.csrf import CSRFProtect, CSRFError
    except ImportError:
        app.logger.warning(
            "Flask-WTF not installed. CSRF protection disabled. "
            "Install with: pip install Flask-WTF"
        )
        return None

    # Initialize CSRFProtect
    csrf = CSRFProtect()
    csrf.init_app(app)

    # Configure CSRF settings
    app.config.setdefault('WTF_CSRF_ENABLED', True)
    app.config.setdefault('WTF_CSRF_TIME_LIMIT', 3600)  # 1 hour token validity
    app.config.setdefault('WTF_CSRF_SSL_STRICT', os.getenv('FLASK_ENV') == 'production')

    # Custom CSRF error handler
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        """Handle CSRF validation failures."""
        # Log the attempt
        try:
            from services.audit_service import log_security_event, SecurityEventType
            from flask import session
            log_security_event(
                event_type=SecurityEventType.CSRF_FAILURE,
                user_id=session.get('user_id'),
                details={
                    'reason': str(e.description),
                    'endpoint': request.endpoint,
                    'method': request.method,
                    'origin': request.headers.get('Origin'),
                    'referer': request.headers.get('Referer')
                }
            )
        except ImportError:
            pass

        # Return appropriate response format
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
           request.content_type == 'application/json':
            return jsonify({
                'success': False,
                'error': 'csrf_error',
                'message': 'CSRF token missing or invalid. Please refresh the page and try again.'
            }), 403

        # For regular form submissions
        return (
            f'<h1>Security Error</h1>'
            f'<p>CSRF token validation failed. Please go back and try again.</p>'
            f'<p><a href="javascript:history.back()">Go Back</a></p>'
        ), 403

    # Add CSRF token to template context
    @app.context_processor
    def csrf_context():
        """Inject CSRF token helper into templates."""
        from flask_wtf.csrf import generate_csrf
        return dict(csrf_token=generate_csrf)

    app.logger.info("CSRF protection initialized")
    return csrf


def csrf_exempt(f):
    """
    Decorator to exempt a view from CSRF protection.

    Use sparingly and only for:
    - Webhook endpoints (verify signatures instead)
    - Public read-only APIs
    - Health check endpoints

    Example:
        @app.route('/webhook/stripe', methods=['POST'])
        @csrf_exempt
        def stripe_webhook():
            # Verify Stripe signature here
            pass
    """
    if csrf is not None:
        return csrf.exempt(f)
    return f


def require_csrf(f):
    """
    Decorator to explicitly require CSRF validation.

    Useful for endpoints that might be exempt by default but should require CSRF.

    Example:
        @app.route('/api/sensitive-action', methods=['POST'])
        @require_csrf
        def sensitive_action():
            pass
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if csrf is None:
            return f(*args, **kwargs)

        # Manually validate CSRF
        from flask_wtf.csrf import validate_csrf
        try:
            # Check header first (for AJAX)
            token = request.headers.get('X-CSRFToken') or \
                    request.headers.get('X-CSRF-Token') or \
                    request.form.get('csrf_token')
            validate_csrf(token)
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'error': 'csrf_error',
                    'message': 'CSRF token missing or invalid.'
                }), 403
            abort(403, description='CSRF validation failed')

        return f(*args, **kwargs)
    return decorated_function


def get_csrf_token():
    """
    Get the current CSRF token for use in AJAX requests.

    Returns:
        str: CSRF token or empty string if CSRF is disabled
    """
    if csrf is None:
        return ''

    from flask_wtf.csrf import generate_csrf
    return generate_csrf()


# JavaScript helper for CSRF token in AJAX requests
CSRF_JS_HELPER = """
// CSRF Token Helper for AJAX Requests
// Include this in your base template

function getCsrfToken() {
    // Try meta tag first
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute('content');

    // Try hidden input
    var input = document.querySelector('input[name="csrf_token"]');
    if (input) return input.value;

    // Try cookie (double-submit pattern)
    var match = document.cookie.match(/csrf_token=([^;]+)/);
    if (match) return match[1];

    return '';
}

// Automatically add CSRF token to all AJAX requests
(function() {
    var originalFetch = window.fetch;
    window.fetch = function(url, options) {
        options = options || {};
        options.headers = options.headers || {};

        // Add CSRF token for state-changing methods
        var method = (options.method || 'GET').toUpperCase();
        if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
            if (!options.headers['X-CSRFToken']) {
                options.headers['X-CSRFToken'] = getCsrfToken();
            }
        }

        return originalFetch(url, options);
    };

    // For jQuery users
    if (typeof $ !== 'undefined' && $.ajaxSetup) {
        $.ajaxSetup({
            beforeSend: function(xhr, settings) {
                if (!(/^(GET|HEAD|OPTIONS|TRACE)$/i.test(settings.type))) {
                    xhr.setRequestHeader('X-CSRFToken', getCsrfToken());
                }
            }
        });
    }
})();
"""
