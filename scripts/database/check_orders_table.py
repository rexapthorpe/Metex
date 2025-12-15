"""Check orders table schema"""
import sqlite3

conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# Get the schema
cursor.execute("PRAGMA table_info(orders)")
columns = cursor.fetchall()

print("Orders table schema:")
print("-" * 60)
for col in columns:
    col_id, name, col_type, notnull, default, pk = col
    nullable = "NOT NULL" if notnull else "NULL"
    primary = " PRIMARY KEY" if pk else ""
    print(f"  {name:20} {col_type:15} {nullable:10}{primary}")

conn.close()
