-- Migration 014: Add third-party grading support to order_items table
-- This enables the buyer add-on service where coins are shipped directly to grading companies
-- DATABASE: database.db

-- Add third_party_grading_requested column
-- Whether the buyer requested third-party grading service for this order item
ALTER TABLE order_items ADD COLUMN third_party_grading_requested INTEGER DEFAULT 0;

-- Add grading_fee_charged column
-- The total grading fee charged for this line (per unit × quantity)
ALTER TABLE order_items ADD COLUMN grading_fee_charged REAL DEFAULT 0;

-- Add grading_service column
-- The grading service to use (e.g., 'PCGS', 'NGC')
ALTER TABLE order_items ADD COLUMN grading_service TEXT DEFAULT 'PCGS';

-- Add grading_status column
-- Tracks the current status of the grading process
-- Values: 'not_requested', 'pending_seller_ship_to_grader', 'in_transit_to_grader', 'at_grader', 'completed'
ALTER TABLE order_items ADD COLUMN grading_status TEXT DEFAULT 'not_requested';

-- Add seller_tracking_to_grader column
-- Seller's tracking number when shipping to the grading service
ALTER TABLE order_items ADD COLUMN seller_tracking_to_grader TEXT;

-- Update existing records to have consistent default values
UPDATE order_items
SET third_party_grading_requested = 0,
    grading_fee_charged = 0,
    grading_status = 'not_requested'
WHERE third_party_grading_requested IS NULL;
