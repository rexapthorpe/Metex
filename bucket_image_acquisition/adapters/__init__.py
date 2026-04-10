"""
Base adapter contract for image acquisition sources.

Every source adapter must:
  1. Subclass BaseAdapter
  2. Set name, source_type, source_priority
  3. Implement find_candidates(bucket) -> List[Candidate]

Candidate is a plain dict; use build_candidate() to ensure all fields are present.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any


# ---------------------------------------------------------------------------
# Candidate schema
# ---------------------------------------------------------------------------

def build_candidate(
    url: str,
    raw_source_title: str,
    source_name: str,
    source_type: str,
    source_page_url: str = "",
    original_image_url: str = "",
    license_type: str = "unknown",
    attribution_text: str = "",
    rights_note: str = "",
    usage_allowed: bool = True,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Dict:
    """Return a fully-populated Candidate dict."""
    return {
        "url": url,
        "raw_source_title": raw_source_title,
        "source_name": source_name,
        "source_type": source_type,
        "source_page_url": source_page_url,
        "original_image_url": original_image_url or url,
        "license_type": license_type,
        "attribution_text": attribution_text,
        "rights_note": rights_note,
        "usage_allowed": usage_allowed,
        "extra_metadata": extra_metadata or {},
    }


# ---------------------------------------------------------------------------
# Base adapter
# ---------------------------------------------------------------------------

class BaseAdapter(ABC):
    """Abstract base class for all image acquisition adapters."""

    # Subclasses must set these
    name: str = "unnamed"
    source_type: str = "unknown"  # public_domain | licensed | approved_db | retailer | unknown
    source_priority: int = 99

    def __init__(self, max_results: int = 5, request_delay: float = 1.0):
        self.max_results = max_results
        self.request_delay = request_delay
        self._last_request: float = 0.0

    def _throttle(self) -> None:
        """Enforce per-adapter rate limiting."""
        elapsed = time.time() - self._last_request
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self._last_request = time.time()

    @abstractmethod
    def find_candidates(self, bucket: Dict) -> List[Dict]:
        """
        Given a standard_bucket dict, return up to self.max_results Candidate dicts.

        bucket keys (from standard_buckets table):
            slug, title, metal, form, weight, weight_oz, denomination,
            mint, product_family, product_series, year_policy, year,
            purity, finish, variant, category_bucket_id

        Returns list of Candidate dicts (use build_candidate()).
        """
        ...

    def _base_candidate(
        self,
        url: str,
        raw_title: str,
        page_url: str = "",
    ) -> Dict:
        """Convenience wrapper that fills in adapter-level fields."""
        return build_candidate(
            url=url,
            raw_source_title=raw_title,
            source_name=self.name,
            source_type=self.source_type,
            source_page_url=page_url,
        )
