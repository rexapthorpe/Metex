-- Migration 020: Add freeze_reason column to users table
-- This stores the admin's reason for freezing a user account

ALTER TABLE users ADD COLUMN freeze_reason TEXT DEFAULT NULL;
