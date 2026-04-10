"""
Ingestion adapters for automatic bucket image discovery.

Each adapter implements BaseImageAdapter and returns a list of ImageCandidate
dicts that can be fed directly into bucket_image_service.ingest_from_url().

Available adapters:
  KnownFilesAdapter    — Hardcoded, verified Wikimedia file catalog (highest precision)
  WikimediaAdapter     — Wikimedia Commons generic search (CC-licensed / public-domain)
  UsMintDirectAdapter  — US Mint products scraped from usmint.gov (public domain, auto-activatable)
  UsMintAdapter        — US Mint products via Wikimedia search (public domain, auto-activatable)
  RcmAdapter           — Royal Canadian Mint products via Wikimedia (licensed, review req'd)
  RoyalMintAdapter     — Royal Mint UK products via Wikimedia (licensed, review req'd)
  PerthMintAdapter     — Perth Mint Australia products via Wikimedia (licensed, review req'd)
  RefinerAdapter       — Bullion bar images via Wikimedia (PAMP, Valcambi, Sunshine, etc.)
  ApmexAdapter         — APMEX product images (retailer, always pending, review req'd)
  JmBullionAdapter     — JM Bullion product images (retailer, always pending, review req'd)
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
from .us_mint_direct import UsMintDirectAdapter
from .retailers import ApmexAdapter, JmBullionAdapter

__all__ = [
    'KnownFilesAdapter',
    'WikimediaAdapter',
    'UsMintDirectAdapter',
    'UsMintAdapter',
    'RcmAdapter',
    'RoyalMintAdapter',
    'PerthMintAdapter',
    'RefinerAdapter',
    'ApmexAdapter',
    'JmBullionAdapter',
]
