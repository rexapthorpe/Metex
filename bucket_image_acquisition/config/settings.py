"""
Central configuration for the bucket image acquisition system.

All paths are relative to the bucket_image_acquisition/ root unless noted.
Import ROOT to resolve absolute paths at runtime.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Root paths
# ---------------------------------------------------------------------------

# Root of this acquisition system
ROOT = Path(__file__).resolve().parent.parent

# Root of the main Metex project (one level up)
METEX_ROOT = ROOT.parent

# ---------------------------------------------------------------------------
# Data directories (working area — not served publicly)
# ---------------------------------------------------------------------------

DATA_DIR       = ROOT / "data"
RAW_DIR        = DATA_DIR / "raw"          # original downloaded bytes
PROCESSED_DIR  = DATA_DIR / "processed"    # web/thumb resized copies
MANIFESTS_DIR  = DATA_DIR / "manifests"    # per-bucket JSON manifests
LOGS_DIR       = DATA_DIR / "logs"         # run logs

# ---------------------------------------------------------------------------
# Catalog directories (organized by metal/family)
# ---------------------------------------------------------------------------

CATALOG_DIR = ROOT / "catalog"

# Map slug prefix → catalog sub-path (first matching prefix wins)
SLUG_TO_CATALOG: dict[str, str] = {
    # Gold coins
    "gold-american-eagle":        "gold/eagles",
    "gold-american-buffalo":      "gold/buffalos",
    "gold-canadian-maple-leaf":   "gold/maples",
    "gold-krugerrand":            "gold/krugerrands",
    "gold-austrian-philharmonic": "gold/philharmonics",
    "gold-australian-kangaroo":   "gold/kangaroos",
    "gold-british-britannia":     "gold/britannias",
    "gold-chinese-panda":         "gold/pandas",
    "gold-mexican-libertad":      "gold/libertads",
    "gold-bar":                   "gold/bars",
    # Silver coins
    "silver-american-eagle":           "silver/eagles",
    "silver-canadian-maple-leaf":      "silver/maples",
    "silver-austrian-philharmonic":    "silver/philharmonics",
    "silver-australian-kangaroo":      "silver/kangaroos",
    "silver-british-britannia":        "silver/britannias",
    "silver-south-african-krugerrand": "silver/krugerrands",
    "silver-mexican-libertad":         "silver/libertads",
    "silver-chinese-panda":            "silver/pandas",
    "silver-round-generic":            "silver/rounds",
    "silver-morgan-dollar":            "silver/morgan_dollars",
    "silver-peace-dollar":             "silver/peace_dollars",
    "silver-walking-liberty":          "silver/walking_liberty",
    "silver-franklin-half":            "silver/franklin_half",
    "silver-mercury-dime":             "silver/mercury_dimes",
    "silver-roosevelt-dime":           "silver/roosevelt_dimes",
    "silver-washington-quarter":       "silver/washington_quarters",
    "silver-bar":                      "silver/bars",
    # Platinum
    "platinum-american-eagle":      "platinum/eagles",
    "platinum-canadian-maple-leaf": "platinum/maples",
    "platinum-bar":                 "platinum/bars",
    # Palladium
    "palladium-american-eagle":      "palladium/eagles",
    "palladium-canadian-maple-leaf": "palladium/maples",
    "palladium-bar":                 "palladium/bars",
    # Copper
    "copper-round": "copper/rounds",
    "copper-bar":   "copper/bars",
}

# All catalog leaf directories that must exist
CATALOG_DIRS: list[str] = sorted(set(SLUG_TO_CATALOG.values()))

# ---------------------------------------------------------------------------
# Download settings
# ---------------------------------------------------------------------------

MAX_DOWNLOAD_BYTES  = 15 * 1024 * 1024   # 15 MB
DOWNLOAD_TIMEOUT_S  = 15
DEFAULT_DELAY_S     = 1.0                 # seconds between requests per adapter
MAX_RETRIES         = 3

ALLOWED_MIME_TYPES  = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_EXTENSIONS  = {".jpg", ".jpeg", ".png", ".webp"}

# ---------------------------------------------------------------------------
# Processing settings
# ---------------------------------------------------------------------------

WEB_MAX_PX   = 1200   # max dimension for web copy
THUMB_MAX_PX = 400    # max dimension for thumbnail
WEB_QUALITY  = 85
THUMB_QUALITY = 80
MAX_PIXELS   = 25_000_000   # decompression bomb guard

# ---------------------------------------------------------------------------
# Scoring / activation thresholds
# ---------------------------------------------------------------------------

MIN_CONFIDENCE_TO_KEEP     = 0.30   # discard below this
AUTO_ACTIVATE_PD_CONFIDENCE = 0.75  # public_domain auto-activates above this

# ---------------------------------------------------------------------------
# Metex integration
# ---------------------------------------------------------------------------

# Path to Metex static uploads (absolute)
METEX_STATIC_DIR = METEX_ROOT / "static"
METEX_UPLOADS_DIR = METEX_STATIC_DIR / "uploads" / "bucket_images"

# ---------------------------------------------------------------------------
# API keys (loaded from env; None = feature disabled)
# ---------------------------------------------------------------------------

PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY")
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY")

# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

REPORTS_DIR = ROOT / "reports"


def catalog_dir_for_slug(slug: str) -> Path:
    """Return the catalog directory for a given bucket slug."""
    for prefix, subpath in SLUG_TO_CATALOG.items():
        if slug.startswith(prefix):
            return CATALOG_DIR / subpath
    # Fallback: metal/misc
    metal = slug.split("-")[0] if "-" in slug else "other"
    return CATALOG_DIR / metal / "misc"


def ensure_dirs() -> None:
    """Create all required directories if they don't exist."""
    for d in [RAW_DIR, PROCESSED_DIR, MANIFESTS_DIR, LOGS_DIR, REPORTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    for rel in CATALOG_DIRS:
        (CATALOG_DIR / rel).mkdir(parents=True, exist_ok=True)
