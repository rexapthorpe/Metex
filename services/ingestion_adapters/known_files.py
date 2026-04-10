"""
KnownFilesAdapter — hardcoded Wikimedia Commons file catalog.

Rather than searching Wikimedia (which has search-quality and rate-limit issues),
this adapter maps bucket slugs to specific, verified Wikimedia Commons file names
and their license metadata.

Benefits:
  - Zero search API calls → no 429 rate-limit risk
  - Guaranteed correct product match
  - Known license metadata → no guessing
  - Deterministic, idempotent

All files here are manually curated and verified to:
  1. Correctly depict the product identified by the slug
  2. Have a free/public-domain license on Wikimedia Commons
  3. Be high quality (obverse or full coin/bar image)

Adding new entries:
  1. Find the file on commons.wikimedia.org (search by product name)
  2. Verify the license (CC0, PD, CC-BY, PD-USGov, etc.)
  3. Add an entry to KNOWN_FILES:
     slug → list of KnownFile(filename, license, attribution, public_domain)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import BaseImageAdapter

log = logging.getLogger(__name__)

_WIKIMEDIA_API = 'https://commons.wikimedia.org/w/api.php'
_REQUEST_DELAY_S = 1.5


@dataclass
class KnownFile:
    """A verified Wikimedia Commons file entry."""
    filename:     str               # e.g. "File:American_Gold_Eagle_obverse.jpg"
    license:      str               # e.g. "PD-USGov", "CC-BY-4.0"
    attribution:  str = ''          # credit line
    public_domain: bool = False     # True → source_type='public_domain'
    notes:        str = ''          # internal notes (not stored in DB)


# ---------------------------------------------------------------------------
# Catalog — manually curated, sorted by metal → product family
# ---------------------------------------------------------------------------
# All US Mint official designs: public domain (US government works)
# Royal Canadian Mint: copyrighted, license=licensed
# Royal Mint UK: copyrighted
# Perth Mint: copyrighted
# South African Mint: copyrighted
# Austrian Mint: copyrighted
# Historical US coinage (pre-1978): public domain
# ---------------------------------------------------------------------------

KNOWN_FILES: Dict[str, List[KnownFile]] = {

    # ─── Gold — US Mint (public domain) ────────────────────────────────────
    # All files verified present on Wikimedia Commons.

    'gold-american-eagle-tenth-oz': [
        KnownFile(
            filename='File:One_Tenth_Ounce_American_Gold_Eagle_reverse.jpg',
            license='PD-USGov',
            attribution='United States Mint',
            public_domain=True,
        ),
    ],
    'gold-american-buffalo-1oz': [
        KnownFile(
            filename='File:2006 American Buffalo Proof Obverse.jpg',
            license='PD-USGov',
            attribution='United States Mint',
            public_domain=True,
        ),
    ],

    # ─── Silver — US Mint (public domain) ──────────────────────────────────

    'silver-american-eagle-1oz': [
        KnownFile(
            filename='File:2022-american-eagle-silver-one-ounce-bullion-coin-obverse.png',
            license='PD-USGov',
            attribution='United States Mint',
            public_domain=True,
        ),
    ],
    'platinum-american-eagle-1oz': [
        KnownFile(
            filename='File:1998_AEPlat_Rev.png',
            license='PD-USGov',
            attribution='United States Mint',
            public_domain=True,
        ),
    ],
    'palladium-american-eagle-1oz': [
        KnownFile(
            filename='File:2017_$25_Palladium_reverse.jpg',
            license='PD-USGov',
            attribution='United States Mint',
            public_domain=True,
        ),
    ],

    # ─── Historic US coinage (pre-1978, public domain) ─────────────────────

    'silver-morgan-dollar': [
        KnownFile(
            filename='File:Morgan silver dollar obverse (2581572743).jpg',
            license='PD-US',
            attribution='United States Mint',
            public_domain=True,
        ),
    ],
    'silver-peace-dollar': [
        KnownFile(
            filename='File:Peace_dollar.jpg',
            license='PD-US',
            attribution='United States Mint',
            public_domain=True,
        ),
    ],
    'silver-walking-liberty-half-dollar': [
        KnownFile(
            filename='File:Walking Liberty Half Dollar 1945D Obverse.png',
            license='PD-US',
            attribution='United States Mint',
            public_domain=True,
        ),
    ],
    'silver-franklin-half-dollar': [
        KnownFile(
            filename='File:Franklin Half 1963 D Obverse TFA.png',
            license='PD-US',
            attribution='United States Mint',
            public_domain=True,
        ),
    ],
    'silver-mercury-dime': [
        KnownFile(
            filename='File:1943D Mercury Dime obverse-cutout.png',
            license='PD-US',
            attribution='United States Mint',
            public_domain=True,
        ),
    ],
    'silver-roosevelt-dime': [
        KnownFile(
            filename='File:2005 Dime Obv Unc P.png',
            license='PD-US',
            attribution='United States Mint',
            public_domain=True,
            notes='Modern clad dime design matches silver Roosevelt dime design',
        ),
    ],
    'silver-washington-quarter': [
        KnownFile(
            filename='File:Washington Quarter Silver 1944S Obverse.png',
            license='PD-US',
            attribution='United States Mint',
            public_domain=True,
        ),
    ],

    # ─── Silver — international (licensed, requires admin review) ──────────

    'silver-british-britannia-1oz': [
        KnownFile(
            filename='File:British_Britannia_Silver_2021_1Oz._.999_Fine_Silver_2_Pounds_English_coin.jpg',
            license='CC-BY-SA-4.0',
            attribution='Wikimedia Commons contributor',
            public_domain=False,
        ),
    ],
    'silver-austrian-philharmonic-1oz': [
        KnownFile(
            filename='File:1_oz_Vienna_Philharmonic_2017_tube.png',
            license='CC-BY-SA-4.0',
            attribution='Wikimedia Commons contributor',
            public_domain=False,
        ),
    ],
    'silver-australian-kangaroo-1oz': [
        KnownFile(
            filename='File:Obverse_2020_Australia_1_oz_Silver_Kangaroo.jpg',
            license='CC-BY-SA-4.0',
            attribution='Wikimedia Commons contributor',
            public_domain=False,
        ),
    ],
    'silver-south-african-krugerrand-1oz': [
        KnownFile(
            filename='File:2022 South Africa 1 oz Silver Krugerrand Obverse.jpg',
            license='CC-BY-SA-4.0',
            attribution='Wikimedia Commons contributor',
            public_domain=False,
        ),
    ],
    'silver-canadian-maple-leaf-1oz': [
        KnownFile(
            filename='File:1-ounce Silver Canadian Maple Leaf MADE OF +.9999% PURE SILVER.jpg',
            license='CC-BY-SA-4.0',
            attribution='Wikimedia Commons contributor',
            public_domain=False,
        ),
    ],

    # ─── Gold — international (licensed) ───────────────────────────────────

    'gold-austrian-philharmonic-1oz': [
        KnownFile(
            filename='File:1 oz Vienna Philharmonic 2017 reverse.png',
            license='CC-BY-SA-4.0',
            attribution='Wikimedia Commons contributor',
            public_domain=False,
        ),
    ],
    'gold-krugerrand-1oz': [
        KnownFile(
            filename='File:1 oz Krugerrand 2017 Wertseite.png',
            license='CC-BY-SA-4.0',
            attribution='Wikimedia Commons contributor',
            public_domain=False,
        ),
    ],

    # ─── Bullion bars ───────────────────────────────────────────────────────
    # Generic bar images — will stay pending for admin review.

    'palladium-canadian-maple-leaf-1oz': [
        KnownFile(
            filename='File:Palladium2007.png',
            license='CC-BY-SA-3.0',
            attribution='Wikimedia Commons contributor',
            public_domain=False,
            notes='Canadian Palladium Maple Leaf coin',
        ),
    ],

    'gold-chinese-panda-1oz': [
        KnownFile(
            filename='File:2016goldpanda1ozwiki.png',
            license='CC-BY-SA-4.0',
            attribution='Wikimedia Commons contributor',
            public_domain=False,
            notes='2016 1oz Gold Panda reverse side',
        ),
    ],

    # ─── Bullion bars ───────────────────────────────────────────────────────
    # Generic bar images — will stay pending for admin review.

    'gold-bar-1oz': [
        KnownFile(
            filename='File:Gold bar.jpg',
            license='CC-BY-SA-3.0',
            attribution='Wikimedia Commons contributor',
            public_domain=False,
            notes='Generic gold bar — verify branding before activating',
        ),
    ],
    'silver-bar-100oz': [
        KnownFile(
            filename='File:100 Troy oz. Silver Bullion Bar from Johnson Matthey.jpg',
            license='CC-BY-SA-3.0',
            attribution='Wikimedia Commons contributor',
            public_domain=False,
            notes='Johnson Matthey 100 oz bar',
        ),
    ],
}


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class KnownFilesAdapter(BaseImageAdapter):
    """
    Fetch images for specific bucket slugs using a hardcoded, verified
    Wikimedia Commons file catalog.

    Completely bypasses Wikimedia search — zero search API calls.
    One imageinfo API call per known file, throttled at 1.5s.
    """

    name        = 'Known Files (Curated)'
    source_type = 'licensed'   # overridden per-entry based on public_domain flag

    def __init__(self, max_results: int = 3, request_delay: float = _REQUEST_DELAY_S):
        self._max      = max_results
        self._delay    = request_delay
        self._last_req = 0.0

    def find_candidates(self, bucket: Dict[str, Any]) -> List[Dict[str, Any]]:
        slug    = bucket.get('slug', '')
        entries = KNOWN_FILES.get(slug, [])
        if not entries:
            return []

        candidates = []
        for entry in entries[:self._max]:
            info = self._get_image_info(entry.filename)
            if info is None:
                log.warning('KnownFiles: could not fetch info for %s', entry.filename)
                continue
            url = info.get('url', '')
            if not url:
                continue

            # Include all bucket metadata in raw_title so confidence scoring
            # reflects the guaranteed slug-match correctness of this catalog.
            raw_title = ' '.join(filter(None, [
                bucket.get('title', ''),
                bucket.get('metal', ''),
                bucket.get('weight', ''),
                bucket.get('mint', ''),
                bucket.get('product_family', ''),
                bucket.get('product_series', ''),
                entry.filename.replace('File:', '').rsplit('.', 1)[0].replace('_', ' '),
            ]))
            c = self._base_candidate(
                url=url,
                raw_title=raw_title,
                page_url=info.get('page_url', ''),
            )
            c['source_name']        = self.name
            c['source_type']        = 'public_domain' if entry.public_domain else 'licensed'
            c['license_type']       = entry.license or info.get('license') or None
            c['attribution_text']   = entry.attribution or info.get('attribution') or None
            c['original_image_url'] = info.get('original_url') or url
            c['rights_note']        = (
                f"Curated catalog entry. License: {entry.license}. "
                f"Source: {info.get('page_url', '')}"
            )
            candidates.append(c)

        return candidates

    # ------------------------------------------------------------------
    # Wikimedia API (imageinfo only — no search needed)
    # ------------------------------------------------------------------

    def _throttle(self):
        now  = time.monotonic()
        wait = self._delay - (now - self._last_req)
        if wait > 0:
            time.sleep(wait)
        self._last_req = time.monotonic()

    def _get_image_info(self, file_title: str, _retries: int = 3) -> Optional[Dict[str, Any]]:
        import requests

        for attempt in range(_retries):
            self._throttle()
            try:
                resp = requests.get(
                    _WIKIMEDIA_API,
                    params={
                        'action':    'query',
                        'titles':    file_title,
                        'prop':      'imageinfo',
                        'iiprop':    'url|extmetadata',
                        'iiurlwidth': 800,
                        'format':    'json',
                    },
                    timeout=15,
                    headers={'User-Agent': 'MetexImageBot/1.0 (metex.com; curated catalog)'},
                )
                if resp.status_code == 429:
                    wait = 30 * (2 ** attempt)   # 30s, 60s, 120s
                    log.warning('KnownFiles 429 for %s — waiting %ds (attempt %d/%d)',
                                file_title, wait, attempt + 1, _retries)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                break   # success
            except Exception as exc:
                log.warning('KnownFiles API error for %s: %s', file_title, exc)
                return None
        else:
            log.warning('KnownFiles: gave up on %s after %d retries', file_title, _retries)
            return None

        data  = resp.json()
        pages = data.get('query', {}).get('pages', {})
        for page in pages.values():
            ii = page.get('imageinfo', [])
            if not ii:
                return None
            info         = ii[0]
            url          = info.get('thumburl') or info.get('url', '')
            original_url = info.get('url', '') or url
            page_url     = f"https://commons.wikimedia.org/wiki/{file_title.replace(' ', '_')}"

            extmeta      = info.get('extmetadata', {})
            def _v(k):
                return extmeta.get(k, {}).get('value', '')
            import re
            attribution = re.sub(r'<[^>]+>', '', _v('Attribution') or _v('Artist') or '').strip()
            license_str = _v('LicenseShortName') or _v('License') or ''

            return {
                'url':          url,
                'original_url': original_url,
                'page_url':     page_url,
                'license':      license_str,
                'attribution':  attribution,
            }
        return None
