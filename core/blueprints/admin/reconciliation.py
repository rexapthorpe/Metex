"""
Admin Financial Reconciliation Routes

Endpoints:
  GET /api/reconciliation/stats        — summary stat cards
  GET /api/reconciliation/rows         — paginated payout-row list with filters
  GET /api/reconciliation/order/<id>   — full money-flow detail for one order

Each row in the list corresponds to one order_payouts record (one seller per
order), which is the natural unit for seller-level reconciliation.

Reconciliation statuses (derived, never hardcoded):
  MATCHED          — paid, Stripe ref present, amounts match, transfer confirmed
  AWAITING_TRANSFER — payout eligible/scheduled but transfer not yet issued
  MISSING_TRANSFER  — payout marked PAID_OUT but provider_transfer_id is NULL
  MISSING_STRIPE_REF — payment_status=paid but stripe_payment_intent_id is NULL
  AMOUNT_MISMATCH   — orders.total_price ≠ gross_amount + spread_capture + tax + buyer_card_fee
  MISSING_CARD_FEE  — card payment where buyer_card_fee = 0 (fee calculation skipped)
  PENDING_PAYOUT    — paid + refs present but payout not yet triggered
  UNPAID            — payment not captured yet (normal pre-payment state)

Spread capture accounting:
  When a buyer bids above the seller's ask, the platform retains the difference as
  spread revenue (separate from the percentage/flat platform fee).
  Canonical identity:  total_price = gross_amount + spread_capture_amount + tax + buyer_card_fee
  gross_amount        = seller-side merchandise value (fee basis + seller payout basis)
  spread_capture_amount = buyer premium above seller ask (pure platform revenue)
"""

from flask import jsonify, request
from utils.auth_utils import admin_required
from . import admin_bp
import database as _db_module

_RECON_STATUS_ORDER = [
    'AMOUNT_MISMATCH', 'MISSING_CARD_FEE', 'MISSING_STRIPE_REF',
    'MISSING_TRANSFER', 'AWAITING_TRANSFER', 'MATCHED', 'MATCHED_SPREAD',
    'PENDING_PAYOUT', 'UNPAID',
]


def _get_conn():
    return _db_module.get_db_connection()


def compute_recon_status(row):
    """
    Derive reconciliation status from stored values.
    Returns one of the RECON_STATUS_ORDER values.

    Canonical amount identity (post-tax, post-spread):
      total_price = gross_amount + spread_capture_amount + tax_amount + buyer_card_fee
      gross_amount          = seller-side merchandise (fee basis; 0 spread = buyer price)
      spread_capture_amount = buyer premium above seller ask (platform revenue; 0 for direct checkout)
      tax_amount            = 0 for orders created before migration 031
    """
    payment_status    = (row.get('payment_status') or '').lower()
    payout_status     = (row.get('payout_status') or '')
    stripe_pi         = row.get('stripe_payment_intent_id')
    transfer_id       = row.get('provider_transfer_id')
    total_price       = float(row.get('total_price') or 0)
    gross_amount      = float(row.get('gross_amount') or 0)
    spread_capture    = float(row.get('spread_capture_amount') or 0)
    buyer_card_fee    = float(row.get('buyer_card_fee') or 0)
    tax_amount        = float(row.get('tax_amount') or 0)   # 0 for pre-tax orders
    payment_method    = (row.get('payment_method_type') or row.get('payment_method') or '').lower()

    if payment_status != 'paid':
        return 'UNPAID'

    if not stripe_pi:
        return 'MISSING_STRIPE_REF'

    # Amount integrity: total_price = gross_amount + spread_capture + tax + card_fee
    # spread_capture = 0 for all direct-checkout orders and committed-listing bid fills.
    # A non-zero spread means the buyer bid above the seller's ask; that delta is
    # platform revenue and must NOT trigger a mismatch flag.
    expected = gross_amount + spread_capture + tax_amount + buyer_card_fee
    if abs(total_price - expected) > 0.02:
        return 'AMOUNT_MISMATCH'

    # Card fee sanity: card payment must have a non-zero fee
    is_card = payment_method in ('card',) or (
        'card' in payment_method and 'ach' not in payment_method
    )
    # A card order where the fee was skipped has total == gross + spread + tax (no fee added)
    buyer_subtotal = gross_amount + spread_capture
    if is_card and buyer_card_fee == 0 and abs(total_price - (buyer_subtotal + tax_amount)) < 0.02:
        return 'MISSING_CARD_FEE'

    if payout_status == 'PAID_OUT' and not transfer_id:
        return 'MISSING_TRANSFER'

    if payout_status in ('PAYOUT_READY', 'PAYOUT_SCHEDULED', 'PAYOUT_IN_PROGRESS'):
        return 'AWAITING_TRANSFER'

    if payout_status == 'PAID_OUT' and transfer_id:
        # Distinguish spread orders so admins can report on bid/ask revenue separately
        return 'MATCHED_SPREAD' if spread_capture > 0 else 'MATCHED'

    # Paid, refs present, payout not yet triggered
    return 'PENDING_PAYOUT'


