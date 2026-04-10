"""
Wikimedia Commons adapters.

Two classes:
  KnownFilesAdapter  — zero-search, curated file catalog (highest precision)
  WikimediaAdapter   — generic search via Commons API (broad catch-all)
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

import requests

from adapters import BaseAdapter, build_candidate

# ---------------------------------------------------------------------------
# Wikimedia API helpers
# ---------------------------------------------------------------------------

_API = "https://commons.wikimedia.org/w/api.php"
_HEADERS = {"User-Agent": "MetexImageAcquisition/1.0 (contact@metex.com)"}
_SESSION = requests.Session()
_SESSION.headers.update(_HEADERS)


def _api_get(params: dict, retries: int = 3) -> dict:
    delay = 30
    for attempt in range(retries):
        try:
            r = _SESSION.get(_API, params=params, timeout=15)
            if r.status_code == 429:
                time.sleep(delay)
                delay *= 2
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(5)
    return {}


def _get_imageinfo(file_title: str) -> Optional[dict]:
    """Fetch URL + metadata for a single File: page."""
    data = _api_get({
        "action": "query",
        "titles": file_title,
        "prop": "imageinfo|extmetadata",
        "iiprop": "url|size|mime|extmetadata",
        "iiextmetadatafilter": "License|LicenseShortName|Artist|ImageDescription",
        "format": "json",
    })
    pages = (data.get("query") or {}).get("pages") or {}
    for page in pages.values():
        ii = (page.get("imageinfo") or [{}])[0]
        if not ii.get("url"):
            continue
        meta = ii.get("extmetadata") or {}
        license_raw = (meta.get("LicenseShortName") or {}).get("value", "")
        artist = (meta.get("Artist") or {}).get("value", "")
        desc = (meta.get("ImageDescription") or {}).get("value", "")
        return {
            "url": ii["url"],
            "page_url": ii.get("descriptionurl", ""),
            "mime": ii.get("mime", ""),
            "width": ii.get("width"),
            "height": ii.get("height"),
            "license": license_raw,
            "attribution": artist or "Wikimedia Commons contributor",
            "description": desc,
        }
    return None


def _classify_license(license_str: str) -> Tuple[str, str]:
    """Return (source_type, rights_note)."""
    s = license_str.lower()
    PD_MARKERS = ["public_domain", "pd-", "cc0", "cc-zero", "us government",
                  "usgov", "pdm", "pd ", "public domain"]
    BLOCKED = ["all rights reserved", "copyright", "non-commercial", "no derivative",
               " nd", "arr", "no-deriv"]
    if any(m in s for m in BLOCKED):
        return "blocked", "License does not permit reuse"
    if any(m in s for m in PD_MARKERS):
        return "public_domain", f"License: {license_str}"
    return "licensed", f"License: {license_str}"


# ---------------------------------------------------------------------------
# Known-files adapter
# ---------------------------------------------------------------------------

# Curated map: slug → list of (wikimedia_file_title, license, attribution, is_pd)
# All entries verified to exist on Wikimedia Commons via API.
_KNOWN: Dict[str, List[Tuple[str, str, str, bool]]] = {
    # --- Gold Eagles (US Mint = public domain) ---
    "gold-american-eagle-1oz": [
        ("File:Liberty $50 Obverse.png", "public_domain", "United States Mint", True),
        ("File:2006 AEGold Proof Obv.png", "public_domain", "United States Mint", True),
    ],
    "gold-american-eagle-tenth-oz": [
        ("File:One Tenth Ounce American Gold Eagle reverse.jpg", "public_domain", "United States Mint", True),
    ],
    # --- Gold Buffalo (US Mint = public domain) ---
    "gold-american-buffalo-1oz": [
        ("File:2006 American Buffalo Proof Obverse.jpg", "public_domain", "United States Mint", True),
        ("File:American buffalo proof vertical edit.jpg", "public_domain", "United States Mint", True),
    ],
    "gold-american-buffalo-half-oz": [
        ("File:2008 American Buffalo $25 half ounce proof coin (obverse).jpg", "public_domain", "United States Mint", True),
    ],
    "gold-american-buffalo-quarter-oz": [
        ("File:2008 American Buffalo $10 quarter ounce proof coin (obverse).jpg", "public_domain", "United States Mint", True),
    ],
    "gold-american-buffalo-tenth-oz": [
        ("File:2008 American Buffalo $5 tenth ounce proof coin (obverse).jpg", "public_domain", "United States Mint", True),
    ],
    # --- Gold Krugerrand (CC0 = public domain equivalent) ---
    "gold-krugerrand-1oz": [
        ("File:1975 1 oz krugerrand obverse.jpg", "CC0", "Wikimedia Commons contributor", True),
    ],
    # --- Gold Philharmonic (licensed CC BY-SA 3.0) ---
    "gold-austrian-philharmonic-1oz": [
        ("File:Wiener Philharmoniker coin Obverse.jpg", "CC-BY-SA-3.0", "Wikimedia Commons contributor", False),
        ("File:1 oz Vienna Philharmonic 2017 averse.png", "CC-BY-SA-4.0", "Wikimedia Commons contributor", False),
    ],
    # --- Gold bar (licensed CC BY-SA 4.0) ---
    "gold-bar-1oz": [
        ("File:Gold bar.jpg", "CC-BY-SA-4.0", "Wikimedia Commons contributor", False),
    ],
    "gold-bar-10oz": [
        ("File:Gold bar.jpg", "CC-BY-SA-4.0", "Wikimedia Commons contributor", False),
    ],
    # --- Silver Eagle (US Mint = public domain) ---
    "silver-american-eagle-1oz": [
        ("File:2022-american-eagle-silver-one-ounce-bullion-coin-obverse.png", "public_domain", "United States Mint", True),
        ("File:American Silver Eagle, obverse, 2022.jpg", "public_domain", "United States Mint", True),
    ],
    # --- Silver Maple (licensed CC BY-SA 4.0) ---
    "silver-canadian-maple-leaf-1oz": [
        ("File:1-ounce Silver Canadian Maple Leaf MADE OF +.9999% PURE SILVER.jpg", "CC-BY-SA-4.0", "Wikimedia Commons contributor", False),
    ],
    # --- Silver Kangaroo (licensed CC BY-SA 4.0) ---
    "silver-australian-kangaroo-1oz": [
        ("File:Obverse 2020 Australia 1 oz Silver Kangaroo.jpg", "CC-BY-SA-4.0", "Perth Mint/Wikimedia", False),
    ],
    # --- Historic US Silver (pre-1978 US Mint = public domain) ---
    "silver-morgan-dollar": [
        ("File:Morgansilverdollar 1882circulated.jpg", "CC0", "Wikimedia Commons contributor", True),
    ],
    "silver-peace-dollar": [
        ("File:Peace dollar.jpg", "public_domain", "United States Mint", True),
    ],
    "silver-walking-liberty-half-dollar": [
        ("File:Walking Liberty Half Dollar 1945D Obverse.png", "public_domain", "United States Mint", True),
    ],
    "silver-franklin-half-dollar": [
        ("File:Franklin Half 1963 D Obverse.png", "public_domain", "United States Mint", True),
    ],
    "silver-mercury-dime": [
        ("File:Mercury dime.jpg", "public_domain", "United States Mint", True),
    ],
    "silver-roosevelt-dime": [
        ("File:2015-W proof Roosevelt dime obverse.jpg", "public_domain", "United States Mint", True),
    ],
    "silver-washington-quarter": [
        ("File:Washington Quarter Silver 1944S Obverse.png", "public_domain", "United States Mint", True),
    ],
    # --- Platinum Eagle (US Mint = public domain) ---
    "platinum-american-eagle-1oz": [
        ("File:American Platinum Eagle 2007 Obv.jpg", "public_domain", "United States Mint", True),
        ("File:2005 AEPlat Proof Obv.png", "public_domain", "United States Mint", True),
    ],
    # --- Palladium Eagle (US Mint = public domain) ---
    "palladium-american-eagle-1oz": [
        ("File:2017 $25 Palladium obverse.jpg", "public_domain", "United States Mint", True),
        ("File:2017 $25 Palladium reverse.jpg", "public_domain", "United States Mint", True),
    ],
}


class KnownFilesAdapter(BaseAdapter):
    """
    Zero-search adapter: directly fetches imageinfo for pre-verified
    Wikimedia filenames. No query noise, no rate-limit risk beyond one
    API call per file.
    """

    name = "Wikimedia Commons (curated)"
    source_type = "public_domain"  # overridden per-file below
    source_priority = 1

    def find_candidates(self, bucket: Dict) -> List[Dict]:
        slug = bucket.get("slug", "")
        files = _KNOWN.get(slug)
        if not files:
            return []

        # Build a synthetic descriptive title from bucket specs so confidence
        # scoring reflects the verified match, not the abbreviated filename.
        metal  = bucket.get("metal", "")
        weight = bucket.get("weight", "")
        family = bucket.get("product_family", "")
        mint   = bucket.get("mint", "")
        synthetic_title = " ".join(p for p in [family, weight, metal, mint] if p)

        candidates: List[Dict] = []
        for file_title, license_str, attribution, is_pd in files[:self.max_results]:
            self._throttle()
            try:
                info = _get_imageinfo(file_title)
            except Exception:
                continue
            if not info:
                continue
            src_type = "public_domain" if is_pd else "licensed"
            # Use synthetic title for scoring; keep real file title in extra_metadata.
            c = build_candidate(
                url=info["url"],
                raw_source_title=synthetic_title or file_title.replace("File:", "").replace("_", " "),
                source_name=self.name,
                source_type=src_type,
                source_page_url=info.get("page_url", ""),
                original_image_url=info["url"],
                license_type=license_str,
                attribution_text=attribution,
                rights_note=f"License: {license_str}",
                usage_allowed=True,
            )
            c.setdefault("extra_metadata", {})["wikimedia_file_title"] = file_title
            candidates.append(c)

        return candidates


# ---------------------------------------------------------------------------
# Generic Wikimedia search adapter
# ---------------------------------------------------------------------------

_QUERY_TEMPLATES = [
    "{family} {weight} {metal} {form} bullion",
    "{mint} {weight} {metal} {form}",
    "{metal} {weight} {form} bullion",
    "{metal} bullion coin",
]


def _build_queries(bucket: Dict) -> List[str]:
    metal  = bucket.get("metal", "")
    weight = bucket.get("weight", "")
    mint   = bucket.get("mint", "")
    family = bucket.get("product_family", "")
    form   = bucket.get("form", "coin")
    queries = []
    for tmpl in _QUERY_TEMPLATES:
        q = tmpl.format(
            metal=metal, weight=weight, mint=mint, family=family, form=form
        ).strip()
        # collapse multiple spaces
        q = " ".join(q.split())
        if q and q not in queries:
            queries.append(q)
    return queries


def _search_files(query: str, limit: int = 10) -> List[str]:
    """Return list of File: titles matching query."""
    data = _api_get({
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srnamespace": "6",  # File namespace
        "srlimit": limit,
        "format": "json",
    })
    results = (data.get("query") or {}).get("search") or []
    titles = []
    for r in results:
        t = r.get("title", "")
        if t.startswith("File:") and any(
            t.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]
        ):
            titles.append(t)
    return titles


class WikimediaAdapter(BaseAdapter):
    """Generic Wikimedia Commons search. Tries 1–3 query variants per bucket."""

    name = "Wikimedia Commons"
    source_type = "licensed"  # reclassified per file
    source_priority = 5

    def find_candidates(self, bucket: Dict) -> List[Dict]:
        queries = _build_queries(bucket)
        seen_titles: set = set()
        candidates: List[Dict] = []

        for query in queries:
            if len(candidates) >= self.max_results:
                break
            self._throttle()
            try:
                titles = _search_files(query, limit=self.max_results * 3)
            except Exception:
                continue

            for title in titles:
                if title in seen_titles or len(candidates) >= self.max_results:
                    break
                seen_titles.add(title)
                self._throttle()
                try:
                    info = _get_imageinfo(title)
                except Exception:
                    continue
                if not info:
                    continue
                src_type, rights_note = _classify_license(info.get("license", ""))
                if src_type == "blocked":
                    continue
                raw_title = title.replace("File:", "").replace("_", " ")
                c = build_candidate(
                    url=info["url"],
                    raw_source_title=raw_title,
                    source_name=self.name,
                    source_type=src_type,
                    source_page_url=info.get("page_url", ""),
                    original_image_url=info["url"],
                    license_type=info.get("license", ""),
                    attribution_text=info.get("attribution", ""),
                    rights_note=rights_note,
                    usage_allowed=True,
                )
                candidates.append(c)

        return candidates
