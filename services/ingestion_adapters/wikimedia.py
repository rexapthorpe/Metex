"""
Wikimedia Commons image adapter.

Uses the public MediaWiki API (no API key required) to search for
CC-licensed or public-domain images of precious-metals products.

API reference: https://www.mediawiki.org/wiki/API:Search
               https://www.mediawiki.org/wiki/API:Imageinfo

License handling:
  - "public domain" / "PD" / government marks → source_type = 'public_domain'
  - CC-BY, CC0, CC-BY-SA, etc.               → source_type = 'licensed'
  - Unknown / no extmetadata                  → source_type = 'licensed' (conservative)
  - "all rights reserved" / proprietary       → skipped entirely

Usage:
    from services.ingestion_adapters import WikimediaAdapter
    adapter = WikimediaAdapter(max_results=3)
    candidates = adapter.find_candidates(bucket_dict)
"""

import logging
import time
from typing import Any, Dict, List, Optional

from .base import BaseImageAdapter

log = logging.getLogger(__name__)

# Wikimedia Commons API endpoint
_API_URL = 'https://commons.wikimedia.org/w/api.php'

# Licenses we will NOT ingest (too restrictive)
_BLOCKED_LICENSE_PATTERNS = (
    'all rights reserved',
    'copyright',
    'non-commercial',
    'no derivative',
    'nd',
)

# Well-known public-domain markers in Wikimedia license strings
_PD_MARKERS = (
    'public domain',
    'pd-',
    'pd ',
    'cc0',
    'cc-zero',
    'us government',
    'usgov',
    'pdm',
)

# Throttle: Wikimedia requests rate guidance is ~1 req/s for bots
_REQUEST_DELAY_S = 1.0


def _is_likely_blocked(license_str: str) -> bool:
    ls = license_str.lower()
    return any(p in ls for p in _BLOCKED_LICENSE_PATTERNS)


def _classify_license(license_str: str) -> str:
    """Map a Wikimedia license string to our source_type."""
    ls = license_str.lower()
    if any(p in ls for p in _PD_MARKERS):
        return 'public_domain'
    if 'cc-by' in ls or 'cc by' in ls or 'creative commons' in ls:
        return 'licensed'
    return 'licensed'  # conservative default


