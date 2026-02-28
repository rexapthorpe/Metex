"""
Order Cancellation Routes
Handles buyer cancellation requests and seller responses
"""

from flask import Blueprint, jsonify, request, session
from database import get_db_connection
from datetime import datetime, timedelta
from services.notification_service import create_notification, notify_cancel_request_submitted

cancellation_bp = Blueprint('cancellation', __name__)

# Constants
CANCELLATION_WINDOW_DAYS = 2  # 2-day window for cancellation requests

# Cancellation reasons (matching the UI reference)
CANCELLATION_REASONS = [
    "Changed my mind",
    "Found a better deal elsewhere",
    "Ordered by mistake",
    "Order is taking too long",
    "Seller is unresponsive",
    "Item no longer needed",
    "Other reason"
]


def get_order_sellers(conn, order_id):
    """Get all unique sellers for an order"""
    sellers = conn.execute("""
        SELECT DISTINCT l.seller_id
        FROM order_items oi
        JOIN listings l ON oi.listing_id = l.id
        WHERE oi.order_id = ?
    """, (order_id,)).fetchall()
    return [s['seller_id'] for s in sellers]


def has_any_tracking(conn, order_id):
    """Check if any seller has added tracking for this order"""
    # Check seller_order_tracking table (per-seller tracking)
    tracking = conn.execute("""
        SELECT 1 FROM seller_order_tracking
        WHERE order_id = ? AND tracking_number IS NOT NULL AND tracking_number != ''
        LIMIT 1
    """, (order_id,)).fetchone()

    if tracking:
        return True

    # Also check legacy tracking in orders table
    order = conn.execute("""
        SELECT tracking_number FROM orders WHERE id = ?
    """, (order_id,)).fetchone()

    return order and order['tracking_number']


def is_within_cancellation_window(order_created_at):
    """Check if order is within the 2-day cancellation window"""
    if isinstance(order_created_at, str):
        order_time = datetime.fromisoformat(order_created_at)
    else:
        order_time = order_created_at

    cutoff = order_time + timedelta(days=CANCELLATION_WINDOW_DAYS)
    return datetime.now() < cutoff


