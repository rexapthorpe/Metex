"""Check if notifications table exists and its schema"""
import sqlite3

conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# Check if notifications table exists
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notifications'")
table_exists = cursor.fetchone()

print("=" * 70)
print("NOTIFICATIONS TABLE CHECK")
print("=" * 70)

if table_exists:
    print("[OK] Notifications table EXISTS")
    print()

    # Get the schema
    cursor.execute("PRAGMA table_info(notifications)")
    columns = cursor.fetchall()

    print("Table Schema:")
    print("-" * 70)
    for col in columns:
        col_id, name, col_type, notnull, default, pk = col
        nullable = "NOT NULL" if notnull else "NULL"
        primary = " PRIMARY KEY" if pk else ""
        print(f"  {name:20} {col_type:15} {nullable:10}{primary}")

    print()
    print("-" * 70)

    # Count notifications
    cursor.execute("SELECT COUNT(*) FROM notifications")
    count = cursor.fetchone()[0]
    print(f"Total notifications in database: {count}")

    if count > 0:
        # Show some sample notifications
        cursor.execute("SELECT id, user_id, type, title, created_at, is_read FROM notifications LIMIT 5")
        notifications = cursor.fetchall()
        print()
        print("Sample notifications:")
        print("-" * 70)
        for notif in notifications:
            notif_id, user_id, notif_type, title, created_at, is_read = notif
            read_status = "READ" if is_read else "UNREAD"
            print(f"  ID {notif_id}: User {user_id} - {notif_type} - {read_status}")
            print(f"    Title: {title}")
            print(f"    Created: {created_at}")
            print()
else:
    print("[ERROR] Notifications table DOES NOT EXIST!")
    print()
    print("The table needs to be created. Here's the CREATE TABLE statement:")
    print()
    print("""
    CREATE TABLE notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        type TEXT NOT NULL,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        related_order_id INTEGER,
        related_bid_id INTEGER,
        related_listing_id INTEGER,
        metadata TEXT,
        is_read INTEGER DEFAULT 0,
        read_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (related_order_id) REFERENCES orders(id),
        FOREIGN KEY (related_bid_id) REFERENCES bids(id),
        FOREIGN KEY (related_listing_id) REFERENCES listings(id)
    );
    """)

conn.close()
print("=" * 70)
