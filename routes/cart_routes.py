# cart_routes.py

from flask import Blueprint, request, redirect, url_for, session, flash, jsonify, render_template
from database import get_db_connection
from utils.cart_utils import get_cart_items

cart_bp = Blueprint('cart', __name__, url_prefix='/cart')


@cart_bp.route('/remove_seller/<int:bucket_id>/<int:seller_id>', methods=['POST'])
def remove_seller_from_cart(bucket_id, seller_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1) Find how many items we’re about to lose
    result = cursor.execute('''
        SELECT SUM(cart.quantity) AS lost_qty
          FROM cart
          JOIN listings ON cart.listing_id = listings.id
         WHERE cart.user_id = ?
           AND listings.category_id = ?
           AND listings.seller_id = ?
    ''', (user_id, bucket_id, seller_id)).fetchone()
    lost_qty = result['lost_qty'] or 0

    # 2) Remove them
    cursor.execute('''
        DELETE FROM cart
         WHERE user_id = ?
           AND listing_id IN (
             SELECT id FROM listings
              WHERE category_id = ?
                AND seller_id = ?
           )
    ''', (user_id, bucket_id, seller_id))
    conn.commit()

    # 3) Refill from cheapest remaining sellers
    remaining = lost_qty
    replacements = cursor.execute('''
        SELECT id, quantity
          FROM listings
         WHERE category_id = ?
           AND active = 1
           AND seller_id != ?
         ORDER BY price_per_coin ASC
    ''', (bucket_id, seller_id)).fetchall()

    for listing in replacements:
        if remaining <= 0:
            break
        take = min(remaining, listing['quantity'])
        existing = cursor.execute(
            'SELECT quantity FROM cart WHERE user_id = ? AND listing_id = ?',
            (user_id, listing['id'])
        ).fetchone()
        if existing:
            cursor.execute(
                'UPDATE cart SET quantity = ? WHERE user_id = ? AND listing_id = ?',
                (existing['quantity'] + take, user_id, listing['id'])
            )
        else:
            cursor.execute(
                'INSERT INTO cart (user_id, listing_id, quantity) VALUES (?, ?, ?)',
                (user_id, listing['id'], take)
            )
        remaining -= take

    conn.commit()
    conn.close()

    # 4) Flash a message
    if lost_qty == 0:
        flash("Nothing to remove from that seller.", "warning")
    elif remaining > 0:
        flash(f"Removed seller. Only {lost_qty - remaining}/{lost_qty} items could be refilled.", "warning")
    else:
        flash("Seller removed and cart refilled with other listings.", "success")

    return redirect(url_for('cart.view_cart'))


@cart_bp.route('/remove_item_confirmation_modal/<int:bucket_id>')
def remove_item_confirmation_modal(bucket_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    return render_template(
        'modals/cart_remove_item_confirmation_modal.html',
        bucket_id=bucket_id
    )


@cart_bp.route('/api/bucket/<int:bucket_id>/cart_sellers')
def get_cart_sellers(bucket_id):
    conn = get_db_connection()
    cart_items = get_cart_items(conn)
    conn.close()

    filtered = [item for item in cart_items if item['category_id'] == bucket_id]

    sellers = {}
    for item in filtered:
        seller_id = item['seller_id']
        if seller_id not in sellers:
            sellers[seller_id] = {
                'seller_id': seller_id,
                'username': item['seller_username'],
                'price_per_coin': item['price_per_coin'],
                'quantity': 0,
                'rating': item['seller_rating'],
                'num_reviews': item['seller_rating_count']
            }
        sellers[seller_id]['quantity'] += item['quantity']

    return jsonify(list(sellers.values()))


@cart_bp.route('/api/bucket/<int:bucket_id>/price_breakdown')
def get_price_breakdown(bucket_id):
    conn = get_db_connection()
    all_items = get_cart_items(conn)
    bucket_items = [item for item in all_items if item['category_id'] == bucket_id]
    conn.close()

    return jsonify([
        {
            'seller_id': item['seller_id'],
            'username': item['seller_username'],
            'price_per_coin': float(item['price_per_coin']),
            'quantity': item['quantity'],
            'listing_id': item['listing_id']
        }
        for item in bucket_items
    ])


@cart_bp.route('/remove_item/<int:listing_id>', methods=['POST'])
def remove_item(listing_id):
    """
    Remove exactly one listing from the cart (DB or guest),
    supports both XHR (204) and normal form (flash + redirect).
    """
    user_id = session.get('user_id')

    # Guest cart
    if not user_id:
        guest_cart = session.get('guest_cart', [])
        updated = [item for item in guest_cart if item['listing_id'] != listing_id]
        session['guest_cart'] = updated
        session.modified = True

        flash("🗑️ Item removed from your cart.", "success")
        return redirect(url_for('buy.view_cart'))

    # Authenticated cart
    conn = get_db_connection()
    conn.execute(
        'DELETE FROM cart WHERE user_id = ? AND listing_id = ?',
        (user_id, listing_id)
    )
    conn.commit()
    conn.close()

    # If AJAX call, just return 204
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return '', 204

    flash("🗑️ Item removed from your cart.", "success")
    return redirect(url_for('cart.view_cart'))


@cart_bp.route('/remove_bucket/<int:bucket_id>', methods=['POST'])
def remove_bucket(bucket_id):
    """
    Delete every cart entry in this bucket (category),
    supports both DB and guest session.
    Always returns 204.
    """
    user_id = session.get('user_id')

    if not user_id:
        guest = session.get('guest_cart', [])
        filtered = [i for i in guest if i.get('category_id') != bucket_id]
        session['guest_cart'] = filtered
        session.modified = True
        return '', 204

    conn = get_db_connection()
    conn.execute('''
        DELETE FROM cart
         WHERE user_id = ?
           AND listing_id IN (
             SELECT id FROM listings WHERE category_id = ?
           )
    ''', (user_id, bucket_id))
    conn.commit()
    conn.close()
    return '', 204