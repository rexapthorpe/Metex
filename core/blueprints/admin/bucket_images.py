"""
Admin Bucket Image Catalog Routes
==================================
All routes under /admin prefix (registered via admin_bp).

Endpoints:
  GET  /admin/api/bucket-images/buckets              — list standard buckets
  POST /admin/api/bucket-images/buckets              — create standard bucket
  GET  /admin/api/bucket-images/buckets/<id>         — bucket detail + assets
  PUT  /admin/api/bucket-images/buckets/<id>         — update bucket fields
  POST /admin/api/bucket-images/buckets/<id>/ingest-url     — ingest from URL
  POST /admin/api/bucket-images/buckets/<id>/upload         — upload directly
  POST /admin/api/bucket-images/buckets/<id>/auto-activate  — activate best candidate
  POST /admin/api/bucket-images/assets/<id>/approve  — approve a pending asset
  POST /admin/api/bucket-images/assets/<id>/activate — set as active cover
  POST /admin/api/bucket-images/assets/<id>/reject   — reject a candidate
  DELETE /admin/api/bucket-images/assets/<id>        — hard-delete asset + files
  POST /admin/api/bucket-images/assets/bulk-reject   — bulk-reject by id list
  GET  /admin/api/bucket-images/coverage             — coverage statistics report
"""

import logging
from flask import jsonify, request, session

from utils.auth_utils import admin_required
from . import admin_bp
import services.bucket_image_service as bis

log = logging.getLogger(__name__)


def _admin_id() -> int:
    return session.get('user_id')


# ---------------------------------------------------------------------------
# Standard bucket CRUD
# ---------------------------------------------------------------------------

