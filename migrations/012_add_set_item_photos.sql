-- Migration: Add photo_path to listing_set_items for per-item photos
-- Cover photo for sets will use the existing listing_photos table

ALTER TABLE listing_set_items ADD COLUMN photo_path TEXT;
