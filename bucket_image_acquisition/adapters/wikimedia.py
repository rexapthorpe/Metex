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
_KNOWN: Dict[str, List[Tuple[str, str, str, bool]]] = {
    # --- Gold Eagles ---
    "gold-american-eagle-1oz": [
        ("File:American_Gold_Eagle_coin.jpg", "public_domain", "United States Mint", True),
        ("File:Gold_American_Eagle_obverse.jpg", "public_domain", "United States Mint", True),
    ],
    "gold-american-eagle-half-oz": [
        ("File:Half_Ounce_American_Gold_Eagle_obverse.jpg", "public_domain", "United States Mint", True),
    ],
    "gold-american-eagle-quarter-oz": [
        ("File:Quarter_Ounce_American_Gold_Eagle_obverse.jpg", "public_domain", "United States Mint", True),
    ],
    "gold-american-eagle-tenth-oz": [
        ("File:One_Tenth_Ounce_American_Gold_Eagle_reverse.jpg", "public_domain", "United States Mint", True),
        ("File:Tenth_ounce_gold_eagle_obverse.jpg", "public_domain", "United States Mint", True),
    ],
    # --- Gold Buffalo ---
    "gold-american-buffalo-1oz": [
        ("File:2006goldbufalloboth.jpg", "public_domain", "United States Mint", True),
        ("File:American_Gold_Buffalo_coin.jpg", "public_domain", "United States Mint", True),
    ],
    # --- Gold Maple Leaf ---
    "gold-canadian-maple-leaf-1oz": [
        ("File:Gold_Maple_Leaf_coin_obverse.jpg", "CC-BY-SA-3.0", "Royal Canadian Mint", False),
    ],
    "gold-canadian-maple-leaf-half-oz": [
        ("File:Gold_maple_half_oz.jpg", "CC-BY-SA-3.0", "Royal Canadian Mint", False),
    ],
    "gold-canadian-maple-leaf-quarter-oz": [
        ("File:Gold_maple_quarter_oz.jpg", "CC-BY-SA-3.0", "Royal Canadian Mint", False),
    ],
    "gold-canadian-maple-leaf-tenth-oz": [
        ("File:Gold_maple_tenth_oz.jpg", "CC-BY-SA-3.0", "Royal Canadian Mint", False),
    ],
    # --- Gold Krugerrand ---
    "gold-krugerrand-1oz": [
        ("File:Krugerrand_gold_coin.jpg", "CC-BY-SA-3.0", "Wikimedia Commons contributor", False),
        ("File:Krugerrand_1oz_front.jpg", "CC-BY-SA-3.0", "Wikimedia Commons contributor", False),
    ],
    "gold-krugerrand-half-oz": [
        ("File:Krugerrand_half_oz.jpg", "CC-BY-SA-3.0", "Wikimedia Commons contributor", False),
    ],
    "gold-krugerrand-quarter-oz": [
        ("File:Krugerrand_quarter_oz.jpg", "CC-BY-SA-3.0", "Wikimedia Commons contributor", False),
    ],
    "gold-krugerrand-tenth-oz": [
        ("File:Krugerrand_tenth_oz.jpg", "CC-BY-SA-3.0", "Wikimedia Commons contributor", False),
    ],
    # --- Gold Philharmonic ---
    "gold-austrian-philharmonic-1oz": [
        ("File:Vienna_Philharmonic_obverse_2002.jpg", "CC-BY-SA-3.0", "Wikimedia Commons contributor", False),
        ("File:Gold_Vienna_Philharmonic_coin.jpg", "CC-BY-SA-3.0", "Wikimedia Commons contributor", False),
    ],
    # --- Gold Kangaroo ---
    "gold-australian-kangaroo-1oz": [
        ("File:Perth_Mint_Gold_Kangaroo_1oz.jpg", "CC-BY-SA-3.0", "Perth Mint", False),
    ],
    "gold-australian-kangaroo-half-oz": [
        ("File:Perth_Mint_Gold_Kangaroo_half_oz.jpg", "CC-BY-SA-3.0", "Perth Mint", False),
    ],
    # --- Gold Britannia ---
    "gold-british-britannia-1oz": [
        ("File:2013_Gold_Britannia_coin.jpg", "CC-BY-SA-3.0", "Royal Mint", False),
    ],
    # --- Gold Panda ---
    "gold-chinese-panda-1oz": [
        ("File:China_Gold_Panda_1_oz_coin.jpg", "CC-BY-SA-3.0", "Wikimedia Commons contributor", False),
    ],
    # --- Gold Bars ---
    "gold-bar-1oz": [
        ("File:Gold_bar.jpg", "CC-BY-SA-3.0", "Wikimedia Commons contributor", False),
        ("File:1oz_gold_bar_PAMP_Suisse.jpg", "CC-BY-SA-3.0", "Wikimedia Commons contributor", False),
    ],
    "gold-bar-10oz": [
        ("File:10oz_gold_bar.jpg", "CC-BY-SA-3.0", "Wikimedia Commons contributor", False),
    ],
    "gold-bar-1kg": [
        ("File:Gold_bullion_bar.jpg", "CC-BY-SA-3.0", "Wikimedia Commons contributor", False),
    ],
    # --- Silver Eagle ---
    "silver-american-eagle-1oz": [
        ("File:Silver_Eagle_2006_Proof_Obv.jpg", "public_domain", "United States Mint", True),
        ("File:American_Silver_Eagle_coin.jpg", "public_domain", "United States Mint", True),
    ],
    # --- Silver Maple ---
    "silver-canadian-maple-leaf-1oz": [
        ("File:Silver_Maple_Leaf_coin.jpg", "CC-BY-SA-3.0", "Royal Canadian Mint", False),
    ],
    # --- Silver Philharmonic ---
    "silver-austrian-philharmonic-1oz": [
        ("File:Silver_Vienna_Philharmonic_1oz.jpg", "CC-BY-SA-3.0", "Austrian Mint", False),
    ],
    # --- Silver Kangaroo ---
    "silver-australian-kangaroo-1oz": [
        ("File:Perth_Mint_Silver_Kangaroo_1oz.jpg", "CC-BY-SA-3.0", "Perth Mint", False),
    ],
    # --- Silver Britannia ---
    "silver-british-britannia-1oz": [
        ("File:Silver_Britannia_2015.jpg", "CC-BY-SA-3.0", "Royal Mint", False),
    ],
    # --- Silver Krugerrand ---
    "silver-south-african-krugerrand-1oz": [
        ("File:Silver_Krugerrand_1oz_2017.jpg", "CC-BY-SA-3.0", "Wikimedia Commons contributor", False),
    ],
    # --- Historic US Silver ---
    "silver-morgan-dollar": [
        ("File:Morgan_dollar_obverse.jpg", "public_domain", "United States Mint", True),
        ("File:Morgan_dollar_coin.jpg", "public_domain", "United States Mint", True),
    ],
    "silver-peace-dollar": [
        ("File:Peace_dollar_obverse.jpg", "public_domain", "United States Mint", True),
    ],
    "silver-walking-liberty-half-dollar": [
        ("File:Walking_Liberty_Half_Dollar_1943_Obverse.jpg", "public_domain", "United States Mint", True),
    ],
    "silver-franklin-half-dollar": [
        ("File:Franklin_half_dollar_obverse.jpg", "public_domain", "United States Mint", True),
    ],
    "silver-mercury-dime": [
        ("File:Mercury_dime_obverse.jpg", "public_domain", "United States Mint", True),
    ],
    "silver-roosevelt-dime": [
        ("File:Roosevelt_dime_obverse.jpg", "public_domain", "United States Mint", True),
    ],
    "silver-washington-quarter": [
        ("File:Washington_quarter_obverse.jpg", "public_domain", "United States Mint", True),
    ],
    # --- Silver Bars ---
    "silver-bar-1oz": [
        ("File:1oz_silver_bar.jpg", "CC-BY-SA-3.0", "Wikimedia Commons contributor", False),
    ],
    "silver-bar-10oz": [
        ("File:10oz_silver_bar.jpg", "CC-BY-SA-3.0", "Wikimedia Commons contributor", False),
    ],
    "silver-bar-100oz": [
        ("File:100oz_silver_bar.jpg", "CC-BY-SA-3.0", "Wikimedia Commons contributor", False),
    ],
    # --- Platinum Eagle ---
    "platinum-american-eagle-1oz": [
        ("File:Platinum_American_Eagle_obverse_2014.jpg", "public_domain", "United States Mint", True),
    ],
    # --- Palladium Eagle ---
    "palladium-american-eagle-1oz": [
        ("File:2019_Palladium_American_Eagle_obverse.jpg", "public_domain", "United States Mint", True),
    ],
    # --- Platinum Maple ---
    "platinum-canadian-maple-leaf-1oz": [
        ("File:Platinum_maple_leaf_1oz.jpg", "CC-BY-SA-3.0", "Royal Canadian Mint", False),
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
            c = build_candidate(
                url=info["url"],
                raw_source_title=file_title.replace("File:", "").replace("_", " "),
                source_name=self.name,
                source_type=src_type,
                source_page_url=info.get("page_url", ""),
                original_image_url=info["url"],
                license_type=license_str,
                attribution_text=attribution,
                rights_note=f"License: {license_str}",
                usage_allowed=True,
            )
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
