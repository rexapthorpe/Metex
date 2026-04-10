"""
Retailer image adapters: APMEX and JM Bullion.

These adapters scrape product images from major US bullion retailers for use
as candidates in the bucket image catalog.

IMPORTANT — publishing policy
==============================
All retailer-sourced candidates have source_type='retailer' and start with
status='pending'.  They are NEVER auto-activated, regardless of confidence
score.  An admin must explicitly approve or activate each one.

These images typically belong to the retailer and are used here for internal
candidate review only (not public display without rights clearance).

Warning detection
=================
Both adapters detect the following flags from product title / page content:
  example_image       — "example image", "sample", "representative image"
  year_varies         — "year varies", "random year", "our choice", "date our choice"
  brand_varies        — "brand varies", "mint varies", "random mint", "assorted"
  proof_vs_bullion    — page title mentions "proof" but bucket finish is not proof
  size_mismatch       — detected downstream by compute_match_confidence

These warnings feed into compute_match_confidence via raw_source_title so the
existing warning caps apply.  The adapters also inject explicit warning hints
into raw_source_title so they are reliably picked up.

Usage
=====
  python scripts/batch_ingest_images.py --all --source apmex
  python scripts/batch_ingest_images.py --missing-only --source jmbullion
  python scripts/batch_ingest_images.py --bucket-id 5 --source apmex --dry-run
"""

import logging
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urljoin

from .base import BaseImageAdapter

log = logging.getLogger(__name__)

_REQUEST_DELAY_S = 2.5   # be polite to retailer sites
_TIMEOUT = 20

_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (compatible; MetexImageBot/1.0; +https://metex.com/bot; '
        'numismatic image catalog research)'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

# ---------------------------------------------------------------------------
# Warning keywords: maps warning flag → list of trigger substrings (lowercase)
# These are injected into raw_source_title so compute_match_confidence picks
# them up via its own keyword detection.
# ---------------------------------------------------------------------------

_WARN_KEYWORDS: Dict[str, tuple] = {
    'example image': (
        'example image', 'sample image', 'representative image',
        'image may vary', 'image for reference', 'for illustrative',
        'stock photo', 'stock image',
    ),
    'year varies': (
        'year varies', 'random year', 'our choice', 'date our choice',
        'year of our choice', 'any year', 'mixed year', 'best value year',
        'current year', 'date we choose', 'dates vary',
    ),
    'brand varies': (
        'brand varies', 'mint varies', 'random mint', 'assorted mint',
        'various brands', 'our choice of mint', 'mint of our choice',
        'random assorted', 'assorted brands',
    ),
}


def _detect_warning_fragments(text: str, bucket: Dict[str, Any]) -> List[str]:
    """
    Scan text for warning keywords and proof/bullion mismatch.
    Returns list of canonical warning-flag strings to append to raw_source_title.
    """
    text_lower = text.lower()
    found: List[str] = []

    for canonical_kw, triggers in _WARN_KEYWORDS.items():
        if any(t in text_lower for t in triggers):
            found.append(canonical_kw)

    # Proof vs bullion: if product title says "proof" but the bucket isn't proof
    bucket_finish = (bucket.get('finish') or '').lower()
    if 'proof' in text_lower and bucket_finish not in ('proof', 'reverse proof'):
        found.append('proof')   # 'proof' substring in title → proof_vs_bullion in scoring

    return found


def _append_warnings_to_title(base_title: str, warnings: List[str]) -> str:
    """
    Append detected warning phrases to base_title so compute_match_confidence
    can detect them via its keyword search.
    """
    if not warnings:
        return base_title
    return base_title + ' [' + ' | '.join(warnings) + ']'


# ---------------------------------------------------------------------------
# Shared HTML utilities
# ---------------------------------------------------------------------------

def _extract_og_image(html: str) -> Optional[str]:
    patterns = [
        r'<meta\s[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']',
        r'<meta\s[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']og:image["\']',
        r'<meta\s[^>]*name=["\']twitter:image["\'][^>]*content=["\']([^"\']+)["\']',
        r'<meta\s[^>]*content=["\']([^"\']+)["\'][^>]*name=["\']twitter:image["\']',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            url = m.group(1).strip()
            if url.startswith('http'):
                return url
    return None


def _extract_og_title(html: str) -> str:
    for pat in (
        r'<meta\s[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']',
        r'<meta\s[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']og:title["\']',
        r'<title[^>]*>([^<]+)</title>',
    ):
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            title = m.group(1).strip()
            # Strip site suffix ("— APMEX", "| JM Bullion", etc.)
            title = re.sub(r'\s*[-–|]\s*(APMEX|JM Bullion|jmbullion\.com)[^"]*$', '', title,
                           flags=re.IGNORECASE).strip()
            return title
    return ''


