"""
Place Bid Routes

Routes for placing and creating bids.

Routes:
- POST /bids/place_bid/<bucket_id>: place_bid - Traditional form-based bid placement
- POST /bids/create/<bucket_id>: create_bid_unified - AJAX-based unified modal bid creation
"""

import logging
import stripe
from flask import request, redirect, url_for, session, flash, jsonify
from database import get_db_connection
from services.notification_types import notify_bid_placed, notify_bid_on_bucket
from services.pricing_service import get_effective_bid_price
from utils.auth_utils import frozen_check

_log = logging.getLogger(__name__)

# Number of failed accepted-bid payments that blocks further bid placement
_BID_STRIKE_THRESHOLD = 3


def _verify_saved_card(user_id: int, conn, selected_pm_id: str):
    """
    Verify that the user has at least one saved Stripe card and that
    selected_pm_id (if given) belongs to their Stripe customer.

    Returns (pm_id_to_use, error_message).
    On success error_message is None.
    On failure pm_id_to_use is None.
    """
    row = conn.execute(
        'SELECT stripe_customer_id FROM users WHERE id = ?', (user_id,)
    ).fetchone()
    customer_id = row['stripe_customer_id'] if row else None

    if not customer_id:
        return None, 'You must save a payment card before placing a bid.'

    try:
        # Check that user has at least one saved card
        pms = stripe.PaymentMethod.list(customer=customer_id, type='card', limit=10)
        pm_list = list(pms.auto_paging_iter())
        if not pm_list:
            return None, 'You must save a payment card before placing a bid.'

        if selected_pm_id:
            # Verify ownership
            matching = [pm for pm in pm_list if pm.id == selected_pm_id]
            if not matching:
                return None, 'The selected payment method was not found on your account.'
            return selected_pm_id, None
        else:
            # Auto-select the first (default) card
            customer = stripe.Customer.retrieve(customer_id)
            default_pm_id = (customer.get('invoice_settings') or {}).get('default_payment_method')
            if default_pm_id and any(pm.id == default_pm_id for pm in pm_list):
                return default_pm_id, None
            return pm_list[0].id, None

    except stripe.error.StripeError as e:
        _log.error('[BID PLACE] Stripe error verifying card for user %s: %s', user_id, e)
        return None, 'Unable to verify payment method. Please try again.'

from . import bid_bp


