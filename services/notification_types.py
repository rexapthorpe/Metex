"""
Notification Types - Specific notification creation functions.

Each function creates a notification for a specific event type:
- notify_bid_filled: Buyer's bid was filled
- notify_order_confirmed: Buyer's order confirmed
- notify_listing_sold: Seller's listing was sold
- notify_new_message: User received a message
- notify_bid_placed: Bidder's bid was placed
- notify_bid_on_bucket: Seller received bid on their bucket
- notify_rating_received: User received a rating
- notify_report_submitted: User's report was submitted
- notify_cancel_request_submitted: User's cancel request was submitted
- notify_rating_submitted: User's rating was submitted

Extracted from notification_service.py during refactor - NO BEHAVIOR CHANGE.
"""

from database import get_db_connection
from services.email_service import send_bid_filled_email, send_listing_sold_email
from .notification_service import create_notification


def notify_bid_filled(buyer_id, order_id, bid_id, item_description, quantity_filled,
                      price_per_unit, total_amount, is_partial=False, remaining_quantity=0):
    """
    Notify a buyer that their bid has been filled

    Args:
        buyer_id: ID of the buyer
        order_id: ID of the created order
        bid_id: ID of the bid that was filled
        item_description: Description of the item
        quantity_filled: How many units were filled
        price_per_unit: Price per unit
        total_amount: Total amount for this fill
        is_partial: Whether this is a partial fill
        remaining_quantity: Remaining quantity if partial

    Returns:
        bool: True if notification created successfully
    """
    # Get buyer info and preferences
    conn = get_db_connection()
    buyer = conn.execute('SELECT username, email FROM users WHERE id = ?', (buyer_id,)).fetchone()

    # Get user notification preferences (default to enabled if not set)
    prefs = conn.execute('SELECT * FROM user_preferences WHERE user_id = ?', (buyer_id,)).fetchone()
    conn.close()

    if not buyer:
        print(f"[NOTIFICATION ERROR] Buyer {buyer_id} not found")
        return False

    # Determine what notifications to send based on preferences
    send_email = True if not prefs else bool(prefs['email_bid_filled'])
    send_inapp = True if not prefs else bool(prefs['inapp_bid_filled'])

    # If both are disabled, skip notification
    if not send_email and not send_inapp:
        print(f"[NOTIFICATION] User {buyer_id} has disabled all bid_filled notifications")
        return False  # No notifications sent

    # Create in-app notification if enabled
    notification_id = None
    if send_inapp:
        if is_partial:
            title = f"Bid Partially Filled - {quantity_filled} Units!"
            message = f"Your bid for {item_description} has been partially filled. {quantity_filled} units purchased at ${price_per_unit:.2f} each (${total_amount:.2f} total). {remaining_quantity} units still pending."
        else:
            title = f"Bid Filled - {quantity_filled} Units!"
            message = f"Your bid for {item_description} has been filled! {quantity_filled} units purchased at ${price_per_unit:.2f} each (${total_amount:.2f} total). Check your Orders tab for details."

        metadata = {
            'quantity': quantity_filled,
            'price_per_unit': price_per_unit,
            'total_amount': total_amount,
            'item_description': item_description,
            'is_partial': is_partial,
            'remaining_quantity': remaining_quantity
        }

        notification_id = create_notification(
            user_id=buyer_id,
            notification_type='bid_filled',
            title=title,
            message=message,
            related_order_id=order_id,
            related_bid_id=bid_id,
            metadata=metadata
        )

    # Send email notification if enabled
    if send_email and buyer['email']:
        try:
            # Build full URL for orders page
            base_url = 'http://127.0.0.1:5000'  # TODO: Get from config or request
            orders_url = f"{base_url}/account#orders"

            send_bid_filled_email(
                to_email=buyer['email'],
                username=buyer['username'],
                item_description=item_description,
                quantity=quantity_filled,
                price_per_unit=price_per_unit,
                total_amount=total_amount,
                partial=is_partial,
                remaining_quantity=remaining_quantity,
                orders_url=orders_url
            )
        except Exception as e:
            print(f"[EMAIL ERROR] Failed to send bid filled email: {e}")

    return True


