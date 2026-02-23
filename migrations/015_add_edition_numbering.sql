-- Migration 015: Add Edition Numbering Support
-- Adds edition_number and edition_total columns for limited edition/minted items (#X of #Y)
-- Applies to one-of-a-kind listings and individual set items

-- ============================================================
-- 1. Add edition numbering to listings table (for one-of-a-kind)
-- ============================================================

-- Add edition_number (the specific number of this item, e.g., 4 in "#4 of #100")
ALTER TABLE listings ADD COLUMN edition_number INTEGER CHECK(edition_number >= 1 OR edition_number IS NULL);

-- Add edition_total (the total edition size, e.g., 100 in "#4 of #100")
ALTER TABLE listings ADD COLUMN edition_total INTEGER CHECK(edition_total >= 1 OR edition_total IS NULL);

-- Add index for querying by edition (useful for filtering/searching)
CREATE INDEX IF NOT EXISTS idx_listings_edition ON listings(edition_number, edition_total);

-- ============================================================
-- 2. Add edition numbering to listing_set_items table (for set item components)
-- ============================================================

-- Add edition_number for individual items within a set
ALTER TABLE listing_set_items ADD COLUMN edition_number INTEGER CHECK(edition_number >= 1 OR edition_number IS NULL);

-- Add edition_total for individual items within a set
ALTER TABLE listing_set_items ADD COLUMN edition_total INTEGER CHECK(edition_total >= 1 OR edition_total IS NULL);

-- Add index for querying set items by edition
CREATE INDEX IF NOT EXISTS idx_set_items_edition ON listing_set_items(edition_number, edition_total);

-- ============================================================
-- Migration complete
-- ============================================================
