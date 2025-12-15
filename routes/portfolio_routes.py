"""
Portfolio Routes
API endpoints for portfolio functionality
"""

from flask import Blueprint, jsonify, request, session
from services.portfolio_service import (
    get_user_holdings,
    calculate_portfolio_value,
    get_portfolio_allocation,
    get_portfolio_history,
    exclude_holding,
    include_holding,
    create_portfolio_snapshot
)
from datetime import datetime, timedelta

portfolio_bp = Blueprint('portfolio', __name__)


@portfolio_bp.route('/portfolio/data', methods=['GET'])
def get_portfolio_data():
    """
    Get complete portfolio data including holdings, value, and allocation
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    user_id = session['user_id']

    try:
        # Get holdings (already consolidated and with calculated values)
        holdings = get_user_holdings(user_id)

        # Calculate portfolio value
        portfolio_value = calculate_portfolio_value(user_id)

        # Get allocation
        allocation = get_portfolio_allocation(user_id)

        # Convert holdings to JSON-serializable format
        holdings_list = []
        for h in holdings:
            # Holdings are already dicts with all calculated values
            holding_dict = h if isinstance(h, dict) else dict(h)

            # Round values for JSON display
            holding_dict['current_value'] = round(holding_dict['current_value'], 2)
            holding_dict['cost_basis'] = round(holding_dict['cost_basis'], 2)
            holding_dict['gain_loss'] = round(holding_dict['gain_loss'], 2)
            holding_dict['gain_loss_percent'] = round(holding_dict['gain_loss_percent'], 2)
            holding_dict['purchase_price'] = round(holding_dict['purchase_price'], 2)

            holdings_list.append(holding_dict)

        return jsonify({
            'success': True,
            'holdings': holdings_list,
            'portfolio_value': portfolio_value,
            'allocation': allocation
        })

    except Exception as e:
        import traceback
        print(f"Error getting portfolio data: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e), 'success': False}), 500


@portfolio_bp.route('/portfolio/history', methods=['GET'])
def get_history():
    """
    Get historical portfolio values for charting
    Query params: range (1d, 1w, 1m, 3m, 1y)
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    user_id = session['user_id']
    time_range = request.args.get('range', '1m')

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
        # get_portfolio_history now ALWAYS includes current value with live prices
        snapshots = get_portfolio_history(user_id, days)
        print(f"[Portfolio History] Received {len(snapshots)} snapshots from service")

        # Convert to list of dicts with consistent key names for frontend
        history = []
        for snap in snapshots:
            history.append({
                'date': snap['snapshot_date'],
                'value': snap['total_value'],
                'cost_basis': snap['total_cost_basis']
            })

        # Log first and last points to verify data
        if history:
            print(f"[Portfolio History] First point: value={history[0]['value']}, cost_basis={history[0]['cost_basis']}")
            print(f"[Portfolio History] Last point: value={history[-1]['value']}, cost_basis={history[-1]['cost_basis']}")
            print(f"[Portfolio History] Sample values: {[h['value'] for h in history[:5]]}")

        return jsonify({
            'success': True,
            'history': history,
            'range': time_range
        })

    except Exception as e:
        print(f"Error getting portfolio history: {e}")
        return jsonify({'error': str(e)}), 500


@portfolio_bp.route('/portfolio/exclude/<int:order_item_id>', methods=['POST'])
def exclude_item(order_item_id):
    """
    Exclude an order item from portfolio calculations
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    user_id = session['user_id']

    try:
        success = exclude_holding(user_id, order_item_id)

        if success:
            # Recalculate portfolio value after exclusion
            portfolio_value = calculate_portfolio_value(user_id)

            return jsonify({
                'success': True,
                'message': 'Item excluded from portfolio',
                'portfolio_value': portfolio_value
            })
        else:
            return jsonify({'error': 'Failed to exclude item'}), 500

    except Exception as e:
        print(f"Error excluding item: {e}")
        return jsonify({'error': str(e)}), 500


@portfolio_bp.route('/portfolio/include/<int:order_item_id>', methods=['POST'])
def include_item(order_item_id):
    """
    Re-include an order item in portfolio calculations
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    user_id = session['user_id']

    try:
        success = include_holding(user_id, order_item_id)

        if success:
            # Recalculate portfolio value after inclusion
            portfolio_value = calculate_portfolio_value(user_id)

            return jsonify({
                'success': True,
                'message': 'Item included in portfolio',
                'portfolio_value': portfolio_value
            })
        else:
            return jsonify({'error': 'Failed to include item'}), 500

    except Exception as e:
        print(f"Error including item: {e}")
        return jsonify({'error': str(e)}), 500


@portfolio_bp.route('/portfolio/snapshot', methods=['POST'])
def create_snapshot():
    """
    Manually create a portfolio snapshot
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    user_id = session['user_id']

    try:
        snapshot_data = create_portfolio_snapshot(user_id)

        return jsonify({
            'success': True,
            'message': 'Snapshot created',
            'snapshot': snapshot_data
        })

    except Exception as e:
        print(f"Error creating snapshot: {e}")
        return jsonify({'error': str(e)}), 500
