-- Migration 029: Add delivered_at to seller_order_tracking
-- Supports delivery-based payout eligibility (admin marks shipment as delivered).

ALTER TABLE seller_order_tracking
    ADD COLUMN delivered_at TIMESTAMP DEFAULT NULL;
