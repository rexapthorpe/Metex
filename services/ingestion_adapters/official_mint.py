"""
Official mint image adapters.

Architecture
============
OfficialMintAdapter — base class for all government/official-mint sources.
  UsMintAdapter     — US Mint (public_domain, eligible for auto-activation)
  RcmAdapter        — Royal Canadian Mint (licensed, admin review required)
  RoyalMintAdapter  — Royal Mint UK (licensed, admin review required)
  PerthMintAdapter  — Perth Mint Australia (licensed, admin review required)

All adapters search Wikimedia Commons using highly targeted official
product terminology, so results have higher precision than the generic
WikimediaAdapter.

Auto-activation
===============
US Mint images are US government works (public domain in the US).
Under the tiered auto-activation policy in bucket_image_service.py,
candidates with source_type='public_domain', confidence >= 0.75, and
no warning flags are promoted directly to 'active' without admin review.

RCM / Royal Mint / Perth Mint images stay 'pending' and require
admin review (their images are copyrighted).

Adding a new mint
=================
  1. Create a subclass of OfficialMintAdapter.
  2. Set: name, source_type, MINT_NAME.
  3. Populate _PRODUCT_TERMS: {slug_prefix: wikimedia_search_string}.
  4. Register in ADAPTERS dict in scripts/batch_ingest_images.py.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from .base import BaseImageAdapter

log = logging.getLogger(__name__)

_WIKIMEDIA_API   = 'https://commons.wikimedia.org/w/api.php'
_REQUEST_DELAY_S = 1.0

_PD_MARKERS = (
    'public domain', 'pd-', 'pd ', 'cc0', 'cc-zero',
    'us government', 'usgov', 'pdm', 'pd-usgov',
)
_BLOCKED_PATTERNS = (
    'all rights reserved', 'copyright',
    'non-commercial', 'no derivative', ' nd',
)


def _is_blocked(license_str: str) -> bool:
    ls = license_str.lower()
    return any(p in ls for p in _BLOCKED_PATTERNS)


def _classify_license(license_str: str) -> str:
    ls = license_str.lower()
    if any(p in ls for p in _PD_MARKERS):
        return 'public_domain'
    if 'cc-by' in ls or 'cc by' in ls or 'creative commons' in ls:
        return 'licensed'
    return 'licensed'


def _strip_html(s: str) -> str:
    import re
    return re.sub(r'<[^>]+>', '', s).strip()


# ---------------------------------------------------------------------------
# Base adapter
# ---------------------------------------------------------------------------

class OfficialMintAdapter(BaseImageAdapter):
    """
    Base adapter for official government/mint coin images via Wikimedia Commons.

    Subclasses override name, source_type, MINT_NAME, and _PRODUCT_TERMS.
    All Wikimedia API logic lives here so subclasses only need to declare
    their mint-specific product terminology.
    """

    name        : str = 'Official Mint'
    source_type : str = 'licensed'
    MINT_NAME   : str = ''   # Injected into generic search queries

    # Map slug prefix → exact Wikimedia search string
    # More specific = higher precision results = higher confidence scores
    _PRODUCT_TERMS: Dict[str, str] = {}

    def __init__(self, max_results: int = 2, request_delay: float = _REQUEST_DELAY_S):
        self._max      = max_results
        self._delay    = request_delay
        self._last_req = 0.0

    # ------------------------------------------------------------------
    # BaseImageAdapter contract
    # ------------------------------------------------------------------

    def find_candidates(self, bucket: Dict[str, Any]) -> List[Dict[str, Any]]:
        queries   = self._build_queries(bucket)
        seen_urls = set()
        candidates: List[Dict] = []

        for query in queries:
            if len(candidates) >= self._max:
                break
            for title in self._search_files(query):
                if len(candidates) >= self._max:
                    break
                info = self._get_image_info(title)
                if info is None:
                    continue
                url = info.get('url', '')
                if not url or url in seen_urls:
                    continue
                license_str = info.get('license', '')
                if _is_blocked(license_str):
                    log.debug('%s: skipping %s — blocked license', self.name, title)
                    continue
                seen_urls.add(url)
                candidates.append(self._build_candidate(bucket, title, info))

        return candidates

    # ------------------------------------------------------------------
    # Query construction
    # ------------------------------------------------------------------

    def _build_queries(self, bucket: Dict[str, Any]) -> List[str]:
        slug   = bucket.get('slug', '')
        metal  = bucket.get('metal', '')
        weight = bucket.get('weight', '')
        family = bucket.get('product_family', '')
        form   = bucket.get('form', 'coin')

        # Check for a slug-prefix override first (most specific)
        for prefix, term in self._PRODUCT_TERMS.items():
            if slug.startswith(prefix):
                queries = [term]
                # Broader fallback so we still find something if the specific
                # query returns no usable images
                if family and weight and metal:
                    queries.append(f'{family} {weight} {metal} {form} coin')
                return queries

        # Generic official-mint fallback
        queries: List[str] = []
        if family and weight and metal:
            queries.append(f'{family} {weight} {metal} {form} coin')
        if self.MINT_NAME and weight and metal:
            queries.append(f'{self.MINT_NAME} {weight} {metal} {form}')
        if metal and weight:
            queries.append(f'{metal} {weight} {form} bullion coin')
        return queries[:3] or [f'{metal} {form} bullion coin']

    # ------------------------------------------------------------------
    # Wikimedia API helpers (shared across all subclasses)
    # ------------------------------------------------------------------

    def _throttle(self):
        now  = time.monotonic()
        wait = self._delay - (now - self._last_req)
        if wait > 0:
            time.sleep(wait)
        self._last_req = time.monotonic()

    def _api_get(self, params: Dict) -> Optional[Dict]:
        self._throttle()
        try:
            import requests
            resp = requests.get(
                _WIKIMEDIA_API,
                params={**params, 'format': 'json'},
                timeout=15,
                headers={'User-Agent': 'MetexImageBot/1.0 (metex.com; official-mint catalog)'},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            log.warning('%s API request failed: %s', self.name, exc)
            return None

    def _search_files(self, query: str) -> List[str]:
        data = self._api_get({
            'action':      'query',
            'list':        'search',
            'srsearch':    query,
            'srnamespace': 6,       # File: namespace
            'srlimit':     min(self._max * 4, 20),
        })
        if not data:
            return []
        titles = []
        for r in data.get('query', {}).get('search', []):
            title = r.get('title', '')
            if title.startswith('File:'):
                ext = title.rsplit('.', 1)[-1].lower() if '.' in title else ''
                if ext in ('jpg', 'jpeg', 'png', 'webp'):
                    titles.append(title)
        return titles

    def _get_image_info(self, file_title: str) -> Optional[Dict]:
        data = self._api_get({
            'action':    'query',
            'titles':    file_title,
            'prop':      'imageinfo',
            'iiprop':    'url|extmetadata',
            'iiurlwidth': 800,   # standard Wikimedia thumbnail size
        })
        if not data:
            return None

        pages = data.get('query', {}).get('pages', {})
        for page in pages.values():
            ii = page.get('imageinfo', [{}])
            if not ii:
                return None
            info         = ii[0]
            # Prefer the pre-generated thumbnail to avoid Wikimedia 429 on full-res downloads
            url          = info.get('thumburl') or info.get('url', '')
            original_url = info.get('url', '') or url
            page_url     = (
                f"https://commons.wikimedia.org/wiki/{file_title.replace(' ', '_')}"
            )
            extmeta = info.get('extmetadata', {})

            def _v(key):
                return extmeta.get(key, {}).get('value', '')

            license_str = _v('LicenseShortName') or _v('License') or _v('UsageTerms')
            attribution = _strip_html(_v('Attribution') or _v('Artist') or '')
            description = _strip_html(
                _v('ImageDescription') or _v('ObjectName') or
                file_title.replace('File:', '').rsplit('.', 1)[0]
            )
            # Normalize underscores to spaces so confidence scoring can do substring matching
            description = description.replace('_', ' ')
            return {
                'url':          url,
                'original_url': original_url,
                'page_url':     page_url,
                'license':      license_str,
                'attribution':  attribution,
                'description':  description,
            }
        return None

    def _build_candidate(
        self, bucket: Dict, file_title: str, info: Dict
    ) -> Dict[str, Any]:
        license_str = info.get('license', '')
        # For public_domain adapters, trust the adapter's declared source_type
        # rather than trying to classify from the Wikimedia license string
        source_type = (
            self.source_type
            if self.source_type == 'public_domain'
            else _classify_license(license_str)
        )

        c = self._base_candidate(
            url=info['url'],
            raw_title=info.get('description', file_title),
            page_url=info.get('page_url', ''),
        )
        c['source_name']        = self.name
        c['source_type']        = source_type
        c['license_type']       = license_str or None
        c['attribution_text']   = info.get('attribution') or self.MINT_NAME or None
        c['original_image_url'] = info.get('original_url') or info['url']
        c['rights_note'] = (
            f"{self.name}. License: {license_str}. "
            f"Source: {info.get('page_url', '')}"
            if license_str else
            f"{self.name}. Source: {info.get('page_url', '')}"
        )
        return c


# ===========================================================================
# US Mint
# ===========================================================================

class UsMintAdapter(OfficialMintAdapter):
    """
    US Mint coin images via Wikimedia Commons.

    US Mint designs are released as US government works and are public domain.
    Candidates with source_type='public_domain', confidence >= 0.75, and no
    warning flags are auto-activated (see bucket_image_service.py).

    Covers: American Gold Eagle, American Gold Buffalo, American Silver Eagle,
            American Platinum Eagle, American Palladium Eagle.
    """
    name        = 'US Mint (Public Domain)'
    source_type = 'public_domain'
    MINT_NAME   = 'United States Mint'

    _PRODUCT_TERMS = {
        'gold-american-eagle':       'American Gold Eagle bullion coin United States Mint',
        'gold-american-buffalo':     'American Gold Buffalo coin United States Mint 24 karat',
        'silver-american-eagle':     'American Silver Eagle bullion coin United States Mint',
        'platinum-american-eagle':   'American Platinum Eagle coin United States Mint bullion',
        'palladium-american-eagle':  'American Palladium Eagle coin United States Mint',
    }


# ===========================================================================
# Royal Canadian Mint
# ===========================================================================

class RcmAdapter(OfficialMintAdapter):
    """
    Royal Canadian Mint coin images via Wikimedia Commons.

    RCM images are copyrighted; candidates stay pending and require admin review.
    Covers: Gold Maple Leaf, Silver Maple Leaf, Platinum Maple Leaf,
            Palladium Maple Leaf.
    """
    name        = 'Royal Canadian Mint'
    source_type = 'licensed'
    MINT_NAME   = 'Royal Canadian Mint'

    _PRODUCT_TERMS = {
        'gold-canadian-maple-leaf':      'Canadian Gold Maple Leaf coin Royal Canadian Mint',
        'silver-canadian-maple-leaf':    'Canadian Silver Maple Leaf coin Royal Canadian Mint',
        'platinum-canadian-maple-leaf':  'Canadian Platinum Maple Leaf coin Royal Canadian Mint',
        'palladium-canadian-maple-leaf': 'Canadian Palladium Maple Leaf coin Royal Canadian Mint',
    }


# ===========================================================================
# Royal Mint (UK)
# ===========================================================================

class RoyalMintAdapter(OfficialMintAdapter):
    """
    Royal Mint (UK) coin images via Wikimedia Commons.

    Covers: Gold Britannia, Silver Britannia.
    Candidates stay pending and require admin review.
    """
    name        = 'Royal Mint (UK)'
    source_type = 'licensed'
    MINT_NAME   = 'Royal Mint'

    _PRODUCT_TERMS = {
        'gold-british-britannia':    'Gold Britannia coin Royal Mint United Kingdom bullion',
        'silver-british-britannia':  'Silver Britannia coin Royal Mint United Kingdom bullion',
    }


# ===========================================================================
# Perth Mint (Australia)
# ===========================================================================

class PerthMintAdapter(OfficialMintAdapter):
    """
    Perth Mint coin images via Wikimedia Commons.

    Covers: Gold Kangaroo (Nugget), Silver Kangaroo, Silver Kookaburra.
    Candidates stay pending and require admin review.
    """
    name        = 'Perth Mint'
    source_type = 'licensed'
    MINT_NAME   = 'Perth Mint'

    _PRODUCT_TERMS = {
        'gold-australian-kangaroo':    'Australian Gold Kangaroo Nugget coin Perth Mint',
        'silver-australian-kangaroo':  'Australian Silver Kangaroo coin Perth Mint bullion',
        'silver-perth-kookaburra':     'Australian Silver Kookaburra coin Perth Mint',
    }
