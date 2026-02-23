# core/blueprints/sell/accept_bid.py
"""
Accept bid route for sell blueprint.

Extracted from routes.py during refactor - NO BEHAVIOR CHANGE.
"""

from flask import flash, redirect, url_for, session, request
from database import get_db_connection
from services.notification_service import notify_bid_filled
from . import sell_bp


@sell_bp.route('/accept_bid/<int:bucket_id>', methods=['POST'])
def accept_bid(bucket_id):
    if 'user_id' not in session:
        flash("Please log in to accept bids.", "warning")
        return redirect(url_for('auth.login'))

    seller_id = session['user_id']
    selected_bid_ids = request.form.getlist('selected_bids')

    if not selected_bid_ids:
        flash("No bids selected.", "warning")
        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    conn = get_db_connection()
    c = conn.cursor()

    total_accepted = 0

    # Collect notification data (will send after commit to avoid database locking)
    notifications_to_send = []

    for bid_id in selected_bid_ids:
        accepted_qty = request.form.get(f'quantity_{bid_id}')
        if not accepted_qty or int(accepted_qty) <= 0:
            continue

        accepted_qty = int(accepted_qty)

        bid = c.execute('''
            SELECT buyer_id, category_id, quantity_requested, price_per_coin, status
            FROM bids WHERE id = ?
        ''', (bid_id,)).fetchone()

        if not bid or bid['status'].lower() not in ['open', 'pending', 'partially filled']:
            continue

        # PREVENT SELF-ACCEPTING: Skip bids from the current user
        if bid['buyer_id'] == seller_id:
            continue

        buyer_id = bid['buyer_id']
        category_id = bid['category_id']
        max_qty = bid['quantity_requested']
        price = bid['price_per_coin']

        qty_to_fulfill = min(accepted_qty, max_qty)

        # Create an order directly
        c.execute('''
            INSERT INTO orders (buyer_id, seller_id, category_id, quantity, price_each, status)
            VALUES (?, ?, ?, ?, ?, 'pending_shipment')
        ''', (buyer_id, seller_id, category_id, qty_to_fulfill, price))

        order_id = c.lastrowid

        # Update the bid
        remaining = max_qty - qty_to_fulfill
        is_partial = remaining > 0
        if remaining == 0:
            c.execute('UPDATE bids SET quantity_requested = 0, active = 0, status = "filled" WHERE id = ?', (bid_id,))
        else:
            c.execute('UPDATE bids SET quantity_requested = ?, status = "partially filled" WHERE id = ?', (remaining, bid_id))

        # Build item description from category
        category = c.execute('SELECT * FROM categories WHERE id = ?', (category_id,)).fetchone()
        item_desc_parts = []
        if category:
            if category['metal']:
                item_desc_parts.append(category['metal'])
            if category['product_line']:
                item_desc_parts.append(category['product_line'])
            if category['weight']:
                item_desc_parts.append(category['weight'])
            if category['year']:
                item_desc_parts.append(category['year'])
        item_description = ' '.join(item_desc_parts) if item_desc_parts else 'Item'

        # Collect notification data (will send after commit)
        notifications_to_send.append({
            'buyer_id': buyer_id,
            'order_id': order_id,
            'bid_id': bid_id,
            'item_description': item_description,
            'quantity_filled': qty_to_fulfill,
            'price_per_unit': price,
            'total_amount': qty_to_fulfill * price,
            'is_partial': is_partial,
            'remaining_quantity': remaining
        })

        total_accepted += qty_to_fulfill

    conn.commit()
    conn.close()

    # Send notifications AFTER commit (avoids database locking)
    for notif_data in notifications_to_send:
        try:
            notify_bid_filled(**notif_data)
        except Exception as notify_error:
            print(f"[ERROR] Failed to notify buyer {notif_data['buyer_id']}: {notify_error}")

    if total_accepted > 0:
        flash(f"You accepted bids totaling {total_accepted} coin(s).", "success")
    else:
        flash("No bids were accepted due to missing quantities.", "warning")

    return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))