class WikimediaAdapter(BaseImageAdapter):
    """Search Wikimedia Commons for CC-licensed or public-domain coin images."""

    name = 'Wikimedia Commons'
    source_type = 'licensed'  # default; overridden per-candidate based on actual license

    def __init__(self, max_results: int = 3, request_delay: float = _REQUEST_DELAY_S):
        self._max = max_results
        self._delay = request_delay
        self._last_request = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_candidates(self, bucket: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Search Wikimedia Commons for images matching this bucket.
        Returns up to max_results ImageCandidate dicts.
        """
        queries = self._build_queries(bucket)
        seen_urls = set()
        candidates = []

        for query in queries:
            if len(candidates) >= self._max:
                break
            titles = self._search_files(query)
            for title in titles:
                if len(candidates) >= self._max:
                    break
                info = self._get_image_info(title)
                if info is None:
                    continue
                url = info.get('url')
                if not url or url in seen_urls:
                    continue
                license_str = info.get('license', '')
                if _is_likely_blocked(license_str):
                    log.debug('Skipping %s: blocked license %s', title, license_str)
                    continue
                seen_urls.add(url)
                c = self._build_candidate(bucket, title, info)
                candidates.append(c)

        return candidates

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_queries(self, bucket: Dict[str, Any]) -> List[str]:
        """
        Generate 1–3 Wikimedia search queries from narrowest to broadest,
        so the first results are most specific.
        """
        metal   = bucket.get('metal', '')
        weight  = bucket.get('weight', '')
        family  = bucket.get('product_family', '')
        mint    = bucket.get('mint', '')
        form    = bucket.get('form', 'coin')

        queries = []

        # Query 1: specific — product family + weight + metal + form
        if family and weight:
            queries.append(f'{family} {weight} {metal} {form} bullion')
        elif family and metal:
            queries.append(f'{family} {metal} {form} bullion')

        # Query 2: mint + weight + metal if no product family
        if mint and weight and metal:
            queries.append(f'{mint} {weight} {metal} {form}')

        # Query 3: broad — metal + weight + form
        if metal and weight:
            queries.append(f'{metal} {weight} {form} bullion coin')

        return queries[:3] if queries else [f'{metal} {form} bullion']

    def _throttle(self):
        now = time.monotonic()
        wait = self._delay - (now - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _api_get(self, params: Dict) -> Optional[Dict]:
        """Make a Wikimedia API GET request. Returns parsed JSON or None."""
        self._throttle()
        try:
            import requests
            resp = requests.get(
                _API_URL,
                params={**params, 'format': 'json'},
                timeout=15,
                headers={'User-Agent': 'MetexImageBot/1.0 (metex.com; precious metals catalog)'},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            log.warning('Wikimedia API request failed: %s', exc)
            return None

    def _search_files(self, query: str) -> List[str]:
        """
        Search Wikimedia Commons (namespace 6 = File:) and return file titles.
        Filters to JPEG/PNG only.
        """
        data = self._api_get({
            'action': 'query',
            'list': 'search',
            'srsearch': query,
            'srnamespace': 6,
            'srlimit': min(self._max * 3, 20),  # fetch more, filter later
        })
        if not data:
            return []
        results = data.get('query', {}).get('search', [])
        titles = []
        for r in results:
            title = r.get('title', '')
            # Only images (namespace 6 titles start with "File:")
            if title.startswith('File:'):
                ext = title.rsplit('.', 1)[-1].lower() if '.' in title else ''
                if ext in ('jpg', 'jpeg', 'png', 'webp'):
                    titles.append(title)
        return titles

    def _get_image_info(self, file_title: str) -> Optional[Dict]:
        """
        Fetch the direct image URL and license metadata for a Wikimedia file.
        Returns a dict with keys: url, page_url, license, attribution, description.
        """
        data = self._api_get({
            'action': 'query',
            'titles': file_title,
            'prop': 'imageinfo',
            'iiprop': 'url|extmetadata',
            'iiurlwidth': 800,   # standard Wikimedia thumbnail size
        })
        if not data:
            return None

        pages = data.get('query', {}).get('pages', {})
        for page in pages.values():
            imageinfo = page.get('imageinfo', [{}])
            if not imageinfo:
                return None
            info = imageinfo[0]
            # Prefer the pre-generated thumbnail (avoids Wikimedia 429 on full-res downloads)
            url = info.get('thumburl') or info.get('url', '')
            original_url = info.get('url', '') or url
            page_url = f"https://commons.wikimedia.org/wiki/{file_title.replace(' ', '_')}"

            extmeta = info.get('extmetadata', {})
            license_str = (
                extmeta.get('LicenseShortName', {}).get('value', '') or
                extmeta.get('License', {}).get('value', '') or
                extmeta.get('UsageTerms', {}).get('value', '')
            )
            attribution = (
                extmeta.get('Attribution', {}).get('value', '') or
                extmeta.get('Artist', {}).get('value', '') or ''
            )
            description = (
                extmeta.get('ImageDescription', {}).get('value', '') or
                extmeta.get('ObjectName', {}).get('value', '') or
                file_title.replace('File:', '').rsplit('.', 1)[0]
            )

            # Strip HTML tags from description
            import re
            description = re.sub(r'<[^>]+>', '', description).strip()
            attribution = re.sub(r'<[^>]+>', '', attribution).strip()
            # Normalize underscores to spaces (filenames-as-fallback use underscores;
            # confidence scoring does substring matching so "american_eagle" ≠ "american eagle")
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
        self,
        bucket: Dict[str, Any],
        file_title: str,
        info: Dict,
    ) -> Dict[str, Any]:
        """Assemble an ImageCandidate dict from bucket + Wikimedia image info."""
        license_str = info.get('license', '')
        source_type = _classify_license(license_str)

        c = self._base_candidate(
            url=info['url'],
            raw_title=info.get('description', file_title),
            page_url=info.get('page_url', ''),
        )
        c['source_type']        = source_type
        c['license_type']       = license_str or None
        c['attribution_text']   = info.get('attribution') or None
        c['original_image_url'] = info.get('original_url') or info['url']
        c['rights_note']        = (
            f"Wikimedia Commons. License: {license_str}. "
            f"Source: {info.get('page_url', '')}"
        ) if license_str else None
        return c
