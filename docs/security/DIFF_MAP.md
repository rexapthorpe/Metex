# Security Hardening - Diff Map

This document lists all files changed/added as part of the security hardening effort.

## Files Changed

| File | Change Type | Description |
|------|-------------|-------------|
| `core/__init__.py` | Modified | Added security headers middleware, session cookie config, rate limiter init |
| `core/blueprints/auth/routes.py` | Modified | Secure password reset tokens, session regeneration, audit logging |
| `core/blueprints/account/orders_api.py` | Modified | Added IDOR protection with authorization checks |
| `requirements.txt` | Modified | Added Flask-Limiter and bleach security dependencies |

## Files Created

| File | Description |
|------|-------------|
| `utils/security.py` | Core security utilities: token generation, authorization helpers, input validation |
| `utils/rate_limit.py` | Rate limiting configuration and decorators |
| `services/audit_service.py` | Security audit logging service with event types |
| `migrations/024_add_security_tables.sql` | Database tables for password reset tokens and audit log |
| `tests/test_security.py` | 15+ security tests covering headers, sessions, tokens, IDOR |
| `docs/security/SECURITY_HARDENING_PLAN.md` | Prioritized security checklist and implementation guide |
| `docs/security/DIFF_MAP.md` | This file - summary of all changes |

## Summary of Security Improvements

### P0 - Critical (Implemented)

1. **Session Security**
   - HttpOnly, SameSite=Lax cookie flags
   - Session regeneration on login (prevents fixation)
   - Proper session clearing on logout

2. **Password Reset Tokens**
   - Cryptographically random tokens (secrets.token_hex)
   - Tokens stored hashed (SHA-256), never plaintext
   - One-time use enforcement
   - 1-hour expiration (configurable)

3. **Security Headers**
   - X-Frame-Options: SAMEORIGIN
   - X-Content-Type-Options: nosniff
   - Content-Security-Policy (permissive initial policy)
   - Referrer-Policy: strict-origin-when-cross-origin
   - Permissions-Policy (restricts camera, mic, etc.)

4. **Authorization/IDOR Protection**
   - Authorization helper functions in utils/security.py
   - Example fix applied to orders_api.py
   - Pattern documented for other routes

### P1 - High (Frameworks Created)

5. **Rate Limiting Framework**
   - Flask-Limiter integration ready
   - Decorators for login, registration, password reset
   - Configurable via environment variables

6. **Audit Logging**
   - SecurityEventType constants for all event types
   - Structured logging to database and console
   - Helper functions for common events

7. **Input Validation**
   - validate_positive_integer()
   - validate_positive_float()
   - sanitize_string()

## Configuration Required

Add to `.env`:

```bash
# Security
SECRET_KEY=<generate-with-secrets.token_hex(32)>
FLASK_ENV=production  # For secure cookies and HSTS

# Rate Limiting (optional)
RATELIMIT_STORAGE_URL=memory://

# Password Reset
PASSWORD_RESET_TOKEN_EXPIRY_HOURS=1
```

## Database Migration Required

Run the security migration to create required tables:

```bash
sqlite3 data/database.db < migrations/024_add_security_tables.sql
```

## Testing

Run the security test suite:

```bash
pytest tests/test_security.py -v
```

## Routes Requiring IDOR Fixes (Manual Review)

The following routes should be audited and fixed using the pattern in `orders_api.py`:

1. `core/blueprints/account/` - All order-related endpoints
2. `core/blueprints/messages/` - Message thread access
3. `core/blueprints/bids/` - Bid viewing/editing
4. `core/blueprints/listings/` - Listing editing
5. `core/blueprints/checkout/` - Order creation verification

Pattern to apply:
```python
from utils.security import authorize_order_participant, log_unauthorized_access

# At start of route:
try:
    authorize_order_participant(order_id)
except AuthorizationError:
    log_unauthorized_access('order', order_id, 'action_name')
    return jsonify(error="Access denied"), 403
```
