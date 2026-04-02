"""
Dispute Service (Phase 2 + Phase 3)
====================================
Business logic for buyer-protection disputes.

Dispute window:  30 days from order creation (DISPUTE_WINDOW_DAYS).
                 Hardcoded for Phase 2; delivery confirmation is not yet tracked.
                 Phase 3 can replace with a configurable setting or delivery-based window.

Dispute types:   not_received | not_as_described | counterfeit | wrong_item
Dispute statuses: open | evidence_requested | under_review | resolved_refund |
                  resolved_denied | resolved_partial | escalated | closed

Actor types:     buyer | seller | admin
Evidence types:  photo | tracking_info | message_screenshot | other
Timeline events: opened | evidence_submitted | status_changed | message_added | seller_responded
"""

from datetime import datetime, timedelta

import database as _db_module


DISPUTE_WINDOW_DAYS = 30  # Phase 2: hardcoded. Replace with system_settings lookup in Phase 3.

VALID_DISPUTE_TYPES = frozenset({'not_received', 'not_as_described', 'counterfeit', 'wrong_item'})
VALID_EVIDENCE_TYPES = frozenset({'photo', 'tracking_info', 'message_screenshot', 'other'})
ACTIVE_DISPUTE_STATUSES = frozenset({'open', 'evidence_requested', 'under_review', 'escalated'})