def notify_order_confirmed(buyer_id, order_id, item_description, quantity_purchased,
                           price_per_unit, total_amount):
    """
    Notify a buyer that their order has been confirmed (for normal purchases, not bid fills)

    Args:
        buyer_id: ID of the buyer
        order_id: ID of the created order
        item_description: Description of the item
        quantity_purchased: How many units were purchased
        price_per_unit: Price per unit
        total_amount: Total amount for the purchase

    Returns:
        bool: True if notification created successfully
    """
    # Get buyer info and preferences
    conn = get_db_connection()
    buyer = conn.execute('SELECT username, email FROM users WHERE id = ?', (buyer_id,)).fetchone()

    # Get user notification preferences (default to enabled if not set)
    # For now, we'll use the bid_filled preferences as a base
    # TODO: Add separate order_confirmed preferences in future migration
    prefs = conn.execute('SELECT * FROM user_preferences WHERE user_id = ?', (buyer_id,)).fetchone()
    conn.close()

    if not buyer:
        print(f"[NOTIFICATION ERROR] Buyer {buyer_id} not found")
        return False

    # Use bid_filled preferences as default for order notifications
    # This ensures buyers who want notifications for purchases will get them
    send_email = True if not prefs else bool(prefs['email_bid_filled'])
    send_inapp = True if not prefs else bool(prefs['inapp_bid_filled'])

    # If both are disabled, skip notification
    if not send_email and not send_inapp:
        print(f"[NOTIFICATION] User {buyer_id} has disabled all purchase notifications")
        return False

    # Create in-app notification if enabled
    notification_id = None
    if send_inapp:
        title = f"Order Confirmed - {quantity_purchased} Units!"
        message = f"Your purchase of {item_description} has been confirmed! {quantity_purchased} units at ${price_per_unit:.2f} each (${total_amount:.2f} total). Check your Orders tab for details."

        metadata = {
            'quantity': quantity_purchased,
            'price_per_unit': price_per_unit,
            'total_amount': total_amount,
            'item_description': item_description
        }

        notification_id = create_notification(
            user_id=buyer_id,
            notification_type='order_confirmed',
            title=title,
            message=message,
            related_order_id=order_id,
            metadata=metadata
        )

    # Send email notification if enabled
    # For now, we'll use a simplified email approach
    # TODO: Create dedicated order_confirmed email template in future
    if send_email and buyer['email']:
        try:
            # Build full URL for orders page
            base_url = 'http://127.0.0.1:5000'  # TODO: Get from config or request
            orders_url = f"{base_url}/account#orders"

            # For now, reuse bid_filled email format with adjusted text
            # This can be replaced with a dedicated email template later
            send_bid_filled_email(
                to_email=buyer['email'],
                username=buyer['username'],
                item_description=item_description,
                quantity=quantity_purchased,
                price_per_unit=price_per_unit,
                total_amount=total_amount,
                partial=False,
                remaining_quantity=0,
                orders_url=orders_url
            )
        except Exception as e:
            print(f"[EMAIL ERROR] Failed to send order confirmed email: {e}")

    return True


