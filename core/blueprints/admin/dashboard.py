"""
Admin Dashboard Routes

This module contains the main admin dashboard page and related helper functions.
Routes:
- /dashboard - Main admin dashboard page with overview stats

IMPORTANT: All route URLs and endpoint names are preserved from original admin_routes.py
"""

from flask import render_template, redirect, url_for
from datetime import datetime
from utils.auth_utils import admin_required
from . import admin_bp


@admin_bp.route('/')
@admin_required
def admin_index():
    """Redirect /admin/ to the dashboard."""
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    """Render the new admin dashboard page with real data"""
    from database import get_db_connection

    conn = get_db_connection()

    stats = {}
    recent_transactions = []
    recent_users = []
    recent_listings = []
    all_users = []
    all_listings = []
    all_transactions = []
    transaction_stats = {}

    try:
        # ========== OVERVIEW STATS ==========

        # Total users
        result = conn.execute('SELECT COUNT(*) as count FROM users').fetchone()
        stats['total_users'] = f"{result['count']:,}"

        # Active listings
        result = conn.execute('SELECT COUNT(*) as count FROM listings WHERE active = 1 AND quantity > 0').fetchone()
        stats['active_listings'] = f"{result['count']:,}"

        # Transaction volume (sum of all order totals)
        result = conn.execute('SELECT COALESCE(SUM(total_price), 0) as total FROM orders').fetchone()
        volume = result['total'] or 0
        if volume >= 1000000:
            stats['transaction_volume'] = f"{volume/1000000:.2f}M"
        elif volume >= 1000:
            stats['transaction_volume'] = f"{volume/1000:.1f}K"
        else:
            stats['transaction_volume'] = f"{volume:,.0f}"

        # Platform revenue (placeholder)
        stats['platform_revenue'] = f"{volume * 0.025:,.0f}"

        # Count active disputes (open reports)
        try:
            active_disputes = conn.execute("""
                SELECT COUNT(*) as count FROM reports
                WHERE status IN ('open', 'under_investigation', 'pending_review')
            """).fetchone()['count']
            stats['active_disputes'] = str(active_disputes)
        except Exception:
            stats['active_disputes'] = '0'

        # Pending orders volume (orders not yet delivered/completed - funds in limbo)
        try:
            pending_volume = conn.execute("""
                SELECT COALESCE(SUM(total_price), 0) as total FROM orders
                WHERE status NOT IN ('Delivered', 'Completed', 'Cancelled', 'Refunded')
            """).fetchone()['total']
            if pending_volume >= 1000:
                stats['pending_orders_volume'] = f"{pending_volume/1000:.1f}K"
            else:
                stats['pending_orders_volume'] = f"{pending_volume:,.0f}"
        except Exception:
            stats['pending_orders_volume'] = '0'

        # ========== RECENT TRANSACTIONS ==========
        transactions_query = conn.execute('''
            SELECT
                o.id,
                o.buyer_id,
                o.total_price,
                o.status,
                o.created_at,
                buyer.username as buyer_username,
                seller.username as seller_username,
                COUNT(oi.id) as item_count
            FROM orders o
            JOIN users buyer ON o.buyer_id = buyer.id
            JOIN order_items oi ON o.id = oi.order_id
            JOIN listings l ON oi.listing_id = l.id
            JOIN users seller ON l.seller_id = seller.id
            GROUP BY o.id
            ORDER BY o.created_at DESC
            LIMIT 10
        ''').fetchall()

        for tx in transactions_query:
            created = tx['created_at'] or ''
            time_ago = _format_time_ago(created)

            recent_transactions.append({
                'id': tx['id'],
                'buyer': tx['buyer_username'],
                'buyer_initial': (tx['buyer_username'] or 'U')[0].upper(),
                'seller': tx['seller_username'],
                'items': tx['item_count'],
                'amount': f"{tx['total_price']:,.2f}",
                'status': tx['status'] or 'pending',
                'time_ago': time_ago
            })

        # ========== RECENT USERS ==========
        users_query = conn.execute('''
            SELECT
                id,
                username,
                email,
                created_at,
                is_admin,
                is_banned,
                is_frozen
            FROM users
            ORDER BY created_at DESC
            LIMIT 10
        ''').fetchall()

        for user in users_query:
            created = user['created_at'] or ''
            joined_ago = _format_time_ago(created)

            # Determine user status
            if user['is_banned']:
                status = 'banned'
            elif user['is_frozen']:
                status = 'frozen'
            else:
                status = 'active'

            recent_users.append({
                'id': user['id'],
                'username': user['username'],
                'initial': (user['username'] or 'U')[0].upper(),
                'email': user['email'],
                'joined_ago': joined_ago,
                'status': status
            })

        # ========== RECENT LISTINGS ==========
        listings_query = conn.execute('''
            SELECT
                l.id,
                l.price_per_coin,
                l.quantity,
                l.active,
                u.username as seller_username,
                c.metal,
                c.product_type,
                c.product_line,
                c.weight
            FROM listings l
            JOIN users u ON l.seller_id = u.id
            JOIN categories c ON l.category_id = c.id
            ORDER BY l.id DESC
            LIMIT 10
        ''').fetchall()

        for listing in listings_query:
            time_ago = 'Recently'  # No created_at column in listings

            # Build title
            title_parts = []
            if listing['weight']:
                title_parts.append(listing['weight'])
            if listing['metal']:
                title_parts.append(listing['metal'])
            if listing['product_line']:
                title_parts.append(listing['product_line'])
            elif listing['product_type']:
                title_parts.append(listing['product_type'])
            title = ' '.join(title_parts) or 'Listing'

            recent_listings.append({
                'id': listing['id'],
                'title': title,
                'seller': listing['seller_username'],
                'metal': listing['metal'] or 'Unknown',
                'price': listing['price_per_coin'] or 0,
                'quantity': listing['quantity'] or 0,
                'status': 'approved' if listing['active'] else 'pending',
                'time_ago': time_ago
            })

        # ========== ALL USERS (for Users tab) ==========
        all_users_query = conn.execute('''
            SELECT
                u.id,
                u.username,
                u.email,
                u.created_at,
                u.is_admin,
                u.is_banned,
                u.is_frozen,
                COUNT(DISTINCT o.id) as transaction_count
            FROM users u
            LEFT JOIN orders o ON u.id = o.buyer_id
            GROUP BY u.id
            ORDER BY u.created_at DESC
        ''').fetchall()

        for user in all_users_query:
            created = user['created_at'] or ''
            joined = _format_time_ago(created)

            # Determine user status from is_banned and is_frozen
            if user['is_banned']:
                status = 'banned'
            elif user['is_frozen']:
                status = 'frozen'
            else:
                status = 'active'

            all_users.append({
                'id': user['id'],
                'username': user['username'],
                'initial': (user['username'] or 'U')[0].upper(),
                'email': user['email'] or 'N/A',
                'status': status,
                'is_banned': user['is_banned'] or 0,
                'is_frozen': user['is_frozen'] or 0,
                'verified': False,  # Placeholder
                'transactions': user['transaction_count'] or 0,
                'joined': joined
            })

        # ========== ALL LISTINGS (for Listings tab) ==========
        from services.pricing_service import get_effective_price

        all_listings_query = conn.execute('''
            SELECT
                l.id,
                l.price_per_coin,
                l.pricing_mode,
                l.spot_premium,
                l.floor_price,
                l.pricing_metal,
                l.quantity,
                l.active,
                u.username as seller_username,
                c.metal,
                c.product_type,
                c.product_line,
                c.weight,
                c.purity,
                c.finish,
                c.year,
                c.mint,
                c.coin_series,
                c.grade,
                c.bucket_id
            FROM listings l
            JOIN users u ON l.seller_id = u.id
            JOIN categories c ON l.category_id = c.id
            ORDER BY l.id DESC
            LIMIT 100
        ''').fetchall()

        # Fetch latest spot prices from DB snapshot only — no external API calls.
        metals_needed = set()
        for row in all_listings_query:
            if (row['pricing_mode'] or 'static') == 'premium_to_spot':
                m = (row['pricing_metal'] or row['metal'] or '').lower()
                if m:
                    metals_needed.add(m)

        snapshot_spot_prices = {}
        for metal in metals_needed:
            # Use REPLACE so rows stored with space-separator ("YYYY-MM-DD HH:MM:SS")
            # sort correctly against T-format rows ("YYYY-MM-DDTHH:MM:SS").
            snap = conn.execute(
                "SELECT price_usd FROM spot_price_snapshots "
                "WHERE metal = ? ORDER BY REPLACE(as_of, ' ', 'T') DESC LIMIT 1",
                (metal,)
            ).fetchone()
            if snap:
                snapshot_spot_prices[metal] = snap['price_usd']

        for listing in all_listings_query:
            time_ago = 'Recently'  # No created_at column in listings

            title_parts = []
            if listing['weight']:
                title_parts.append(str(listing['weight']))
            if listing['metal']:
                title_parts.append(listing['metal'])
            if listing['product_line']:
                title_parts.append(listing['product_line'])
            elif listing['product_type']:
                title_parts.append(listing['product_type'])
            title = ' '.join(title_parts) or 'Listing'

            pricing_mode = listing['pricing_mode'] or 'static'
            listing_dict = dict(listing)

            # Compute effective price using DB snapshot spot prices only.
            if pricing_mode == 'premium_to_spot':
                pricing_metal = (listing['pricing_metal'] or listing['metal'] or '').lower()
                spot_available = pricing_metal in snapshot_spot_prices
                if spot_available:
                    effective_price = get_effective_price(listing_dict, spot_prices=snapshot_spot_prices)
                else:
                    effective_price = None  # No snapshot available; show "—" in UI
            else:
                effective_price = get_effective_price(listing_dict, spot_prices={})
                spot_available = True  # N/A for static listings

            # "Stored" price: floor_price for premium_to_spot, price_per_coin for static.
            stored_price = listing['floor_price'] if pricing_mode == 'premium_to_spot' else listing['price_per_coin']
            stored_price = stored_price or listing['price_per_coin'] or 0

            # Spot snapshot price used in computation (for the modal display).
            spot_snapshot_price = None
            if pricing_mode == 'premium_to_spot':
                pm_key = (listing['pricing_metal'] or listing['metal'] or '').lower()
                spot_snapshot_price = snapshot_spot_prices.get(pm_key)

            all_listings.append({
                'id': listing['id'],
                'title': title,
                'seller': listing['seller_username'],
                'metal': listing['metal'] or 'Unknown',
                'price': stored_price,
                'effective_price': effective_price,
                'pricing_mode': pricing_mode,
                'spot_available': spot_available,
                # Extra fields for the detail modal
                'price_per_coin': listing['price_per_coin'] or 0,
                'spot_premium': listing['spot_premium'],
                'floor_price': listing['floor_price'],
                'pricing_metal': listing['pricing_metal'] or listing['metal'] or '',
                'spot_snapshot_price': spot_snapshot_price,
                'quantity': listing['quantity'] or 0,
                'product_type': listing['product_type'] or '',
                'product_line': listing['product_line'] or '',
                'weight': str(listing['weight']) if listing['weight'] else '',
                'purity': listing['purity'] or '',
                'finish': listing['finish'] or '',
                'year': listing['year'] or '',
                'mint': listing['mint'] or '',
                'coin_series': listing['coin_series'] or '',
                'grade': listing['grade'] or '',
                'status': 'approved' if listing['active'] else 'pending',
                'created': time_ago,
                'bucket_id': listing['bucket_id']
            })

        # ========== TRANSACTION STATS (for Transactions tab) ==========
        # Exclude cancelled orders from all volume/count stats so figures
        # reflect real economic activity only.

        # Today's volume (non-cancelled orders placed today)
        result = conn.execute('''
            SELECT COALESCE(SUM(total_price), 0) as total
            FROM orders
            WHERE date(created_at) = date('now')
              AND status NOT IN ('Canceled', 'Cancelled')
        ''').fetchone()
        today_volume = result['total'] or 0
        if today_volume >= 1_000_000:
            transaction_stats['today_volume'] = f"${today_volume/1_000_000:.2f}M"
        elif today_volume >= 1_000:
            transaction_stats['today_volume'] = f"${today_volume/1_000:.1f}K"
        else:
            transaction_stats['today_volume'] = f"${today_volume:,.2f}"

        # Transactions today (non-cancelled)
        result = conn.execute('''
            SELECT COUNT(*) as count
            FROM orders
            WHERE date(created_at) = date('now')
              AND status NOT IN ('Canceled', 'Cancelled')
        ''').fetchone()
        transaction_stats['transactions_today'] = f"{result['count']:,}"

        # Average order value (non-cancelled orders only)
        result = conn.execute('''
            SELECT AVG(total_price) as avg_value
            FROM orders
            WHERE status NOT IN ('Canceled', 'Cancelled')
        ''').fetchone()
        avg_value = result['avg_value'] or 0
        transaction_stats['avg_order_value'] = f"${avg_value:,.2f}"

        # Processing orders (active, non-cancelled orders awaiting fulfilment)
        result = conn.execute('''
            SELECT COUNT(*) as count
            FROM orders
            WHERE status IN ('Pending', 'Pending Shipment', 'Processing')
        ''').fetchone()
        transaction_stats['processing'] = f"{result['count']}"

        # ========== ALL TRANSACTIONS (for Transactions tab) ==========
        # LEFT JOINs on listings/seller so orders survive even if a listing
        # or seller account is later deleted.
        all_tx_query = conn.execute('''
            SELECT
                o.id,
                o.buyer_id,
                o.total_price,
                o.status,
                o.created_at,
                buyer.username as buyer_username,
                seller.username as seller_username,
                COUNT(oi.id) as item_count
            FROM orders o
            JOIN users buyer ON o.buyer_id = buyer.id
            LEFT JOIN order_items oi ON o.id = oi.order_id
            LEFT JOIN listings l ON oi.listing_id = l.id
            LEFT JOIN users seller ON l.seller_id = seller.id
            GROUP BY o.id
            ORDER BY o.created_at DESC
            LIMIT 100
        ''').fetchall()

        for tx in all_tx_query:
            created = tx['created_at'] or ''
            time_ago = _format_time_ago(created)

            # Map raw status to a display class
            status = tx['status'] or 'pending'
            status_lower = status.lower()
            if 'cancel' in status_lower:
                display_status = 'cancelled'
            elif 'completed' in status_lower or 'delivered' in status_lower:
                display_status = 'completed'
            elif 'pending' in status_lower or 'processing' in status_lower:
                display_status = 'processing'
            elif 'disputed' in status_lower:
                display_status = 'disputed'
            else:
                display_status = 'completed'

            all_transactions.append({
                'id': tx['id'],
                'buyer': tx['buyer_username'] or 'Unknown',
                'seller': tx['seller_username'] or 'Unknown',
                'items': tx['item_count'],
                'amount': f"${tx['total_price']:,.2f}" if tx['total_price'] else '$0.00',
                'status': display_status,
                'date': time_ago
            })

    except Exception as e:
        print(f"Error getting admin dashboard data: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

    return render_template(
        'admin/dashboard.html',
        stats=stats,
        recent_transactions=recent_transactions,
        recent_users=recent_users,
        recent_listings=recent_listings,
        users=all_users,
        listings=all_listings,
        transactions=all_transactions,
        transaction_stats=transaction_stats
    )


def _format_time_ago(timestamp_str):
    """Format a timestamp string as 'X time ago'"""
    if not timestamp_str:
        return 'Unknown'

    try:
        # Parse the timestamp
        if 'T' in timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        else:
            timestamp = datetime.strptime(timestamp_str[:19], '%Y-%m-%d %H:%M:%S')

        # Make naive if needed
        if timestamp.tzinfo:
            timestamp = timestamp.replace(tzinfo=None)

        now = datetime.now()
        diff = now - timestamp

        # Handle future timestamps
        if diff.total_seconds() < 0:
            return 'Just now'

        days = diff.days
        seconds = diff.seconds

        if days >= 365:
            years = days // 365
            return f"{years} year{'s' if years > 1 else ''} ago"
        elif days >= 30:
            months = days // 30
            return f"{months} month{'s' if months > 1 else ''} ago"
        elif days > 0:
            return f"{days} day{'s' if days > 1 else ''} ago"
        elif seconds >= 3600:
            hours = seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif seconds >= 60:
            minutes = seconds // 60
            return f"{minutes} min ago"
        else:
            return "Just now"
    except Exception:
        return 'Unknown'
