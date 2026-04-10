"""
Perth Mint adapter — Kangaroo, Kookaburra, and Koala coins (gold and silver).

Licensed images. All candidates require admin review.
"""
from __future__ import annotations

from typing import Dict, List

import requests

from adapters import BaseAdapter, build_candidate

_API = "https://commons.wikimedia.org/w/api.php"
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "MetexImageAcquisition/1.0 (contact@metex.com)"})

_PRODUCT_QUERIES: Dict[str, List[str]] = {
    "gold-australian-kangaroo-1oz": [
        "Perth Mint gold kangaroo 1 oz coin Australia",
        "Australian Gold Nugget Kangaroo coin bullion",
    ],
    "gold-australian-kangaroo-half-oz": [
        "Perth Mint gold kangaroo half ounce coin",
        "Australian Gold Kangaroo 1/2 oz",
    ],
    "silver-australian-kangaroo-1oz": [
        "Perth Mint silver kangaroo 1 oz coin Australia",
        "Australian Silver Kangaroo bullion coin",
    ],
    "silver-australian-kookaburra-1oz": [
        "Perth Mint silver kookaburra 1 oz coin Australia",
        "Australian Silver Kookaburra bullion coin",
    ],
    "silver-australian-koala-1oz": [
        "Perth Mint silver koala 1 oz coin Australia",
        "Australian Silver Koala bullion coin",
    ],
}


class PerthMintAdapter(BaseAdapter):
    """Perth Mint — Kangaroo, Kookaburra, Koala families."""

    name = "Perth Mint"
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
                if len(candidates) >= self.max_results:
                    break
                if title in seen:
                    continue
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
                        if ii.get("url"):
                            raw_title = title.replace("File:", "").replace("_", " ")
                            candidates.append(build_candidate(
                                url=ii["url"],
                                raw_source_title=raw_title,
                                source_name=self.name,
                                source_type="licensed",
                                source_page_url=ii.get("descriptionurl", ""),
                                original_image_url=ii["url"],
                                license_type="licensed",
                                attribution_text="Perth Mint",
                                rights_note="Perth Mint licensed image — requires admin review",
                                usage_allowed=True,
                            ))
                except Exception:
                    continue

        return candidates
