# routes/category_options.py
"""
Category Dropdown Options

This module provides dropdown options for all category specifications.
It uses the canonical catalogue from utils/category_catalog as the baseline,
and optionally unions in additional values discovered in the database for
backward compatibility.

The catalogue ensures that dropdown options are always available, even when
the database is empty (e.g., after wiping buckets in development).
"""

from database import get_db_connection
from utils.category_catalog import get_builtin_category_specs

# Cache so we don't hit the DB on every request
_dropdown_options_cache = None


def _load_dropdown_options():
    """
    Load dropdown options from the canonical catalogue, with optional database union.

    Returns a dictionary containing all category dropdown options:
    - metals
    - product_types
    - weights
    - purities
    - mints
    - years
    - finishes
    - grades
    - product_lines

    The loading strategy:
    1. Start with built-in values from the canonical catalogue
    2. Query the database for any additional values (backward compatibility)
    3. Union the two sets together
    4. Sort and return

    This ensures that:
    - Dropdowns are never empty (built-ins always present)
    - Old data is preserved (database values unioned in)
    - The system is easy to extend (add to catalogue module)
    """
    # Get the canonical built-in specifications
    builtin_specs, builtin_years = get_builtin_category_specs()

    # Connect to database for optional union of legacy values
    conn = get_db_connection()
    opts = {}

    # ==================== PATTERN FOR EACH DIMENSION ====================
    # For each dimension:
    # 1. Start with a set of built-in values
    # 2. Query database for additional values (if any exist)
    # 3. Add database values to the set
    # 4. Convert to sorted list
    #
    # To add a new dimension:
    # - Add it to utils/category_catalog.py first
    # - Copy this pattern and adjust the dimension name and SQL column
    # ===================================================================

    # --- METALS ---
    metal_values = set(builtin_specs["metals"])
    rows = conn.execute(
        "SELECT DISTINCT metal FROM categories WHERE metal IS NOT NULL"
    ).fetchall()
    for row in rows:
        metal_values.add(row["metal"])
    opts["metals"] = sorted(metal_values)

    # --- PRODUCT TYPES ---
    product_type_values = set(builtin_specs["product_types"])
    rows = conn.execute(
        "SELECT DISTINCT product_type FROM categories WHERE product_type IS NOT NULL"
    ).fetchall()
    for row in rows:
        product_type_values.add(row["product_type"])
    opts["product_types"] = sorted(product_type_values)

    # --- WEIGHTS ---
    weight_values = set(builtin_specs["weights"])
    rows = conn.execute(
        "SELECT DISTINCT weight FROM categories WHERE weight IS NOT NULL"
    ).fetchall()
    for row in rows:
        weight_values.add(row["weight"])
    # Note: Weight sorting is alphabetical for now
    # Future enhancement: implement custom sort by actual weight value
    opts["weights"] = sorted(weight_values)

    # --- PURITIES ---
    purity_values = set(builtin_specs["purities"])
    rows = conn.execute(
        "SELECT DISTINCT purity FROM categories WHERE purity IS NOT NULL"
    ).fetchall()
    for row in rows:
        purity_values.add(row["purity"])
    opts["purities"] = sorted(purity_values)

    # --- MINTS ---
    mint_values = set(builtin_specs["mints"])
    rows = conn.execute(
        "SELECT DISTINCT mint FROM categories WHERE mint IS NOT NULL"
    ).fetchall()
    for row in rows:
        mint_values.add(row["mint"])
    opts["mints"] = sorted(mint_values)

    # --- YEARS ---
    # Start with generated years (1900 to current_year + 5)
    # This ensures the years dropdown is NEVER empty
    # IMPORTANT: Convert to strings for consistency with form data
    year_values = set(str(y) for y in builtin_years)
    # Optionally union in any years from the database that fall outside the range
    rows = conn.execute(
        "SELECT DISTINCT year FROM categories WHERE year IS NOT NULL"
    ).fetchall()
    for row in rows:
        # Add any year values from DB (handles edge cases like very old or future years)
        # Convert to string to ensure consistent type with form data
        year_val = row["year"]
        if isinstance(year_val, int):
            year_val = str(year_val)
        elif isinstance(year_val, str):
            # Validate it's numeric
            try:
                int(year_val)  # Just to validate
            except ValueError:
                continue  # Skip non-numeric year values
        else:
            continue
        year_values.add(year_val)
    # Sort years as strings (they'll sort correctly since they're all numeric)
    opts["years"] = sorted(year_values)

    # --- FINISHES ---
    finish_values = set(builtin_specs["finishes"])
    rows = conn.execute(
        "SELECT DISTINCT finish FROM categories WHERE finish IS NOT NULL"
    ).fetchall()
    for row in rows:
        finish_values.add(row["finish"])
    opts["finishes"] = sorted(finish_values)

    # --- GRADES ---
    grade_values = set(builtin_specs["grades"])
    rows = conn.execute(
        "SELECT DISTINCT grade FROM categories WHERE grade IS NOT NULL"
    ).fetchall()
    for row in rows:
        grade_values.add(row["grade"])
    opts["grades"] = sorted(grade_values)

    # --- PRODUCT LINES ---
    # Special handling: exclude values that are actually product types
    # (historical quirk where some product types leaked into product_line column)
    product_line_values = set(builtin_specs["product_lines"])
    rows = conn.execute(
        """
        SELECT DISTINCT product_line
        FROM categories
        WHERE product_line IS NOT NULL
          AND product_line NOT IN ('Coin', 'Bar', 'Round')
        """
    ).fetchall()
    for row in rows:
        product_line_values.add(row["product_line"])
    opts["product_lines"] = sorted(product_line_values)

    # --- PACKAGING TYPES ---
    packaging_values = set(builtin_specs["packaging_types"])
    rows = conn.execute(
        "SELECT DISTINCT packaging_type FROM listings WHERE packaging_type IS NOT NULL"
    ).fetchall()
    for row in rows:
        packaging_values.add(row["packaging_type"])
    opts["packaging_types"] = sorted(packaging_values)

    # --- CONDITION CATEGORIES ---
    condition_values = set(builtin_specs["condition_categories"])
    rows = conn.execute(
        "SELECT DISTINCT condition_category FROM categories WHERE condition_category IS NOT NULL"
    ).fetchall()
    for row in rows:
        condition_values.add(row["condition_category"])
    opts["condition_categories"] = sorted(condition_values)

    # --- SERIES VARIANTS ---
    variant_values = set(builtin_specs["series_variants"])
    rows = conn.execute(
        "SELECT DISTINCT series_variant FROM categories WHERE series_variant IS NOT NULL"
    ).fetchall()
    for row in rows:
        variant_values.add(row["series_variant"])
    opts["series_variants"] = sorted(variant_values)

    conn.close()

    return opts


def get_dropdown_options():
    """
    Return cached dropdown options; load from catalogue/DB on first use.

    This function should be called by routes and templates that need dropdown options.
    The result is cached in memory to avoid repeated database queries.

    To refresh the cache (e.g., after adding new values to the catalogue):
    - Restart the application, OR
    - Call invalidate_dropdown_cache()
    """
    global _dropdown_options_cache
    if _dropdown_options_cache is None:
        _dropdown_options_cache = _load_dropdown_options()
    return _dropdown_options_cache


def invalidate_dropdown_cache():
    """
    Clear the dropdown options cache.

    Call this function if you need to force a reload of dropdown options
    (e.g., after adding new catalogue values or database migrations).
    """
    global _dropdown_options_cache
    _dropdown_options_cache = None
