
# ==============================
# routes/listings_routes.py (UPDATED)
# ==============================

from flask import Blueprint, render_template, request, redirect, url_for, session
from database import get_db_connection
import sqlite3

listings_bp = Blueprint('listings', __name__)


def _purge_zero_quantity_listings(conn):
    """Hard-delete any listings whose quantity is <= 0."""
    conn.execute("DELETE FROM listings WHERE quantity <= 0")
    conn.commit()


@listings_bp.route('/edit_listing/<int:listing_id>', methods=['GET', 'POST'])
def edit_listing(listing_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row

    # (Safety) purge any zero-qty listings before we proceed
    _purge_zero_quantity_listings(conn)

    # Fetch the listing, including the existing 'graded' flag and purity
    listing = conn.execute('''
        SELECT l.id AS listing_id,
               l.quantity,
               l.price_per_coin,
               l.graded        AS graded,
               l.grading_service,
               c.id            AS category_id,
               c.metal,
               c.coin_series,
               c.product_type,
               c.special_designation,
               c.purity,
               c.weight,
               c.mint,
               c.year,
               c.finish,
               c.grade
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.id = ? AND l.seller_id = ?
    ''', (listing_id, session['user_id'])).fetchone()

    if not listing:
        conn.close()
        return "Listing not found or unauthorized", 404

    if request.method == 'POST':
        graded = 1 if request.form.get('graded') == 'yes' else 0
        grading_service = request.form.get('grading_service') if graded else None
        new_quantity = int(request.form['quantity'])
        new_price   = float(request.form['price_per_coin'])

        # find matching category including purity
        new_cat = conn.execute('''
            SELECT id FROM categories
            WHERE metal=? AND coin_series=? AND product_type=? 
              AND special_designation=? AND purity=? AND weight=?
              AND mint=? AND year=? AND finish=? AND grade=?
        ''', (
            request.form['metal'],
            request.form['coin_series'],
            request.form['product_type'],
            request.form['special_designation'],
            request.form['purity'],
            request.form['weight'],
            request.form['mint'],
            request.form['year'],
            request.form['finish'],
            request.form['grade']
        )).fetchone()

        if not new_cat:
            conn.close()
            return "Invalid product combination", 400
        new_cat_id = new_cat['id']

        # If quantity becomes 0 or negative, hard-delete this listing
        if new_quantity <= 0:
            conn.execute(
                "DELETE FROM listings WHERE id = ? AND seller_id = ?",
                (listing_id, session['user_id'])
            )
            conn.commit()
            conn.close()

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return ('', 204)
            return redirect(url_for('listings.my_listings'))

        # Otherwise, update and keep active = 1
        conn.execute('''
            UPDATE listings
            SET category_id     = ?,
                quantity        = ?,
                price_per_coin  = ?,
                graded          = ?,
                grading_service = ?,
                active          = 1
            WHERE id = ? AND seller_id = ?
        ''', (
            new_cat_id,
            new_quantity,
            new_price,
            graded,
            grading_service,
            listing_id,
            session['user_id']
        ))
        conn.commit()
        conn.close()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return ('', 204)

        return redirect(url_for('listings.my_listings'))

    # === GET: gather dropdown options ===
    metals               = [r[0] for r in conn.execute("SELECT DISTINCT metal FROM categories")]
    coin_series          = [r[0] for r in conn.execute("SELECT DISTINCT coin_series FROM categories")]
    product_types        = [r[0] for r in conn.execute("SELECT DISTINCT product_type FROM categories")]
    special_designations = [r[0] for r in conn.execute("SELECT DISTINCT special_designation FROM categories")]
    purities             = [r[0] for r in conn.execute("SELECT DISTINCT purity FROM categories")]
    weights              = [r[0] for r in conn.execute("SELECT DISTINCT weight FROM categories")]
    mints                = [r[0] for r in conn.execute("SELECT DISTINCT mint FROM categories")]
    years                = [r[0] for r in conn.execute("SELECT DISTINCT year FROM categories")]
    finishes             = [r[0] for r in conn.execute("SELECT DISTINCT finish FROM categories")]
    grades               = [r[0] for r in conn.execute("SELECT DISTINCT grade FROM categories")]
    grading_services     = ['PCGS', 'NGC', 'ANACS', 'ICG']

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_template(
            'modals/edit_listing_modal.html',
            listing=listing,
            metals=metals,
            coin_series=coin_series,
            product_types=product_types,
            special_designations=special_designations,
            purities=purities,
            weights=weights,
            mints=mints,
            years=years,
            finishes=finishes,
            grades=grades,
            grading_services=grading_services
        )
        conn.close()
        return html

    conn.close()
    return render_template('edit_listing_fullpage.html', listing=listing)


@listings_bp.route('/cancel_listing/<int:listing_id>', methods=['POST'])
def cancel_listing(listing_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row

    listing = conn.execute('SELECT seller_id FROM listings WHERE id = ?', (listing_id,)).fetchone()

    if listing and listing['seller_id'] == session['user_id']:
        # Status-quo behavior: deactivate; do not delete seller's content on cancel
        conn.execute('UPDATE listings SET active = 0 WHERE id = ?', (listing_id,))
        conn.commit()

    conn.close()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return ('', 204)
    return redirect(url_for('listings.my_listings'))


@listings_bp.route('/cancel_listing_confirmation_modal/<int:listing_id>')
def cancel_listing_confirmation_modal(listing_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    return render_template('modals/cancel_listing_confirmation_modal.html', listing_id=listing_id)


@listings_bp.route('/my_listings')
def my_listings():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row

    # Purge zero-qty listings globally before showing the page
    _purge_zero_quantity_listings(conn)

    # Fetch Active Listings (only active and qty>0)
    listings = conn.execute('''
        SELECT l.id as listing_id,
               l.quantity,
               l.price_per_coin,
               c.bucket_id  AS bucket_id,
               c.metal,
               c.product_type,
               c.special_designation,
               c.weight,
               c.mint,
               c.year,
               c.finish,
               c.grade
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.seller_id = ? AND l.active = 1 AND l.quantity > 0
        ORDER BY l.id DESC
    ''', (session['user_id'],)).fetchall()

    # Orders from listings
    sales_from_listings = conn.execute('''
        SELECT o.id   AS order_id,
               oi.quantity,
               oi.price_each,
               o.status,
               o.delivery_address, 
               u.username AS buyer_username,
               c.metal,
               c.product_type,
               c.special_designation,
               0 AS already_rated
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        JOIN listings l     ON oi.listing_id = l.id
        JOIN categories c   ON l.category_id = c.id
        JOIN users u        ON o.buyer_id = u.id
        WHERE l.seller_id = ?
        ORDER BY o.created_at DESC
    ''', (session['user_id'],)).fetchall()

    # Orders from accepted bids
    sales_from_bids = conn.execute('''
        SELECT o.id   AS order_id,
               o.quantity,
               o.price_each,
               o.status,
               o.delivery_address,
               u.username AS buyer_username,
               c.metal,
               c.product_type,
               c.special_designation,
               0 AS already_rated
        FROM orders o
        JOIN categories c ON o.category_id = c.id
        JOIN users u      ON o.buyer_id = u.id
        WHERE o.seller_id = ?
        ORDER BY o.created_at DESC
    ''', (session['user_id'],)).fetchall()

    sales = sales_from_listings + sales_from_bids

    conn.close()
    return render_template('my_listings.html', listings=listings, sales=sales)
