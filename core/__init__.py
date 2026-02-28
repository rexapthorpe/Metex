"""
Metex Application Factory

This module provides the create_app() function which creates and configures
the Flask application. This pattern allows for:
- Multiple app instances for testing
- Deferred configuration
- Easier refactoring

IMPORTANT: This factory must produce an app that behaves IDENTICALLY to the
original app.py. No behavior changes are permitted during refactoring.
"""
import os
import sqlite3
import click
from flask import Flask, redirect, url_for, request
from flask.cli import with_appcontext


def create_app(test_config=None):
    """
    Application factory function.

    Args:
        test_config: Optional dictionary of configuration overrides for testing.

    Returns:
        Flask application instance configured and ready to run.
    """
    # Import config at function scope to avoid circular imports
    import config as app_config

    # Create Flask app
    app = Flask(__name__, template_folder='../templates', static_folder='../static')

    # Configure the app
    app.secret_key = app_config.SECRET_KEY

    # =========================================================================
    # Security: Session Cookie Configuration
    # =========================================================================
    # These settings protect session cookies from theft and misuse
    is_production = os.getenv('FLASK_ENV') == 'production'

    app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JS access to cookies
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Prevent CSRF via cookies
    # Only set Secure flag in production (requires HTTPS)
    app.config['SESSION_COOKIE_SECURE'] = is_production
    # Session expires after 24 hours of inactivity
    app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours

    # Set max upload size to 100MB (allows multiple photos per set listing)
    app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
    app.config['MAX_FORM_MEMORY_SIZE'] = 100 * 1024 * 1024  # 100MB

    # Apply test config if provided
    if test_config:
        app.config.update(test_config)

    # =========================================================================
    # Security: Proxy Safety (for deployment behind Render, Heroku, etc.)
    # =========================================================================
    if os.getenv('BEHIND_PROXY', 'false').lower() == 'true':
        try:
            from werkzeug.middleware.proxy_fix import ProxyFix
            # Trust X-Forwarded-* headers from 1 proxy
            app.wsgi_app = ProxyFix(
                app.wsgi_app,
                x_for=1,      # X-Forwarded-For
                x_proto=1,    # X-Forwarded-Proto
                x_host=1,     # X-Forwarded-Host
                x_prefix=1    # X-Forwarded-Prefix
            )
            app.logger.info("ProxyFix middleware enabled")
        except ImportError:
            app.logger.warning("ProxyFix not available")

    # =========================================================================
    # Security: Initialize CSRF Protection
    # =========================================================================
    csrf_initialized = False
    if not test_config or not test_config.get('WTF_CSRF_ENABLED', True):
        try:
            from utils.csrf import init_csrf
            result = init_csrf(app)
            csrf_initialized = result is not None
        except ImportError:
            app.logger.warning("Flask-WTF not installed. CSRF protection disabled.")

    # If CSRF wasn't initialized (Flask-WTF not installed), add a dummy csrf_token
    # function to prevent template errors
    if not csrf_initialized:
        @app.context_processor
        def csrf_dummy_context():
            """Provide dummy csrf_token when Flask-WTF is not installed."""
            def dummy_csrf_token():
                return ''
            return dict(csrf_token=dummy_csrf_token)

    # =========================================================================
    # Security: Initialize Rate Limiter
    # =========================================================================
    if not test_config or not test_config.get('TESTING'):
        try:
            from utils.rate_limit import init_rate_limiter
            init_rate_limiter(app)
        except ImportError:
            pass  # Flask-Limiter not installed

    # =========================================================================
    # Security: Security Headers Middleware
    # =========================================================================
    # Determine security mode from explicit config (more reliable than FLASK_ENV)
    secure_cookies = os.getenv('SECURE_COOKIES', 'false').lower() == 'true'
    enable_hsts = os.getenv('ENABLE_HSTS', 'false').lower() == 'true'

    # Update session cookie security based on explicit config
    if secure_cookies:
        app.config['SESSION_COOKIE_SECURE'] = True

    @app.after_request
    def add_security_headers(response):
        """Add security headers to all responses."""
        # Prevent clickjacking
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'

        # Prevent MIME type sniffing
        response.headers['X-Content-Type-Options'] = 'nosniff'

        # XSS Protection (legacy, but still useful)
        response.headers['X-XSS-Protection'] = '1; mode=block'

        # Referrer Policy - don't leak full URLs to external sites
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        # Permissions Policy - restrict browser features
        response.headers['Permissions-Policy'] = (
            'accelerometer=(), camera=(), geolocation=(), gyroscope=(), '
            'magnetometer=(), microphone=(), payment=(), usb=()'
        )

        # Content Security Policy - tightened but still compatible
        # Uses explicit CDN hosts, restricts object/embed/frame
        csp_directives = [
            "default-src 'self'",
            # Scripts: Allow self, CDNs for libraries. unsafe-inline needed for existing code
            # TODO: Migrate inline scripts to external files and add nonces to remove unsafe-inline
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://unpkg.com",
            # Styles: Allow self, Google Fonts, CDNs. unsafe-inline for inline styles
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com",
            # Fonts from Google and CDNjs
            "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com",
            # Images from self, data URIs (for inline images), and HTTPS sources
            "img-src 'self' data: blob: https:",
            # Connect (AJAX/Fetch) only to self
            "connect-src 'self'",
            # Prevent embedding in frames except self
            "frame-ancestors 'self'",
            # Forms can only submit to self
            "form-action 'self'",
            # Base URI must be self (prevents base tag injection)
            "base-uri 'self'",
            # Block object, embed, applet (Flash, Java plugins)
            "object-src 'none'",
            # Upgrade insecure requests to HTTPS
            "upgrade-insecure-requests"
        ]
        response.headers['Content-Security-Policy'] = '; '.join(csp_directives)

        # HSTS - only when explicitly enabled AND request is over HTTPS
        # request.is_secure respects ProxyFix's X-Forwarded-Proto handling
        if enable_hsts and request.is_secure:
            response.headers['Strict-Transport-Security'] = (
                'max-age=31536000; includeSubDomains; preload'
            )

        return response

    # Initialize database schema
    from db_init import init_database
    init_database()

    # Register context processors
    _register_context_processors(app)

    # Register blueprints
    _register_blueprints(app)

    # Register error handlers
    _register_error_handlers(app)

    # Register Jinja filters
    _register_jinja_filters(app)

    # Register CLI commands
    _register_cli_commands(app)

    # Register index route
    @app.route('/')
    def index():
        return redirect(url_for('buy.buy'))

    return app


