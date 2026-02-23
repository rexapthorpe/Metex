"""
Admin Order Management Routes

Routes for admin order/payout hold, approve, release, and refund operations.
"""

from flask import jsonify, request, session
from utils.auth_utils import admin_required
from . import admin_bp


@admin_bp.route('/api/orders/<int:order_id>/hold', methods=['POST'])
@admin_required
def admin_hold_order(order_id):
    """
    Admin action: Place an order under review and hold all related payouts.

    POST /admin/api/orders/<order_id>/hold
    Body: { "reason": "string (required)" }

    Effects:
    - order_status → UNDER_REVIEW
    - ALL payouts → PAYOUT_ON_HOLD
    - Logs ORDER_HELD event
    """
    from services.ledger_service import LedgerService, EscrowControlError

    data = request.get_json() or {}
    reason = data.get('reason', '').strip()

    if not reason:
        return jsonify({'success': False, 'error': 'Reason is required'}), 400

    admin_id = session.get('user_id')

    try:
        LedgerService.hold_order(order_id, admin_id, reason)
        return jsonify({
            'success': True,
            'message': f'Order {order_id} placed under review',
            'new_status': 'UNDER_REVIEW'
        })

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 404

    except EscrowControlError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    except Exception as e:
        print(f"Error holding order {order_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/orders/<int:order_id>/approve', methods=['POST'])
@admin_required
def admin_approve_order(order_id):
    """
    Admin action: Release an order from review to awaiting shipment.

    POST /admin/api/orders/<order_id>/approve

    Effects:
    - order_status → AWAITING_SHIPMENT
    - Held payouts → PAYOUT_NOT_READY
    - Logs ORDER_APPROVED event
    """
    from services.ledger_service import LedgerService, EscrowControlError

    admin_id = session.get('user_id')

    try:
        LedgerService.approve_order(order_id, admin_id)
        return jsonify({
            'success': True,
            'message': f'Order {order_id} approved and released from review',
            'new_status': 'AWAITING_SHIPMENT'
        })

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 404

    except EscrowControlError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    except Exception as e:
        print(f"Error approving order {order_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/payouts/<int:payout_id>/hold', methods=['POST'])
@admin_required
def admin_hold_payout(payout_id):
    """
    Admin action: Hold a specific seller's payout.

    POST /admin/api/payouts/<payout_id>/hold
    Body: { "reason": "string (required)" }

    Effects:
    - payout_status → PAYOUT_ON_HOLD
    - Logs PAYOUT_HELD event
    """
    from services.ledger_service import LedgerService, EscrowControlError

    data = request.get_json() or {}
    reason = data.get('reason', '').strip()

    if not reason:
        return jsonify({'success': False, 'error': 'Reason is required'}), 400

    admin_id = session.get('user_id')

    try:
        LedgerService.hold_payout(payout_id, admin_id, reason)
        return jsonify({
            'success': True,
            'message': f'Payout {payout_id} placed on hold',
            'new_status': 'PAYOUT_ON_HOLD'
        })

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 404

    except EscrowControlError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    except Exception as e:
        print(f"Error holding payout {payout_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/payouts/<int:payout_id>/release', methods=['POST'])
@admin_required
def admin_release_payout(payout_id):
    """
    Admin action: Release a held payout to PAYOUT_READY.

    POST /admin/api/payouts/<payout_id>/release

    Effects:
    - payout_status → PAYOUT_READY
    - Logs PAYOUT_RELEASED event
    """
    from services.ledger_service import LedgerService, EscrowControlError

    admin_id = session.get('user_id')

    try:
        LedgerService.release_payout(payout_id, admin_id)
        return jsonify({
            'success': True,
            'message': f'Payout {payout_id} released',
            'new_status': 'PAYOUT_READY'
        })

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 404

    except EscrowControlError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    except Exception as e:
        print(f"Error releasing payout {payout_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/orders/<int:order_id>/refund', methods=['POST'])
@admin_required
def admin_refund_order(order_id):
    """
    Admin action: Process a full or partial refund (ledger-only, no money movement).

    POST /admin/api/orders/<order_id>/refund
    Body: {
        "refund_type": "full" | "partial" (required),
        "reason": "string (required)",
        "seller_id": int (optional, for partial),
        "order_item_ids": [int] (optional, for partial)
    }

    Effects:
    - order_status → REFUNDED or PARTIALLY_REFUNDED
    - Affected payouts → PAYOUT_CANCELLED
    - Logs REFUND_INITIATED and REFUND_COMPLETED events
    """
    from services.ledger_service import LedgerService, EscrowControlError

    data = request.get_json() or {}
    refund_type = data.get('refund_type')
    reason = data.get('reason', '').strip()
    seller_id = data.get('seller_id')
    order_item_ids = data.get('order_item_ids')

    if not refund_type or refund_type not in ('full', 'partial'):
        return jsonify({'success': False, 'error': "refund_type must be 'full' or 'partial'"}), 400

    if not reason:
        return jsonify({'success': False, 'error': 'Reason is required'}), 400

    if refund_type == 'partial' and not seller_id and not order_item_ids:
        return jsonify({'success': False, 'error': 'Partial refund requires seller_id or order_item_ids'}), 400

    admin_id = session.get('user_id')

    try:
        result = LedgerService.process_refund(
            order_id=order_id,
            admin_id=admin_id,
            refund_type=refund_type,
            reason=reason,
            seller_id=seller_id,
            order_item_ids=order_item_ids
        )
        return jsonify({
            'success': True,
            'message': f'Refund processed for order {order_id}',
            'refund_type': refund_type,
            'refund_amount': result['refund_amount'],
            'affected_items': result['affected_items'],
            'affected_payouts': result['affected_payouts'],
            'new_status': 'REFUNDED' if refund_type == 'full' else 'PARTIALLY_REFUNDED'
        })

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 404

    except EscrowControlError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    except Exception as e:
        print(f"Error refunding order {order_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
