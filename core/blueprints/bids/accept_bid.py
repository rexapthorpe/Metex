"""
Accept Bid Routes

Contains routes for accepting and cancelling bids:
- /accept_bid/<bucket_id> (POST) - Accept one or more bids from a bucket
- /cancel/<bid_id> (POST) - Cancel an active bid
"""

import logging
import stripe
from flask import request, redirect, url_for, session, flash, jsonify
from database import get_db_connection
from services.notification_service import notify_bid_filled
from services.notification_types import notify_bid_payment_failed
from services.pricing_service import get_effective_price, get_effective_bid_price

from . import bid_bp

_log = logging.getLogger(__name__)

# Must match place_bid.py — buyers reaching this threshold are blocked from placing new bids
_BID_STRIKE_THRESHOLD = 3

# ── Charge components ────────────────────────────────────────────────────────
# These must stay in sync with core/blueprints/checkout/routes.py.
# Bid payments are always card payments (the buyer's saved card on file).
_CARD_RATE = 0.0299   # 2.99%
_CARD_FLAT = 0.0     # $0.30 fixed per transaction

# Must match the fallback rate in core/blueprints/checkout/routes.py
# and the preview rate in static/js/modals/bid_modal_steps.js.
# Applied when Stripe Tax is unavailable but a postal code is present.
FALLBACK_TAX_RATE = 0.0  # 8.25%


def _parse_address_for_tax(delivery_address: str):
    """
    Extract (postal_code, state) from a bullet-separated delivery_address string.
    Format: "Line1 [• Line2] • City, STATE ZIP"
    Returns ('', '') if parsing fails.
    """
    import re
    if not delivery_address:
        return '', ''
    parts = [p.strip() for p in delivery_address.split('•')]
    last = parts[-1] if parts else ''
    m = re.search(r'\b([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\s*$', last)
    if m:
        return m.group(2), m.group(1)  # (postal_code, state)
    return '', ''


def _get_stripe_tax_for_bid(subtotal_cents: int, postal_code: str, state: str = '') -> int:
    """
    Look up sales tax via Stripe Tax for a bid-acceptance charge.
    Returns tax in cents.

    - No postal code or zero subtotal → 0 (no address, cannot tax)
    - Stripe Tax succeeds → exact Stripe-computed cents
    - Stripe Tax fails with postal code present → FALLBACK_TAX_RATE * subtotal
      (keeps the charge consistent with what the bid modal preview shows)
    """
    if not postal_code or subtotal_cents <= 0:
        return 0
    try:
        calc = stripe.tax.Calculation.create(
            currency='usd',
            line_items=[{'amount': subtotal_cents, 'reference': 'bid_subtotal'}],
            customer_details={
                'address': {
                    'postal_code': str(postal_code).strip(),
                    'state': str(state).strip() if state else '',
                    'country': 'US',
                },
                'address_source': 'shipping',
            },
        )
        _log.info('[BID TAX] Stripe calc=%s subtotal_cents=%d tax_cents=%d',
                  calc.id, subtotal_cents, calc.tax_amount_exclusive)
        return int(calc.tax_amount_exclusive)
    except Exception as exc:
        _log.error('[BID TAX] Stripe Tax unavailable; execution blocked: %s', exc)
        raise


