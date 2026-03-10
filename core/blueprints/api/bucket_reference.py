"""
Bucket Reference Price History Endpoint

GET /api/buckets/<bucket_id>/reference_price_history?range=1m

Returns the canonical Reference Price P(t) time series for the bucket page
chart. The series is computed from:
  - BestAsk(t): min effective listing price at time t (using historical spot)
  - BestBid(t): max active bid at time t
  - LastClearedPrice(t): most recent executed trade at or before t

See services/reference_price_service.py for the full P(t) definition.
"""

from flask import request, jsonify
from . import api_bp
from services.reference_price_service import get_reference_price_history
from datetime import datetime, timedelta

RANGE_TO_DAYS = {
    '1d':  1,
    '1w':  7,
    '1m':  30,
    '3m':  90,
    '1y':  365,
}


@api_bp.route('/api/buckets/<int:bucket_id>/reference_price_history', methods=['GET'])
def bucket_reference_price_history(bucket_id):
    """
    Get Reference Price history for a bucket.

    Query params:
        range: '1d' | '1w' | '1m' | '3m' | '1y'  (default: '1m')

    Returns:
        {
          success: true,
          primary_series: [{t: ISO8601, price: float}, ...],
          summary: {
            current_price: float | null,
            first_price: float | null,
            change_amount: float,
            change_percent: float,
            has_data: bool
          },
          latest_spot_as_of: str | null,
          latest_bid_as_of: str | null,
          latest_clear_as_of: str | null,
          range: str
        }
    """
    time_range = request.args.get('range', '1m')
    days = RANGE_TO_DAYS.get(time_range, 30)

    try:
        result = get_reference_price_history(bucket_id, days)

        series = result['primary_series']

        # Build summary statistics
        if series:
            first_price   = series[0]['price']
            current_price = series[-1]['price']
            change_amount = current_price - first_price
            change_pct    = ((change_amount / first_price) * 100) if first_price else 0.0
            summary = {
                'current_price':  round(current_price, 2),
                'first_price':    round(first_price, 2),
                'change_amount':  round(change_amount, 2),
                'change_percent': round(change_pct, 2),
                'has_data':       True,
            }
        else:
            summary = {
                'current_price':  None,
                'first_price':    None,
                'change_amount':  0.0,
                'change_percent': 0.0,
                'has_data':       False,
            }

        return jsonify({
            'success':           True,
            'primary_series':    series,
            'summary':           summary,
            'latest_spot_as_of': result['latest_spot_as_of'],
            'latest_bid_as_of':  result['latest_bid_as_of'],
            'latest_clear_as_of': result['latest_clear_as_of'],
            'range':             time_range,
        })

    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(exc)}), 500


@api_bp.route('/api/buckets/<int:bucket_id>/transactions', methods=['GET'])
def bucket_transactions(bucket_id):
    """
    Get transaction history for a bucket, newest first.

    Returns:
        {
          success: true,
          transactions: [
            {order_id, created_at, quantity, price_each, grading_fee, total,
             buyer, seller}
          ],
          total_count: int
        }
    """
    from database import get_db_connection
    conn = get_db_connection()
    try:
        rows = conn.execute("""
            SELECT
                o.id            AS order_id,
                o.created_at,
                oi.quantity,
                oi.price_each,
                COALESCE(oi.grading_fee_charged, 0) AS grading_fee,
                buyer.username  AS buyer_username,
                seller.username AS seller_username
            FROM order_items oi
            JOIN orders     o  ON o.id  = oi.order_id
            JOIN listings   l  ON l.id  = oi.listing_id
            JOIN categories c  ON c.id  = l.category_id
            JOIN users buyer   ON buyer.id  = o.buyer_id
            JOIN users seller  ON seller.id = l.seller_id
            WHERE c.bucket_id = ?
              AND (o.status IS NULL
                   OR o.status NOT IN ('Cancelled', 'Canceled'))
            ORDER BY o.created_at DESC
        """, (bucket_id,)).fetchall()

        transactions = []
        for row in rows:
            total = (row['quantity'] * row['price_each']) + row['grading_fee']
            transactions.append({
                'order_id':    row['order_id'],
                'created_at':  row['created_at'],
                'quantity':    row['quantity'],
                'price_each':  round(row['price_each'], 2),
                'grading_fee': round(row['grading_fee'], 2),
                'total':       round(total, 2),
                'buyer':       row['buyer_username'],
                'seller':      row['seller_username'],
            })

        return jsonify({
            'success':      True,
            'transactions': transactions,
            'total_count':  len(transactions),
        })

    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(exc)}), 500
    finally:
        conn.close()


