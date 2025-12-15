# app.py
import config
import sqlite3
import click
from flask import Flask, redirect, url_for
from flask.cli import with_appcontext

# Route Blueprints
from routes.auth_routes import auth_bp
from routes.sell_routes import sell_bp
from routes.listings_routes import listings_bp
from routes.buy_routes import buy_bp
from routes.account_routes import account_bp
from routes.checkout_routes import checkout_bp
from routes.messages_routes import messages_bp
from routes.cart_routes import cart_bp
from routes.bid_routes import bid_bp
from routes.ratings_routes import ratings_bp
from routes.api_routes import api_bp
from routes.notification_routes import notification_bp
from routes.portfolio_routes import portfolio_bp
from routes.bucket_routes import bucket_bp

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(sell_bp)
app.register_blueprint(listings_bp, url_prefix='/listings')
app.register_blueprint(buy_bp)
app.register_blueprint(account_bp)
app.register_blueprint(checkout_bp)
app.register_blueprint(messages_bp)
app.register_blueprint(cart_bp)
app.register_blueprint(bid_bp)
app.register_blueprint(ratings_bp)
app.register_blueprint(api_bp)
app.register_blueprint(notification_bp)
app.register_blueprint(portfolio_bp)
app.register_blueprint(bucket_bp)


# Custom Jinja Filters
@app.template_filter('commas')
def format_with_commas(value):
    """
    Format a number with comma separators for thousands.
    Preserves decimals. Examples: 1234 -> 1,234 | 1234.56 -> 1,234.56
    """
    if value is None:
        return ''

    try:
        # Convert to float to handle both int and float inputs
        num = float(value)

        # Split into integer and decimal parts
        if '.' in str(num):
            int_part, dec_part = str(num).split('.')
            # Format integer part with commas
            int_part = '{:,}'.format(int(float(int_part)))
            return f"{int_part}.{dec_part}"
        else:
            # No decimal part, just format the integer
            return '{:,}'.format(int(num))
    except (ValueError, TypeError):
        # If conversion fails, return original value as string
        return str(value)


@app.cli.command('clear-marketplace-data')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation prompt')
@with_appcontext
def clear_marketplace_data(yes):
    """
    Clear all marketplace data (buckets, listings, bids, orders, cart, etc.)
    while preserving user accounts and database schema.

    This command deletes all marketplace transactions and inventory data but keeps:
    - User accounts and authentication
    - Address books
    - User preferences
    - Database structure (tables, columns, indexes)

    Usage:
        flask clear-marketplace-data          # With confirmation
        flask clear-marketplace-data --yes    # Skip confirmation
    """
    if not yes:
        click.echo('\n⚠️  WARNING: This will delete ALL marketplace data!')
        click.echo('\nThe following will be cleared:')
        click.echo('  • All buckets (categories)')
        click.echo('  • All listings')
        click.echo('  • All bids')
        click.echo('  • All orders and order items')
        click.echo('  • All cart items')
        click.echo('  • All ratings')
        click.echo('  • All messages/conversations')
        click.echo('  • All notifications')
        click.echo('  • All portfolio data (exclusions, snapshots)')
        click.echo('  • All bucket price history')
        click.echo('\nUser accounts, addresses, and preferences will be PRESERVED.')
        click.echo()

        if not click.confirm('Are you sure you want to proceed?'):
            click.echo('Operation cancelled.')
            return

    try:
        conn = sqlite3.connect('marketplace.db')
        cursor = conn.cursor()

        # Disable foreign key constraints temporarily for easier deletion
        cursor.execute('PRAGMA foreign_keys = OFF')

        click.echo('\n🗑️  Clearing marketplace data...\n')

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
            # Count records before deletion
            count_result = cursor.execute(f'SELECT COUNT(*) FROM {table_name}').fetchone()
            count = count_result[0] if count_result else 0

            # Delete all records
            cursor.execute(f'DELETE FROM {table_name}')

            # Reset autoincrement counter
            cursor.execute(f"DELETE FROM sqlite_sequence WHERE name = '{table_name}'")

            deleted_counts[description] = count
            click.echo(f'  ✓ Cleared {count:,} {description}')

        # Re-enable foreign key constraints
        cursor.execute('PRAGMA foreign_keys = ON')

        # Commit all changes
        conn.commit()
        conn.close()

        click.echo('\n✅ Marketplace data cleared successfully!')
        click.echo(f'\nTotal records deleted: {sum(deleted_counts.values()):,}')
        click.echo('\n📊 Summary:')
        for description, count in deleted_counts.items():
            if count > 0:
                click.echo(f'     {description}: {count:,}')

    except sqlite3.Error as e:
        click.echo(f'\n❌ Database error: {e}', err=True)
        return 1
    except Exception as e:
        click.echo(f'\n❌ Unexpected error: {e}', err=True)
        return 1


@app.route('/')
def index():
    return redirect(url_for('buy.buy'))

if __name__ == '__main__':
    app.run(debug=True, port=5001)
