-- Migration 022: Add bucket-level platform fee columns
-- This migration adds fee configuration fields to the categories table
-- to allow bucket-level fee customization.

-- Add platform_fee_type column (percent or flat)
ALTER TABLE categories ADD COLUMN platform_fee_type TEXT CHECK(platform_fee_type IN ('percent', 'flat') OR platform_fee_type IS NULL);

-- Add platform_fee_value column
ALTER TABLE categories ADD COLUMN platform_fee_value REAL;

-- Add fee_updated_at timestamp
ALTER TABLE categories ADD COLUMN fee_updated_at TIMESTAMP;

-- Create index for bucket_id lookups
CREATE INDEX IF NOT EXISTS idx_categories_bucket_id ON categories(bucket_id);

-- Create bucket_fee_events table for audit logging
CREATE TABLE IF NOT EXISTS bucket_fee_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bucket_id INTEGER NOT NULL,
    old_fee_type TEXT,
    old_fee_value REAL,
    new_fee_type TEXT NOT NULL,
    new_fee_value REAL NOT NULL,
    admin_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (admin_id) REFERENCES users(id)
);

-- Create index for bucket_fee_events lookups
CREATE INDEX IF NOT EXISTS idx_bucket_fee_events_bucket_id ON bucket_fee_events(bucket_id);
