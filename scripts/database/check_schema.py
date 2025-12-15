from database import get_db_connection

conn = get_db_connection()

print("=== CATEGORIES TABLE ===")
for row in conn.execute('PRAGMA table_info(categories)').fetchall():
    print(f"{row[1]:20} {row[2]:15} NOT NULL: {row[3]} DEFAULT: {row[4]}")

print("\n=== LISTINGS TABLE ===")
for row in conn.execute('PRAGMA table_info(listings)').fetchall():
    print(f"{row[1]:20} {row[2]:15} NOT NULL: {row[3]} DEFAULT: {row[4]}")

conn.close()
