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


@admin_bp.route('/api/orders/<int:order_id>/refund-preview', methods=['GET'])
@admin_required
def admin_refund_preview(order_id):
    """
    Return all data needed to populate the refund confirmation modal.

    GET /admin/api/orders/<order_id>/refund-preview

    Returns:
      can_refund: bool
      block_reason: str | null
      order: { id, buyer_username, total_price, tax_amount, buyer_card_fee,
               subtotal, payment_status, refund_status, refund_amount,
               refund_subtotal, refund_tax_amount, refund_processing_fee,
               stripe_payment_intent_id, refund_reason, stripe_refund_id, refunded_at }
      payouts: [{ id, seller_id, seller_username, seller_net_amount,
                  payout_status, provider_transfer_id, payout_recovery_status }]
      refundable_amount: float
      already_refunded: float
      requires_recovery: bool
      paid_out_payout_count: int
    """
    import database as _db_module

    conn = _db_module.get_db_connection()
    try:
        order = conn.execute('''
            SELECT o.id, o.total_price, o.tax_amount, o.buyer_card_fee,
                   o.payment_status, o.refund_status, o.refund_amount,
                   o.refund_subtotal, o.refund_tax_amount, o.refund_processing_fee,
                   o.platform_covered_amount,
                   o.stripe_payment_intent_id, o.refund_reason, o.stripe_refund_id, o.refunded_at,
                   u.username AS buyer_username
            FROM orders o
            JOIN users u ON o.buyer_id = u.id
            WHERE o.id = ?
        ''', (order_id,)).fetchone()

        if not order:
            return jsonify({'success': False, 'error': 'Order not found'}), 404

        order_dict = dict(order)
        total_price = float(order['total_price'] or 0)
        tax_amount  = float(order['tax_amount'] or 0)
        card_fee    = float(order['buyer_card_fee'] or 0)
        # subtotal = items only (gross_amount from ledger is canonical, but can derive)
        order_dict['subtotal'] = round(total_price - tax_amount - card_fee, 2)

        # Eligibility check
        if order['payment_status'] != 'paid':
            return jsonify({
                'success': True,
                'can_refund': False,
                'block_reason': f"Payment status is '{order['payment_status']}' — must be 'paid'",
                'order': order_dict,
                'payouts': [],
                'refundable_amount': 0.0,
                'already_refunded': 0.0,
                'requires_recovery': False,
                'paid_out_payout_count': 0,
            })

        refund_status = order['refund_status'] or 'not_refunded'
        if refund_status == 'refunded':
            return jsonify({
                'success': True,
                'can_refund': False,
                'block_reason': 'Order is already fully refunded',
                'order': order_dict,
                'payouts': [],
                'refundable_amount': 0.0,
                'already_refunded': round(order['refund_amount'] or 0, 2),
                'requires_recovery': False,
                'paid_out_payout_count': 0,
            })

        # Payout rows
        payout_rows = conn.execute('''
            SELECT op.id, op.seller_id, op.seller_net_amount, op.payout_status,
                   op.provider_transfer_id, op.payout_recovery_status,
                   u.username AS seller_username
            FROM order_payouts op
            JOIN users u ON op.seller_id = u.id
            WHERE op.order_id = ?
            ORDER BY op.id
        ''', (order_id,)).fetchall()

        payouts = [dict(p) for p in payout_rows]
        paid_out_payouts = [p for p in payouts if p['payout_status'] == 'PAID_OUT']
        requires_recovery = len(paid_out_payouts) > 0

        already_refunded = round(order['refund_amount'] or 0, 2)
        refundable_amount = round(total_price - already_refunded, 2)

        return jsonify({
            'success': True,
            'can_refund': True,
            'block_reason': None,
            'order': order_dict,
            'payouts': payouts,
            'refundable_amount': refundable_amount,
            'already_refunded': already_refunded,
            'requires_recovery': requires_recovery,
            'paid_out_payout_count': len(paid_out_payouts),
        })

    except Exception as exc:
        logger.exception('[RefundPreview] error  order_id=%s', order_id)
        return jsonify({'success': False, 'error': str(exc)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/orders/<int:order_id>/refund-stripe', methods=['POST'])
@admin_required
def admin_refund_buyer_stripe(order_id):
    """
    Admin action: Create a full or partial Stripe refund for the buyer's payment.

    POST /admin/api/orders/<order_id>/refund-stripe
    Body: {
        "reason": "string (optional)",
        "amount": float (optional — omit for full refund, provide for partial)
    }

    Effects:
    - Creates stripe.Refund against the stored PaymentIntent
    - Marks orders.refund_status = 'refunded' or 'partially_refunded'
    - Tracks refund breakdown: refund_subtotal, refund_tax_amount, refund_processing_fee
    - Reverses platform fee / spread on orders_ledger
    - Cancels unreleased payouts; attempts auto-recovery for released payouts
    - Updates orders_ledger.order_status = REFUNDED
    """
    from services.ledger_service import LedgerService, EscrowControlError

    data = request.get_json() or {}
    reason = data.get('reason', '').strip() or 'Admin refund'
    amount = data.get('amount')  # None = full refund
    if amount is not None:
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'amount must be a number'}), 400

    admin_id = session.get('user_id')

    logger.info(
        "[Refund] Admin %s initiating refund for order %s  amount=%s",
        admin_id, order_id, amount,
    )

    try:
        result = LedgerService.refund_buyer_stripe(order_id, admin_id, reason, amount=amount)
        logger.info(
            "[Refund] Success  order_id=%s  refund_id=%s  is_partial=%s  requires_recovery=%s",
            order_id, result['refund_id'], result['is_partial'], result['requires_payout_recovery'],
        )
        return jsonify({
            'success': True,
            'message': f"Stripe refund created: {result['refund_id']}",
            'refund_id': result['refund_id'],
            'amount': result['amount'],
            'refund_subtotal': result['refund_subtotal'],
            'refund_tax_amount': result['refund_tax_amount'],
            'refund_processing_fee': result['refund_processing_fee'],
            'is_partial': result['is_partial'],
            'requires_payout_recovery': result['requires_payout_recovery'],
            'recovery_outcomes': result['recovery_outcomes'],
            'recovery_pending_payout_ids': result['recovery_pending_payout_ids'],
            'cancelled_payout_ids': result['cancelled_payout_ids'],
            'platform_covered_amount': result['platform_covered_amount'],
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


@admin_bp.route('/api/orders/<int:order_id>/mark-delivered', methods=['POST'])
@admin_required
def admin_mark_delivered(order_id):
    """
    Admin action: Mark a seller's shipment as delivered for a given order.

    POST /admin/api/orders/<order_id>/mark-delivered
    Body: { "seller_id": int (required) }

    Idempotent: if delivered_at is already set, returns success without overwriting.
    Sets seller_order_tracking.delivered_at = now.
    """
    import database as _db_module
    from datetime import datetime

    data = request.get_json(silent=True) or {}
    seller_id = data.get('seller_id')
    if not seller_id:
        return jsonify({'success': False, 'error': 'seller_id is required'}), 400

    try:
        seller_id = int(seller_id)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'seller_id must be an integer'}), 400

    admin_id = session.get('user_id')
    conn = _db_module.get_db_connection()
    try:
        row = conn.execute(
            'SELECT id, delivered_at FROM seller_order_tracking WHERE order_id = ? AND seller_id = ?',
            (order_id, seller_id),
        ).fetchone()

        if not row:
            return jsonify({'success': False, 'error': 'No tracking record found for this order/seller'}), 404

        if row['delivered_at']:
            return jsonify({
                'success': True,
                'already_delivered': True,
                'delivered_at': str(row['delivered_at']),
                'message': f'Order {order_id} already marked delivered',
            })

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            'UPDATE seller_order_tracking SET delivered_at = ? WHERE order_id = ? AND seller_id = ?',
            (now_str, order_id, seller_id),
        )
        conn.commit()

        logger.info(
            "[MarkDelivered] admin=%s  order_id=%s  seller_id=%s  delivered_at=%s",
            admin_id, order_id, seller_id, now_str,
        )

        return jsonify({
            'success': True,
            'already_delivered': False,
            'delivered_at': now_str,
            'message': f'Order {order_id} marked as delivered',
        })

    except Exception:
        logger.exception("[MarkDelivered] Unexpected error  order_id=%s  seller_id=%s", order_id, seller_id)
        return jsonify({'success': False, 'error': 'Internal error. Check server logs.'}), 500
    finally:
        conn.close()


