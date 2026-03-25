-- Migration 027: Add payment_status and payout_status to orders table
-- Enables fine-grained payment lifecycle tracking and payout-readiness visibility.
-- Neither field triggers any fund movement — they are status flags only.

ALTER TABLE orders ADD COLUMN payment_status TEXT NOT NULL DEFAULT 'unpaid';
ALTER TABLE orders ADD COLUMN payout_status TEXT NOT NULL DEFAULT 'not_ready_for_payout';
