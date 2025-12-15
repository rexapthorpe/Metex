-- Migration 011: Add title (name already exists) and description to listings
-- The 'name' field already exists in listings table, so we only need to add description

ALTER TABLE listings ADD COLUMN description TEXT;
