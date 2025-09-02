# routes/sell_routes.py

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_db_connection
import sqlite3




sell_bp = Blueprint('sell', __name__)

# --- Global Cache for Dropdowns ---
dropdown_options = {
    'metals': [],
    'product_lines': [],  # ✅ MUST exist here
    'product_types': [],
    'weights': [],
    'mints': [],
    'years': [],
    'finishes': [],
    'grades': []
}


def load_dropdown_options():
    conn = get_db_connection()

    dropdown_options['product_lines'] = [
    row['product_line'] for row in conn.execute(
        'SELECT DISTINCT product_line FROM categories WHERE product_line IS NOT NULL ORDER BY product_line'
    ).fetchall()
]


    # Fetch real values
    dropdown_options['metals'] = [row['metal'] for row in conn.execute('SELECT DISTINCT metal FROM categories WHERE metal IS NOT NULL ORDER BY metal').fetchall()]
    dropdown_options['product_types'] = [row['product_type'] for row in conn.execute('SELECT DISTINCT product_type FROM categories WHERE product_type IS NOT NULL ORDER BY product_type').fetchall()]
    dropdown_options['weights'] = [row['weight'] for row in conn.execute('SELECT DISTINCT weight FROM categories WHERE weight IS NOT NULL ORDER BY weight').fetchall()]
    dropdown_options['mints'] = [row['mint'] for row in conn.execute('SELECT DISTINCT mint FROM categories WHERE mint IS NOT NULL ORDER BY mint').fetchall()]
    dropdown_options['years'] = [row['year'] for row in conn.execute('SELECT DISTINCT year FROM categories WHERE year IS NOT NULL ORDER BY year').fetchall()]
    dropdown_options['finishes'] = [row['finish'] for row in conn.execute('SELECT DISTINCT finish FROM categories WHERE finish IS NOT NULL ORDER BY finish').fetchall()]
    dropdown_options['grades'] = [row['grade'] for row in conn.execute('SELECT DISTINCT grade FROM categories WHERE grade IS NOT NULL ORDER BY grade').fetchall()]

    conn.close()

    # --- FORCE INSERT standard values if missing ---
    if 'Gold' not in dropdown_options['metals']:
        dropdown_options['metals'].append('Gold')
    if 'Silver' not in dropdown_options['metals']:
        dropdown_options['metals'].append('Silver')
    if 'Platinum' not in dropdown_options['metals']:
        dropdown_options['metals'].append('Platinum')
    if 'Palladium' not in dropdown_options['metals']:
        dropdown_options['metals'].append('Palladium')

    if 'Coin' not in dropdown_options['product_types']:
        dropdown_options['product_types'].append('Coin')
    if 'Bar' not in dropdown_options['product_types']:
        dropdown_options['product_types'].append('Bar')
    if 'Round' not in dropdown_options['product_types']:
        dropdown_options['product_types'].append('Round')

    # Sort to keep dropdowns clean
    dropdown_options['metals'].sort()
    dropdown_options['product_types'].sort()
    dropdown_options['weights'].sort()
    dropdown_options['mints'].sort()
    dropdown_options['years'].sort()
    dropdown_options['finishes'].sort()
    dropdown_options['grades'].sort()

# --- Load Dropdowns at App Startup ---
load_dropdown_options()