def _extract_json_ld_image(html: str) -> Optional[str]:
    """Extract the first 'image' field from JSON-LD <script type="application/ld+json"> blocks."""
    import json
    for block in re.finditer(
        r'<script\s[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.IGNORECASE | re.DOTALL
    ):
        try:
            data = json.loads(block.group(1))
            # Handle list-of-schemas
            if isinstance(data, list):
                data = next((d for d in data if isinstance(d, dict) and d.get('@type') == 'Product'), {})
            img = data.get('image')
            if isinstance(img, str) and img.startswith('http'):
                return img
            if isinstance(img, list) and img:
                return img[0]
        except Exception:
            pass
    return None


def _first_product_link(html: str, base_url: str) -> Optional[str]:
    """
    Try to extract the URL of the first product link from a search results page.
    Looks for <a href="..."> elements that contain a product-image or product-title.
    """
    # Look for links that appear inside product-card containers
    # Most retailer search pages use class names like "product-item", "product-card", etc.
    product_block_pat = re.search(
        r'(?:class=["\'][^"\']*(?:product[-_](?:item|card|result|listing|title|name))[^"\']*["\'])'
        r'[^<]*<a\s+href=["\']([^"\']+)["\']'
        r'|'
        r'<a\s+href=["\']([^"\']+)["\'][^>]*>\s*<img',
        html, re.IGNORECASE | re.DOTALL,
    )
    if product_block_pat:
        href = product_block_pat.group(1) or product_block_pat.group(2)
        if href:
            return urljoin(base_url, href.strip())
    return None


# ---------------------------------------------------------------------------
# Base class for retailer adapters
# ---------------------------------------------------------------------------