@bid_bp.route('/accept_bid/<int:bucket_id>', methods=['POST'])
def accept_bid(bucket_id):
    """Accept each selected bid as an independent canonical payment/execution."""
    if 'user_id' not in session:
        return jsonify(success=False,message='Authentication required.'),401
    seller_id=session['user_id']; selected=request.form.getlist('selected_bids')
    if not selected:
        return jsonify(success=False,message='No bids selected.'),400
    from services.flow_of_funds import FlowError, execute_bid_fill
    conn=get_db_connection(); cursor=conn.cursor(); results=[]; failures=[]
    try:
        spots={}
        try:
            rows=cursor.execute("SELECT metal,price_usd FROM spot_price_snapshots WHERE id IN (SELECT MAX(id) FROM spot_price_snapshots GROUP BY metal)").fetchall()
            spots={r['metal'].lower():float(r['price_usd']) for r in rows}
        except Exception: pass
        for raw_id in selected:
            bid_id=int(raw_id)
            bid=cursor.execute("SELECT b.*,c.metal,c.weight FROM bids b JOIN categories c ON c.id=b.category_id WHERE b.id=?",(bid_id,)).fetchone()
            if not bid or bid['buyer_id']==seller_id or not bid['active']:
                failures.append({'bid_id':bid_id,'reason':'Bid is no longer eligible.'}); continue
            key=f'accept_qty[{bid_id}]'; qty=int(request.form.get(key,request.form.get(f'quantity_{bid_id}',0)) or 0)
            qty=min(qty,int(bid['remaining_quantity'] or 0))
            if qty<=0: continue
            if not bid['bid_payment_method_id']:
                failures.append({'bid_id':bid_id,'reason':'Buyer payment method is missing.'}); continue
            pm=stripe.PaymentMethod.retrieve(bid['bid_payment_method_id']); rail=pm.type
            if rail not in ('card','us_bank_account'):
                failures.append({'bid_id':bid_id,'reason':'Unsupported payment method.'}); continue
            buyer=cursor.execute('SELECT stripe_customer_id FROM users WHERE id=?',(bid['buyer_id'],)).fetchone()
            if not buyer or not buyer['stripe_customer_id']:
                failures.append({'bid_id':bid_id,'reason':'Buyer payment account is missing.'}); continue
            buyer_price=get_effective_bid_price(dict(bid),spot_prices=spots)
            listings=cursor.execute("SELECT l.*,c.metal,c.weight FROM listings l JOIN categories c ON c.id=l.category_id WHERE l.category_id=? AND l.seller_id=? AND l.active=1 AND l.quantity>0 ORDER BY l.price_per_coin,l.id",(bid['category_id'],seller_id)).fetchall()
            items=[]; remaining=qty
            for listing in listings:
                ask=get_effective_price(dict(listing),spot_prices=spots)
                if ask>buyer_price or remaining<=0: continue
                take=min(remaining,int(listing['quantity'])); items.append({'listing_id':listing['id'],'quantity':take,'price_each':buyer_price,'seller_price_each':ask,'source_bid_id':bid_id,'requires_grading':bool(bid['requires_grading'])}); remaining-=take
            if remaining:
                cursor.execute('INSERT INTO listings (category_id,seller_id,quantity,price_per_coin,active) VALUES (?,?,?,?,1)',(bid['category_id'],seller_id,remaining,buyer_price))
                items.append({'listing_id':cursor.lastrowid,'quantity':remaining,'price_each':buyer_price,'seller_price_each':buyer_price,'source_bid_id':bid_id,'requires_grading':bool(bid['requires_grading'])}); conn.commit()
            subtotal_cents=sum(round(i['price_each']*100)*i['quantity'] for i in items)
            postal,state=_parse_address_for_tax(bid['delivery_address']); tax_cents=_get_stripe_tax_for_bid(subtotal_cents,postal,state)
            shipping={'shipping_address':bid['delivery_address'],'recipient_first':bid['recipient_first_name'],'recipient_last':bid['recipient_last_name'],'postal_code':postal,'state':state,'country':'US'}
            try:
                outcome=execute_bid_fill(bid_id,bid['buyer_id'],seller_id,items,rail,tax_cents,shipping,bid['bid_payment_method_id'],buyer['stripe_customer_id'])
                results.append({'bid_id':bid_id,**outcome})
            except Exception as exc:
                failures.append({'bid_id':bid_id,'reason':str(exc)})
                try: notify_bid_payment_failed(bid['buyer_id'],bid_id,str(exc))
                except Exception: pass
        conn.close()
    except FlowError as exc:
        conn.close(); return jsonify(success=False,message=str(exc),error_code=exc.code),exc.status
    except Exception:
        conn.close(); _log.exception('Canonical bid acceptance failed')
        return jsonify(success=False,message='Bid acceptance could not be completed.'),500
    if request.headers.get('X-Requested-With')=='XMLHttpRequest':
        return jsonify(success=bool(results),filled_count=len(results),executions=results,payment_failures=failures,message='Bid fill submitted.' if results else 'No bid was filled.')
    flash('Bid fill submitted.' if results else 'No bid was filled.','success' if results else 'warning')
    return redirect(url_for('buy.view_bucket',bucket_id=bucket_id))


@bid_bp.route('/cancel/<int:bid_id>', methods=['POST'])
def cancel_bid(bid_id):
    # 1) Auth guard
    if 'user_id' not in session:
        # AJAX?
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(error="Authentication required"), 401
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    # 2) Verify bid exists & is owned by this user
    row = cursor.execute(
        'SELECT active, status, remaining_quantity FROM bids WHERE id = ? AND buyer_id = ?',
        (bid_id, user_id)
    ).fetchone()

    if not row:
        conn.close()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(error="Bid not found"), 404
        flash("❌ Bid not found.", "error")
        return redirect(url_for('bid.my_bids'))

    # Check if bid can be cancelled (must be active with remaining quantity)
    # Allow cancelling 'Open' or 'Partially Filled' bids that still have remaining quantity
    if not row['active'] or (row['remaining_quantity'] or 0) <= 0:
        conn.close()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(error="This bid cannot be cancelled (already inactive or fully filled)"), 400
        flash("❌ This bid cannot be cancelled (already inactive or fully filled).", "error")
        return redirect(url_for('bid.my_bids'))

    # 3) Soft‐delete it
    cursor.execute(
        '''
        UPDATE bids
           SET active = 0,
               status = 'Cancelled'
         WHERE id = ? AND buyer_id = ?
        ''',
        (bid_id, user_id)
    )
    conn.commit()
    conn.close()

    # 4) Response
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return ('', 204)

    flash("✅ Your bid has been cancelled.", "success")
    return redirect(request.referrer or url_for('bid.my_bids'))
