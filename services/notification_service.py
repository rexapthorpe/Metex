"""
Notification Service
Handles creating and managing user notifications.

Central API
-----------
  notify(user_id, notification_type, title, body, ...)
      The single entry-point for all notification emission.
      Checks notification_settings before inserting a row.

  is_notification_enabled(user_id, notification_type)
      Returns True if the user has the type enabled (or if no override row
      exists and the type's default is ON).

  get_user_notification_settings(user_id)
      Returns dict { type: bool } merged with NOTIFICATION_DEFAULTS.

  update_notification_settings(user_id, settings)
      Upserts rows in notification_settings for the given {type: bool} dict.

Legacy helpers (kept for backward compat)
------------------------------------------
  create_notification(...)   – used by many callers; now calls notify() internally
  get_user_notifications(...) / mark_notification_read(...) / etc.
"""

import database as _db_module
from datetime import datetime
import json


def _get_conn():
    """Late-binding DB connection — patchable via monkeypatch on database module."""
    return _db_module.get_db_connection()


# ---------------------------------------------------------------------------
# Notification type defaults
# True  = ON  by default (user must explicitly disable)
# False = OFF by default (user must explicitly enable)
# ---------------------------------------------------------------------------
NOTIFICATION_DEFAULTS = {  # type: dict[str, bool]
    # ── Listings ──────────────────────────────────────────────────────────
    'listing_created_success':              True,
    'listing_edited':                       False,   # noisy – OFF
    'listing_delisted':                     True,
    'listing_expired':                      True,
    # ── Bids ──────────────────────────────────────────────────────────────
    'bid_placed_success':                   True,
    'bid_updated':                          True,
    'bid_received':                         True,
    'bid_withdrawn':                        True,
    'outbid':                               True,
    'bid_now_leading':                      False,   # noisy – OFF
    'bid_accepted':                         True,
    'bid_rejected_or_expired':              True,
    'bid_partially_accepted':               True,
    'bid_fully_filled':                     True,
    # ── Orders (buyer) ────────────────────────────────────────────────────
    'order_created':                        True,
    'payment_succeeded':                    False,   # stub – OFF
    'payment_failed':                       False,   # stub – OFF
    'order_status_updated':                 True,
    'order_shipped':                        True,
    'tracking_updated':                     False,   # noisy – OFF
    'delivered_confirmed':                  True,
    'refund_issued':                        False,   # stub – OFF
    'cancellation_requested':               True,
    'cancellation_denied':                  True,
    'cancellation_approved':                True,
    # ── Sales (seller) ────────────────────────────────────────────────────
    'seller_order_received':                True,
    'seller_fulfillment_needed':            False,   # noisy – OFF
    'seller_cancellation_request_received': True,
    'seller_cancellation_finalized':        True,
    'payout_available':                     False,   # stub – OFF
    # ── Messages ──────────────────────────────────────────────────────────
    'new_direct_message':                   True,
    'new_order_message':                    True,
    # ── Ratings ───────────────────────────────────────────────────────────
    'rating_received':                      True,
    'rating_to_leave_reminder':             False,   # noisy – OFF
    # ── Account / Security ────────────────────────────────────────────────
    'new_login':                            True,
    'password_changed':                     True,
    'email_changed':                        True,
    # ── Watchlist (stubs) ─────────────────────────────────────────────────
    'price_alert_triggered':                False,   # future – OFF
    'availability_alert_triggered':         False,   # future – OFF
    'saved_search_match':                   False,   # future – OFF
    # ── Legacy type aliases (kept for backward compat) ────────────────────
    'bid_filled':                           True,
    'listing_sold':                         True,
    'order_confirmed':                      True,
    'new_message':                          True,
    'bid_placed':                           True,
    'bid_on_bucket':                        True,
    'cancel_request_submitted':             True,
    'cancellation_request':                 True,
    'report_submitted':                     True,
    'rating_submitted':                     True,
}


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def is_notification_enabled(user_id, notification_type):
    """
    Return True when the user has this notification type turned on.
    Falls back to NOTIFICATION_DEFAULTS when no override row exists.
    Unknown types default to True (fail open).
    """
    conn = _get_conn()
    row = conn.execute(
        'SELECT enabled FROM notification_settings WHERE user_id = ? AND notification_type = ?',
        (user_id, notification_type)
    ).fetchone()
    conn.close()

    if row is not None:
        return bool(row['enabled'])
    return NOTIFICATION_DEFAULTS.get(notification_type, True)