def _is_problem_status(status):
    return status in ('AMOUNT_MISMATCH', 'MISSING_CARD_FEE',
                      'MISSING_STRIPE_REF', 'MISSING_TRANSFER')


def is_spread_order(status):
    """Return True for reconciliation statuses that involve bid/ask spread capture."""
    return status == 'MATCHED_SPREAD'


# ─── Core list query ──────────────────────────────────────────────────────────

_BASE_QUERY = """
    SELECT
        op.id              AS payout_row_id,
        op.order_id,
        op.seller_id,
        op.payout_status,
        op.seller_gross_amount,
        op.fee_amount      AS payout_fee_amount,
        op.seller_net_amount,
        COALESCE(op.spread_capture_amount, 0) AS payout_spread_capture,
        op.provider_transfer_id,
        op.provider_payout_id,
        op.provider_reversal_id,
        op.payout_recovery_status,
        op.created_at      AS payout_created_at,
        op.updated_at      AS payout_updated_at,
        ol.order_status,
        ol.gross_amount,
        ol.platform_fee_amount,
        -- Effective spread: use stored value if non-zero, otherwise derive from order_items.
        -- order_items.seller_price_each is the seller's ask; price_each is what the buyer paid.
        -- For regular checkout orders seller_price_each IS NULL (no spread).
        CASE
            WHEN COALESCE(ol.spread_capture_amount, 0) > 0
            THEN ol.spread_capture_amount
            ELSE COALESCE(
                (SELECT SUM(
                    CASE WHEN oi.seller_price_each IS NOT NULL
                              AND oi.seller_price_each < oi.price_each
                         THEN (oi.price_each - oi.seller_price_each) * oi.quantity
                         ELSE 0 END
                 )
                 FROM order_items oi WHERE oi.order_id = op.order_id),
                0
            )
        END AS spread_capture_amount,
        ol.payment_method,
        ol.created_at      AS order_created_at,
        o.total_price,
        o.payment_status,
        o.refund_status,
        o.payment_method_type,
        o.stripe_payment_intent_id,
        o.stripe_refund_id,
        COALESCE(o.buyer_card_fee, 0)  AS buyer_card_fee,
        COALESCE(o.tax_amount, 0)      AS tax_amount,
        COALESCE(o.tax_rate, 0)        AS tax_rate,
        buyer.username     AS buyer_username,
        buyer.id           AS buyer_id,
        seller.username    AS seller_username
    FROM order_payouts op
    JOIN orders_ledger ol  ON op.order_ledger_id = ol.id
    JOIN orders o          ON op.order_id = o.id
    LEFT JOIN users buyer  ON o.buyer_id  = buyer.id
    LEFT JOIN users seller ON op.seller_id = seller.id
    WHERE 1=1
"""


def _build_rows(conn, extra_where='', params=None,
                limit=100, offset=0):
    if params is None:
        params = []
    sql = _BASE_QUERY + extra_where + \
          ' ORDER BY ol.created_at DESC LIMIT ? OFFSET ?'
    params = list(params) + [limit, offset]
    rows = conn.execute(sql, params).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        # total_charged = seller gross + spread capture + tax + card fee = buyer subtotal + tax + fee
        d['total_charged'] = round(
            float(d['gross_amount']) + float(d.get('spread_capture_amount', 0)) +
            float(d.get('tax_amount', 0)) + float(d['buyer_card_fee']), 2)
        d['recon_status'] = compute_recon_status(d)
        d['is_problem'] = _is_problem_status(d['recon_status'])
        result.append(d)
    return result