def _get_conn():
    return _db_module.get_db_connection()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _add_timeline_entry(cursor, dispute_id, actor_type, actor_id, event_type, note=None):
    """Insert one row into dispute_timeline. Must be called within an active transaction."""
    cursor.execute(
        '''INSERT INTO dispute_timeline (dispute_id, actor_type, actor_id, event_type, note, created_at)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (dispute_id, actor_type, actor_id, event_type, note, datetime.now().isoformat()),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def can_open_dispute(order_id, buyer_id, conn):
    """
    Return (True, None) if the buyer is eligible to open a dispute on this order,
    or (False, reason_string) if not.

    Checks:
      - order exists and belongs to buyer
      - order is not cancelled or forfeited
      - within DISPUTE_WINDOW_DAYS of order creation
      - no active dispute already exists on this order
    """
    order = conn.execute(
        'SELECT buyer_id, created_at, status FROM orders WHERE id = ?',
        (order_id,)
    ).fetchone()

    if not order:
        return False, 'Order not found.'
    if order['buyer_id'] != buyer_id:
        return False, 'You are not the buyer on this order.'

    status_l = (order['status'] or '').lower()
    if status_l in ('cancelled', 'canceled', 'forfeited'):
        return False, 'Disputes cannot be opened on cancelled or forfeited orders.'

    try:
        order_dt = datetime.fromisoformat(order['created_at'])
    except Exception:
        order_dt = datetime.now()  # graceful fallback — allow if parse fails

    deadline = order_dt + timedelta(days=DISPUTE_WINDOW_DAYS)
    if datetime.now() > deadline:
        return False, (
            f'The {DISPUTE_WINDOW_DAYS}-day dispute window for this order has closed.'
        )

    existing = conn.execute(
        '''SELECT id FROM disputes
           WHERE order_id = ? AND status IN ('open','evidence_requested','under_review','escalated')''',
        (order_id,)
    ).fetchone()
    if existing:
        return False, 'An active dispute already exists for this order.'

    return True, None


def open_dispute(order_id, buyer_id, dispute_type, description):
    """
    Open a new dispute for the given order.

    Returns the new dispute_id on success.
    Raises ValueError with a user-facing message on failure.
    """
    if dispute_type not in VALID_DISPUTE_TYPES:
        raise ValueError(f'Invalid dispute type: {dispute_type}')
    if not description or len(description.strip()) < 10:
        raise ValueError('Please provide a description of at least 10 characters.')

    conn = _get_conn()
    cursor = conn.cursor()

    ok, reason = can_open_dispute(order_id, buyer_id, conn)
    if not ok:
        conn.close()
        raise ValueError(reason)

    # Resolve seller_id from the first listing in the order
    item_row = cursor.execute(
        '''SELECT l.seller_id FROM order_items oi
           JOIN listings l ON oi.listing_id = l.id
           WHERE oi.order_id = ? LIMIT 1''',
        (order_id,)
    ).fetchone()
    seller_id = item_row['seller_id'] if item_row else None

    now = datetime.now().isoformat()
    cursor.execute(
        '''INSERT INTO disputes
               (order_id, opened_by_user_id, buyer_id, seller_id,
                dispute_type, status, description, opened_at)
           VALUES (?, ?, ?, ?, ?, 'open', ?, ?)''',
        (order_id, buyer_id, buyer_id, seller_id,
         dispute_type, description.strip(), now),
    )
    dispute_id = cursor.lastrowid

    _add_timeline_entry(
        cursor, dispute_id, 'buyer', buyer_id, 'opened',
        f'Dispute opened ({dispute_type})',
    )

    conn.commit()
    conn.close()

    # Notify seller (best-effort — failure must not abort the dispute)
    if seller_id:
        try:
            from services.notification_types import notify_dispute_opened
            notify_dispute_opened(seller_id, dispute_id, order_id, dispute_type)
        except Exception as exc:
            print(f'[DISPUTE] notify_dispute_opened failed: {exc}')

    # Recompute risk profiles (Phase 4 — best-effort)
    try:
        from services import risk_service
        risk_service.recompute_risk_profile(buyer_id)
        if seller_id:
            risk_service.recompute_risk_profile(seller_id)
    except Exception as exc:
        print(f'[DISPUTE] risk recompute after open failed: {exc}')

    return dispute_id


def add_seller_response(dispute_id, seller_id, note):
    """
    Record a seller response to an open or evidence_requested dispute.
    Moves status to under_review.
    Notifies the buyer.
    Raises ValueError on authorization or state errors.
    """
    conn = _get_conn()
    cursor = conn.cursor()

    dispute = cursor.execute(
        'SELECT * FROM disputes WHERE id = ?', (dispute_id,)
    ).fetchone()
    if not dispute:
        conn.close()
        raise ValueError('Dispute not found.')
    if dispute['seller_id'] != seller_id:
        conn.close()
        raise ValueError('You are not the seller on this dispute.')
    if dispute['status'] not in ('open', 'evidence_requested'):
        conn.close()
        raise ValueError('This dispute is not in a state that accepts a seller response.')

    cursor.execute(
        "UPDATE disputes SET status = 'under_review' WHERE id = ?",
        (dispute_id,),
    )
    _add_timeline_entry(cursor, dispute_id, 'seller', seller_id, 'seller_responded', note)

    buyer_id = dispute['buyer_id']
    order_id = dispute['order_id']
    conn.commit()
    conn.close()

    # Notify buyer (best-effort)
    try:
        from services.notification_types import notify_dispute_seller_responded
        notify_dispute_seller_responded(buyer_id, dispute_id, order_id)
    except Exception as exc:
        print(f'[DISPUTE] notify_dispute_seller_responded failed: {exc}')


def add_evidence(dispute_id, user_id, actor_type, evidence_type, file_path, note):
    """
    Submit evidence to a dispute.
    user_id must be the buyer or seller on the dispute.
    At least one of file_path or note must be provided.
    Returns the new evidence row id.
    Raises ValueError on authorization or validation errors.
    """
    if not file_path and not (note and note.strip()):
        raise ValueError('Must provide a file or a note.')
    if evidence_type not in VALID_EVIDENCE_TYPES:
        evidence_type = 'other'

    conn = _get_conn()
    cursor = conn.cursor()

    dispute = cursor.execute(
        'SELECT buyer_id, seller_id, status FROM disputes WHERE id = ?',
        (dispute_id,)
    ).fetchone()
    if not dispute:
        conn.close()
        raise ValueError('Dispute not found.')
    if user_id not in (dispute['buyer_id'], dispute['seller_id']):
        conn.close()
        raise ValueError('You are not a party to this dispute.')
    if dispute['status'] not in ACTIVE_DISPUTE_STATUSES:
        conn.close()
        raise ValueError('Evidence cannot be added to a closed or resolved dispute.')

    now = datetime.now().isoformat()
    cursor.execute(
        '''INSERT INTO dispute_evidence
               (dispute_id, submitted_by_user_id, actor_type, evidence_type, file_path, note, submitted_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (dispute_id, user_id, actor_type, evidence_type, file_path, note, now),
    )
    evidence_id = cursor.lastrowid

    _add_timeline_entry(
        cursor, dispute_id, actor_type, user_id, 'evidence_submitted',
        f'{evidence_type} evidence submitted',
    )

    conn.commit()
    conn.close()
    return evidence_id


# ===========================================================================
# Phase 3 — Admin adjudication
# ===========================================================================

# Non-terminal status transitions allowed by admin (forward and backward moves)
ADMIN_STATUS_TRANSITIONS = {
    'open':               frozenset({'evidence_requested', 'under_review', 'escalated'}),
    'evidence_requested': frozenset({'open', 'under_review', 'escalated'}),
    'under_review':       frozenset({'evidence_requested', 'escalated'}),
    'escalated':          frozenset({'under_review', 'evidence_requested'}),
}

# Terminal outcomes that close a dispute
ADMIN_TERMINAL_OUTCOMES = frozenset({'resolved_refund', 'resolved_denied', 'closed'})


def get_dispute_list(status=None, dispute_type=None,
                     buyer_username=None, seller_username=None):
    """
    Return (list_of_dicts, stats_dict) for the admin disputes list view.
    All filters are optional; returns up to 200 most-recent disputes.
    """
    conn = _get_conn()

    conditions = []
    params = []

    if status:
        conditions.append('d.status = ?')
        params.append(status)
    if dispute_type:
        conditions.append('d.dispute_type = ?')
        params.append(dispute_type)
    if buyer_username:
        conditions.append('ub.username LIKE ?')
        params.append(f'%{buyer_username}%')
    if seller_username:
        conditions.append('us.username LIKE ?')
        params.append(f'%{seller_username}%')

    where_clause = (' AND ' + ' AND '.join(conditions)) if conditions else ''

    rows = conn.execute(
        f'''SELECT d.id, d.order_id, d.dispute_type, d.status,
                   d.buyer_id, d.seller_id, d.opened_at, d.resolved_at,
                   d.description, d.resolution_note, d.refund_amount,
                   ub.username AS buyer_username,
                   us.username AS seller_username,
                   o.total_price AS order_amount
            FROM disputes d
            LEFT JOIN users  ub ON d.buyer_id  = ub.id
            LEFT JOIN users  us ON d.seller_id = us.id
            LEFT JOIN orders o  ON d.order_id  = o.id
            WHERE 1=1 {where_clause}
            ORDER BY d.opened_at DESC LIMIT 200''',
        params,
    ).fetchall()

    stats = {
        'open': conn.execute(
            "SELECT COUNT(*) as c FROM disputes WHERE status = 'open'"
        ).fetchone()['c'],
        'under_review': conn.execute(
            "SELECT COUNT(*) as c FROM disputes WHERE status IN ('under_review','escalated')"
        ).fetchone()['c'],
        'resolved_today': conn.execute(
            "SELECT COUNT(*) as c FROM disputes WHERE status LIKE 'resolved%' "
            "AND date(resolved_at) = date('now')"
        ).fetchone()['c'],
    }

    conn.close()

    now = datetime.now()
    result = []
    for r in rows:
        try:
            opened_dt = datetime.fromisoformat(r['opened_at'])
            days_open = (now - opened_dt).days
        except Exception:
            days_open = 0
        result.append({
            'id': r['id'],
            'order_id': r['order_id'],
            'dispute_type': r['dispute_type'],
            'status': r['status'],
            'buyer_id': r['buyer_id'],
            'buyer_username': r['buyer_username'] or '',
            'seller_id': r['seller_id'],
            'seller_username': r['seller_username'] or '',
            'opened_at': r['opened_at'],
            'resolved_at': r['resolved_at'],
            'days_open': days_open,
            'order_amount': r['order_amount'] or 0,
            'description': (r['description'] or '')[:200],
            'resolution_note': r['resolution_note'],
            'refund_amount': r['refund_amount'],
        })
    return result, stats


def get_dispute_detail(dispute_id):
    """
    Return full dispute detail dict for admin review, or None if not found.
    Includes: metadata, evidence, timeline (all entries incl. admin_note),
              and transaction snapshots for the order.
    """
    conn = _get_conn()

    dispute = conn.execute('''
        SELECT d.*,
               ub.username AS buyer_username, ub.email AS buyer_email,
               us.username AS seller_username, us.email AS seller_email,
               o.total_price AS order_amount,
               o.status      AS order_status,
               o.stripe_payment_intent_id
        FROM disputes d
        LEFT JOIN users  ub ON d.buyer_id  = ub.id
        LEFT JOIN users  us ON d.seller_id = us.id
        LEFT JOIN orders o  ON d.order_id  = o.id
        WHERE d.id = ?
    ''', (dispute_id,)).fetchone()

    if not dispute:
        conn.close()
        return None

    evidence = conn.execute('''
        SELECT de.*, u.username AS submitter_username
        FROM dispute_evidence de
        LEFT JOIN users u ON de.submitted_by_user_id = u.id
        WHERE de.dispute_id = ?
        ORDER BY de.submitted_at ASC
    ''', (dispute_id,)).fetchall()

    timeline = conn.execute('''
        SELECT dt.*, u.username AS actor_username
        FROM dispute_timeline dt
        LEFT JOIN users u ON dt.actor_id = u.id
        WHERE dt.dispute_id = ?
        ORDER BY dt.created_at ASC
    ''', (dispute_id,)).fetchall()

    snapshots = conn.execute(
        'SELECT * FROM transaction_snapshots WHERE order_id = ? LIMIT 10',
        (dispute['order_id'],)
    ).fetchall()

    conn.close()

    return {
        'id': dispute['id'],
        'order_id': dispute['order_id'],
        'order_item_id': dispute['order_item_id'],
        'buyer_id': dispute['buyer_id'],
        'buyer_username': dispute['buyer_username'] or '',
        'buyer_email': dispute['buyer_email'] or '',
        'seller_id': dispute['seller_id'],
        'seller_username': dispute['seller_username'] or '',
        'seller_email': dispute['seller_email'] or '',
        'dispute_type': dispute['dispute_type'],
        'status': dispute['status'],
        'description': dispute['description'],
        'opened_at': dispute['opened_at'],
        'resolved_at': dispute['resolved_at'],
        'resolved_by_admin_id': dispute['resolved_by_admin_id'],
        'resolution_note': dispute['resolution_note'],
        'refund_amount': dispute['refund_amount'],
        'stripe_refund_id': dispute['stripe_refund_id'],
        'order_amount': dispute['order_amount'] or 0,
        'order_status': dispute['order_status'],
        'stripe_payment_intent_id': dispute['stripe_payment_intent_id'],
        'evidence': [dict(e) for e in evidence],
        'timeline': [dict(t) for t in timeline],
        'snapshots': [dict(s) for s in snapshots],
    }


def admin_change_status(dispute_id, admin_id, new_status, note=None):
    """
    Move a dispute to a non-terminal status (forward or backward in workflow).

    Validates the transition against ADMIN_STATUS_TRANSITIONS.
    Writes a 'status_changed' timeline entry.
    Sends evidence_requested notification to both parties if applicable.
    Raises ValueError on invalid input or transition.
    """
    all_allowed = {s for ts in ADMIN_STATUS_TRANSITIONS.values() for s in ts}
    if new_status not in all_allowed:
        raise ValueError(f'Invalid status: {new_status!r}')

    conn = _get_conn()
    cursor = conn.cursor()

    dispute = cursor.execute(
        'SELECT id, status, buyer_id, seller_id, order_id FROM disputes WHERE id = ?',
        (dispute_id,)
    ).fetchone()
    if not dispute:
        conn.close()
        raise ValueError('Dispute not found.')

    current = dispute['status']
    allowed = ADMIN_STATUS_TRANSITIONS.get(current, frozenset())
    if new_status not in allowed:
        conn.close()
        raise ValueError(f'Cannot transition from {current!r} to {new_status!r}.')

    cursor.execute('UPDATE disputes SET status = ? WHERE id = ?', (new_status, dispute_id))
    _add_timeline_entry(cursor, dispute_id, 'admin', admin_id, 'status_changed',
                        note or f'Status changed to {new_status}')
    conn.commit()

    buyer_id = dispute['buyer_id']
    seller_id = dispute['seller_id']
    order_id = dispute['order_id']
    conn.close()

    if new_status == 'evidence_requested':
        for uid in [buyer_id, seller_id]:
            if uid:
                try:
                    from services.notification_types import notify_dispute_evidence_requested
                    notify_dispute_evidence_requested(uid, dispute_id, order_id, note)
                except Exception as exc:
                    print(f'[DISPUTE] notify_dispute_evidence_requested failed: {exc}')


def admin_add_note(dispute_id, admin_id, note):
    """
    Add an internal admin-only note to the dispute timeline.

    Stored as event_type='admin_note', actor_type='admin'.
    NOT exposed to buyers or sellers via any user-facing API.
    Raises ValueError if dispute not found or note is empty.
    """
    if not note or not note.strip():
        raise ValueError('Note cannot be empty.')

    conn = _get_conn()
    cursor = conn.cursor()

    exists = cursor.execute('SELECT id FROM disputes WHERE id = ?', (dispute_id,)).fetchone()
    if not exists:
        conn.close()
        raise ValueError('Dispute not found.')

    _add_timeline_entry(cursor, dispute_id, 'admin', admin_id, 'admin_note', note.strip())
    conn.commit()
    conn.close()


def admin_resolve(dispute_id, admin_id, resolution, note):
    """
    Resolve a dispute as admin.

    resolution must be one of: 'resolved_refund' | 'resolved_denied' | 'closed'

    For 'resolved_refund':
      - Looks up orders.stripe_payment_intent_id
      - Calls stripe.Refund.create(payment_intent=pi_id) for a full refund
      - Writes a row to the refunds table
      - Updates disputes.stripe_refund_id + refund_amount
      - If no PI or Stripe fails, still resolves dispute and warns in result dict

    Phase 3 limitation: partial refunds are NOT implemented here.
    Partial refund support requires an explicit amount UI — deferred to Phase 4.

    Returns dict with refund details (may include 'warning' if Stripe unavailable).
    Raises ValueError on invalid state or missing required fields.
    """
    if resolution not in ADMIN_TERMINAL_OUTCOMES:
        raise ValueError(f'Invalid resolution: {resolution!r}. '
                         f'Must be one of: {sorted(ADMIN_TERMINAL_OUTCOMES)}')
    if not note or not note.strip():
        raise ValueError('A resolution note is required.')

    conn = _get_conn()
    cursor = conn.cursor()

    dispute = cursor.execute('''
        SELECT d.id, d.status, d.buyer_id, d.seller_id, d.order_id,
               o.stripe_payment_intent_id, o.total_price AS order_amount
        FROM disputes d
        LEFT JOIN orders o ON d.order_id = o.id
        WHERE d.id = ?
    ''', (dispute_id,)).fetchone()

    if not dispute:
        conn.close()
        raise ValueError('Dispute not found.')

    if dispute['status'] not in ACTIVE_DISPUTE_STATUSES:
        conn.close()
        raise ValueError(f'Dispute is already in a terminal state: {dispute["status"]}.')

    now = datetime.now().isoformat()
    refund_result = {}
    stripe_refund_id = None
    refund_amount = None

    if resolution == 'resolved_refund':
        pi_id = dispute['stripe_payment_intent_id']
        order_amount = dispute['order_amount'] or 0

        if pi_id and order_amount > 0:
            refund_result = _attempt_stripe_refund(pi_id, dispute_id)
            if refund_result.get('success'):
                stripe_refund_id = refund_result['refund_id']
                refund_amount = order_amount
                cursor.execute(
                    '''INSERT INTO refunds
                           (dispute_id, order_id, order_item_id, buyer_id, seller_id,
                            amount, provider_refund_id, issued_by_admin_id, issued_at, note)
                       VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)''',
                    (dispute_id, dispute['order_id'],
                     dispute['buyer_id'], dispute['seller_id'],
                     order_amount, stripe_refund_id, admin_id, now, note.strip()),
                )
            else:
                refund_result['warning'] = (
                    'Dispute marked resolved_refund but Stripe refund failed. '
                    'Manual action required with payment processor.'
                )
        else:
            refund_result = {
                'success': False,
                'warning': 'No Stripe PaymentIntent on file for this order. '
                           'Resolve refund manually with payment processor.',
            }

    event_note = note.strip()
    if refund_amount:
        event_note += f' (Refund: ${refund_amount:.2f})'

    cursor.execute('''
        UPDATE disputes
        SET status = ?, resolved_at = ?, resolved_by_admin_id = ?,
            resolution_note = ?, stripe_refund_id = ?, refund_amount = ?
        WHERE id = ?
    ''', (resolution, now, admin_id, note.strip(),
          stripe_refund_id, refund_amount, dispute_id))

    _add_timeline_entry(cursor, dispute_id, 'admin', admin_id, 'status_changed',
                        f'Resolved as {resolution}: {event_note}')

    buyer_id = dispute['buyer_id']
    seller_id = dispute['seller_id']
    order_id = dispute['order_id']

    conn.commit()
    conn.close()

    # Notify both parties (best-effort)
    for uid in [buyer_id, seller_id]:
        if uid:
            try:
                from services.notification_types import notify_dispute_resolved
                notify_dispute_resolved(uid, dispute_id, order_id, resolution, note)
            except Exception as exc:
                print(f'[DISPUTE] notify_dispute_resolved failed: {exc}')

    # Recompute risk profiles for both parties (Phase 4 — best-effort)
    try:
        from services import risk_service
        risk_service.recompute_risk_profile(buyer_id)
        if seller_id:
            risk_service.recompute_risk_profile(seller_id)
    except Exception as exc:
        print(f'[DISPUTE] risk recompute after resolve failed: {exc}')

    return refund_result


def _attempt_stripe_refund(payment_intent_id, dispute_id):
    """
    Attempt a full Stripe refund against a PaymentIntent.

    Returns {'success': True, 'refund_id': 're_xxx', 'amount': float}
         or {'success': False, 'error': str}

    Uses idempotency_key so re-running after a partial failure is safe.
    Full refunds only — partial refunds deferred to Phase 4.
    """
    try:
        import stripe
        refund = stripe.Refund.create(
            payment_intent=payment_intent_id,
            reason='fraudulent',
            metadata={'dispute_id': str(dispute_id)},
            idempotency_key=f'dispute-refund-{dispute_id}',
        )
        return {
            'success': True,
            'refund_id': refund.id,
            'amount': refund.amount / 100,
        }
    except Exception as exc:
        import stripe
        if isinstance(exc, stripe.error.InvalidRequestError):
            # e.g., "This charge has already been fully refunded"
            return {'success': False, 'error': str(exc)}
        return {'success': False, 'error': str(exc)}
