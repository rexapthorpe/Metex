"""
Refiner/bar adapter — bullion bars (gold, silver, platinum, palladium, copper).

Searches Wikimedia Commons for images of bars from PAMP Suisse, Valcambi,
Sunshine Minting, Engelhard, Johnson Matthey, and generic bar images.

All bar images are licensed (copyright by refiners) — candidates stay pending.
"""
from __future__ import annotations

from typing import Dict, List

import requests

from adapters import BaseAdapter, build_candidate

_API = "https://commons.wikimedia.org/w/api.php"
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "MetexImageAcquisition/1.0 (contact@metex.com)"})

# Slug prefix → list of search queries
_BAR_QUERIES: Dict[str, List[str]] = {
    # Gold bars
    "gold-bar-1g":    ["1 gram gold bar PAMP Suisse bullion", "1g gold bullion bar"],
    "gold-bar-2.5g":  ["2.5 gram gold bar bullion", "2.5g gold bar PAMP"],
    "gold-bar-5g":    ["5 gram gold bar PAMP bullion", "5g gold bar Valcambi"],
    "gold-bar-10g":   ["10 gram gold bar bullion", "10g gold bar PAMP Suisse"],
    "gold-bar-1-4oz": ["quarter ounce gold bar bullion", "1/4 oz gold bar"],
    "gold-bar-1oz":   ["1 oz gold bar PAMP Suisse Lady Fortuna",
                       "one troy ounce gold bar bullion",
                       "gold bar 1 ounce Valcambi"],
    "gold-bar-10oz":  ["10 oz gold bar bullion", "ten ounce gold bar"],
    "gold-bar-1kg":   ["1 kilogram gold bar bullion", "1kg gold bar PAMP",
                       "gold bullion bar kilogram"],
    # Silver bars
    "silver-bar-1oz":   ["1 oz silver bar bullion Sunshine Minting",
                          "one ounce silver bar"],
    "silver-bar-2oz":   ["2 oz silver bar bullion"],
    "silver-bar-5oz":   ["5 oz silver bar bullion Engelhard"],
    "silver-bar-10oz":  ["10 oz silver bar bullion Johnson Matthey",
                          "ten ounce silver bar"],
    "silver-bar-50oz":  ["50 oz silver bar bullion"],
    "silver-bar-100oz": ["100 oz silver bar bullion", "hundred ounce silver bar",
                          "100 troy ounce silver bar"],
    "silver-bar-1kg":   ["1 kilogram silver bar bullion", "1kg silver bar"],
    # Platinum bars
    "platinum-bar-1oz": ["1 oz platinum bar bullion PAMP",
                          "one troy ounce platinum bar"],
    # Palladium bars
    "palladium-bar-1oz": ["1 oz palladium bar bullion",
                           "one troy ounce palladium bar"],
    # Copper bars
    "copper-bar-1oz":   ["1 oz copper bar bullion", "one ounce copper bar"],
    "copper-bar-1lb":   ["1 pound copper bar bullion", "one pound copper bar"],
}

_REFINERS = ["PAMP Suisse", "Valcambi", "Sunshine Minting", "Engelhard", "Johnson Matthey",
             "Perth Mint", "Royal Canadian Mint", "Scottsdale", "SilverTowne", "APMEX"]


class RefinerAdapter(BaseAdapter):
    """Bullion bars — all metals, multiple refiners."""

    name = "Refiner"
    source_type = "licensed"
    source_priority = 4

    def find_candidates(self, bucket: Dict) -> List[Dict]:
        slug = bucket.get("slug", "")

        # Find matching query set (prefix match)
        queries: List[str] = []
        for prefix, qlist in _BAR_QUERIES.items():
            # Convert dash-encoded weight like "gold-bar-1-4oz" → "gold-bar-1/4oz"
            if slug.replace("/", "-").startswith(prefix) or slug.startswith(prefix):
                queries = qlist
                break

        if not queries:
            return []

        candidates: List[Dict] = []
        seen: set = set()

        for query in queries:
            if len(candidates) >= self.max_results:
                break
            self._throttle()
            try:
                r = _SESSION.get(_API, params={
                    "action": "query", "list": "search",
                    "srsearch": query, "srnamespace": "6",
                    "srlimit": self.max_results * 2, "format": "json",
                }, timeout=15)
                r.raise_for_status()
                titles = [
                    t["title"] for t in r.json().get("query", {}).get("search", [])
                    if t.get("title", "").startswith("File:")
                ]
            except Exception:
                continue

            for title in titles:
                if len(candidates) >= self.max_results or title in seen:
                    break
                seen.add(title)
                self._throttle()
                try:
                    r2 = _SESSION.get(_API, params={
                        "action": "query", "titles": title,
                        "prop": "imageinfo", "iiprop": "url",
                        "format": "json",
                    }, timeout=15)
                    r2.raise_for_status()
                    pages = r2.json().get("query", {}).get("pages", {})
                    for page in pages.values():
                        ii = (page.get("imageinfo") or [{}])[0]
                        if not ii.get("url"):
                            continue
                        raw_title = title.replace("File:", "").replace("_", " ")
                        # Try to detect refiner
                        refiner = next(
                            (ref for ref in _REFINERS
                             if ref.lower() in raw_title.lower()),
                            "Various refiners"
                        )
                        candidates.append(build_candidate(
                            url=ii["url"],
                            raw_source_title=raw_title,
                            source_name=self.name,
                            source_type="licensed",
                            source_page_url=ii.get("descriptionurl", ""),
                            original_image_url=ii["url"],
                            license_type="licensed",
                            attribution_text=refiner,
                            rights_note="Refiner licensed image — requires admin review",
                            usage_allowed=True,
                        ))
                except Exception:
                    continue

        return candidates
