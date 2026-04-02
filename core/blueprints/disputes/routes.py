"""
Dispute Routes (Phase 2)
========================
Buyer-protection dispute submission flows.

Endpoints:
  POST /disputes/open          — buyer opens a new dispute
  POST /disputes/<id>/respond  — seller responds to a dispute
  POST /disputes/<id>/evidence — buyer or seller submits evidence
"""

import os
from flask import request, session, jsonify

import database as _db_module
from services.dispute_service import (
    open_dispute,
    add_seller_response,
    add_evidence,
    VALID_EVIDENCE_TYPES,
)
from . import disputes_bp

_ALLOWED_EVIDENCE_MIME = ['image/png', 'image/jpeg', 'image/webp', 'image/heic']
_EVIDENCE_UPLOAD_DIR = 'uploads/dispute_evidence'


def _current_user():
    return session.get('user_id')


def _get_conn():
    return _db_module.get_db_connection()


# ---------------------------------------------------------------------------
# Buyer: open a dispute
# ---------------------------------------------------------------------------

@disputes_bp.route('/disputes/open', methods=['POST'])
def open_dispute_route():
    user_id = _current_user()
    if not user_id:
        return jsonify({'error': 'Login required.'}), 401

    order_id = request.form.get('order_id', type=int)
    dispute_type = request.form.get('dispute_type', '').strip()
    description = request.form.get('description', '').strip()

    if not order_id:
        return jsonify({'error': 'Order ID is required.'}), 400

    try:
        dispute_id = open_dispute(order_id, user_id, dispute_type, description)
        return jsonify({'success': True, 'dispute_id': dispute_id})
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400


# ---------------------------------------------------------------------------
# Seller: respond to a dispute
# ---------------------------------------------------------------------------

@disputes_bp.route('/disputes/<int:dispute_id>/respond', methods=['POST'])
def respond_to_dispute(dispute_id):
    user_id = _current_user()
    if not user_id:
        return jsonify({'error': 'Login required.'}), 401

    note = request.form.get('note', '').strip()
    if not note or len(note) < 5:
        return jsonify({'error': 'A response of at least 5 characters is required.'}), 400

    try:
        add_seller_response(dispute_id, user_id, note)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    # Optional evidence file submitted alongside the response
    _maybe_attach_file(dispute_id, user_id, request.files.get('evidence_file'),
                       actor_type='seller', evidence_type='photo', note=note)

    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# Buyer or Seller: submit evidence
# ---------------------------------------------------------------------------

@disputes_bp.route('/disputes/<int:dispute_id>/evidence', methods=['POST'])
def submit_evidence(dispute_id):
    user_id = _current_user()
    if not user_id:
        return jsonify({'error': 'Login required.'}), 401

    note = request.form.get('note', '').strip() or None
    evidence_type = request.form.get('evidence_type', 'other').strip()
    if evidence_type not in VALID_EVIDENCE_TYPES:
        evidence_type = 'other'

    # Determine actor_type from DB
    conn = _get_conn()
    dispute = conn.execute(
        'SELECT buyer_id, seller_id FROM disputes WHERE id = ?', (dispute_id,)
    ).fetchone()
    conn.close()

    if not dispute:
        return jsonify({'error': 'Dispute not found.'}), 404

    if user_id == dispute['buyer_id']:
        actor_type = 'buyer'
    elif user_id == dispute['seller_id']:
        actor_type = 'seller'
    else:
        return jsonify({'error': 'You are not a party to this dispute.'}), 403

    file_path = None
    uploaded_file = request.files.get('evidence_file')
    if uploaded_file and uploaded_file.filename:
        from utils.upload_security import save_secure_upload
        result = save_secure_upload(
            uploaded_file,
            upload_dir=_EVIDENCE_UPLOAD_DIR,
            allowed_types=_ALLOWED_EVIDENCE_MIME,
            category='report_evidence',
        )
        if result.get('success'):
            file_path = result['path']
        else:
            return jsonify({'error': f"File rejected: {result.get('error', 'unknown')}"}), 400

    if not file_path and not note:
        return jsonify({'error': 'Must provide a file or a note.'}), 400

    try:
        add_evidence(dispute_id, user_id, actor_type, evidence_type, file_path, note)
        return jsonify({'success': True})
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _maybe_attach_file(dispute_id, user_id, uploaded_file, actor_type, evidence_type, note):
    """Silently attempt to save an optional attached file as dispute evidence."""
    if not uploaded_file or not uploaded_file.filename:
        return
    try:
        from utils.upload_security import save_secure_upload
        result = save_secure_upload(
            uploaded_file,
            upload_dir=_EVIDENCE_UPLOAD_DIR,
            allowed_types=_ALLOWED_EVIDENCE_MIME,
            category='report_evidence',
        )
        if result.get('success'):
            add_evidence(dispute_id, user_id, actor_type, evidence_type, result['path'], note)
    except Exception as exc:
        print(f'[DISPUTE] Optional file attachment failed: {exc}')