def notify_listing_sold(seller_id, order_id, listing_id, item_description, quantity_sold,
                        price_per_unit, total_amount, shipping_address, is_partial=False,
                        remaining_quantity=0):
    """
    Notify a seller that their listing has been sold

    Args:
        seller_id: ID of the seller
        order_id: ID of the created order
        listing_id: ID of the listing that was sold
        item_description: Description of the item
        quantity_sold: How many units were sold
        price_per_unit: Price per unit
        total_amount: Total sale amount
        shipping_address: Where to ship the items
        is_partial: Whether this is a partial sale
        remaining_quantity: Remaining quantity in listing if partial

    Returns:
        bool: True if notification created successfully
    """
    # Get seller info and preferences
    conn = get_db_connection()
    seller = conn.execute('SELECT username, email FROM users WHERE id = ?', (seller_id,)).fetchone()

    # Get user notification preferences (default to enabled if not set)
    prefs = conn.execute('SELECT * FROM user_preferences WHERE user_id = ?', (seller_id,)).fetchone()
    conn.close()

    if not seller:
        print(f"[NOTIFICATION ERROR] Seller {seller_id} not found")
        return False

    # Determine what notifications to send based on preferences
    send_email = True if not prefs else bool(prefs['email_listing_sold'])
    send_inapp = True if not prefs else bool(prefs['inapp_listing_sold'])

    # If both are disabled, skip notification
    if not send_email and not send_inapp:
        print(f"[NOTIFICATION] User {seller_id} has disabled all listing_sold notifications")
        return False  # No notifications sent

    # Create in-app notification if enabled
    notification_id = None
    if send_inapp:
        if is_partial:
            title = f"Listing Partially Sold - {quantity_sold} Units!"
            message = f"Your listing for {item_description} has been partially sold. {quantity_sold} units sold at ${price_per_unit:.2f} each (${total_amount:.2f} total). {remaining_quantity} units remain available. Please ship to the buyer soon!"
        else:
            title = f"Listing Sold - {quantity_sold} Units!"
            message = f"Your listing for {item_description} has been sold! {quantity_sold} units sold at ${price_per_unit:.2f} each (${total_amount:.2f} total). Please ship to the buyer soon!"

        metadata = {
            'quantity': quantity_sold,
            'price_per_unit': price_per_unit,
            'total_amount': total_amount,
            'item_description': item_description,
            'shipping_address': shipping_address,
            'is_partial': is_partial,
            'remaining_quantity': remaining_quantity
        }

        notification_id = create_notification(
            user_id=seller_id,
            notification_type='listing_sold',
            title=title,
            message=message,
            related_order_id=order_id,
            related_listing_id=listing_id,
            metadata=metadata
        )

    # Send email notification if enabled
    if send_email and seller['email']:
        try:
            # Build full URL for sold tab
            base_url = 'http://127.0.0.1:5000'  # TODO: Get from config or request
            sold_tab_url = f"{base_url}/account#sold"

            send_listing_sold_email(
                to_email=seller['email'],
                username=seller['username'],
                item_description=item_description,
                quantity=quantity_sold,
                price_per_unit=price_per_unit,
                total_amount=total_amount,
                shipping_address=shipping_address,
                partial=is_partial,
                remaining_quantity=remaining_quantity,
                sold_tab_url=sold_tab_url
            )
        except Exception as e:
            print(f"[EMAIL ERROR] Failed to send listing sold email: {e}")

    return True


def notify_new_message(receiver_id, sender_id, order_id, message_preview):
    """
    Notify a user that they received a new message

    Args:
        receiver_id: ID of the message recipient
        sender_id: ID of the message sender
        order_id: ID of the related order
        message_preview: Short preview of the message content

    Returns:
        bool: True if notification created successfully
    """
    # Get receiver info and preferences
    conn = get_db_connection()
    receiver = conn.execute('SELECT username FROM users WHERE id = ?', (receiver_id,)).fetchone()
    sender = conn.execute('SELECT username FROM users WHERE id = ?', (sender_id,)).fetchone()

    # Get user notification preferences (default to enabled if not set)
    prefs = conn.execute('SELECT * FROM user_preferences WHERE user_id = ?', (receiver_id,)).fetchone()
    conn.close()

    if not receiver or not sender:
        print(f"[NOTIFICATION ERROR] Receiver {receiver_id} or sender {sender_id} not found")
        return False

    # Check if in-app message notifications are enabled
    send_inapp = True if not prefs else bool(prefs['inapp_messages']) if 'inapp_messages' in prefs.keys() else True

    if not send_inapp:
        print(f"[NOTIFICATION] User {receiver_id} has disabled message notifications")
        return False

    # Create in-app notification
    # Truncate message preview if too long
    if len(message_preview) > 100:
        message_preview = message_preview[:97] + '...'

    title = f"New message from {sender['username']}"
    message = message_preview if message_preview else "You have a new message"

    metadata = {
        'sender_id': sender_id,
        'sender_username': sender['username'],
        'order_id': order_id
    }

    notification_id = create_notification(
        user_id=receiver_id,
        notification_type='new_message',
        title=title,
        message=message,
        related_order_id=order_id,
        metadata=metadata
    )

    return notification_id is not None