@admin_bp.route('/api/orders/<int:order_id>/confirm-payment', methods=['POST'])
@admin_required
def admin_confirm_payment(order_id):
    """
    Admin action: Manually confirm an order's payment and sync ledger status.

    Use when a Stripe webhook failed to deliver, or during local dev testing
    without a webhook forwarding CLI.  Idempotent: no-op if already paid.

    POST /admin/api/orders/<order_id>/confirm-payment
    Body (optional): {
        "payment_intent_id": "pi_xxx",   // stored on order if provided
        "payment_method_type": "card"    // defaults to "card"
    }
    """
    import database as _db_module
    from datetime import datetime

    data = request.get_json(silent=True) or {}
    payment_method_type = (data.get('payment_method_type') or 'card').lower()
    pi_id = (data.get('payment_intent_id') or '').strip()

    admin_id = session.get('user_id')
    conn = _db_module.get_db_connection()
    try:
        row = conn.execute(
            'SELECT id, payment_status, stripe_payment_intent_id FROM orders WHERE id = ?',
            (order_id,),
        ).fetchone()

        if not row:
            return jsonify({'success': False, 'error': 'Order not found'}), 404

        if row['payment_status'] == 'paid':
            # Payment already recorded but the ledger may still be stuck in
            # CHECKOUT_INITIATED (common when webhook didn't fire in local dev).
            # Always attempt the ledger sync — it's a no-op if already correct.
            conn.execute(
                """UPDATE orders_ledger
                      SET order_status = 'PAID_IN_ESCROW',
                          updated_at   = CURRENT_TIMESTAMP
                    WHERE order_id = ?
                      AND order_status IN ('CHECKOUT_INITIATED', 'PAYMENT_PENDING')""",
                (order_id,),
            )
            conn.commit()
            logger.info(
                "[AdminConfirmPayment] ledger sync (already paid)  order_id=%s", order_id
            )
            return jsonify({'success': True, 'already_paid': True,
                            'message': f'Order {order_id} is already marked paid (ledger synced)'})

        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        requires_clearance = 1 if payment_method_type == 'us_bank_account' else 0
        effective_pi = pi_id or row['stripe_payment_intent_id'] or ''

        conn.execute(
            """UPDATE orders
                  SET status                     = 'paid',
                      payment_status             = 'paid',
                      paid_at                    = ?,
                      payment_method_type        = ?,
                      requires_payment_clearance = ?,
                      stripe_payment_intent_id   = COALESCE(NULLIF(?, ''), stripe_payment_intent_id)
                WHERE id = ?""",
            (now_str, payment_method_type, requires_clearance, effective_pi, order_id),
        )
        # Sync ledger: CHECKOUT_INITIATED / PAYMENT_PENDING → PAID_IN_ESCROW
        conn.execute(
            """UPDATE orders_ledger
                  SET order_status = 'PAID_IN_ESCROW',
                      updated_at   = CURRENT_TIMESTAMP
                WHERE order_id = ?
                  AND order_status IN ('CHECKOUT_INITIATED', 'PAYMENT_PENDING')""",
            (order_id,),
        )
        conn.commit()

        logger.info(
            "[AdminConfirmPayment] admin=%s  order_id=%s  method=%s",
            admin_id, order_id, payment_method_type,
        )
        return jsonify({'success': True, 'already_paid': False,
                        'message': f'Order {order_id} marked as paid'})

    except Exception:
        logger.exception("[AdminConfirmPayment] Unexpected error  order_id=%s", order_id)
        return jsonify({'success': False, 'error': 'Internal error. Check server logs.'}), 500
    finally:
        conn.close()


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
