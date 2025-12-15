"""
Check if there are any real notifications in the database
"""
from database import get_db_connection

conn = get_db_connection()

# Get all notifications
all_notifs = conn.execute("SELECT * FROM notifications ORDER BY created_at DESC").fetchall()
total_count = conn.execute("SELECT COUNT(*) as count FROM notifications").fetchone()['count']

# Get all users
users = conn.execute("SELECT id, username FROM users ORDER BY id").fetchall()

conn.close()

print("=" * 80)
print("REAL NOTIFICATIONS CHECK")
print("=" * 80)

print(f"\nTotal notifications in database: {total_count}")

if total_count > 0:
    print("\nAll notifications:")
    print("-" * 80)
    for notif in all_notifs:
        print(f"ID {notif['id']}: User {notif['user_id']} - {notif['type']}")
        print(f"  Title: {notif['title']}")
        print(f"  Created: {notif['created_at']}")
        print(f"  Read: {'Yes' if notif['is_read'] else 'No'}")
        print()
else:
    print("\n[ISSUE] NO notifications found in database!")
    print("This explains why you're not seeing any notifications.")

print("\nUsers in database:")
print("-" * 80)
for user in users:
    print(f"ID {user['id']}: {user['username']}")

print("\n" + "=" * 80)