def check_and_auto_deny_expired_requests():
    """Auto-deny any pending requests that have passed the 2-day window"""
    conn = get_db_connection()

    # Find pending requests where the order is past the cancellation window
    expired_requests = conn.execute("""
        SELECT cr.id, cr.order_id, cr.buyer_id
        FROM cancellation_requests cr
        JOIN orders o ON cr.order_id = o.id
        WHERE cr.status = 'pending'
        AND datetime(o.created_at, '+' || ? || ' days') < datetime('now')
    """, (CANCELLATION_WINDOW_DAYS,)).fetchall()

    for req in expired_requests:
        # Auto-deny the request
        conn.execute("""
            UPDATE cancellation_requests
            SET status = 'denied', resolved_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (req['id'],))

        # Notify buyer
        create_notification(
            user_id=req['buyer_id'],
            notification_type='cancellation_denied',
            title='Cancel Request Denied',
            message='Your cancellation request has been automatically denied because the 2-day response window has expired.',
            related_order_id=req['order_id']
        )

    conn.commit()
    conn.close()


def restore_inventory(conn, order_id):
    """Restore inventory for all items in a canceled order"""
    # Get all order items with their listing info
    order_items = conn.execute("""
        SELECT oi.listing_id, oi.quantity
        FROM order_items oi
        WHERE oi.order_id = ?
    """, (order_id,)).fetchall()

    for item in order_items:
        # Restore quantity to listing
        conn.execute("""
            UPDATE listings
            SET quantity = quantity + ?, active = 1
            WHERE id = ?
        """, (item['quantity'], item['listing_id']))

    return len(order_items)


def update_cancellation_stats(conn, order_id, buyer_id, seller_ids, order_total, is_approved):
    """Update cancellation statistics for users"""
    now = datetime.now().isoformat()

    # Update buyer stats
    if is_approved:
        conn.execute("""
            INSERT INTO user_cancellation_stats (user_id, canceled_orders_as_buyer, canceled_volume_as_buyer, last_updated)
            VALUES (?, 1, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                canceled_orders_as_buyer = canceled_orders_as_buyer + 1,
                canceled_volume_as_buyer = canceled_volume_as_buyer + ?,
                last_updated = ?
        """, (buyer_id, order_total, now, order_total, now))

        # Update each seller's stats
        for seller_id in seller_ids:
            # Get seller's portion of the order
            seller_portion = conn.execute("""
                SELECT SUM(oi.quantity * oi.price_each) as total
                FROM order_items oi
                JOIN listings l ON oi.listing_id = l.id
                WHERE oi.order_id = ? AND l.seller_id = ?
            """, (order_id, seller_id)).fetchone()

            seller_total = seller_portion['total'] if seller_portion else 0

            conn.execute("""
                INSERT INTO user_cancellation_stats (user_id, canceled_orders_as_seller, canceled_volume_as_seller, last_updated)
                VALUES (?, 1, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    canceled_orders_as_seller = canceled_orders_as_seller + 1,
                    canceled_volume_as_seller = canceled_volume_as_seller + ?,
                    last_updated = ?
            """, (seller_id, seller_total, now, seller_total, now))
    else:
        # Denied cancellation
        conn.execute("""
            INSERT INTO user_cancellation_stats (user_id, denied_cancellations, last_updated)
            VALUES (?, 1, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                denied_cancellations = denied_cancellations + 1,
                last_updated = ?
        """, (buyer_id, now, now))


@cancellation_bp.route('/api/cancellation/reasons', methods=['GET'])
def get_cancellation_reasons():
    """Get available cancellation reasons"""
    return jsonify({
        'success': True,
        'reasons': CANCELLATION_REASONS
    })


@cancellation_bp.route('/api/orders/<int:order_id>/cancellation/status', methods=['GET'])
def get_cancellation_status(order_id):
    """Get the cancellation status for an order"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    # Verify user is buyer or seller for this order
    order = conn.execute("""
        SELECT o.id, o.buyer_id, o.created_at, o.status
        FROM orders o
        WHERE o.id = ?
    """, (order_id,)).fetchone()

    if not order:
        conn.close()
        return jsonify({'success': False, 'error': 'Order not found'}), 404

    seller_ids = get_order_sellers(conn, order_id)

    if order['buyer_id'] != user_id and user_id not in seller_ids:
        conn.close()
        return jsonify({'success': False, 'error': 'Not authorized'}), 403

    # Check for existing cancellation request
    cancel_request = conn.execute("""
        SELECT * FROM cancellation_requests WHERE order_id = ?
    """, (order_id,)).fetchone()

    # Check cancellation eligibility
    can_cancel = (
        order['buyer_id'] == user_id and
        cancel_request is None and
        is_within_cancellation_window(order['created_at']) and
        not has_any_tracking(conn, order_id) and
        order['status'] not in ('Canceled', 'Cancelled', 'Complete', 'Delivered', 'Refunded')
    )

    result = {
        'success': True,
        'can_cancel': can_cancel,
        'is_buyer': order['buyer_id'] == user_id,
        'is_seller': user_id in seller_ids,
        'order_status': order['status'],
        'has_tracking': has_any_tracking(conn, order_id),
        'within_window': is_within_cancellation_window(order['created_at'])
    }

    if cancel_request:
        # Get seller responses
        responses = conn.execute("""
            SELECT csr.seller_id, csr.response, csr.responded_at, u.username
            FROM cancellation_seller_responses csr
            JOIN users u ON csr.seller_id = u.id
            WHERE csr.request_id = ?
        """, (cancel_request['id'],)).fetchall()

        result['cancellation_request'] = {
            'id': cancel_request['id'],
            'status': cancel_request['status'],
            'reason': cancel_request['reason'],
            'additional_details': cancel_request['additional_details'],
            'created_at': cancel_request['created_at'],
            'resolved_at': cancel_request['resolved_at'],
            'seller_responses': [dict(r) for r in responses],
            'total_sellers': len(seller_ids),
            'approved_count': sum(1 for r in responses if r['response'] == 'approved'),
            'denied_count': sum(1 for r in responses if r['response'] == 'denied'),
            'pending_count': len(seller_ids) - len([r for r in responses if r['response']])
        }

    conn.close()
    return jsonify(result)


@cancellation_bp.route('/api/orders/<int:order_id>/cancel', methods=['POST'])
def request_cancellation(order_id):
    """Buyer requests to cancel an order"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        # Get order and verify buyer
        order = conn.execute("""
            SELECT o.id, o.buyer_id, o.created_at, o.status, o.total_price
            FROM orders o
            WHERE o.id = ? AND o.buyer_id = ?
        """, (order_id, user_id)).fetchone()

        if not order:
            conn.close()
            return jsonify({'success': False, 'error': 'Order not found or not authorized'}), 404

        # Check if order is in a cancelable state
        if order['status'] in ('Canceled', 'Cancelled', 'Complete', 'Delivered', 'Refunded'):
            conn.close()
            return jsonify({'success': False, 'error': 'This order cannot be canceled'}), 400

        # Check for existing cancellation request
        existing = conn.execute("""
            SELECT * FROM cancellation_requests WHERE order_id = ?
        """, (order_id,)).fetchone()

        if existing:
            conn.close()
            return jsonify({'success': False, 'error': 'A cancellation request already exists for this order'}), 400

        # Check 2-day window
        if not is_within_cancellation_window(order['created_at']):
            conn.close()
            return jsonify({'success': False, 'error': 'Cancellation window has expired (2 days from order)'}), 400

        # Check tracking
        if has_any_tracking(conn, order_id):
            conn.close()
            return jsonify({'success': False, 'error': 'Cannot cancel - a seller has already shipped'}), 400

        # Get request data
        data = request.get_json()
        reason = data.get('reason', '').strip()
        additional_details = data.get('additional_details', '').strip()

        if not reason:
            conn.close()
            return jsonify({'success': False, 'error': 'Cancellation reason is required'}), 400

        if reason not in CANCELLATION_REASONS:
            conn.close()
            return jsonify({'success': False, 'error': 'Invalid cancellation reason'}), 400

        # Create cancellation request
        cursor = conn.execute("""
            INSERT INTO cancellation_requests (order_id, buyer_id, reason, additional_details)
            VALUES (?, ?, ?, ?)
        """, (order_id, user_id, reason, additional_details))

        request_id = cursor.lastrowid

        # Get all sellers for this order
        seller_ids = get_order_sellers(conn, order_id)

        # Create response records for each seller (one vote per seller)
        for seller_id in seller_ids:
            conn.execute("""
                INSERT INTO cancellation_seller_responses (request_id, seller_id)
                VALUES (?, ?)
            """, (request_id, seller_id))

            # Notify each seller immediately
            create_notification(
                user_id=seller_id,
                notification_type='cancellation_request',
                title='Buyer Requested Order Cancellation',
                message=f'A buyer has requested to cancel order #ORD-2026-{order_id:06d}. Please review and respond in your Sold Items tab.',
                related_order_id=order_id,
                metadata={'reason': reason, 'buyer_id': user_id}
            )

        conn.commit()

        # Get item description for the notification
        order_item = conn.execute("""
            SELECT c.metal, c.product_line, c.weight, c.year
            FROM order_items oi
            JOIN listings l ON oi.listing_id = l.id
            JOIN categories c ON l.category_id = c.id
            WHERE oi.order_id = ?
            LIMIT 1
        """, (order_id,)).fetchone()

        item_desc_parts = []
        if order_item:
            if order_item['metal']:
                item_desc_parts.append(order_item['metal'])
            if order_item['product_line']:
                item_desc_parts.append(order_item['product_line'])
            if order_item['weight']:
                item_desc_parts.append(order_item['weight'])
        item_description = ' '.join(item_desc_parts) if item_desc_parts else f'Order #{order_id}'

        conn.close()

        # Notify the buyer that their cancellation request was submitted
        try:
            notify_cancel_request_submitted(
                requester_id=user_id,
                order_id=order_id,
                item_description=item_description
            )
        except Exception as e:
            print(f"[NOTIFICATION ERROR] Failed to send cancel_request_submitted notification: {e}")

        return jsonify({
            'success': True,
            'message': 'Cancellation request submitted. All sellers must approve for the order to be canceled.',
            'request_id': request_id,
            'seller_count': len(seller_ids)
        })

    except Exception as e:
        conn.close()
        print(f"[CANCELLATION ERROR] {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@cancellation_bp.route('/api/orders/<int:order_id>/cancel/respond', methods=['POST'])
def respond_to_cancellation(order_id):
    """Seller responds to a cancellation request"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        # Get the cancellation request
        cancel_request = conn.execute("""
            SELECT cr.*, o.buyer_id, o.total_price
            FROM cancellation_requests cr
            JOIN orders o ON cr.order_id = o.id
            WHERE cr.order_id = ? AND cr.status = 'pending'
        """, (order_id,)).fetchone()

        if not cancel_request:
            conn.close()
            return jsonify({'success': False, 'error': 'No pending cancellation request found'}), 404

        # Verify user is a seller for this order
        seller_ids = get_order_sellers(conn, order_id)

        if user_id not in seller_ids:
            conn.close()
            return jsonify({'success': False, 'error': 'Not authorized - you are not a seller for this order'}), 403

        # Get response data
        data = request.get_json()
        response = data.get('response', '').strip().lower()

        if response not in ('approved', 'denied'):
            conn.close()
            return jsonify({'success': False, 'error': 'Response must be "approved" or "denied"'}), 400

        # Check if seller already responded
        existing_response = conn.execute("""
            SELECT * FROM cancellation_seller_responses
            WHERE request_id = ? AND seller_id = ? AND response IS NOT NULL
        """, (cancel_request['id'], user_id)).fetchone()

        if existing_response:
            conn.close()
            return jsonify({'success': False, 'error': 'You have already responded to this request'}), 400

        # Record the response
        conn.execute("""
            UPDATE cancellation_seller_responses
            SET response = ?, responded_at = CURRENT_TIMESTAMP
            WHERE request_id = ? AND seller_id = ?
        """, (response, cancel_request['id'], user_id))

        # If denied, immediately deny the entire request
        if response == 'denied':
            conn.execute("""
                UPDATE cancellation_requests
                SET status = 'denied', resolved_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (cancel_request['id'],))

            # Update stats
            update_cancellation_stats(conn, order_id, cancel_request['buyer_id'], seller_ids,
                                     cancel_request['total_price'], is_approved=False)

            # Notify buyer of denial
            create_notification(
                user_id=cancel_request['buyer_id'],
                notification_type='cancellation_denied',
                title='Cancel Request Denied',
                message=f'Your cancellation request for order #ORD-2026-{order_id:06d} has been denied by a seller.',
                related_order_id=order_id
            )

            conn.commit()
            conn.close()

            return jsonify({
                'success': True,
                'message': 'Cancellation request denied.',
                'final_status': 'denied'
            })

        # If approved, check if all sellers have approved
        all_responses = conn.execute("""
            SELECT seller_id, response FROM cancellation_seller_responses
            WHERE request_id = ?
        """, (cancel_request['id'],)).fetchall()

        # Guard: must have response rows for all expected sellers (prevents vacuous-truth approval)
        all_approved = (
            len(all_responses) >= len(seller_ids) > 0 and
            all(r['response'] == 'approved' for r in all_responses)
        )
        all_responded = (
            len(all_responses) >= len(seller_ids) > 0 and
            all(r['response'] is not None for r in all_responses)
        )

        if all_approved and all_responded:
            # All sellers approved - cancel the order
            conn.execute("""
                UPDATE cancellation_requests
                SET status = 'approved', resolved_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (cancel_request['id'],))

            conn.execute("""
                UPDATE orders
                SET status = 'Canceled', canceled_at = CURRENT_TIMESTAMP, cancellation_reason = ?
                WHERE id = ?
            """, (cancel_request['reason'], order_id))

            # Restore inventory
            items_restored = restore_inventory(conn, order_id)

            # Update stats
            update_cancellation_stats(conn, order_id, cancel_request['buyer_id'], seller_ids,
                                     cancel_request['total_price'], is_approved=True)

            # Notify buyer of success
            create_notification(
                user_id=cancel_request['buyer_id'],
                notification_type='cancellation_approved',
                title='Order Canceled Successfully',
                message=f'Order #ORD-2026-{order_id:06d} has been successfully canceled. You will receive a full refund.',
                related_order_id=order_id
            )

            # Notify all sellers of success
            for seller_id in seller_ids:
                create_notification(
                    user_id=seller_id,
                    notification_type='cancellation_approved',
                    title='Order Canceled',
                    message=f'Order #ORD-2026-{order_id:06d} has been canceled. Inventory has been returned to your available listings.',
                    related_order_id=order_id
                )

            conn.commit()
            conn.close()

            return jsonify({
                'success': True,
                'message': 'All sellers approved. Order has been canceled and inventory restored.',
                'final_status': 'approved',
                'items_restored': items_restored
            })

        conn.commit()
        conn.close()

        # Still waiting for other sellers
        approved_count = sum(1 for r in all_responses if r['response'] == 'approved')
        pending_count = sum(1 for r in all_responses if r['response'] is None)

        return jsonify({
            'success': True,
            'message': f'Response recorded. Waiting for {pending_count} more seller(s) to respond.',
            'final_status': 'pending',
            'approved_count': approved_count,
            'pending_count': pending_count
        })

    except Exception as e:
        conn.close()
        print(f"[CANCELLATION ERROR] {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@cancellation_bp.route('/api/orders/<int:order_id>/cancel/auto-deny-tracking', methods=['POST'])
def auto_deny_on_tracking(order_id):
    """Called when a seller adds tracking - auto-denies any pending cancellation"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        # Check for pending cancellation request
        cancel_request = conn.execute("""
            SELECT cr.*, o.buyer_id
            FROM cancellation_requests cr
            JOIN orders o ON cr.order_id = o.id
            WHERE cr.order_id = ? AND cr.status = 'pending'
        """, (order_id,)).fetchone()

        if not cancel_request:
            conn.close()
            return jsonify({'success': True, 'message': 'No pending cancellation to deny'})

        seller_ids = get_order_sellers(conn, order_id)

        # Verify the user is a seller
        if user_id not in seller_ids:
            conn.close()
            return jsonify({'success': False, 'error': 'Not authorized'}), 403

        # Auto-deny the request
        conn.execute("""
            UPDATE cancellation_requests
            SET status = 'denied', resolved_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (cancel_request['id'],))

        # Update stats
        update_cancellation_stats(conn, order_id, cancel_request['buyer_id'], seller_ids,
                                 0, is_approved=False)

        # Notify buyer
        create_notification(
            user_id=cancel_request['buyer_id'],
            notification_type='cancellation_denied',
            title='Cancel Request Denied',
            message=f'Your cancellation request for order #ORD-2026-{order_id:06d} was denied because the seller has shipped the order.',
            related_order_id=order_id
        )

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Pending cancellation request has been auto-denied due to tracking number entry.'
        })

    except Exception as e:
        conn.close()
        print(f"[CANCELLATION ERROR] {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@cancellation_bp.route('/api/seller/<int:seller_id>/cancellation-stats', methods=['GET'])
def get_seller_cancellation_stats(seller_id):
    """Get cancellation statistics for a seller (for analytics)"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    conn = get_db_connection()

    stats = conn.execute("""
        SELECT * FROM user_cancellation_stats WHERE user_id = ?
    """, (seller_id,)).fetchone()

    conn.close()

    if not stats:
        return jsonify({
            'success': True,
            'stats': {
                'canceled_orders_as_buyer': 0,
                'canceled_volume_as_buyer': 0,
                'canceled_orders_as_seller': 0,
                'canceled_volume_as_seller': 0,
                'denied_cancellations': 0
            }
        })

    return jsonify({
        'success': True,
        'stats': dict(stats)
    })
