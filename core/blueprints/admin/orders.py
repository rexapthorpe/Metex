"""
Admin Order Management Routes

Routes for admin order/payout hold, approve, release, and refund operations.
"""

import logging

from flask import jsonify, request, session
from utils.auth_utils import admin_required
from . import admin_bp

logger = logging.getLogger(__name__)


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


@admin_bp.route('/api/orders/<int:order_id>/mark-ach-cleared', methods=['POST'])
@admin_required
def admin_mark_ach_cleared(order_id):
    """
    Admin action: Mark an ACH payment as cleared so seller payouts become eligible.

    POST /admin/api/orders/<order_id>/mark-ach-cleared

    Idempotent: Returns success even if already cleared.
    """
    from services.ledger_service import LedgerService, EscrowControlError

    admin_id = session.get('user_id')

    try:
        result = LedgerService.mark_ach_cleared(order_id, admin_id)
        return jsonify({
            'success': True,
            'already_cleared': result['already_cleared'],
            'cleared_at': result['cleared_at'],
            'message': (
                f'Order {order_id} ACH payment already cleared'
                if result['already_cleared']
                else f'Order {order_id} ACH payment marked as cleared'
            ),
        })

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 404

    except EscrowControlError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    except Exception as e:
        logger.exception("Unexpected error marking ACH cleared for order %s", order_id)
        return jsonify({'success': False, 'error': 'Internal error. Check server logs.'}), 500


@admin_bp.route('/api/orders/<int:order_id>/refund-stripe', methods=['POST'])
@admin_required
def admin_refund_buyer_stripe(order_id):
    """
    Admin action: Create a full Stripe refund for the buyer's payment.

    POST /admin/api/orders/<order_id>/refund-stripe
    Body: { "reason": "string (optional)" }

    Effects:
    - Creates stripe.Refund against the stored PaymentIntent
    - Marks orders.refund_status = 'refunded'
    - Cancels unreleased payouts; flags released payouts for recovery
    - Updates orders_ledger.order_status = REFUNDED
    """
    from services.ledger_service import LedgerService, EscrowControlError

    data = request.get_json() or {}
    reason = data.get('reason', '').strip() or 'Admin refund'
    admin_id = session.get('user_id')

    logger.info("[Refund] Admin %s initiating refund for order %s", admin_id, order_id)

    try:
        result = LedgerService.refund_buyer_stripe(order_id, admin_id, reason)
        logger.info(
            "[Refund] Success  order_id=%s  refund_id=%s  requires_recovery=%s",
            order_id, result['refund_id'], result['requires_payout_recovery'],
        )
        return jsonify({
            'success': True,
            'message': f"Stripe refund created: {result['refund_id']}",
            'refund_id': result['refund_id'],
            'amount': result['amount'],
            'requires_payout_recovery': result['requires_payout_recovery'],
            'recovery_pending_payout_ids': result['recovery_pending_payout_ids'],
            'cancelled_payout_ids': result['cancelled_payout_ids'],
        })

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 404

    except EscrowControlError as e:
        logger.warning("[Refund] Blocked  order_id=%s: %s", order_id, e)
        return jsonify({'success': False, 'error': str(e)}), 400

    except Exception:
        logger.exception("[Refund] Unexpected error  order_id=%s", order_id)
        return jsonify({'success': False, 'error': 'Internal error. Check server logs.'}), 500


@admin_bp.route('/api/payouts/<int:payout_id>/stripe-transfer', methods=['POST'])
@admin_required
def admin_release_stripe_transfer(payout_id):
    """
    Admin action: Create a Stripe transfer to release a seller payout.

    POST /admin/api/payouts/<payout_id>/stripe-transfer

    Idempotency: Returns 400 if payout already released (no double-transfer).
    ACH: Returns 400 if requires_payment_clearance is set.
    """
    from services.ledger_service import LedgerService, EscrowControlError
    from services.system_settings_service import get_manual_payouts_enabled

    admin_id = session.get('user_id')

    if not get_manual_payouts_enabled():
        logger.warning(
            '[ManualPayout] blocked — manual_payouts_enabled=False  payout_id=%s  admin=%s',
            payout_id, admin_id,
        )
        return jsonify({
            'success': False,
            'error': 'Manual payout releases are currently disabled. Enable them in System Settings → Payment Controls.',
        }), 403

    try:
        result = LedgerService.release_stripe_transfer(payout_id, admin_id)
        return jsonify({
            'success': True,
            'message': f"Stripe transfer created: {result['transfer_id']}",
            'transfer_id': result['transfer_id'],
            'amount': result['amount'],
            'seller_id': result['seller_id'],
        })

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 404

    except EscrowControlError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    except Exception as e:
        logger.exception("Unexpected error releasing Stripe transfer for payout %s", payout_id)
        return jsonify({'success': False, 'error': 'Internal error. Check server logs.'}), 500


