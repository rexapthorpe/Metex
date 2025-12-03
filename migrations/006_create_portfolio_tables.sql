-- Migration 006: Create Portfolio System Tables
-- This migration creates tables to support portfolio tracking functionality

-- Table: portfolio_exclusions
-- Tracks which order items the user has excluded from their portfolio calculations
CREATE TABLE IF NOT EXISTS portfolio_exclusions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    order_item_id INTEGER NOT NULL,
    excluded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (order_item_id) REFERENCES order_items(id) ON DELETE CASCADE,
    UNIQUE(user_id, order_item_id)
);

-- Table: portfolio_snapshots
-- Stores historical portfolio value data for charting
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    snapshot_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_value REAL NOT NULL,
    total_cost_basis REAL DEFAULT 0,
    snapshot_type TEXT DEFAULT 'auto', -- 'auto', 'daily', 'manual'
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_portfolio_exclusions_user
    ON portfolio_exclusions(user_id);

CREATE INDEX IF NOT EXISTS idx_portfolio_exclusions_order_item
    ON portfolio_exclusions(order_item_id);

CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_user_date
    ON portfolio_snapshots(user_id, snapshot_date DESC);
