"""
Base interface for image ingestion adapters.

An adapter is responsible for:
  1. Building a search query from a standard_bucket dict.
  2. Calling an external source (API, website, etc.).
  3. Returning a list of ImageCandidate dicts.

The batch runner calls adapter.find_candidates(bucket) and pipes each
candidate into bucket_image_service.ingest_from_url().

ImageCandidate keys (all str unless noted):
  url              — direct image URL (required)
  source_name      — human-readable label, e.g. "Wikimedia Commons"
  source_type      — one of: public_domain | licensed | approved_db | retailer | unknown
  source_page_url  — page where the image was found (optional)
  raw_source_title — title / alt text from source (used for confidence scoring)
  license_type     — e.g. "public_domain", "CC-BY-4.0" (optional)
  attribution_text — attribution string (optional)
  rights_note      — free-text rights notice (optional)
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseImageAdapter(ABC):
    """Abstract base for image ingestion adapters."""

    #: Human-readable name shown in ingestion_run.source_name
    name: str = 'unknown'

    #: Default source_type for all results from this adapter
    source_type: str = 'unknown'

    @abstractmethod
    def find_candidates(self, bucket: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Search for candidate images for a given standard_bucket dict.

        Args:
            bucket: A standard_buckets row dict (keys: slug, title, metal,
                    weight, mint, product_family, product_series, purity, etc.)

        Returns:
            List of ImageCandidate dicts (see module docstring).
            Empty list if no usable candidates found.
        """
        raise NotImplementedError

    def _base_candidate(self, url: str, raw_title: str = '', page_url: str = '') -> Dict[str, Any]:
        """Return a candidate dict pre-filled with adapter defaults."""
        return {
            'url':              url,
            'source_name':      self.name,
            'source_type':      self.source_type,
            'source_page_url':  page_url or None,
            'raw_source_title': raw_title,
            'license_type':     None,
            'attribution_text': None,
            'rights_note':      None,
        }
