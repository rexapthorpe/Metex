import sqlite3

def run_migration():
    """Run migration 006 to create portfolio tables"""
    conn = sqlite3.connect('metex.db')
    cursor = conn.cursor()

    try:
        # Read and execute the migration file
        with open('migrations/006_create_portfolio_tables.sql', 'r') as f:
            migration_sql = f.read()

        # Execute each statement
        cursor.executescript(migration_sql)
        conn.commit()

        print("Migration 006 completed successfully!")
        print("Created tables:")
        print("  - portfolio_exclusions")
        print("  - portfolio_snapshots")
        print("Created indexes for performance optimization")

    except Exception as e:
        print(f"Error running migration: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    run_migration()