# ─── Routes ───────────────────────────────────────────────────────────────────

@admin_bp.route('/api/reconciliation/stats')
@admin_required
def reconciliation_stats():
    """Summary stats for the reconciliation tab header cards."""
    try:
        conn = _get_conn()

        # Fetch all rows (no limit) to compute status breakdown
        rows = _build_rows(conn, limit=5000, offset=0)

        total = len(rows)
        matched = sum(1 for r in rows if r['recon_status'] == 'MATCHED')
        problems = sum(1 for r in rows if r['is_problem'])
        awaiting = sum(1 for r in rows if r['recon_status'] == 'AWAITING_TRANSFER')
        unpaid   = sum(1 for r in rows if r['recon_status'] == 'UNPAID')

        # Total volume (gross_amount across all paid payouts)
        paid_rows = [r for r in rows if r['payment_status'] == 'paid']
        total_volume = round(sum(float(r['gross_amount']) for r in paid_rows), 2)

        conn.close()
        return jsonify({
            'success': True,
            'stats': {
                'total_rows':    total,
                'matched':       matched,
                'problems':      problems,
                'awaiting':      awaiting,
                'unpaid':        unpaid,
                'total_volume':  total_volume,
            }
        })
    except Exception as e:
        print(f'[Reconciliation] stats error: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/reconciliation/rows')
@admin_required
def reconciliation_rows():
    """
    Paginated reconciliation row list.

    Query params (all optional):
      payment_status   — paid | unpaid
      payout_status    — PAYOUT_NOT_READY | PAYOUT_READY | ... | PAID_OUT
      payment_method   — card | ach
      recon_status     — MATCHED | AWAITING_TRANSFER | MISSING_TRANSFER | ...
      start_date       — YYYY-MM-DD (inclusive)
      end_date         — YYYY-MM-DD (inclusive)
      order_id         — exact integer
      stripe_ref       — substring match on stripe_payment_intent_id or
                         provider_transfer_id
      seller           — seller username substring
      buyer            — buyer username substring
      limit            — default 100, max 200
      offset           — default 0
    """
    try:
        conn = _get_conn()

        payment_status_f = request.args.get('payment_status', '').strip()
        payout_status_f  = request.args.get('payout_status',  '').strip()
        payment_method_f = request.args.get('payment_method', '').strip()
        start_date       = request.args.get('start_date',     '').strip()
        end_date         = request.args.get('end_date',       '').strip()
        order_id_f       = request.args.get('order_id',       '').strip()
        stripe_ref       = request.args.get('stripe_ref',     '').strip()
        seller_f         = request.args.get('seller',         '').strip()
        buyer_f          = request.args.get('buyer',          '').strip()
        limit            = min(request.args.get('limit',  100, type=int), 200)
        offset           = request.args.get('offset', 0, type=int)

        where_clauses = []
        params = []

        if payment_status_f:
            where_clauses.append(' AND o.payment_status = ?')
            params.append(payment_status_f)

        if payout_status_f:
            where_clauses.append(' AND op.payout_status = ?')
            params.append(payout_status_f)

        if payment_method_f:
            where_clauses.append(' AND (o.payment_method_type LIKE ? OR ol.payment_method LIKE ?)')
            params.extend([f'%{payment_method_f}%', f'%{payment_method_f}%'])

        if start_date:
            where_clauses.append(' AND ol.created_at >= ?')
            params.append(start_date)

        if end_date:
            where_clauses.append(' AND ol.created_at < ?')
            # Make inclusive by bumping to next day
            from datetime import datetime, timedelta
            try:
                dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                params.append(dt.strftime('%Y-%m-%d'))
            except ValueError:
                params.append(end_date)

        if order_id_f:
            try:
                where_clauses.append(' AND op.order_id = ?')
                params.append(int(order_id_f))
            except ValueError:
                pass

        if stripe_ref:
            where_clauses.append(
                ' AND (o.stripe_payment_intent_id LIKE ? OR op.provider_transfer_id LIKE ?)')
            params.extend([f'%{stripe_ref}%', f'%{stripe_ref}%'])

        if seller_f:
            where_clauses.append(' AND seller.username LIKE ?')
            params.append(f'%{seller_f}%')

        if buyer_f:
            where_clauses.append(' AND buyer.username LIKE ?')
            params.append(f'%{buyer_f}%')

        extra_where = ''.join(where_clauses)
        rows = _build_rows(conn, extra_where=extra_where, params=params,
                           limit=limit, offset=offset)

        # Post-filter by recon_status (can't push into SQL)
        recon_status_f = request.args.get('recon_status', '').strip()
        if recon_status_f:
            rows = [r for r in rows if r['recon_status'] == recon_status_f]

        conn.close()
        return jsonify({'success': True, 'rows': rows, 'count': len(rows)})

    except Exception as e:
        print(f'[Reconciliation] rows error: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/reconciliation/order/<int:order_id>')
