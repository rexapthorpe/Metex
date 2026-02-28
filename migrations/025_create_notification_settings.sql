-- Migration 025: Create notification_settings table
-- Stores per-user, per-type enabled/disabled toggles for in-app notifications.
-- When a row is absent the NOTIFICATION_DEFAULTS in notification_service.py apply.

CREATE TABLE IF NOT EXISTS notification_settings (
    user_id           INTEGER NOT NULL,
    notification_type TEXT    NOT NULL,
    enabled           INTEGER NOT NULL DEFAULT 1,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, notification_type),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_notif_settings_user
    ON notification_settings(user_id);
