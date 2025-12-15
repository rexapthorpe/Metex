import sqlite3
import os

db_path = 'marketplace.db'

# Check file size
file_size = os.path.getsize(db_path)
print(f"Database file size: {file_size} bytes")

if file_size == 0:
    print("\n[INFO] Database is completely empty (0 bytes)")
    print("The database has been wiped or was never initialized.")
    print("\nTo populate it:")
    print("  1. Run the Flask app: python app.py")
    print("  2. Access the application in your browser")
    print("  3. The app will create tables on first use")
else:
    # Check tables
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()

    print(f"\nFound {len(tables)} tables:")
    for table in tables:
        count = cursor.execute(f'SELECT COUNT(*) FROM {table[0]}').fetchone()[0]
        print(f"  {table[0]}: {count} records")

    conn.close()
