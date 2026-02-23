-- Migration 023: Add payment methods table for saved cards
-- Stores masked card info (never full card numbers)

CREATE TABLE IF NOT EXISTS payment_methods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    card_type TEXT NOT NULL,           -- 'visa', 'mastercard', 'amex', 'discover'
    last_four TEXT NOT NULL,           -- Last 4 digits only
    expiry_month INTEGER NOT NULL,     -- 1-12
    expiry_year INTEGER NOT NULL,      -- 4-digit year
    cardholder_name TEXT NOT NULL,
    is_default INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Index for quick user lookups
CREATE INDEX IF NOT EXISTS idx_payment_methods_user ON payment_methods(user_id);
