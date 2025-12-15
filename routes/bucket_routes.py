"""
Bucket Routes
API endpoints for bucket-specific functionality including price history
"""

from flask import Blueprint, jsonify, request, session
from services.bucket_price_history_service import (
    get_bucket_price_history,
    get_current_best_ask,
    update_bucket_price
)

bucket_bp = Blueprint('bucket', __name__)


@bucket_bp.route('/bucket/<int:bucket_id>/price-history', methods=['GET'])
def get_price_history(bucket_id):
    """
    Get historical best ask prices for a bucket for charting

    Query params:
        range: Time range (1d, 1w, 1m, 3m, 1y) - default: 1m
        random_year: If '1', aggregate data across all years matching bucket specs
        packaging_styles: Multi-select packaging type filters (list)

    Returns:
        JSON with history data and current price info
    """
    from database import get_db_connection
    from datetime import datetime, timedelta

    time_range = request.args.get('range', '1m')
    random_year = request.args.get('random_year') == '1'

    # Get packaging filters (multi-select)
    packaging_styles = request.args.getlist('packaging_styles')
    packaging_styles = [ps.strip() for ps in packaging_styles if ps.strip()]

    # Map range to days
    range_map = {
        '1d': 1,
        '1w': 7,
        '1m': 30,
        '3m': 90,
        '1y': 365
    }

    days = range_map.get(time_range, 30)

    try:
        # Get bucket IDs to query based on Random Year mode
        if random_year:
            conn = get_db_connection()

            # Get the base bucket info
            bucket = conn.execute('SELECT * FROM categories WHERE bucket_id = ? LIMIT 1', (bucket_id,)).fetchone()

            if not bucket:
                return jsonify({'error': 'Bucket not found'}), 404

            # Find all matching buckets (same specs except year)
            matching_buckets_query = '''
                SELECT bucket_id FROM categories
                WHERE metal = ? AND product_type = ? AND weight = ? AND purity = ?
                  AND mint = ? AND finish = ? AND grade = ? AND product_line = ?
                  AND condition_category IS NOT DISTINCT FROM ?
                  AND series_variant IS NOT DISTINCT FROM ?
                  AND is_isolated = 0
            '''
            matching_buckets = conn.execute(matching_buckets_query, (
                bucket['metal'], bucket['product_type'], bucket['weight'], bucket['purity'],
                bucket['mint'], bucket['finish'], bucket['grade'], bucket['product_line'],
                bucket['condition_category'], bucket['series_variant']
            )).fetchall()

            bucket_ids = [row['bucket_id'] for row in matching_buckets] if matching_buckets else [bucket_id]
            conn.close()
        else:
            bucket_ids = [bucket_id]

        # Get historical data for all relevant buckets
        all_history = []
        for bid in bucket_ids:
            history = get_bucket_price_history(bid, days)
            all_history.extend(history)

        # Sort combined history by timestamp
        all_history.sort(key=lambda x: x['timestamp'])

        history = all_history

        # Get current price for all relevant buckets (with packaging filters)
        if random_year:
            # Get best ask across all matching buckets
            current_prices = [get_current_best_ask(bid, packaging_styles=packaging_styles) for bid in bucket_ids]
            valid_prices = [p for p in current_prices if p is not None]
            current_price = min(valid_prices) if valid_prices else None
        else:
            # Single bucket mode
            current_price = get_current_best_ask(bucket_id, packaging_styles=packaging_styles)

        # If no history in requested range, check if ANY history exists at all
        # This handles the case where all listings are removed but historical data exists
        if not history:
            # Check for any historical data (last 1 year)
            all_history = get_bucket_price_history(bucket_id, 365)

            if all_history:
                # Historical data exists, but not in this time range
                # Use the most recent historical price as the starting point
                last_historical_point = all_history[-1]

                # Create a single data point with the last known price
                # The frontend will forward-fill this to "now"
                history = [last_historical_point]

                print(f"[Bucket {bucket_id}] No history in {time_range} range, but found historical data. Using last known price: ${last_historical_point['price']}")

        # Calculate summary statistics for the range
        if history:
            first_price = history[0]['price']
            last_price = history[-1]['price'] if len(history) > 1 else first_price

            # Use current price if available, otherwise use last historical price
            if current_price is not None:
                current = current_price
            else:
                current = last_price

            change_amount = current - first_price
            change_percent = ((current - first_price) / first_price * 100) if first_price > 0 else 0

            summary = {
                'current_price': round(current, 2),
                'change_amount': round(change_amount, 2),
                'change_percent': round(change_percent, 2),
                'first_price': round(first_price, 2),
                'has_active_listings': current_price is not None
            }
        else:
            # No history at all - truly empty bucket
            summary = {
                'current_price': round(current_price, 2) if current_price else None,
                'change_amount': 0.0,
                'change_percent': 0.0,
                'first_price': round(current_price, 2) if current_price else None,
                'has_active_listings': current_price is not None
            }

        return jsonify({
            'success': True,
            'history': history,
            'summary': summary,
            'range': time_range
        })

    except Exception as e:
        print(f"Error getting bucket price history: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@bucket_bp.route('/bucket/<int:bucket_id>/update-price', methods=['POST'])
def trigger_price_update(bucket_id):
    """
    Manually trigger a price update for a bucket

    This endpoint can be called after listing changes to ensure price history is updated.
    Normally, this would be called automatically by the system when listings change.

    Returns:
        JSON with the updated price
    """
    try:
        current_price = update_bucket_price(bucket_id)

        return jsonify({
            'success': True,
            'current_price': round(current_price, 2) if current_price else None,
            'message': 'Price updated successfully'
        })

    except Exception as e:
        print(f"Error updating bucket price: {e}")
        return jsonify({'error': str(e)}), 500
