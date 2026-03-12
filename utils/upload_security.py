"""
File Upload Security Module

Provides secure file upload handling with:
- MIME type validation (not just extension)
- Content validation (actual image decoding)
- Decompression bomb protection (max pixels)
- EXIF/metadata stripping via re-encoding
- Size limits
- Path traversal prevention
- Randomized filenames

Usage:
    from utils.upload_security import validate_upload, save_secure_upload

    file = request.files.get('photo')
    result = validate_upload(file, allowed_types=['image/png', 'image/jpeg'])
    if result['valid']:
        path = save_secure_upload(file, 'uploads/listings')
"""
import os
import io
from PIL import Image
import secrets
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from werkzeug.utils import secure_filename

# ============================================================================
# Decompression Bomb Protection
# ============================================================================
# Maximum image dimensions to prevent decompression bombs
MAX_IMAGE_PIXELS = 25_000_000  # 25 megapixels (e.g., 5000x5000)
MAX_IMAGE_WIDTH = 8000  # Maximum width in pixels
MAX_IMAGE_HEIGHT = 8000  # Maximum height in pixels

# Configure Pillow's decompression bomb protection
try:
    from PIL import Image
    # Set Pillow's built-in decompression bomb limit
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
except ImportError:
    pass

# Maximum file sizes by category
MAX_FILE_SIZES = {
    'listing_photo': 10 * 1024 * 1024,   # 10MB
    'message_attachment': 5 * 1024 * 1024,  # 5MB
    'report_evidence': 10 * 1024 * 1024,  # 10MB
    'default': 5 * 1024 * 1024,  # 5MB default
}

# Allowed MIME types and their extensions
ALLOWED_IMAGE_TYPES = {
    'image/png': ['.png'],
    'image/jpeg': ['.jpg', '.jpeg'],
    'image/webp': ['.webp'],
    'image/heic': ['.heic'],
}

# SVG is explicitly DISALLOWED due to XSS risks
DISALLOWED_TYPES = frozenset([
    'image/svg+xml',
    'application/xml',
    'text/xml',
    'text/html',
    'application/javascript',
    'text/javascript',
])

# Magic bytes for image format detection
IMAGE_MAGIC_BYTES = {
    b'\x89PNG\r\n\x1a\n': 'png',
    b'\xff\xd8\xff': 'jpeg',
    b'RIFF': 'webp',  # WebP starts with RIFF....WEBP
}


def get_image_type_from_content(file_content: bytes) -> Optional[str]:
    """
    Detect actual image type from file content (magic bytes).

    Args:
        file_content: Raw file bytes

    Returns:
        Image type string ('png', 'jpeg', 'webp', 'heic') or None
    """
    # Check magic bytes
    for magic, img_type in IMAGE_MAGIC_BYTES.items():
        if file_content.startswith(magic):
            if img_type == 'webp':
                # WebP has additional validation
                if len(file_content) >= 12 and file_content[8:12] == b'WEBP':
                    return 'webp'
            else:
                return img_type

    # HEIC: uses ISO Base Media File Format - 'ftyp' box at offset 4
    if len(file_content) >= 12 and file_content[4:8] == b'ftyp':
        brand = file_content[8:12]
        if brand in (b'heic', b'heis', b'mif1', b'msf1', b'hevc', b'hevx'):
            return 'heic'

    # Fallback to Pillow
    try:
        img = Image.open(io.BytesIO(file_content))
        fmt = img.format  # e.g. 'PNG', 'JPEG', 'WEBP'
        if fmt:
            return fmt.lower()
    except Exception:
        pass

    return None


def validate_image_content(file_content: bytes) -> Tuple[bool, Optional[str]]:
    """
    Validate that file content is actually a valid image by attempting to decode it.
    Also checks for decompression bombs and suspicious metadata.

    Args:
        file_content: Raw file bytes

    Returns:
        Tuple of (is_valid, error_message)
    """
    # HEIC: Pillow requires the pillow-heif plugin to decode HEIC files.
    # If the file passes magic-byte detection (ftyp box with heic brand), accept it.
    if len(file_content) >= 12 and file_content[4:8] == b'ftyp':
        brand = file_content[8:12]
        if brand in (b'heic', b'heis', b'mif1', b'msf1', b'hevc', b'hevx'):
            return True, None

    try:
        # Try PIL/Pillow if available (most thorough)
        try:
            from PIL import Image, ImageFile
            # Don't load truncated images
            ImageFile.LOAD_TRUNCATED_IMAGES = False

            img = Image.open(io.BytesIO(file_content))
            img.verify()  # Verify it's a valid image

            # Re-open after verify (verify closes the file)
            img = Image.open(io.BytesIO(file_content))

            # Check image dimensions for decompression bomb
            width, height = img.size
            if width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT:
                return False, f"Image dimensions too large. Maximum: {MAX_IMAGE_WIDTH}x{MAX_IMAGE_HEIGHT}"

            pixel_count = width * height
            if pixel_count > MAX_IMAGE_PIXELS:
                return False, f"Image has too many pixels ({pixel_count:,}). Maximum: {MAX_IMAGE_PIXELS:,}"

            # Check for suspicious content in image metadata
            # Some attacks embed scripts in EXIF data
            if hasattr(img, '_getexif') and img._getexif():
                exif = img._getexif()
                if exif:
                    for tag, value in exif.items():
                        if isinstance(value, str):
                            # Check for script-like content
                            lower_val = value.lower()
                            if '<script' in lower_val or 'javascript:' in lower_val:
                                return False, "Suspicious content detected in image metadata"

            return True, None

        except ImportError:
            # PIL not available, use basic validation
            detected_type = get_image_type_from_content(file_content)
            if detected_type:
                return True, None
            return False, "Could not validate image content"

    except Image.DecompressionBombError:
        return False, "Image is too large (potential decompression bomb)"
    except Exception as e:
        return False, f"Invalid image: {str(e)}"


