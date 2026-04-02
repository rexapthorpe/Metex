"""
Risk Profile Service (Phase 4)
================================
Business logic for user fraud/risk monitoring.

Risk Score Formula (0–100, data-driven):
    total_disputes_as_buyer         × 4
    disputes_upheld_buyer           × 10   (buyer won = valid claims)
    disputes_denied_buyer           × 1    (weak signal)
    total_disputes_as_seller        × 3
    disputes_upheld_against_seller  × 12   (strongest seller signal)
    refunds_issued_count            × 8
    refunds_issued_amount           × 0.02 (capped at 20 pts)
    capped at 100

Manual flags are stored separately and displayed alongside the score.
Scores are advisory signals — NOT automatic enforcement verdicts.

Auto-flag rules (within 180-day window → 'watch'):
    Rule 1: buyer opened >= 3 disputes
    Rule 2: seller had >= 2 upheld disputes against them
    Rule 3: buyer received >= $500 in refunds

Auto-flags only escalate to 'watch'. Admins manually escalate to
'restricted' or 'suspended'.
"""

from datetime import datetime, timedelta

import database as _db_module

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RISK_FLAGS = ('none', 'watch', 'restricted', 'suspended')

AUTO_FLAG_WINDOW_DAYS = 180
AUTO_FLAG_BUYER_DISPUTE_COUNT = 3
AUTO_FLAG_SELLER_UPHELD_COUNT = 2
AUTO_FLAG_REFUND_AMOUNT_THRESHOLD = 500.0


def _get_conn():
    return _db_module.get_db_connection()


# ---------------------------------------------------------------------------
# Score formula
# ---------------------------------------------------------------------------

def _score_from_stats(stats):
    """
    Deterministic risk score formula.
    Returns integer 0–100.
    """
    base = (
        (stats.get('total_disputes_as_buyer') or 0) * 4
        + (stats.get('disputes_upheld_buyer') or 0) * 10
        + (stats.get('disputes_denied_buyer') or 0) * 1
        + (stats.get('total_disputes_as_seller') or 0) * 3
        + (stats.get('disputes_upheld_against_seller') or 0) * 12
        + (stats.get('refunds_issued_count') or 0) * 8
        + min((stats.get('refunds_issued_amount') or 0.0) * 0.02, 20)
    )
    return min(100, round(base))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_risk_profile(conn, user_id):
    """
    Insert a default risk profile row if none exists.
    Uses a SELECT then INSERT to stay compatible with both SQLite and PostgreSQL.
    """
    existing = conn.execute(
        'SELECT 1 FROM user_risk_profile WHERE user_id = ?', (user_id,)
    ).fetchone()
    if not existing:
        conn.execute(
            'INSERT INTO user_risk_profile (user_id) VALUES (?)', (user_id,)
        )