@api_bp.route('/api/buckets/<int:bucket_id>/trade_price_history', methods=['GET'])
def bucket_trade_price_history(bucket_id):
    """
    Get cleared-trade price history for a bucket — only real transactions.

    Returns one data point per executed trade within the selected range.
    An opening-price point is prepended at the range boundary using the
    most recent trade that occurred before the range (if any), so the line
    starts from a meaningful value rather than an empty gap.

    Response format matches reference_price_history so the chart JS is
    drop-in compatible.
    """
    from database import get_db_connection

    time_range = request.args.get('range', '1d')
    days = RANGE_TO_DAYS.get(time_range, 1)

    # Use UTC throughout so JS timestamps (appended with 'Z') align with
    # the browser's chart window, which is also based on UTC via new Date().
    now_utc = datetime.utcnow()
    range_start = now_utc - timedelta(days=days)
    # SQLite stores CURRENT_TIMESTAMP in UTC with space separator
    range_start_str = range_start.strftime('%Y-%m-%d %H:%M:%S')

    _CANCELLED = ('Cancelled', 'Canceled')

    conn = get_db_connection()
    try:
        # All trades within the time range, oldest first
        rows = conn.execute("""
            SELECT o.created_at, oi.price_each
            FROM order_items oi
            JOIN orders     o  ON o.id  = oi.order_id
            JOIN listings   l  ON l.id  = oi.listing_id
            JOIN categories c  ON c.id  = l.category_id
            WHERE c.bucket_id = ?
              AND o.created_at >= ?
              AND (o.status IS NULL OR o.status NOT IN (?, ?))
            ORDER BY o.created_at ASC
        """, (bucket_id, range_start_str, *_CANCELLED)).fetchall()

        # Most recent trade BEFORE the range start — gives the "opening" price
        opening = conn.execute("""
            SELECT o.created_at, oi.price_each
            FROM order_items oi
            JOIN orders     o  ON o.id  = oi.order_id
            JOIN listings   l  ON l.id  = oi.listing_id
            JOIN categories c  ON c.id  = l.category_id
            WHERE c.bucket_id = ?
              AND o.created_at < ?
              AND (o.status IS NULL OR o.status NOT IN (?, ?))
            ORDER BY o.created_at DESC
            LIMIT 1
        """, (bucket_id, range_start_str, *_CANCELLED)).fetchone()

        def _to_utc_iso(sqlite_ts):
            """Convert SQLite UTC timestamp to JS-safe ISO 8601 with Z suffix."""
            if not sqlite_ts:
                return None
            return sqlite_ts.replace(' ', 'T') + 'Z'

        series = []
        if opening:
            # Pin the opening price at the range boundary (UTC, with Z)
            series.append({
                't':     range_start.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'price': round(opening['price_each'], 2),
            })

        for row in rows:
            series.append({
                't':     _to_utc_iso(row['created_at']),
                'price': round(row['price_each'], 2),
            })

        latest_clear = series[-1]['t'] if series else None

        if series:
            first_price   = series[0]['price']
            current_price = series[-1]['price']
            change_amount = current_price - first_price
            change_pct    = ((change_amount / first_price) * 100) if first_price else 0.0
            summary = {
                'current_price':  current_price,
                'first_price':    first_price,
                'change_amount':  round(change_amount, 2),
                'change_percent': round(change_pct, 2),
                'has_data':       True,
            }
        else:
            summary = {
                'current_price':  None,
                'first_price':    None,
                'change_amount':  0.0,
                'change_percent': 0.0,
                'has_data':       False,
            }

        return jsonify({
            'success':            True,
            'primary_series':     series,
            'summary':            summary,
            'latest_clear_as_of': latest_clear,
            'latest_spot_as_of':  None,
            'latest_bid_as_of':   None,
            'range':              time_range,
        })

    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(exc)}), 500
    finally:
        conn.close()
