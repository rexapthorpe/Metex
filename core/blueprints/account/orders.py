"""
Orders Routes

Routes for viewing orders: my_orders, order details, sold_orders.
"""

from flask import render_template, session, redirect, url_for, flash
from database import get_db_connection

from . import account_bp


@account_bp.route('/my_orders')
def my_orders():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    return redirect(url_for('account.account') + '#orders')


@account_bp.route('/order/<int:order_id>')
def view_order_details(order_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    conn = get_db_connection()

    order = conn.execute('''
        SELECT orders.id, orders.total_price, orders.status, orders.shipping_address, orders.created_at
        FROM orders
        WHERE orders.id = ? AND orders.buyer_id = ?
    ''', (order_id, session['user_id'])).fetchone()

    if not order:
        conn.close()
        flash('Order not found.')
        return redirect(url_for('account.my_orders'))

    order_items = conn.execute('''
        SELECT categories.metal, categories.product_type, order_items.quantity, order_items.price_each
        FROM order_items
        JOIN listings ON order_items.listing_id = listings.id
        JOIN categories ON listings.category_id = categories.id
        WHERE order_items.order_id = ?
    ''', (order_id,)).fetchall()

    tracking = conn.execute('''
        SELECT carrier, tracking_number, tracking_status
        FROM tracking
        WHERE order_id = ?
    ''', (order_id,)).fetchone()

    conn.close()

    return render_template('order_details.html', order=order, order_items=order_items, tracking=tracking)


@account_bp.route('/sold_orders')
def sold_orders():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    return redirect(url_for('account.account') + '#sold')