@admin_bp.route('/api/bucket-images/buckets')
@admin_required
def bi_list_buckets():
    """
    List standard buckets with cover-image stats.

    Query params:
      missing_cover    (bool)  — buckets with no active cover
      pending_only     (bool)  — pending candidates, no active image
      low_confidence   (bool)  — active image confidence < threshold
      conf_threshold   (float) — threshold for low_confidence (default 0.6)
      retailer_only    (bool)  — all non-rejected assets are retailer-sourced
      missing_license  (bool)  — active image has no license_type
      metal            (str)   — filter by metal
      active_only      (bool)  — skip inactive standard_bucket rows (default true)
    """
    def _bool(key, default='false'):
        return request.args.get(key, default).lower() == 'true'

    missing_cover   = _bool('missing_cover')
    pending_only    = _bool('pending_only')
    low_confidence  = _bool('low_confidence')
    retailer_only   = _bool('retailer_only')
    missing_license = _bool('missing_license')
    no_candidates   = _bool('no_candidates')
    metal           = request.args.get('metal', '').strip() or None
    active_only     = request.args.get('active_only', 'true').lower() != 'false'
    try:
        conf_threshold = float(request.args.get('conf_threshold', '0.6'))
    except ValueError:
        conf_threshold = 0.6

    try:
        buckets = bis.list_standard_buckets(
            missing_cover=missing_cover,
            metal=metal,
            active_only=active_only,
            pending_only=pending_only,
            low_confidence=low_confidence,
            low_confidence_threshold=conf_threshold,
            retailer_only=retailer_only,
            missing_license=missing_license,
            no_candidates=no_candidates,
        )
        return jsonify({'success': True, 'buckets': buckets})
    except Exception as exc:
        log.exception('bi_list_buckets error')
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/bucket-images/buckets', methods=['POST'])
@admin_required
def bi_create_bucket():
    """Create a new standard bucket entry."""
    data = request.get_json(silent=True) or {}
    required = ('slug', 'title', 'metal')
    missing = [f for f in required if not (data.get(f) or '').strip()]
    if missing:
        return jsonify({'success': False, 'error': f"Missing required fields: {', '.join(missing)}"}), 400
    try:
        bucket_id = bis.create_standard_bucket(data)
        return jsonify({'success': True, 'bucket_id': bucket_id}), 201
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        log.exception('bi_create_bucket error')
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/bucket-images/buckets/<int:bucket_id>')
@admin_required
def bi_get_bucket(bucket_id):
    """Return a standard bucket with its full asset list."""
    try:
        bucket = bis.get_standard_bucket_with_assets(bucket_id)
        if not bucket:
            return jsonify({'success': False, 'error': 'Bucket not found.'}), 404
        return jsonify({'success': True, 'bucket': bucket})
    except Exception as exc:
        log.exception('bi_get_bucket error')
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/bucket-images/buckets/<int:bucket_id>', methods=['PUT'])
@admin_required
def bi_update_bucket(bucket_id):
    """Update mutable fields on a standard bucket."""
    data = request.get_json(silent=True) or {}
    try:
        bis.update_standard_bucket(bucket_id, data)
        return jsonify({'success': True})
    except Exception as exc:
        log.exception('bi_update_bucket error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# Ingestion endpoints
# ---------------------------------------------------------------------------

@admin_bp.route('/api/bucket-images/buckets/<int:bucket_id>/ingest-url', methods=['POST'])
@admin_required
def bi_ingest_url(bucket_id):
    """
    Download an image from a URL and ingest it as a candidate for this bucket.

    Expected JSON body:
      url            (required) — direct image URL
      source_name    (required) — human-readable source label
      source_type    (required) — one of: internal_upload | public_domain | licensed | approved_db | retailer | unknown
      source_page_url          — the page where the image was found
      attribution_text
      license_type             — e.g. "public_domain", "CC-BY-4.0", "all_rights_reserved"
      rights_note
      usage_allowed            — bool (default true)
      raw_source_title         — title / alt text from source page (used for confidence scoring)
      raw_source_metadata      — arbitrary metadata dict
      matched_title / matched_weight / matched_mint / matched_year / matched_series
    """
    data = request.get_json(silent=True) or {}
    url = (data.get('url') or '').strip()
    if not url:
        return jsonify({'success': False, 'error': 'url is required.'}), 400
    source_name = (data.get('source_name') or '').strip()
    if not source_name:
        return jsonify({'success': False, 'error': 'source_name is required.'}), 400
    source_type = (data.get('source_type') or 'unknown').strip()

    source_info = {
        'source_name':       source_name,
        'source_type':       source_type,
        'source_page_url':   data.get('source_page_url'),
        'original_image_url': url,
        'attribution_text':  data.get('attribution_text'),
        'license_type':      data.get('license_type'),
        'rights_note':       data.get('rights_note'),
        'usage_allowed':     bool(data.get('usage_allowed', True)),
        'raw_source_title':  data.get('raw_source_title', ''),
        'raw_source_metadata': data.get('raw_source_metadata'),
        'matched_title':     data.get('matched_title'),
        'matched_weight':    data.get('matched_weight'),
        'matched_mint':      data.get('matched_mint'),
        'matched_year':      data.get('matched_year'),
        'matched_series':    data.get('matched_series'),
    }

    try:
        result = bis.ingest_from_url(
            standard_bucket_id=bucket_id,
            url=url,
            source_info=source_info,
            admin_user_id=_admin_id(),
        )
        return jsonify({'success': True, **result}), 201
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        log.exception('bi_ingest_url error bucket=%s', bucket_id)
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/bucket-images/buckets/<int:bucket_id>/upload', methods=['POST'])
@admin_required
def bi_upload_image(bucket_id):
    """
    Accept a multipart/form-data image upload for a bucket.

    Form fields:
      image            (required) — the image file
      source_name      (required) — label (default: "Admin Upload")
      source_type      (default: internal_upload)
      attribution_text
      license_type
      rights_note
      raw_source_title
    """
    file_obj = request.files.get('image')
    if not file_obj or not file_obj.filename:
        return jsonify({'success': False, 'error': 'image file is required.'}), 400

    source_info = {
        'source_name':      request.form.get('source_name', 'Admin Upload').strip() or 'Admin Upload',
        'source_type':      request.form.get('source_type', 'internal_upload').strip(),
        'attribution_text': request.form.get('attribution_text'),
        'license_type':     request.form.get('license_type'),
        'rights_note':      request.form.get('rights_note'),
        'raw_source_title': request.form.get('raw_source_title', ''),
        'usage_allowed':    True,
    }

    try:
        result = bis.ingest_from_upload(
            standard_bucket_id=bucket_id,
            file_stream=file_obj,
            source_info=source_info,
            admin_user_id=_admin_id(),
        )
        return jsonify({'success': True, **result}), 201
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        log.exception('bi_upload_image error bucket=%s', bucket_id)
        return jsonify({'success': False, 'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# Asset lifecycle
# ---------------------------------------------------------------------------

@admin_bp.route('/api/bucket-images/assets/<int:asset_id>/approve', methods=['POST'])
@admin_required
def bi_approve_asset(asset_id):
    """Move an asset from pending → approved."""
    try:
        asset = bis.approve_asset(asset_id, admin_user_id=_admin_id())
        return jsonify({'success': True, 'asset': asset})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 404
    except Exception as exc:
        log.exception('bi_approve_asset error')
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/bucket-images/assets/<int:asset_id>/activate', methods=['POST'])
@admin_required
def bi_activate_asset(asset_id):
    """Set an asset as the active cover image for its bucket."""
    try:
        asset = bis.activate_asset(asset_id, admin_user_id=_admin_id())
        return jsonify({'success': True, 'asset': asset})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 404
    except Exception as exc:
        log.exception('bi_activate_asset error')
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/bucket-images/assets/<int:asset_id>/reject', methods=['POST'])
@admin_required
def bi_reject_asset(asset_id):
    """Mark an asset as rejected (preserved in DB for audit; files kept on disk)."""
    try:
        asset = bis.reject_asset(asset_id, admin_user_id=_admin_id())
        return jsonify({'success': True, 'asset': asset})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 404
    except Exception as exc:
        log.exception('bi_reject_asset error')
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/bucket-images/assets/<int:asset_id>', methods=['DELETE'])
@admin_required
def bi_delete_asset(asset_id):
    """Hard-delete an asset: removes the DB row and all on-disk files."""
    try:
        deleted = bis.delete_asset(asset_id)
        if not deleted:
            return jsonify({'success': False, 'error': 'Asset not found.'}), 404
        return jsonify({'success': True})
    except Exception as exc:
        log.exception('bi_delete_asset error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# Bulk / convenience operations
# ---------------------------------------------------------------------------

@admin_bp.route('/api/bucket-images/buckets/<int:bucket_id>/auto-activate', methods=['POST'])
@admin_required
def bi_auto_activate_best(bucket_id):
    """
    Activate the highest-confidence non-rejected candidate for a bucket.
    Prefers approved > pending; breaks ties by confidence score.
    Returns 404 if no candidates exist.
    """
    try:
        asset = bis.auto_activate_best_candidate(bucket_id, admin_user_id=_admin_id())
        if not asset:
            return jsonify({'success': False, 'error': 'No candidates available.'}), 404
        return jsonify({'success': True, 'asset': asset})
    except Exception as exc:
        log.exception('bi_auto_activate_best error bucket=%s', bucket_id)
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/bucket-images/assets/bulk-reject', methods=['POST'])
@admin_required
def bi_bulk_reject_assets():
    """
    Bulk-reject a list of assets.

    Expected JSON body:
      asset_ids  — list of integer asset IDs to reject

    Active images are NOT rejected (they must be demoted individually).
    Returns count of assets changed.
    """
    data      = request.get_json(silent=True) or {}
    asset_ids = data.get('asset_ids', [])
    if not isinstance(asset_ids, list) or not asset_ids:
        return jsonify({'success': False, 'error': 'asset_ids must be a non-empty list.'}), 400
    try:
        count = bis.bulk_reject_assets(
            [int(i) for i in asset_ids],
            admin_user_id=_admin_id(),
        )
        return jsonify({'success': True, 'rejected_count': count})
    except Exception as exc:
        log.exception('bi_bulk_reject_assets error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# Coverage reporting
# ---------------------------------------------------------------------------

@admin_bp.route('/api/bucket-images/coverage')
@admin_required
def bi_coverage_report():
    """
    Return image coverage statistics for all active standard buckets.

    Response:
      {
        total, with_active, pending_only, no_candidates, coverage_pct,
        by_metal: {metal: {total, with_active, coverage_pct}},
        by_source: {source_name: count}
      }
    """
    try:
        report = bis.get_coverage_report()
        return jsonify({'success': True, 'report': report})
    except Exception as exc:
        log.exception('bi_coverage_report error')
        return jsonify({'success': False, 'error': str(exc)}), 500
