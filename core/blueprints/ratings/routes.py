"""
Ratings Routes

Rating routes: rate order.
"""

from flask import request, redirect, url_for, session, flash, render_template, jsonify
from database import get_db_connection
from services.notification_service import notify_rating_received, notify_rating_submitted

from . import ratings_bp


@ratings_bp.route('/rate/<int:order_id>', methods=['GET', 'POST'])
def rate_order(order_id):
    # Check if this is an AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json or 'application/json' in request.headers.get('Accept', '')

    # 1) Login required
    if 'user_id' not in session:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Login required'}), 401
        flash("Login to leave a review.", "error")
        return redirect(url_for('auth.login'))

    # 2) Pull the buyer_id & seller_id via the order_items → listings join
    conn = get_db_connection()
    order = conn.execute('''
        SELECT o.id,
               o.buyer_id,
               l.seller_id
        FROM orders AS o
        JOIN order_items AS oi ON oi.order_id = o.id
        JOIN listings    AS l  ON oi.listing_id = l.id
        WHERE o.id = ?
    ''', (order_id,)).fetchone()
    conn.close()

    # 3) Authorization: only buyer or seller may rate
    if not order or session['user_id'] not in (order['buyer_id'], order['seller_id']):
        if is_ajax:
            return jsonify({'success': False, 'message': 'You are not authorized to rate this order'}), 403
        flash("You are not authorized to rate this order.", "error")
        return redirect(url_for('account.account'))

    rater_id = session['user_id']
    ratee_id = order['seller_id'] if rater_id == order['buyer_id'] else order['buyer_id']

    if request.method == 'POST':
        # 4) Read form values
        rating  = int(request.form.get('rating', 0))
        comment = request.form.get('comment', '').strip()

        # Validate rating
        if rating < 1 or rating > 5:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Please select a rating between 1 and 5'}), 400
            flash("Please select a rating between 1 and 5.", "error")
            return redirect(url_for('account.account'))

        conn = get_db_connection()
        # 5) Prevent double-rating
        existing = conn.execute('''
            SELECT 1 FROM ratings
            WHERE order_id = ? AND rater_id = ?
        ''', (order_id, rater_id)).fetchone()
        if existing:
            conn.close()
            if is_ajax:
                return jsonify({'success': False, 'message': 'You have already rated this order'}), 400
            flash("You've already rated this order.", "error")
            return redirect(url_for('account.account'))

        # 6) Insert the new rating
        conn.execute('''
            INSERT INTO ratings (order_id, rater_id, ratee_id, rating, comment)
            VALUES (?, ?, ?, ?, ?)
        ''', (order_id, rater_id, ratee_id, rating, comment))
        conn.commit()

        # 7) Get usernames for notifications
        rater_info = conn.execute('SELECT username FROM users WHERE id = ?', (rater_id,)).fetchone()
        ratee_info = conn.execute('SELECT username FROM users WHERE id = ?', (ratee_id,)).fetchone()
        conn.close()

        rater_username = rater_info['username'] if rater_info else 'Someone'
        ratee_username = ratee_info['username'] if ratee_info else 'Someone'

        # 8) Send notifications
        # Notify the person who received the rating
        try:
            notify_rating_received(
                user_id=ratee_id,
                rater_username=rater_username,
                rating_value=rating,
                order_id=order_id
            )
        except Exception as e:
            print(f"[NOTIFICATION ERROR] Failed to send rating_received notification: {e}")

        # Notify the person who submitted the rating (confirmation)
        try:
            notify_rating_submitted(
                rater_id=rater_id,
                ratee_username=ratee_username,
                rating_value=rating,
                order_id=order_id
            )
        except Exception as e:
            print(f"[NOTIFICATION ERROR] Failed to send rating_submitted notification: {e}")

        if is_ajax:
            return jsonify({'success': True, 'message': 'Rating submitted successfully!'})

        flash("Review submitted!", "success")
        return redirect(url_for('account.account'))

    # 7) GET: render rate form
    return render_template('rate_user.html', order_id=order_id)