def notify_bid_placed(bidder_id, bid_id, bucket_id, item_description, quantity, price_per_unit):
    """
    Notify a bidder that their bid has been placed successfully

    Args:
        bidder_id: ID of the bidder
        bid_id: ID of the created bid
        bucket_id: ID of the bucket being bid on
        item_description: Description of the item
        quantity: Number of units bid for
        price_per_unit: Price per unit offered

    Returns:
        bool: True if notification created successfully
    """
    conn = get_db_connection()
    bidder = conn.execute('SELECT username FROM users WHERE id = ?', (bidder_id,)).fetchone()
    prefs = conn.execute('SELECT * FROM user_preferences WHERE user_id = ?', (bidder_id,)).fetchone()
    conn.close()

    if not bidder:
        print(f"[NOTIFICATION ERROR] Bidder {bidder_id} not found")
        return False

    # Check if in-app notifications are enabled (default to True)
    send_inapp = True if not prefs else bool(prefs.get('inapp_bid_filled', 1))

    if not send_inapp:
        print(f"[NOTIFICATION] User {bidder_id} has disabled bid notifications")
        return False

    total_amount = quantity * price_per_unit
    title = "Bid Placed Successfully"
    message = f"Your bid for {quantity} units of {item_description} at ${price_per_unit:.2f}/unit (${total_amount:.2f} total) has been placed. You'll be notified when it's filled."

    metadata = {
        'bucket_id': bucket_id,
        'quantity': quantity,
        'price_per_unit': price_per_unit,
        'total_amount': total_amount,
        'item_description': item_description
    }

    notification_id = create_notification(
        user_id=bidder_id,
        notification_type='bid_placed',
        title=title,
        message=message,
        related_bid_id=bid_id,
        metadata=metadata
    )

    return notification_id is not None


def notify_bid_on_bucket(seller_id, bidder_username, bucket_id, item_description, bid_price, quantity):
    """
    Notify a seller that a bid was placed on a bucket containing their listing

    Args:
        seller_id: ID of the seller
        bidder_username: Username of the bidder
        bucket_id: ID of the bucket
        item_description: Description of the item
        bid_price: Price per unit offered
        quantity: Number of units being bid for

    Returns:
        bool: True if notification created successfully
    """
    conn = get_db_connection()
    seller = conn.execute('SELECT username FROM users WHERE id = ?', (seller_id,)).fetchone()
    prefs = conn.execute('SELECT * FROM user_preferences WHERE user_id = ?', (seller_id,)).fetchone()
    conn.close()

    if not seller:
        print(f"[NOTIFICATION ERROR] Seller {seller_id} not found")
        return False

    # Check if in-app notifications are enabled (default to True)
    send_inapp = True if not prefs else bool(prefs.get('inapp_listing_sold', 1))

    if not send_inapp:
        print(f"[NOTIFICATION] User {seller_id} has disabled listing notifications")
        return False

    total_amount = quantity * bid_price
    title = "New Bid on Your Listing"
    message = f"{bidder_username} placed a bid for {quantity} units of {item_description} at ${bid_price:.2f}/unit (${total_amount:.2f} total). The bid will auto-fill if it meets your price."

    metadata = {
        'bucket_id': bucket_id,
        'bidder_username': bidder_username,
        'quantity': quantity,
        'bid_price': bid_price,
        'total_amount': total_amount,
        'item_description': item_description
    }

    notification_id = create_notification(
        user_id=seller_id,
        notification_type='bid_on_bucket',
        title=title,
        message=message,
        metadata=metadata
    )

    return notification_id is not None


