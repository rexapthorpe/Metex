"""
Security Audit Logging Service

Provides structured logging for security-relevant events:
- Authentication events (login, logout, failed login)
- Authorization failures (IDOR attempts)
- Admin actions (user bans, freezes, data changes)
- Sensitive operations (password resets, payment actions)
- Rate limit triggers

Events are stored in the security_audit_log table for compliance and
incident investigation.
"""
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from flask import request, session
from database import get_db_connection

# Set up structured logging
logger = logging.getLogger('security')
logger.setLevel(logging.INFO)

# Create console handler if not already configured
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s SECURITY: %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


# ============================================================================
# Event Types
# ============================================================================

class SecurityEventType:
    """Security event type constants."""
    # Authentication
    LOGIN_SUCCESS = 'login_success'
    LOGIN_FAILED = 'login_failed'
    LOGOUT = 'logout'
    REGISTRATION = 'registration'

    # Password
    PASSWORD_RESET_REQUEST = 'password_reset_request'
    PASSWORD_RESET_SUCCESS = 'password_reset_success'
    PASSWORD_RESET_FAILED = 'password_reset_failed'
    PASSWORD_CHANGED = 'password_changed'

    # Authorization
    UNAUTHORIZED_ACCESS = 'unauthorized_access'
    IDOR_ATTEMPT = 'idor_attempt'
    ADMIN_ACCESS_DENIED = 'admin_access_denied'

    # Admin Actions
    ADMIN_USER_BAN = 'admin_user_ban'
    ADMIN_USER_UNBAN = 'admin_user_unban'
    ADMIN_USER_FREEZE = 'admin_user_freeze'
    ADMIN_USER_UNFREEZE = 'admin_user_unfreeze'
    ADMIN_MAKE_ADMIN = 'admin_make_admin'
    ADMIN_REMOVE_ADMIN = 'admin_remove_admin'
    ADMIN_DATA_DELETE = 'admin_data_delete'
    ADMIN_ORDER_MODIFY = 'admin_order_modify'

    # Rate Limiting
    RATE_LIMIT_EXCEEDED = 'rate_limit_exceeded'

    # CSRF
    CSRF_FAILURE = 'csrf_failure'

    # Suspicious Activity
    SUSPICIOUS_INPUT = 'suspicious_input'
    MULTIPLE_FAILED_LOGINS = 'multiple_failed_logins'

    # Data Access
    SENSITIVE_DATA_ACCESS = 'sensitive_data_access'
    EXPORT_DATA = 'export_data'


# ============================================================================
# Core Logging Functions
# ============================================================================