def _register_context_processors(app):
    """Register template context processors."""
    from utils.auth_utils import is_user_admin

    @app.context_processor
    def inject_admin_check():
        from flask import session
        return dict(is_user_admin=is_user_admin(session.get('user_id')))

    @app.context_processor
    def inject_frozen_status():
        """Inject frozen account status for global banner display"""
        from flask import session
        from database import get_db_connection

        user_id = session.get('user_id')
        if not user_id:
            return dict(is_user_frozen=False, freeze_reason=None, frozen_admin_id=None)

        try:
            conn = get_db_connection()
            user = conn.execute(
                'SELECT is_frozen, freeze_reason FROM users WHERE id = ?',
                (user_id,)
            ).fetchone()
            conn.close()

            if user and user['is_frozen']:
                # Get an admin user id for messaging
                conn = get_db_connection()
                admin = conn.execute(
                    'SELECT id FROM users WHERE is_admin = 1 LIMIT 1'
                ).fetchone()
                conn.close()
                admin_id = admin['id'] if admin else None

                return dict(
                    is_user_frozen=True,
                    freeze_reason=user['freeze_reason'] or 'No reason provided',
                    frozen_admin_id=admin_id
                )
        except Exception as e:
            print(f"[Context Processor] Error checking frozen status: {e}")

        return dict(is_user_frozen=False, freeze_reason=None, frozen_admin_id=None)


