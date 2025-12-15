#!/usr/bin/env python3
"""
Clear Marketplace Data Script

This script clears all marketplace data (buckets, listings, bids, orders, cart, etc.)
while preserving user accounts and database schema.

Usage:
    python clear_marketplace_data.py          # With confirmation prompt
    python clear_marketplace_data.py --yes    # Skip confirmation

What gets cleared:
    - All buckets (categories)
    - All listings
    - All bids
    - All orders and order items
    - All cart items
    - All ratings
    - All messages/conversations
    - All notifications
    - All portfolio data (exclusions, snapshots)
    - All bucket price history

What stays intact:
    - User accounts and authentication
    - Address books
    - User preferences
    - Database structure (tables, columns, indexes)
"""

import sqlite3
import sys
import os


def clear_marketplace_data(skip_confirmation=False):
    """Clear all marketplace data from the database."""

    if not skip_confirmation:
        print('\n⚠️  WARNING: This will delete ALL marketplace data!')
        print('\nThe following will be cleared:')
        print('  • All buckets (categories)')
        print('  • All listings')
        print('  • All bids')
        print('  • All orders and order items')
        print('  • All cart items')
        print('  • All ratings')
        print('  • All messages/conversations')
        print('  • All notifications')
        print('  • All portfolio data (exclusions, snapshots)')
        print('  • All bucket price history')
        print('\nUser accounts, addresses, and preferences will be PRESERVED.')
        print()

        response = input('Are you sure you want to proceed? (yes/no): ').strip().lower()
        if response not in ['yes', 'y']:
            print('Operation cancelled.')
            return 0

    # Check if database file exists
    db_path = 'marketplace.db'
    if not os.path.exists(db_path):
        print(f'\n❌ Error: Database file "{db_path}" not found.')
        print('   Make sure you are running this script from the project root directory.')
        return 1

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Disable foreign key constraints temporarily for easier deletion
        cursor.execute('PRAGMA foreign_keys = OFF')

        print('\n🗑️  Clearing marketplace data...\n')

        # Delete in order that respects dependencies (child tables first)
        tables_to_clear = [
            ('portfolio_exclusions', 'Portfolio exclusions'),
            ('portfolio_snapshots', 'Portfolio snapshots'),
            ('bucket_price_history', 'Bucket price history'),
            ('ratings', 'Ratings'),
            ('messages', 'Messages/conversations'),
            ('notifications', 'Notifications'),
            ('order_items', 'Order items'),
            ('orders', 'Orders'),
            ('bids', 'Bids'),
            ('cart', 'Cart items'),
            ('listings', 'Listings'),
            ('categories', 'Buckets/categories'),
        ]

        deleted_counts = {}

        for table_name, description in tables_to_clear:
            try:
                # Count records before deletion
                count_result = cursor.execute(f'SELECT COUNT(*) FROM {table_name}').fetchone()
                count = count_result[0] if count_result else 0

                # Delete all records
                cursor.execute(f'DELETE FROM {table_name}')

                # Reset autoincrement counter
                cursor.execute(f"DELETE FROM sqlite_sequence WHERE name = '{table_name}'")

                deleted_counts[description] = count
                print(f'  ✓ Cleared {count:,} {description}')

            except sqlite3.OperationalError as e:
                # Table might not exist - that's okay, just skip it
                print(f'  ⚠️  Skipped {description} (table not found)')
                deleted_counts[description] = 0

        # Re-enable foreign key constraints
        cursor.execute('PRAGMA foreign_keys = ON')

        # Commit all changes
        conn.commit()
        conn.close()

        print('\n✅ Marketplace data cleared successfully!')
        print(f'\nTotal records deleted: {sum(deleted_counts.values()):,}')

        # Show summary of non-zero deletions
        non_zero_deletions = {k: v for k, v in deleted_counts.items() if v > 0}
        if non_zero_deletions:
            print('\n📊 Summary:')
            for description, count in non_zero_deletions.items():
                print(f'     {description}: {count:,}')

        return 0

    except sqlite3.Error as e:
        print(f'\n❌ Database error: {e}', file=sys.stderr)
        return 1
    except Exception as e:
        print(f'\n❌ Unexpected error: {e}', file=sys.stderr)
        return 1


def main():
    """Main entry point for the script."""
    # Check for --yes or -y flag
    skip_confirmation = '--yes' in sys.argv or '-y' in sys.argv

    # Show help if requested
    if '--help' in sys.argv or '-h' in sys.argv:
        print(__doc__)
        return 0

    return clear_marketplace_data(skip_confirmation)


if __name__ == '__main__':
    sys.exit(main())
