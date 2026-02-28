"""
Notification Types
==================
Convenience wrappers that build the right title/body/metadata for each
event type, then call notify() from notification_service so that:

  1. User notification_settings are checked automatically.
  2. All inserts go through a single code path.

Add a new event by writing a small notify_<event>() function here.
"""

import database as _db_module
from services.notification_service import notify


def _get_conn():
    return _db_module.get_db_connection()


# ---------------------------------------------------------------------------
# ── Listings ────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

def notify_listing_created(seller_id, listing_id, item_description):
    """Confirm to a seller that their listing was published."""
    return notify(
        user_id=seller_id,
        notification_type='listing_created_success',
        title='Listing Published',
        body=f'Your listing for {item_description} is now live.',
        related_listing_id=listing_id,
        metadata={'item_description': item_description},
    )


def notify_listing_edited(seller_id, listing_id, item_description):
    """Confirm to a seller that their listing was updated."""
    return notify(
        user_id=seller_id,
        notification_type='listing_edited',
        title='Listing Updated',
        body=f'Your listing for {item_description} has been updated.',
        related_listing_id=listing_id,
        metadata={'item_description': item_description},
    )


def notify_listing_delisted(seller_id, listing_id, item_description):
    """Notify a seller that their listing has been removed / cancelled."""
    return notify(
        user_id=seller_id,
        notification_type='listing_delisted',
        title='Listing Removed',
        body=f'Your listing for {item_description} has been removed.',
        related_listing_id=listing_id,
        metadata={'item_description': item_description},
    )


def notify_listing_expired(seller_id, listing_id, item_description):
    """Notify a seller that their listing expired (stub – no expiration system yet)."""
    return notify(
        user_id=seller_id,
        notification_type='listing_expired',
        title='Listing Expired',
        body=f'Your listing for {item_description} has expired.',
        related_listing_id=listing_id,
        metadata={'item_description': item_description},
    )


# ---------------------------------------------------------------------------
# ── Bids ────────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

def notify_bid_placed(bidder_id, bid_id, bucket_id, item_description, quantity, price_per_unit):
    """Confirm to a bidder that their bid was placed."""
    total = quantity * price_per_unit
    return notify(
        user_id=bidder_id,
        notification_type='bid_placed_success',
        title='Bid Placed Successfully',
        body=(
            f'Your bid for {quantity} unit(s) of {item_description} at '
            f'${price_per_unit:.2f}/unit (${total:.2f} total) has been placed.'
        ),
        related_bid_id=bid_id,
        metadata={
            'bucket_id': bucket_id,
            'quantity': quantity,
            'price_per_unit': price_per_unit,
            'total_amount': total,
            'item_description': item_description,
        },
    )


def notify_bid_received(seller_id, bidder_username, bid_id, bucket_id,
                        item_description, bid_price, quantity):
    """Notify a seller that a bid was received on their listing."""
    total = quantity * bid_price
    return notify(
        user_id=seller_id,
        notification_type='bid_received',
        title='New Bid Received',
        body=(
            f'{bidder_username} placed a bid for {quantity} unit(s) of '
            f'{item_description} at ${bid_price:.2f}/unit (${total:.2f} total).'
        ),
        related_bid_id=bid_id,
        metadata={
            'bucket_id': bucket_id,
            'bidder_username': bidder_username,
            'quantity': quantity,
            'bid_price': bid_price,
            'total_amount': total,
            'item_description': item_description,
        },
    )


def notify_outbid(previous_bidder_id, bid_id, item_description, old_price, new_price):
    """Notify a bidder that they have been outbid."""
    return notify(
        user_id=previous_bidder_id,
        notification_type='outbid',
        title="You've Been Outbid",
        body=(
            f'Your bid on {item_description} at ${old_price:.2f} was outbid '
            f'— the current best offer is ${new_price:.2f}.'
        ),
        related_bid_id=bid_id,
        metadata={
            'item_description': item_description,
            'old_price': old_price,
            'new_price': new_price,
        },
    )


