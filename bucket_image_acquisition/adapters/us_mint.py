"""
US Mint adapter — public domain images of American Eagle, Buffalo,
Platinum Eagle, and Palladium Eagle coins.

All US Mint images are US Government works (public domain).
These can auto-activate in Metex if confidence ≥ 0.75.
"""
from __future__ import annotations

import time
from typing import Dict, List

import requests

from adapters import BaseAdapter, build_candidate

_API = "https://commons.wikimedia.org/w/api.php"
_HEADERS = {"User-Agent": "MetexImageAcquisition/1.0 (contact@metex.com)"}
_SESSION = requests.Session()
_SESSION.headers.update(_HEADERS)

# Slug prefix → list of Wikimedia search queries (most specific first)
_PRODUCT_QUERIES: Dict[str, List[str]] = {
    # Gold
    "gold-american-eagle-1oz":          ["American Gold Eagle bullion coin 1 oz United States Mint",
                                          "Gold Eagle 1 ounce coin US Mint obverse"],
    "gold-american-eagle-half-oz":       ["American Gold Eagle half ounce US Mint",
                                          "1/2 oz Gold Eagle coin United States Mint"],
    "gold-american-eagle-quarter-oz":    ["American Gold Eagle quarter ounce US Mint",
                                          "1/4 oz Gold Eagle coin United States Mint"],
    "gold-american-eagle-tenth-oz":      ["American Gold Eagle one-tenth ounce coin US Mint",
                                          "1/10 oz Gold Eagle United States Mint"],
    "gold-american-buffalo-1oz":         ["American Gold Buffalo 1 oz coin US Mint 24 karat",
                                          "Gold Buffalo bullion coin United States Mint"],
    # Silver
    "silver-american-eagle-1oz":         ["American Silver Eagle bullion coin 1 oz United States Mint",
                                          "Silver Eagle 1 ounce US Mint obverse"],
    # Platinum
    "platinum-american-eagle-1oz":       ["Platinum Eagle bullion coin 1 oz US Mint",
                                          "American Platinum Eagle one ounce"],
    "platinum-american-eagle-quarter-oz":["Platinum Eagle quarter ounce US Mint"],
    "platinum-american-eagle-tenth-oz":  ["Platinum Eagle one-tenth ounce US Mint"],
    # Palladium
    "palladium-american-eagle-1oz":      ["Palladium Eagle bullion coin 1 oz US Mint",
                                          "American Palladium Eagle one ounce"],
}


def _search_commons(query: str, limit: int = 10) -> List[str]:
    try:
        r = _SESSION.get(_API, params={
            "action": "query", "list": "search",
            "srsearch": query, "srnamespace": "6",
            "srlimit": limit, "format": "json",
        }, timeout=15)
        r.raise_for_status()
        results = r.json().get("query", {}).get("search", [])
        return [
            res["title"] for res in results
            if res.get("title", "").startswith("File:")
            and any(res["title"].lower().endswith(e) for e in [".jpg", ".jpeg", ".png"])
        ]
    except Exception:
        return []


def _get_imageinfo(file_title: str) -> Dict:
    try:
        r = _SESSION.get(_API, params={
            "action": "query", "titles": file_title,
            "prop": "imageinfo", "iiprop": "url|size|mime",
            "format": "json",
        }, timeout=15)
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
        for page in pages.values():
            ii = (page.get("imageinfo") or [{}])[0]
            if ii.get("url"):
                return {"url": ii["url"],
                        "page_url": ii.get("descriptionurl", ""),
                        "mime": ii.get("mime", "")}
    except Exception:
        pass
    return {}


class UsMintAdapter(BaseAdapter):
    """US Mint public-domain images via Wikimedia Commons."""

    name = "US Mint (public domain)"
    source_type = "public_domain"
    source_priority = 2

    def find_candidates(self, bucket: Dict) -> List[Dict]:
        slug = bucket.get("slug", "")

        # Find matching query list
        queries: List[str] = []
        for prefix, qlist in _PRODUCT_QUERIES.items():
            if slug.startswith(prefix):
                queries = qlist
                break

        if not queries:
            return []

        seen: set = set()
        candidates: List[Dict] = []

        for query in queries:
            if len(candidates) >= self.max_results:
                break
            self._throttle()
            titles = _search_commons(query, limit=self.max_results * 2)
            for title in titles:
                if title in seen or len(candidates) >= self.max_results:
                    break
                seen.add(title)
                self._throttle()
                info = _get_imageinfo(title)
                if not info:
                    continue
                raw_title = title.replace("File:", "").replace("_", " ")
                c = build_candidate(
                    url=info["url"],
                    raw_source_title=raw_title,
                    source_name=self.name,
                    source_type="public_domain",
                    source_page_url=info.get("page_url", ""),
                    original_image_url=info["url"],
                    license_type="public_domain",
                    attribution_text="United States Mint / US Government",
                    rights_note="US Government work — public domain",
                    usage_allowed=True,
                )
                candidates.append(c)

        return candidates
