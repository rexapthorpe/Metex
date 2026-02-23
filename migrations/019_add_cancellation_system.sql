-- Migration 019: Add Order Cancellation System
-- Creates tables for tracking order cancellation requests and seller responses

-- Cancellation Requests table
-- Tracks buyer-initiated cancellation requests
CREATE TABLE IF NOT EXISTS cancellation_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL UNIQUE,
    buyer_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    additional_details TEXT,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'denied')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (buyer_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Cancellation Seller Responses table
-- Tracks individual seller responses (one vote per seller per order)
CREATE TABLE IF NOT EXISTS cancellation_seller_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL,
    seller_id INTEGER NOT NULL,
    response TEXT CHECK(response IN ('approved', 'denied')),
    responded_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (request_id) REFERENCES cancellation_requests(id) ON DELETE CASCADE,
    FOREIGN KEY (seller_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(request_id, seller_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_cancellation_requests_order ON cancellation_requests(order_id);
CREATE INDEX IF NOT EXISTS idx_cancellation_requests_buyer ON cancellation_requests(buyer_id);
CREATE INDEX IF NOT EXISTS idx_cancellation_requests_status ON cancellation_requests(status);
CREATE INDEX IF NOT EXISTS idx_cancellation_seller_responses_request ON cancellation_seller_responses(request_id);
CREATE INDEX IF NOT EXISTS idx_cancellation_seller_responses_seller ON cancellation_seller_responses(seller_id);

-- Add cancellation-related columns to orders table
-- canceled_at: timestamp when order was canceled (if applicable)
-- cancellation_reason: reason for cancellation (stored for analytics)
ALTER TABLE orders ADD COLUMN canceled_at TIMESTAMP;
ALTER TABLE orders ADD COLUMN cancellation_reason TEXT;

-- Add seller_tracking_number to track per-seller tracking (one per seller portion)
-- This allows multi-seller orders where each seller has their own tracking
CREATE TABLE IF NOT EXISTS seller_order_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    seller_id INTEGER NOT NULL,
    tracking_number TEXT,
    carrier TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (seller_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(order_id, seller_id)
);

CREATE INDEX IF NOT EXISTS idx_seller_order_tracking_order ON seller_order_tracking(order_id);
CREATE INDEX IF NOT EXISTS idx_seller_order_tracking_seller ON seller_order_tracking(seller_id);

-- User cancellation statistics (for analytics)
CREATE TABLE IF NOT EXISTS user_cancellation_stats (
    user_id INTEGER PRIMARY KEY,
    canceled_orders_as_buyer INTEGER DEFAULT 0,
    canceled_volume_as_buyer REAL DEFAULT 0,
    canceled_orders_as_seller INTEGER DEFAULT 0,
    canceled_volume_as_seller REAL DEFAULT 0,
    denied_cancellations INTEGER DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