def notify_bid_withdrawn(bidder_id, bid_id, item_description):
    """Confirm to a bidder that their bid was withdrawn."""
    return notify(
        user_id=bidder_id,
        notification_type='bid_withdrawn',
        title='Bid Withdrawn',
        body=f'Your bid for {item_description} has been withdrawn.',
        related_bid_id=bid_id,
        metadata={'item_description': item_description},
    )


def notify_bid_on_bucket(seller_id, bidder_username, bucket_id,
                         item_description, bid_price, quantity):
    """Notify a seller that a bid was placed on a bucket containing their listing (legacy alias)."""
    bid_id = None
    return notify(
        user_id=seller_id,
        notification_type='bid_on_bucket',
        title='New Bid on Your Listing',
        body=(
            f'{bidder_username} placed a bid for {quantity} unit(s) of '
            f'{item_description} at ${bid_price:.2f}/unit. '
            f'The bid will auto-fill if it meets your price.'
        ),
        metadata={
            'bucket_id': bucket_id,
            'bidder_username': bidder_username,
            'quantity': quantity,
            'bid_price': bid_price,
            'item_description': item_description,
        },
    )


def notify_bid_accepted(buyer_id, order_id, bid_id, item_description,
                        quantity_filled, price_per_unit, total_amount,
                        is_partial=False, remaining_quantity=0):
    """Notify a buyer that their bid was accepted (full or partial)."""
    ntype = 'bid_partially_accepted' if is_partial else 'bid_fully_filled'
    if is_partial:
        title = f'Bid Partially Filled – {quantity_filled} Unit(s)'
        body = (
            f'Your bid for {item_description} was partially filled. '
            f'{quantity_filled} unit(s) at ${price_per_unit:.2f} each '
            f'(${total_amount:.2f} total). {remaining_quantity} unit(s) still pending.'
        )
    else:
        title = f'Bid Filled – {quantity_filled} Unit(s)'
        body = (
            f'Your bid for {item_description} was filled! '
            f'{quantity_filled} unit(s) at ${price_per_unit:.2f} each '
            f'(${total_amount:.2f} total). Check your Orders tab.'
        )
    return notify(
        user_id=buyer_id,
        notification_type=ntype,
        title=title,
        body=body,
        related_order_id=order_id,
        related_bid_id=bid_id,
        metadata={
            'quantity': quantity_filled,
            'price_per_unit': price_per_unit,
            'total_amount': total_amount,
            'item_description': item_description,
            'is_partial': is_partial,
            'remaining_quantity': remaining_quantity,
        },
    )


def notify_bid_rejected_or_expired(bidder_id, bid_id, item_description):
    """Notify a bidder that their bid expired or was rejected."""
    return notify(
        user_id=bidder_id,
        notification_type='bid_rejected_or_expired',
        title='Bid Expired',
        body=f'Your bid for {item_description} has expired without being filled.',
        related_bid_id=bid_id,
        metadata={'item_description': item_description},
    )


# ---------------------------------------------------------------------------
# Legacy alias – many callers use notify_bid_filled
# ---------------------------------------------------------------------------

def notify_bid_filled(buyer_id, order_id, bid_id, item_description, quantity_filled,
                      price_per_unit, total_amount, is_partial=False, remaining_quantity=0):
    """
    Notify a buyer that their bid has been filled.
    Thin wrapper around notify_bid_accepted that also fires the legacy
    'bid_filled' type so existing notification rows keep working.
    """
    return notify(
        user_id=buyer_id,
        notification_type='bid_filled',
        title=(
            f'Bid Partially Filled – {quantity_filled} Unit(s)!'
            if is_partial else
            f'Bid Filled – {quantity_filled} Unit(s)!'
        ),
        body=(
            f'Your bid for {item_description} was partially filled. '
            f'{quantity_filled} unit(s) at ${price_per_unit:.2f} each '
            f'(${total_amount:.2f} total). {remaining_quantity} unit(s) still pending.'
            if is_partial else
            f'Your bid for {item_description} was filled! '
            f'{quantity_filled} unit(s) at ${price_per_unit:.2f} each '
            f'(${total_amount:.2f} total). Check your Orders tab.'
        ),
        related_order_id=order_id,
        related_bid_id=bid_id,
        metadata={
            'quantity': quantity_filled,
            'price_per_unit': price_per_unit,
            'total_amount': total_amount,
            'item_description': item_description,
            'is_partial': is_partial,
            'remaining_quantity': remaining_quantity,
        },
    )


