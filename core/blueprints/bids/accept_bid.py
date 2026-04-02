"""
Accept Bid Routes

Contains routes for accepting and cancelling bids:
- /accept_bid/<bucket_id> (POST) - Accept one or more bids from a bucket
- /cancel/<bid_id> (POST) - Cancel an active bid
"""

import logging
import stripe
from flask import request, redirect, url_for, session, flash, jsonify
from database import get_db_connection
from services.notification_service import notify_bid_filled
from services.notification_types import notify_bid_payment_failed
from services.pricing_service import get_effective_price, get_effective_bid_price
from services.order_service import write_order_item_snapshot

from . import bid_bp

_log = logging.getLogger(__name__)

# Must match place_bid.py — buyers reaching this threshold are blocked from placing new bids
_BID_STRIKE_THRESHOLD = 3


def _charge_bid_payment(bid_id: int, order_id: int, buyer_id: int,
                        pm_id: str, customer_id: str, amount_dollars: float) -> dict:
    """
    Create and confirm a Stripe PaymentIntent off-session for a bid acceptance.

    Returns:
        {'success': True, 'pi_id': 'pi_xxx'}
        {'success': False, 'code': 'card_declined', 'message': '...'}
    """
    try:
        pi = stripe.PaymentIntent.create(
            amount=max(1, round(amount_dollars * 100)),
            currency='usd',
            customer=customer_id,
            payment_method=pm_id,
            confirm=True,
            off_session=True,
            metadata={
                'user_id': str(buyer_id),
                'order_id': str(order_id),
                'bid_id': str(bid_id),
                'source': 'bid_acceptance',
            },
            idempotency_key=f'bid-accept-{bid_id}-{order_id}',
        )
        if pi.status == 'succeeded':
            return {'success': True, 'pi_id': pi.id}
        # Unexpected status (requires_action, etc.)
        return {
            'success': False,
            'code': pi.status,
            'message': f'Payment could not be confirmed automatically (status: {pi.status}). '
                       'The buyer may need to complete authentication.',
        }
    except stripe.error.CardError as e:
        err = e.error
        return {
            'success': False,
            'code': getattr(err, 'code', 'card_error'),
            'message': getattr(err, 'message', str(e)) or 'Card declined.',
            'is_card_decline': True,
        }
    except stripe.error.InvalidRequestError as e:
        return {
            'success': False,
            'code': 'invalid_request',
            'message': str(e),
            'is_card_decline': False,
        }
    except stripe.error.StripeError as e:
        _log.error('[BID ACCEPT] Stripe error charging bid %s order %s: %s', bid_id, order_id, e)
        return {
            'success': False,
            'code': 'stripe_error',
            'message': 'A payment processing error occurred. Please try again.',
            'is_card_decline': False,
        }


