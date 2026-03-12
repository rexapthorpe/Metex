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
            SELECT buyer_id, category_id, quantity_requested, remaining_quantity, price_per_coin, status
            FROM bids WHERE id = ?
        ''', (bid_id,)).fetchone()

        if not bid or bid['status'].lower() not in ['open', 'pending', 'partially filled']:
            continue

        # PREVENT SELF-ACCEPTING: Skip bids from the current user
        if bid['buyer_id'] == seller_id:
            continue

        buyer_id = bid['buyer_id']
        category_id = bid['category_id']
        # Use remaining_quantity (not quantity_requested) for partially-filled bids
        max_qty = bid['remaining_quantity'] if bid['remaining_quantity'] is not None else bid['quantity_requested']
        price = bid['price_per_coin']

        qty_to_fulfill = min(accepted_qty, max_qty)

        # Check seller has sufficient active inventory to fulfill this quantity.
        # bids.category_id is actually the bucket_id; must join through categories.
        seller_listings = c.execute('''
            SELECT l.id, l.quantity
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE c.bucket_id = ? AND l.seller_id = ? AND l.active = 1
            ORDER BY l.quantity DESC
        ''', (category_id, seller_id)).fetchall()

        total_available = sum(l['quantity'] for l in seller_listings)
        if total_available < qty_to_fulfill:
            # Not enough inventory — skip this bid
            continue

        # Create an order using the canonical schema (no seller_id/category_id at order level;
        # seller identity is resolved via order_items → listings → seller_id)
        total_price = round(qty_to_fulfill * price, 2)
        c.execute('''
            INSERT INTO orders (buyer_id, total_price, status)
            VALUES (?, ?, 'Pending Shipment')
        ''', (buyer_id, total_price))

        order_id = c.lastrowid

        # Create order_items record so the order is properly linked to listings
        # Deduct inventory atomically from seller's listings (largest first)
        remaining_to_deduct = qty_to_fulfill
        for listing_row in seller_listings:
            if remaining_to_deduct <= 0:
                break
            take = min(listing_row['quantity'], remaining_to_deduct)
            result = c.execute('''
                UPDATE listings
                   SET quantity = quantity - ?,
                       active = CASE WHEN quantity - ? <= 0 THEN 0 ELSE active END
                 WHERE id = ? AND quantity >= ? AND active = 1
            ''', (take, take, listing_row['id'], take))
            if result.rowcount > 0:
                # Insert order_item for this listing
                c.execute('''
                    INSERT INTO order_items (order_id, listing_id, quantity, price_each)
                    VALUES (?, ?, ?, ?)
                ''', (order_id, listing_row['id'], take, price))
                remaining_to_deduct -= take

        # Update the bid — decrement remaining_quantity (canonical unfilled count)
        remaining = max_qty - qty_to_fulfill
        is_partial = remaining > 0
        if remaining == 0:
            c.execute(
                'UPDATE bids SET remaining_quantity = 0, active = 0, status = "filled" WHERE id = ?',
                (bid_id,)
            )
        else:
            c.execute(
                'UPDATE bids SET remaining_quantity = ?, status = "partially filled" WHERE id = ?',
                (remaining, bid_id)
            )

        # Build item description from category (bids.category_id is a bucket_id)
        category = c.execute('SELECT * FROM categories WHERE bucket_id = ? LIMIT 1', (category_id,)).fetchone()
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
