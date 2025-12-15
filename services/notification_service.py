"""
Notification Service
Handles creating and managing user notifications
"""

from database import get_db_connection
from services.email_service import send_bid_filled_email, send_listing_sold_email
from datetime import datetime
import json


def create_notification(user_id, notification_type, title, message, related_order_id=None,
                       related_bid_id=None, related_listing_id=None, metadata=None):
    """
    Create a new notification for a user

    Args:
        user_id: ID of the user to notify
        notification_type: Type of notification ('bid_filled', 'listing_sold')
        title: Short title for the notification
        message: Detailed message
        related_order_id: Optional related order ID
        related_bid_id: Optional related bid ID
        related_listing_id: Optional related listing ID
        metadata: Optional dict of additional data (will be JSON encoded)

    Returns:
        int: ID of created notification, or None if failed
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        metadata_json = json.dumps(metadata) if metadata else None

        cursor.execute('''
            INSERT INTO notifications (
                user_id, type, title, message, related_order_id,
                related_bid_id, related_listing_id, metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id, notification_type, title, message,
            related_order_id, related_bid_id, related_listing_id,
            metadata_json
        ))

        notification_id = cursor.lastrowid
        conn.commit()
        conn.close()

        print(f"[NOTIFICATION] Created notification #{notification_id} for user {user_id}: {title}")
        return notification_id

    except Exception as e:
        print(f"[NOTIFICATION ERROR] Failed to create notification: {e}")
        conn.close()
        return None


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


def get_user_notifications(user_id, unread_only=False, limit=50):
    """
    Get notifications for a user

    Args:
        user_id: ID of the user
        unread_only: If True, only return unread notifications
        limit: Maximum number of notifications to return

    Returns:
        list: List of notification dicts
    """
    conn = get_db_connection()

    query = '''
        SELECT * FROM notifications
        WHERE user_id = ?
    '''

    params = [user_id]

    if unread_only:
        query += ' AND is_read = 0'

    query += ' ORDER BY created_at DESC LIMIT ?'
    params.append(limit)

    notifications = conn.execute(query, params).fetchall()
    conn.close()

    # Convert to dicts and parse JSON metadata
    result = []
    for notif in notifications:
        notif_dict = dict(notif)
        if notif_dict['metadata']:
            try:
                notif_dict['metadata'] = json.loads(notif_dict['metadata'])
            except:
                notif_dict['metadata'] = None
        result.append(notif_dict)

    return result


def mark_notification_read(notification_id):
    """Mark a notification as read"""
    conn = get_db_connection()
    conn.execute('''
        UPDATE notifications
        SET is_read = 1, read_at = ?
        WHERE id = ?
    ''', (datetime.now(), notification_id))
    conn.commit()
    conn.close()
    print(f"[NOTIFICATION] Marked notification #{notification_id} as read")
    return True


def delete_notification(notification_id, user_id):
    """
    Delete a notification (with user ownership check)

    Args:
        notification_id: ID of notification to delete
        user_id: ID of user (for ownership verification)

    Returns:
        bool: True if deleted successfully
    """
    conn = get_db_connection()

    # Verify ownership before deleting
    result = conn.execute(
        'DELETE FROM notifications WHERE id = ? AND user_id = ?',
        (notification_id, user_id)
    )

    deleted = result.rowcount > 0
    conn.commit()
    conn.close()

    if deleted:
        print(f"[NOTIFICATION] Deleted notification #{notification_id}")
    else:
        print(f"[NOTIFICATION ERROR] Could not delete notification #{notification_id} (not found or wrong user)")

    return deleted


def get_unread_count(user_id):
    """Get count of unread notifications for a user"""
    conn = get_db_connection()
    result = conn.execute(
        'SELECT COUNT(*) as count FROM notifications WHERE user_id = ? AND is_read = 0',
        (user_id,)
    ).fetchone()
    conn.close()

    return result['count'] if result else 0
