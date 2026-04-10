"""
Ingestion adapters for automatic bucket image discovery.

Each adapter implements BaseImageAdapter and returns a list of ImageCandidate
dicts that can be fed directly into bucket_image_service.ingest_from_url().

Available adapters:
  KnownFilesAdapter — Hardcoded, verified Wikimedia file catalog (highest precision)
  WikimediaAdapter  — Wikimedia Commons generic search (CC-licensed / public-domain)
  UsMintAdapter     — US Mint products via Wikimedia (public domain, auto-activatable)
  RcmAdapter        — Royal Canadian Mint products via Wikimedia (licensed, review req'd)
  RoyalMintAdapter  — Royal Mint UK products via Wikimedia (licensed, review req'd)
  PerthMintAdapter  — Perth Mint Australia products via Wikimedia (licensed, review req'd)
  RefinerAdapter    — Bullion bar images via Wikimedia (PAMP, Valcambi, Sunshine, etc.)
"""

from .known_files import KnownFilesAdapter
from .wikimedia import WikimediaAdapter
from .official_mint import (
    UsMintAdapter,
    RcmAdapter,
    RoyalMintAdapter,
    PerthMintAdapter,
)
from .refiner import RefinerAdapter

__all__ = [
    'KnownFilesAdapter',
    'WikimediaAdapter',
    'UsMintAdapter',
    'RcmAdapter',
    'RoyalMintAdapter',
    'PerthMintAdapter',
    'RefinerAdapter',
]