def validate_upload(
    file,
    allowed_types: Optional[List[str]] = None,
    max_size: Optional[int] = None,
    category: str = 'default'
) -> Dict[str, Any]:
    """
    Validate an uploaded file for security.

    Args:
        file: FileStorage object from request.files
        allowed_types: List of allowed MIME types (e.g., ['image/png', 'image/jpeg'])
        max_size: Maximum file size in bytes (overrides category default)
        category: Size category for default max size

    Returns:
        Dict with keys:
            - valid: bool
            - error: str or None
            - detected_type: str (actual content type)
            - original_filename: str
            - sanitized_filename: str
    """
    result = {
        'valid': False,
        'error': None,
        'detected_type': None,
        'original_filename': None,
        'sanitized_filename': None,
        'size': 0
    }

    # Check file exists
    if not file or not file.filename:
        result['error'] = "No file provided"
        return result

    result['original_filename'] = file.filename

    # Sanitize filename (prevents path traversal)
    sanitized = secure_filename(file.filename)
    if not sanitized:
        result['error'] = "Invalid filename"
        return result
    result['sanitized_filename'] = sanitized

    # Get file extension
    ext = os.path.splitext(sanitized)[1].lower()

    # Read file content
    file.seek(0)
    content = file.read()
    file.seek(0)  # Reset for later use

    result['size'] = len(content)

    # Check file size
    size_limit = max_size or MAX_FILE_SIZES.get(category, MAX_FILE_SIZES['default'])
    if len(content) > size_limit:
        result['error'] = f"File too large. Maximum size is {size_limit // (1024*1024)}MB"
        return result

    # Check for empty file
    if len(content) == 0:
        result['error'] = "Empty file"
        return result

    # Detect actual content type
    detected_type = get_image_type_from_content(content)
    if detected_type:
        result['detected_type'] = f"image/{detected_type}"

    # Check against disallowed types
    claimed_type = file.content_type or ''
    if claimed_type in DISALLOWED_TYPES:
        result['error'] = f"File type not allowed: {claimed_type}"
        return result

    # Set default allowed types if not specified
    if allowed_types is None:
        allowed_types = list(ALLOWED_IMAGE_TYPES.keys())

    # Validate MIME type matches content
    if detected_type:
        detected_mime = f"image/{detected_type}"
        if detected_mime not in allowed_types:
            result['error'] = f"File type not allowed: {detected_mime}"
            return result

        # Check extension matches content
        allowed_exts = ALLOWED_IMAGE_TYPES.get(detected_mime, [])
        if ext and ext not in allowed_exts:
            result['error'] = f"File extension ({ext}) doesn't match content type ({detected_type})"
            return result
    else:
        # Could not detect type - reject for safety
        result['error'] = "Could not verify file type. Only images are allowed."
        return result

    # Validate actual image content (decode test)
    is_valid_image, img_error = validate_image_content(content)
    if not is_valid_image:
        result['error'] = img_error or "Invalid image file"
        return result

    result['valid'] = True
    return result


def generate_secure_filename(original_filename: str, prefix: str = '') -> str:
    """
    Generate a secure, randomized filename.

    Args:
        original_filename: Original filename (for extension)
        prefix: Optional prefix for the filename

    Returns:
        Secure filename like: prefix_a1b2c3d4e5f6.jpg
    """
    # Get extension from original
    ext = os.path.splitext(secure_filename(original_filename))[1].lower()
    if not ext:
        ext = '.bin'

    # Generate random component
    random_part = secrets.token_hex(12)  # 24 character hex string

    # Build filename
    if prefix:
        return f"{prefix}_{random_part}{ext}"
    return f"{random_part}{ext}"


