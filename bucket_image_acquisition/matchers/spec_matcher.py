"""
Spec matcher: scores image candidates against standard bucket specs.

This is a standalone, enhanced version of the confidence scorer used in
the main Metex bucket_image_service. It runs without a database connection
and operates purely on bucket dicts + raw image metadata strings.

Score range: 0.0 – 1.0
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Weight synonym map  (canonical → list of equivalent strings)
# ---------------------------------------------------------------------------

_WEIGHT_SYNONYMS: Dict[str, List[str]] = {
    "1 g":    ["1g", "1 gram", "one gram", "1-gram", "1gram"],
    "2.5 g":  ["2.5g", "2.5 gram", "2-1/2 gram", "two and a half gram"],
    "5 g":    ["5g", "5 gram", "five gram", "5-gram"],
    "10 g":   ["10g", "10 gram", "ten gram", "10-gram"],
    "1/10 oz":["tenth ounce", "one tenth ounce", "one-tenth ounce", "1/10oz", "0.1 oz", "0.1oz",
               "1-10 oz", "tenth oz"],
    "1/4 oz": ["quarter ounce", "quarter oz", "1/4oz", "0.25 oz", "0.25oz", "quarter-ounce"],
    "1/2 oz": ["half ounce", "half oz", "1/2oz", "0.5 oz", "0.5oz", "half-ounce"],
    "1 oz":   ["one ounce", "one oz", "1oz", "1 troy ounce", "1 troy oz", "one troy ounce",
               "1-oz", "1oz bullion"],
    "2 oz":   ["two ounce", "two oz", "2oz", "2 troy ounce"],
    "5 oz":   ["five ounce", "five oz", "5oz", "5 troy ounce"],
    "10 oz":  ["ten ounce", "ten oz", "10oz", "10 troy ounce"],
    "50 oz":  ["fifty ounce", "fifty oz", "50oz"],
    "100 oz": ["hundred ounce", "100oz", "100 troy ounce"],
    "1 kg":   ["kilogram", "kilo", "1kg", "one kilogram", "one kilo", "1-kg"],
    "1 lb":   ["pound", "one pound", "1lb", "16 oz"],
}

# Flatten to (term, canonical) pairs for fast lookup
_WEIGHT_LOOKUP: Dict[str, str] = {}
for canonical, synonyms in _WEIGHT_SYNONYMS.items():
    _WEIGHT_LOOKUP[canonical.lower()] = canonical
    for s in synonyms:
        _WEIGHT_LOOKUP[s.lower()] = canonical


def _normalize_weight(text: str) -> Optional[str]:
    """Return canonical weight string if found in text, else None."""
    t = text.lower()
    # Longest match first
    for term in sorted(_WEIGHT_LOOKUP, key=len, reverse=True):
        if term in t:
            return _WEIGHT_LOOKUP[term]
    return None


# ---------------------------------------------------------------------------
# Metal keyword sets
# ---------------------------------------------------------------------------

_METAL_TERMS: Dict[str, List[str]] = {
    "gold":      ["gold", "au ", "au-", "aurum"],
    "silver":    ["silver", "ag ", "ag-", "argent"],
    "platinum":  ["platinum", "pt ", "pt-"],
    "palladium": ["palladium", "pd ", "pd-"],
    "copper":    ["copper", "cu ", "cu-"],
}


def _contains_metal(text: str, metal: str) -> bool:
    t = text.lower()
    for term in _METAL_TERMS.get(metal, [metal]):
        if term in t:
            return True
    return False


# ---------------------------------------------------------------------------
# Family / product-line keyword map
# ---------------------------------------------------------------------------

_FAMILY_TERMS: Dict[str, List[str]] = {
    "american eagle":     ["american eagle", "ame", "us eagle", "usa eagle"],
    "american buffalo":   ["american buffalo", "buffalo", "bison"],
    "maple leaf":         ["maple leaf", "maple", "rcm maple"],
    "krugerrand":         ["krugerrand", "kruger rand", "kruggerand"],
    "philharmonic":       ["philharmonic", "wiener philharmoniker", "vienna philharmonic"],
    "kangaroo":           ["kangaroo", "nugget"],
    "britannia":          ["britannia"],
    "panda":              ["panda", "chinese panda"],
    "libertad":           ["libertad"],
    "kookaburra":         ["kookaburra"],
    "bar":                ["bar", "ingot", "bullion bar"],
    "round":              ["round"],
    "morgan":             ["morgan dollar", "morgan silver"],
    "peace dollar":       ["peace dollar"],
    "walking liberty":    ["walking liberty", "liberty half", "walking lib"],
    "franklin half":      ["franklin half", "franklin"],
    "mercury dime":       ["mercury dime", "winged liberty"],
    "roosevelt dime":     ["roosevelt dime"],
    "washington quarter": ["washington quarter"],
}


def _family_match_score(text: str, product_family: Optional[str]) -> float:
    if not product_family:
        return 0.0
    t = text.lower()
    fam = product_family.lower()
    # Direct substring
    if fam in t:
        return 0.20
    # Keyword table
    for canonical, terms in _FAMILY_TERMS.items():
        if canonical in fam or fam in canonical:
            if any(term in t for term in terms):
                return 0.18
    return 0.0


# ---------------------------------------------------------------------------
# Mint keyword map
# ---------------------------------------------------------------------------

_MINT_TERMS: Dict[str, List[str]] = {
    "us mint":              ["united states mint", "us mint", "usmint", "u.s. mint"],
    "royal canadian mint":  ["royal canadian mint", "rcm", "canada mint"],
    "perth mint":           ["perth mint", "perthmint"],
    "royal mint":           ["royal mint", "royal mint uk", "uk mint"],
    "austrian mint":        ["austrian mint", "münze österreich", "austria mint"],
    "south african mint":   ["south african mint", "sa mint", "rand refinery"],
    "mexican mint":         ["mexican mint", "casa de moneda", "mexican"],
    "china gold coin":      ["china gold coin", "chinese mint", "prc mint"],
    "pamp suisse":          ["pamp suisse", "pamp", "pamp sa"],
    "valcambi":             ["valcambi"],
    "sunshine minting":     ["sunshine minting", "sunshine mint"],
    "engelhard":            ["engelhard"],
    "johnson matthey":      ["johnson matthey", "jm"],
    "scottsdale mint":      ["scottsdale mint", "scottsdale"],
    "silvertowne":          ["silvertowne", "silver towne"],
    "apmex":                ["apmex"],
    "generic":              ["generic", "various", "assorted"],
}


def _mint_match_score(text: str, mint: Optional[str]) -> float:
    if not mint:
        return 0.0
    t = text.lower()
    m = mint.lower()
    if m in t:
        return 0.20
    for canonical, terms in _MINT_TERMS.items():
        if canonical in m or any(term in m for term in terms):
            if any(term in t for term in terms):
                return 0.18
    return 0.0


# ---------------------------------------------------------------------------
# Warning patterns (cap confidence)
# ---------------------------------------------------------------------------

_WARNING_CAPS: List[Tuple[re.Pattern, float, str]] = [
    (re.compile(r"\b(sample|example|for example|specimen)\b", re.I), 0.50, "example_image"),
    (re.compile(r"\b(generic|placeholder|stock photo)\b", re.I),      0.40, "generic_image"),
    (re.compile(r"\b(brand varies|mint varies|random mint|assorted)\b", re.I), 0.60, "brand_varies"),
    (re.compile(r"\b(lot of|bag of|roll of|\d+\s*coins?)\b", re.I),   0.55, "lot_image"),
    (re.compile(r"\b(reverse|back|obverse|front)\b", re.I),           1.00, None),  # neutral info
]

_SIZE_MISMATCH_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(oz|ounce|gram|kg|lb)\b", re.I
)


def compute_confidence(
    raw_source_title: str,
    bucket: Dict,
    source_type: str = "unknown",
) -> Tuple[float, List[str]]:
    """
    Score a candidate title against bucket specs.

    Returns (score, warnings_list).
    Score is in [0.0, 1.0].
    """
    title = (raw_source_title or "").lower()
    warnings: List[str] = []
    score = 0.0

    # 1. Metal (0.20)
    metal = (bucket.get("metal") or "").lower()
    if metal and _contains_metal(title, metal):
        score += 0.20

    # 2. Weight (0.20) + size mismatch check
    weight = bucket.get("weight") or ""
    found_weight = _normalize_weight(title)
    bucket_weight = _normalize_weight(weight) or weight.lower()
    if bucket_weight:
        if found_weight == bucket_weight:
            score += 0.20
        elif found_weight and found_weight != bucket_weight:
            warnings.append("size_mismatch")

    # 3. Mint (0.20)
    mint = bucket.get("mint") or ""
    score += _mint_match_score(title, mint)

    # 4. Product family (0.20)
    family = bucket.get("product_family") or ""
    score += _family_match_score(title, family)

    # 5. Product series (0.10)
    series = (bucket.get("product_series") or "").lower()
    if series and series in title:
        score += 0.10

    # 6. Denomination (0.05)
    denom = (bucket.get("denomination") or "").lower()
    if denom and denom in title:
        score += 0.05

    # 7. Year (0.05)
    year_policy = bucket.get("year_policy") or "fixed"
    year = (bucket.get("year") or "").strip()
    if year_policy == "fixed" and year:
        if year in title:
            score += 0.05
        # else: no penalty, year just not in title
    elif year_policy in ("varies", "any"):
        score += 0.03  # small bonus for flexible year policy

    # Apply warning caps
    cap = 1.0
    for pattern, limit, warn_key in _WARNING_CAPS:
        if pattern.search(raw_source_title or ""):
            if warn_key and warn_key not in warnings:
                warnings.append(warn_key)
            cap = min(cap, limit)

    # Retailer source cap
    if source_type == "retailer":
        if score >= 0.70:
            warnings.append("retailer_source")
        cap = min(cap, 0.75)

    score = min(score, cap)
    score = round(score, 4)
    return score, warnings
