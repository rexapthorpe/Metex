-- Migration 010: Add Isolated, Numismatic, and Set Listings Support
-- Adds support for one-of-a-kind items, numismatic issues (X of Y), and set listings (multiple items sold as one)

-- ============================================================
-- 1. Modify listings table to support isolated and numismatic listings
-- ============================================================

-- Add is_isolated flag (whether this listing has its own dedicated bucket)
ALTER TABLE listings ADD COLUMN is_isolated INTEGER NOT NULL DEFAULT 0;

-- Add isolated_type (one_of_a_kind, set, or NULL for non-isolated)
ALTER TABLE listings ADD COLUMN isolated_type TEXT
    CHECK(isolated_type IN ('one_of_a_kind', 'set') OR isolated_type IS NULL);

-- Add issue_number for numismatic items (X in "X out of Y")
ALTER TABLE listings ADD COLUMN issue_number INTEGER;

-- Add issue_total for numismatic items (Y in "X out of Y")
ALTER TABLE listings ADD COLUMN issue_total INTEGER;

-- Add index for querying isolated listings
CREATE INDEX IF NOT EXISTS idx_listings_isolated ON listings(is_isolated, isolated_type);

-- Add index for querying numismatic items
CREATE INDEX IF NOT EXISTS idx_listings_numismatic ON listings(issue_number, issue_total);

-- ============================================================
-- 2. Modify categories table (buckets) to support isolation flag
-- ============================================================

-- Add is_isolated flag to buckets (prevents other listings from joining)
ALTER TABLE categories ADD COLUMN is_isolated INTEGER NOT NULL DEFAULT 0;

-- Add index for filtering out isolated buckets during matching
CREATE INDEX IF NOT EXISTS idx_categories_isolated ON categories(is_isolated);

-- ============================================================
-- 3. Create listing_set_items table (components of a set listing)
-- ============================================================

CREATE TABLE IF NOT EXISTS listing_set_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL,
    position_index INTEGER NOT NULL DEFAULT 0,

    -- Category/spec fields (mirror what defines a normal listing)
    metal TEXT,
    product_line TEXT,
    product_type TEXT,
    weight TEXT,
    purity TEXT,
    mint TEXT,
    year INTEGER,
    finish TEXT,
    grade TEXT,
    coin_series TEXT,
    special_designation TEXT,

    -- Grading info (if applicable to component items)
    graded INTEGER DEFAULT 0,
    grading_service TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (listing_id) REFERENCES listings(id) ON DELETE CASCADE
);

-- Index for fast lookup of set components by parent listing
CREATE INDEX IF NOT EXISTS idx_set_items_listing ON listing_set_items(listing_id);

-- Index for ordering set items within a listing
CREATE INDEX IF NOT EXISTS idx_set_items_position ON listing_set_items(listing_id, position_index);

-- ============================================================
-- 4. Backfill existing data
-- ============================================================

-- Ensure all existing listings are marked as non-isolated
UPDATE listings
SET is_isolated = 0
WHERE is_isolated IS NULL;

-- Ensure all existing buckets are marked as non-isolated
UPDATE categories
SET is_isolated = 0
WHERE is_isolated IS NULL;

-- ============================================================
-- Migration complete
-- ============================================================
