"""
Bullion bar / refiner image adapter.

Searches Wikimedia Commons for images of bullion bars from major refiners:

  PAMP Suisse   — Lady Fortuna series; best Wikimedia coverage for gold bars
  Valcambi      — Swiss refiner; good coverage for gram/kilo gold bars
  Sunshine Minting — US; best coverage for 1–10 oz silver bars
  Engelhard     — historic US silver bars (vintage, widely photographed)
  Johnson Matthey — historic UK/US bars
  Credit Suisse — 10 oz and kilo gold bars

Coverage approach
-----------------
Each bar slug maps to a specific weight-aware, refiner-named search term.
A generic fallback query ("silver 10 oz bar bullion") is also tried so
that slugs without a specific term still receive candidates.

Auto-activation policy
----------------------
Bar images are ALWAYS source_type='licensed' and always stay 'pending'.
The tiered auto-activation rule in bucket_image_service.py only auto-
activates 'internal_upload' or 'public_domain' images — refiner images
never qualify. Every bar candidate requires admin review.

Adding new bar buckets
----------------------
  1. Add an entry to _PRODUCT_TERMS: full_slug → best Wikimedia search string
  2. That's it — the batch runner picks up all bar slugs automatically via
     the 'refiner' adapter key already registered in batch_ingest_images.py.
"""

import logging
from typing import Any, Dict, List

from .official_mint import OfficialMintAdapter

log = logging.getLogger(__name__)


class RefinerAdapter(OfficialMintAdapter):
    """
    Wikimedia Commons adapter for bullion bar images.

    Uses weight-aware, refiner-specific search queries so Wikimedia search
    results map as closely as possible to the correct bar product.

    All candidates go to 'pending' for admin review — no auto-activation.
    """

    name        = 'Bullion Refiner'
    source_type = 'licensed'
    MINT_NAME   = ''

    # -----------------------------------------------------------------------
    # Slug → primary Wikimedia search string
    #
    # Keys are FULL slug names (not prefixes) so each bar weight gets its own
    # targeted query rather than a single generic fallback for all gold bars.
    #
    # Refiner ordering in search terms reflects Wikimedia coverage depth:
    #   PAMP Suisse ≫ Valcambi > Sunshine Minting > Engelhard > JM
    # -----------------------------------------------------------------------
    _PRODUCT_TERMS: Dict[str, str] = {

        # ── Gold bars ──────────────────────────────────────────────────────
        'gold-bar-1g':          'PAMP Suisse Lady Fortuna 1 gram gold bar bullion',
        'gold-bar-2-5g':        'PAMP Suisse 2.5 gram gold bar bullion Valcambi',
        'gold-bar-5g':          'PAMP Suisse Valcambi 5 gram gold bar bullion',
        'gold-bar-10g':         'PAMP Suisse Valcambi 10 gram gold bar bullion',
        'gold-bar-quarter-oz':  'PAMP Suisse gold bar quarter ounce 1/4 oz bullion',
        'gold-bar-1oz':         'PAMP Suisse Lady Fortuna 1 troy ounce gold bar bullion',
        'gold-bar-10oz':        'gold bar 10 troy ounce bullion Valcambi Credit Suisse',
        'gold-bar-1kg':         'PAMP Suisse Valcambi 1 kilogram gold bar bullion',

        # ── Silver bars ────────────────────────────────────────────────────
        'silver-bar-1oz':       'silver bar 1 troy ounce bullion Sunshine Minting',
        'silver-bar-2oz':       'silver bar 2 troy ounce bullion Sunshine',
        'silver-bar-5oz':       'silver bar 5 troy ounce bullion Sunshine Minting',
        'silver-bar-10oz':      'Sunshine Minting silver bar 10 troy ounce bullion',
        'silver-bar-50oz':      'silver bar 50 troy ounce Engelhard Johnson Matthey bullion',
        'silver-bar-100oz':     'silver bar 100 troy ounce bullion Engelhard',
        'silver-bar-1kg':       'silver bar 1 kilogram bullion PAMP Suisse Valcambi',

        # ── Platinum / Palladium bars ───────────────────────────────────────
        'platinum-bar-1oz':     'platinum bar 1 troy ounce bullion PAMP Suisse',
        'palladium-bar-1oz':    'palladium bar 1 troy ounce bullion',

        # ── Copper bars ─────────────────────────────────────────────────────
        'copper-bar-1oz':       'copper bar 1 ounce bullion',
        'copper-bar-1lb':       'copper bar 1 pound bullion',
    }

    # -----------------------------------------------------------------------
    # Query construction — overrides OfficialMintAdapter to avoid 'coin' suffix
    # -----------------------------------------------------------------------

    def _build_queries(self, bucket: Dict[str, Any]) -> List[str]:
        """
        Build 1–2 search queries per bar bucket.

        Primary  : specific refiner + weight term from _PRODUCT_TERMS.
        Fallback : generic ``metal weight bar bullion`` (no 'coin' suffix).

        If no slug match exists, falls back to weight-aware generic queries
        so that any new bar bucket slug still receives candidate images.
        """
        slug   = bucket.get('slug', '')
        metal  = (bucket.get('metal') or '').lower()
        weight =  bucket.get('weight') or ''
        form   =  bucket.get('form') or 'bar'

        # Exact-slug match in _PRODUCT_TERMS
        for prefix, term in self._PRODUCT_TERMS.items():
            if slug.startswith(prefix):
                queries = [term]
                # Secondary generic fallback — helps when specific term returns
                # few usable images (e.g. premium refiner out-of-date on Wikimedia)
                if metal and weight:
                    queries.append(f'{metal} {weight} {form} bullion')
                return queries

        # No specific term — use generic weight-aware bar queries
        queries: List[str] = []
        if metal and weight:
            queries.append(f'{metal} {weight} {form} bullion')
        if metal:
            queries.append(f'{metal} bullion {form}')
        return queries[:3] or [f'{form} bullion']
