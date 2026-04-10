"""
Royal Canadian Mint adapter — Maple Leaf coins (gold, silver, platinum, palladium).

Images are RCM-licensed (copyright). All candidates stay pending; admin must review.
Source searches Wikimedia Commons for RCM product images.
"""
from __future__ import annotations

from typing import Dict, List

import requests

from adapters import BaseAdapter, build_candidate

_API = "https://commons.wikimedia.org/w/api.php"
_HEADERS = {"User-Agent": "MetexImageAcquisition/1.0 (contact@metex.com)"}
_SESSION = requests.Session()
_SESSION.headers.update(_HEADERS)

_PRODUCT_QUERIES: Dict[str, List[str]] = {
    # Gold Maple
    "gold-canadian-maple-leaf-1oz":     ["Gold Maple Leaf coin 1 oz Royal Canadian Mint",
                                          "Canadian Gold Maple 1 ounce bullion"],
    "gold-canadian-maple-leaf-half-oz": ["Gold Maple Leaf half ounce Royal Canadian Mint",
                                          "Canadian Gold Maple 1/2 oz"],
    "gold-canadian-maple-leaf-quarter-oz": ["Gold Maple Leaf quarter ounce Royal Canadian Mint"],
    "gold-canadian-maple-leaf-tenth-oz": ["Gold Maple Leaf one-tenth ounce Royal Canadian Mint"],
    # Silver Maple
    "silver-canadian-maple-leaf-1oz":   ["Silver Maple Leaf coin 1 oz Royal Canadian Mint",
                                          "Canadian Silver Maple 1 ounce bullion"],
    # Platinum Maple
    "platinum-canadian-maple-leaf-1oz": ["Platinum Maple Leaf coin 1 oz Royal Canadian Mint",
                                          "Canadian Platinum Maple 1 ounce"],
    # Palladium Maple
    "palladium-canadian-maple-leaf-1oz": ["Palladium Maple Leaf coin 1 oz Royal Canadian Mint"],
}


def _search_and_fetch(query: str, limit: int) -> List[Dict]:
    results = []
    try:
        r = _SESSION.get(_API, params={
            "action": "query", "list": "search",
            "srsearch": query, "srnamespace": "6",
            "srlimit": limit, "format": "json",
        }, timeout=15)
        r.raise_for_status()
        titles = [
            res["title"] for res in r.json().get("query", {}).get("search", [])
            if res.get("title", "").startswith("File:")
        ]
    except Exception:
        return []

    for title in titles[:limit]:
        try:
            r2 = _SESSION.get(_API, params={
                "action": "query", "titles": title,
                "prop": "imageinfo", "iiprop": "url|size|mime",
                "format": "json",
            }, timeout=15)
            r2.raise_for_status()
            pages = r2.json().get("query", {}).get("pages", {})
            for page in pages.values():
                ii = (page.get("imageinfo") or [{}])[0]
                if ii.get("url"):
                    results.append({
                        "url": ii["url"],
                        "page_url": ii.get("descriptionurl", ""),
                        "title": title,
                    })
        except Exception:
            continue
    return results


class RcmAdapter(BaseAdapter):
    """Royal Canadian Mint — Maple Leaf family."""

    name = "Royal Canadian Mint"
    source_type = "licensed"
    source_priority = 3

    def find_candidates(self, bucket: Dict) -> List[Dict]:
        slug = bucket.get("slug", "")
        queries: List[str] = []
        for prefix, qlist in _PRODUCT_QUERIES.items():
            if slug.startswith(prefix):
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
            items = _search_and_fetch(query, limit=self.max_results * 2)
            for item in items:
                url = item["url"]
                if url in seen or len(candidates) >= self.max_results:
                    continue
                seen.add(url)
                raw_title = item["title"].replace("File:", "").replace("_", " ")
                c = build_candidate(
                    url=url,
                    raw_source_title=raw_title,
                    source_name=self.name,
                    source_type="licensed",
                    source_page_url=item.get("page_url", ""),
                    original_image_url=url,
                    license_type="licensed",
                    attribution_text="Royal Canadian Mint",
                    rights_note="RCM licensed image — requires admin review",
                    usage_allowed=True,
                )
                candidates.append(c)

        return candidates
