"""
Open Numismatics adapter — historic US silver coins (junk silver).

Targets: Morgan dollar, Peace dollar, Walking Liberty half, Franklin half,
Mercury dime, Roosevelt dime, Washington quarter.

Uses Wikimedia Commons; all pre-1978 US Mint coins are public domain.
"""
from __future__ import annotations

from typing import Dict, List

import requests

from adapters import BaseAdapter, build_candidate

_API = "https://commons.wikimedia.org/w/api.php"
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "MetexImageAcquisition/1.0 (contact@metex.com)"})

_COIN_QUERIES: Dict[str, List[str]] = {
    "silver-morgan-dollar": [
        "Morgan dollar silver coin obverse United States",
        "Morgan dollar 1878 1921 obverse reverse",
        "Morgan silver dollar coin",
    ],
    "silver-peace-dollar": [
        "Peace dollar silver coin 1921 1935 obverse",
        "Peace dollar United States silver coin",
    ],
    "silver-walking-liberty-half-dollar": [
        "Walking Liberty Half Dollar obverse silver coin",
        "Walking Liberty half dollar 1916 1947",
        "Walking Liberty silver half dollar coin",
    ],
    "silver-franklin-half-dollar": [
        "Franklin half dollar obverse silver coin 1948 1963",
        "Benjamin Franklin half dollar United States",
    ],
    "silver-mercury-dime": [
        "Mercury dime silver coin Winged Liberty Head obverse",
        "Mercury dime 1916 1945 United States",
    ],
    "silver-roosevelt-dime": [
        "Roosevelt dime silver 90 percent obverse",
        "Roosevelt dime 1946 1964 silver coin",
    ],
    "silver-washington-quarter": [
        "Washington quarter silver 90 percent obverse",
        "Washington quarter 1932 1964 silver coin",
    ],
}


class OpenNumismaticsAdapter(BaseAdapter):
    """Historic US silver coins — all public domain pre-1978 US Mint works."""

    name = "Open Numismatics (historic US)"
    source_type = "public_domain"
    source_priority = 2

    def find_candidates(self, bucket: Dict) -> List[Dict]:
        slug = bucket.get("slug", "")
        queries: List[str] = []
        for prefix, qlist in _COIN_QUERIES.items():
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
                        if ii.get("url"):
                            raw_title = title.replace("File:", "").replace("_", " ")
                            candidates.append(build_candidate(
                                url=ii["url"],
                                raw_source_title=raw_title,
                                source_name=self.name,
                                source_type="public_domain",
                                source_page_url=ii.get("descriptionurl", ""),
                                original_image_url=ii["url"],
                                license_type="public_domain",
                                attribution_text="United States Mint (pre-1978 public domain)",
                                rights_note="Pre-1978 US Mint — public domain",
                                usage_allowed=True,
                            ))
                except Exception:
                    continue

        return candidates
