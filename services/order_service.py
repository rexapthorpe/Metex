import json
from datetime import datetime

import database as _db_module


def _get_conn():
    return _db_module.get_db_connection()


def write_order_item_snapshot(cursor, order_id, order_item_id, listing_id,
                               quantity, price_each, buyer_id,
                               buyer_username=None, buyer_email=None,
                               pricing_mode_used=None, spot_info=None,
                               payment_intent_id=None):
    """
    Write one row to transaction_snapshots for a purchased order item.

    Must be called with a cursor that is already inside an active transaction
    so the snapshot is committed atomically with the order row(s).

    Args:
        cursor:            Active DB cursor (same transaction as order creation).
        order_id:          The order just created.
        order_item_id:     The order_items row just created (or None).
        listing_id:        The listing that was purchased.
        quantity:          Items purchased.
        price_each:        Effective price paid per item.
        buyer_id:          Buyer's user ID.
        buyer_username:    Pre-fetched username (avoids extra query if already known).
        buyer_email:       Pre-fetched email (avoids extra query if already known).
        pricing_mode_used: 'static' or 'premium_to_spot'.
        spot_info:         dict with 'price_usd' key, or None.
        payment_intent_id: Stripe PaymentIntent ID if available at snapshot time.
    """
    snapshot_at = datetime.now().isoformat()

    # Query listing + joined category + seller in one shot
    listing_row = cursor.execute('''
        SELECT l.listing_title, l.description,
               l.packaging_type, l.packaging_notes, l.condition_notes,
               l.seller_id,
               c.metal, c.product_line, c.product_type, c.weight, c.year,
               c.mint, c.purity, c.finish, c.condition_category, c.series_variant
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.id = ?
    ''', (listing_id,)).fetchone()

    if listing_row:
        seller_id = listing_row['seller_id']
        seller_row = cursor.execute(
            'SELECT username, email FROM users WHERE id = ?', (seller_id,)
        ).fetchone()
        seller_username = seller_row['username'] if seller_row else None
        seller_email = seller_row['email'] if seller_row else None

        photo_rows = cursor.execute(
            'SELECT file_path FROM listing_photos WHERE listing_id = ? ORDER BY id',
            (listing_id,)
        ).fetchall()
        photo_filenames = ','.join(r['file_path'] for r in photo_rows) if photo_rows else None

        spot_price = spot_info['price_usd'] if spot_info else None

        cursor.execute('''
            INSERT INTO transaction_snapshots (
                order_id, order_item_id, snapshot_at,
                listing_id, listing_title, listing_description,
                metal, product_line, product_type, weight, year, mint, purity, finish,
                condition_category, series_variant,
                packaging_type, packaging_notes, condition_notes,
                photo_filenames,
                quantity, price_each, pricing_mode, spot_price_at_purchase,
                seller_id, seller_username, seller_email,
                buyer_id, buyer_username, buyer_email,
                payment_intent_id
            ) VALUES (
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?,
                ?, ?, ?,
                ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?
            )
        ''', (
            order_id, order_item_id, snapshot_at,
            listing_id, listing_row['listing_title'], listing_row['description'],
            listing_row['metal'], listing_row['product_line'], listing_row['product_type'],
            listing_row['weight'], listing_row['year'], listing_row['mint'],
            listing_row['purity'], listing_row['finish'],
            listing_row['condition_category'], listing_row['series_variant'],
            listing_row['packaging_type'], listing_row['packaging_notes'],
            listing_row['condition_notes'],
            photo_filenames,
            quantity, price_each, pricing_mode_used, spot_price,
            seller_id, seller_username, seller_email,
            buyer_id, buyer_username, buyer_email,
            payment_intent_id,
        ))
    else:
        # Listing may have been deleted between selection and order creation (race).
        # Write a minimal snapshot so the order_item still has an evidence row.
        cursor.execute('''
            INSERT INTO transaction_snapshots (
                order_id, order_item_id, snapshot_at,
                listing_id, quantity, price_each,
                buyer_id, buyer_username, buyer_email,
                payment_intent_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            order_id, order_item_id, snapshot_at,
            listing_id, quantity, price_each,
            buyer_id, buyer_username, buyer_email,
            payment_intent_id,
        ))


def calculate_cart_total(cart_items):
    """Calculate item-only total (excludes grading fees)."""
    total = 0
    for item in cart_items:
        total += item['price_each'] * item['quantity']
    return round(total, 2)


def create_order(buyer_id, cart_items, shipping_address, recipient_first='', recipient_last='',
                  placed_from_ip=None, payment_intent_id=None, buyer_card_fee=0.0,
                  tax_amount=0.0, tax_rate=0.0):
    """
    Create a new order and related order items.

    Each item in cart_items must have: listing_id, quantity, price_each.

    Pricing order (canonical):
      subtotal        = sum of item line totals
      tax_amount      = round(subtotal * tax_rate, 2)   — locked at checkout time
      buyer_card_fee  = round((subtotal + tax_amount) * 0.0299 + 0.30, 2)  for card; 0 for ACH
      total_price     = subtotal + tax_amount + buyer_card_fee

    Phase 1 additions:
      placed_from_ip:    Buyer's IP address at checkout submission.
      payment_intent_id: Stripe PaymentIntent ID written to transaction_snapshots.
      buyer_card_fee:    Card processing fee applied to taxed subtotal (2.99%+$0.30 for
                         card, 0.0 for ACH). orders.total_price equals Stripe charge amount.
      tax_amount:        Tax in dollars, locked at checkout so history is immutable.
      tax_rate:          Rate applied (e.g. 0.0825), stored for audit purposes.
    """
    conn = _get_conn()
    cursor = conn.cursor()

    items_total = calculate_cart_total(cart_items)
    buyer_card_fee = round(float(buyer_card_fee), 2)
    tax_amount = round(float(tax_amount), 2)
    tax_rate = float(tax_rate)
    total_price = round(items_total + tax_amount + buyer_card_fee, 2)

    cursor.execute('''
        INSERT INTO orders (buyer_id, total_price, buyer_card_fee, tax_amount, tax_rate,
                            shipping_address, recipient_first_name, recipient_last_name,
                            placed_from_ip)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (buyer_id, total_price, buyer_card_fee, tax_amount, tax_rate,
          shipping_address, recipient_first, recipient_last, placed_from_ip))

    order_id = cursor.lastrowid

    # Fetch buyer info once for all snapshot rows
    buyer_row = cursor.execute(
        'SELECT username, email FROM users WHERE id = ?', (buyer_id,)
    ).fetchone()
    buyer_username = buyer_row['username'] if buyer_row else None
    buyer_email = buyer_row['email'] if buyer_row else None

    for item in cart_items:
        # Spot audit fields (populated when checkout_spot_service was used)
        spot_info = item.get('spot_info')  # {price_usd, as_of, source} or None
        spot_price_at_purchase = spot_info['price_usd'] if spot_info else None
        spot_as_of_used = spot_info['as_of'] if spot_info else None
        spot_source_used = spot_info['source'] if spot_info else None
        pricing_mode_at_purchase = item.get('pricing_mode_used')
        spot_premium_used = item.get('spot_premium_used')
        weight_used = item.get('weight_used')

        cursor.execute('''
            INSERT INTO order_items (order_id, listing_id, quantity, price_each,
                                     spot_price_at_purchase, spot_as_of_used,
                                     spot_source_used, pricing_mode_at_purchase,
                                     spot_premium_used, weight_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (order_id, item['listing_id'], item['quantity'], item['price_each'],
              spot_price_at_purchase, spot_as_of_used,
              spot_source_used, pricing_mode_at_purchase,
              spot_premium_used, weight_used))

        order_item_id = cursor.lastrowid

        # Phase 1: write immutable transaction snapshot for this order item.
        write_order_item_snapshot(
            cursor=cursor,
            order_id=order_id,
            order_item_id=order_item_id,
            listing_id=item['listing_id'],
            quantity=item['quantity'],
            price_each=item['price_each'],
            buyer_id=buyer_id,
            buyer_username=buyer_username,
            buyer_email=buyer_email,
            pricing_mode_used=item.get('pricing_mode_used'),
            spot_info=spot_info,
            payment_intent_id=payment_intent_id,
        )

    conn.commit()
    conn.close()

    return order_id
