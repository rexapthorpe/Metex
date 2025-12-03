# routes/category_options.py

from database import get_db_connection

# Cache so we don't hit the DB on every request
_dropdown_options_cache = None


def _load_dropdown_options():
    conn = get_db_connection()
    opts = {}

    # Product lines: pull from DB but ignore values that are really product types
    opts['product_lines'] = [
        row['product_line']
        for row in conn.execute(
            '''
            SELECT DISTINCT product_line
            FROM categories
            WHERE product_line IS NOT NULL
              AND product_line NOT IN ('Coin', 'Bar', 'Round')
            ORDER BY product_line
            '''
        ).fetchall()
    ]

    # Metals
    opts['metals'] = [
        row['metal']
        for row in conn.execute(
            'SELECT DISTINCT metal FROM categories WHERE metal IS NOT NULL ORDER BY metal'
        ).fetchall()
    ]

    # Product types
    opts['product_types'] = [
        row['product_type']
        for row in conn.execute(
            'SELECT DISTINCT product_type FROM categories WHERE product_type IS NOT NULL ORDER BY product_type'
        ).fetchall()
    ]

    # Weights
    opts['weights'] = [
        row['weight']
        for row in conn.execute(
            'SELECT DISTINCT weight FROM categories WHERE weight IS NOT NULL ORDER BY weight'
        ).fetchall()
    ]

    # Purities
    opts['purities'] = [
        row['purity']
        for row in conn.execute(
            'SELECT DISTINCT purity FROM categories WHERE purity IS NOT NULL ORDER BY purity'
        ).fetchall()
    ]

    # Mints
    opts['mints'] = [
        row['mint']
        for row in conn.execute(
            'SELECT DISTINCT mint FROM categories WHERE mint IS NOT NULL ORDER BY mint'
        ).fetchall()
    ]

    # Years
    opts['years'] = [
        row['year']
        for row in conn.execute(
            'SELECT DISTINCT year FROM categories WHERE year IS NOT NULL ORDER BY year'
        ).fetchall()
    ]

    # Finishes
    opts['finishes'] = [
        row['finish']
        for row in conn.execute(
            'SELECT DISTINCT finish FROM categories WHERE finish IS NOT NULL ORDER BY finish'
        ).fetchall()
    ]

    # Grades
    opts['grades'] = [
        row['grade']
        for row in conn.execute(
            'SELECT DISTINCT grade FROM categories WHERE grade IS NOT NULL ORDER BY grade'
        ).fetchall()
    ]

    conn.close()

    # ---------- FORCE INSERT standard values if missing ----------

    # Metals
    for metal in ['Gold', 'Silver', 'Platinum', 'Palladium']:
        if metal not in opts['metals']:
            opts['metals'].append(metal)

    # Product types
    for t in ['Coin', 'Bar', 'Round']:
        if t not in opts['product_types']:
            opts['product_types'].append(t)

    # Product lines – seed with common options
    default_product_lines = [
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

        # --- Generic / “junk” / bulk style product lines ---
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
    ]
    for line in default_product_lines:
        if line not in opts['product_lines']:
            opts['product_lines'].append(line)

    # Purities – seed with common bullion fineness values
    default_purities = [
        ".9999",
        ".999",
        ".995",
        ".990",
        ".958",
        ".925",
        ".900",
    ]
    for p in default_purities:
        if p not in opts['purities']:
            opts['purities'].append(p)

    # Sort everything to keep dropdowns clean
    opts['product_lines'].sort()
    opts['metals'].sort()
    opts['product_types'].sort()
    opts['weights'].sort()
    opts['purities'].sort()
    opts['mints'].sort()
    opts['years'].sort()
    opts['finishes'].sort()
    opts['grades'].sort()

    return opts


def get_dropdown_options():
    """Return cached dropdown options; load from DB on first use."""
    global _dropdown_options_cache
    if _dropdown_options_cache is None:
        _dropdown_options_cache = _load_dropdown_options()
    return _dropdown_options_cache
