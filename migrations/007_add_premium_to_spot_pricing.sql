-- Migration 007: Add Premium-to-Spot Pricing System
-- Adds support for dynamic pricing based on live spot prices

-- ============================================================
-- 1. Create spot_prices table (cache for live metal prices)
-- ============================================================
CREATE TABLE IF NOT EXISTS spot_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metal TEXT NOT NULL UNIQUE,
    price_usd_per_oz REAL NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source TEXT DEFAULT 'metalpriceapi'
);

-- Index for fast metal lookups
CREATE INDEX IF NOT EXISTS idx_spot_prices_metal ON spot_prices(metal);

-- ============================================================
-- 2. Create price_locks table (temporary price guarantees during checkout)
-- ============================================================
CREATE TABLE IF NOT EXISTS price_locks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    locked_price REAL NOT NULL,
    spot_price_at_lock REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    FOREIGN KEY (listing_id) REFERENCES listings(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Index for fast lookup of active locks
CREATE INDEX IF NOT EXISTS idx_price_locks_listing_user ON price_locks(listing_id, user_id);
CREATE INDEX IF NOT EXISTS idx_price_locks_expires ON price_locks(expires_at);

-- ============================================================
-- 3. Modify listings table to support dual pricing modes
-- ============================================================

-- Add pricing_mode column (static or premium_to_spot)
ALTER TABLE listings ADD COLUMN pricing_mode TEXT DEFAULT 'static'
    CHECK(pricing_mode IN ('static', 'premium_to_spot'));

-- Add spot_premium column (USD amount added to spot price)
ALTER TABLE listings ADD COLUMN spot_premium REAL DEFAULT 0;

-- Add floor_price column (minimum price for premium-to-spot mode)
ALTER TABLE listings ADD COLUMN floor_price REAL DEFAULT 0;

-- Add pricing_metal column (metal to use for spot price lookup, may differ from category metal)
ALTER TABLE listings ADD COLUMN pricing_metal TEXT;

-- ============================================================
-- 4. Modify order_items table to preserve pricing snapshot at purchase
-- ============================================================

-- Add price_at_purchase column (actual locked price paid)
ALTER TABLE order_items ADD COLUMN price_at_purchase REAL;

-- Add pricing_mode_at_purchase column (static or premium_to_spot at time of purchase)
ALTER TABLE order_items ADD COLUMN pricing_mode_at_purchase TEXT;

-- Add spot_price_at_purchase column (spot price at time of purchase, for dynamic items)
ALTER TABLE order_items ADD COLUMN spot_price_at_purchase REAL;

-- ============================================================
-- 5. Backfill existing data
-- ============================================================

-- For existing listings: ensure they're marked as static mode
UPDATE listings
SET pricing_mode = 'static'
WHERE pricing_mode IS NULL;

-- For existing order_items: backfill price_at_purchase with price_each
UPDATE order_items
SET price_at_purchase = price_each,
    pricing_mode_at_purchase = 'static'
WHERE price_at_purchase IS NULL;

-- ============================================================
-- 6. Seed initial spot prices (placeholder values)
-- ============================================================
-- These will be replaced by actual API data on first fetch
INSERT OR IGNORE INTO spot_prices (metal, price_usd_per_oz, source) VALUES
    ('gold', 2000.00, 'initial_seed'),
    ('silver', 25.00, 'initial_seed'),
    ('platinum', 950.00, 'initial_seed'),
    ('palladium', 1000.00, 'initial_seed');

-- ============================================================
-- Migration complete
-- ============================================================