@bid_bp.route('/place_bid/<int:bucket_id>', methods=['POST'])
@frozen_check
def place_bid(bucket_id):
    if 'user_id' not in session:
        flash("You must be logged in to place a bid.", "error")
        return redirect(url_for('auth.login'))

    # Block buyers who have reached the strike threshold
    conn_check = get_db_connection()
    try:
        strike_row = conn_check.execute(
            'SELECT COALESCE(bid_payment_strikes, 0) as strikes FROM users WHERE id = ?',
            (session['user_id'],)
        ).fetchone()
        strikes = strike_row['strikes'] if strike_row else 0
    finally:
        conn_check.close()

    if strikes >= _BID_STRIKE_THRESHOLD:
        flash(
            "Your account has been restricted from placing bids due to multiple payment failures. "
            "Please contact support to restore access.",
            "error"
        )
        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    try:
        # Extract pricing mode (normalize 'variable' to 'premium_to_spot' for backward compatibility)
        pricing_mode = request.form.get('bid_pricing_mode', 'static').strip()
        if pricing_mode == 'variable':
            pricing_mode = 'premium_to_spot'

        # Extract quantity (use shared bid_quantity field for both modes)
        bid_quantity = int(request.form.get('bid_quantity', 1))

        delivery_address = request.form['delivery_address'].strip()
        requires_grading = request.form.get('requires_grading') == 'yes'
        random_year = 1 if request.form.get('random_year') == 'on' else 0

        # Extract pricing parameters based on mode
        if pricing_mode == 'premium_to_spot':
            # Premium-to-spot mode
            spot_premium_str = request.form.get('bid_spot_premium', '0').strip()
            ceiling_price_str = request.form.get('bid_ceiling_price', '0').strip()

            # Handle empty strings by using 0 as default
            spot_premium = float(spot_premium_str) if spot_premium_str else 0.0
            ceiling_price = float(ceiling_price_str) if ceiling_price_str else 0.0
            pricing_metal = request.form.get('bid_pricing_metal', '').strip()

            # For backwards compatibility, store ceiling_price as price_per_coin
            bid_price = ceiling_price
        else:
            # Static mode
            bid_price_str = request.form.get('bid_price', '0').strip()
            bid_price = float(bid_price_str) if bid_price_str else 0.0
            spot_premium = None
            ceiling_price = None
            pricing_metal = None
            pricing_mode = 'static'

    except (ValueError, KeyError) as e:
        flash(f"Invalid form data: {str(e)}", "error")
        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    # Validate based on pricing mode
    if pricing_mode == 'premium_to_spot':
        if ceiling_price <= 0:
            flash("Max price (ceiling) must be greater than zero for premium-to-spot bids.", "error")
            return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))
        if spot_premium < 0:
            flash("Premium cannot be negative.", "error")
            return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))
    else:
        if bid_price <= 0:
            flash("Bid price must be greater than zero.", "error")
            return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    if bid_quantity <= 0:
        flash("Bid quantity must be greater than zero.", "error")
        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    selected_pm_id = request.form.get('selected_payment_method_id', '').strip()

    # Get recipient name from user's Account Details (source of truth)
    conn = get_db_connection()
    cursor = conn.cursor()

    # Validate saved card before any other work
    pm_id_to_use, card_error = _verify_saved_card(session['user_id'], conn, selected_pm_id)
    if card_error:
        conn.close()
        flash(card_error, "error")
        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    user_info = cursor.execute(
        'SELECT first_name, last_name FROM users WHERE id = ?',
        (session['user_id'],)
    ).fetchone()

    # Resolve actual category_id from bucket_id
    # bids.category_id is a FK to categories.id (not bucket_id)
    category_row = cursor.execute(
        'SELECT id FROM categories WHERE bucket_id = ? LIMIT 1', (bucket_id,)
    ).fetchone()
    if not category_row:
        conn.close()
        flash("Item not found.", "error")
        return redirect(url_for('buy.buy'))
    actual_category_id = category_row['id']

    # Block bid if all active listings in this bucket belong to the current user
    counts = cursor.execute('''
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN l.seller_id != ? THEN 1 ELSE 0 END) AS others
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ? AND l.active = 1 AND l.quantity > 0
    ''', (session['user_id'], bucket_id)).fetchone()
    if counts['total'] > 0 and counts['others'] == 0:
        conn.close()
        flash("You can't bid on a bucket where your listings are the only ones available.", "error")
        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    recipient_first = (user_info['first_name'] if user_info and user_info['first_name'] else '')
    recipient_last = (user_info['last_name'] if user_info and user_info['last_name'] else '')

    cursor.execute(
        '''
        INSERT INTO bids (
            category_id, buyer_id, quantity_requested, price_per_coin,
            remaining_quantity, active, requires_grading,
            delivery_address, status,
            pricing_mode, spot_premium, ceiling_price, pricing_metal,
            recipient_first_name, recipient_last_name, random_year,
            bid_payment_method_id, bid_payment_status
        ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, 'Open', ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        ''',
        (
            actual_category_id,
            session['user_id'],
            bid_quantity,
            bid_price,
            bid_quantity,
            1 if requires_grading else 0,
            delivery_address,
            pricing_mode,
            spot_premium,
            ceiling_price,
            pricing_metal,
            recipient_first,
            recipient_last,
            random_year,
            pm_id_to_use,
        )
    )
    new_bid_id = cursor.lastrowid

    # Auto-match intentionally disabled: bids fill only when a seller manually
    # accepts via /bids/accept_bid/<bucket_id>, which charges the buyer's card.
    # Calling auto_match here would create orders without payment.
    conn.commit()
    conn.close()

    flash("Your bid was placed successfully!", "success")
    return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))


