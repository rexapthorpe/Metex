-- Migration 026: Add Stripe Connect fields to users table
-- Enables seller payout onboarding via Stripe Express accounts.

ALTER TABLE users ADD COLUMN stripe_account_id TEXT;
ALTER TABLE users ADD COLUMN stripe_onboarding_complete INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN stripe_charges_enabled INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN stripe_payouts_enabled INTEGER DEFAULT 0;
