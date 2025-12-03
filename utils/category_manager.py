"""
Unified Category Management Module
Handles category lookup, creation, and bucket assignment for both Sell and Edit flows
"""

def get_or_create_category(conn, category_spec):
    """
    Find existing category or create new one with proper bucket_id assignment.

    Args:
        conn: Database connection
        category_spec: Dict with keys: metal, product_line, product_type, weight,
                      purity, mint, year, finish, grade

    Returns:
        category_id: ID of existing or newly created category
    """
    cursor = conn.cursor()

    # Extract specifications
    metal = category_spec['metal']
    product_line = category_spec['product_line']
    product_type = category_spec['product_type']
    weight = category_spec['weight']
    purity = category_spec['purity']
    mint = category_spec['mint']
    year = category_spec['year']
    finish = category_spec['finish']
    grade = category_spec['grade']

    # 1. Look for existing category with exact specifications
    existing_cat = cursor.execute(
        '''
        SELECT id, bucket_id
        FROM categories
        WHERE metal = ? AND product_line = ? AND product_type = ?
          AND weight = ? AND purity = ? AND mint = ?
          AND year = ? AND finish = ? AND grade = ?
        LIMIT 1
        ''',
        (metal, product_line, product_type, weight, purity, mint, year, finish, grade)
    ).fetchone()

    if existing_cat:
        return existing_cat['id']

    # 2. No exact match - check for existing bucket (same core attributes, different finish/grade)
    bucket_row = cursor.execute(
        '''
        SELECT bucket_id
        FROM categories
        WHERE metal = ? AND product_line = ? AND product_type = ?
          AND weight = ? AND purity = ? AND mint = ? AND year = ?
        LIMIT 1
        ''',
        (metal, product_line, product_type, weight, purity, mint, year)
    ).fetchone()

    if bucket_row:
        bucket_id = bucket_row['bucket_id']
    else:
        # 3. No bucket exists - create new bucket_id (MAX + 1)
        new_bucket = cursor.execute(
            'SELECT COALESCE(MAX(bucket_id), 0) + 1 AS new_bucket_id FROM categories'
        ).fetchone()
        bucket_id = new_bucket['new_bucket_id']

    # 4. Insert new category with proper bucket_id
    # Build human-readable name
    parts = [year, metal, product_type, weight, purity, grade]
    category_name = " ".join([p for p in parts if p and p != "None"])

    cursor.execute(
        '''
        INSERT INTO categories (
            bucket_id,
            name,
            metal,
            product_line,
            product_type,
            weight,
            purity,
            mint,
            year,
            finish,
            grade
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            bucket_id,
            category_name,
            metal,
            product_line,
            product_type,
            weight,
            purity,
            mint,
            year,
            finish,
            grade
        )
    )

    category_id = cursor.lastrowid
    return category_id


def validate_category_specification(category_spec, valid_options):
    """
    Validate that all category specification values are from allowed dropdown options.

    Args:
        category_spec: Dict with category fields
        valid_options: Dict of allowed values from get_dropdown_options()

    Returns:
        (is_valid: bool, error_message: str or None)
    """
    # Map specification keys to validation lists
    validations = {
        'metal': ('metals', 'Metal'),
        'product_line': ('product_lines', 'Product Line'),
        'product_type': ('product_types', 'Product Type'),
        'weight': ('weights', 'Weight'),
        'purity': ('purities', 'Purity'),
        'mint': ('mints', 'Mint'),
        'year': ('years', 'Year'),
        'finish': ('finishes', 'Finish'),
        'grade': ('grades', 'Grade')
    }

    for spec_key, (options_key, display_name) in validations.items():
        value = category_spec.get(spec_key, '').strip()

        # Check if value is empty
        if not value:
            return False, f"{display_name} is required"

        # Check if value is in allowed options
        allowed_values = valid_options.get(options_key, [])
        if value not in allowed_values:
            return False, f'"{value}" is not a valid {display_name}. Please select from the dropdown.'

    return True, None