def _register_blueprints(app):
    """Register all application blueprints."""
    # Import blueprints from routes/ (current location)
    from routes.auth_routes import auth_bp
    from core.blueprints.sell import sell_bp
    from core.blueprints.listings import listings_bp
    from routes.buy_routes import buy_bp
    from routes.account_routes import account_bp
    from routes.checkout_routes import checkout_bp
    from routes.messages_routes import messages_bp
    from routes.cart_routes import cart_bp
    from core.blueprints.bids import bid_bp
    from routes.ratings_routes import ratings_bp
    from routes.api_routes import api_bp
    from routes.notification_routes import notification_bp
    from routes.portfolio_routes import portfolio_bp
    from routes.bucket_routes import bucket_bp
    from routes.admin_routes import admin_bp
    from routes.cancellation_routes import cancellation_bp
    from routes.report_routes import report_bp

    # Register blueprints with their URL prefixes
    # IMPORTANT: url_prefix values must remain IDENTICAL during refactoring
    app.register_blueprint(auth_bp)
    app.register_blueprint(sell_bp)
    app.register_blueprint(listings_bp, url_prefix='/listings')
    app.register_blueprint(buy_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(checkout_bp)
    app.register_blueprint(messages_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(bid_bp)
    app.register_blueprint(ratings_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(notification_bp)
    app.register_blueprint(portfolio_bp)
    app.register_blueprint(bucket_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(cancellation_bp)
    app.register_blueprint(report_bp)


def _register_error_handlers(app):
    """Register custom error handlers."""
    from flask import jsonify, request as req
    import traceback

    # Diagnostic endpoint to check upload limits
    @app.route('/diagnostic/upload-limits')
    def diagnostic_upload_limits():
        """Show current upload limit configuration"""
        max_size = app.config.get('MAX_CONTENT_LENGTH', 0)
        max_size_mb = max_size / (1024 * 1024)

        return jsonify({
            'max_content_length_bytes': max_size,
            'max_content_length_mb': round(max_size_mb, 2),
            'status': 'configured' if max_size > 0 else 'not_set'
        })

    @app.errorhandler(413)
    def request_entity_too_large(error):
        """Handle 413 errors with helpful message"""
        max_size_mb = app.config.get('MAX_CONTENT_LENGTH', 0) / (1024 * 1024)

        error_msg = f"Upload too large. Maximum allowed size is {max_size_mb:.0f}MB. " \
                    f"Please reduce photo sizes or use fewer photos."

        # For AJAX requests, return JSON
        if req.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': error_msg,
                'max_size_mb': int(max_size_mb)
            }), 413

        # For regular requests, return HTML
        return f'''
        <!DOCTYPE html>
        <html>
        <head><title>Upload Too Large</title></head>
        <body>
            <h1>Upload Too Large (413)</h1>
            <p>{error_msg}</p>
            <p><a href="javascript:history.back()">Go Back</a></p>
        </body>
        </html>
        ''', 413

    @app.errorhandler(500)
    def internal_server_error(error):
        """Handle 500 errors - always return JSON for AJAX requests"""
        # Log the actual error for debugging
        print("=" * 80)
        print("[500 ERROR HANDLER]")
        print(f"Error: {error}")
        print(traceback.format_exc())
        print("=" * 80)

        error_msg = "An unexpected error occurred. Please try again."

        # For AJAX requests, return JSON
        if req.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': error_msg
            }), 500

        # For regular requests, return HTML
        return f'''
        <!DOCTYPE html>
        <html>
        <head><title>Server Error</title></head>
        <body>
            <h1>Server Error (500)</h1>
            <p>{error_msg}</p>
            <p><a href="javascript:history.back()">Go Back</a></p>
        </body>
        </html>
        ''', 500

    @app.errorhandler(400)
    def bad_request(error):
        """Handle 400 errors - always return JSON for AJAX requests"""
        error_msg = str(error.description) if hasattr(error, 'description') else "Bad request. Please check your input."

        # For AJAX requests, return JSON
        if req.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': error_msg
            }), 400

        # For regular requests, return HTML
        return f'''
        <!DOCTYPE html>
        <html>
        <head><title>Bad Request</title></head>
        <body>
            <h1>Bad Request (400)</h1>
            <p>{error_msg}</p>
            <p><a href="javascript:history.back()">Go Back</a></p>
        </body>
        </html>
        ''', 400


def _register_jinja_filters(app):
    """Register custom Jinja2 template filters."""

    @app.template_filter('commas')
    def format_with_commas(value):
        """
        Format a number with comma separators for thousands.
        Preserves decimals. Examples: 1234 -> 1,234 | 1234.56 -> 1,234.56
        """
        if value is None:
            return ''

        try:
            # Convert to float to handle both int and float inputs
            num = float(value)

            # Split into integer and decimal parts
            if '.' in str(num):
                int_part, dec_part = str(num).split('.')
                # Format integer part with commas
                int_part = '{:,}'.format(int(float(int_part)))
                return f"{int_part}.{dec_part}"
            else:
                # No decimal part, just format the integer
                return '{:,}'.format(int(num))
        except (ValueError, TypeError):
            # If conversion fails, return original value as string
            return str(value)

    @app.template_filter('currency')
    def format_currency(value):
        """
        Format a number as currency with 2 decimal places and comma separators.
        Examples: 1234 -> 1,234.00 | 1234.5 -> 1,234.50 | 1234.56 -> 1,234.56
        """
        if value is None:
            return ''

        try:
            num = float(value)
            return '{:,.2f}'.format(num)
        except (ValueError, TypeError):
            return str(value)

    @app.template_filter('format_datetime')
    def format_datetime(value, format_str='%I:%M %p, %d %B %Y'):
        """
        Format a datetime string to a human-readable format.
        Default: "12:17 AM, 10 January 2026"
        """
        if not value:
            return 'N/A'

        from datetime import datetime

        try:
            # Try parsing common datetime formats
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d']:
                try:
                    dt = datetime.strptime(str(value)[:19] if len(str(value)) > 19 else str(value), fmt)
                    return dt.strftime(format_str)
                except ValueError:
                    continue
            # If no format worked, return the original value
            return str(value)
        except Exception:
            return str(value)


