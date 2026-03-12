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

    # 2) Get order and check authorization
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

    if request.method == 'POST':
        # 3) Read form values
        try:
            rating = int(request.form.get('rating', 0))
        except (ValueError, TypeError):
            rating = 0
        comment = request.form.get('comment', '').strip()

        # Validate rating is within 1–5
        if not (1 <= rating <= 5):
            conn.close()
            if is_ajax:
                return jsonify({'error': 'Rating must be between 1 and 5'}), 400
            flash("❌ Invalid rating value.", "error")
            return redirect(url_for('account.account'))

        # Limit comment length
        comment = comment[:2000]

        # 4) Determine ratee_id
        if is_seller:
            # Sellers always rate the buyer
            ratee_id = order['buyer_id']
        else:
            # Buyers rate a specific seller — ratee_id comes from the form
            try:
                ratee_id = int(request.form.get('ratee_id', 0))
            except (ValueError, TypeError):
                ratee_id = 0

            if not ratee_id:
                conn.close()
                if is_ajax:
                    return jsonify({'error': 'Missing seller to rate'}), 400
                flash("Error: could not determine who to rate.", "error")
                return redirect(url_for('account.account'))

            # Security: verify ratee_id is actually a seller in this order
            valid_seller = conn.execute('''
                SELECT 1 FROM order_items oi
                JOIN listings l ON oi.listing_id = l.id
                WHERE oi.order_id = ? AND l.seller_id = ?
                LIMIT 1
            ''', (order_id, ratee_id)).fetchone()

            if not valid_seller:
                conn.close()
                if is_ajax:
                    return jsonify({'error': 'Invalid seller for this order'}), 400
                flash("Error: invalid seller.", "error")
                return redirect(url_for('account.account'))

        # 5) Prevent double-rating the same person in the same order
        existing = conn.execute('''
            SELECT 1 FROM ratings
            WHERE order_id = ? AND rater_id = ? AND ratee_id = ?
        ''', (order_id, user_id, ratee_id)).fetchone()
        if existing:
            conn.close()
            if is_ajax:
                return jsonify({'error': 'Already rated this user for this order'}), 400
            flash("❌ You've already rated this user for this order.", "error")
            return redirect(url_for('account.account'))

        # 6) Insert the new rating
        conn.execute('''
            INSERT INTO ratings (order_id, rater_id, ratee_id, rating, comment)
            VALUES (?, ?, ?, ?, ?)
        ''', (order_id, user_id, ratee_id, rating, comment))
        conn.commit()
        conn.close()

        if is_ajax:
            return jsonify({'success': True})
        flash("✅ Review submitted!", "success")
        return redirect(url_for('account.account'))

    conn.close()
    # GET: render legacy rate form
    return render_template('rate_user.html', order_id=order_id)
