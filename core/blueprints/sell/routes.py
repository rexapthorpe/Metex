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
import sqlite3

# Import extracted modules to register their routes
from . import accept_bid  # noqa: F401 - registers accept_bid route


# --- Sell Route ---
@sell_bp.route('/sell', methods=['GET', 'POST'])
@frozen_check
def sell():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        # Safety guard: if edit_listing_id is present in the form, this POST
        # should have gone to /listings/edit_listing/<id> — forward it there
        # to prevent accidental duplicate listing creation.
        edit_listing_id_str = request.form.get('edit_listing_id', '').strip()
        if edit_listing_id_str and edit_listing_id_str.isdigit():
            print(f"[SELL POST] edit_listing_id={edit_listing_id_str} detected — forwarding to edit_listing handler")
            from core.blueprints.listings.routes import edit_listing
            return edit_listing(int(edit_listing_id_str))

        # Delegate to extracted POST handler
        from .listing_creation import handle_sell_post
        return handle_sell_post()

    # GET request - check for edit mode first
    edit_listing_id = request.args.get('edit_listing_id', type=int)
    edit_prefill = None

    if edit_listing_id:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            listing = conn.execute(
                '''
                SELECT l.id AS listing_id, l.quantity, l.price_per_coin, l.pricing_mode,
                       l.spot_premium, l.floor_price, l.pricing_metal, l.graded,
                       l.grading_service, l.name AS listing_title,
                       l.description AS listing_description, l.is_isolated,
                       l.isolated_type, l.issue_number, l.issue_total,
                       l.edition_number, l.edition_total, l.packaging_type,
                       l.packaging_notes, l.cert_number, l.condition_notes,
                       l.actual_year,
                       c.metal, c.product_line, c.product_type, c.purity, c.weight,
                       c.mint, c.year, c.finish, c.grade, c.series_variant,
                       c.condition_category, c.coin_series
                FROM listings l
                JOIN categories c ON l.category_id = c.id
                WHERE l.id = ? AND l.seller_id = ?
                ''',
                (edit_listing_id, session['user_id'])
            ).fetchone()

            photos = conn.execute(
                'SELECT id, file_path FROM listing_photos WHERE listing_id = ? ORDER BY id',
                (edit_listing_id,)
            ).fetchall()

        if listing:
            edit_prefill = {k: listing[k] for k in listing.keys()}
            edit_prefill['existing_photos'] = [
                {'id': p['id'], 'url': '/static/' + p['file_path']} for p in photos
                if p['file_path'] is not None
            ]

            # For set listings, fetch each item with its first photo for display
            if edit_prefill.get('isolated_type') == 'set':
                set_items_raw = conn.execute(
                    '''
                    SELECT lsi.id, lsi.position_index, lsi.metal, lsi.product_line,
                           lsi.product_type, lsi.weight, lsi.purity, lsi.mint,
                           lsi.year, lsi.finish, lsi.grade, lsi.item_title,
                           lsi.packaging_type, lsi.packaging_notes, lsi.condition_notes,
                           lsi.edition_number, lsi.edition_total, lsi.quantity,
                           (SELECT lsip.file_path FROM listing_set_item_photos lsip
                            WHERE lsip.set_item_id = lsi.id AND lsip.position_index = 1
                            LIMIT 1) AS first_photo_path
                    FROM listing_set_items lsi
                    WHERE lsi.listing_id = ?
                    ORDER BY lsi.position_index ASC
                    ''',
                    (edit_listing_id,)
                ).fetchall()
                edit_prefill['set_items'] = [dict(row) for row in set_items_raw]
        else:
            edit_listing_id = None  # not found or unauthorized

    # Fallback URL-param prefill (used when coming from bucket page)
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
        prefill=edit_prefill if edit_prefill is not None else prefill,
        edit_listing_id=edit_listing_id
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
    existing_tracking = cursor.execute(
        'SELECT id FROM tracking WHERE order_id = ?', (order_id,)
    ).fetchone()
    if existing_tracking:
        cursor.execute('''
            UPDATE tracking SET carrier = ?, tracking_number = ? WHERE order_id = ?
        ''', (carrier, tracking_number, order_id))
    else:
        cursor.execute('''
            INSERT INTO tracking (order_id, carrier, tracking_number) VALUES (?, ?, ?)
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