# ---------------------------------------------------------------------------
# ── Orders (buyer) ──────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

def notify_order_created(buyer_id, order_id, item_description,
                         quantity, price_per_unit, total_amount):
    """Notify a buyer that their order was placed."""
    return notify(
        user_id=buyer_id,
        notification_type='order_created',
        title='Order Placed',
        body=(
            f'Your order for {quantity} unit(s) of {item_description} '
            f'(${total_amount:.2f} total) was placed successfully.'
        ),
        related_order_id=order_id,
        metadata={
            'quantity': quantity,
            'price_per_unit': price_per_unit,
            'total_amount': total_amount,
            'item_description': item_description,
        },
    )


def notify_order_confirmed(buyer_id, order_id, item_description,
                           quantity_purchased, price_per_unit, total_amount):
    """Legacy alias for notify_order_created."""
    return notify(
        user_id=buyer_id,
        notification_type='order_confirmed',
        title=f'Order Confirmed – {quantity_purchased} Unit(s)!',
        body=(
            f'Your purchase of {item_description} was confirmed! '
            f'{quantity_purchased} unit(s) at ${price_per_unit:.2f} each '
            f'(${total_amount:.2f} total). Check your Orders tab.'
        ),
        related_order_id=order_id,
        metadata={
            'quantity': quantity_purchased,
            'price_per_unit': price_per_unit,
            'total_amount': total_amount,
            'item_description': item_description,
        },
    )


def notify_order_shipped(buyer_id, order_id, item_description, tracking_number=None):
    """Notify a buyer that their order has shipped."""
    body = f'Your order for {item_description} has been shipped.'
    if tracking_number:
        body += f' Tracking: {tracking_number}.'
    return notify(
        user_id=buyer_id,
        notification_type='order_shipped',
        title='Order Shipped',
        body=body,
        related_order_id=order_id,
        metadata={'item_description': item_description, 'tracking_number': tracking_number},
    )


def notify_tracking_updated(buyer_id, order_id, item_description, tracking_number):
    """Notify a buyer that tracking info was updated."""
    return notify(
        user_id=buyer_id,
        notification_type='tracking_updated',
        title='Tracking Updated',
        body=f'Tracking for your order ({item_description}) was updated: {tracking_number}.',
        related_order_id=order_id,
        metadata={'item_description': item_description, 'tracking_number': tracking_number},
    )


def notify_order_status_updated(buyer_id, order_id, item_description, new_status):
    """Notify a buyer that their order status changed."""
    return notify(
        user_id=buyer_id,
        notification_type='order_status_updated',
        title='Order Status Updated',
        body=f'Your order for {item_description} is now: {new_status}.',
        related_order_id=order_id,
        metadata={'item_description': item_description, 'status': new_status},
    )


def notify_delivered_confirmed(buyer_id, order_id, item_description):
    """Notify a buyer that their order has been delivered."""
    return notify(
        user_id=buyer_id,
        notification_type='delivered_confirmed',
        title='Order Delivered',
        body=f'Your order for {item_description} has been delivered.',
        related_order_id=order_id,
        metadata={'item_description': item_description},
    )


# ---------------------------------------------------------------------------
# ── Cancellations ────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

def notify_cancel_request_submitted(requester_id, order_id, item_description):
    """Notify a buyer that their cancellation request was submitted."""
    return notify(
        user_id=requester_id,
        notification_type='cancel_request_submitted',
        title='Cancellation Request Submitted',
        body=(
            f'Your cancellation request for order #{order_id} ({item_description}) '
            f'was submitted. The seller(s) will be notified.'
        ),
        related_order_id=order_id,
        metadata={'order_id': order_id, 'item_description': item_description},
    )


