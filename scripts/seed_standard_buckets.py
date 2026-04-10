"""
Seed and sync standard_buckets table.

Usage:
    python scripts/seed_standard_buckets.py [--sync-categories] [--dry-run]

What this does:
  1. Inserts ~63 curated standard precious-metals products (idempotent by slug).
  2. Optionally (--sync-categories) auto-imports non-isolated categories from the
     categories table into standard_buckets, matching by inferred slug.

Safe to run multiple times — uses slug as unique key, skips existing rows.
"""

import argparse
import sys
import os

# Ensure project root is on path when run as a script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database
import services.bucket_image_service as bis


# ---------------------------------------------------------------------------
# Curated seed catalog — ~45 most-traded standard precious-metals products
# ---------------------------------------------------------------------------

SEED_PRODUCTS = [
    # ── GOLD COINS ────────────────────────────────────────────────────────
    {
        'slug': 'gold-american-eagle-1oz',
        'title': '1 oz American Gold Eagle Coin',
        'metal': 'Gold', 'form': 'coin',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': 'United States Mint', 'denomination': '$50',
        'product_family': 'American Gold Eagle', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9167',
    },
    {
        'slug': 'gold-american-eagle-half-oz',
        'title': '1/2 oz American Gold Eagle Coin',
        'metal': 'Gold', 'form': 'coin',
        'weight': '1/2 oz', 'weight_oz': 0.5,
        'mint': 'United States Mint', 'denomination': '$25',
        'product_family': 'American Gold Eagle', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9167',
    },
    {
        'slug': 'gold-american-eagle-quarter-oz',
        'title': '1/4 oz American Gold Eagle Coin',
        'metal': 'Gold', 'form': 'coin',
        'weight': '1/4 oz', 'weight_oz': 0.25,
        'mint': 'United States Mint', 'denomination': '$10',
        'product_family': 'American Gold Eagle', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9167',
    },
    {
        'slug': 'gold-american-eagle-tenth-oz',
        'title': '1/10 oz American Gold Eagle Coin',
        'metal': 'Gold', 'form': 'coin',
        'weight': '1/10 oz', 'weight_oz': 0.1,
        'mint': 'United States Mint', 'denomination': '$5',
        'product_family': 'American Gold Eagle', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9167',
    },
    {
        'slug': 'gold-american-buffalo-1oz',
        'title': '1 oz American Gold Buffalo Coin',
        'metal': 'Gold', 'form': 'coin',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': 'United States Mint', 'denomination': '$50',
        'product_family': 'American Gold Buffalo', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9999',
    },
    {
        'slug': 'gold-canadian-maple-leaf-1oz',
        'title': '1 oz Canadian Gold Maple Leaf Coin',
        'metal': 'Gold', 'form': 'coin',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': 'Royal Canadian Mint', 'denomination': '$50 CAD',
        'product_family': 'Gold Maple Leaf', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9999',
    },
    {
        'slug': 'gold-krugerrand-1oz',
        'title': '1 oz South African Gold Krugerrand Coin',
        'metal': 'Gold', 'form': 'coin',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': 'South African Mint', 'denomination': None,
        'product_family': 'Krugerrand', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9167',
    },
    {
        'slug': 'gold-austrian-philharmonic-1oz',
        'title': '1 oz Austrian Gold Philharmonic Coin',
        'metal': 'Gold', 'form': 'coin',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': 'Austrian Mint', 'denomination': '100 Euro',
        'product_family': 'Gold Philharmonic', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9999',
    },
    {
        'slug': 'gold-australian-kangaroo-1oz',
        'title': '1 oz Australian Gold Kangaroo Coin',
        'metal': 'Gold', 'form': 'coin',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': 'Perth Mint', 'denomination': '$100 AUD',
        'product_family': 'Gold Kangaroo', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9999',
    },
    {
        'slug': 'gold-british-britannia-1oz',
        'title': '1 oz British Gold Britannia Coin',
        'metal': 'Gold', 'form': 'coin',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': 'Royal Mint', 'denomination': '£100',
        'product_family': 'Gold Britannia', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9999',
    },
    {
        'slug': 'gold-chinese-panda-1oz',
        'title': '1 oz Chinese Gold Panda Coin',
        'metal': 'Gold', 'form': 'coin',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': 'China Gold Coin', 'denomination': '500 Yuan',
        'product_family': 'Gold Panda', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.999',
    },
    {
        'slug': 'gold-mexican-libertad-1oz',
        'title': '1 oz Mexican Gold Libertad Coin',
        'metal': 'Gold', 'form': 'coin',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': 'Mexican Mint', 'denomination': None,
        'product_family': 'Gold Libertad', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.999',
    },

    # ── GOLD BARS ─────────────────────────────────────────────────────────
    {
        'slug': 'gold-bar-1g',
        'title': '1 g Gold Bar',
        'metal': 'Gold', 'form': 'bar',
        'weight': '1 g', 'weight_oz': 0.032,
        'mint': None, 'denomination': None,
        'product_family': 'Gold Bar', 'product_series': None,
        'year_policy': 'varies', 'purity': '.9999',
    },
    {
        'slug': 'gold-bar-5g',
        'title': '5 g Gold Bar',
        'metal': 'Gold', 'form': 'bar',
        'weight': '5 g', 'weight_oz': 0.161,
        'mint': None, 'denomination': None,
        'product_family': 'Gold Bar', 'product_series': None,
        'year_policy': 'varies', 'purity': '.9999',
    },
    {
        'slug': 'gold-bar-10g',
        'title': '10 g Gold Bar',
        'metal': 'Gold', 'form': 'bar',
        'weight': '10 g', 'weight_oz': 0.321,
        'mint': None, 'denomination': None,
        'product_family': 'Gold Bar', 'product_series': None,
        'year_policy': 'varies', 'purity': '.9999',
    },
    {
        'slug': 'gold-bar-1oz',
        'title': '1 oz Gold Bar',
        'metal': 'Gold', 'form': 'bar',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': None, 'denomination': None,
        'product_family': 'Gold Bar', 'product_series': None,
        'year_policy': 'varies', 'purity': '.9999',
    },
    {
        'slug': 'gold-bar-10oz',
        'title': '10 oz Gold Bar',
        'metal': 'Gold', 'form': 'bar',
        'weight': '10 oz', 'weight_oz': 10.0,
        'mint': None, 'denomination': None,
        'product_family': 'Gold Bar', 'product_series': None,
        'year_policy': 'varies', 'purity': '.9999',
    },
    {
        'slug': 'gold-bar-1kg',
        'title': '1 kg Gold Bar',
        'metal': 'Gold', 'form': 'bar',
        'weight': '1 kg', 'weight_oz': 32.15,
        'mint': None, 'denomination': None,
        'product_family': 'Gold Bar', 'product_series': None,
        'year_policy': 'varies', 'purity': '.9999',
    },

    # ── SILVER COINS ──────────────────────────────────────────────────────
    {
        'slug': 'silver-american-eagle-1oz',
        'title': '1 oz American Silver Eagle Coin',
        'metal': 'Silver', 'form': 'coin',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': 'United States Mint', 'denomination': '$1',
        'product_family': 'American Silver Eagle', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.999',
    },
    {
        'slug': 'silver-canadian-maple-leaf-1oz',
        'title': '1 oz Canadian Silver Maple Leaf Coin',
        'metal': 'Silver', 'form': 'coin',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': 'Royal Canadian Mint', 'denomination': '$5 CAD',
        'product_family': 'Silver Maple Leaf', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9999',
    },
    {
        'slug': 'silver-austrian-philharmonic-1oz',
        'title': '1 oz Austrian Silver Philharmonic Coin',
        'metal': 'Silver', 'form': 'coin',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': 'Austrian Mint', 'denomination': '1.50 Euro',
        'product_family': 'Silver Philharmonic', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.999',
    },
    {
        'slug': 'silver-australian-kangaroo-1oz',
        'title': '1 oz Australian Silver Kangaroo Coin',
        'metal': 'Silver', 'form': 'coin',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': 'Perth Mint', 'denomination': '$1 AUD',
        'product_family': 'Silver Kangaroo', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.999',
    },
    {
        'slug': 'silver-british-britannia-1oz',
        'title': '1 oz British Silver Britannia Coin',
        'metal': 'Silver', 'form': 'coin',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': 'Royal Mint', 'denomination': '£2',
        'product_family': 'Silver Britannia', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.999',
    },
    {
        'slug': 'silver-south-african-krugerrand-1oz',
        'title': '1 oz South African Silver Krugerrand Coin',
        'metal': 'Silver', 'form': 'coin',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': 'South African Mint', 'denomination': None,
        'product_family': 'Silver Krugerrand', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.999',
    },
    {
        'slug': 'silver-mexican-libertad-1oz',
        'title': '1 oz Mexican Silver Libertad Coin',
        'metal': 'Silver', 'form': 'coin',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': 'Mexican Mint', 'denomination': None,
        'product_family': 'Silver Libertad', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.999',
    },
    {
        'slug': 'silver-round-generic-1oz',
        'title': '1 oz Silver Round (.999)',
        'metal': 'Silver', 'form': 'round',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': None, 'denomination': None,
        'product_family': 'Silver Round', 'product_series': None,
        'year_policy': 'varies', 'purity': '.999',
    },
    {
        'slug': 'silver-morgan-dollar',
        'title': 'Morgan Silver Dollar (90% Silver)',
        'metal': 'Silver', 'form': 'coin',
        'weight': '0.77 oz', 'weight_oz': 0.7734,
        'mint': 'United States Mint', 'denomination': '$1',
        'product_family': 'Morgan Dollar', 'product_series': 'Classic US Coinage',
        'year_policy': 'varies', 'purity': '.900',
    },
    {
        'slug': 'silver-peace-dollar',
        'title': 'Peace Silver Dollar (90% Silver)',
        'metal': 'Silver', 'form': 'coin',
        'weight': '0.77 oz', 'weight_oz': 0.7734,
        'mint': 'United States Mint', 'denomination': '$1',
        'product_family': 'Peace Dollar', 'product_series': 'Classic US Coinage',
        'year_policy': 'varies', 'purity': '.900',
    },

    # ── SILVER BARS ───────────────────────────────────────────────────────
    {
        'slug': 'silver-bar-1oz',
        'title': '1 oz Silver Bar',
        'metal': 'Silver', 'form': 'bar',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': None, 'denomination': None,
        'product_family': 'Silver Bar', 'product_series': None,
        'year_policy': 'varies', 'purity': '.999',
    },
    {
        'slug': 'silver-bar-5oz',
        'title': '5 oz Silver Bar',
        'metal': 'Silver', 'form': 'bar',
        'weight': '5 oz', 'weight_oz': 5.0,
        'mint': None, 'denomination': None,
        'product_family': 'Silver Bar', 'product_series': None,
        'year_policy': 'varies', 'purity': '.999',
    },
    {
        'slug': 'silver-bar-10oz',
        'title': '10 oz Silver Bar',
        'metal': 'Silver', 'form': 'bar',
        'weight': '10 oz', 'weight_oz': 10.0,
        'mint': None, 'denomination': None,
        'product_family': 'Silver Bar', 'product_series': None,
        'year_policy': 'varies', 'purity': '.999',
    },
    {
        'slug': 'silver-bar-100oz',
        'title': '100 oz Silver Bar',
        'metal': 'Silver', 'form': 'bar',
        'weight': '100 oz', 'weight_oz': 100.0,
        'mint': None, 'denomination': None,
        'product_family': 'Silver Bar', 'product_series': None,
        'year_policy': 'varies', 'purity': '.999',
    },
    {
        'slug': 'silver-bar-1kg',
        'title': '1 kg Silver Bar',
        'metal': 'Silver', 'form': 'bar',
        'weight': '1 kg', 'weight_oz': 32.15,
        'mint': None, 'denomination': None,
        'product_family': 'Silver Bar', 'product_series': None,
        'year_policy': 'varies', 'purity': '.999',
    },

    # ── PLATINUM ──────────────────────────────────────────────────────────
    {
        'slug': 'platinum-american-eagle-1oz',
        'title': '1 oz American Platinum Eagle Coin',
        'metal': 'Platinum', 'form': 'coin',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': 'United States Mint', 'denomination': '$100',
        'product_family': 'American Platinum Eagle', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9995',
    },
    {
        'slug': 'platinum-canadian-maple-leaf-1oz',
        'title': '1 oz Canadian Platinum Maple Leaf Coin',
        'metal': 'Platinum', 'form': 'coin',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': 'Royal Canadian Mint', 'denomination': '$50 CAD',
        'product_family': 'Platinum Maple Leaf', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9995',
    },
    {
        'slug': 'platinum-bar-1oz',
        'title': '1 oz Platinum Bar',
        'metal': 'Platinum', 'form': 'bar',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': None, 'denomination': None,
        'product_family': 'Platinum Bar', 'product_series': None,
        'year_policy': 'varies', 'purity': '.9995',
    },

    # ── PALLADIUM ─────────────────────────────────────────────────────────
    {
        'slug': 'palladium-american-eagle-1oz',
        'title': '1 oz American Palladium Eagle Coin',
        'metal': 'Palladium', 'form': 'coin',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': 'United States Mint', 'denomination': '$25',
        'product_family': 'American Palladium Eagle', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9995',
    },
    {
        'slug': 'palladium-canadian-maple-leaf-1oz',
        'title': '1 oz Canadian Palladium Maple Leaf Coin',
        'metal': 'Palladium', 'form': 'coin',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': 'Royal Canadian Mint', 'denomination': '$50 CAD',
        'product_family': 'Palladium Maple Leaf', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9995',
    },
    {
        'slug': 'palladium-bar-1oz',
        'title': '1 oz Palladium Bar',
        'metal': 'Palladium', 'form': 'bar',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': None, 'denomination': None,
        'product_family': 'Palladium Bar', 'product_series': None,
        'year_policy': 'varies', 'purity': '.9995',
    },

    # ── COPPER ────────────────────────────────────────────────────────────
    {
        'slug': 'copper-round-1oz',
        'title': '1 oz Copper Round (.999)',
        'metal': 'Copper', 'form': 'round',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': None, 'denomination': None,
        'product_family': 'Copper Round', 'product_series': None,
        'year_policy': 'varies', 'purity': '.999',
    },
    {
        'slug': 'copper-bar-1oz',
        'title': '1 oz Copper Bar (.999)',
        'metal': 'Copper', 'form': 'bar',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': None, 'denomination': None,
        'product_family': 'Copper Bar', 'product_series': None,
        'year_policy': 'varies', 'purity': '.999',
    },
    {
        'slug': 'copper-bar-1lb',
        'title': '1 lb Copper Bar (.999)',
        'metal': 'Copper', 'form': 'bar',
        'weight': '1 lb', 'weight_oz': 16.0,
        'mint': None, 'denomination': None,
        'product_family': 'Copper Bar', 'product_series': None,
        'year_policy': 'varies', 'purity': '.999',
    },

    # ── GOLD COINS — ADDITIONAL SIZES ─────────────────────────────────────
    {
        'slug': 'gold-krugerrand-half-oz',
        'title': '1/2 oz South African Gold Krugerrand Coin',
        'metal': 'Gold', 'form': 'coin',
        'weight': '1/2 oz', 'weight_oz': 0.5,
        'mint': 'South African Mint', 'denomination': None,
        'product_family': 'Krugerrand', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9167',
    },
    {
        'slug': 'gold-krugerrand-quarter-oz',
        'title': '1/4 oz South African Gold Krugerrand Coin',
        'metal': 'Gold', 'form': 'coin',
        'weight': '1/4 oz', 'weight_oz': 0.25,
        'mint': 'South African Mint', 'denomination': None,
        'product_family': 'Krugerrand', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9167',
    },
    {
        'slug': 'gold-krugerrand-tenth-oz',
        'title': '1/10 oz South African Gold Krugerrand Coin',
        'metal': 'Gold', 'form': 'coin',
        'weight': '1/10 oz', 'weight_oz': 0.1,
        'mint': 'South African Mint', 'denomination': None,
        'product_family': 'Krugerrand', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9167',
    },
    {
        'slug': 'gold-canadian-maple-leaf-half-oz',
        'title': '1/2 oz Canadian Gold Maple Leaf Coin',
        'metal': 'Gold', 'form': 'coin',
        'weight': '1/2 oz', 'weight_oz': 0.5,
        'mint': 'Royal Canadian Mint', 'denomination': '$20 CAD',
        'product_family': 'Gold Maple Leaf', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9999',
    },
    {
        'slug': 'gold-canadian-maple-leaf-quarter-oz',
        'title': '1/4 oz Canadian Gold Maple Leaf Coin',
        'metal': 'Gold', 'form': 'coin',
        'weight': '1/4 oz', 'weight_oz': 0.25,
        'mint': 'Royal Canadian Mint', 'denomination': '$10 CAD',
        'product_family': 'Gold Maple Leaf', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9999',
    },
    {
        'slug': 'gold-canadian-maple-leaf-tenth-oz',
        'title': '1/10 oz Canadian Gold Maple Leaf Coin',
        'metal': 'Gold', 'form': 'coin',
        'weight': '1/10 oz', 'weight_oz': 0.1,
        'mint': 'Royal Canadian Mint', 'denomination': '$5 CAD',
        'product_family': 'Gold Maple Leaf', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9999',
    },
    {
        'slug': 'gold-australian-kangaroo-half-oz',
        'title': '1/2 oz Australian Gold Kangaroo Coin',
        'metal': 'Gold', 'form': 'coin',
        'weight': '1/2 oz', 'weight_oz': 0.5,
        'mint': 'Perth Mint', 'denomination': '$50 AUD',
        'product_family': 'Gold Kangaroo', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9999',
    },

    # ── GOLD BARS — ADDITIONAL SIZES ──────────────────────────────────────
    {
        'slug': 'gold-bar-2-5g',
        'title': '2.5 g Gold Bar',
        'metal': 'Gold', 'form': 'bar',
        'weight': '2.5 g', 'weight_oz': 0.080,
        'mint': None, 'denomination': None,
        'product_family': 'Gold Bar', 'product_series': None,
        'year_policy': 'varies', 'purity': '.9999',
    },
    {
        'slug': 'gold-bar-quarter-oz',
        'title': '1/4 oz Gold Bar',
        'metal': 'Gold', 'form': 'bar',
        'weight': '1/4 oz', 'weight_oz': 0.25,
        'mint': None, 'denomination': None,
        'product_family': 'Gold Bar', 'product_series': None,
        'year_policy': 'varies', 'purity': '.9999',
    },

    # ── PLATINUM — ADDITIONAL SIZES ───────────────────────────────────────
    {
        'slug': 'platinum-american-eagle-quarter-oz',
        'title': '1/4 oz American Platinum Eagle Coin',
        'metal': 'Platinum', 'form': 'coin',
        'weight': '1/4 oz', 'weight_oz': 0.25,
        'mint': 'United States Mint', 'denomination': '$25',
        'product_family': 'American Platinum Eagle', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9995',
    },
    {
        'slug': 'platinum-american-eagle-tenth-oz',
        'title': '1/10 oz American Platinum Eagle Coin',
        'metal': 'Platinum', 'form': 'coin',
        'weight': '1/10 oz', 'weight_oz': 0.1,
        'mint': 'United States Mint', 'denomination': '$10',
        'product_family': 'American Platinum Eagle', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.9995',
    },

    # ── SILVER — CLASSIC US COINAGE ───────────────────────────────────────
    {
        'slug': 'silver-walking-liberty-half-dollar',
        'title': 'Walking Liberty Half Dollar (90% Silver)',
        'metal': 'Silver', 'form': 'coin',
        'weight': '0.36 oz', 'weight_oz': 0.3617,
        'mint': 'United States Mint', 'denomination': '$0.50',
        'product_family': 'Walking Liberty Half Dollar',
        'product_series': 'Classic US Coinage',
        'year_policy': 'varies', 'purity': '.900',
    },
    {
        'slug': 'silver-franklin-half-dollar',
        'title': 'Franklin Half Dollar (90% Silver)',
        'metal': 'Silver', 'form': 'coin',
        'weight': '0.36 oz', 'weight_oz': 0.3617,
        'mint': 'United States Mint', 'denomination': '$0.50',
        'product_family': 'Franklin Half Dollar',
        'product_series': 'Classic US Coinage',
        'year_policy': 'varies', 'purity': '.900',
    },
    {
        'slug': 'silver-mercury-dime',
        'title': 'Mercury Dime (90% Silver)',
        'metal': 'Silver', 'form': 'coin',
        'weight': '0.077 oz', 'weight_oz': 0.0723,
        'mint': 'United States Mint', 'denomination': '$0.10',
        'product_family': 'Mercury Dime',
        'product_series': 'Classic US Coinage',
        'year_policy': 'varies', 'purity': '.900',
    },
    {
        'slug': 'silver-roosevelt-dime',
        'title': 'Roosevelt Dime (90% Silver)',
        'metal': 'Silver', 'form': 'coin',
        'weight': '0.077 oz', 'weight_oz': 0.0723,
        'mint': 'United States Mint', 'denomination': '$0.10',
        'product_family': 'Roosevelt Dime',
        'product_series': 'Classic US Coinage',
        'year_policy': 'varies', 'purity': '.900',
    },
    {
        'slug': 'silver-washington-quarter',
        'title': 'Washington Quarter (90% Silver)',
        'metal': 'Silver', 'form': 'coin',
        'weight': '0.18 oz', 'weight_oz': 0.1808,
        'mint': 'United States Mint', 'denomination': '$0.25',
        'product_family': 'Washington Quarter',
        'product_series': 'Classic US Coinage',
        'year_policy': 'varies', 'purity': '.900',
    },
    {
        'slug': 'silver-junk-face-1-dollar',
        'title': '$1 Face Value 90% Junk Silver Coins',
        'metal': 'Silver', 'form': 'coin',
        'weight': '0.715 oz', 'weight_oz': 0.715,
        'mint': 'United States Mint', 'denomination': '$1 face',
        'product_family': 'Junk Silver', 'product_series': '90% US Coinage',
        'year_policy': 'varies', 'purity': '.900',
    },

    # ── SILVER — INTERNATIONAL COLLECTOR COINS ────────────────────────────
    {
        'slug': 'silver-perth-kookaburra-1oz',
        'title': '1 oz Australian Silver Kookaburra Coin',
        'metal': 'Silver', 'form': 'coin',
        'weight': '1 oz', 'weight_oz': 1.0,
        'mint': 'Perth Mint', 'denomination': '$1 AUD',
        'product_family': 'Silver Kookaburra', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.999',
    },
    {
        'slug': 'silver-chinese-panda-30g',
        'title': '30 g Chinese Silver Panda Coin',
        'metal': 'Silver', 'form': 'coin',
        'weight': '30 g', 'weight_oz': 0.965,
        'mint': 'China Gold Coin', 'denomination': '10 Yuan',
        'product_family': 'Silver Panda', 'product_series': 'Bullion',
        'year_policy': 'varies', 'purity': '.999',
    },

    # ── SILVER BARS — ADDITIONAL SIZES ────────────────────────────────────
    {
        'slug': 'silver-bar-2oz',
        'title': '2 oz Silver Bar',
        'metal': 'Silver', 'form': 'bar',
        'weight': '2 oz', 'weight_oz': 2.0,
        'mint': None, 'denomination': None,
        'product_family': 'Silver Bar', 'product_series': None,
        'year_policy': 'varies', 'purity': '.999',
    },
    {
        'slug': 'silver-bar-50oz',
        'title': '50 oz Silver Bar',
        'metal': 'Silver', 'form': 'bar',
        'weight': '50 oz', 'weight_oz': 50.0,
        'mint': None, 'denomination': None,
        'product_family': 'Silver Bar', 'product_series': None,
        'year_policy': 'varies', 'purity': '.999',
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slug_from_category(cat: dict) -> str:
    """Build a slug from a categories row for auto-sync."""
    parts = []
    metal = (cat.get('metal') or '').lower()
    if metal:
        parts.append(metal)
    product_line = (cat.get('product_line') or cat.get('coin_series') or '').lower()
    if product_line:
        parts.append(product_line.replace(' ', '-'))
    weight = (cat.get('weight') or '').lower().replace(' ', '')
    if weight:
        parts.append(weight)
    year = str(cat.get('year') or '')
    if year:
        parts.append(year)

    slug = '-'.join(p for p in parts if p)
    # Sanitise
    import re
    slug = re.sub(r'[^a-z0-9\-]', '', slug)
    slug = re.sub(r'-{2,}', '-', slug).strip('-')
    return slug or f"category-bucket-{cat.get('bucket_id', 'unknown')}"


def _seed_curated(conn, dry_run: bool) -> tuple:
    """Insert curated products. Returns (inserted, skipped)."""
    inserted = 0
    skipped = 0
    for product in SEED_PRODUCTS:
        slug = product['slug']
        existing = conn.execute(
            "SELECT id FROM standard_buckets WHERE slug = ?", (slug,)
        ).fetchone()
        if existing:
            skipped += 1
            continue
        if dry_run:
            print(f"  [DRY-RUN] Would insert: {slug}")
            inserted += 1
            continue
        try:
            bis.create_standard_bucket(product, conn=conn)
            print(f"  Inserted: {slug}")
            inserted += 1
        except ValueError as exc:
            print(f"  Skipped {slug}: {exc}")
            skipped += 1
    return inserted, skipped


def _sync_from_categories(conn, dry_run: bool) -> tuple:
    """
    Auto-import non-isolated categories into standard_buckets.
    Uses bucket_id as category_bucket_id link.
    Skips rows without bucket_id or with missing metal/product_type.
    """
    cats = conn.execute(
        "SELECT * FROM categories WHERE is_isolated = 0 AND bucket_id IS NOT NULL"
    ).fetchall()

    inserted = 0
    skipped = 0
    for cat in cats:
        cat = dict(cat)
        slug = _slug_from_category(cat)
        existing = conn.execute(
            "SELECT id FROM standard_buckets WHERE slug = ? OR category_bucket_id = ?",
            (slug, cat['bucket_id'])
        ).fetchone()
        if existing:
            skipped += 1
            continue

        metal = cat.get('metal') or ''
        if not metal:
            skipped += 1
            continue

        product_line = cat.get('product_line') or cat.get('coin_series') or ''
        product_type = cat.get('product_type') or 'Coin'
        title_parts = [p for p in [
            cat.get('year'), cat.get('weight'), metal, product_line or product_type
        ] if p]
        title = ' '.join(title_parts)

        data = {
            'slug':              slug,
            'title':             title,
            'metal':             metal,
            'form':              product_type.lower() if product_type else 'coin',
            'weight':            cat.get('weight'),
            'mint':              cat.get('mint'),
            'denomination':      cat.get('denomination'),
            'product_family':    product_line,
            'product_series':    cat.get('coin_series'),
            'year_policy':       'fixed' if cat.get('year') else 'varies',
            'year':              str(cat.get('year')) if cat.get('year') else None,
            'purity':            cat.get('purity'),
            'finish':            cat.get('finish'),
            'category_bucket_id': cat['bucket_id'],
        }

        if dry_run:
            print(f"  [DRY-RUN] Would sync category bucket_id={cat['bucket_id']}: {slug}")
            inserted += 1
            continue

        try:
            bis.create_standard_bucket(data, conn=conn)
            print(f"  Synced category bucket_id={cat['bucket_id']}: {slug}")
            inserted += 1
        except ValueError as exc:
            print(f"  Skipped category bucket_id={cat['bucket_id']}: {exc}")
            skipped += 1

    return inserted, skipped


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Seed standard_buckets catalog.')
    parser.add_argument('--sync-categories', action='store_true',
                        help='Also auto-import non-isolated categories into standard_buckets')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be inserted without writing anything')
    args = parser.parse_args()

    conn = database.get_db_connection()
    try:
        print('=== Seeding curated standard buckets ===')
        ins, skp = _seed_curated(conn, dry_run=args.dry_run)
        print(f'  Curated: {ins} inserted, {skp} already existed\n')

        if args.sync_categories:
            print('=== Syncing from categories table ===')
            ins2, skp2 = _sync_from_categories(conn, dry_run=args.dry_run)
            print(f'  Categories: {ins2} imported, {skp2} skipped\n')

        total = conn.execute("SELECT COUNT(*) FROM standard_buckets").fetchone()[0]
        print(f'=== Done. Total standard_buckets: {total} ===')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
