"""
View Bids Routes

Contains routes for viewing bids:
- /my_bids (GET) - my_bids: Legacy redirect to account page
- /bid/<int:bucket_id> (GET) - bid_page: Submit bid page for a bucket
"""

from flask import render_template, redirect, url_for, session, flash
from database import get_db_connection

from . import bid_bp


@bid_bp.route('/my_bids')
def my_bids():
    """
    Legacy route that redirects to the Account page.
    The 'My Bids' tab on the Account page shows all user bids.
    """
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    # Redirect to account page where user can access My Bids tab
    return redirect(url_for('account.account') + '#bids')


@bid_bp.route("/bid/<int:bucket_id>", methods=["GET"])
def bid_page(bucket_id):
    if "user_id" not in session:
        flash(("error", "You must be logged in to submit a bid."))
        return redirect(url_for("auth.login"))

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM categories WHERE id = ?", (bucket_id,))
    bucket = c.fetchone()

    if not bucket:
        conn.close()
        flash(("error", "Item not found."))
        return redirect(url_for("buy.buy"))

    # Calculate lowest listed price
    lowest = c.execute('''
        SELECT MIN(price_per_coin) as min_price
        FROM listings
        WHERE category_id = ? AND active = 1 AND quantity > 0
    ''', (bucket_id,)).fetchone()
    lowest_listed_price = lowest['min_price'] or 0

    # Calculate highest active bid
    highest = c.execute('''
        SELECT MAX(price_per_coin) as max_bid
        FROM bids
        WHERE category_id = ? AND active = 1
    ''', (bucket_id,)).fetchone()
    highest_current_bid = highest['max_bid'] or 0

    conn.close()

    return render_template(
        "submit_bid.html",
        bucket=bucket,
        bid=None,
        is_edit=False,
        form_action_url=url_for('bid.place_bid', bucket_id=bucket_id),
        best_bid_price=round(lowest_listed_price + 5, 2),
        good_bid_price=round(highest_current_bid, 2)
    )
