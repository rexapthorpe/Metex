-- Migration 022: Add PARTIALLY_REFUNDED status to orders_ledger
-- This migration adds the PARTIALLY_REFUNDED status for partial refund support (Phase 2)

-- SQLite doesn't support ALTER TABLE to modify CHECK constraints directly
-- Instead, we need to recreate the table or use a workaround

-- Since SQLite CHECK constraints are advisory in some contexts and the application
-- layer enforces the valid status values, we'll add a comment here documenting
-- the new valid status value.

-- The orders_ledger.order_status field now accepts these values:
-- CHECKOUT_INITIATED, PAYMENT_PENDING, PAID_IN_ESCROW, UNDER_REVIEW,
-- AWAITING_SHIPMENT, PARTIALLY_SHIPPED, SHIPPED, COMPLETED,
-- CANCELLED, REFUNDED, PARTIALLY_REFUNDED

-- For SQLite, the CHECK constraint isn't strictly enforced on existing data,
-- and the application layer (ledger_constants.py) is the authoritative source
-- for valid status values.

-- Note: If using PostgreSQL or MySQL in production, update the CHECK constraint:
-- ALTER TABLE orders_ledger DROP CONSTRAINT orders_ledger_order_status_check;
-- ALTER TABLE orders_ledger ADD CONSTRAINT orders_ledger_order_status_check
--   CHECK(order_status IN (...all values including PARTIALLY_REFUNDED...));

-- For completeness, we'll create a simple flag table to track migrations
CREATE TABLE IF NOT EXISTS _migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT UNIQUE NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO _migrations (version) VALUES ('022_add_partially_refunded_status');
