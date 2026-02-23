# core/blueprints/sell/routes.py
"""
Sell Routes - Main coordinator module.

Route handlers for selling items on the marketplace.
Heavy logic extracted to:
- listing_creation.py: POST handling for new listings
- accept_bid.py: Accepting bids on listings
"""

from flask import render_template, request, redirect, url_for, session, flash
from database import get_db_connection
from . import sell_bp
from routes.category_options import get_dropdown_options
from utils.auth_utils import frozen_check

# Import extracted modules to register their routes
from . import accept_bid  # noqa: F401 - registers accept_bid route


# --- Sell Route ---
@sell_bp.route('/sell', methods=['GET', 'POST'])
@frozen_check
def sell():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        # Delegate to extracted POST handler
        from .listing_creation import handle_sell_post
        return handle_sell_post()

    # GET request - extract URL parameters for pre-population
    prefill = {
        'metal': request.args.get('metal', ''),
        'product_line': request.args.get('product_line', ''),
        'product_type': request.args.get('product_type', ''),
        'weight': request.args.get('weight', ''),
        'purity': request.args.get('purity', ''),
        'mint': request.args.get('mint', ''),
        'year': request.args.get('year', ''),
        'finish': request.args.get('finish', ''),
        'grade': request.args.get('grade', ''),
        'condition_category': request.args.get('condition_category', ''),
        'series_variant': request.args.get('series_variant', '')
    }

    options = get_dropdown_options()

    return render_template(
        'sell.html',
        metals=options['metals'],
        product_lines=options['product_lines'],
        product_types=options['product_types'],
        weights=options['weights'],
        purities=options['purities'],
        mints=options['mints'],
        years=options['years'],
        finishes=options['finishes'],
        grades=options['grades'],
        packaging_types=options['packaging_types'],
        condition_categories=options['condition_categories'],
        series_variants=options['series_variants'],
        prefill=prefill
    )


@sell_bp.route('/upload_tracking/<int:order_id>', methods=['POST'])
def upload_tracking(order_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    tracking_number = request.form.get('tracking_number')
    carrier = request.form.get('carrier')

    if not tracking_number or not carrier:
        flash('Please provide tracking number and carrier.')
        return redirect(url_for('sell.sold_orders'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Insert or update tracking info (legacy table)
    cursor.execute('''
        INSERT INTO tracking (order_id, carrier, tracking_number, tracking_status)
        VALUES (?, ?, ?, 'In Transit')
        ON CONFLICT(order_id) DO UPDATE SET
            carrier=excluded.carrier,
            tracking_number=excluded.tracking_number,
            tracking_status='In Transit'
    ''', (order_id, carrier, tracking_number))

    # Also update seller_order_tracking (per-seller tracking for cancellation system)
    cursor.execute('''
        INSERT INTO seller_order_tracking (order_id, seller_id, tracking_number, carrier, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(order_id, seller_id) DO UPDATE SET
            tracking_number = excluded.tracking_number,
            carrier = excluded.carrier,
            updated_at = CURRENT_TIMESTAMP
    ''', (order_id, user_id, tracking_number, carrier))

    # Update order status to 'Awaiting Delivery'
    cursor.execute('''
        UPDATE orders
        SET status = 'Awaiting Delivery'
        WHERE id = ?
    ''', (order_id,))

    conn.commit()
    conn.close()

    # Auto-deny any pending cancellation request when tracking is added
    try:
        from database import get_db_connection as get_conn
        from services.notification_service import create_notification

        conn2 = get_conn()
        cancel_request = conn2.execute("""
            SELECT cr.*, o.buyer_id
            FROM cancellation_requests cr
            JOIN orders o ON cr.order_id = o.id
            WHERE cr.order_id = ? AND cr.status = 'pending'
        """, (order_id,)).fetchone()

        if cancel_request:
            conn2.execute("""
                UPDATE cancellation_requests
                SET status = 'denied', resolved_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (cancel_request['id'],))

            # Notify buyer
            create_notification(
                user_id=cancel_request['buyer_id'],
                notification_type='cancellation_denied',
                title='Cancel Request Denied',
                message=f'Your cancellation request for order #ORD-2026-{order_id:06d} was denied because the seller has shipped the order.',
                related_order_id=order_id
            )
            conn2.commit()
        conn2.close()
    except Exception as e:
        print(f"[CANCELLATION AUTO-DENY] Error: {e}")

    flash('Tracking number uploaded successfully!')
    return redirect(url_for('sell.sold_orders'))


@sell_bp.route('/sold_orders')
def sold_orders():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    conn = get_db_connection()

    # Fetch sold orders for this seller
    sold_orders = conn.execute('''
        SELECT orders.id, orders.quantity, orders.price, orders.status, orders.order_date,
            orders.shipping_address,
            categories.metal, categories.product_type,
            users.username AS buyer_username,
            (
                SELECT 1 FROM ratings
                WHERE ratings.order_id = orders.id AND ratings.rater_id = ?
            ) AS already_rated
        FROM orders
        JOIN listings ON orders.listing_id = listings.id
        JOIN categories ON listings.category_id = categories.id
        JOIN users ON orders.buyer_id = users.id
        WHERE listings.seller_id = ?
        ORDER BY orders.order_date DESC
    ''', (session['user_id'], session['user_id'])).fetchall()

    conn.close()

    return render_template('sold_orders.html', sold_orders=sold_orders)
