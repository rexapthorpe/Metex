-- Migration: Add index for fast category lookups
-- This speeds up the Edit Listing modal save operation

CREATE INDEX IF NOT EXISTS idx_categories_lookup
ON categories (metal, product_line, product_type, weight, purity, mint, year, finish, grade);

-- To run this migration, execute:
-- sqlite3 database.db < migrations/001_add_category_lookup_index.sql
