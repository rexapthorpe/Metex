"""
Admin User Management Routes

This module contains user management routes for the admin panel.
Routes:
- /api/user/<user_id> - Get user details
- /api/user/<user_id>/ban - Ban/unban a user
- /api/user/<user_id>/freeze - Freeze/unfreeze a user
- /api/user/<user_id>/delete - Delete a user
- /api/user/<user_id>/message - Send message to user
- /api/user/<user_id>/messages - Get messages with user
- /api/conversations - Get admin conversations
- /api/order/<order_id> - Get order details

IMPORTANT: All route URLs and endpoint names are preserved from original admin_routes.py
"""

from flask import jsonify, request, session
from utils.auth_utils import admin_required
from . import admin_bp
from .dashboard import _format_time_ago


@admin_bp.route('/api/user/<int:user_id>')
@admin_required
def get_user_details(user_id):
    """Get detailed information about a user for admin modal"""
    from database import get_db_connection

    conn = get_db_connection()
    try:
        # Get user info
        user = conn.execute('''
            SELECT id, username, email, created_at, is_admin,
                   first_name, last_name, phone
            FROM users WHERE id = ?
        ''', (user_id,)).fetchone()

        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        # Get transaction stats
        buy_stats = conn.execute('''
            SELECT COUNT(*) as count, COALESCE(SUM(total_price), 0) as total
            FROM orders WHERE buyer_id = ?
        ''', (user_id,)).fetchone()

        sell_stats = conn.execute('''
            SELECT COUNT(DISTINCT o.id) as count, COALESCE(SUM(o.total_price), 0) as total
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            JOIN listings l ON oi.listing_id = l.id
            WHERE l.seller_id = ?
        ''', (user_id,)).fetchone()

        # Get listing count
        listings = conn.execute('''
            SELECT COUNT(*) as count FROM listings WHERE seller_id = ? AND active = 1
        ''', (user_id,)).fetchone()

        # Get active bids count
        bids = conn.execute('''
            SELECT COUNT(*) as count FROM bids WHERE buyer_id = ? AND status IN ('Open', 'Partially Filled')
        ''', (user_id,)).fetchone()

        # Get rating
        rating = conn.execute('''
            SELECT AVG(rating) as avg_rating, COUNT(*) as count
            FROM ratings WHERE ratee_id = ?
        ''', (user_id,)).fetchone()

        # Check if user is banned or frozen
        status = 'active'
        is_banned = conn.execute('SELECT is_banned FROM users WHERE id = ?', (user_id,)).fetchone()
        is_frozen = conn.execute('SELECT is_frozen FROM users WHERE id = ?', (user_id,)).fetchone()

        if is_banned and is_banned['is_banned']:
            status = 'banned'
        elif is_frozen and is_frozen['is_frozen']:
            status = 'frozen'

        return jsonify({
            'success': True,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'email': user['email'] or 'N/A',
                'first_name': user['first_name'] or '',
                'last_name': user['last_name'] or '',
                'phone': user['phone'] or 'N/A',
                'joined': _format_time_ago(user['created_at']),
                'joined_date': user['created_at'][:10] if user['created_at'] else 'Unknown',
                'is_admin': user['is_admin'],
                'status': status,
                'stats': {
                    'purchases': buy_stats['count'],
                    'purchase_total': buy_stats['total'],
                    'sales': sell_stats['count'],
                    'sales_total': sell_stats['total'],
                    'active_listings': listings['count'],
                    'active_bids': bids['count'],
                    'rating': round(rating['avg_rating'], 1) if rating['avg_rating'] else 0,
                    'rating_count': rating['count']
                }
            }
        })

    except Exception as e:
        print(f"Error getting user details: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/user/<int:user_id>/ban', methods=['POST'])
@admin_required
def ban_user(user_id):
    """Ban a user - closes all their listings and bids"""
    from database import get_db_connection

    conn = get_db_connection()
    try:
        # Check if user exists
        user = conn.execute('SELECT id, username, is_banned FROM users WHERE id = ?', (user_id,)).fetchone()
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        # Toggle ban status
        new_status = 0 if user['is_banned'] else 1

        if new_status == 1:  # Banning user
            # Close all active listings
            conn.execute('UPDATE listings SET active = 0 WHERE seller_id = ?', (user_id,))

            # Close all open bids
            conn.execute('''
                UPDATE bids SET status = 'Cancelled'
                WHERE buyer_id = ? AND status IN ('Open', 'Partially Filled')
            ''', (user_id,))

        # Update ban status
        conn.execute('UPDATE users SET is_banned = ? WHERE id = ?', (new_status, user_id))
        conn.commit()

        action = 'banned' if new_status else 'unbanned'
        return jsonify({
            'success': True,
            'message': f'User {user["username"]} has been {action}',
            'is_banned': new_status == 1
        })

    except Exception as e:
        print(f"Error banning user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/user/<int:user_id>/freeze', methods=['POST'])
@admin_required
def freeze_user(user_id):
    """Freeze a user - prevents buying, selling, and bidding"""
    from database import get_db_connection

    data = request.get_json() or {}
    reason = data.get('reason', '').strip()
    action_type = data.get('action')  # 'freeze' or 'unfreeze'

    conn = get_db_connection()
    try:
        # Check if user exists
        user = conn.execute('SELECT id, username, is_frozen FROM users WHERE id = ?', (user_id,)).fetchone()
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        # Determine new status based on action or toggle
        if action_type == 'freeze':
            new_status = 1
            if not reason:
                return jsonify({'success': False, 'error': 'Reason is required when freezing an account'}), 400
        elif action_type == 'unfreeze':
            new_status = 0
            reason = None  # Clear reason when unfreezing
        else:
            # Legacy toggle behavior (for backwards compatibility)
            new_status = 0 if user['is_frozen'] else 1
            if new_status == 1 and not reason:
                return jsonify({'success': False, 'error': 'Reason is required when freezing an account'}), 400
            if new_status == 0:
                reason = None

        # Update freeze status and reason
        conn.execute('UPDATE users SET is_frozen = ?, freeze_reason = ? WHERE id = ?', (new_status, reason, user_id))
        conn.commit()

        action = 'frozen' if new_status else 'unfrozen'
        return jsonify({
            'success': True,
            'message': f'User {user["username"]} account has been {action}',
            'is_frozen': new_status == 1
        })

    except Exception as e:
        print(f"Error freezing user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/user/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    """Permanently delete a user and all their associated data"""
    from database import get_db_connection

    conn = get_db_connection()
    try:
        # Check if user exists
        user = conn.execute('SELECT id, username FROM users WHERE id = ?', (user_id,)).fetchone()
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        # Prevent deleting yourself
        admin_id = session.get('user_id')
        if user_id == admin_id:
            return jsonify({'success': False, 'error': 'You cannot delete your own account'}), 400

        # Disable FK constraints temporarily for cascading deletes
        conn.execute('PRAGMA foreign_keys = OFF')

        deleted_counts = {}

        def safe_delete(sql, params=None):
            """Helper to safely execute delete and return count"""
            try:
                result = conn.execute(sql, params) if params else conn.execute(sql)
                return result.rowcount
            except Exception as e:
                print(f"[Delete User] Error executing: {sql[:50]}... - {e}")
                return 0

        # ========================================
        # 1. LISTING-RELATED DATA
        # ========================================
        listing_ids = [row['id'] for row in conn.execute(
            'SELECT id FROM listings WHERE seller_id = ?', (user_id,)
        ).fetchall()]

        if listing_ids:
            placeholders = ','.join('?' * len(listing_ids))

            # Delete set item photos
            deleted_counts['set_item_photos'] = safe_delete(f'''
                DELETE FROM listing_set_item_photos
                WHERE set_item_id IN (
                    SELECT id FROM listing_set_items WHERE listing_id IN ({placeholders})
                )
            ''', listing_ids)

            # Delete set items
            deleted_counts['set_items'] = safe_delete(
                f'DELETE FROM listing_set_items WHERE listing_id IN ({placeholders})', listing_ids)

            # Delete listing photos
            deleted_counts['listing_photos'] = safe_delete(
                f'DELETE FROM listing_photos WHERE listing_id IN ({placeholders})', listing_ids)

        # Delete listings
        deleted_counts['listings'] = safe_delete('DELETE FROM listings WHERE seller_id = ?', (user_id,))

        # ========================================
        # 2. ORDER-RELATED DATA
        # ========================================
        order_ids = [row['id'] for row in conn.execute(
            'SELECT id FROM orders WHERE buyer_id = ?', (user_id,)
        ).fetchall()]

        if order_ids:
            placeholders = ','.join('?' * len(order_ids))

            # Delete order items
            deleted_counts['order_items'] = safe_delete(
                f'DELETE FROM order_items WHERE order_id IN ({placeholders})', order_ids)

            # Delete tracking records
            deleted_counts['tracking'] = safe_delete(
                f'DELETE FROM tracking WHERE order_id IN ({placeholders})', order_ids)

            # Delete seller order tracking for these orders
            deleted_counts['seller_order_tracking'] = safe_delete(
                f'DELETE FROM seller_order_tracking WHERE order_id IN ({placeholders})', order_ids)

            # Delete cancellation seller responses
            deleted_counts['cancellation_responses'] = safe_delete(f'''
                DELETE FROM cancellation_seller_responses
                WHERE request_id IN (SELECT id FROM cancellation_requests WHERE order_id IN ({placeholders}))
            ''', order_ids)

            # Delete cancellation requests
            deleted_counts['cancellation_requests'] = safe_delete(
                f'DELETE FROM cancellation_requests WHERE order_id IN ({placeholders})', order_ids)

        # Delete orders where user is buyer
        deleted_counts['orders'] = safe_delete('DELETE FROM orders WHERE buyer_id = ?', (user_id,))

        # ========================================
        # 3. BID-RELATED DATA
        # ========================================
        bid_ids = [row['id'] for row in conn.execute(
            'SELECT id FROM bids WHERE buyer_id = ?', (user_id,)
        ).fetchall()]

        if bid_ids:
            placeholders = ','.join('?' * len(bid_ids))
            deleted_counts['bid_fills'] = safe_delete(
                f'DELETE FROM bid_fills WHERE bid_id IN ({placeholders})', bid_ids)

        deleted_counts['bids'] = safe_delete('DELETE FROM bids WHERE buyer_id = ?', (user_id,))

        # ========================================
        # 4. CART DATA (correct table name is 'cart')
        # ========================================
        deleted_counts['cart'] = safe_delete('DELETE FROM cart WHERE user_id = ?', (user_id,))

        # ========================================
        # 5. REPORTS DATA
        # ========================================
        report_ids = [row['id'] for row in conn.execute(
            'SELECT id FROM reports WHERE reporter_user_id = ? OR reported_user_id = ?', (user_id, user_id)
        ).fetchall()]

        if report_ids:
            placeholders = ','.join('?' * len(report_ids))
            deleted_counts['report_attachments'] = safe_delete(
                f'DELETE FROM report_attachments WHERE report_id IN ({placeholders})', report_ids)

        deleted_counts['reports'] = safe_delete(
            'DELETE FROM reports WHERE reporter_user_id = ? OR reported_user_id = ?', (user_id, user_id))

        # ========================================
        # 6. MESSAGING DATA
        # ========================================
        deleted_counts['messages'] = safe_delete(
            'DELETE FROM messages WHERE sender_id = ? OR receiver_id = ?', (user_id, user_id))
        deleted_counts['message_reads'] = safe_delete(
            'DELETE FROM message_reads WHERE user_id = ? OR participant_id = ?', (user_id, user_id))

        # ========================================
        # 7. RATINGS DATA
        # ========================================
        deleted_counts['ratings'] = safe_delete(
            'DELETE FROM ratings WHERE rater_id = ? OR ratee_id = ?', (user_id, user_id))

        # ========================================
        # 8. NOTIFICATION DATA
        # ========================================
        deleted_counts['notifications'] = safe_delete('DELETE FROM notifications WHERE user_id = ?', (user_id,))
        deleted_counts['notification_preferences'] = safe_delete(
            'DELETE FROM notification_preferences WHERE user_id = ?', (user_id,))

        # ========================================
        # 9. USER PREFERENCES
        # ========================================
        deleted_counts['user_preferences'] = safe_delete(
            'DELETE FROM user_preferences WHERE user_id = ?', (user_id,))

        # ========================================
        # 10. PORTFOLIO DATA
        # ========================================
        deleted_counts['portfolio_exclusions'] = safe_delete(
            'DELETE FROM portfolio_exclusions WHERE user_id = ?', (user_id,))
        deleted_counts['portfolio_snapshots'] = safe_delete(
            'DELETE FROM portfolio_snapshots WHERE user_id = ?', (user_id,))

        # ========================================
        # 11. ADDRESS DATA
        # ========================================
        deleted_counts['addresses'] = safe_delete('DELETE FROM addresses WHERE user_id = ?', (user_id,))

        # ========================================
        # 12. PRICE LOCKS
        # ========================================
        deleted_counts['price_locks'] = safe_delete('DELETE FROM price_locks WHERE user_id = ?', (user_id,))

        # ========================================
        # 13. CANCELLATION STATS
        # ========================================
        deleted_counts['cancellation_stats'] = safe_delete(
            'DELETE FROM user_cancellation_stats WHERE user_id = ?', (user_id,))

        # ========================================
        # 14. SELLER-RELATED DATA (as seller, not buyer)
        # ========================================
        deleted_counts['seller_tracking'] = safe_delete(
            'DELETE FROM seller_order_tracking WHERE seller_id = ?', (user_id,))
        deleted_counts['seller_cancellation_responses'] = safe_delete(
            'DELETE FROM cancellation_seller_responses WHERE seller_id = ?', (user_id,))

        # ========================================
        # 15. FINALLY DELETE THE USER
        # ========================================
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        deleted_counts['user'] = 1

        # Re-enable FK constraints
        conn.execute('PRAGMA foreign_keys = ON')
        conn.commit()

        # Calculate total deleted records
        total_deleted = sum(deleted_counts.values())

        print(f"[Admin] Successfully deleted user @{user['username']} (ID: {user_id})")
        print(f"[Admin] Deleted counts: {deleted_counts}")

        return jsonify({
            'success': True,
            'message': f'User @{user["username"]} and all associated data have been permanently deleted',
            'deleted_counts': deleted_counts,
            'total_deleted': total_deleted
        })

    except Exception as e:
        print(f"Error deleting user: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/users/bulk-freeze', methods=['POST'])
@admin_required
def bulk_freeze_users():
    """Freeze or unfreeze multiple users at once"""
    from database import get_db_connection

    data = request.get_json() or {}
    user_ids = data.get('user_ids', [])
    action = data.get('action', 'freeze')   # 'freeze' or 'unfreeze'
    reason = data.get('reason', '').strip()

    if not user_ids:
        return jsonify({'success': False, 'error': 'No users selected'}), 400
    if action == 'freeze' and not reason:
        return jsonify({'success': False, 'error': 'A reason is required when freezing accounts'}), 400

    new_status = 1 if action == 'freeze' else 0
    stored_reason = reason if action == 'freeze' else None

    conn = get_db_connection()
    try:
        count = 0
        admin_id = session.get('user_id')
        for uid in user_ids:
            # Skip admins and the requesting admin's own account
            user = conn.execute(
                'SELECT id FROM users WHERE id = ? AND is_admin = 0 AND id != ?',
                (uid, admin_id)
            ).fetchone()
            if user:
                conn.execute(
                    'UPDATE users SET is_frozen = ?, freeze_reason = ? WHERE id = ?',
                    (new_status, stored_reason, uid)
                )
                count += 1
        conn.commit()
        action_word = 'frozen' if new_status else 'unfrozen'
        return jsonify({
            'success': True,
            'message': f'{count} account{"s" if count != 1 else ""} {action_word} successfully',
            'count': count
        })
    except Exception as e:
        print(f"Error bulk freezing users: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/users/bulk-delete', methods=['POST'])
@admin_required
def bulk_delete_users():
    """Permanently delete multiple users and all their associated data"""
    from database import get_db_connection

    data = request.get_json() or {}
    user_ids = data.get('user_ids', [])

    if not user_ids:
        return jsonify({'success': False, 'error': 'No users selected'}), 400

    admin_id = session.get('user_id')
    conn = get_db_connection()
    try:
        conn.execute('PRAGMA foreign_keys = OFF')
        total_deleted = 0

        for user_id in user_ids:
            # Skip admins and the requesting admin's own account
            user = conn.execute(
                'SELECT id, username FROM users WHERE id = ? AND is_admin = 0 AND id != ?',
                (user_id, admin_id)
            ).fetchone()
            if not user:
                continue

            def safe_del(sql, params=None):
                try:
                    r = conn.execute(sql, params) if params else conn.execute(sql)
                    return r.rowcount
                except Exception as ex:
                    print(f"[bulk-delete] {sql[:60]} - {ex}")
                    return 0

            listing_ids = [r['id'] for r in conn.execute(
                'SELECT id FROM listings WHERE seller_id = ?', (user_id,)
            ).fetchall()]
            if listing_ids:
                ph = ','.join('?' * len(listing_ids))
                safe_del(f'DELETE FROM listing_set_item_photos WHERE set_item_id IN (SELECT id FROM listing_set_items WHERE listing_id IN ({ph}))', listing_ids)
                safe_del(f'DELETE FROM listing_set_items WHERE listing_id IN ({ph})', listing_ids)
                safe_del(f'DELETE FROM listing_photos WHERE listing_id IN ({ph})', listing_ids)
            safe_del('DELETE FROM listings WHERE seller_id = ?', (user_id,))

            order_ids = [r['id'] for r in conn.execute(
                'SELECT id FROM orders WHERE buyer_id = ?', (user_id,)
            ).fetchall()]
            if order_ids:
                ph = ','.join('?' * len(order_ids))
                safe_del(f'DELETE FROM order_items WHERE order_id IN ({ph})', order_ids)
                safe_del(f'DELETE FROM tracking WHERE order_id IN ({ph})', order_ids)
                safe_del(f'DELETE FROM seller_order_tracking WHERE order_id IN ({ph})', order_ids)
                safe_del(f'DELETE FROM cancellation_seller_responses WHERE request_id IN (SELECT id FROM cancellation_requests WHERE order_id IN ({ph}))', order_ids)
                safe_del(f'DELETE FROM cancellation_requests WHERE order_id IN ({ph})', order_ids)
            safe_del('DELETE FROM orders WHERE buyer_id = ?', (user_id,))

            bid_ids = [r['id'] for r in conn.execute(
                'SELECT id FROM bids WHERE buyer_id = ?', (user_id,)
            ).fetchall()]
            if bid_ids:
                ph = ','.join('?' * len(bid_ids))
                safe_del(f'DELETE FROM bid_fills WHERE bid_id IN ({ph})', bid_ids)
            safe_del('DELETE FROM bids WHERE buyer_id = ?', (user_id,))

            safe_del('DELETE FROM cart WHERE user_id = ?', (user_id,))

            report_ids = [r['id'] for r in conn.execute(
                'SELECT id FROM reports WHERE reporter_user_id = ? OR reported_user_id = ?', (user_id, user_id)
            ).fetchall()]
            if report_ids:
                ph = ','.join('?' * len(report_ids))
                safe_del(f'DELETE FROM report_attachments WHERE report_id IN ({ph})', report_ids)
            safe_del('DELETE FROM reports WHERE reporter_user_id = ? OR reported_user_id = ?', (user_id, user_id))

            safe_del('DELETE FROM messages WHERE sender_id = ? OR receiver_id = ?', (user_id, user_id))
            safe_del('DELETE FROM message_reads WHERE user_id = ? OR participant_id = ?', (user_id, user_id))
            safe_del('DELETE FROM ratings WHERE rater_id = ? OR ratee_id = ?', (user_id, user_id))
            safe_del('DELETE FROM notifications WHERE user_id = ?', (user_id,))
            safe_del('DELETE FROM notification_preferences WHERE user_id = ?', (user_id,))
            safe_del('DELETE FROM user_preferences WHERE user_id = ?', (user_id,))
            safe_del('DELETE FROM portfolio_exclusions WHERE user_id = ?', (user_id,))
            safe_del('DELETE FROM portfolio_snapshots WHERE user_id = ?', (user_id,))
            safe_del('DELETE FROM addresses WHERE user_id = ?', (user_id,))
            safe_del('DELETE FROM price_locks WHERE user_id = ?', (user_id,))
            safe_del('DELETE FROM user_cancellation_stats WHERE user_id = ?', (user_id,))
            safe_del('DELETE FROM seller_order_tracking WHERE seller_id = ?', (user_id,))
            safe_del('DELETE FROM cancellation_seller_responses WHERE seller_id = ?', (user_id,))
            safe_del('DELETE FROM users WHERE id = ?', (user_id,))

            total_deleted += 1
            print(f"[Admin] Bulk-deleted user ID {user_id} (@{user['username']})")

        conn.execute('PRAGMA foreign_keys = ON')
        conn.commit()
        return jsonify({
            'success': True,
            'message': f'{total_deleted} account{"s" if total_deleted != 1 else ""} permanently deleted',
            'count': total_deleted
        })
    except Exception as e:
        conn.execute('PRAGMA foreign_keys = ON')
        print(f"Error bulk deleting users: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/user/<int:user_id>/message', methods=['POST'])
@admin_required
def send_admin_message(user_id):
    """Send a message from admin to a user"""
    from database import get_db_connection
    from flask import session

    data = request.get_json() or {}
    message = data.get('message', '').strip()

    if not message:
        return jsonify({'success': False, 'error': 'Message cannot be empty'}), 400

    admin_id = session.get('user_id')

    conn = get_db_connection()
    try:
        # Check if user exists
        user = conn.execute('SELECT id, username FROM users WHERE id = ?', (user_id,)).fetchone()
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        # Insert message with order_id = 0 to indicate admin message
        conn.execute('''
            INSERT INTO messages (order_id, sender_id, receiver_id, content)
            VALUES (0, ?, ?, ?)
        ''', (admin_id, user_id, message))
        conn.commit()

        return jsonify({
            'success': True,
            'message': f'Message sent to {user["username"]}'
        })

    except Exception as e:
        print(f"Error sending admin message: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/conversations')
@admin_required
def get_admin_conversations():
    """Get all conversations where the admin has sent or received messages"""
    from database import get_db_connection
    from flask import session

    admin_id = session.get('user_id')

    conn = get_db_connection()
    try:
        # First, get all unique users the admin has conversed with (order_id = 0)
        other_users = conn.execute('''
            SELECT DISTINCT
                CASE WHEN sender_id = ? THEN receiver_id ELSE sender_id END AS other_user_id
            FROM messages
            WHERE order_id = 0
              AND (sender_id = ? OR receiver_id = ?)
        ''', (admin_id, admin_id, admin_id)).fetchall()

        result = []
        for row in other_users:
            other_user_id = row['other_user_id']

            # Get user info
            user = conn.execute('SELECT username FROM users WHERE id = ?', (other_user_id,)).fetchone()
            if not user:
                continue

            # Get the latest message in this conversation
            last_msg = conn.execute('''
                SELECT content, timestamp
                FROM messages
                WHERE order_id = 0
                  AND ((sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?))
                ORDER BY timestamp DESC
                LIMIT 1
            ''', (admin_id, other_user_id, other_user_id, admin_id)).fetchone()

            # Get the last read timestamp for this conversation
            read_record = conn.execute('''
                SELECT last_read_ts FROM message_reads
                WHERE user_id = ? AND participant_id = ? AND order_id = 0
            ''', (admin_id, other_user_id)).fetchone()

            last_read_ts = read_record['last_read_ts'] if read_record else None

            # Count unread messages (messages FROM the other user TO admin, after last_read_ts)
            if last_read_ts:
                unread = conn.execute('''
                    SELECT COUNT(*) as cnt FROM messages
                    WHERE order_id = 0
                      AND sender_id = ?
                      AND receiver_id = ?
                      AND timestamp > ?
                ''', (other_user_id, admin_id, last_read_ts)).fetchone()
            else:
                # If never read, count all messages from other user
                unread = conn.execute('''
                    SELECT COUNT(*) as cnt FROM messages
                    WHERE order_id = 0
                      AND sender_id = ?
                      AND receiver_id = ?
                ''', (other_user_id, admin_id)).fetchone()

            result.append({
                'other_user_id': other_user_id,
                'other_username': user['username'],
                'last_message_content': last_msg['content'] if last_msg else '',
                'last_message_time': last_msg['timestamp'] if last_msg else '',
                'unread_count': unread['cnt'] if unread else 0
            })

        # Sort by last message time (most recent first)
        result.sort(key=lambda x: x['last_message_time'] or '', reverse=True)

        return jsonify({
            'success': True,
            'conversations': result
        })

    except Exception as e:
        print(f"Error getting admin conversations: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/user/<int:user_id>/messages')
@admin_required
def get_admin_user_messages(user_id):
    """Get all messages between admin and a specific user"""
    from database import get_db_connection
    from flask import session

    admin_id = session.get('user_id')

    conn = get_db_connection()
    try:
        # Get user info
        user = conn.execute('SELECT id, username FROM users WHERE id = ?', (user_id,)).fetchone()
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        # Get all messages between admin and user (order_id = 0)
        messages = conn.execute('''
            SELECT
                m.id,
                m.sender_id,
                m.receiver_id,
                m.content,
                m.timestamp,
                sender.username AS sender_username
            FROM messages m
            JOIN users sender ON sender.id = m.sender_id
            WHERE m.order_id = 0
              AND ((m.sender_id = ? AND m.receiver_id = ?)
                OR (m.sender_id = ? AND m.receiver_id = ?))
            ORDER BY m.timestamp ASC
        ''', (admin_id, user_id, user_id, admin_id)).fetchall()

        # Mark messages as read
        conn.execute('''
            INSERT OR REPLACE INTO message_reads (user_id, participant_id, order_id, last_read_ts)
            VALUES (?, ?, 0, CURRENT_TIMESTAMP)
        ''', (admin_id, user_id))
        conn.commit()

        result = []
        for msg in messages:
            result.append({
                'id': msg['id'],
                'sender_id': msg['sender_id'],
                'receiver_id': msg['receiver_id'],
                'content': msg['content'],
                'timestamp': msg['timestamp'],
                'sender_username': msg['sender_username'],
                'is_admin': msg['sender_id'] == admin_id
            })

        return jsonify({
            'success': True,
            'user': {
                'id': user['id'],
                'username': user['username']
            },
            'messages': result,
            'admin_id': admin_id
        })

    except Exception as e:
        print(f"Error getting admin-user messages: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/order/<int:order_id>')
@admin_required
def get_order_details(order_id):
    """Get detailed information about an order for admin modal"""
    from database import get_db_connection

    conn = get_db_connection()
    try:
        # Get order info
        order = conn.execute('''
            SELECT o.*, buyer.username as buyer_username, buyer.email as buyer_email
            FROM orders o
            JOIN users buyer ON o.buyer_id = buyer.id
            WHERE o.id = ?
        ''', (order_id,)).fetchone()

        if not order:
            return jsonify({'success': False, 'error': 'Order not found'}), 404

        # Get order items
        items = conn.execute('''
            SELECT oi.*, l.seller_id, seller.username as seller_username,
                   c.metal, c.product_type, c.product_line, c.weight
            FROM order_items oi
            JOIN listings l ON oi.listing_id = l.id
            JOIN users seller ON l.seller_id = seller.id
            JOIN categories c ON l.category_id = c.id
            WHERE oi.order_id = ?
        ''', (order_id,)).fetchall()

        items_list = []
        sellers = set()
        for item in items:
            title_parts = []
            if item['weight']:
                title_parts.append(item['weight'])
            if item['metal']:
                title_parts.append(item['metal'])
            if item['product_line']:
                title_parts.append(item['product_line'])
            elif item['product_type']:
                title_parts.append(item['product_type'])

            items_list.append({
                'id': item['id'],
                'listing_id': item['listing_id'],
                'title': ' '.join(title_parts) or 'Item',
                'quantity': item['quantity'],
                'price_each': item['price_each'],
                'subtotal': item['quantity'] * item['price_each'],
                'seller': item['seller_username'],
                'metal': item['metal']
            })
            sellers.add(item['seller_username'])

        return jsonify({
            'success': True,
            'order': {
                'id': order['id'],
                'buyer': order['buyer_username'],
                'buyer_email': order['buyer_email'],
                'sellers': list(sellers),
                'total_price': order['total_price'],
                'status': order['status'],
                'created_at': order['created_at'],
                'created_ago': _format_time_ago(order['created_at']),
                'shipping_address': order['shipping_address'] or 'N/A',
                'tracking_number': order['tracking_number'] if 'tracking_number' in order.keys() else None,
                'items': items_list,
                'item_count': len(items_list)
            }
        })

    except Exception as e:
        print(f"Error getting order details: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()
