-- Migration 031: Add spread_capture_amount to ledger tables
--
-- Background: When a buyer's bid price exceeds the seller's ask price, the difference
-- (the "spread") is platform revenue distinct from the percentage/flat platform fee.
-- Without this column, the reconciliation system cannot distinguish a legitimate
-- spread-capture order from a true amount mismatch, causing false AMOUNT_MISMATCH flags.
--
-- Accounting model (post-migration):
--   orders.total_price  = buyer_subtotal + tax + buyer_card_fee
--   buyer_subtotal      = orders_ledger.gross_amount + orders_ledger.spread_capture_amount
--   seller payout basis = orders_ledger.gross_amount  (fee is taken on seller-side only)
--
-- All new columns default to 0 so existing rows reconcile correctly (no spread = no change).

ALTER TABLE orders_ledger
    ADD COLUMN spread_capture_amount REAL NOT NULL DEFAULT 0.0;

ALTER TABLE order_items_ledger
    ADD COLUMN buyer_unit_price REAL DEFAULT NULL;

ALTER TABLE order_items_ledger
    ADD COLUMN spread_per_unit REAL NOT NULL DEFAULT 0.0;

ALTER TABLE order_payouts
    ADD COLUMN spread_capture_amount REAL NOT NULL DEFAULT 0.0;
