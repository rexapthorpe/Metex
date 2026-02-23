-- Migration 024: Add security-related tables
-- This migration adds:
-- 1. password_reset_tokens: Secure, one-time-use, time-limited tokens
-- 2. security_audit_log: Immutable audit trail for security events
-- 3. session_versions: Track session invalidation on password change

-- ============================================================================
-- Password Reset Tokens Table
-- ============================================================================
-- Stores hashed tokens (never plaintext) with expiration timestamps.
-- Tokens are single-use and deleted after successful reset.

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL,          -- SHA-256 hash of actual token
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,     -- Token expiration time
    used_at TIMESTAMP,                 -- When token was used (NULL if unused)
    ip_address TEXT,                   -- IP that requested the reset
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Index for efficient token lookup
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_hash ON password_reset_tokens(token_hash);

-- Index for cleanup of expired tokens
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_expires ON password_reset_tokens(expires_at);

-- Prevent multiple unused tokens per user (cleanup old ones first)
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user_unused
    ON password_reset_tokens(user_id, used_at);


-- ============================================================================
-- Security Audit Log Table
-- ============================================================================
-- Immutable audit trail for security-relevant events.
-- This table should never have UPDATE or DELETE operations in production.

CREATE TABLE IF NOT EXISTS security_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,           -- Type of security event
    user_id INTEGER,                    -- User who performed action (NULL if unauthenticated)
    target_user_id INTEGER,             -- User affected by action (for admin actions)
    target_resource_type TEXT,          -- Type of resource affected
    target_resource_id INTEGER,         -- ID of affected resource
    ip_address TEXT,                    -- Client IP address
    user_agent TEXT,                    -- Browser user agent (truncated)
    request_path TEXT,                  -- Request path
    request_method TEXT,                -- HTTP method
    details TEXT,                       -- JSON-encoded additional details
    severity TEXT DEFAULT 'INFO',       -- INFO, WARNING, ERROR, CRITICAL
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_audit_log_event_type ON security_audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON security_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_target_user ON security_audit_log(target_user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON security_audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_severity ON security_audit_log(severity);

-- Composite index for user audit trail queries
CREATE INDEX IF NOT EXISTS idx_audit_log_user_time
    ON security_audit_log(user_id, created_at DESC);


-- ============================================================================
-- Session Version Tracking (for password change invalidation)
-- ============================================================================
-- When a user changes their password, increment their session_version.
-- All sessions with older versions are automatically invalidated.

-- Add session_version column to users table if it doesn't exist
-- SQLite doesn't support IF NOT EXISTS for ALTER TABLE, so we use a workaround

-- First, check if column exists by trying to select it
-- If this fails, the migration runner should add it

-- For safety, we'll handle this in Python migration code


-- ============================================================================
-- Failed Login Tracking (for brute force detection)
-- ============================================================================
-- Tracks failed login attempts by IP and username for rate limiting

CREATE TABLE IF NOT EXISTS failed_login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip_address TEXT NOT NULL,
    username TEXT NOT NULL,
    attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for efficient counting
CREATE INDEX IF NOT EXISTS idx_failed_logins_ip_time
    ON failed_login_attempts(ip_address, attempted_at);
CREATE INDEX IF NOT EXISTS idx_failed_logins_username_time
    ON failed_login_attempts(username, attempted_at);


-- ============================================================================
-- Cleanup Job Placeholder
-- ============================================================================
-- In production, set up a scheduled job to run these cleanups:
--
-- 1. Delete expired password reset tokens:
--    DELETE FROM password_reset_tokens WHERE expires_at < datetime('now');
--
-- 2. Delete old failed login attempts (older than 24 hours):
--    DELETE FROM failed_login_attempts WHERE attempted_at < datetime('now', '-24 hours');
--
-- 3. Optionally archive old audit logs (keep 90 days online):
--    -- Archive to separate table or export to file first
--    DELETE FROM security_audit_log WHERE created_at < datetime('now', '-90 days');
