-- Migration: Add packaging, condition, series variant, and extended product specifications
-- This migration supports the Random Year system, packaging filters, and buyer-side TPG

-- Add packaging fields to listings table
ALTER TABLE listings ADD COLUMN packaging_type TEXT CHECK(packaging_type IN ('Loose', 'Capsule', 'OGP', 'Tube_Full', 'Tube_Partial', 'MonsterBox_Full', 'MonsterBox_Partial', 'Assay_Card'));
ALTER TABLE listings ADD COLUMN packaging_notes TEXT;

-- Add extended product specification fields to listings table
ALTER TABLE listings ADD COLUMN cert_number TEXT;
ALTER TABLE listings ADD COLUMN condition_notes TEXT;
ALTER TABLE listings ADD COLUMN actual_year TEXT;

-- Add bucket-level specification fields to categories table
ALTER TABLE categories ADD COLUMN condition_category TEXT CHECK(condition_category IN ('BU', 'AU', 'Circulated', 'Cull', 'Random_Condition', 'None'));
ALTER TABLE categories ADD COLUMN series_variant TEXT CHECK(series_variant IN ('None', 'First_Strike', 'Early_Releases', 'First_Day_of_Issue', 'Privy', 'MintDirect'));

-- Add Random Year support to bids table
ALTER TABLE bids ADD COLUMN random_year INTEGER DEFAULT 0;

-- Add third-party grading request to cart table (buyer-side add-on)
ALTER TABLE cart ADD COLUMN third_party_grading_requested INTEGER DEFAULT 0;

-- Add third-party grading and packaging info to order_items table
ALTER TABLE order_items ADD COLUMN third_party_grading_requested INTEGER DEFAULT 0;
ALTER TABLE order_items ADD COLUMN packaging_type TEXT;
ALTER TABLE order_items ADD COLUMN cert_number TEXT;
ALTER TABLE order_items ADD COLUMN condition_notes TEXT;
