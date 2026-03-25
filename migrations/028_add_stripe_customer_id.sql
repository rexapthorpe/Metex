-- Migration 028: Add stripe_customer_id to users for buyer payment methods
-- This is separate from stripe_account_id (which is for seller payouts via Stripe Connect).
-- stripe_customer_id ties a buyer to a Stripe Customer object for saved payment methods.

ALTER TABLE users ADD COLUMN stripe_customer_id TEXT;
CREATE INDEX IF NOT EXISTS idx_users_stripe_customer ON users(stripe_customer_id);
