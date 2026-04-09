-- Migration 030: Add buyer_card_fee to orders table
-- Stores the card processing fee charged to the buyer (2.99% + $0.30 flat) separately
-- from the platform fee and items subtotal. Zero for ACH payments.
-- Idempotent: uses DO $$ block to check column existence before adding.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'orders' AND column_name = 'buyer_card_fee'
    ) THEN
        ALTER TABLE orders ADD COLUMN buyer_card_fee NUMERIC(10,2) NOT NULL DEFAULT 0;
    END IF;
END $$;