@admin_required
def reconciliation_order_detail(order_id):
    """
    Full money-flow detail for one order: all payout rows plus Stripe IDs.
    """
    try:
        conn = _get_conn()

        rows = _build_rows(conn,
                           extra_where=' AND op.order_id = ?',
                           params=[order_id],
                           limit=50, offset=0)

        if not rows:
            conn.close()
            return jsonify({'success': False, 'error': 'Order not found'}), 404

        # Order-level fields (same for all rows in an order)
        first = rows[0]

        # Fetch refund/reversal info from orders directly
        o_row = conn.execute(
            '''SELECT stripe_refund_id, refund_status, refund_amount, refunded_at,
                      refund_reason, requires_payout_recovery, stripe_payment_intent_id,
                      payment_method_type, payment_status,
                      COALESCE(buyer_card_fee, 0) AS buyer_card_fee,
                      COALESCE(tax_amount, 0)     AS tax_amount,
                      COALESCE(tax_rate, 0)        AS tax_rate,
                      total_price
               FROM orders WHERE id = ?''',
            (order_id,)
        ).fetchone()
        order_meta = dict(o_row) if o_row else {}

        conn.close()

        _tax_amount     = float(order_meta.get('tax_amount') or 0)
        _tax_rate       = float(order_meta.get('tax_rate') or 0)
        _spread_capture = float(first.get('spread_capture_amount') or 0)
        _buyer_subtotal = round(float(first['gross_amount']) + _spread_capture, 2)
        total_charged   = round(_buyer_subtotal + _tax_amount + float(first['buyer_card_fee']), 2)
        total_platform_fee = round(
            sum(float(r['payout_fee_amount']) for r in rows), 2)
        total_seller_net = round(
            sum(float(r['seller_net_amount']) for r in rows), 2)
        # Total platform revenue = fee (on seller gross) + spread capture (buyer premium)
        total_platform_revenue = round(total_platform_fee + _spread_capture, 2)

        return jsonify({
            'success': True,
            'order_id': order_id,
            'money_flow': {
                'subtotal':               float(first['gross_amount']),  # seller-side gross
                'spread_capture':         _spread_capture,               # platform spread revenue
                'buyer_subtotal':         _buyer_subtotal,               # = subtotal + spread
                'tax_amount':             _tax_amount,
                'tax_rate':               _tax_rate,
                'buyer_card_fee':         float(first['buyer_card_fee']),
                'total_charged':          total_charged,
                'platform_fee':           total_platform_fee,
                'total_platform_revenue': total_platform_revenue,
                'total_seller_net':       total_seller_net,
            },
            'payment': {
                'stripe_payment_intent_id': order_meta.get('stripe_payment_intent_id'),
                'payment_status':           order_meta.get('payment_status'),
                'payment_method':           order_meta.get('payment_method_type'),
                'total_price_stored':       float(order_meta.get('total_price') or 0),
            },
            'refund': {
                'stripe_refund_id':  order_meta.get('stripe_refund_id'),
                'refund_status':     order_meta.get('refund_status'),
                'refund_amount':     float(order_meta.get('refund_amount') or 0),
                'refunded_at':       order_meta.get('refunded_at'),
                'refund_reason':     order_meta.get('refund_reason'),
            },
            'payout_rows': rows,
            'order_status':   first['order_status'],
            'order_created_at': first['order_created_at'],
            'buyer_username': first['buyer_username'],
            'buyer_id':       first['buyer_id'],
        })

    except Exception as e:
        print(f'[Reconciliation] detail error for order {order_id}: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500
