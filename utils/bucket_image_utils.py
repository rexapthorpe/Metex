"""
Bucket Image Resolution Utilities
===================================
Provides helpers used by Jinja templates and view code to resolve the active
cover image URL for a standard bucket.

Usage in a template (after registration as a Jinja global):
    {{ bucket_cover_url(category_bucket_id) }}

Returns a URL string like "/static/uploads/bucket_images/web/abc123_web.jpg"
or None if no active image exists for the bucket (use a placeholder in templates).
"""

from typing import Optional


def get_bucket_cover_url(category_bucket_id: Optional[int]) -> Optional[str]:
    """
    Resolve the active cover image URL for a bucket, identified by the
    category_bucket_id stored in the `categories` table.

    Returns a URL path relative to the site root (e.g.
    "/static/uploads/bucket_images/web/abc123_web.jpg") or None.

    Designed to be called from Jinja templates as a global function.
    Safe — never raises; returns None on any error.
    """
    if not category_bucket_id:
        return None
    try:
        from services.bucket_image_service import get_active_image_url_by_category_bucket_id
        web_path = get_active_image_url_by_category_bucket_id(category_bucket_id)
        if not web_path:
            return None
        # web_path is relative to static/ e.g. "uploads/bucket_images/web/abc_web.jpg"
        return f'/static/{web_path}'
    except Exception:
        return None


def get_bucket_cover_url_by_standard_id(standard_bucket_id: Optional[int]) -> Optional[str]:
    """
    Same as get_bucket_cover_url but accepts the standard_bucket primary key
    instead of the category_bucket_id.
    """
    if not standard_bucket_id:
        return None
    try:
        from services.bucket_image_service import get_active_image_url
        web_path = get_active_image_url(standard_bucket_id)
        if not web_path:
            return None
        return f'/static/{web_path}'
    except Exception:
        return None