@admin_bp.route('/api/payouts/<int:payout_id>/attempt-recovery', methods=['POST'])
@admin_required
def admin_attempt_payout_recovery(payout_id):
    """
    Admin action: Attempt Stripe Transfer Reversal to recover a seller payout.

    POST /admin/api/payouts/<payout_id>/attempt-recovery

    Safe to call on 'pending', 'failed', or 'manual_review' rows.
    Returns 200 no-op if already 'recovered'.
    Returns 400 if preconditions not met (not PAID_OUT, no transfer ID, etc.).

    Outcomes in JSON:
      outcome: 'recovered' | 'manual_review' | 'failed'
      reversal_id: Stripe reversal ID (if recovered)
      reason: failure/manual-review reason (if not recovered)
    """
    from services.ledger_service import LedgerService, EscrowControlError

    admin_id = session.get('user_id')

    logger.info(
        "[Recovery] Admin %s attempting recovery for payout %s", admin_id, payout_id
    )

    try:
        result = LedgerService.attempt_payout_recovery(payout_id, admin_id)
        return jsonify({
            'success': True,
            'outcome': result['outcome'],
            'reversal_id': result['reversal_id'],
            'reason': result['reason'],
        })

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 404

    except EscrowControlError as e:
        logger.warning("[Recovery] Blocked  payout_id=%s: %s", payout_id, e)
        return jsonify({'success': False, 'error': str(e)}), 400

    except Exception:
        logger.exception("[Recovery] Unexpected error  payout_id=%s", payout_id)
        return jsonify({'success': False, 'error': 'Internal error. Check server logs.'}), 500


@admin_bp.route('/api/payouts/<int:payout_id>/evaluate-readiness', methods=['POST'])
@admin_required
def admin_evaluate_payout_readiness(payout_id):
    """
    Evaluate and update readiness state for a single payout row.

    POST /admin/api/payouts/<payout_id>/evaluate-readiness

    Transitions:
    - PAYOUT_NOT_READY → PAYOUT_READY  (if all conditions met)
    - PAYOUT_READY → PAYOUT_NOT_READY  (if conditions no longer met)

    Does NOT override: PAID_OUT, PAYOUT_CANCELLED, PAYOUT_ON_HOLD,
    PAYOUT_SCHEDULED, PAYOUT_IN_PROGRESS.

    Returns:
      ready: bool
      reason: block reason string, or null if ready
      status_updated: bool
      old_status: str
      new_status: str
    """
    from services.ledger_service import LedgerService, EscrowControlError

    try:
        result = LedgerService.evaluate_payout_readiness(payout_id)
        return jsonify({
            'success': True,
            'payout_id': result['payout_id'],
            'ready': result['ready'],
            'reason': result['reason'],
            'status_updated': result['status_updated'],
            'old_status': result['old_status'],
            'new_status': result['new_status'],
        })

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 404

    except Exception:
        logger.exception("Unexpected error evaluating readiness for payout %s", payout_id)
        return jsonify({'success': False, 'error': 'Internal error. Check server logs.'}), 500


