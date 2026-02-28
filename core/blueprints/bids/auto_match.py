# core/blueprints/bids/auto_match.py
"""
Auto-matching helper functions for bids and listings.

These functions handle automatic matching of bids to listings and vice versa,
using the spread model pricing system.
"""

from services.pricing_service import (
    get_effective_price,
    get_effective_bid_price,
    can_bid_fill_listing,
)


def auto_match_bid_to_listings(bid_id, cursor):
    """
    Automatically match a bid to available listings.
    Called immediately after bid creation to auto-fill if possible.

    IMPORTANT: For premium-to-spot bids, this calculates the effective bid price
    (spot + premium, capped at ceiling) and only matches listings at or below that price.

    Args:
        bid_id: The ID of the newly created bid
        cursor: Database cursor (assumes transaction is already open)

    Returns:
        dict with 'filled_quantity', 'orders_created', 'message'
    """
    # Load the bid with all fields including metal and weight for price calculation
    bid = cursor.execute('''
        SELECT b.*, c.metal, c.weight, c.product_type
        FROM bids b
        JOIN categories c ON b.category_id = c.id
        WHERE b.id = ?
    ''', (bid_id,)).fetchone()

    if not bid or bid['remaining_quantity'] <= 0:
        return {'filled_quantity': 0, 'orders_created': 0, 'message': 'No quantity to fill'}

    category_id = bid['category_id']
    buyer_id = bid['buyer_id']
    delivery_address = bid['delivery_address']
    quantity_needed = bid['remaining_quantity']
    recipient_first_name = bid['recipient_first_name']
    recipient_last_name = bid['recipient_last_name']

    # Fetch spot prices from the SAME database connection
    # This ensures test databases and production use consistent spot prices
    spot_prices_rows = cursor.execute('SELECT metal, price_usd_per_oz FROM spot_prices').fetchall()
    spot_prices = {row['metal'].lower(): row['price_usd_per_oz'] for row in spot_prices_rows}

    # Calculate effective bid price (handles both static and premium-to-spot modes)
    # For premium-to-spot, this calculates spot + premium and enforces ceiling
    bid_dict = dict(bid)
    effective_bid_price = get_effective_bid_price(bid_dict, spot_prices=spot_prices)

    # This is the maximum price the buyer will pay
    bid_price = effective_bid_price

    # Query matching listings - fetch ALL fields needed for effective price calculation.
    # We'll filter by effective price in Python after calculating it for each listing.
    # IMPORTANT: Exclude listings from the same user (no self-trades).
    # Grading is NOT used as an eligibility constraint.
    random_year = bid_dict.get('random_year', 0)

    if random_year:
        # Random Year ON: match listings from any category with the same specs except year.
        # Fetch bid's category specs to use for cross-year matching.
        bid_cat = cursor.execute('''
            SELECT metal, product_line, product_type, weight, purity, mint, finish
            FROM categories WHERE id = ?
        ''', (category_id,)).fetchone()

        # Find all category IDs that share the same specs but any year.
        # Use IS for NULL-safe equality (SQLite: NULL IS NULL = TRUE).
        matching_cats = cursor.execute('''
            SELECT id FROM categories
            WHERE metal IS ?
              AND product_line IS ?
              AND product_type IS ?
              AND weight IS ?
              AND purity IS ?
              AND mint IS ?
              AND finish IS ?
        ''', (
            bid_cat['metal'], bid_cat['product_line'], bid_cat['product_type'],
            bid_cat['weight'], bid_cat['purity'], bid_cat['mint'], bid_cat['finish']
        )).fetchall()

        cat_ids = [row['id'] for row in matching_cats] or [category_id]
        placeholders = ','.join('?' * len(cat_ids))

        listings = cursor.execute(f'''
            SELECT l.id, l.seller_id, l.quantity, l.price_per_coin, l.grading_service,
                   l.pricing_mode, l.spot_premium, l.floor_price, l.pricing_metal,
                   c.metal, c.weight
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE l.category_id IN ({placeholders})
              AND l.seller_id != ?
              AND l.active = 1
              AND l.quantity > 0
        ''', cat_ids + [buyer_id]).fetchall()
    else:
        # Standard exact category match (Random Year OFF or unset).
        listings = cursor.execute('''
            SELECT l.id, l.seller_id, l.quantity, l.price_per_coin, l.grading_service,
                   l.pricing_mode, l.spot_premium, l.floor_price, l.pricing_metal,
                   c.metal, c.weight
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE l.category_id = ?
              AND l.seller_id != ?
              AND l.active = 1
              AND l.quantity > 0
        ''', (category_id, buyer_id)).fetchall()

    if not listings:
        return {'filled_quantity': 0, 'orders_created': 0, 'message': 'No matching listings found'}

    # ============================================================================
    # SPREAD MODEL MATCHING
    # Uses can_bid_fill_listing() to match all 4 combinations (fixed/variable)
    # ============================================================================

    # Calculate pricing info for each listing using spread model
    matched_listings = []
    for listing in listings:
        listing_dict = dict(listing)

        # Check if bid can fill this listing (works for all 4 combinations)
        pricing_info = can_bid_fill_listing(bid_dict, listing_dict, spot_prices=spot_prices)

        if pricing_info['can_fill']:
            # Store pricing info on the listing for later use
            listing_dict['bid_effective_price'] = pricing_info['bid_effective_price']
            listing_dict['listing_effective_price'] = pricing_info['listing_effective_price']
            listing_dict['spread'] = pricing_info['spread']
            matched_listings.append(listing_dict)

    # Sort by listing effective price (cheapest for seller first), then by id
    matched_listings.sort(key=lambda x: (x['listing_effective_price'], x['id']))

    if not matched_listings:
        return {'filled_quantity': 0, 'orders_created': 0, 'message': 'No matching listings found (bid price < listing price)'}

    # Group fills by seller (one order per seller)
    # Store BOTH buyer and seller prices for each fill
    seller_fills = {}  # seller_id -> list of {listing_id, quantity, buyer_price, seller_price}
    total_filled = 0

    for listing in matched_listings:
        if total_filled >= quantity_needed:
            break

        seller_id = listing['seller_id']
        available = listing['quantity']
        fill_qty = min(available, quantity_needed - total_filled)

        # Update listing quantity
        new_qty = available - fill_qty
        if new_qty <= 0:
            cursor.execute('UPDATE listings SET quantity = 0, active = 0 WHERE id = ?', (listing['id'],))
        else:
            cursor.execute('UPDATE listings SET quantity = ? WHERE id = ?', (new_qty, listing['id']))

        # Track fill for this seller with BOTH prices
        if seller_id not in seller_fills:
            seller_fills[seller_id] = []

        # SPREAD MODEL:
        # - Buyer pays: bid effective price
        # - Seller receives: listing effective price
        # - Metex keeps: bid effective - listing effective
        seller_fills[seller_id].append({
            'listing_id': listing['id'],
            'quantity': fill_qty,
            'buyer_price_each': listing['bid_effective_price'],      # What buyer pays
            'seller_price_each': listing['listing_effective_price']  # What seller receives
        })

        total_filled += fill_qty

    # Get item description for notifications
    category_info = cursor.execute('''
        SELECT metal, product_type, product_line, weight, year
        FROM categories WHERE id = ?
    ''', (category_id,)).fetchone()

    item_desc_parts = []
    if category_info:
        if category_info['metal']:
            item_desc_parts.append(category_info['metal'])
        if category_info['product_line']:
            item_desc_parts.append(category_info['product_line'])
        if category_info['weight']:
            item_desc_parts.append(category_info['weight'])
    item_description = ' '.join(item_desc_parts) if item_desc_parts else 'Item'

    # Create one order per seller and collect notification data
    orders_created = 0
    notifications_to_send = []

    for seller_id, items in seller_fills.items():
        # Calculate total based on BUYER price (what buyer pays)
        total_price = sum(item['quantity'] * item['buyer_price_each'] for item in items)
        fill_qty = sum(item['quantity'] for item in items)

        # Create order
        cursor.execute('''
            INSERT INTO orders (buyer_id, total_price, shipping_address, status, created_at,
                               recipient_first_name, recipient_last_name)
            VALUES (?, ?, ?, 'Pending Shipment', datetime('now'), ?, ?)
        ''', (buyer_id, total_price, delivery_address, recipient_first_name, recipient_last_name))

        order_id = cursor.lastrowid
        orders_created += 1

        # Create order_items with BOTH buyer and seller prices
        for item in items:
            cursor.execute('''
                INSERT INTO order_items (order_id, listing_id, quantity, price_each, seller_price_each)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                order_id,
                item['listing_id'],
                item['quantity'],
                item['buyer_price_each'],   # What buyer pays
                item['seller_price_each']   # What seller receives
            ))

        # Collect notification data for buyer (will be sent after commit)
        avg_price = total_price / fill_qty if fill_qty > 0 else effective_bid_price
        notifications_to_send.append({
            'buyer_id': buyer_id,
            'order_id': order_id,
            'bid_id': bid_id,
            'item_description': item_description,
            'quantity_filled': fill_qty,
            'price_per_unit': avg_price,
            'total_amount': total_price,
            'is_partial': False,  # Will be updated below
            'remaining_quantity': 0  # Will be updated below
        })

    # Update bid status
    new_remaining = quantity_needed - total_filled
    if new_remaining <= 0:
        # Fully filled
        cursor.execute('''
            UPDATE bids
            SET remaining_quantity = 0,
                active = 0,
                status = 'Filled'
            WHERE id = ?
        ''', (bid_id,))
        message = f'Bid fully filled! Matched {total_filled} items from {orders_created} seller(s).'
    else:
        # Partially filled - update notification data
        cursor.execute('''
            UPDATE bids
            SET remaining_quantity = ?,
                status = 'Partially Filled'
            WHERE id = ?
        ''', (new_remaining, bid_id))
        message = f'Bid partially filled! Matched {total_filled} of {quantity_needed} items from {orders_created} seller(s). {new_remaining} items still open.'

        # Mark notifications as partial fills
        for notif in notifications_to_send:
            notif['is_partial'] = True
            notif['remaining_quantity'] = new_remaining

    return {
        'filled_quantity': total_filled,
        'orders_created': orders_created,
        'message': message,
        'notifications': notifications_to_send
    }


def auto_match_listing_to_bids(listing_id, cursor):
    """
    Automatically match a listing to existing bids.
    Called immediately after listing creation to auto-fill if possible.

    This is the reverse of auto_match_bid_to_listings - when a new listing
    is created, check if any existing bids can be filled by this listing.

    Args:
        listing_id: The ID of the newly created listing
        cursor: Database cursor (assumes transaction is already open)

    Returns:
        dict with 'filled_quantity', 'orders_created', 'message', 'notifications'
    """
    # Load the listing with all fields including extra category specs for random_year matching.
    listing = cursor.execute('''
        SELECT l.*, c.metal, c.weight, c.product_type, c.bucket_id,
               c.product_line, c.purity, c.mint, c.finish
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.id = ?
    ''', (listing_id,)).fetchone()

    if not listing or listing['quantity'] <= 0:
        return {'filled_quantity': 0, 'orders_created': 0, 'message': 'No quantity available', 'notifications': []}

    category_id = listing['category_id']
    seller_id = listing['seller_id']
    quantity_available = listing['quantity']

    # Fetch spot prices from the database
    spot_prices_rows = cursor.execute('SELECT metal, price_usd_per_oz FROM spot_prices').fetchall()
    spot_prices = {row['metal'].lower(): row['price_usd_per_oz'] for row in spot_prices_rows}

    # Calculate effective listing price
    listing_dict = dict(listing)
    effective_listing_price = get_effective_price(listing_dict, spot_prices=spot_prices)

    # Query active bids: exact category match OR random_year=1 bids whose category
    # shares the same specs (metal, product_line, product_type, weight, purity, mint, finish)
    # as this listing's category, regardless of year.
    listing_metal = listing_dict.get('metal')
    listing_product_line = listing_dict.get('product_line')
    listing_product_type = listing_dict.get('product_type')
    listing_weight = listing_dict.get('weight')
    listing_purity = listing_dict.get('purity')
    listing_mint = listing_dict.get('mint')
    listing_finish = listing_dict.get('finish')

    bids = cursor.execute('''
        SELECT b.*, c.metal, c.weight, c.product_type
        FROM bids b
        JOIN categories c ON b.category_id = c.id
        WHERE b.buyer_id != ?
          AND b.active = 1
          AND b.remaining_quantity > 0
          AND (
            b.category_id = ?
            OR (
              b.random_year = 1
              AND c.metal IS ?
              AND c.product_line IS ?
              AND c.product_type IS ?
              AND c.weight IS ?
              AND c.purity IS ?
              AND c.mint IS ?
              AND c.finish IS ?
            )
          )
        ORDER BY b.created_at ASC
    ''', (
        seller_id, category_id,
        listing_metal, listing_product_line, listing_product_type,
        listing_weight, listing_purity, listing_mint, listing_finish
    )).fetchall()

    if not bids:
        return {'filled_quantity': 0, 'orders_created': 0, 'message': 'No matching bids found', 'notifications': []}

    # Get item description for notifications
    item_desc_parts = []
    if listing_dict.get('metal'):
        item_desc_parts.append(listing_dict['metal'])
    if listing_dict.get('product_type'):
        item_desc_parts.append(listing_dict['product_type'])
    if listing_dict.get('weight'):
        item_desc_parts.append(str(listing_dict['weight']))
    item_description = ' '.join(item_desc_parts) if item_desc_parts else 'Item'

    # Match bids that can fill this listing
    matched_bids = []
    for bid in bids:
        bid_dict = dict(bid)

        # Check if bid can fill this listing
        pricing_info = can_bid_fill_listing(bid_dict, listing_dict, spot_prices=spot_prices)

        if pricing_info['can_fill']:
            bid_dict['bid_effective_price'] = pricing_info['bid_effective_price']
            bid_dict['listing_effective_price'] = pricing_info['listing_effective_price']
            bid_dict['spread'] = pricing_info['spread']
            matched_bids.append(bid_dict)

    if not matched_bids:
        return {'filled_quantity': 0, 'orders_created': 0, 'message': 'No matching bids (bid price < listing price)', 'notifications': []}

    # Sort by bid effective price (highest paying bid first)
    matched_bids.sort(key=lambda x: (-x['bid_effective_price'], x['id']))

    # Fill bids with listing inventory
    orders_created = 0
    total_filled = 0
    remaining_inventory = quantity_available
    notifications_to_send = []

    for bid in matched_bids:
        if remaining_inventory <= 0:
            break

        bid_id = bid['id']
        buyer_id = bid['buyer_id']
        bid_remaining = bid['remaining_quantity']
        delivery_address = bid['delivery_address']
        recipient_first_name = bid.get('recipient_first_name', '')
        recipient_last_name = bid.get('recipient_last_name', '')

        # Determine fill quantity
        fill_qty = min(remaining_inventory, bid_remaining)

        # Calculate prices using spread model
        buyer_price_each = bid['bid_effective_price']
        seller_price_each = bid['listing_effective_price']
        total_price = buyer_price_each * fill_qty

        # Create order
        cursor.execute('''
            INSERT INTO orders (buyer_id, total_price, shipping_address, status, created_at,
                               recipient_first_name, recipient_last_name)
            VALUES (?, ?, ?, 'Pending Shipment', datetime('now'), ?, ?)
        ''', (buyer_id, total_price, delivery_address, recipient_first_name, recipient_last_name))

        order_id = cursor.lastrowid
        orders_created += 1

        # Create order item with both prices
        cursor.execute('''
            INSERT INTO order_items (order_id, listing_id, quantity, price_each, seller_price_each)
            VALUES (?, ?, ?, ?, ?)
        ''', (order_id, listing_id, fill_qty, buyer_price_each, seller_price_each))

        # Update bid remaining quantity
        new_bid_remaining = bid_remaining - fill_qty
        if new_bid_remaining <= 0:
            cursor.execute('''
                UPDATE bids SET remaining_quantity = 0, active = 0, status = 'Filled' WHERE id = ?
            ''', (bid_id,))
        else:
            cursor.execute('''
                UPDATE bids SET remaining_quantity = ?, status = 'Partially Filled' WHERE id = ?
            ''', (new_bid_remaining, bid_id))

        # Collect notification data for buyer
        notifications_to_send.append({
            'buyer_id': buyer_id,
            'order_id': order_id,
            'bid_id': bid_id,
            'item_description': item_description,
            'quantity_filled': fill_qty,
            'price_per_unit': buyer_price_each,
            'total_amount': total_price,
            'is_partial': new_bid_remaining > 0,
            'remaining_quantity': new_bid_remaining if new_bid_remaining > 0 else 0
        })

        remaining_inventory -= fill_qty
        total_filled += fill_qty

    # Update listing quantity
    if remaining_inventory <= 0:
        cursor.execute('UPDATE listings SET quantity = 0, active = 0 WHERE id = ?', (listing_id,))
    else:
        cursor.execute('UPDATE listings SET quantity = ? WHERE id = ?', (remaining_inventory, listing_id))

    message = f'Listing auto-filled! Matched {total_filled} items to {orders_created} bid(s).'
    if remaining_inventory > 0:
        message += f' {remaining_inventory} items still available.'

    return {
        'filled_quantity': total_filled,
        'orders_created': orders_created,
        'message': message,
        'notifications': notifications_to_send
    }


def check_all_pending_matches(conn):
    """
    Check all active bids against all active listings for potential matches.
    Called on page load to catch matches that became possible due to spot price changes.

    Args:
        conn: Database connection (will create its own cursor)

    Returns:
        dict with 'total_filled', 'orders_created', 'bids_matched'
    """
    cursor = conn.cursor()

    total_filled = 0
    orders_created = 0
    bids_matched = 0
    notifications_to_send = []

    # Get all active bids with remaining quantity
    active_bids = cursor.execute('''
        SELECT b.id, b.category_id, b.buyer_id
        FROM bids b
        WHERE b.active = 1
          AND b.remaining_quantity > 0
          AND b.status IN ('Open', 'Partially Filled')
        ORDER BY b.created_at ASC
    ''').fetchall()

    if not active_bids:
        return {'total_filled': 0, 'orders_created': 0, 'bids_matched': 0, 'notifications': []}

    for bid_row in active_bids:
        bid_id = bid_row['id']

        # Check if there are any potential listings for this bid's category
        # (from different users)
        potential_listings = cursor.execute('''
            SELECT 1 FROM listings l
            WHERE l.category_id = ?
              AND l.seller_id != ?
              AND l.active = 1
              AND l.quantity > 0
            LIMIT 1
        ''', (bid_row['category_id'], bid_row['buyer_id'])).fetchone()

        if not potential_listings:
            continue

        # Try to match this bid
        result = auto_match_bid_to_listings(bid_id, cursor)

        if result['filled_quantity'] > 0:
            total_filled += result['filled_quantity']
            orders_created += result['orders_created']
            bids_matched += 1
            if result.get('notifications'):
                notifications_to_send.extend(result['notifications'])

    # Commit all changes
    conn.commit()

    return {
        'total_filled': total_filled,
        'orders_created': orders_created,
        'bids_matched': bids_matched,
        'notifications': notifications_to_send
    }