class RetailerAdapter(BaseImageAdapter):
    """
    Base class for retailer image adapters.

    Subclasses implement _build_search_url() and can override _scrape_product_page()
    for site-specific HTML structure.  The default implementation:
      1. Builds a search URL from the bucket's metal/weight/product_family/mint.
      2. Fetches the search results page.
      3. Follows the first product link.
      4. Extracts the og:image (or JSON-LD image) from the product page.
    """

    name        = 'Retailer'
    source_type = 'retailer'

    def __init__(self, max_results: int = 2, request_delay: float = _REQUEST_DELAY_S):
        self._max      = max_results
        self._delay    = request_delay
        self._last_req = 0.0

    # ------------------------------------------------------------------
    # Subclass interface
    # ------------------------------------------------------------------

    def _build_search_url(self, bucket: Dict[str, Any]) -> Optional[str]:
        """Return the URL to fetch for this bucket. Override per retailer."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # BaseImageAdapter contract
    # ------------------------------------------------------------------

    def find_candidates(self, bucket: Dict[str, Any]) -> List[Dict[str, Any]]:
        search_url = self._build_search_url(bucket)
        if not search_url:
            return []

        html = self._fetch_html(search_url)
        if not html:
            return []

        # Try to get a direct product page for a better image
        product_url = _first_product_link(html, search_url) or search_url
        if product_url != search_url:
            product_html = self._fetch_html(product_url)
        else:
            product_html = html

        if not product_html:
            product_html = html
            product_url  = search_url

        return self._build_candidates(bucket, product_html, product_url)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _throttle(self):
        now  = time.monotonic()
        wait = self._delay - (now - self._last_req)
        if wait > 0:
            time.sleep(wait)
        self._last_req = time.monotonic()

    def _fetch_html(self, url: str) -> Optional[str]:
        self._throttle()
        try:
            import requests
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT,
                                allow_redirects=True)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            log.warning('%s: fetch failed for %s — %s', self.name, url, exc)
            return None

    def _build_candidates(
        self, bucket: Dict[str, Any], html: str, page_url: str
    ) -> List[Dict[str, Any]]:
        """Extract image from product page HTML and build candidate dicts."""
        # Prefer JSON-LD product image (highest quality), then og:image
        img_url = _extract_json_ld_image(html) or _extract_og_image(html)
        if not img_url:
            log.debug('%s: no product image found at %s', self.name, page_url)
            return []

        # Product title for raw_source_title
        product_title = _extract_og_title(html) or bucket.get('title', '')

        # Detect and append warning fragments
        warn_frags = _detect_warning_fragments(product_title, bucket)
        raw_title  = _append_warnings_to_title(product_title, warn_frags)

        c = self._base_candidate(url=img_url, raw_title=raw_title, page_url=page_url)
        c['source_name']        = self.name
        c['source_type']        = self.source_type
        c['license_type']       = 'all_rights_reserved'
        c['attribution_text']   = self.name
        c['original_image_url'] = img_url
        c['rights_note'] = (
            f'Image from {self.name} product page. Retailer copyright — '
            'for internal candidate review only. Not for public display '
            f'without rights clearance. Source: {page_url}'
        )
        return [c]


# ---------------------------------------------------------------------------
# APMEX Adapter
# ---------------------------------------------------------------------------

# Curated slug-prefix → APMEX category/product page URL.
# Category pages are stable and return HTML without JavaScript rendering.
# Preference: category pages → simpler HTML, multiple products visible.
_APMEX_URLS: Dict[str, str] = {
    'gold-american-eagle':              'https://www.apmex.com/category/80/gold-american-eagle-coins',
    'silver-american-eagle':            'https://www.apmex.com/category/176/silver-american-eagle-coins',
    'gold-american-buffalo':            'https://www.apmex.com/category/82/american-gold-buffalo-coins',
    'platinum-american-eagle':          'https://www.apmex.com/category/234/american-platinum-eagle-coins',
    'palladium-american-eagle':         'https://www.apmex.com/category/3091/american-palladium-eagle-coins',
    'gold-canadian-maple-leaf':         'https://www.apmex.com/category/199/gold-canadian-maple-leaf-coins',
    'silver-canadian-maple-leaf':       'https://www.apmex.com/category/133/silver-canadian-maple-leaf-coins',
    'platinum-canadian-maple-leaf':     'https://www.apmex.com/category/204/platinum-canadian-maple-leaf-coins',
    'gold-south-african-krugerrand':    'https://www.apmex.com/category/7/south-african-gold-krugerrand-coins',
    'gold-austrian-philharmonic':       'https://www.apmex.com/category/6/austrian-gold-philharmonic-coins',
    'silver-austrian-philharmonic':     'https://www.apmex.com/category/192/austrian-silver-philharmonic-coins',
    'gold-australian-kangaroo':         'https://www.apmex.com/category/8/australian-gold-kangaroo-coins',
    'silver-australian-kangaroo':       'https://www.apmex.com/category/181/silver-australian-kangaroo-coins',
    'silver-perth-kookaburra':          'https://www.apmex.com/category/183/australian-silver-kookaburra-coins',
    'silver-chinese-panda':             'https://www.apmex.com/category/182/chinese-silver-panda-coins',
    'gold-chinese-panda':               'https://www.apmex.com/category/24/chinese-gold-panda-coins',
    'gold-british-britannia':           'https://www.apmex.com/category/13/gold-britannia-coins',
    'silver-british-britannia':         'https://www.apmex.com/category/193/silver-britannia-coins',
    'gold-mexican-libertad':            'https://www.apmex.com/category/26/mexican-gold-libertad-coins',
    'silver-mexican-libertad':          'https://www.apmex.com/category/174/mexican-silver-libertad-coins',
    'silver-american-liberty':          'https://www.apmex.com/category/3504/american-liberty-silver-medals',
    'gold-american-liberty':            'https://www.apmex.com/category/3503/american-liberty-gold-coins',
}

_APMEX_SEARCH = 'https://www.apmex.com/search?cp=product&keyword={query}'


class ApmexAdapter(RetailerAdapter):
    """
    APMEX product image adapter.

    For buckets with a known APMEX category page, fetches that page directly.
    For other buckets, falls back to a keyword search.
    All candidates are source_type='retailer' and start pending.
    """

    name = 'APMEX'

    def _build_search_url(self, bucket: Dict[str, Any]) -> Optional[str]:
        slug = bucket.get('slug', '')
        # Check curated category map first
        for prefix, url in _APMEX_URLS.items():
            if slug.startswith(prefix):
                return url
        # Fall back to search
        return self._build_keyword_search(bucket)

    def _build_keyword_search(self, bucket: Dict[str, Any]) -> Optional[str]:
        parts = []
        weight = bucket.get('weight', '')
        if weight:
            parts.append(weight)
        family = bucket.get('product_family', '')
        if family:
            parts.append(family)
        metal = bucket.get('metal', '')
        if metal:
            parts.append(metal)
        if not parts:
            return None
        query = ' '.join(parts)
        return _APMEX_SEARCH.format(query=quote_plus(query))


# ---------------------------------------------------------------------------
# JM Bullion Adapter
# ---------------------------------------------------------------------------

# Curated slug-prefix → JM Bullion category page URL.
# JM Bullion uses clean slug-based URLs that are stable.
_JMBULLION_URLS: Dict[str, str] = {
    'gold-american-eagle':              'https://www.jmbullion.com/gold/american-gold-eagle/',
    'silver-american-eagle':            'https://www.jmbullion.com/silver/american-silver-eagle/',
    'gold-american-buffalo':            'https://www.jmbullion.com/gold/american-gold-buffalo/',
    'platinum-american-eagle':          'https://www.jmbullion.com/platinum/american-platinum-eagle/',
    'palladium-american-eagle':         'https://www.jmbullion.com/palladium/american-palladium-eagle/',
    'gold-canadian-maple-leaf':         'https://www.jmbullion.com/gold/canadian-maple-leaf/',
    'silver-canadian-maple-leaf':       'https://www.jmbullion.com/silver/canadian-maple-leaf/',
    'gold-south-african-krugerrand':    'https://www.jmbullion.com/gold/krugerrands/',
    'gold-austrian-philharmonic':       'https://www.jmbullion.com/gold/austrian-philharmonic/',
    'silver-austrian-philharmonic':     'https://www.jmbullion.com/silver/austrian-philharmonic/',
    'gold-australian-kangaroo':         'https://www.jmbullion.com/gold/australian-kangaroo/',
    'silver-australian-kangaroo':       'https://www.jmbullion.com/silver/australian-kangaroo/',
    'silver-perth-kookaburra':          'https://www.jmbullion.com/silver/australian-kookaburra/',
    'silver-chinese-panda':             'https://www.jmbullion.com/silver/chinese-silver-panda/',
    'gold-chinese-panda':               'https://www.jmbullion.com/gold/chinese-gold-panda/',
    'gold-british-britannia':           'https://www.jmbullion.com/gold/british-britannia/',
    'silver-british-britannia':         'https://www.jmbullion.com/silver/british-britannia/',
    'gold-mexican-libertad':            'https://www.jmbullion.com/gold/mexican-libertad/',
    'silver-mexican-libertad':          'https://www.jmbullion.com/silver/mexican-libertad/',
    'gold-american-liberty':            'https://www.jmbullion.com/gold/american-liberty/',
    'silver-american-liberty':          'https://www.jmbullion.com/silver/american-liberty-medals/',
    'silver-morgan-dollar':             'https://www.jmbullion.com/silver/morgan-dollar/',
    'silver-peace-dollar':              'https://www.jmbullion.com/silver/peace-dollar/',
    # Bars
    'gold-bar':                         'https://www.jmbullion.com/gold/gold-bars/',
    'silver-bar':                       'https://www.jmbullion.com/silver/silver-bars/',
    'platinum-bar':                     'https://www.jmbullion.com/platinum/platinum-bars/',
    'palladium-bar':                    'https://www.jmbullion.com/palladium/palladium-bars/',
}

_JMBULLION_SEARCH = 'https://www.jmbullion.com/search/?q={query}'


class JmBullionAdapter(RetailerAdapter):
    """
    JM Bullion product image adapter.

    For buckets with a known JM Bullion category page, fetches that page
    directly.  For other buckets, falls back to a keyword search.
    All candidates are source_type='retailer' and start pending.
    """

    name = 'JM Bullion'

    def _build_search_url(self, bucket: Dict[str, Any]) -> Optional[str]:
        slug = bucket.get('slug', '')
        for prefix, url in _JMBULLION_URLS.items():
            if slug.startswith(prefix):
                return url
        return self._build_keyword_search(bucket)

    def _build_keyword_search(self, bucket: Dict[str, Any]) -> Optional[str]:
        parts = []
        weight = bucket.get('weight', '')
        if weight:
            parts.append(weight)
        family = bucket.get('product_family', '')
        if family:
            parts.append(family)
        metal = bucket.get('metal', '')
        if metal:
            parts.append(metal)
        if not parts:
            return None
        query = ' '.join(parts)
        return _JMBULLION_SEARCH.format(query=quote_plus(query))