def notify_cancellation_requested_seller(seller_id, order_id, item_description, reason=''):
    """Notify a seller that a buyer requested cancellation."""
    body = f'A buyer requested cancellation for order #{order_id} ({item_description}).'
    if reason:
        body += f' Reason: {reason}'
    return notify(
        user_id=seller_id,
        notification_type='seller_cancellation_request_received',
        title='Cancellation Request Received',
        body=body,
        related_order_id=order_id,
        metadata={'order_id': order_id, 'item_description': item_description, 'reason': reason},
    )


def notify_cancellation_denied(buyer_id, order_id, item_description):
    """Notify a buyer that their cancellation was denied."""
    return notify(
        user_id=buyer_id,
        notification_type='cancellation_denied',
        title='Cancellation Request Denied',
        body=(
            f'Your cancellation request for order #{order_id} ({item_description}) '
            f'was denied. The order will proceed as normal.'
        ),
        related_order_id=order_id,
        metadata={'order_id': order_id, 'item_description': item_description},
    )


def notify_cancellation_approved(buyer_id, order_id, item_description):
    """Notify a buyer that their cancellation was approved."""
    return notify(
        user_id=buyer_id,
        notification_type='cancellation_approved',
        title='Order Cancelled',
        body=(
            f'Your cancellation request for order #{order_id} ({item_description}) '
            f'was approved. The order has been cancelled.'
        ),
        related_order_id=order_id,
        metadata={'order_id': order_id, 'item_description': item_description},
    )


def notify_seller_cancellation_finalized(seller_id, order_id, item_description, approved):
    """Notify a seller that a cancellation request was finalized."""
    outcome = 'approved' if approved else 'denied'
    title = f'Cancellation {outcome.capitalize()}'
    body = (
        f'The cancellation for order #{order_id} ({item_description}) '
        f'has been {outcome}.'
    )
    return notify(
        user_id=seller_id,
        notification_type='seller_cancellation_finalized',
        title=title,
        body=body,
        related_order_id=order_id,
        metadata={'order_id': order_id, 'item_description': item_description, 'outcome': outcome},
    )


# ---------------------------------------------------------------------------
# ── Sales (seller) ──────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

def notify_seller_order_received(seller_id, order_id, listing_id,
                                  item_description, quantity_sold,
                                  price_per_unit, total_amount, shipping_address=''):
    """Notify a seller that an order was received for their listing."""
    return notify(
        user_id=seller_id,
        notification_type='seller_order_received',
        title='New Order Received',
        body=(
            f'You sold {quantity_sold} unit(s) of {item_description} '
            f'for ${total_amount:.2f}. Please ship to the buyer soon!'
        ),
        related_order_id=order_id,
        related_listing_id=listing_id,
        metadata={
            'quantity': quantity_sold,
            'price_per_unit': price_per_unit,
            'total_amount': total_amount,
            'item_description': item_description,
            'shipping_address': shipping_address,
        },
    )


def notify_listing_sold(seller_id, order_id, listing_id, item_description,
                        quantity_sold, price_per_unit, total_amount, shipping_address,
                        is_partial=False, remaining_quantity=0):
    """Legacy alias for notify_seller_order_received."""
    if is_partial:
        title = f'Listing Partially Sold – {quantity_sold} Unit(s)!'
        body = (
            f'Your listing for {item_description} was partially sold. '
            f'{quantity_sold} unit(s) at ${price_per_unit:.2f} each '
            f'(${total_amount:.2f} total). {remaining_quantity} unit(s) remain.'
        )
    else:
        title = f'Listing Sold – {quantity_sold} Unit(s)!'
        body = (
            f'Your listing for {item_description} was sold! '
            f'{quantity_sold} unit(s) at ${price_per_unit:.2f} each '
            f'(${total_amount:.2f} total). Please ship soon!'
        )
    return notify(
        user_id=seller_id,
        notification_type='listing_sold',
        title=title,
        body=body,
        related_order_id=order_id,
        related_listing_id=listing_id,
        metadata={
            'quantity': quantity_sold,
            'price_per_unit': price_per_unit,
            'total_amount': total_amount,
            'item_description': item_description,
            'shipping_address': shipping_address,
            'is_partial': is_partial,
            'remaining_quantity': remaining_quantity,
        },
    )


