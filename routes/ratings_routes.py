# routes/ratings_routes.py

from flask import Blueprint, request, redirect, url_for, session, flash, render_template, jsonify
from database import get_db_connection

ratings_bp = Blueprint('ratings', __name__)

@ratings_bp.route('/rate/<int:order_id>', methods=['GET', 'POST'])
def rate_order(order_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    # 1) Login required
    if 'user_id' not in session:
        if is_ajax:
            return jsonify({'error': 'Login required'}), 401
        flash("Login to leave a review.", "error")
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    conn = get_db_connection()

    # 2) Get order and check authorization properly
    order = conn.execute('SELECT id, buyer_id FROM orders WHERE id = ?', (order_id,)).fetchone()

    is_buyer = order and order['buyer_id'] == user_id

    # Check if user is a seller on any item in this order
    seller_row = conn.execute('''
        SELECT l.seller_id FROM order_items oi
        JOIN listings l ON oi.listing_id = l.id
        WHERE oi.order_id = ? AND l.seller_id = ?
        LIMIT 1
    ''', (order_id, user_id)).fetchone()
    is_seller = seller_row is not None

    if not order or (not is_buyer and not is_seller):
        conn.close()
        if is_ajax:
            return jsonify({'error': 'Unauthorized'}), 403
        flash("❌ You are not authorized to rate this order.", "error")
        return redirect(url_for('account.account'))

    rater_id = user_id
    # Sellers rate the buyer; buyers rate the seller
    if is_seller:
        ratee_id = order['buyer_id']
    else:
        # Buyer rating: find first seller in this order
        first_seller = conn.execute('''
            SELECT DISTINCT l.seller_id FROM order_items oi
            JOIN listings l ON oi.listing_id = l.id
            WHERE oi.order_id = ? LIMIT 1
        ''', (order_id,)).fetchone()
        ratee_id = first_seller['seller_id'] if first_seller else None

    if request.method == 'POST':
        # 3) Read form values
        rating  = int(request.form.get('rating', 0))
        comment = request.form.get('comment', '').strip()

        if not ratee_id:
            conn.close()
            if is_ajax:
                return jsonify({'error': 'Could not determine who to rate'}), 400
            flash("Error: could not determine who to rate.", "error")
            return redirect(url_for('account.account'))

        # 4) Prevent double-rating
        existing = conn.execute('''
            SELECT 1 FROM ratings
            WHERE order_id = ? AND rater_id = ?
        ''', (order_id, rater_id)).fetchone()
        if existing:
            conn.close()
            if is_ajax:
                return jsonify({'error': 'Already rated'}), 400
            flash("❌ You've already rated this order.", "error")
            return redirect(url_for('account.account'))

        # 5) Insert the new rating
        conn.execute('''
            INSERT INTO ratings (order_id, rater_id, ratee_id, rating, comment)
            VALUES (?, ?, ?, ?, ?)
        ''', (order_id, rater_id, ratee_id, rating, comment))
        conn.commit()
        conn.close()

        if is_ajax:
            return jsonify({'success': True})
        flash("✅ Review submitted!", "success")
        return redirect(url_for('account.account'))

    conn.close()
    # GET: render rate form
    return render_template('rate_user.html', order_id=order_id)