def _log_risk_event(cursor, user_id, event_type, triggered_by,
                    old_score, new_score, old_flag, new_flag, note=None):
    cursor.execute(
        '''INSERT INTO user_risk_events
             (user_id, event_type, triggered_by, old_score, new_score,
              old_flag, new_flag, note, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (user_id, event_type, triggered_by, old_score, new_score,
         old_flag, new_flag, note, datetime.now().isoformat()),
    )


def _check_auto_flags(cursor, user_id, current_flag, current_score, now):
    """
    Evaluate rule-based auto-flag logic within a transaction.
    Only auto-escalates to 'watch'; never auto-restricts or auto-suspends.
    Writes a user_risk_events row if a new auto-flag is applied.
    """
    # Skip if already flagged at or above 'watch' level
    if current_flag not in ('none', None, ''):
        return

    window_start = (now - timedelta(days=AUTO_FLAG_WINDOW_DAYS)).isoformat()
    reasons = []

    # Rule 1: buyer opened >= 3 disputes in window
    buyer_row = cursor.execute(
        '''SELECT COUNT(*) AS cnt FROM disputes
           WHERE buyer_id = ? AND opened_at >= ?''',
        (user_id, window_start),
    ).fetchone()
    if (buyer_row['cnt'] or 0) >= AUTO_FLAG_BUYER_DISPUTE_COUNT:
        reasons.append(
            f"buyer opened {buyer_row['cnt']} disputes in {AUTO_FLAG_WINDOW_DAYS}d"
        )

    # Rule 2: seller had >= 2 upheld disputes in window
    seller_row = cursor.execute(
        '''SELECT COUNT(*) AS cnt FROM disputes
           WHERE seller_id = ? AND status = 'resolved_refund' AND resolved_at >= ?''',
        (user_id, window_start),
    ).fetchone()
    if (seller_row['cnt'] or 0) >= AUTO_FLAG_SELLER_UPHELD_COUNT:
        reasons.append(
            f"seller had {seller_row['cnt']} upheld disputes in {AUTO_FLAG_WINDOW_DAYS}d"
        )

    # Rule 3: refund total >= threshold in window
    refund_row = cursor.execute(
        '''SELECT COALESCE(SUM(amount), 0) AS total FROM refunds
           WHERE buyer_id = ? AND issued_at >= ?''',
        (user_id, window_start),
    ).fetchone()
    if (refund_row['total'] or 0) >= AUTO_FLAG_REFUND_AMOUNT_THRESHOLD:
        reasons.append(
            f"refunds ${refund_row['total']:.2f} in {AUTO_FLAG_WINDOW_DAYS}d"
        )

    if not reasons:
        return

    reason_str = '; '.join(reasons)

    cursor.execute(
        '''UPDATE user_risk_profile
             SET manual_risk_flag = 'watch',
                 manual_flag_reason = ?,
                 manual_flagged_at = ?
           WHERE user_id = ? AND (manual_risk_flag IS NULL OR manual_risk_flag = 'none')''',
        (f'Auto-flagged: {reason_str}', now.isoformat(), user_id),
    )

    if cursor.rowcount and cursor.rowcount > 0:
        _log_risk_event(
            cursor, user_id, 'auto_flagged', 'system',
            old_score=current_score, new_score=current_score,
            old_flag='none', new_flag='watch',
            note=f'Auto-flagged watch: {reason_str}',
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def recompute_risk_profile(user_id):
    """
    Recompute behavioral stats and risk score for user_id.
    Writes updated counters, score, and any auto-flag to user_risk_profile.
    Records score changes and auto-flags in user_risk_events.

    Best-effort: exceptions are caught and printed (never raise to caller).
    Safe to call multiple times.
    """
    try:
        _recompute_inner(user_id)
    except Exception as exc:
        print(f'[RISK] recompute_risk_profile({user_id}) failed: {exc}')


def _recompute_inner(user_id):
    conn = _get_conn()
    cursor = conn.cursor()

    _ensure_risk_profile(conn, user_id)

    # --- Fetch live stats ---

    buyer_row = cursor.execute(
        '''SELECT
             COUNT(*) AS total,
             SUM(CASE WHEN status = 'resolved_refund' THEN 1 ELSE 0 END) AS upheld,
             SUM(CASE WHEN status = 'resolved_denied'  THEN 1 ELSE 0 END) AS denied
           FROM disputes WHERE buyer_id = ?''',
        (user_id,),
    ).fetchone()
    total_disputes_as_buyer = buyer_row['total'] or 0
    disputes_upheld_buyer   = buyer_row['upheld'] or 0
    disputes_denied_buyer   = buyer_row['denied'] or 0

    seller_row = cursor.execute(
        '''SELECT
             COUNT(*) AS total,
             SUM(CASE WHEN status = 'resolved_refund' THEN 1 ELSE 0 END) AS upheld
           FROM disputes WHERE seller_id = ?''',
        (user_id,),
    ).fetchone()
    total_disputes_as_seller       = seller_row['total'] or 0
    disputes_upheld_against_seller = seller_row['upheld'] or 0

    orders_bought_row = cursor.execute(
        'SELECT COUNT(*) AS cnt FROM orders WHERE buyer_id = ?', (user_id,)
    ).fetchone()
    total_orders_bought = orders_bought_row['cnt'] or 0

    orders_sold_row = cursor.execute(
        '''SELECT COUNT(DISTINCT oi.order_id) AS cnt
           FROM order_items oi
           JOIN listings l ON oi.listing_id = l.id
           WHERE l.seller_id = ?''',
        (user_id,),
    ).fetchone()
    total_orders_sold = orders_sold_row['cnt'] or 0

    refunds_row = cursor.execute(
        '''SELECT COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS total
           FROM refunds WHERE buyer_id = ?''',
        (user_id,),
    ).fetchone()
    refunds_issued_count  = refunds_row['cnt'] or 0
    refunds_issued_amount = refunds_row['total'] or 0.0

    stats = {
        'total_disputes_as_buyer':        total_disputes_as_buyer,
        'disputes_upheld_buyer':           disputes_upheld_buyer,
        'disputes_denied_buyer':           disputes_denied_buyer,
        'total_disputes_as_seller':        total_disputes_as_seller,
        'disputes_upheld_against_seller':  disputes_upheld_against_seller,
        'total_orders_bought':             total_orders_bought,
        'total_orders_sold':               total_orders_sold,
        'refunds_issued_count':            refunds_issued_count,
        'refunds_issued_amount':           refunds_issued_amount,
    }
    new_score = _score_from_stats(stats)

    # Get current profile values for comparison
    profile = cursor.execute(
        'SELECT risk_score, manual_risk_flag FROM user_risk_profile WHERE user_id = ?',
        (user_id,),
    ).fetchone()
    old_score = (profile['risk_score']      if profile else None) or 0
    old_flag  = (profile['manual_risk_flag'] if profile else None) or 'none'

    cursor.execute(
        '''UPDATE user_risk_profile
             SET total_disputes_as_buyer        = ?,
                 disputes_upheld_buyer           = ?,
                 disputes_denied_buyer           = ?,
                 total_disputes_as_seller        = ?,
                 disputes_upheld_against_seller  = ?,
                 total_orders_bought             = ?,
                 total_orders_sold               = ?,
                 refunds_issued_count            = ?,
                 refunds_issued_amount           = ?,
                 risk_score                      = ?
           WHERE user_id = ?''',
        (total_disputes_as_buyer, disputes_upheld_buyer, disputes_denied_buyer,
         total_disputes_as_seller, disputes_upheld_against_seller,
         total_orders_bought, total_orders_sold,
         refunds_issued_count, refunds_issued_amount,
         new_score, user_id),
    )

    if new_score != old_score:
        _log_risk_event(cursor, user_id, 'score_updated', 'system',
                        old_score=old_score, new_score=new_score,
                        old_flag=old_flag, new_flag=old_flag,
                        note=f'Score recomputed: {old_score} → {new_score}')

    now = datetime.now()
    _check_auto_flags(cursor, user_id, old_flag, new_score, now)

    conn.commit()
    conn.close()


def set_manual_flag(user_id, admin_id, flag, reason, note=None):
    """
    Set a manual risk flag on a user profile.
    Writes a user_risk_events row.
    Raises ValueError for unrecognised flag values.
    """
    if flag not in RISK_FLAGS:
        raise ValueError(f'Invalid flag: {flag!r}. Must be one of: {RISK_FLAGS}')

    conn = _get_conn()
    cursor = conn.cursor()

    _ensure_risk_profile(conn, user_id)

    profile = cursor.execute(
        'SELECT risk_score, manual_risk_flag FROM user_risk_profile WHERE user_id = ?',
        (user_id,),
    ).fetchone()
    old_flag      = (profile['manual_risk_flag'] if profile else None) or 'none'
    current_score = (profile['risk_score']        if profile else None) or 0

    now = datetime.now().isoformat()
    cursor.execute(
        '''UPDATE user_risk_profile
             SET manual_risk_flag            = ?,
                 manual_flag_reason          = ?,
                 manual_flagged_at           = ?,
                 manual_flagged_by_admin_id  = ?
           WHERE user_id = ?''',
        (flag, reason or '', now, admin_id, user_id),
    )
    _log_risk_event(cursor, user_id, 'manual_flagged', f'admin:{admin_id}',
                    old_score=current_score, new_score=current_score,
                    old_flag=old_flag, new_flag=flag,
                    note=note or reason or f'Flag set to {flag}')
    conn.commit()
    conn.close()


def clear_manual_flag(user_id, admin_id, note=None):
    """
    Clear the manual risk flag, resetting it to 'none'.
    Writes a user_risk_events row.
    """
    conn = _get_conn()
    cursor = conn.cursor()

    _ensure_risk_profile(conn, user_id)

    profile = cursor.execute(
        'SELECT risk_score, manual_risk_flag FROM user_risk_profile WHERE user_id = ?',
        (user_id,),
    ).fetchone()
    old_flag      = (profile['manual_risk_flag'] if profile else None) or 'none'
    current_score = (profile['risk_score']        if profile else None) or 0

    now = datetime.now().isoformat()
    cursor.execute(
        '''UPDATE user_risk_profile
             SET manual_risk_flag           = 'none',
                 manual_flag_reason         = NULL,
                 manual_flagged_at          = NULL,
                 manual_flagged_by_admin_id = NULL
           WHERE user_id = ?''',
        (user_id,),
    )
    _log_risk_event(cursor, user_id, 'flag_cleared', f'admin:{admin_id}',
                    old_score=current_score, new_score=current_score,
                    old_flag=old_flag, new_flag='none',
                    note=note or 'Flag cleared by admin')
    conn.commit()
    conn.close()


def update_admin_note(user_id, admin_id, note):
    """
    Update the admin-only notes field on a risk profile.
    Does NOT write a risk event (notes are free-text scratchpad).
    """
    conn = _get_conn()
    _ensure_risk_profile(conn, user_id)
    conn.execute(
        'UPDATE user_risk_profile SET notes = ? WHERE user_id = ?',
        (note, user_id),
    )
    conn.commit()
    conn.close()


def update_last_login(user_id, ip_address):
    """
    Update last_login_ip and last_login_at on the risk profile.
    Called from the login route. Creates profile row if needed.
    Best-effort: exceptions are printed, not raised.
    """
    try:
        conn = _get_conn()
        _ensure_risk_profile(conn, user_id)
        conn.execute(
            '''UPDATE user_risk_profile
                 SET last_login_ip = ?, last_login_at = ?
               WHERE user_id = ?''',
            (ip_address, datetime.now().isoformat(), user_id),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        print(f'[RISK] update_last_login({user_id}) failed: {exc}')


def get_risk_list(flag_filter=None, score_min=None, username=None):
    """
    Return risk profiles for admin list view.
    Sorted by risk_score DESC.
    Returns list of dicts.
    """
    conn = _get_conn()
    query = '''
        SELECT urp.user_id, urp.risk_score, urp.manual_risk_flag,
               urp.manual_flag_reason, urp.manual_flagged_at,
               urp.total_disputes_as_buyer, urp.disputes_upheld_buyer,
               urp.total_disputes_as_seller, urp.disputes_upheld_against_seller,
               urp.refunds_issued_count, urp.refunds_issued_amount,
               urp.total_orders_bought, urp.total_orders_sold,
               urp.last_login_ip, urp.last_login_at,
               u.username, u.created_at AS account_created_at,
               u.is_banned, u.is_frozen
        FROM user_risk_profile urp
        JOIN users u ON urp.user_id = u.id
        WHERE 1=1
    '''
    params = []

    if flag_filter and flag_filter != 'all':
        query += ' AND urp.manual_risk_flag = ?'
        params.append(flag_filter)

    if score_min is not None:
        query += ' AND urp.risk_score >= ?'
        params.append(int(score_min))

    if username:
        query += ' AND u.username LIKE ?'
        params.append(f'%{username}%')

    query += ' ORDER BY urp.risk_score DESC, urp.manual_flagged_at DESC LIMIT 200'

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_risk_detail(user_id):
    """
    Return full risk profile + event history for admin detail view.
    Returns dict with 'profile' and 'events' keys, or None if user not found.
    """
    conn = _get_conn()

    _ensure_risk_profile(conn, user_id)
    conn.commit()

    profile = conn.execute(
        '''SELECT urp.*, u.username, u.email, u.created_at AS account_created_at,
                  u.is_banned, u.is_frozen
           FROM user_risk_profile urp
           JOIN users u ON urp.user_id = u.id
           WHERE urp.user_id = ?''',
        (user_id,),
    ).fetchone()

    if not profile:
        conn.close()
        return None

    events = conn.execute(
        '''SELECT * FROM user_risk_events
           WHERE user_id = ?
           ORDER BY created_at DESC
           LIMIT 50''',
        (user_id,),
    ).fetchall()

    conn.close()
    return {
        'profile': dict(profile),
        'events': [dict(e) for e in events],
    }