# --- Sell Route ---
@sell_bp.route('/sell', methods=['GET', 'POST'])
def sell():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        metal = request.form['metal']
        product_line = request.form['product_line']
        product_type = request.form['product_type']
        weight = request.form['weight']
        mint = request.form['mint']
        year = request.form['year']
        finish = request.form['finish']
        grade = request.form['grade']
        quantity = int(request.form['quantity'])
        price_per_coin = float(request.form['price_per_coin'])
        graded = int(request.form.get('graded', 0))
        grading_service = request.form.get('grading_service') if graded else None


        conn = get_db_connection()

        # Look for existing category with all fields
        category = conn.execute('''
            SELECT id FROM categories
            WHERE 
                metal = ? AND
                product_line = ? AND
                product_type = ? AND
                weight = ? AND
                mint = ? AND
                year = ? AND
                finish = ? AND
                grade = ?
        ''', (metal, product_line, product_type, weight, mint, year, finish, grade)).fetchone()

        if category:
            category_id = category['id']
        else:
            # Create new category if not found
            conn.execute('''
                INSERT INTO categories (
                    metal, product_line, product_type, weight, mint, year, finish, grade
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (metal, product_line, product_type, weight, mint, year, finish, grade))
            conn.commit()

            category_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

        # Insert listing
        conn.execute('''
            INSERT INTO listings (category_id, seller_id, quantity, price_per_coin, graded, grading_service, active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        ''', (category_id, session['user_id'], quantity, price_per_coin, graded, grading_service))

        conn.commit()
        conn.close()

        return "✅ Your item was successfully listed!"

    return render_template(
        'sell.html',
        metals=dropdown_options['metals'],
        product_lines=dropdown_options['product_lines'],
        product_types=dropdown_options['product_types'],
        weights=dropdown_options['weights'],
        mints=dropdown_options['mints'],
        years=dropdown_options['years'],
        finishes=dropdown_options['finishes'],
        grades=dropdown_options['grades']
    )



@sell_bp.route('/upload_tracking/<int:order_id>', methods=['POST'])
def upload_tracking(order_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    tracking_number = request.form.get('tracking_number')
    carrier = request.form.get('carrier')

    if not tracking_number or not carrier:
        flash('Please provide tracking number and carrier.')
        return redirect(url_for('sell.sold_orders'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Insert or update tracking info
    cursor.execute('''
        INSERT INTO tracking (order_id, carrier, tracking_number, tracking_status)
        VALUES (?, ?, ?, 'In Transit')
        ON CONFLICT(order_id) DO UPDATE SET
            carrier=excluded.carrier,
            tracking_number=excluded.tracking_number,
            tracking_status='In Transit'
    ''', (order_id, carrier, tracking_number))

    # Update order status to 'Awaiting Delivery'
    cursor.execute('''
        UPDATE orders
        SET status = 'Awaiting Delivery'
        WHERE id = ?
    ''', (order_id,))

    conn.commit()
    conn.close()

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


@sell_bp.route('/accept_bid/<int:bucket_id>', methods=['POST'])
def accept_bid(bucket_id):
    from flask import flash, redirect, url_for, session, request
    if 'user_id' not in session:
        flash("🔒 Please log in to accept bids.", "warning")
        return redirect(url_for('auth.login'))

    seller_id = session['user_id']
    selected_bid_ids = request.form.getlist('selected_bids')

    if not selected_bid_ids:
        flash("⚠️ No bids selected.", "warning")
        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    conn = get_db_connection()
    c = conn.cursor()

    total_accepted = 0

    for bid_id in selected_bid_ids:
        accepted_qty = request.form.get(f'quantity_{bid_id}')
        if not accepted_qty or int(accepted_qty) <= 0:
            continue

        accepted_qty = int(accepted_qty)

        bid = c.execute('''
            SELECT buyer_id, category_id, quantity_requested, price_per_coin, status
            FROM bids WHERE id = ?
        ''', (bid_id,)).fetchone()

        if not bid or bid['status'].lower() not in ['open', 'pending', 'partially filled']:
            continue

        buyer_id = bid['buyer_id']
        category_id = bid['category_id']
        max_qty = bid['quantity_requested']
        price = bid['price_per_coin']

        qty_to_fulfill = min(accepted_qty, max_qty)

        # Create an order directly
        c.execute('''
            INSERT INTO orders (buyer_id, seller_id, category_id, quantity, price_each, status)
            VALUES (?, ?, ?, ?, ?, 'pending_shipment')
        ''', (buyer_id, seller_id, category_id, qty_to_fulfill, price))

        # Update the bid
        remaining = max_qty - qty_to_fulfill
        if remaining == 0:
            c.execute('UPDATE bids SET quantity_requested = 0, active = 0, status = "filled" WHERE id = ?', (bid_id,))
        else:
            c.execute('UPDATE bids SET quantity_requested = ?, status = "partially filled" WHERE id = ?', (remaining, bid_id))

        total_accepted += qty_to_fulfill

    conn.commit()
    conn.close()

    if total_accepted > 0:
        flash(f"✅ You accepted bids totaling {total_accepted} coin(s).", "success")
    else:
        flash("⚠️ No bids were accepted due to missing quantities.", "warning")

    return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))
