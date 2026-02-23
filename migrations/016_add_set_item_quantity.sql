-- Migration 016: Add quantity column to listing_set_items
-- This allows each item in a set to have its own quantity

ALTER TABLE listing_set_items ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1;