@admin_bp.route('/api/orders/<int:order_id>/evaluate-readiness', methods=['POST'])
@admin_required
def admin_evaluate_order_readiness(order_id):
    """
    Evaluate and update readiness for ALL payout rows of an order.

    POST /admin/api/orders/<order_id>/evaluate-readiness

    Returns per-payout results plus a summary.
    """
    from services.ledger_service import LedgerService
    import database

    conn = database.get_db_connection()
    try:
        payout_rows = conn.execute(
            'SELECT id FROM order_payouts WHERE order_id = ? ORDER BY id',
            (order_id,)
        ).fetchall()
    finally:
        conn.close()

    if not payout_rows:
        return jsonify({'success': False, 'error': f'No payouts found for order {order_id}'}), 404

    results = []
    errors = []
    for row in payout_rows:
        payout_id = row['id']
        try:
            r = LedgerService.evaluate_payout_readiness(payout_id)
            results.append(r)
        except Exception as exc:
            logger.exception(
                "Error evaluating readiness for payout %s (order %s)", payout_id, order_id
            )
            errors.append({'payout_id': payout_id, 'error': str(exc)})

    ready_count = sum(1 for r in results if r['ready'])
    updated_count = sum(1 for r in results if r['status_updated'])

    return jsonify({
        'success': True,
        'order_id': order_id,
        'total_payouts': len(payout_rows),
        'ready_count': ready_count,
        'updated_count': updated_count,
        'results': results,
        'errors': errors,
    })


@admin_bp.route('/api/payouts/run-auto', methods=['POST'])
@admin_required
def admin_run_auto_payouts():
    """
    Admin action: Automatically release all PAYOUT_READY payouts via Stripe.

    POST /admin/api/payouts/run-auto

    For every payout in PAYOUT_READY status:
    - Re-checks readiness via get_payout_block_reason() (never trusts stale state)
    - Skips if provider_transfer_id already set (idempotency)
    - Skips if payout_status == PAID_OUT (idempotency)
    - Calls release_stripe_transfer() for each still-eligible payout

    Returns:
        { processed, successful, skipped, errors, results }
    """
    from services.ledger_service import LedgerService
    from services.system_settings_service import get_auto_payouts_enabled

    admin_id = session.get('user_id')

    if not get_auto_payouts_enabled():
        logger.warning('[AutoPayouts] blocked — auto_payouts_enabled=False  admin=%s', admin_id)
        return jsonify({
            'success': False,
            'error': 'Auto payouts are currently disabled. Enable them in System Settings → Payment Controls.',
        }), 403

    try:
        summary = LedgerService.run_auto_payouts(admin_id=admin_id)
        return jsonify({'success': True, **summary})

    except Exception as e:
        logger.exception("Error in admin_run_auto_payouts")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/orders/<int:order_id>/nudge-seller', methods=['POST'])
@admin_required
def nudge_seller(order_id):
    """
    Send a reminder notification to the seller(s) on an order to upload tracking.

    POST /admin/api/orders/<order_id>/nudge-seller
    Returns: { success, notified_count }
    """
    import database

    conn = database.get_db_connection()
    try:
        # Get unique sellers for this order
        rows = conn.execute('''
            SELECT DISTINCT l.seller_id
            FROM order_items oi
            JOIN listings l ON oi.listing_id = l.id
            WHERE oi.order_id = ?
        ''', (order_id,)).fetchall()

        if not rows:
            return jsonify({'success': False, 'error': 'Order not found or has no items'}), 404

        # Check tracking status — only notify sellers who haven't uploaded tracking
        notified = 0
        for row in rows:
            seller_id = row['seller_id']
            tracking = conn.execute(
                'SELECT id FROM seller_order_tracking WHERE order_id = ? AND seller_id = ?',
                (order_id, seller_id)
            ).fetchone()
            if tracking:
                continue  # Already uploaded — skip

            # Insert nudge notification
            try:
                conn.execute('''
                    INSERT INTO notifications (user_id, type, message, is_read, created_at)
                    VALUES (?, 'admin_nudge', ?, 0, CURRENT_TIMESTAMP)
                ''', (seller_id,
                      f'Reminder: Please upload your tracking number for order #{order_id}. '
                      f'Your payout cannot be released until tracking is confirmed.'))
                notified += 1
            except Exception:
                pass  # Notifications table may not exist yet — non-fatal

        conn.commit()
        return jsonify({'success': True, 'notified_count': notified})

    except Exception as e:
        logger.exception("Error in nudge_seller order_id=%s", order_id)
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()
