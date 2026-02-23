-- Migration 021: Add Ledger Tables for Transaction Tracking and Escrow/Payout State Machine
-- This migration is IDEMPOTENT - safe to run multiple times

-- =====================================================
-- 1. orders_ledger - Main ledger record for each order
-- =====================================================
CREATE TABLE IF NOT EXISTS orders_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER UNIQUE NOT NULL,
    buyer_id INTEGER NOT NULL,
    order_status TEXT NOT NULL DEFAULT 'CHECKOUT_INITIATED' CHECK(order_status IN (
        'CHECKOUT_INITIATED',
        'PAYMENT_PENDING',
        'PAID_IN_ESCROW',
        'UNDER_REVIEW',
        'AWAITING_SHIPMENT',
        'PARTIALLY_SHIPPED',
        'SHIPPED',
        'COMPLETED',
        'CANCELLED',
        'REFUNDED'
    )),
    payment_method TEXT,
    gross_amount REAL NOT NULL,
    platform_fee_amount REAL NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (buyer_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_orders_ledger_order_id ON orders_ledger(order_id);
CREATE INDEX IF NOT EXISTS idx_orders_ledger_buyer_id ON orders_ledger(buyer_id);
CREATE INDEX IF NOT EXISTS idx_orders_ledger_status ON orders_ledger(order_status);
CREATE INDEX IF NOT EXISTS idx_orders_ledger_created_at ON orders_ledger(created_at);


-- =====================================================
-- 2. order_items_ledger - Per-item fee breakdown
-- =====================================================
CREATE TABLE IF NOT EXISTS order_items_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_ledger_id INTEGER NOT NULL,
    order_id INTEGER NOT NULL,
    seller_id INTEGER NOT NULL,
    listing_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    gross_amount REAL NOT NULL,
    fee_type TEXT NOT NULL DEFAULT 'percent' CHECK(fee_type IN ('percent', 'flat')),
    fee_value REAL NOT NULL DEFAULT 0,
    fee_amount REAL NOT NULL DEFAULT 0,
    seller_net_amount REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_ledger_id) REFERENCES orders_ledger(id) ON DELETE CASCADE,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (seller_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (listing_id) REFERENCES listings(id) ON DELETE CASCADE
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_order_items_ledger_order_ledger_id ON order_items_ledger(order_ledger_id);
CREATE INDEX IF NOT EXISTS idx_order_items_ledger_order_id ON order_items_ledger(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_ledger_seller_id ON order_items_ledger(seller_id);
CREATE INDEX IF NOT EXISTS idx_order_items_ledger_listing_id ON order_items_ledger(listing_id);


-- =====================================================
-- 3. order_payouts - Per-seller payout tracking
-- =====================================================
CREATE TABLE IF NOT EXISTS order_payouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_ledger_id INTEGER NOT NULL,
    order_id INTEGER NOT NULL,
    seller_id INTEGER NOT NULL,
    payout_status TEXT NOT NULL DEFAULT 'PAYOUT_NOT_READY' CHECK(payout_status IN (
        'PAYOUT_NOT_READY',
        'PAYOUT_READY',
        'PAYOUT_ON_HOLD',
        'PAYOUT_SCHEDULED',
        'PAYOUT_IN_PROGRESS',
        'PAID_OUT',
        'PAYOUT_CANCELLED'
    )),
    seller_gross_amount REAL NOT NULL,
    fee_amount REAL NOT NULL DEFAULT 0,
    seller_net_amount REAL NOT NULL,
    scheduled_for TIMESTAMP,
    provider_transfer_id TEXT,
    provider_payout_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_ledger_id) REFERENCES orders_ledger(id) ON DELETE CASCADE,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (seller_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(order_ledger_id, seller_id)
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_order_payouts_order_ledger_id ON order_payouts(order_ledger_id);
CREATE INDEX IF NOT EXISTS idx_order_payouts_order_id ON order_payouts(order_id);
CREATE INDEX IF NOT EXISTS idx_order_payouts_seller_id ON order_payouts(seller_id);
CREATE INDEX IF NOT EXISTS idx_order_payouts_status ON order_payouts(payout_status);
CREATE INDEX IF NOT EXISTS idx_order_payouts_scheduled ON order_payouts(scheduled_for);


-- =====================================================
-- 4. order_events - Audit trail for order lifecycle
-- =====================================================
CREATE TABLE IF NOT EXISTS order_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK(actor_type IN ('system', 'admin', 'buyer', 'seller', 'payment_provider')),
    actor_id INTEGER,
    payload_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
);

-- Indexes for fast lookups and event ordering
CREATE INDEX IF NOT EXISTS idx_order_events_order_id ON order_events(order_id);
CREATE INDEX IF NOT EXISTS idx_order_events_type ON order_events(event_type);
CREATE INDEX IF NOT EXISTS idx_order_events_created_at ON order_events(created_at);
CREATE INDEX IF NOT EXISTS idx_order_events_order_created ON order_events(order_id, created_at);


-- =====================================================
-- 5. Fee Configuration Table (for future extensibility)
-- =====================================================
CREATE TABLE IF NOT EXISTS fee_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_key TEXT UNIQUE NOT NULL,
    fee_type TEXT NOT NULL DEFAULT 'percent' CHECK(fee_type IN ('percent', 'flat')),
    fee_value REAL NOT NULL DEFAULT 0,
    description TEXT,
    active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default platform fee (2.5%)
INSERT OR IGNORE INTO fee_config (config_key, fee_type, fee_value, description)
VALUES ('default_platform_fee', 'percent', 2.5, 'Default platform fee applied to all transactions');
