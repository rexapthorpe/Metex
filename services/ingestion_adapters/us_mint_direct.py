"""
US Mint Direct Image Adapter.

Fetches coin images directly from usmint.gov official program pages rather
than searching Wikimedia Commons.  Uses og:image metadata from each program
page as the primary image; falls back to main-content <img> tags.

All US government works are in the public domain, so source_type is
'public_domain'.  Candidates with confidence >= 0.75 and no warning flags
are auto-activated by the ingestion pipeline.

Coverage (slug prefixes mapped to program pages):
  gold-american-eagle, gold-american-buffalo, silver-american-eagle,
  platinum-american-eagle, palladium-american-eagle, gold-american-liberty,
  silver-american-liberty, silver-morgan-dollar, silver-peace-dollar,
  silver-america-beautiful, gold-us-commemorative, silver-american-innovation.
"""

import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseImageAdapter

log = logging.getLogger(__name__)

_REQUEST_DELAY_S = 2.0
_HEADERS = {
    'User-Agent': 'MetexImageBot/1.0 (metex.com; numismatic image catalog)',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

# ---------------------------------------------------------------------------
# Slug prefix → (program_page_url, product_title_hint)
#
# product_title_hint is appended to the scraped page title when building
# raw_source_title so confidence scoring has good field overlap.
# ---------------------------------------------------------------------------

_PROGRAM_PAGES: Dict[str, Tuple[str, str]] = {
    'gold-american-eagle': (
        'https://www.usmint.gov/coins/coin-medal-programs/bullion/american-gold-eagle',
        'American Gold Eagle bullion coin gold',
    ),
    'gold-american-buffalo': (
        'https://www.usmint.gov/coins/coin-medal-programs/bullion/american-gold-buffalo',
        'American Gold Buffalo bullion coin gold 24 karat',
    ),
    'silver-american-eagle': (
        'https://www.usmint.gov/coins/coin-medal-programs/bullion/american-silver-eagle',
        'American Silver Eagle bullion coin silver 1 oz',
    ),
    'platinum-american-eagle': (
        'https://www.usmint.gov/coins/coin-medal-programs/bullion/american-platinum-eagle',
        'American Platinum Eagle bullion coin platinum',
    ),
    'palladium-american-eagle': (
        'https://www.usmint.gov/coins/coin-medal-programs/bullion/american-palladium-eagle',
        'American Palladium Eagle bullion coin palladium',
    ),
    'gold-american-liberty': (
        'https://www.usmint.gov/coins/coin-medal-programs/american-liberty',
        'American Liberty gold coin high relief',
    ),
    'silver-american-liberty': (
        'https://www.usmint.gov/coins/coin-medal-programs/american-liberty',
        'American Liberty silver medal',
    ),
    'silver-morgan-dollar': (
        'https://www.usmint.gov/coins/coin-medal-programs/morgan-and-peace-dollar',
        'Morgan silver dollar coin',
    ),
    'silver-peace-dollar': (
        'https://www.usmint.gov/coins/coin-medal-programs/morgan-and-peace-dollar',
        'Peace silver dollar coin',
    ),
    'silver-america-beautiful': (
        'https://www.usmint.gov/coins/coin-medal-programs/america-the-beautiful-quarters',
        'America the Beautiful silver bullion coin',
    ),
    'silver-american-innovation': (
        'https://www.usmint.gov/coins/coin-medal-programs/american-innovation-dollar',
        'American Innovation dollar coin silver',
    ),
    'gold-us-commemorative': (
        'https://www.usmint.gov/coins/coin-medal-programs/commemorative-coins',
        'US Mint commemorative gold coin',
    ),
    'silver-us-commemorative': (
        'https://www.usmint.gov/coins/coin-medal-programs/commemorative-coins',
        'US Mint commemorative silver coin',
    ),
    'gold-first-spouse': (
        'https://www.usmint.gov/coins/coin-medal-programs/first-spouse-gold-coins',
        'First Spouse gold coin US Mint',
    ),
}

# ---------------------------------------------------------------------------
# HTML parsing helpers (regex-based, no external dependency beyond requests)
# ---------------------------------------------------------------------------

def _extract_og_image(html: str) -> Optional[str]:
    """Extract og:image (or twitter:image) URL from page HTML."""
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


def _extract_page_title(html: str) -> str:
    """Extract and clean the <title> text from HTML."""
    m = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
    if not m:
        return ''
    title = m.group(1).strip()
    # Strip trailing " | United States Mint" or similar
    title = re.sub(r'\s*\|\s*United States Mint.*$', '', title, flags=re.IGNORECASE).strip()
    title = re.sub(r'\s*[-–|].*$', '', title).strip()
    return title


def _extract_article_images(html: str, base_url: str) -> List[str]:
    """
    Extract image src URLs from the <main> or <article> content area.
    Returns absolute HTTPS URLs only; skips icons, logos, and tiny thumbnails.
    """
    # Try to isolate main content section
    section_html = html
    for tag in ('main', 'article', 'div[^>]*class=["\'][^"\']*content[^"\']*["\']'):
        m = re.search(
            rf'<{tag}>(.*?)</{tag.split("[")[0]}>',
            html, re.IGNORECASE | re.DOTALL,
        )
        if m:
            section_html = m.group(1)
            break

    # Derive base domain for relative → absolute resolution
    domain_m = re.match(r'(https?://[^/]+)', base_url)
    base_domain = domain_m.group(1) if domain_m else 'https://www.usmint.gov'

    urls: List[str] = []
    skip_fragments = (
        '/icon', '/logo', '/nav', '/flag', '/sprite', '/favicon',
        '/badge', '/seal', '/header', '/footer',
    )
    for m in re.finditer(r'<img\b[^>]+\bsrc=["\']([^"\']+)["\']', section_html, re.IGNORECASE):
        src = m.group(1).strip()
        if not src or src.startswith('data:') or src.endswith('.svg'):
            continue
        # Normalise to absolute
        if src.startswith('//'):
            src = 'https:' + src
        elif src.startswith('/'):
            src = base_domain + src
        elif not src.startswith('http'):
            continue
        if any(frag in src.lower() for frag in skip_fragments):
            continue
        if src not in urls:
            urls.append(src)

    return urls


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class UsMintDirectAdapter(BaseImageAdapter):
    """
    Fetches official coin images directly from usmint.gov program pages.

    Covers: American Eagle series (gold, silver, platinum, palladium),
    American Gold Buffalo, American Liberty, Morgan/Peace Dollars, and other
    US Mint coin programs.  Only buckets whose slug matches a known program
    page prefix are processed; others are skipped silently.

    Source type: public_domain (US government works).
    Auto-activation: eligible when confidence >= 0.75 and no warnings.
    """

    name        = 'US Mint (Official)'
    source_type = 'public_domain'

    def __init__(self, max_results: int = 2, request_delay: float = _REQUEST_DELAY_S):
        self._max      = max_results
        self._delay    = request_delay
        self._last_req = 0.0

    # ------------------------------------------------------------------
    # BaseImageAdapter contract
    # ------------------------------------------------------------------

    def find_candidates(self, bucket: Dict[str, Any]) -> List[Dict[str, Any]]:
        slug = bucket.get('slug', '')
        for prefix, (page_url, hint) in _PROGRAM_PAGES.items():
            if slug.startswith(prefix):
                candidates = self._scrape_program_page(bucket, page_url, hint)
                return candidates[:self._max]
        return []

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
            resp = requests.get(url, headers=_HEADERS, timeout=20, allow_redirects=True)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            log.warning('%s: fetch failed for %s — %s', self.name, url, exc)
            return None

    def _scrape_program_page(
        self, bucket: Dict[str, Any], page_url: str, hint: str
    ) -> List[Dict[str, Any]]:
        html = self._fetch_html(page_url)
        if not html:
            return []

        # Collect candidate image URLs: og:image first, then article images
        image_urls: List[str] = []
        og = _extract_og_image(html)
        if og:
            image_urls.append(og)
        for url in _extract_article_images(html, page_url):
            if url not in image_urls:
                image_urls.append(url)

        if not image_urls:
            log.debug('%s: no images found at %s', self.name, page_url)
            return []

        # Build raw_source_title: page title + product hint for good confidence scoring
        page_title = _extract_page_title(html) or hint
        raw_title = page_title if hint.lower() in page_title.lower() else f'{page_title} — {hint}'

        candidates = []
        for img_url in image_urls:
            c = self._base_candidate(url=img_url, raw_title=raw_title, page_url=page_url)
            c['source_name']        = self.name
            c['source_type']        = self.source_type
            c['license_type']       = 'public_domain'
            c['attribution_text']   = 'United States Mint — US Government Work (Public Domain)'
            c['original_image_url'] = img_url
            c['rights_note'] = (
                'US government work produced by the United States Mint. '
                'Public domain in the United States — may be freely used. '
                f'Source page: {page_url}'
            )
            candidates.append(c)

        return candidates