# ---------------------------------------------------------------------------
# ── Messages ────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

def notify_new_message(receiver_id, sender_id, order_id, message_preview):
    """Notify a user that they received a new order message."""
    conn = _get_conn()
    sender = conn.execute('SELECT username FROM users WHERE id = ?', (sender_id,)).fetchone()
    conn.close()
    sender_username = sender['username'] if sender else 'Someone'

    if len(message_preview) > 100:
        message_preview = message_preview[:97] + '...'

    ntype = 'new_order_message' if order_id else 'new_direct_message'
    return notify(
        user_id=receiver_id,
        notification_type=ntype,
        title=f'New message from {sender_username}',
        body=message_preview or 'You have a new message.',
        related_order_id=order_id,
        metadata={
            'sender_id': sender_id,
            'sender_username': sender_username,
            'order_id': order_id,
        },
    )


# ---------------------------------------------------------------------------
# ── Ratings ─────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

def notify_rating_received(user_id, rater_username, rating_value, order_id):
    """Notify a user that they received a rating."""
    stars = '★' * rating_value + '☆' * (5 - rating_value)
    return notify(
        user_id=user_id,
        notification_type='rating_received',
        title=f'New Rating Received – {stars}',
        body=f'{rater_username} rated you {rating_value}/5 stars.',
        related_order_id=order_id,
        metadata={
            'rater_username': rater_username,
            'rating_value': rating_value,
            'order_id': order_id,
        },
    )


def notify_rating_submitted(rater_id, ratee_username, rating_value, order_id):
    """Confirm to a user that their rating was submitted."""
    stars = '★' * rating_value + '☆' * (5 - rating_value)
    return notify(
        user_id=rater_id,
        notification_type='rating_submitted',
        title='Rating Submitted',
        body=f'Your {rating_value}-star rating ({stars}) for {ratee_username} was submitted.',
        related_order_id=order_id,
        metadata={
            'ratee_username': ratee_username,
            'rating_value': rating_value,
            'order_id': order_id,
        },
    )


# ---------------------------------------------------------------------------
# ── Account / Security ────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

def notify_new_login(user_id, ip_address=None, user_agent=None):
    """Notify a user of a new login to their account."""
    body = 'A new login to your account was detected.'
    if ip_address:
        body += f' IP: {ip_address}.'
    return notify(
        user_id=user_id,
        notification_type='new_login',
        title='New Login Detected',
        body=body,
        metadata={'ip_address': ip_address, 'user_agent': user_agent},
    )


def notify_password_changed(user_id):
    """Notify a user that their password was changed."""
    return notify(
        user_id=user_id,
        notification_type='password_changed',
        title='Password Changed',
        body='Your account password was changed. If this was not you, contact support immediately.',
    )


def notify_email_changed(user_id, new_email):
    """Notify a user that their email was changed."""
    return notify(
        user_id=user_id,
        notification_type='email_changed',
        title='Email Address Changed',
        body=f'Your account email was updated to {new_email}.',
        metadata={'new_email': new_email},
    )


# ---------------------------------------------------------------------------
# ── Reports ─────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

def notify_report_submitted(reporter_id, reported_username, report_id):
    """Notify a user that their report was submitted."""
    return notify(
        user_id=reporter_id,
        notification_type='report_submitted',
        title='Report Submitted',
        body=(
            f'Your report against {reported_username} was submitted and is under review.'
        ),
        metadata={'reported_username': reported_username, 'report_id': report_id},
    )