def get_user_notification_settings(user_id):
    """
    Return a dict of ALL known notification types → bool for this user,
    merging NOTIFICATION_DEFAULTS with any user overrides.
    """
    conn = _get_conn()
    rows = conn.execute(
        'SELECT notification_type, enabled FROM notification_settings WHERE user_id = ?',
        (user_id,)
    ).fetchall()
    conn.close()

    # Start from defaults
    result = dict(NOTIFICATION_DEFAULTS)
    # Apply user overrides
    for row in rows:
        result[row['notification_type']] = bool(row['enabled'])
    return result


def update_notification_settings(user_id, settings):
    """
    Upsert notification_settings rows for the given {type: bool} mapping.
    Only updates types listed in NOTIFICATION_DEFAULTS.
    """
    conn = _get_conn()
    now = datetime.now()
    for ntype, enabled in settings.items():
        if ntype not in NOTIFICATION_DEFAULTS:
            continue  # ignore unknown types
        conn.execute(
            '''
            INSERT INTO notification_settings (user_id, notification_type, enabled, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, notification_type) DO UPDATE
               SET enabled = excluded.enabled, updated_at = excluded.updated_at
            ''',
            (user_id, ntype, 1 if enabled else 0, now)
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Central emit function
# ---------------------------------------------------------------------------

def notify(
    user_id,
    notification_type,
    title,
    body,
    url=None,
    related_order_id=None,
    related_bid_id=None,
    related_listing_id=None,
    metadata=None,
):
    """
    Central notification emitter.

    Checks the user's notification_settings (with NOTIFICATION_DEFAULTS
    fallback) before inserting. Returns the new notification id, or None
    if suppressed or on error.
    """
    if not is_notification_enabled(user_id, notification_type):
        print(f'[NOTIFICATION] Suppressed {notification_type!r} for user {user_id}')
        return None

    return _insert_notification(
        user_id=user_id,
        notification_type=notification_type,
        title=title,
        message=body,
        related_order_id=related_order_id,
        related_bid_id=related_bid_id,
        related_listing_id=related_listing_id,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Internal insert helper (bypasses settings check – used by create_notification)
# ---------------------------------------------------------------------------

def _insert_notification(
    user_id, notification_type, title, message,
    related_order_id=None, related_bid_id=None,
    related_listing_id=None, metadata=None,
):
    conn = _get_conn()
    cursor = conn.cursor()
    try:
        metadata_json = json.dumps(metadata) if metadata else None
        cursor.execute(
            '''
            INSERT INTO notifications
                (user_id, type, title, message, related_order_id,
                 related_bid_id, related_listing_id, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                user_id, notification_type, title, message,
                related_order_id, related_bid_id, related_listing_id,
                metadata_json,
            ),
        )
        notification_id = cursor.lastrowid
        conn.commit()
        print(
            f'[NOTIFICATION] Created #{notification_id} '
            f'type={notification_type!r} user={user_id} title={title!r}'
        )
        return notification_id
    except Exception as exc:
        print(f'[NOTIFICATION ERROR] Failed to create notification: {exc}')
        return None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Legacy public create_notification() – preserved for backward compat.
# Now routes through notify() so settings are honoured automatically.
# ---------------------------------------------------------------------------

def create_notification(
    user_id,
    notification_type,
    title,
    message,
    related_order_id=None,
    related_bid_id=None,
    related_listing_id=None,
    metadata=None,
):
    """
    Create a new notification for a user.

    Checks the user's notification_settings before inserting.
    Returns the new notification id, or None if suppressed / on error.
    """
    return notify(
        user_id=user_id,
        notification_type=notification_type,
        title=title,
        body=message,
        related_order_id=related_order_id,
        related_bid_id=related_bid_id,
        related_listing_id=related_listing_id,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Re-export wrappers (kept for modules that import from notification_service)
# ---------------------------------------------------------------------------

def notify_cancel_request_submitted(requester_id, order_id, item_description):
    """Re-export wrapper to avoid circular import with notification_types"""
    from services.notification_types import notify_cancel_request_submitted as _impl
    return _impl(requester_id, order_id, item_description)


def notify_report_submitted(reporter_id, reported_username, report_id):
    """Re-export wrapper to avoid circular import with notification_types"""
    from services.notification_types import notify_report_submitted as _impl
    return _impl(reporter_id, reported_username, report_id)


# ---------------------------------------------------------------------------
# Query / management helpers
# ---------------------------------------------------------------------------

def get_user_notifications(user_id, unread_only=False, limit=50, offset=0):
    """Get notifications for a user (newest first)."""
    conn = _get_conn()
    query = 'SELECT * FROM notifications WHERE user_id = ?'
    params = [user_id]
    if unread_only:
        query += ' AND is_read = 0'
    query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
    params.append(limit)
    params.append(offset)
    notifications = conn.execute(query, params).fetchall()
    conn.close()

    result = []
    for notif in notifications:
        nd = dict(notif)
        if nd.get('metadata'):
            try:
                nd['metadata'] = json.loads(nd['metadata'])
            except Exception:
                nd['metadata'] = None
        result.append(nd)
    return result


def mark_notification_read(notification_id, user_id=None):
    """Mark a notification as read.

    If user_id is supplied the update is scoped to that owner (ownership check).
    Returns True if a row was updated, False if not found / not owned.
    """
    conn = _get_conn()
    if user_id is not None:
        result = conn.execute(
            'UPDATE notifications SET is_read = 1, read_at = ? WHERE id = ? AND user_id = ?',
            (datetime.now(), notification_id, user_id),
        )
    else:
        result = conn.execute(
            'UPDATE notifications SET is_read = 1, read_at = ? WHERE id = ?',
            (datetime.now(), notification_id),
        )
    updated = result.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def mark_all_notifications_read(user_id):
    """Mark all unread notifications for a user as read."""
    conn = _get_conn()
    conn.execute(
        'UPDATE notifications SET is_read = 1, read_at = ? WHERE user_id = ? AND is_read = 0',
        (datetime.now(), user_id),
    )
    conn.commit()
    conn.close()
    return True


def delete_notification(notification_id, user_id):
    """Delete a notification (ownership-checked)."""
    conn = _get_conn()
    result = conn.execute(
        'DELETE FROM notifications WHERE id = ? AND user_id = ?',
        (notification_id, user_id),
    )
    deleted = result.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def get_unread_count(user_id):
    """Return the count of unread notifications for a user."""
    conn = _get_conn()
    row = conn.execute(
        'SELECT COUNT(*) AS count FROM notifications WHERE user_id = ? AND is_read = 0',
        (user_id,),
    ).fetchone()
    conn.close()
    return row['count'] if row else 0


# ---------------------------------------------------------------------------
# Legacy high-level helpers that lived here before the notification_types split
# (retained as thin wrappers to avoid import breakage)
# ---------------------------------------------------------------------------

def notify_bid_filled(buyer_id, order_id, bid_id, item_description, quantity_filled,
                      price_per_unit, total_amount, is_partial=False, remaining_quantity=0):
    from services.notification_types import notify_bid_filled as _impl
    return _impl(buyer_id, order_id, bid_id, item_description, quantity_filled,
                 price_per_unit, total_amount, is_partial, remaining_quantity)


def notify_order_confirmed(buyer_id, order_id, item_description,
                           quantity_purchased, price_per_unit, total_amount):
    from services.notification_types import notify_order_confirmed as _impl
    return _impl(buyer_id, order_id, item_description,
                 quantity_purchased, price_per_unit, total_amount)


def notify_listing_sold(seller_id, order_id, listing_id, item_description,
                        quantity_sold, price_per_unit, total_amount, shipping_address,
                        is_partial=False, remaining_quantity=0):
    from services.notification_types import notify_listing_sold as _impl
    return _impl(seller_id, order_id, listing_id, item_description,
                 quantity_sold, price_per_unit, total_amount, shipping_address,
                 is_partial, remaining_quantity)