@bid_bp.route('/create/<int:bucket_id>', methods=['POST'])
@frozen_check
def create_bid_unified(bucket_id):
    """
    Create a new bid (unified modal version).
    Returns JSON for AJAX handling.

    After creating the bid, automatically attempts to match it with available listings.

    Form parameters:
    - bid_pricing_mode: 'static' or 'premium_to_spot'
    - Static mode: bid_price, bid_quantity
    - Premium mode: bid_spot_premium, bid_ceiling_price, bid_quantity_premium, bid_pricing_metal
    - delivery_address: string
    - requires_grading: 'yes' or 'no'
    - preferred_grader: string (optional)
    """
    if 'user_id' not in session:
        return jsonify(success=False, message="Authentication required"), 401

    # Block buyers who have reached the strike threshold
    conn_check = get_db_connection()
    try:
        strike_row = conn_check.execute(
            'SELECT COALESCE(bid_payment_strikes, 0) as strikes FROM users WHERE id = ?',
            (session['user_id'],)
        ).fetchone()
        strikes = strike_row['strikes'] if strike_row else 0
    finally:
        conn_check.close()

    if strikes >= _BID_STRIKE_THRESHOLD:
        return jsonify(
            success=False,
            message="Your account is restricted from placing bids due to multiple payment failures. "
                    "Please contact support to restore access.",
            strike_blocked=True
        ), 403

    errors = {}
    try:
        # Extract pricing mode (normalize 'variable' to 'premium_to_spot' for backward compatibility)
        pricing_mode = request.form.get('bid_pricing_mode', 'static').strip()
        if pricing_mode == 'variable':
            pricing_mode = 'premium_to_spot'

        # Extract quantity (use shared bid_quantity field for both modes)
        bid_quantity_str = request.form.get('bid_quantity', '').strip()
        bid_quantity = int(bid_quantity_str) if bid_quantity_str else 0

        delivery_address = request.form.get('delivery_address', '').strip()
        requires_grading = request.form.get('requires_grading') == 'yes'
        random_year = 1 if request.form.get('random_year') == 'on' else 0

        # Extract pricing parameters based on mode
        if pricing_mode == 'premium_to_spot':
            # Premium-to-spot mode
            spot_premium_str = request.form.get('bid_spot_premium', '').strip()
            ceiling_price_str = request.form.get('bid_ceiling_price', '').strip()

            # Handle empty strings - premium can be 0, ceiling must be positive
            spot_premium = float(spot_premium_str) if spot_premium_str else 0.0
            ceiling_price = float(ceiling_price_str) if ceiling_price_str else 0.0
            pricing_metal = request.form.get('bid_pricing_metal', '').strip()

            # For backwards compatibility, store ceiling_price as price_per_coin
            bid_price = ceiling_price
        else:
            # Static mode
            bid_price_str = request.form.get('bid_price', '').strip()
            bid_price = float(bid_price_str) if bid_price_str else 0.0
            spot_premium = None
            ceiling_price = None
            pricing_metal = None
            pricing_mode = 'static'

    except (ValueError, KeyError) as e:
        return jsonify(success=False, message=f"Invalid form data: {str(e)}"), 400

    # Server-side validation based on pricing mode
    if pricing_mode == 'premium_to_spot':
        if ceiling_price <= 0:
            errors['bid_ceiling_price'] = "Max price (ceiling) must be greater than zero for premium-to-spot bids."
        if spot_premium < 0:
            errors['bid_spot_premium'] = "Premium cannot be negative."
    else:
        if bid_price <= 0:
            errors['bid_price'] = "Price must be greater than zero."

    if bid_quantity <= 0:
        errors['bid_quantity'] = "Quantity must be greater than zero."
    if not delivery_address:
        errors['delivery_address'] = "Delivery address is required."

    if errors:
        return jsonify(success=False, errors=errors), 400

    selected_pm_id = request.form.get('selected_payment_method_id', '').strip()

    # Get recipient name from user's Account Details (source of truth)
    conn = get_db_connection()
    cursor = conn.cursor()

    # Validate saved card before any other work
    pm_id_to_use, card_error = _verify_saved_card(session['user_id'], conn, selected_pm_id)
    if card_error:
        conn.close()
        return jsonify(success=False, message=card_error, requires_saved_card=True), 400

    user_info = cursor.execute(
        'SELECT first_name, last_name FROM users WHERE id = ?',
        (session['user_id'],)
    ).fetchone()

    # Resolve actual category_id from bucket_id
    # bids.category_id is a FK to categories.id (not bucket_id)
    category_row = cursor.execute(
        'SELECT id FROM categories WHERE bucket_id = ? LIMIT 1', (bucket_id,)
    ).fetchone()
    if not category_row:
        conn.close()
        return jsonify(success=False, message="Item not found."), 404
    actual_category_id = category_row['id']

    # Block bid if all active listings in this bucket belong to the current user
    counts = cursor.execute('''
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN l.seller_id != ? THEN 1 ELSE 0 END) AS others
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ? AND l.active = 1 AND l.quantity > 0
    ''', (session['user_id'], bucket_id)).fetchone()
    if counts['total'] > 0 and counts['others'] == 0:
        conn.close()
        return jsonify(
            success=False,
            message="You can't bid on a bucket where your listings are the only ones available."
        ), 403

    recipient_first = (user_info['first_name'] if user_info and user_info['first_name'] else '')
    recipient_last = (user_info['last_name'] if user_info and user_info['last_name'] else '')

    # Insert bid into database
    try:
        cursor.execute(
            '''
            INSERT INTO bids (
                category_id, buyer_id, quantity_requested, price_per_coin,
                remaining_quantity, active, requires_grading,
                delivery_address, status,
                pricing_mode, spot_premium, ceiling_price, pricing_metal,
                recipient_first_name, recipient_last_name, random_year,
                bid_payment_method_id, bid_payment_status
            ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, 'Open', ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            ''',
            (
                actual_category_id,
                session['user_id'],
                bid_quantity,
                bid_price,
                bid_quantity,  # remaining_quantity starts equal to quantity_requested
                1 if requires_grading else 0,
                delivery_address,
                pricing_mode,
                spot_premium,
                ceiling_price,
                pricing_metal,
                recipient_first,
                recipient_last,
                random_year,
                pm_id_to_use,
            )
        )
        new_bid_id = cursor.lastrowid

        # Auto-match intentionally disabled: bids fill only when a seller manually
        # accepts via /bids/accept_bid/<bucket_id>, which charges the buyer's card.
        # Calling auto_match here would create orders without payment.
        match_result = {'filled_quantity': 0, 'orders_created': 0, 'message': '', 'notifications': [], 'ledger_orders': []}

        conn.commit()

        # Get the created bid with all fields for effective price calculation
        created_bid = conn.execute('''
            SELECT b.*, c.metal, c.weight, c.product_type
            FROM bids b
            JOIN categories c ON b.category_id = c.id
            WHERE b.id = ?
        ''', (new_bid_id,)).fetchone()

        # Get bucket info for item description (before closing connection)
        bucket_info = conn.execute('''
            SELECT metal, product_type, product_line, weight, year
            FROM categories WHERE id = ?
        ''', (bucket_id,)).fetchone()

        # Get all unique sellers with active listings in this bucket (for notifications)
        # Get bidder username for the notification
        bidder_info = conn.execute('SELECT username FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        bidder_username = bidder_info['username'] if bidder_info else 'Someone'

        sellers = conn.execute('''
            SELECT DISTINCT l.seller_id
            FROM listings l
            WHERE l.category_id = ?
              AND l.active = 1
              AND l.quantity > 0
              AND l.seller_id != ?
        ''', (bucket_id, session['user_id'])).fetchall()

        # Fetch spot prices from the canonical source (spot_price_snapshots) before
        # closing the connection so that the effective_price in the response uses
        # the same prices as auto_match and accept_bid.  Falls back to legacy
        # spot_prices cache so test environments still work correctly.
        try:
            snap_rows = conn.execute(
                "SELECT metal, price_usd FROM spot_price_snapshots "
                "WHERE id IN (SELECT MAX(id) FROM spot_price_snapshots GROUP BY metal)"
            ).fetchall()
            if snap_rows:
                db_spot_prices = {row['metal'].lower(): float(row['price_usd']) for row in snap_rows}
            else:
                raise ValueError('no snapshots')
        except Exception:
            try:
                legacy_rows = conn.execute(
                    'SELECT metal, price_usd_per_oz FROM spot_prices'
                ).fetchall()
                db_spot_prices = {row['metal'].lower(): float(row['price_usd_per_oz']) for row in legacy_rows}
            except Exception:
                db_spot_prices = {}

        conn.close()

        # Calculate effective bid price: min(spot + premium, ceiling).
        # Pass the DB spot prices explicitly to avoid falling back to the external
        # spot-price service (which may be unavailable and would return ceiling instead).
        bid_dict = dict(created_bid) if created_bid else {}
        effective_price = get_effective_bid_price(bid_dict, spot_prices=db_spot_prices) if created_bid else bid_price

        # Expose the current spot price for the success modal display
        current_spot_price = db_spot_prices.get(pricing_metal.lower()) if pricing_metal else None

        # Build item description from bucket info
        item_desc_parts = []
        if bucket_info:
            if bucket_info['metal']:
                item_desc_parts.append(bucket_info['metal'])
            if bucket_info['product_line']:
                item_desc_parts.append(bucket_info['product_line'])
            if bucket_info['weight']:
                item_desc_parts.append(bucket_info['weight'])
            if bucket_info['year']:
                item_desc_parts.append(str(bucket_info['year']))
        item_description = ' '.join(item_desc_parts) if item_desc_parts else 'Item'

        # Send notifications (after connection closed)
        # 1. Notify the bidder that their bid was placed
        try:
            notify_bid_placed(
                bidder_id=session['user_id'],
                bid_id=new_bid_id,
                bucket_id=bucket_id,
                item_description=item_description,
                quantity=bid_quantity,
                price_per_unit=effective_price
            )
        except Exception as e:
            print(f"[NOTIFICATION ERROR] Failed to send bid_placed notification: {e}")

        # 2. Notify sellers in this bucket about the new bid
        try:
            for seller in sellers:
                notify_bid_on_bucket(
                    seller_id=seller['seller_id'],
                    bidder_username=bidder_username,
                    bucket_id=bucket_id,
                    item_description=item_description,
                    bid_price=effective_price,
                    quantity=bid_quantity
                )
        except Exception as e:
            print(f"[NOTIFICATION ERROR] Failed to send bid_on_bucket notifications: {e}")

        # 3. Send fill notifications if bid was auto-matched
        for notif in match_result.get('notifications', []):
            try:
                notify_bid_filled(
                    buyer_id=notif['buyer_id'],
                    order_id=notif['order_id'],
                    bid_id=notif['bid_id'],
                    item_description=notif['item_description'],
                    quantity_filled=notif['quantity_filled'],
                    price_per_unit=notif['price_per_unit'],
                    total_amount=notif['total_amount'],
                    is_partial=notif['is_partial'],
                    remaining_quantity=notif['remaining_quantity']
                )
            except Exception as e:
                print(f"[NOTIFICATION ERROR] Failed to send bid fill notification: {e}")

        # Build response message
        if pricing_mode == 'premium_to_spot':
            base_message = f"Your variable bid (effective price: ${effective_price:.2f}) for {bid_quantity} item(s) was placed successfully!"
        else:
            base_message = f"Your bid of ${bid_price:.2f} for {bid_quantity} item(s) was placed successfully!"

        if match_result['filled_quantity'] > 0:
            # Bid was filled (fully or partially)
            full_message = f"{base_message}\n\n{match_result['message']}"
        else:
            # Bid is still open, no matches found
            full_message = f"{base_message} Your bid is now open and waiting for matching listings."

        return jsonify(
            success=True,
            message=full_message,
            bid_id=new_bid_id,
            filled_quantity=match_result['filled_quantity'],
            orders_created=match_result['orders_created'],
            pricing_mode=pricing_mode,
            effective_price=effective_price,
            current_spot_price=current_spot_price
        )

    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except:
            pass  # Connection may already be closed
        return jsonify(success=False, message=f"Database error: {str(e)}"), 500


@bid_bp.route('/relist/<int:bid_id>', methods=['POST'])
@frozen_check
def relist_failed_bid(bid_id):
    """
    Relist a payment-failed bid with the same specs on the same bucket.
    The original failed bid is left as-is; a new Open bid is created.
    """
    if 'user_id' not in session:
        return jsonify(success=False, error='Authentication required'), 401

    user_id = session['user_id']

    # Block buyers who have reached the strike threshold
    conn = get_db_connection()
    try:
        strike_row = conn.execute(
            'SELECT COALESCE(bid_payment_strikes, 0) as strikes FROM users WHERE id = ?',
            (user_id,)
        ).fetchone()
        strikes = strike_row['strikes'] if strike_row else 0
        if strikes >= _BID_STRIKE_THRESHOLD:
            conn.close()
            return jsonify(
                success=False,
                error='Your account is restricted from placing bids due to multiple payment failures. '
                      'Please contact support to restore access.'
            ), 403

        # Fetch the original failed bid (must not have been relisted already)
        original = conn.execute(
            '''SELECT b.*, c.bucket_id
               FROM bids b
               LEFT JOIN categories c ON b.category_id = c.id
               WHERE b.id = ? AND b.buyer_id = ?
                 AND b.bid_payment_status = 'failed'
                 AND b.status != 'Relisted'
            ''',
            (bid_id, user_id)
        ).fetchone()

        if not original:
            conn.close()
            return jsonify(success=False, error='Bid not found or not eligible for relisting'), 404

        # Verify the bucket is still active (at least one non-owned listing exists)
        bucket_id = original['bucket_id']
        counts = conn.execute(
            '''SELECT COUNT(*) AS total,
                      SUM(CASE WHEN l.seller_id != ? THEN 1 ELSE 0 END) AS others
               FROM listings l
               JOIN categories c ON l.category_id = c.id
               WHERE c.bucket_id = ? AND l.active = 1 AND l.quantity > 0
            ''',
            (user_id, bucket_id)
        ).fetchone()
        if not counts or counts['total'] == 0 or not (counts['others'] or 0):
            conn.close()
            return jsonify(
                success=False,
                error='No eligible listings remain on this bucket — cannot relist.'
            ), 400

        # Verify user still has a saved card (use their current default)
        pm_id_to_use, card_error = _verify_saved_card(user_id, conn, None)
        if card_error:
            conn.close()
            return jsonify(success=False, error=card_error), 400

        # Insert new bid with same specs, using current default payment method
        conn.execute(
            '''INSERT INTO bids (
                   category_id, buyer_id, quantity_requested, price_per_coin,
                   remaining_quantity, active, requires_grading,
                   delivery_address, status,
                   pricing_mode, spot_premium, ceiling_price, pricing_metal,
                   recipient_first_name, recipient_last_name, random_year,
                   bid_payment_method_id, bid_payment_status
               ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, 'Open', ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            ''',
            (
                original['category_id'],
                user_id,
                original['quantity_requested'],
                original['price_per_coin'],
                original['quantity_requested'],
                original['requires_grading'],
                original['delivery_address'],
                original['pricing_mode'],
                original['spot_premium'],
                original['ceiling_price'],
                original['pricing_metal'],
                original['recipient_first_name'],
                original['recipient_last_name'],
                original['random_year'] or 0,
                pm_id_to_use,
            )
        )
        # Mark original bid as Relisted so it no longer shows the relist button
        conn.execute(
            "UPDATE bids SET status = 'Relisted' WHERE id = ?",
            (bid_id,)
        )
        conn.commit()
        conn.close()
        return jsonify(success=True, message='Bid relisted successfully')

    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        _log.error('[RELIST BID] Error relisting bid %s for user %s: %s', bid_id, user_id, e)
        return jsonify(success=False, error='Failed to relist bid'), 500
