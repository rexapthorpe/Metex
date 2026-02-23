"""
Listings Blueprint - Helper Functions

Contains file upload handling, validation, and set item management utilities.
"""

from werkzeug.utils import secure_filename
import os

# Photo upload settings
UPLOAD_FOLDER = os.path.join("static", "uploads", "listings")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


def allowed_file(filename):
    """Check if filename has an allowed extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_edition_numbers(issue_number, issue_total, edition_number, edition_total):
    """
    Validate edition and issue numbering rules.
    Returns (is_valid, error_message)
    """
    # Issue numbers: both or neither required
    if (issue_number is not None and issue_total is None) or (issue_number is None and issue_total is not None):
        return False, "Issue number and issue total must both be provided or both be empty"

    # If both provided, validate issue_number <= issue_total
    if issue_number is not None and issue_total is not None:
        if issue_number > issue_total:
            return False, "Issue number cannot be greater than issue total"
        if issue_number < 1 or issue_total < 1:
            return False, "Issue number and total must be at least 1"

    # Edition numbers: both or neither required
    if (edition_number is not None and edition_total is None) or (edition_number is None and edition_total is not None):
        return False, "Edition number and edition total must both be provided or both be empty"

    # If both provided, validate edition_number <= edition_total
    if edition_number is not None and edition_total is not None:
        if edition_number > edition_total:
            return False, "Edition number cannot be greater than edition total"
        if edition_number < 1 or edition_total < 1:
            return False, "Edition number and total must be at least 1"

    return True, None


def save_uploaded_photo(photo_file, subfolder="listings"):
    """
    Save an uploaded photo file and return the relative file path.
    Returns None if no file or invalid file.
    """
    if not photo_file or not photo_file.filename or not allowed_file(photo_file.filename):
        return None

    upload_path = os.path.join("static", "uploads", subfolder)
    os.makedirs(upload_path, exist_ok=True)

    safe_name = secure_filename(photo_file.filename)
    base, ext = os.path.splitext(safe_name)
    candidate = safe_name
    i = 1
    while os.path.exists(os.path.join(upload_path, candidate)):
        candidate = f"{base}_{i}{ext}"
        i += 1

    photo_filename = candidate
    full_path = os.path.join(upload_path, photo_filename)
    photo_file.save(full_path)

    return f"uploads/{subfolder}/{photo_filename}"


def update_set_items(conn, listing_id, set_items_data):
    """
    Update set items for a listing. Handles add/remove/reorder operations.
    set_items_data should be a list of dicts with set item details.
    """
    # Get existing set items
    existing_items = conn.execute(
        'SELECT id FROM listing_set_items WHERE listing_id = ?',
        (listing_id,)
    ).fetchall()
    existing_ids = {row['id'] for row in existing_items}

    # Track which IDs are in the new data
    new_ids = set()

    # Process each item in the new data
    for idx, item_data in enumerate(set_items_data):
        item_id = item_data.get('id')

        if item_id and item_id in existing_ids:
            # Update existing item
            conn.execute(
                '''
                UPDATE listing_set_items
                SET position_index = ?,
                    metal = ?, product_line = ?, product_type = ?,
                    weight = ?, purity = ?, mint = ?, year = ?,
                    finish = ?, grade = ?, coin_series = ?,
                    special_designation = ?, graded = ?, grading_service = ?,
                    edition_number = ?, edition_total = ?
                WHERE id = ?
                ''',
                (
                    idx,
                    item_data.get('metal'), item_data.get('product_line'),
                    item_data.get('product_type'), item_data.get('weight'),
                    item_data.get('purity'), item_data.get('mint'),
                    item_data.get('year'), item_data.get('finish'),
                    item_data.get('grade'), item_data.get('coin_series'),
                    item_data.get('special_designation'), item_data.get('graded', 0),
                    item_data.get('grading_service'), item_data.get('edition_number'),
                    item_data.get('edition_total'), item_id
                )
            )
            new_ids.add(item_id)
        else:
            # Insert new item
            cursor = conn.execute(
                '''
                INSERT INTO listing_set_items (
                    listing_id, position_index, metal, product_line, product_type,
                    weight, purity, mint, year, finish, grade, coin_series,
                    special_designation, graded, grading_service, edition_number, edition_total
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    listing_id, idx,
                    item_data.get('metal'), item_data.get('product_line'),
                    item_data.get('product_type'), item_data.get('weight'),
                    item_data.get('purity'), item_data.get('mint'),
                    item_data.get('year'), item_data.get('finish'),
                    item_data.get('grade'), item_data.get('coin_series'),
                    item_data.get('special_designation'), item_data.get('graded', 0),
                    item_data.get('grading_service'), item_data.get('edition_number'),
                    item_data.get('edition_total')
                )
            )
            new_item_id = cursor.lastrowid
            new_ids.add(new_item_id)
            item_data['id'] = new_item_id  # Store for photo handling

    # Delete items that were removed (in existing but not in new)
    items_to_delete = existing_ids - new_ids
    for item_id in items_to_delete:
        # Delete photos first (cascade should handle this, but be explicit)
        conn.execute('DELETE FROM listing_set_item_photos WHERE set_item_id = ?', (item_id,))
        conn.execute('DELETE FROM listing_set_items WHERE id = ?', (item_id,))


def handle_set_item_photos(conn, set_item_id, photo_files):
    """
    Handle photo uploads for a set item (up to 3 photos).
    photo_files should be a list of file objects.
    """
    # Delete existing photos for this item
    conn.execute('DELETE FROM listing_set_item_photos WHERE set_item_id = ?', (set_item_id,))

    # Upload and insert new photos
    for idx, photo_file in enumerate(photo_files[:3]):  # Max 3 photos
        if photo_file and photo_file.filename:
            file_path = save_uploaded_photo(photo_file, subfolder="listings")
            if file_path:
                conn.execute(
                    '''
                    INSERT INTO listing_set_item_photos (set_item_id, file_path, position_index)
                    VALUES (?, ?, ?)
                    ''',
                    (set_item_id, file_path, idx + 1)
                )