@bid_bp.route('/accept_bid/<int:bucket_id>', methods=['POST'])
def accept_bid(bucket_id):
    """
    Accept one or more bids from this bucket. Frontend submits:
      - selected_bids: list of bid IDs
      - accept_qty[<bid_id>]: integer accepted quantity for that bid (0..remaining_quantity)
    Falls back to legacy quantity_<bid_id> if present.
    """
    # Debug logging for session
    print(f"[DEBUG] /accept_bid session keys: {list(session.keys())}")
    print(f"[DEBUG] /accept_bid user_id in session: {'user_id' in session}")
    if 'user_id' in session:
        print(f"[DEBUG] /accept_bid user_id value: {session['user_id']}")

    # Check authentication - return JSON 401 for AJAX, redirect for traditional form submissions
    if 'user_id' not in session:
        print(f"[ERROR] /accept_bid - No user_id in session. Session: {dict(session)}")
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if is_ajax:
            return jsonify(success=False, message="Authentication required. Please log in."), 401
        else:
            return redirect(url_for('auth.login'))

    seller_id = session['user_id']
    selected_bid_ids = request.form.getlist('selected_bids')

    if not selected_bid_ids:
        flash("⚠️ No bids selected.", "warning")
        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch spot prices from the canonical source (spot_price_snapshots) so the
    # charge amount matches what was shown to the buyer at bid/wizard time.
    # Falls back to the legacy spot_prices cache so existing tests still work.
    try:
        snap_rows = cursor.execute(
            "SELECT metal, price_usd FROM spot_price_snapshots "
            "WHERE id IN (SELECT MAX(id) FROM spot_price_snapshots GROUP BY metal)"
        ).fetchall()
        if snap_rows:
            spot_prices = {row['metal'].lower(): float(row['price_usd']) for row in snap_rows}
        else:
            raise ValueError('no snapshots')
    except Exception:
        try:
            legacy_rows = cursor.execute('SELECT metal, price_usd_per_oz FROM spot_prices').fetchall()
            spot_prices = {row['metal'].lower(): float(row['price_usd_per_oz']) for row in legacy_rows}
        except Exception:
            spot_prices = {}

    total_filled = 0

    # Collect notification data (will send after commit to avoid database locking)
    notifications_to_send = []

    # Collect order details for AJAX response (for success modal) - SUPPORTS MULTIPLE BIDS
    all_order_details = []

    # Collect payment failures to report to the seller
    payment_failures = []

    # Collect buyer notification data for payment failures (sent after commit)
    failed_payment_notifications = []

    for bid_id in selected_bid_ids:
        # Load bid with all pricing and payment fields
        bid = cursor.execute('''
            SELECT b.id, b.category_id, b.quantity_requested, b.remaining_quantity,
                   b.price_per_coin, b.buyer_id, b.delivery_address, b.status,
                   b.pricing_mode, b.spot_premium, b.ceiling_price, b.pricing_metal,
                   b.recipient_first_name, b.recipient_last_name,
                   b.bid_payment_method_id, b.bid_payment_status,
                   c.metal, c.weight
            FROM bids b
            JOIN categories c ON b.category_id = c.id
            WHERE b.id = ?
        ''', (bid_id,)).fetchone()
        if not bid:
            continue

        # PREVENT SELF-ACCEPTING: Skip bids from the current user
        if bid['buyer_id'] == seller_id:
            continue

        # Prevent double-acceptance and block permanently invalid (payment-failed) bids
        if bid['bid_payment_status'] in ('charged', 'failed'):
            continue

        category_id          = bid['category_id']
        buyer_id             = bid['buyer_id']
        delivery_address     = bid['delivery_address']
        recipient_first_name = bid['recipient_first_name']
        recipient_last_name  = bid['recipient_last_name']
        bid_pm_id            = bid['bid_payment_method_id']

        # Require a saved payment method on the bid
        if not bid_pm_id:
            payment_failures.append({
                'bid_id': bid_id,
                'buyer_id': buyer_id,
                'reason': 'Buyer has no payment method saved for this bid.',
            })
            continue

        # Load buyer's Stripe customer ID
        buyer_row = cursor.execute(
            'SELECT stripe_customer_id FROM users WHERE id = ?', (buyer_id,)
        ).fetchone()
        buyer_customer_id = buyer_row['stripe_customer_id'] if buyer_row else None
        if not buyer_customer_id:
            payment_failures.append({
                'bid_id': bid_id,
                'buyer_id': buyer_id,
                'reason': 'Buyer has no Stripe payment account.',
            })
            continue

        # Calculate effective bid price (handles both static and premium-to-spot)
        bid_dict = dict(bid)
        effective_bid_price = get_effective_bid_price(bid_dict, spot_prices=spot_prices)
        price_limit = effective_bid_price

        # Requested accept quantity from form (supports new and legacy names)
        req_qty = 0
        key_new = f'accept_qty[{bid_id}]'
        key_legacy = f'quantity_{bid_id}'
        if key_new in request.form:
            try:
                req_qty = int(request.form.get(key_new, '0'))
            except ValueError:
                req_qty = 0
        elif key_legacy in request.form:
            try:
                req_qty = int(request.form.get(key_legacy, '0'))
            except ValueError:
                req_qty = 0

        # Determine remaining on the bid (fallback to quantity_requested if remaining_quantity is NULL)
        remaining_qty = bid['remaining_quantity'] if bid['remaining_quantity'] is not None else (bid['quantity_requested'] or 0)
        if remaining_qty <= 0:
            continue

        # Clamp request; skip if user chose 0
        quantity_needed = max(0, min(remaining_qty, req_qty))
        if quantity_needed == 0:
            continue

        # Try to fill from seller's listings first (if any)
        # Fetch all pricing fields to calculate effective prices
        listings = cursor.execute('''
            SELECT l.id, l.quantity, l.price_per_coin, l.seller_id,
                   l.pricing_mode, l.spot_premium, l.floor_price, l.pricing_metal,
                   c.metal, c.weight
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE l.category_id = ?
              AND l.seller_id   = ?
              AND l.active = 1
        ''', (category_id, seller_id)).fetchall()

        # Filter listings by effective price and sort by effective price
        matched_listings = []
        for listing in listings:
            listing_dict = dict(listing)
            listing_effective_price = get_effective_price(listing_dict, spot_prices=spot_prices)

            # Only match if listing's current effective price is at or below bid's effective price
            if listing_effective_price <= effective_bid_price:
                listing_dict['effective_price'] = listing_effective_price
                matched_listings.append(listing_dict)

        # Sort by effective price (cheapest first)
        matched_listings.sort(key=lambda x: x['effective_price'])

        # Phase 1: Build the fill plan without writing to the DB yet.
        # All inventory mutations happen inside the SAVEPOINT (Phase 2) so that
        # a payment failure rolls them back atomically along with the order.
        filled = 0
        inventory_plan = []   # [(listing_id, new_qty)] — applied inside SAVEPOINT
        order_items_to_create = []

        for listing in matched_listings:
            if filled >= quantity_needed:
                break
            if listing['quantity'] <= 0:
                continue

            fill_qty = min(listing['quantity'], quantity_needed - filled)
            new_list_qty = listing['quantity'] - fill_qty

            # Record the inventory change — no DB write yet
            inventory_plan.append((listing['id'], new_list_qty))

            order_items_to_create.append({
                'listing_id': listing['id'],
                'quantity': fill_qty,
                'price_each': effective_bid_price
            })

            filled += fill_qty

        # Record whether we need a seller-committed listing for the unfilled portion
        need_committed = filled < quantity_needed
        unfilled_qty = quantity_needed - filled if need_committed else 0
        if need_committed:
            filled += unfilled_qty

        # Calculate new_remaining for use in both notification and bid update
        new_remaining = remaining_qty - filled

        # Only create order if something will be filled
        if filled > 0 and (order_items_to_create or need_committed):
            # All items are priced at effective_bid_price
            total_price = filled * effective_bid_price

            # Use a savepoint so we can roll back ALL DB changes (inventory decrements,
            # committed-listing creation, order, order_items) if payment fails.
            sp_name = f'sp_bid_{bid_id}'
            cursor.execute(f'SAVEPOINT {sp_name}')

            # Phase 2: Apply inventory updates inside the savepoint
            for listing_id, new_list_qty in inventory_plan:
                if new_list_qty <= 0:
                    cursor.execute('UPDATE listings SET quantity = 0, active = 0 WHERE id = ?', (listing_id,))
                else:
                    cursor.execute('UPDATE listings SET quantity = ? WHERE id = ?', (new_list_qty, listing_id))

            # Create committed listing placeholder if needed (inside savepoint)
            if need_committed:
                cursor.execute('''
                    INSERT INTO listings (category_id, seller_id, quantity, price_per_coin,
                                         graded, grading_service, image_url, active)
                    VALUES (?, ?, 0, ?, 0, NULL, NULL, 0)
                ''', (category_id, seller_id, effective_bid_price))
                committed_listing_id = cursor.lastrowid
                order_items_to_create.append({
                    'listing_id': committed_listing_id,
                    'quantity': unfilled_qty,
                    'price_each': effective_bid_price
                })

            # Create the order record (unpaid until payment succeeds)
            cursor.execute('''
                INSERT INTO orders (buyer_id, total_price, shipping_address, status, created_at,
                                   recipient_first_name, recipient_last_name, payment_status,
                                   source_bid_id)
                VALUES (?, ?, ?, 'Pending Shipment', datetime('now'), ?, ?, 'unpaid', ?)
            ''', (buyer_id, total_price, delivery_address, recipient_first_name, recipient_last_name,
                  int(bid_id)))

            order_id = cursor.lastrowid

            # Create order_items for each fill; track order_item_id for snapshots
            order_item_ids = []
            for item in order_items_to_create:
                cursor.execute('''
                    INSERT INTO order_items (order_id, listing_id, quantity, price_each)
                    VALUES (?, ?, ?, ?)
                ''', (order_id, item['listing_id'], item['quantity'], item['price_each']))
                order_item_ids.append(cursor.lastrowid)

            # ── Attempt payment ──────────────────────────────────────────
            pay_result = _charge_bid_payment(
                bid_id=int(bid_id),
                order_id=order_id,
                buyer_id=buyer_id,
                pm_id=bid_pm_id,
                customer_id=buyer_customer_id,
                amount_dollars=total_price,
            )

            if not pay_result['success']:
                # Payment failed — roll back all DB work for this bid
                cursor.execute(f'ROLLBACK TO SAVEPOINT {sp_name}')
                cursor.execute(f'RELEASE SAVEPOINT {sp_name}')

                # Record failure on the bid; permanently close it so it cannot be re-accepted
                cursor.execute('''
                    UPDATE bids
                       SET bid_payment_status = 'failed',
                           bid_payment_failure_code = ?,
                           bid_payment_failure_message = ?,
                           bid_payment_attempted_at = datetime('now'),
                           active = 0,
                           status = 'Payment Failed'
                     WHERE id = ?
                ''', (pay_result.get('code'), pay_result.get('message'), bid_id))

                # Increment strike counter for card-level declines (not network errors).
                # Buyers with >= _BID_STRIKE_THRESHOLD strikes are blocked from placing new bids.
                if pay_result.get('is_card_decline'):
                    cursor.execute('''
                        UPDATE users
                           SET bid_payment_strikes = COALESCE(bid_payment_strikes, 0) + 1
                         WHERE id = ?
                    ''', (buyer_id,))

                failure_msg = pay_result.get('message', 'Payment declined.')
                payment_failures.append({
                    'bid_id': bid_id,
                    'buyer_id': buyer_id,
                    'reason': failure_msg,
                })

                # Queue buyer notification (sent after commit)
                failed_payment_notifications.append({
                    'buyer_id': buyer_id,
                    'bid_id': int(bid_id),
                    'failure_message': failure_msg,
                })
                continue
            # ── Payment succeeded ────────────────────────────────────────

            pi_id = pay_result['pi_id']

            # Stamp order with payment info
            cursor.execute('''
                UPDATE orders
                   SET stripe_payment_intent_id = ?,
                       payment_status = 'paid',
                       status = 'paid',
                       paid_at = datetime('now'),
                       payment_method_type = 'card'
                 WHERE id = ?
            ''', (pi_id, order_id))

            # Mark bid payment as charged
            cursor.execute('''
                UPDATE bids
                   SET bid_payment_status = 'charged',
                       bid_payment_intent_id = ?,
                       bid_payment_attempted_at = datetime('now')
                 WHERE id = ?
            ''', (pi_id, bid_id))

            # Phase 1: write immutable transaction snapshots inside the savepoint.
            # placed_from_ip is NULL for bid-accepted orders — no buyer HTTP request exists
            # at acceptance time; the action is seller-triggered.
            buyer_row = cursor.execute(
                'SELECT username, email FROM users WHERE id = ?', (buyer_id,)
            ).fetchone()
            _snap_buyer_username = buyer_row['username'] if buyer_row else None
            _snap_buyer_email = buyer_row['email'] if buyer_row else None
            for _snap_item, _snap_oi_id in zip(order_items_to_create, order_item_ids):
                try:
                    write_order_item_snapshot(
                        cursor=cursor,
                        order_id=order_id,
                        order_item_id=_snap_oi_id,
                        listing_id=_snap_item['listing_id'],
                        quantity=_snap_item['quantity'],
                        price_each=_snap_item['price_each'],
                        buyer_id=buyer_id,
                        buyer_username=_snap_buyer_username,
                        buyer_email=_snap_buyer_email,
                        payment_intent_id=pi_id,
                    )
                except Exception as _snap_err:
                    _log.warning('[BID ACCEPT] snapshot write failed for order %s item %s: %s',
                                 order_id, _snap_oi_id, _snap_err)

            cursor.execute(f'RELEASE SAVEPOINT {sp_name}')
            # ─────────────────────────────────────────────────────────────

            # Capture order details for THIS accepted bid (for AJAX response to show in modal)
            buyer_info = cursor.execute('SELECT username, first_name, last_name FROM users WHERE id = ?', (buyer_id,)).fetchone()
            all_order_details.append({
                'buyer_name': buyer_info['username'] if buyer_info else 'Unknown',
                'buyer_first_name': buyer_info['first_name'] if buyer_info else '',
                'buyer_last_name': buyer_info['last_name'] if buyer_info else '',
                'delivery_address': delivery_address,
                'price_per_coin': effective_bid_price,
                'quantity': filled,
                'total_price': total_price,
                'order_id': order_id
            })

            # Collect notification data for this bid (will send after commit)
            category = cursor.execute('SELECT metal, product_type, product_line, weight, year FROM categories WHERE id = ?', (category_id,)).fetchone()
            item_desc_parts = []
            if category:
                if category['metal']:
                    item_desc_parts.append(category['metal'])
                if category['product_line']:
                    item_desc_parts.append(category['product_line'])
                if category['weight']:
                    item_desc_parts.append(category['weight'])
                if category['year']:
                    item_desc_parts.append(str(category['year']))
            item_description = ' '.join(item_desc_parts) if item_desc_parts else 'Item'

            avg_price_per_unit = total_price / filled if filled > 0 else effective_bid_price
            notifications_to_send.append({
                'buyer_id': buyer_id,
                'order_id': order_id,
                'bid_id': bid_id,
                'item_description': item_description,
                'quantity_filled': filled,
                'price_per_unit': avg_price_per_unit,
                'total_amount': total_price,
                'is_partial': new_remaining > 0,
                'remaining_quantity': new_remaining
            })

        total_filled += filled

        # Update bid status / remaining
        if filled == 0:
            # no change
            pass
        elif new_remaining <= 0:
            cursor.execute('''
                UPDATE bids
                   SET remaining_quantity = 0,
                       active = 0,
                       status = 'Filled'
                 WHERE id = ?
            ''', (bid_id,))
        else:
            # Partial fill: reset bid_payment_status so a future seller can
            # accept the remaining quantity. Leaving it 'charged' would
            # permanently block re-acceptance (see guard at top of loop).
            cursor.execute('''
                UPDATE bids
                   SET remaining_quantity = ?,
                       status = 'Partially Filled',
                       bid_payment_status = 'pending',
                       bid_payment_intent_id = NULL
                 WHERE id = ?
            ''', (new_remaining, bid_id))

    conn.commit()
    conn.close()

    # Send payment failure notifications to buyers AFTER commit
    for fail_notif in failed_payment_notifications:
        try:
            notify_bid_payment_failed(
                buyer_id=fail_notif['buyer_id'],
                bid_id=fail_notif['bid_id'],
                failure_message=fail_notif['failure_message'],
            )
        except Exception as notif_err:
            print(f"[ERROR] Failed to notify buyer {fail_notif['buyer_id']} of payment failure: {notif_err}")

    # Send fill notifications AFTER commit (avoids database locking)
    for notif_data in notifications_to_send:
        try:
            notify_bid_filled(**notif_data)
        except Exception as notify_error:
            print(f"[ERROR] Failed to notify buyer {notif_data['buyer_id']}: {notify_error}")

    # Check if this is an AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if is_ajax:
        # Return JSON for AJAX requests
        if total_filled > 0:
            response_data = {
                'success': True,
                'message': f'You fulfilled a total of {total_filled} coin(s) across {len(all_order_details)} bid(s).',
                'total_filled': total_filled,
                'orders_created': len(all_order_details)
            }
            # Include ALL order details (for success modal to show all accepted bids)
            if all_order_details:
                response_data['all_order_details'] = all_order_details
                # Keep first one for backward compatibility with old JS
                response_data['order_details'] = all_order_details[0] if all_order_details else None
            # Surface any payment failures alongside successes
            if payment_failures:
                response_data['payment_failures'] = payment_failures
                response_data['payment_failure_count'] = len(payment_failures)
            return jsonify(response_data)
        elif payment_failures:
            # All bids failed payment
            failure_msgs = '; '.join(f"Bid {pf['bid_id']}: {pf['reason']}" for pf in payment_failures)
            return jsonify({
                'success': False,
                'message': f'Payment failed for selected bid(s). {failure_msgs}',
                'payment_failures': payment_failures,
            }), 402
        else:
            return jsonify({
                'success': False,
                'message': 'None of the selected bids could be filled.'
            }), 400
    else:
        # Traditional HTML response
        if total_filled > 0:
            flash(f"✅ You fulfilled a total of {total_filled} coin(s) across selected bids.", "success")
        elif payment_failures:
            reasons = '; '.join(pf['reason'] for pf in payment_failures)
            flash(f"❌ Payment failed for selected bid(s). {reasons}", "error")
        else:
            flash("❌ None of the selected bids could be filled from your listings.", "error")

        return redirect(url_for('buy.view_bucket', bucket_id=bucket_id))


