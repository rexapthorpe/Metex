# Security Hardening V2 - Diff Map

Complete list of all files changed/added as part of P0 security hardening.

## Files Created

| File | Description |
|------|-------------|
| `utils/csrf.py` | CSRF protection module with Flask-WTF integration |
| `utils/upload_security.py` | Secure file upload validation with MIME and content checking |
| `static/js/csrf_helper.js` | Client-side CSRF token helper for AJAX requests |
| `tests/test_security_p0.py` | 35+ security tests covering all P0 items |
| `docs/security/SECURITY_HARDENING_PLAN_V2.md` | Updated security plan with all implementations |
| `docs/security/DIFF_MAP_V2.md` | This file - complete diff map |

## Files Modified

### Core Application

| File | Changes |
|------|---------|
| `core/__init__.py` | Added CSRF init, ProxyFix support, tightened CSP, explicit security config flags |
| `requirements.txt` | Added Flask-WTF>=1.2.0, Pillow>=10.0.0 |
| `templates/base.html` | Added CSRF meta tag, CSRF helper JS include |

### Security Utilities

| File | Changes |
|------|---------|
| `utils/security.py` | Added 6 new authorization helpers: address, notification, payment method, report, cart bucket |
| `utils/rate_limit.py` | Rewrote with deferred decorators that work with blueprints |
| `services/audit_service.py` | Added CSRF_FAILURE event type |

### Auth Routes

| File | Changes |
|------|---------|
| `core/blueprints/auth/routes.py` | Added rate limiting imports, applied @limit_login, @limit_registration, @limit_password_reset |

### Account Routes

| File | Changes |
|------|---------|
| `core/blueprints/account/orders_api.py` | Added IDOR protection to order_sellers() and order_items() |

### Cart Routes

| File | Changes |
|------|---------|
| `core/blueprints/cart/routes.py` | Added auth checks to get_cart_sellers() and get_price_breakdown() |

### Bids Routes

| File | Changes |
|------|---------|
| `core/blueprints/bids/api.py` | Added seller verification to get_bidder_info(), requires auth |

### Messages Routes

| File | Changes |
|------|---------|
| `core/blueprints/messages/routes.py` | Added rate limiting import, applied to post_message(), added admin_id validation to 3 admin message routes |

## Summary of Security Controls Added

### CSRF Protection
- Global CSRF protection via Flask-WTF
- CSRF token in meta tag for AJAX
- JavaScript helper auto-adds tokens
- Custom 403 handler with audit logging

### Authorization (IDOR)
- 9 routes fixed with authorization checks
- 6 new authorization helper functions
- Consistent pattern across all blueprints

### Rate Limiting
- Login: 5/min, 20/hour
- Registration: 3/hour
- Password Reset: 3/hour
- Message Send: 30/min

### CSP Tightening
- Added `object-src 'none'`
- Added `upgrade-insecure-requests`
- Explicit CDN whitelist

### File Upload Security
- MIME type validation
- Content validation (image decoding)
- SVG disallowed
- Secure randomized filenames

### Deployment Hardening
- ProxyFix support (BEHIND_PROXY env var)
- Explicit SECURE_COOKIES flag
- Explicit ENABLE_HSTS flag
- Session cookie SameSite=Lax

## Configuration Required

Add to `.env` for production:

```bash
# Security
SECRET_KEY=<generate-with-secrets.token_hex(32)>
SECURE_COOKIES=true
ENABLE_HSTS=true
BEHIND_PROXY=true

# Rate Limiting
RATELIMIT_STORAGE_URL=memory://

# Password Reset
PASSWORD_RESET_TOKEN_EXPIRY_HOURS=1
```

## Testing

Run the security test suite:

```bash
# Run all P0 security tests
pytest tests/test_security_p0.py -v

# Run with coverage
pytest tests/test_security_p0.py -v --cov=utils --cov=core

# Run specific test class
pytest tests/test_security_p0.py::TestCSRFProtection -v
pytest tests/test_security_p0.py::TestIDORProtection -v
```
