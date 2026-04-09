"""
Ledger Retrieval

Methods for querying ledger data.
"""

from typing import Dict, List, Optional, Any
import database


def get_db_connection():
    """Get database connection - wrapper for late binding in tests"""
    return database.get_db_connection()


def get_order_ledger(order_id: int) -> Optional[Dict[str, Any]]:
    """Get full ledger data for an order"""
    conn = get_db_connection()
    try:
        # Get order ledger — join orders to get webhook-authoritative payment_method_type
        order = conn.execute('''
            SELECT ol.*, u.username as buyer_username,
                   o.payment_method_type,
                   o.payment_status,
                   o.requires_payment_clearance
            FROM orders_ledger ol
            JOIN users u ON ol.buyer_id = u.id
            LEFT JOIN orders o ON o.id = ol.order_id
            WHERE ol.order_id = ?
        ''', (order_id,)).fetchone()

        if not order:
            return None

        # Get items
        items = conn.execute('''
            SELECT oil.*, u.username as seller_username
            FROM order_items_ledger oil
            JOIN users u ON oil.seller_id = u.id
            WHERE oil.order_id = ?
        ''', (order_id,)).fetchall()

        # Get payouts
        payouts = conn.execute('''
            SELECT op.*, u.username as seller_username
            FROM order_payouts op
            JOIN users u ON op.seller_id = u.id
            WHERE op.order_id = ?
        ''', (order_id,)).fetchall()

        # Get events
        events = conn.execute('''
            SELECT * FROM order_events
            WHERE order_id = ?
            ORDER BY created_at ASC
        ''', (order_id,)).fetchall()

        return {
            'order': dict(order),
            'items': [dict(item) for item in items],
            'payouts': [dict(payout) for payout in payouts],
            'events': [dict(event) for event in events]
        }

    finally:
        conn.close()


def get_orders_ledger_list(
    status_filter: Optional[str] = None,
    buyer_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    min_gross: Optional[float] = None,
    max_gross: Optional[float] = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    Get filtered list of ledger orders.

    Args:
        status_filter: Filter by order status
        buyer_id: Filter by buyer
        start_date: Filter by start date (created_at >=)
        end_date: Filter by end date (created_at <=)
        min_gross: Filter by minimum gross amount
        max_gross: Filter by maximum gross amount
        limit: Max results to return
        offset: Results offset for pagination

    Returns:
        List of order ledger records
    """
    conn = get_db_connection()
    try:
        # Base query — payment_method_type is always present in orders
        query = '''
            SELECT ol.*, u.username as buyer_username,
                   o.payment_method_type,
                   o.payment_status,
                   (SELECT COUNT(*) FROM order_items_ledger WHERE order_ledger_id = ol.id) as item_count,
                   (SELECT COUNT(DISTINCT seller_id) FROM order_items_ledger WHERE order_ledger_id = ol.id) as seller_count
            FROM orders_ledger ol
            JOIN users u ON ol.buyer_id = u.id
            LEFT JOIN orders o ON o.id = ol.order_id
            WHERE 1=1
        '''
        # Detect if extended payment columns exist on orders table (added by migration)
        # These may be absent in test SQLite schemas.
        _extended_cols = []
        try:
            _probe = conn.execute('SELECT payout_status, refund_status, requires_payment_clearance, requires_payout_recovery FROM orders LIMIT 0')
            _extended_cols = ['o.payout_status', 'o.refund_status', 'o.requires_payment_clearance', 'o.requires_payout_recovery']
            query = '''
                SELECT ol.*, u.username as buyer_username,
                       o.payment_method_type,
                       o.payment_status,
                       o.payout_status,
                       o.refund_status,
                       o.requires_payment_clearance,
                       o.requires_payout_recovery,
                       (SELECT COUNT(*) FROM order_items_ledger WHERE order_ledger_id = ol.id) as item_count,
                       (SELECT COUNT(DISTINCT seller_id) FROM order_items_ledger WHERE order_ledger_id = ol.id) as seller_count
                FROM orders_ledger ol
                JOIN users u ON ol.buyer_id = u.id
                LEFT JOIN orders o ON o.id = ol.order_id
                WHERE 1=1
            '''
            # Try to also include tax columns (added by migration 031)
            try:
                conn.execute('SELECT tax_amount, buyer_card_fee FROM orders LIMIT 0')
                query = '''
                    SELECT ol.*, u.username as buyer_username,
                           o.payment_method_type,
                           o.payment_status,
                           o.payout_status,
                           o.refund_status,
                           o.requires_payment_clearance,
                           o.requires_payout_recovery,
                           COALESCE(o.tax_amount, 0) AS tax_amount,
                           COALESCE(o.buyer_card_fee, 0) AS buyer_card_fee,
                           (SELECT COUNT(*) FROM order_items_ledger WHERE order_ledger_id = ol.id) as item_count,
                           (SELECT COUNT(DISTINCT seller_id) FROM order_items_ledger WHERE order_ledger_id = ol.id) as seller_count
                    FROM orders_ledger ol
                    JOIN users u ON ol.buyer_id = u.id
                    LEFT JOIN orders o ON o.id = ol.order_id
                    WHERE 1=1
                '''
            except Exception:
                pass  # pre-migration — no tax columns; keep extended query without them
        except Exception:
            pass  # Fall back to base query without extended columns
        params = []

        if status_filter:
            query += ' AND ol.order_status = ?'
            params.append(status_filter)
        if buyer_id:
            query += ' AND ol.buyer_id = ?'
            params.append(buyer_id)
        if start_date:
            query += ' AND ol.created_at >= ?'
            params.append(start_date)
        if end_date:
            query += ' AND ol.created_at <= ?'
            params.append(end_date)
        if min_gross is not None:
            query += ' AND ol.gross_amount >= ?'
            params.append(min_gross)
        if max_gross is not None:
            query += ' AND ol.gross_amount <= ?'
            params.append(max_gross)

        query += ' ORDER BY ol.created_at DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])

        results = conn.execute(query, params).fetchall()
        return [dict(row) for row in results]

    finally:
        conn.close()