def strip_metadata_and_reencode(file_content: bytes, target_format: str = 'JPEG') -> Tuple[Optional[bytes], Optional[str]]:
    """
    Strip EXIF/metadata from an image by re-encoding it.
    This removes all metadata including GPS location, camera info, etc.

    Args:
        file_content: Raw image bytes
        target_format: Output format ('JPEG', 'PNG', 'WEBP')

    Returns:
        Tuple of (clean_image_bytes, error_message)
    """
    try:
        from PIL import Image

        # Open the image
        img = Image.open(io.BytesIO(file_content))

        # Convert to RGB if necessary (removes alpha channel for JPEG)
        if target_format == 'JPEG' and img.mode in ('RGBA', 'P', 'LA'):
            # Create white background for transparent images
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')

        # Re-encode without metadata
        output = io.BytesIO()

        # Format-specific options
        if target_format == 'JPEG':
            img.save(output, format='JPEG', quality=92, optimize=True, exif=b'')
        elif target_format == 'PNG':
            img.save(output, format='PNG', optimize=True)
        elif target_format == 'WEBP':
            img.save(output, format='WEBP', quality=92, method=4)
        else:
            img.save(output, format=target_format)

        return output.getvalue(), None

    except ImportError:
        return None, "Pillow not installed, cannot strip metadata"
    except Exception as e:
        return None, f"Error stripping metadata: {str(e)}"


def has_exif_data(file_content: bytes) -> bool:
    """
    Check if an image contains EXIF metadata.

    Args:
        file_content: Raw image bytes

    Returns:
        True if image contains EXIF data
    """
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(file_content))

        # Check for EXIF in JPEG
        if hasattr(img, '_getexif') and img._getexif():
            return True

        # Check for info dict (other metadata)
        if img.info and any(key.lower() in ['exif', 'icc_profile', 'photoshop'] for key in img.info.keys()):
            return True

        return False

    except Exception:
        return False


def save_secure_upload(
    file,
    upload_dir: str,
    allowed_types: Optional[List[str]] = None,
    max_size: Optional[int] = None,
    category: str = 'default',
    strip_metadata: bool = True
) -> Dict[str, Any]:
    """
    Validate and save an uploaded file securely.

    Args:
        file: FileStorage object from request.files
        upload_dir: Directory to save to (relative to static/)
        allowed_types: List of allowed MIME types
        max_size: Maximum file size in bytes
        category: Size category for default max size
        strip_metadata: If True, re-encode image to strip EXIF/metadata

    Returns:
        Dict with keys:
            - success: bool
            - error: str or None
            - path: str (relative path for database storage)
            - full_path: str (absolute filesystem path)
            - metadata_stripped: bool (whether metadata was stripped)
    """
    result = {
        'success': False,
        'error': None,
        'path': None,
        'full_path': None,
        'metadata_stripped': False
    }

    # Validate the upload
    validation = validate_upload(file, allowed_types, max_size, category)
    if not validation['valid']:
        result['error'] = validation['error']
        return result

    # Read file content for potential re-encoding
    file.seek(0)
    content = file.read()
    file.seek(0)

    # Strip metadata if requested
    if strip_metadata:
        detected_type = validation.get('detected_type', 'image/jpeg')
        format_map = {
            'image/jpeg': 'JPEG',
            'image/png': 'PNG',
            'image/webp': 'WEBP',
            'image/heic': 'JPEG',  # Re-encode HEIC as JPEG (requires pillow-heif; falls back gracefully)
        }
        target_format = format_map.get(detected_type, 'JPEG')

        clean_content, strip_error = strip_metadata_and_reencode(content, target_format)
        if clean_content:
            content = clean_content
            result['metadata_stripped'] = True
        # If stripping fails, continue with original content (log but don't fail)

    # Generate secure filename
    secure_name = generate_secure_filename(file.filename)

    # Build paths
    # upload_dir should be like 'uploads/listings'
    static_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'static'
    )
    full_dir = os.path.join(static_dir, upload_dir)

    # Ensure directory exists
    os.makedirs(full_dir, exist_ok=True)

    # Full path for saving
    full_path = os.path.join(full_dir, secure_name)

    # Relative path for database
    relative_path = os.path.join(upload_dir, secure_name)

    try:
        # Save the (potentially re-encoded) content
        with open(full_path, 'wb') as f:
            f.write(content)

        # Verify saved file
        if not os.path.exists(full_path):
            result['error'] = "Failed to save file"
            return result

        result['success'] = True
        result['path'] = relative_path
        result['full_path'] = full_path

    except Exception as e:
        result['error'] = f"Error saving file: {str(e)}"
        # Clean up partial file
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except:
                pass

    return result


def delete_upload(path: str) -> bool:
    """
    Safely delete an uploaded file.

    Args:
        path: Relative path (as stored in database)

    Returns:
        True if deleted, False otherwise
    """
    if not path:
        return False

    # Prevent path traversal
    if '..' in path or path.startswith('/'):
        return False

    static_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'static'
    )
    full_path = os.path.join(static_dir, path)

    # Verify path is within static directory
    full_path = os.path.realpath(full_path)
    if not full_path.startswith(os.path.realpath(static_dir)):
        return False

    try:
        if os.path.exists(full_path):
            os.remove(full_path)
            return True
    except Exception:
        pass

    return False