def notify_rating_received(user_id, rater_username, rating_value, order_id):
    """
    Notify a user that they received a rating

    Args:
        user_id: ID of the user being rated
        rater_username: Username of the person who rated them
        rating_value: The rating value (1-5)
        order_id: ID of the related order

    Returns:
        bool: True if notification created successfully
    """
    conn = get_db_connection()
    user = conn.execute('SELECT username FROM users WHERE id = ?', (user_id,)).fetchone()
    prefs = conn.execute('SELECT * FROM user_preferences WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()

    if not user:
        print(f"[NOTIFICATION ERROR] User {user_id} not found")
        return False

    # Check if in-app notifications are enabled (default to True)
    send_inapp = True if not prefs else bool(prefs.get('inapp_bid_filled', 1))

    if not send_inapp:
        print(f"[NOTIFICATION] User {user_id} has disabled notifications")
        return False

    # Create star display
    stars = '★' * rating_value + '☆' * (5 - rating_value)
    title = f"New Rating Received - {stars}"
    message = f"{rater_username} rated you {rating_value}/5 stars. Check your Ratings tab to view the full review."

    metadata = {
        'rater_username': rater_username,
        'rating_value': rating_value,
        'order_id': order_id
    }

    notification_id = create_notification(
        user_id=user_id,
        notification_type='rating_received',
        title=title,
        message=message,
        related_order_id=order_id,
        metadata=metadata
    )

    return notification_id is not None


def notify_report_submitted(reporter_id, reported_username, report_id):
    """
    Notify a user that their report was submitted successfully

    Args:
        reporter_id: ID of the user who submitted the report
        reported_username: Username of the reported user
        report_id: ID of the report

    Returns:
        bool: True if notification created successfully
    """
    conn = get_db_connection()
    reporter = conn.execute('SELECT username FROM users WHERE id = ?', (reporter_id,)).fetchone()
    conn.close()

    if not reporter:
        print(f"[NOTIFICATION ERROR] Reporter {reporter_id} not found")
        return False

    title = "Report Submitted"
    message = f"Your report against {reported_username} has been submitted and is under review. An admin will review it shortly."

    metadata = {
        'reported_username': reported_username,
        'report_id': report_id
    }

    notification_id = create_notification(
        user_id=reporter_id,
        notification_type='report_submitted',
        title=title,
        message=message,
        metadata=metadata
    )

    return notification_id is not None


def notify_cancel_request_submitted(requester_id, order_id, item_description):
    """
    Notify a user that their cancellation request was submitted

    Args:
        requester_id: ID of the user who submitted the request
        order_id: ID of the order being cancelled
        item_description: Description of the item in the order

    Returns:
        bool: True if notification created successfully
    """
    conn = get_db_connection()
    requester = conn.execute('SELECT username FROM users WHERE id = ?', (requester_id,)).fetchone()
    conn.close()

    if not requester:
        print(f"[NOTIFICATION ERROR] Requester {requester_id} not found")
        return False

    title = "Cancellation Request Submitted"
    message = f"Your cancellation request for order #{order_id} ({item_description}) has been submitted. The other party will be notified and can accept or decline."

    metadata = {
        'order_id': order_id,
        'item_description': item_description
    }

    notification_id = create_notification(
        user_id=requester_id,
        notification_type='cancel_request_submitted',
        title=title,
        message=message,
        related_order_id=order_id,
        metadata=metadata
    )

    return notification_id is not None


def notify_rating_submitted(rater_id, ratee_username, rating_value, order_id):
    """
    Notify a user that their rating was successfully submitted

    Args:
        rater_id: ID of the user who submitted the rating
        ratee_username: Username of the person they rated
        rating_value: The rating value (1-5)
        order_id: ID of the related order

    Returns:
        bool: True if notification created successfully
    """
    conn = get_db_connection()
    rater = conn.execute('SELECT username FROM users WHERE id = ?', (rater_id,)).fetchone()
    conn.close()

    if not rater:
        print(f"[NOTIFICATION ERROR] Rater {rater_id} not found")
        return False

    stars = '★' * rating_value + '☆' * (5 - rating_value)
    title = "Rating Submitted Successfully"
    message = f"Your {rating_value}-star rating ({stars}) for {ratee_username} has been submitted. Thank you for your feedback!"

    metadata = {
        'ratee_username': ratee_username,
        'rating_value': rating_value,
        'order_id': order_id
    }

    notification_id = create_notification(
        user_id=rater_id,
        notification_type='rating_submitted',
        title=title,
        message=message,
        related_order_id=order_id,
        metadata=metadata
    )

    return notification_id is not None
