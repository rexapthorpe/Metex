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
