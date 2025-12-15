# utils/category_catalog.py
"""
Canonical Category Catalogue

This module is the single source of truth for all dropdown options in Metex.
It provides built-in default values for all category specifications, ensuring that
dropdowns remain populated even when the database is empty.

To add new options:
1. Add the value to the appropriate list in get_builtin_category_specs()
2. Restart the application (the cache will be refreshed)

To add a new category dimension:
1. Add a new key and list to the returned dictionary in get_builtin_category_specs()
2. Update routes/category_options.py to load and union this new dimension
3. Update templates and validation logic as needed
"""

from datetime import datetime


def get_builtin_category_specs():
    """
    Returns the canonical catalogue of all category specifications.

    Returns:
        tuple: (specs_dict, years_list) where:
            - specs_dict contains all category dimensions as lists
            - years_list is a generated list of years from 1900 to current_year + 5

    This function is called by routes/category_options.py to provide baseline
    dropdown options that are immune to database state.
    """
    current_year = datetime.now().year
    years = list(range(1900, current_year + 6))  # 1900 through current_year + 5

    specs = {
        # ==================== METALS ====================
        "metals": [
            "Gold",
            "Silver",
            "Platinum",
            "Palladium",
        ],

        # ==================== PRODUCT TYPES ====================
        "product_types": [
            "Coin",
            "Bar",
            "Round",
        ],

        # ==================== WEIGHTS ====================
        # Organized by unit type for clarity
        "weights": [
            # Troy ounces (fractional)
            "1/20 oz",
            "1/10 oz",
            "1/4 oz",
            "1/2 oz",
            # Troy ounces (whole)
            "1 oz",
            "2 oz",
            "5 oz",
            "10 oz",
            # Grams
            "1 g",
            "2.5 g",
            "5 g",
            "10 g",
            "20 g",
            "50 g",
            "100 g",
            "250 g",
            "500 g",
            # Kilograms
            "1 kilo",
            "5 kilo",
        ],

        # ==================== PURITIES ====================
        # Common bullion fineness values
        "purities": [
            ".9999",  # Four nines fine (99.99%)
            ".999",   # Three nines fine (99.9%)
            ".995",   # 99.5%
            ".990",   # 99.0%
            ".958",   # 22 karat gold (Britannia, etc.)
            ".925",   # Sterling silver
            ".900",   # 90% silver (U.S. junk silver, etc.)
        ],

        # ==================== MINTS ====================
        "mints": [
            # U.S.
            "United States Mint",
            # Canada
            "Royal Canadian Mint",
            # Australia
            "Perth Mint",
            "Royal Australian Mint",
            # United Kingdom
            "Royal Mint (UK)",
            # Europe
            "Austrian Mint",
            "Germania Mint",
            # Asia
            "Chinese Mint",
            # Africa
            "South African Mint",
            "Rand Refinery",
            # Mexico
            "Mexican Mint",
            # Private / Refiners
            "PAMP Suisse",
            "Credit Suisse",
            "Valcambi",
            "Sunshine Mint",
            "Scottsdale Mint",
            "New Zealand Mint",
            # Catch-all
            "Generic / Private Mint",
        ],

        # ==================== FINISHES ====================
        "finishes": [
            "Bullion",
            "Brilliant Uncirculated",
            "Proof",
            "Reverse Proof",
            "Matte",
            "Polished",
            "Burnished",
        ],

        # ==================== GRADES ====================
        # Standard numismatic grading scale (Sheldon scale)
        "grades": [
            # About Good to Good
            "AG-3",
            "G-4",
            # Very Good
            "VG-8",
            # Fine
            "F-12",
            # Very Fine
            "VF-20",
            "VF-30",
            # Extremely Fine / Extra Fine
            "XF-40",
            "XF-45",
            # About Uncirculated
            "AU-50",
            "AU-53",
            "AU-55",
            "AU-58",
            # Mint State (Uncirculated)
            "MS-60",
            "MS-61",
            "MS-62",
            "MS-63",
            "MS-64",
            "MS-65",
            "MS-66",
            "MS-67",
            "MS-68",
            "MS-69",
            "MS-70",  # Perfect
        ],

        # ==================== PRODUCT LINES ====================
        # Comprehensive list of coin/bar series and brands
        # This is the full list previously hard-coded in category_options.py
        "product_lines": [
            # --- U.S. Mint bullion & modern programs ---
            "American Eagle",
            "American Buffalo",
            "America the Beautiful",
            "American Liberty",
            "American Innovation",
            "Pre-1933 U.S. Gold",
            "Morgan Dollar",
            "Peace Dollar",

            # --- Royal Canadian Mint (Canada) ---
            "Canadian Maple Leaf",
            "Canadian Wildlife Series",
            "Canadian Predator Series",
            "Canadian Birds of Prey",
            "Canadian Call of the Wild",
            "Maplegram",

            # --- The Royal Mint (United Kingdom) ---
            "Britannia",
            "Sovereign",
            "Queen's Beasts",
            "Royal Tudor Beasts",
            "Royal Arms",
            "Landmarks of Britain",
            "Lunar Series (Royal Mint)",

            # --- Austrian Mint ---
            "Austrian Philharmonic",

            # --- Perth Mint & Royal Australian Mint (Australia) ---
            "Australian Kangaroo",
            "Australian Nugget",
            "Australian Kookaburra",
            "Australian Koala",
            "Australian Swan",
            "Australian Emu",
            "Australian Wedge-Tailed Eagle",
            "Australian Lunar Series I",
            "Australian Lunar Series II",
            "Australian Lunar Series III",
            "Australian Rectangular Dragon",
            "Australian Domed Coins",
            "Australian Dolphin",
            "Australian Lunar (Royal Australian Mint)",

            # --- Mexican Mint (Casa de Moneda de México) ---
            "Mexican Libertad",
            "Mexican Centenario",
            "Mexican Peso Gold Series",

            # --- South African Mint ---
            "Krugerrand",
            "Natura",

            # --- Other major government bullion series ---
            "Chinese Panda",
            "Somalian Elephant",
            "Somalian Leopard",
            "Rwanda African Ounce",
            "Armenian Noah's Ark",
            "Indian Wildlife Series",
            "KOMSCO Chiwoo Cheonwang",
            "KOMSCO Tiger",
            "KOMSCO ZI:SIN Series",

            # --- Generic / "junk" / bulk style product lines ---
            "Junk Silver",
            "90% Silver",
            "40% Silver",
            "35% Silver",
            "80% Canadian Silver",
            "Hand Poured Silver",
            "Silver Bullets",
            "Silver Grain",

            # --- Major bar & round brands / lines ---
            "APMEX",
            "APMEX Stackable",
            "PAMP Suisse Fortuna",
            "PAMP Suisse Lunar",
            "PAMP Suisse Rosa",
            "Credit Suisse",
            "Valcambi",
            "Valcambi CombiBar",
            "Johnson Matthey",
            "Engelhard",
            "Sunshine Mint",
            "Scottsdale Stacker",
            "Scottsdale Mint",
            "Geiger Edelmetalle",
            "Argor-Heraeus",
            "Asahi Refining",
            "Royal Canadian Mint Bars",
            "Perth Mint Bars",
            "Royal Mint Bars",
            "9Fine Mint",
            "Pioneer Metals",
            "U.S. Assay Office",
            "Istanbul Gold Refinery",
            "Metalor",

            # --- Licensed / themed lines ---
            "Coca-Cola Series",
            "John Wick Series",
            "Harry Potter Series",
            "Peanuts Series",
            "Star Wars Series",
            "Disney Series",
            "DC Comics Series",
        ],

        # ==================== PACKAGING TYPES ====================
        # How the item is physically packaged/protected
        "packaging_types": [
            "Loose",
            "Capsule",
            "OGP",  # Original Government Packaging
            "Tube_Full",
            "Tube_Partial",
            "MonsterBox_Full",
            "MonsterBox_Partial",
            "Assay_Card",
        ],

        # ==================== CONDITION CATEGORIES ====================
        # Broad condition classifications for non-graded items
        "condition_categories": [
            "BU",  # Brilliant Uncirculated
            "AU",  # About Uncirculated
            "Circulated",
            "Cull",
            "Random_Condition",
            "None",
        ],

        # ==================== SERIES VARIANTS ====================
        # Special designations and labels for premium products
        "series_variants": [
            "None",
            "First_Strike",
            "Early_Releases",
            "First_Day_of_Issue",
            "Privy",
            "MintDirect",
        ],
    }

    return specs, years


def get_all_category_keys():
    """
    Returns a list of all category dimension keys.

    Useful for validation and iteration over all category types.
    """
    specs, _ = get_builtin_category_specs()
    return list(specs.keys()) + ['years']
