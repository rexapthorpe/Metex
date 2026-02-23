-- Migration: Add additional notification preference columns
-- Adds email_price_alerts, email_newsletter, inapp_messages, inapp_price_alerts

-- Add new columns to user_preferences table
ALTER TABLE user_preferences ADD COLUMN email_price_alerts INTEGER DEFAULT 0;
ALTER TABLE user_preferences ADD COLUMN email_newsletter INTEGER DEFAULT 1;
ALTER TABLE user_preferences ADD COLUMN inapp_messages INTEGER DEFAULT 1;
ALTER TABLE user_preferences ADD COLUMN inapp_price_alerts INTEGER DEFAULT 0;