def _register_cli_commands(app):
    """Register Flask CLI commands."""

    @app.cli.command('clear-marketplace-data')
    @click.option('--yes', '-y', is_flag=True, help='Skip confirmation prompt')
    @with_appcontext
    def clear_marketplace_data(yes):
        """
        Clear all marketplace data (buckets, listings, bids, orders, cart, etc.)
        while preserving user accounts and database schema.
        """
        if not yes:
            click.echo('\n  WARNING: This will delete ALL marketplace data!')
            click.echo('\nThe following will be cleared:')
            click.echo('  - All buckets (categories)')
            click.echo('  - All listings')
            click.echo('  - All bids')
            click.echo('  - All orders and order items')
            click.echo('  - All cart items')
            click.echo('  - All ratings')
            click.echo('  - All messages/conversations')
            click.echo('  - All notifications')
            click.echo('  - All portfolio data (exclusions, snapshots)')
            click.echo('  - All bucket price history')
            click.echo('\nUser accounts, addresses, and preferences will be PRESERVED.')
            click.echo()

            if not click.confirm('Are you sure you want to proceed?'):
                click.echo('Operation cancelled.')
                return

        try:
            conn = sqlite3.connect('data/database.db')
            cursor = conn.cursor()

            # Disable foreign key constraints temporarily for easier deletion
            cursor.execute('PRAGMA foreign_keys = OFF')

            click.echo('\n  Clearing marketplace data...\n')

            # Delete in order that respects dependencies (child tables first)
            tables_to_clear = [
                ('portfolio_exclusions', 'Portfolio exclusions'),
                ('portfolio_snapshots', 'Portfolio snapshots'),
                ('bucket_price_history', 'Bucket price history'),
                ('ratings', 'Ratings'),
                ('messages', 'Messages/conversations'),
                ('notifications', 'Notifications'),
                ('order_items', 'Order items'),
                ('orders', 'Orders'),
                ('bids', 'Bids'),
                ('cart', 'Cart items'),
                ('listings', 'Listings'),
                ('categories', 'Buckets/categories'),
            ]

            deleted_counts = {}

            for table_name, description in tables_to_clear:
                # Count records before deletion
                count_result = cursor.execute(f'SELECT COUNT(*) FROM {table_name}').fetchone()
                count = count_result[0] if count_result else 0

                # Delete all records
                cursor.execute(f'DELETE FROM {table_name}')

                # Reset autoincrement counter
                cursor.execute(f"DELETE FROM sqlite_sequence WHERE name = '{table_name}'")

                deleted_counts[description] = count
                click.echo(f'  Cleared {count:,} {description}')

            # Re-enable foreign key constraints
            cursor.execute('PRAGMA foreign_keys = ON')

            # Commit all changes
            conn.commit()
            conn.close()

            click.echo('\n  Marketplace data cleared successfully!')
            click.echo(f'\nTotal records deleted: {sum(deleted_counts.values()):,}')
            click.echo('\n  Summary:')
            for description, count in deleted_counts.items():
                if count > 0:
                    click.echo(f'     {description}: {count:,}')

        except sqlite3.Error as e:
            click.echo(f'\n  Database error: {e}', err=True)
            return 1
        except Exception as e:
            click.echo(f'\n  Unexpected error: {e}', err=True)
            return 1

    @app.cli.command('make-admin')
    @click.argument('email')
    @with_appcontext
    def make_admin(email):
        """
        Promote a user to admin by their email address.
        """
        try:
            conn = sqlite3.connect('data/database.db')
            cursor = conn.cursor()

            # Find user by email
            cursor.execute('SELECT id, email, is_admin FROM users WHERE email = ?', (email,))
            user = cursor.fetchone()

            if not user:
                click.echo(f'  User not found: {email}', err=True)
                conn.close()
                return 1

            user_id, user_email, is_admin = user

            if is_admin:
                click.echo(f'  User is already an admin: {user_email}')
                conn.close()
                return 0

            # Promote to admin
            cursor.execute('UPDATE users SET is_admin = 1 WHERE id = ?', (user_id,))
            conn.commit()
            conn.close()

            click.echo(f'  User promoted to admin: {user_email}')
            return 0

        except sqlite3.Error as e:
            click.echo(f'  Database error: {e}', err=True)
            return 1
        except Exception as e:
            click.echo(f'  Unexpected error: {e}', err=True)
            return 1

    @app.cli.command('remove-admin')
    @click.argument('email')
    @with_appcontext
    def remove_admin(email):
        """
        Revoke admin privileges from a user by their email address.
        """
        try:
            conn = sqlite3.connect('data/database.db')
            cursor = conn.cursor()

            # Find user by email
            cursor.execute('SELECT id, email, is_admin FROM users WHERE email = ?', (email,))
            user = cursor.fetchone()

            if not user:
                click.echo(f'  User not found: {email}', err=True)
                conn.close()
                return 1

            user_id, user_email, is_admin = user

            if not is_admin:
                click.echo(f'  User is not an admin: {user_email}')
                conn.close()
                return 0

            # Revoke admin privileges
            cursor.execute('UPDATE users SET is_admin = 0 WHERE id = ?', (user_id,))
            conn.commit()
            conn.close()

            click.echo(f'  Admin privileges revoked: {user_email}')
            return 0

        except sqlite3.Error as e:
            click.echo(f'  Database error: {e}', err=True)
            return 1
        except Exception as e:
            click.echo(f'  Unexpected error: {e}', err=True)
            return 1

    @app.cli.command('list-admins')
    @with_appcontext
    def list_admins():
        """
        List all admin users.
        """
        try:
            conn = sqlite3.connect('data/database.db')
            cursor = conn.cursor()

            cursor.execute(
                'SELECT id, email, username, first_name, last_name FROM users WHERE is_admin = 1'
            )
            admins = cursor.fetchall()
            conn.close()

            if not admins:
                click.echo('No admin users found.')
                return 0

            click.echo(f'\n  Admin Users ({len(admins)}):')
            click.echo('=' * 60)
            for admin in admins:
                user_id, email, username, first_name, last_name = admin
                name = f'{first_name} {last_name}' if first_name and last_name else 'N/A'
                click.echo(f'  ID: {user_id}')
                click.echo(f'  Email: {email}')
                click.echo(f'  Username: {username}')
                click.echo(f'  Name: {name}')
                click.echo('-' * 60)

            return 0

        except sqlite3.Error as e:
            click.echo(f'  Database error: {e}', err=True)
            return 1
        except Exception as e:
            click.echo(f'  Unexpected error: {e}', err=True)
            return 1