@bid_bp.route('/cancel/<int:bid_id>', methods=['POST'])
def cancel_bid(bid_id):
    # 1) Auth guard
    if 'user_id' not in session:
        # AJAX?
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(error="Authentication required"), 401
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    # 2) Verify bid exists & is owned by this user
    row = cursor.execute(
        'SELECT active, status, remaining_quantity FROM bids WHERE id = ? AND buyer_id = ?',
        (bid_id, user_id)
    ).fetchone()

    if not row:
        conn.close()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(error="Bid not found"), 404
        flash("❌ Bid not found.", "error")
        return redirect(url_for('bid.my_bids'))

    # Check if bid can be cancelled (must be active with remaining quantity)
    # Allow cancelling 'Open' or 'Partially Filled' bids that still have remaining quantity
    if not row['active'] or (row['remaining_quantity'] or 0) <= 0:
        conn.close()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(error="This bid cannot be cancelled (already inactive or fully filled)"), 400
        flash("❌ This bid cannot be cancelled (already inactive or fully filled).", "error")
        return redirect(url_for('bid.my_bids'))

    # 3) Soft‐delete it
    cursor.execute(
        '''
        UPDATE bids
           SET active = 0,
               status = 'Cancelled'
         WHERE id = ? AND buyer_id = ?
        ''',
        (bid_id, user_id)
    )
    conn.commit()
    conn.close()

    # 4) Response
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return ('', 204)

    flash("✅ Your bid has been cancelled.", "success")
    return redirect(request.referrer or url_for('bid.my_bids'))
