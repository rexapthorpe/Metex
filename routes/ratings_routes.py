# routes/ratings_routes.py

from flask import Blueprint, request, redirect, url_for, session, flash, render_template
from database import get_db_connection

ratings_bp = Blueprint('ratings', __name__)

@ratings_bp.route('/rate/<int:order_id>', methods=['GET', 'POST'])
def rate_order(order_id):
    # 1) Login required
    if 'user_id' not in session:
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
        flash("❌ You are not authorized to rate this order.", "error")
        return redirect(url_for('account.account'))

    rater_id = session['user_id']
    ratee_id = order['seller_id'] if rater_id == order['buyer_id'] else order['buyer_id']

    if request.method == 'POST':
        # 4) Read form values
        rating  = int(request.form.get('rating', 0))
        comment = request.form.get('comment', '').strip()

        conn = get_db_connection()
        # 5) Prevent double‐rating
        existing = conn.execute('''
            SELECT 1 FROM ratings
            WHERE order_id = ? AND rater_id = ?
        ''', (order_id, rater_id)).fetchone()
        if existing:
            conn.close()
            flash("❌ You’ve already rated this order.", "error")
            return redirect(url_for('account.account'))

        # 6) Insert the new rating
        conn.execute('''
            INSERT INTO ratings (order_id, rater_id, ratee_id, rating, comment)
            VALUES (?, ?, ?, ?, ?)
        ''', (order_id, rater_id, ratee_id, rating, comment))
        conn.commit()
        conn.close()

        flash("✅ Review submitted!", "success")
        return redirect(url_for('account.account'))

    # 7) GET: render rate form
    return render_template('rate_user.html', order_id=order_id)