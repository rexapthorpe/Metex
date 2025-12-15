-- Migration 008: Create bucket_price_history table
--
-- Purpose: Track historical best ask prices for each bucket over time
-- This enables price history charts on bucket pages similar to portfolio charts
--
-- Design decisions:
-- - Store only when best ask price changes (event-driven, not time-based)
-- - Keep up to 1 year of history per bucket
-- - Cleanup of old data handled by periodic job
-- - Index on bucket_id + timestamp for efficient range queries

CREATE TABLE IF NOT EXISTS bucket_price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bucket_id INTEGER NOT NULL,
    best_ask_price REAL NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (bucket_id) REFERENCES categories(bucket_id) ON DELETE CASCADE
);

-- Index for efficient queries by bucket and time range
CREATE INDEX IF NOT EXISTS idx_bucket_price_history_bucket_time
ON bucket_price_history(bucket_id, timestamp DESC);

-- Index for efficient cleanup of old records
CREATE INDEX IF NOT EXISTS idx_bucket_price_history_timestamp
ON bucket_price_history(timestamp);
