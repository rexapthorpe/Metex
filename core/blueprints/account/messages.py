"""
Messages Route

Route for viewing user messages.
"""

from flask import render_template, session, redirect, url_for
from database import get_db_connection

from . import account_bp


@account_bp.route('/messages')
def my_messages():
    print("⚡ /messages route hit!")

    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    conn = get_db_connection()

    # First, get list of distinct conversations with latest message details
    base_conversations = conn.execute('''
        SELECT
            users.id AS other_user_id,
            users.username AS other_username,
            messages.content AS latest_message,
            messages.timestamp AS latest_timestamp
        FROM messages
        JOIN (
            SELECT
                CASE
                    WHEN sender_id = ? THEN receiver_id
                    ELSE sender_id
                END AS other_id,
                MAX(timestamp) AS max_time
            FROM messages
            WHERE sender_id = ? OR receiver_id = ?
            GROUP BY other_id
        ) AS latest_convos
        ON (
            (messages.sender_id = ? AND messages.receiver_id = latest_convos.other_id)
            OR (messages.sender_id = latest_convos.other_id AND messages.receiver_id = ?)
        )
        AND messages.timestamp = latest_convos.max_time
        JOIN users ON users.id = latest_convos.other_id
        ORDER BY messages.timestamp DESC;
    ''', (user_id, user_id, user_id, user_id, user_id)).fetchall()

    conversations = []

    for convo in base_conversations:
        other_user_id = convo['other_user_id']
        convo_data = {
            'other_user_id': other_user_id,
            'other_username': convo['other_username'],
            'last_message_content': convo['latest_message'],
            'last_message_time': convo['latest_timestamp'],
            'messages': []
        }

        # Now get all messages for this conversation
        convo_data['messages'] = conn.execute('''
            SELECT sender_id, receiver_id, content, timestamp
            FROM messages
            WHERE (sender_id = ? AND receiver_id = ?)
               OR (sender_id = ? AND receiver_id = ?)
            ORDER BY timestamp ASC
        ''', (user_id, other_user_id, other_user_id, user_id)).fetchall()

        conversations.append(convo_data)

    conn.close()
    print("Loaded messages route. Conversations found:", len(conversations))

    return render_template('partials/my_messages.html', conversations=conversations, current_user_id=user_id)
