"""
Pixabay adapter — free commercial-use images via Pixabay API.

Requires: PIXABAY_API_KEY environment variable.
All Pixabay images are free for commercial use (Pixabay License).
Falls back to empty list if no API key is set.

API docs: https://pixabay.com/api/docs/
"""
from __future__ import annotations

import os
from typing import Dict, List

import requests

from adapters import BaseAdapter, build_candidate

_API_BASE = "https://pixabay.com/api/"
_SESSION = requests.Session()

_SEARCH_TERMS: Dict[str, List[str]] = {
    "gold-american-eagle":     ["american eagle gold coin"],
    "gold-american-buffalo":   ["american buffalo gold coin bullion"],
    "gold-canadian-maple":     ["canadian maple leaf gold coin"],
    "gold-krugerrand":         ["krugerrand gold coin"],
    "gold-austrian-philharmonic": ["austrian philharmonic gold coin"],
    "gold-australian-kangaroo":   ["kangaroo gold coin australia"],
    "gold-british-britannia":  ["britannia gold coin"],
    "gold-chinese-panda":      ["chinese panda gold coin"],
    "gold-bar":                ["gold bullion bar", "gold bar ingot"],
    "silver-american-eagle":   ["american eagle silver coin"],
    "silver-canadian-maple":   ["silver maple leaf coin"],
    "silver-bar":              ["silver bullion bar", "silver bar ingot"],
    "silver-morgan":           ["morgan silver dollar coin"],
    "silver-peace":            ["peace dollar silver coin"],
    "platinum-american-eagle": ["platinum eagle coin"],
    "platinum-bar":            ["platinum bar bullion"],
    "palladium-american-eagle":["palladium eagle coin"],
    "copper-round":            ["copper round coin bullion"],
    "copper-bar":              ["copper bar bullion"],
}


def _build_search_terms(bucket: Dict) -> List[str]:
    slug = bucket.get("slug", "")
    for prefix, terms in _SEARCH_TERMS.items():
        if slug.startswith(prefix):
            return terms
    # Fallback
    metal = bucket.get("metal", "")
    family = bucket.get("product_family", "")
    form = bucket.get("form", "coin")
    weight = bucket.get("weight", "")
    return [f"{family} {weight} {metal} {form} bullion".strip()]


class PixabayAdapter(BaseAdapter):
    """
    Pixabay free image search.
    Disabled (returns []) if PIXABAY_API_KEY is not set.
    """

    name = "Pixabay"
    source_type = "approved_db"   # Pixabay License = free commercial use
    source_priority = 4

    def __init__(self, max_results: int = 5, request_delay: float = 0.5):
        super().__init__(max_results=max_results, request_delay=request_delay)
        self._api_key = os.environ.get("PIXABAY_API_KEY")

    def find_candidates(self, bucket: Dict) -> List[Dict]:
        if not self._api_key:
            return []

        terms = _build_search_terms(bucket)
        candidates: List[Dict] = []
        seen: set = set()

        for term in terms:
            if len(candidates) >= self.max_results:
                break
            self._throttle()
            try:
                r = _SESSION.get(_API_BASE, params={
                    "key": self._api_key,
                    "q": term,
                    "image_type": "photo",
                    "safesearch": "true",
                    "per_page": min(20, self.max_results * 3),
                    "category": "business",
                }, timeout=15)
                r.raise_for_status()
                hits = r.json().get("hits", [])
            except Exception:
                continue

            for hit in hits:
                if len(candidates) >= self.max_results:
                    break
                url = hit.get("largeImageURL") or hit.get("webformatURL", "")
                if not url or url in seen:
                    continue
                seen.add(url)
                tags = hit.get("tags", "")
                user = hit.get("user", "Pixabay contributor")
                page_url = f"https://pixabay.com/photos/{hit.get('id', '')}"
                candidates.append(build_candidate(
                    url=url,
                    raw_source_title=tags,
                    source_name=self.name,
                    source_type="approved_db",
                    source_page_url=page_url,
                    original_image_url=url,
                    license_type="Pixabay License",
                    attribution_text=f"{user} / Pixabay",
                    rights_note="Pixabay License — free for commercial use, no attribution required",
                    usage_allowed=True,
                ))

        return candidates
