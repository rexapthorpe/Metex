-- Migration: Create user_preferences table for notification settings
-- This table stores user preferences for email and in-app notifications

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id INTEGER PRIMARY KEY,

    -- Email notification preferences
    email_listing_sold INTEGER DEFAULT 1,  -- Email when listing is sold
    email_bid_filled INTEGER DEFAULT 1,    -- Email when bid is accepted/filled

    -- In-app notification preferences
    inapp_listing_sold INTEGER DEFAULT 1,  -- In-app notification when listing is sold
    inapp_bid_filled INTEGER DEFAULT 1,    -- In-app notification when bid is filled

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Create index for performance
CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id ON user_preferences(user_id);
