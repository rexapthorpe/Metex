-- Migration 009: Add seller_price_each to order_items table
-- This enables the spread model where buyer pays one price and seller receives another
-- DATABASE: database.db (not marketplace.db)

-- Add seller_price_each column to order_items
-- This stores the listing's effective price (what seller receives)
-- while price_each stores the bid's effective price (what buyer pays)
-- STATUS: ✓ APPLIED to database.db on 2025-12-05
ALTER TABLE order_items ADD COLUMN seller_price_each REAL;

-- Backfill existing records: set seller_price_each = price_each for old data
-- This maintains consistency for orders created before the spread model
-- Backfilled 25 existing records on initial run
UPDATE order_items
SET seller_price_each = price_each
WHERE seller_price_each IS NULL;
