/**
 * CSRF Protection Helper for AJAX Requests
 *
 * This script automatically adds CSRF tokens to all state-changing AJAX requests.
 * Include this in your base template after the CSRF meta tag.
 *
 * Usage:
 *   1. Add meta tag: <meta name="csrf-token" content="{{ csrf_token() }}">
 *   2. Include this script: <script src="{{ url_for('static', filename='js/csrf_helper.js') }}"></script>
 *
 * The script will automatically:
 *   - Add X-CSRFToken header to fetch() requests (POST, PUT, PATCH, DELETE)
 *   - Add X-CSRFToken header to jQuery $.ajax() requests
 *   - Provide getCsrfToken() function for manual use
 */

(function() {
    'use strict';

    /**
     * Get the CSRF token from the page.
     * Tries multiple sources in order of preference.
     *
     * @returns {string} CSRF token or empty string if not found
     */
    window.getCsrfToken = function() {
        // 1. Try meta tag (preferred)
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) {
            return meta.getAttribute('content') || '';
        }

        // 2. Try hidden input (for forms)
        var input = document.querySelector('input[name="csrf_token"]');
        if (input) {
            return input.value || '';
        }

        // 3. Try cookie (double-submit pattern fallback)
        var match = document.cookie.match(/csrf_token=([^;]+)/);
        if (match) {
            return match[1];
        }

        console.warn('CSRF token not found on page');
        return '';
    };

    /**
     * Check if a request method requires CSRF protection.
     *
     * @param {string} method - HTTP method
     * @returns {boolean} True if CSRF token should be added
     */
    function requiresCsrf(method) {
        method = (method || 'GET').toUpperCase();
        return ['POST', 'PUT', 'PATCH', 'DELETE'].indexOf(method) !== -1;
    }

    /**
     * Wrap fetch() to automatically add CSRF token.
     */
    var originalFetch = window.fetch;
    window.fetch = function(url, options) {
        options = options || {};

        // Ensure headers object exists
        if (!options.headers) {
            options.headers = {};
        }

        // Convert Headers object to plain object if needed
        if (options.headers instanceof Headers) {
            var headersObj = {};
            options.headers.forEach(function(value, key) {
                headersObj[key] = value;
            });
            options.headers = headersObj;
        }

        // Add CSRF token for state-changing methods
        var method = options.method || 'GET';
        if (requiresCsrf(method) && !options.headers['X-CSRFToken']) {
            var token = getCsrfToken();
            if (token) {
                options.headers['X-CSRFToken'] = token;
            }
        }

        return originalFetch(url, options);
    };

    /**
     * Configure jQuery AJAX to add CSRF token if jQuery is available.
     */
    function configureJQuery() {
        if (typeof $ === 'undefined' || !$.ajaxSetup) {
            return;
        }

        $.ajaxSetup({
            beforeSend: function(xhr, settings) {
                if (requiresCsrf(settings.type || settings.method)) {
                    var token = getCsrfToken();
                    if (token) {
                        xhr.setRequestHeader('X-CSRFToken', token);
                    }
                }
            }
        });
    }

    // Configure jQuery immediately if available
    configureJQuery();

    // Also configure jQuery when DOM is ready (in case jQuery loads later)
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', configureJQuery);
    }

    /**
     * Add CSRF token to form submissions.
     * This adds a hidden input if not already present.
     */
    document.addEventListener('submit', function(e) {
        var form = e.target;
        if (form.tagName !== 'FORM') return;

        // Skip GET forms
        var method = (form.method || 'GET').toUpperCase();
        if (!requiresCsrf(method)) return;

        // Skip if already has CSRF token
        if (form.querySelector('input[name="csrf_token"]')) return;

        // Add hidden CSRF input
        var token = getCsrfToken();
        if (token) {
            var input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'csrf_token';
            input.value = token;
            form.appendChild(input);
        }
    }, true);

    /**
     * Handle CSRF errors in responses.
     * Shows user-friendly message when CSRF validation fails.
     */
    window.handleCsrfError = function(response) {
        if (response && response.error === 'csrf_error') {
            // Show user-friendly error
            alert('Your session has expired. Please refresh the page and try again.');
            return true;
        }
        return false;
    };

    console.log('CSRF protection initialized');
})();
