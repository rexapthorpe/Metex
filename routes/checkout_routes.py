from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from database import get_db_connection
from services.order_service import create_order
from utils.cart_utils import get_cart_items

# In cart_routes.py (or a new api_routes.py if you're organizing API calls separately)

checkout_bp = Blueprint('checkout', __name__)

@checkout_bp.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    conn = get_db_connection()

    if request.method == 'POST':
        bucket_id = request.form.get('bucket_id')
        quantity = int(request.form.get('quantity', 1))

        if bucket_id:
            graded_only = request.form.get('graded_only') == '1'
            any_grader = request.form.get('any_grader') == '1'
            pcgs = request.form.get('pcgs') == '1'
            ngc = request.form.get('ngc') == '1'

            grading_filter_applied = graded_only and (any_grader or pcgs or ngc)

            query = '''
                SELECT id, quantity, price_per_coin
                FROM listings
                WHERE category_id = ? AND active = 1 AND quantity > 0
            '''
            params = [bucket_id]

            if grading_filter_applied:
                query += ' AND graded = 1'
                if not any_grader:
                    services = []
                    if pcgs:
                        services.append("'PCGS'")
                    if ngc:
                        services.append("'NGC'")
                    if services:
                        query += f" AND grading_service IN ({', '.join(services)})"
                    else:
                        flash("No matching graded listings found.", "error")
                        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

            query += ' ORDER BY price_per_coin ASC'
            listings = conn.execute(query, params).fetchall()

            selected = []
            remaining = quantity

            for listing in listings:
                if remaining <= 0:
                    break
                take = min(listing['quantity'], remaining)
                selected.append({
                    'listing_id': listing['id'],
                    'quantity': take,
                    'price_each': listing['price_per_coin']
                })
                remaining -= take

            if remaining > 0:
                flash("Not enough inventory to fulfill your request.")
                return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

            session['checkout_items'] = selected
            return redirect(url_for('checkout.checkout'))

        else:
            shipping_address = request.form.get('shipping_address')

            cart_items = conn.execute('''
                SELECT cart.id, cart.quantity, cart.listing_id, listings.price_per_coin
                FROM cart
                JOIN listings ON cart.listing_id = listings.id
                WHERE cart.user_id = ?
            ''', (user_id,)).fetchall()

            cart_data = [{
                'listing_id': item['listing_id'],
                'quantity': item['quantity'],
                'price_each': item['price_per_coin']
            } for item in cart_items]

            order_id = create_order(user_id, cart_data, shipping_address)

            for item in cart_data:
                listing = conn.execute('SELECT quantity FROM listings WHERE id = ?', (item['listing_id'],)).fetchone()
                if listing:
                    new_quantity = listing['quantity'] - item['quantity']
                    if new_quantity <= 0:
                        conn.execute('UPDATE listings SET quantity = 0, active = 0 WHERE id = ?', (item['listing_id'],))
                    else:
                        conn.execute('UPDATE listings SET quantity = ? WHERE id = ?', (new_quantity, item['listing_id']))

            conn.execute('DELETE FROM cart WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()

            return redirect(url_for('checkout.order_confirmation', order_id=order_id))

    else:
        session_items = session.pop('checkout_items', None)

        if session_items:
            cart_data = session_items

            listings_info = []
            for item in cart_data:
                listing = conn.execute('''
                    SELECT listings.price_per_coin, listings.quantity,
                           categories.metal, categories.product_type,
                           categories.weight, categories.mint, categories.year,
                           categories.finish, categories.grade
                    FROM listings
                    JOIN categories ON listings.category_id = categories.id
                    WHERE listings.id = ?
                ''', (item['listing_id'],)).fetchone()

                if listing:
                    listing_dict = dict(listing)
                    listing_dict['quantity'] = item['quantity']
                    listing_dict['price_per_coin'] = item['price_each']
                    listings_info.append(listing_dict)

        else:
            raw_items = get_cart_items(conn)
            listings_info = [dict(row) for row in raw_items]

        conn.close()

        buckets = {}
        cart_total = 0

        for item in listings_info:
            bucket_key = f"{item['metal']}-{item['product_type']}-{item['weight']}-{item['mint']}-{item['year']}-{item['finish']}-{item['grade']}"

            if bucket_key not in buckets:
                buckets[bucket_key] = {
                    'category': {
                        'metal': item['metal'],
                        'product_type': item['product_type'],
                        'weight': item['weight'],
                        'mint': item['mint'],
                        'year': item['year'],
                        'finish': item['finish'],
                        'grade': item['grade']
                    },
                    'quantity': 0,
                    'total_qty': 0,
                    'total_price': 0,
                    'avg_price': 0
                }

                # ✅ Properly attach grading_preference
                if 'grading_preference' in item and item['grading_preference']:
                    buckets[bucket_key]['grading_preference'] = item['grading_preference']

            subtotal = item['price_per_coin'] * item['quantity']
            buckets[bucket_key]['quantity'] += item['quantity']
            buckets[bucket_key]['total_qty'] += item['quantity']
            buckets[bucket_key]['total_price'] += subtotal
            cart_total += subtotal

        for bucket in buckets.values():
            if bucket['quantity'] > 0:
                bucket['avg_price'] = round(bucket['total_price'] / bucket['quantity'], 2)

        import pprint
        pprint.pprint(buckets)

        return render_template(
            'checkout.html',
            buckets=buckets,
            cart_total=round(cart_total, 2),
            grading_preference=session.get('grading_preference')
        )


@checkout_bp.route('/checkout/confirm/<int:order_id>')
def order_confirmation(order_id):
    return render_template('order_confirmation.html', order_id=order_id)
