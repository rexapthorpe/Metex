"""
Registry of all available acquisition adapters.

Usage:
    from config.source_registry import REGISTRY, get_adapter

    adapter = get_adapter("wikimedia")
    candidates = adapter.find_candidates(bucket)
"""
from __future__ import annotations

from typing import Dict, Type

# Lazy imports so that adapters with optional deps don't break everything
def _load_registry() -> Dict[str, Type]:
    from adapters.wikimedia          import WikimediaAdapter, KnownFilesAdapter
    from adapters.us_mint            import UsMintAdapter
    from adapters.rcm                import RcmAdapter
    from adapters.royal_mint         import RoyalMintAdapter
    from adapters.perth_mint         import PerthMintAdapter
    from adapters.refiner            import RefinerAdapter
    from adapters.pixabay            import PixabayAdapter
    from adapters.open_numismatics   import OpenNumismaticsAdapter

    return {
        "known_files":       KnownFilesAdapter,
        "wikimedia":         WikimediaAdapter,
        "us_mint":           UsMintAdapter,
        "rcm":               RcmAdapter,
        "royal_mint":        RoyalMintAdapter,
        "perth_mint":        PerthMintAdapter,
        "refiner":           RefinerAdapter,
        "pixabay":           PixabayAdapter,
        "open_numismatics":  OpenNumismaticsAdapter,
    }


# Priority order for a full sweep (lower index = tried first)
SWEEP_ORDER = [
    "known_files",       # curated, zero-noise
    "us_mint",           # public domain, high confidence
    "rcm",               # licensed — Maple Leaf family
    "royal_mint",        # licensed — Britannia family
    "perth_mint",        # licensed — Kangaroo/Kookaburra family
    "refiner",           # licensed — bars
    "open_numismatics",  # junk/historic US silver
    "wikimedia",         # broad catch-all
    "pixabay",           # free images (API key required)
]

# Which sources cover which metal families (for targeted runs)
METAL_SOURCES: Dict[str, list[str]] = {
    "gold":      ["known_files", "us_mint", "rcm", "royal_mint", "perth_mint", "refiner", "wikimedia"],
    "silver":    ["known_files", "us_mint", "rcm", "royal_mint", "perth_mint", "refiner", "open_numismatics", "wikimedia"],
    "platinum":  ["known_files", "us_mint", "rcm", "refiner", "wikimedia"],
    "palladium": ["known_files", "us_mint", "rcm", "refiner", "wikimedia"],
    "copper":    ["known_files", "refiner", "wikimedia"],
}

FAMILY_SOURCES: Dict[str, list[str]] = {
    "eagles":           ["known_files", "us_mint", "wikimedia"],
    "buffalos":         ["known_files", "us_mint", "wikimedia"],
    "maples":           ["known_files", "rcm", "wikimedia"],
    "britannias":       ["known_files", "royal_mint", "wikimedia"],
    "kangaroos":        ["known_files", "perth_mint", "wikimedia"],
    "kookaburras":      ["known_files", "perth_mint", "wikimedia"],
    "philharmonics":    ["known_files", "wikimedia"],
    "krugerrands":      ["known_files", "wikimedia"],
    "pandas":           ["known_files", "wikimedia"],
    "libertads":        ["known_files", "wikimedia"],
    "bars":             ["known_files", "refiner", "wikimedia"],
    "rounds":           ["known_files", "wikimedia"],
    "morgan_dollars":   ["known_files", "open_numismatics", "wikimedia"],
    "peace_dollars":    ["known_files", "open_numismatics", "wikimedia"],
    "walking_liberty":  ["known_files", "open_numismatics", "wikimedia"],
    "franklin_half":    ["known_files", "open_numismatics", "wikimedia"],
    "mercury_dimes":    ["known_files", "open_numismatics", "wikimedia"],
    "junk_silver":      ["known_files", "open_numismatics", "wikimedia"],
}


_registry_cache: Dict[str, Type] | None = None


def get_registry() -> Dict[str, Type]:
    global _registry_cache
    if _registry_cache is None:
        _registry_cache = _load_registry()
    return _registry_cache


def get_adapter(source_name: str, max_results: int = 5):
    """Instantiate and return an adapter by name."""
    reg = get_registry()
    if source_name not in reg:
        raise ValueError(f"Unknown source: {source_name!r}. Available: {sorted(reg)}")
    return reg[source_name](max_results=max_results)


def list_sources() -> list[str]:
    return sorted(get_registry().keys())