def log_security_event(
    event_type: str,
    user_id: Optional[int] = None,
    target_user_id: Optional[int] = None,
    target_resource_type: Optional[str] = None,
    target_resource_id: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
    severity: str = 'INFO'
) -> int:
    """
    Log a security event to database and logger.

    Args:
        event_type: Type of security event (use SecurityEventType constants)
        user_id: ID of user performing action (None if unauthenticated)
        target_user_id: ID of user affected by action (for admin actions)
        target_resource_type: Type of resource affected (e.g., 'order', 'listing')
        target_resource_id: ID of affected resource
        details: Additional context as dict
        severity: Log severity level ('INFO', 'WARNING', 'ERROR', 'CRITICAL')

    Returns:
        ID of created audit log entry
    """
    # Get request context
    ip_address = _get_client_ip()
    user_agent = request.headers.get('User-Agent', '')[:500] if request else None
    request_path = request.path if request else None
    request_method = request.method if request else None

    # Get session user if not provided
    if user_id is None and session:
        user_id = session.get('user_id')

    # Serialize details to JSON
    details_json = json.dumps(details) if details else None

    # Log to structured logger
    log_message = (
        f"event={event_type} user_id={user_id} target_user={target_user_id} "
        f"resource={target_resource_type}:{target_resource_id} ip={ip_address}"
    )
    if details:
        log_message += f" details={details_json}"

    log_func = getattr(logger, severity.lower(), logger.info)
    log_func(log_message)

    # Store in database
    try:
        conn = get_db_connection()
        cursor = conn.execute('''
            INSERT INTO security_audit_log (
                event_type, user_id, target_user_id,
                target_resource_type, target_resource_id,
                ip_address, user_agent, request_path, request_method,
                details, severity, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            event_type, user_id, target_user_id,
            target_resource_type, target_resource_id,
            ip_address, user_agent, request_path, request_method,
            details_json, severity, datetime.utcnow().isoformat()
        ))
        log_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return log_id
    except Exception as e:
        # Don't let audit logging failures break the app
        logger.error(f"Failed to write audit log to database: {e}")
        return -1


# ============================================================================
# Convenience Logging Functions
# ============================================================================

def log_login_success(user_id: int, username: str = None):
    """Log successful login."""
    log_security_event(
        SecurityEventType.LOGIN_SUCCESS,
        user_id=user_id,
        details={'username': username}
    )


def log_login_failed(username: str, reason: str = 'invalid_credentials'):
    """Log failed login attempt."""
    log_security_event(
        SecurityEventType.LOGIN_FAILED,
        details={'username': username, 'reason': reason},
        severity='WARNING'
    )


def log_logout(user_id: int):
    """Log user logout."""
    log_security_event(
        SecurityEventType.LOGOUT,
        user_id=user_id
    )


def log_registration(user_id: int, username: str, email: str):
    """Log new user registration."""
    log_security_event(
        SecurityEventType.REGISTRATION,
        user_id=user_id,
        details={'username': username, 'email': _mask_email(email)}
    )


def log_password_reset_request(email: str, user_found: bool):
    """Log password reset request."""
    log_security_event(
        SecurityEventType.PASSWORD_RESET_REQUEST,
        details={'email': _mask_email(email), 'user_found': user_found}
    )


def log_password_reset_success(user_id: int):
    """Log successful password reset."""
    log_security_event(
        SecurityEventType.PASSWORD_RESET_SUCCESS,
        user_id=user_id
    )


def log_password_reset_failed(user_id: int, reason: str):
    """Log failed password reset attempt."""
    log_security_event(
        SecurityEventType.PASSWORD_RESET_FAILED,
        user_id=user_id,
        details={'reason': reason},
        severity='WARNING'
    )


def log_unauthorized_access(
    resource_type: str,
    resource_id: int,
    attempted_action: str
):
    """Log unauthorized access attempt (IDOR)."""
    log_security_event(
        SecurityEventType.IDOR_ATTEMPT,
        target_resource_type=resource_type,
        target_resource_id=resource_id,
        details={'attempted_action': attempted_action},
        severity='WARNING'
    )


def log_admin_action(
    action_type: str,
    target_user_id: int,
    details: Dict[str, Any] = None
):
    """Log admin action for audit trail."""
    log_security_event(
        action_type,
        target_user_id=target_user_id,
        details=details,
        severity='INFO'
    )


def log_rate_limit_exceeded(endpoint: str, limit: str):
    """Log rate limit exceeded event."""
    log_security_event(
        SecurityEventType.RATE_LIMIT_EXCEEDED,
        details={'endpoint': endpoint, 'limit': limit},
        severity='WARNING'
    )


def log_suspicious_input(field: str, value_preview: str, reason: str):
    """Log suspicious input detected."""
    log_security_event(
        SecurityEventType.SUSPICIOUS_INPUT,
        details={
            'field': field,
            'value_preview': value_preview[:100],  # Truncate for safety
            'reason': reason
        },
        severity='WARNING'
    )


# ============================================================================
# Query Functions
# ============================================================================

def get_recent_failed_logins(username: str, minutes: int = 15) -> int:
    """
    Count recent failed login attempts for a username.

    Args:
        username: Username to check
        minutes: Time window to check

    Returns:
        Number of failed login attempts
    """
    try:
        conn = get_db_connection()
        result = conn.execute('''
            SELECT COUNT(*) as count
            FROM security_audit_log
            WHERE event_type = ?
            AND json_extract(details, '$.username') = ?
            AND created_at > datetime('now', ?)
        ''', (
            SecurityEventType.LOGIN_FAILED,
            username,
            f'-{minutes} minutes'
        )).fetchone()
        conn.close()
        return result['count'] if result else 0
    except Exception:
        return 0


def get_user_audit_trail(user_id: int, limit: int = 100) -> list:
    """
    Get audit trail for a specific user.

    Args:
        user_id: User to get trail for
        limit: Maximum records to return

    Returns:
        List of audit log entries
    """
    conn = get_db_connection()
    logs = conn.execute('''
        SELECT * FROM security_audit_log
        WHERE user_id = ? OR target_user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    ''', (user_id, user_id, limit)).fetchall()
    conn.close()
    return [dict(log) for log in logs]


def get_admin_actions(days: int = 30, limit: int = 500) -> list:
    """
    Get all admin actions for audit review.

    Args:
        days: Number of days to look back
        limit: Maximum records to return

    Returns:
        List of admin action audit entries
    """
    conn = get_db_connection()
    logs = conn.execute('''
        SELECT * FROM security_audit_log
        WHERE event_type LIKE 'admin_%'
        AND created_at > datetime('now', ?)
        ORDER BY created_at DESC
        LIMIT ?
    ''', (f'-{days} days', limit)).fetchall()
    conn.close()
    return [dict(log) for log in logs]


# ============================================================================
# Helper Functions
# ============================================================================

def _get_client_ip() -> str:
    """Get the client's real IP address, handling proxies."""
    if not request:
        return 'unknown'

    # Check for forwarded headers (when behind proxy/load balancer)
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        # X-Forwarded-For can be comma-separated list; take the first (client) IP
        return forwarded.split(',')[0].strip()

    # Check for real IP header
    real_ip = request.headers.get('X-Real-IP', '')
    if real_ip:
        return real_ip

    # Fall back to direct connection IP
    return request.remote_addr or 'unknown'


def _mask_email(email: str) -> str:
    """Mask an email address for logging (privacy)."""
    if not email or '@' not in email:
        return '***'

    parts = email.split('@')
    local = parts[0]
    domain = parts[1]

    # Show first 2 chars of local part
    if len(local) > 2:
        local = local[:2] + '***'

    return f"{local}@{domain}"
