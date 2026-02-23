-- Migration 017: Add packaging fields to listing_set_items
-- Allows each item in a set to have its own packaging specification

ALTER TABLE listing_set_items ADD COLUMN packaging_type TEXT;
ALTER TABLE listing_set_items ADD COLUMN packaging_notes TEXT;