def print_startup_diagnostics():
    """Print environment configuration status on startup (masked for security)"""
    import config as app_config
    import os

    print('\n' + '='*80)
    print('MetEx - Environment Configuration')
    print('='*80)

    # Check METALPRICE_API_KEY
    api_key = app_config.METALPRICE_API_KEY
    if api_key:
        # Mask the key, show only last 4 characters
        masked_key = '****' + api_key[-4:] if len(api_key) >= 4 else '****'
        print(f'  METALPRICE_API_KEY: Set ({masked_key})')
    else:
        print(f'  METALPRICE_API_KEY: NOT SET')
        print(f'  -> Spot prices will use stale cache or show "unavailable"')
        print(f'  -> Create .env file and add your API key to enable live prices')

    # Check other critical env vars
    if app_config.SECRET_KEY and app_config.SECRET_KEY != 'your-very-random-fallback-key-here':
        print(f'  SECRET_KEY: Set (custom)')
    else:
        print(f'  SECRET_KEY: Using default (not secure for production)')

    # Database check
    db_path = 'data/database.db'
    if os.path.exists(db_path):
        db_size = os.path.getsize(db_path) / (1024 * 1024)  # MB
        print(f'  Database: {db_path} ({db_size:.2f} MB)')
    else:
        print(f'  Database: Not found at {db_path}')

    print('='*80 + '\n')
