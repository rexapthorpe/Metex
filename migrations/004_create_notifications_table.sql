-- Migration 004: Create notifications table
-- Purpose: Store in-app notifications for users (bid fills, listing sales, etc.)

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    type TEXT NOT NULL,  -- 'bid_filled', 'listing_sold'
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    is_read INTEGER DEFAULT 0,  -- 0 = unread, 1 = read
    related_order_id INTEGER,
    related_bid_id INTEGER,
    related_listing_id INTEGER,
    metadata TEXT,  -- JSON string for additional data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (related_order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (related_bid_id) REFERENCES bids(id) ON DELETE CASCADE,
    FOREIGN KEY (related_listing_id) REFERENCES listings(id) ON DELETE CASCADE
);

-- Index for faster queries by user_id and read status
CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, is_read);
CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at DESC);
