"""
Tracking Forfeiture Service

Handles automatic forfeiture of orders where the seller has not uploaded
tracking information within the configured time window.

Forfeiture logic:
  - Orders with status 'Pending' and no seller_order_tracking row (or empty
    tracking_number) that have exceeded (created_at + forfeit_window) are
    updated to status 'Forfeited'.
  - Window is stored in system_settings as total seconds.
"""

from datetime import datetime


def _parse_dt(s):
    """Parse a DB datetime string into a naive UTC datetime."""
    if not s:
        return None
    if isinstance(s, datetime):
        return s
    s = str(s)
    try:
        if 'T' in s:
            return datetime.fromisoformat(s)
        return datetime.strptime(s, '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return None


def check_and_forfeit_expired_orders(conn, seller_id=None):
    """
    Find Pending orders with no tracking uploaded that have passed their
    forfeiture deadline, and set their status to 'Forfeited'.

    Args:
        conn:      An open DB connection.
        seller_id: If provided, only check this seller's orders.

    Returns:
        list of int — order IDs that were just forfeited.
    """
    from services.system_settings_service import get_tracking_forfeit_window
    window_seconds = get_tracking_forfeit_window()
    now = datetime.utcnow()

    if seller_id:
        rows = conn.execute(
            """
            SELECT DISTINCT o.id AS order_id, o.created_at
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.id
            JOIN listings l ON l.id = oi.listing_id
            WHERE o.status = 'Pending'
              AND l.seller_id = ?
              AND NOT EXISTS (
                  SELECT 1 FROM seller_order_tracking sot
                  WHERE sot.order_id = o.id
                    AND sot.seller_id = l.seller_id
                    AND sot.tracking_number IS NOT NULL
                    AND sot.tracking_number != ''
              )
            """,
            (seller_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT DISTINCT o.id AS order_id, o.created_at
            FROM orders o
            WHERE o.status = 'Pending'
              AND NOT EXISTS (
                  SELECT 1 FROM seller_order_tracking sot
                  WHERE sot.order_id = o.id
                    AND sot.tracking_number IS NOT NULL
                    AND sot.tracking_number != ''
              )
            """,
        ).fetchall()

    forfeited_ids = []
    for row in rows:
        created_at = _parse_dt(row['created_at'])
        if created_at is None:
            continue
        elapsed = (now - created_at).total_seconds()
        if elapsed > window_seconds:
            conn.execute(
                "UPDATE orders SET status = 'Forfeited' WHERE id = ?",
                (row['order_id'],),
            )
            forfeited_ids.append(row['order_id'])

    if forfeited_ids:
        conn.commit()
        for order_id in forfeited_ids:
            _apply_forfeiture_consequences(conn, order_id)

    return forfeited_ids


def _apply_forfeiture_consequences(conn, order_id):
    """Issue ledger refund, restore bid if applicable, and notify buyer + seller(s)."""
    # Fetch order
    order = conn.execute(
        "SELECT id, buyer_id, source_bid_id FROM orders WHERE id = ?",
        (order_id,),
    ).fetchone()
    if not order:
        return

    # Fetch item description and seller IDs
    items = conn.execute(
        """
        SELECT COALESCE(l.listing_title, l.metal, 'item') AS item_title,
               l.seller_id
        FROM order_items oi
        JOIN listings l ON l.id = oi.listing_id
        WHERE oi.order_id = ?
        """,
        (order_id,),
    ).fetchall()

    item_desc = items[0]['item_title'] if items else f'Order #{order_id}'
    seller_ids = list({r['seller_id'] for r in items if r['seller_id']})

    # Restore bid to active if this order came from a bid match
    source_bid_id = order['source_bid_id'] if order['source_bid_id'] else None
    if source_bid_id:
        try:
            _restore_bid(conn, order_id, source_bid_id)
        except Exception as e:
            print(f"[TRACKING FORFEIT] Bid restore failed for order {order_id}: {e}")

    # Ledger refund
    try:
        from core.services.ledger import LedgerService
        LedgerService.process_refund(
            order_id=order_id,
            admin_id=None,
            refund_type='full',
            reason='Seller did not upload tracking information within the required window.',
        )
    except Exception as e:
        print(f"[TRACKING FORFEIT] Ledger refund failed for order {order_id}: {e}")

    # Notify buyer
    try:
        from services.notification_types import notify_order_forfeited_buyer
        notify_order_forfeited_buyer(order['buyer_id'], order_id, item_desc)
    except Exception as e:
        print(f"[TRACKING FORFEIT] Buyer notification failed for order {order_id}: {e}")

    # Notify seller(s)
    try:
        from services.notification_types import notify_order_forfeited_seller
        for sid in seller_ids:
            notify_order_forfeited_seller(sid, order_id, item_desc)
    except Exception as e:
        print(f"[TRACKING FORFEIT] Seller notification failed for order {order_id}: {e}")


def _restore_bid(conn, order_id, bid_id):
    """
    Return the quantity from a forfeited order back to the originating bid
    and re-activate it so it can match again.
    """
    qty_row = conn.execute(
        "SELECT COALESCE(SUM(quantity), 0) AS total_qty FROM order_items WHERE order_id = ?",
        (order_id,),
    ).fetchone()
    restore_qty = qty_row['total_qty'] if qty_row else 0
    if restore_qty <= 0:
        return

    bid = conn.execute(
        "SELECT id, quantity_requested, remaining_quantity FROM bids WHERE id = ?",
        (bid_id,),
    ).fetchone()
    if not bid:
        return

    new_remaining = bid['remaining_quantity'] + restore_qty
    # Cap at original requested quantity
    if new_remaining >= bid['quantity_requested']:
        new_remaining = bid['quantity_requested']
        new_status = 'Open'
    else:
        new_status = 'Partially Filled'

    conn.execute(
        "UPDATE bids SET remaining_quantity = ?, active = 1, status = ? WHERE id = ?",
        (new_remaining, new_status, bid_id),
    )
    conn.commit()
