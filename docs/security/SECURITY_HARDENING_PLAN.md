# Metex Security Hardening Plan

## Executive Summary

This document outlines the comprehensive security hardening for the Metex Flask application. Vulnerabilities are prioritized as P0 (critical, deploy blockers), P1 (high, fix before production), and P2 (medium, fix in near term).

---

## Prioritized Security Checklist

### P0 - Critical (Deploy Blockers)

| # | Issue | Rationale | Files to Modify |
|---|-------|-----------|-----------------|
| 1 | **Weak password reset tokens** | Tokens are deterministic (user_id + hardcoded secret). Attacker can calculate any user's reset token. | `core/blueprints/auth/routes.py` |
| 2 | **Plaintext password storage** | Both `password` and `password_hash` columns store the hash, but schema implies plaintext. | `core/blueprints/auth/routes.py`, migration |
| 3 | **No CSRF protection** | All POST routes vulnerable to cross-site request forgery. | `core/__init__.py`, all templates |
| 4 | **Session not regenerated on login** | Session fixation attack possible. | `core/blueprints/auth/routes.py` |
| 5 | **Missing authorization checks (IDOR)** | Routes accept IDs without verifying ownership. | Multiple route files |
| 6 | **Debug mode in production** | Stack traces and debugger exposed. | `app.py` |
| 7 | **Insecure cookie settings** | Missing HttpOnly, Secure, SameSite flags. | `core/__init__.py` |

### P1 - High (Fix Before Production)

| # | Issue | Rationale | Files to Modify |
|---|-------|-----------|-----------------|
| 8 | **No rate limiting** | Brute force, credential stuffing, spam attacks possible. | New middleware |
| 9 | **Missing security headers** | XSS, clickjacking, MIME sniffing attacks possible. | `core/__init__.py` |
| 10 | **No audit logging** | Cannot detect or investigate security incidents. | New service |
| 11 | **Weak input validation** | Type errors, negative values can crash or exploit app. | Multiple route files |
| 12 | **File upload risks** | Extension-only validation, no size limits in some routes. | `core/blueprints/sell/routes.py` |
| 13 | **SQL string interpolation** | CLI commands use f-strings for table names. | `core/__init__.py` |

### P2 - Medium (Fix in Near Term)

| # | Issue | Rationale | Files to Modify |
|---|-------|-----------|-----------------|
| 14 | **No 2FA capability** | Account takeover easier without MFA option. | New module |
| 15 | **Password complexity not enforced** | Only 8-char minimum, no complexity rules. | `core/blueprints/auth/routes.py` |
| 16 | **Session version for password changes** | Old sessions remain valid after password change. | Auth module |
| 17 | **Admin audit trail** | Admin actions not logged to immutable store. | New table/service |
| 18 | **Dependency scanning** | No automated vulnerability scanning. | CI/CD config |

---

## Implementation Details

### 1. New Dependencies Required

Add to `requirements.txt`:

```
Flask-WTF>=1.2.0
Flask-Limiter>=3.5.0
bleach>=6.0.0
argon2-cffi>=23.1.0
```

### 2. New Environment Variables

Add to `.env.example`:

```bash
# Security Configuration
SECRET_KEY=<generate-with-secrets.token_hex(32)>
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_HTTPONLY=true
SESSION_COOKIE_SAMESITE=Lax

# Rate Limiting
RATELIMIT_STORAGE_URL=memory://
RATELIMIT_DEFAULT=200/hour
RATELIMIT_LOGIN=5/minute
RATELIMIT_REGISTER=3/hour
RATELIMIT_PASSWORD_RESET=3/hour

# Password Reset
PASSWORD_RESET_TOKEN_EXPIRY_HOURS=1
```

---

## New Files to Create

1. `utils/security.py` - Security utilities (token generation, authorization helpers)
2. `utils/rate_limit.py` - Rate limiting configuration
3. `services/audit_service.py` - Security audit logging
4. `migrations/024_add_security_tables.sql` - Password reset tokens, audit log tables
5. `tests/test_security.py` - Security test suite

---

## Deployment Hardening (Render/Hosting)

### Environment Variables (Required)

```bash
# Generate a strong secret key
python -c "import secrets; print(secrets.token_hex(32))"

# Set in Render dashboard:
SECRET_KEY=<generated-key>
FLASK_ENV=production
SESSION_COOKIE_SECURE=true
```

### HTTPS Configuration

- Enable "Force HTTPS" in Render dashboard
- Set HSTS header only after confirming HTTPS works

### Database Security

- Use PostgreSQL instead of SQLite for production
- Enable SSL connections to database
- Use environment variable for DATABASE_URL
- Enable automated backups

### Additional Render Settings

- Set health check endpoint: `/diagnostic/upload-limits`
- Configure log retention (at least 30 days)
- Enable DDoS protection if available
