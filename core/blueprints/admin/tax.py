"""
Admin Sales Tax Tab Routes

Endpoints:
  GET /admin/api/tax/stats              — summary stat cards
  GET /admin/api/tax/rows               — paginated order-level tax records
  GET /admin/api/tax/export             — CSV export of filtered records
  GET /admin/api/tax/jurisdiction-summary — aggregate by state/country

Tax Liability Accounting:
  Tax Collected     = SUM(tax_amount) for paid orders
  Tax Refunded      = SUM(tax_amount) for fully-refunded orders only.
                      Partial-refund tax attribution is not supported yet —
                      refunded_tax is shown as 0 for partial refunds.
  Net Tax Liability = Tax Collected - Tax Refunded

Tax is buyer-collected liability held by the platform for reporting/remittance.
It is NOT platform revenue and NOT seller revenue.
"""

import re
import csv
import io
from datetime import datetime, timedelta
from flask import jsonify, request, Response
from utils.auth_utils import admin_required
from . import admin_bp
import database as _db_module


def _get_conn():
    return _db_module.get_db_connection()


def _parse_state_zip(address: str):
    """Extract (state_abbr, postal_code) from bullet-separated delivery_address.

    Format: 'Line1 [• Line2] • City, STATE ZIP'
    Returns ('', '') if parsing fails.
    NOTE: Duplicated from accept_bid.py/_parse_address_for_tax — both must stay in sync.
    """
    if not address:
        return '', ''
    parts = [p.strip() for p in address.split('•')]
    last = parts[-1] if parts else ''
    m = re.search(r'\b([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\s*$', last)
    if m:
        return m.group(1), m.group(2)
    return '', ''


def _is_full_refund(row):
    """True if the order was fully refunded (refund_amount ≈ total_price)."""
    if (row.get('refund_status') or '').lower() != 'refunded':
        return False
    ra = float(row.get('refund_amount') or 0)
    tp = float(row.get('total_price') or 0)
    return tp > 0 and abs(ra - tp) < 0.02


def _compute_row_tax_fields(d: dict) -> dict:
    """Enrich a raw order dict with derived tax fields."""
    state, postal = _parse_state_zip(d.get('address') or '')
    d['state']           = state
    d['postal']          = postal
    d['country']         = 'US' if state else ''
    d['refunded_tax']    = float(d['tax_amount']) if _is_full_refund(d) else 0.0
    d['net_tax']         = round(float(d['tax_amount']) - d['refunded_tax'], 2)
    # Taxable subtotal = total_price - tax - card_fee
    d['taxable_subtotal'] = round(
        float(d['total_price']) - float(d['tax_amount']) - float(d['buyer_card_fee']), 2)
    return d


# ── Base SELECT (orders + buyer join) ─────────────────────────────────────────

_BASE_SELECT = """
    SELECT
        o.id                                          AS order_id,
        o.created_at,
        o.total_price,
        COALESCE(o.tax_amount, 0)                     AS tax_amount,
        COALESCE(o.tax_rate, 0)                       AS tax_rate,
        COALESCE(o.buyer_card_fee, 0)                 AS buyer_card_fee,
        o.payment_status,
        COALESCE(o.refund_status, 'not_refunded')     AS refund_status,
        COALESCE(o.refund_amount, 0)                  AS refund_amount,
        o.stripe_payment_intent_id,
        COALESCE(o.shipping_address, '')              AS address,
        u.username                                    AS buyer_username,
        o.buyer_id
    FROM orders o
    LEFT JOIN users u ON o.buyer_id = u.id
"""


def _build_filters(args):
    """Build (where_str, params, state_f) from request args.

    where_str: a SQL AND clause fragment (no leading WHERE keyword), or '' for none.
    state_f:   uppercase state abbreviation to filter post-fetch (requires address parsing).
    """
    clauses = []
    params  = []
    state_f = (args.get('state') or '').strip().upper()

    start = (args.get('start_date') or '').strip()
    end   = (args.get('end_date')   or '').strip()
    pmt   = (args.get('payment_status') or '').strip()
    ref   = (args.get('refund_status')  or '').strip()

    if start:
        clauses.append('o.created_at >= ?')
        params.append(start)
    if end:
        try:
            dt = datetime.strptime(end, '%Y-%m-%d') + timedelta(days=1)
            clauses.append('o.created_at < ?')
            params.append(dt.strftime('%Y-%m-%d'))
        except ValueError:
            clauses.append('o.created_at <= ?')
            params.append(end)
    if pmt:
        clauses.append('o.payment_status = ?')
        params.append(pmt)
    if ref:
        clauses.append("COALESCE(o.refund_status, 'not_refunded') = ?")
        params.append(ref)

    where_str = ' AND '.join(clauses) if clauses else ''
    return where_str, params, state_f


def _fetch_tax_rows(conn, where_str='', params=None, limit=200, offset=0,
                    paid_only=False, tax_only=True):
    """
    Fetch orders with tax data from the DB.

    paid_only: if True, restrict to payment_status = 'paid'
    tax_only:  if True, restrict to tax_amount > 0 (for row/export views)
    """
    if params is None:
        params = []

    clauses = []
    if where_str:
        clauses.append(where_str)
    if paid_only:
        clauses.append("o.payment_status = 'paid'")
    if tax_only:
        clauses.append('COALESCE(o.tax_amount, 0) > 0')

    where_clause = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
    sql = (_BASE_SELECT + where_clause
           + ' ORDER BY o.created_at DESC LIMIT ? OFFSET ?')
    rows = conn.execute(sql, list(params) + [limit, offset]).fetchall()
    return [_compute_row_tax_fields(dict(r)) for r in rows]


# ── Routes ────────────────────────────────────────────────────────────────────

@admin_bp.route('/api/tax/stats')
@admin_required
def tax_stats():
    """Summary stat cards for the Sales Tax tab."""
    try:
        conn   = _get_conn()
        args   = request.args
        where_str, params, state_f = _build_filters(args)

        # Fetch all paid rows (no tax_only filter — zero-tax orders count as taxable=$0)
        paid_rows = _fetch_tax_rows(conn, where_str=where_str, params=params,
                                    limit=100000, offset=0,
                                    paid_only=True, tax_only=False)

        if state_f:
            paid_rows = [r for r in paid_rows if r['state'] == state_f]

        total_tax_collected = round(
            sum(float(r.get('tax_amount') or 0) for r in paid_rows), 2)
        taxable_orders = sum(
            1 for r in paid_rows if float(r.get('tax_amount') or 0) > 0)
        total_tax_refunded = round(
            sum(r['refunded_tax'] for r in paid_rows), 2)
        net_tax_liability = round(total_tax_collected - total_tax_refunded, 2)

        now_str    = datetime.now().strftime('%Y-%m-01')
        this_month = round(
            sum(float(r.get('tax_amount') or 0)
                for r in paid_rows
                if str(r.get('created_at') or '') >= now_str), 2)

        conn.close()
        return jsonify({
            'success': True,
            'stats': {
                'total_tax_collected':  total_tax_collected,
                'total_tax_refunded':   total_tax_refunded,
                'net_tax_liability':    net_tax_liability,
                'taxable_orders':       taxable_orders,
                'this_month_collected': this_month,
            }
        })
    except Exception as e:
        print(f'[Tax] stats error: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/tax/rows')
@admin_required
def tax_rows():
    """Paginated order-level tax records (tax_amount > 0 only)."""
    try:
        conn  = _get_conn()
        args  = request.args
        where_str, params, state_f = _build_filters(args)
        limit  = min(args.get('limit',  100, type=int), 500)
        offset = args.get('offset', 0, type=int)

        rows = _fetch_tax_rows(conn, where_str=where_str, params=params,
                               limit=limit + 1, offset=offset, tax_only=True)

        if state_f:
            rows = [r for r in rows if r['state'] == state_f]

        has_more = len(rows) > limit
        rows = rows[:limit]
        conn.close()
        return jsonify({'success': True, 'rows': rows, 'has_more': has_more})
    except Exception as e:
        print(f'[Tax] rows error: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/tax/export')
@admin_required
def tax_export():
    """
    CSV export of tax records for the filtered scope.

    Includes all columns needed for accountant/filing review:
    Order ID, Date, Buyer, State, Postal Code, Country,
    Taxable Subtotal, Tax Amount, Tax Rate (%), Buyer Card Fee,
    Total Charged, Payment Status, Refund Status,
    Refunded Tax, Net Tax, Stripe Payment Intent
    """
    try:
        conn = _get_conn()
        args = request.args
        where_str, params, state_f = _build_filters(args)

        rows = _fetch_tax_rows(conn, where_str=where_str, params=params,
                               limit=100000, offset=0, tax_only=True)
        if state_f:
            rows = [r for r in rows if r['state'] == state_f]
        conn.close()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'Order ID', 'Order Date', 'Buyer', 'State', 'Postal Code', 'Country',
            'Taxable Subtotal', 'Tax Amount', 'Tax Rate (%)', 'Buyer Card Fee',
            'Total Charged', 'Payment Status', 'Refund Status',
            'Refunded Tax', 'Net Tax', 'Stripe Payment Intent',
        ])
        for r in rows:
            tax_rate_pct = round(float(r.get('tax_rate') or 0) * 100, 4)
            writer.writerow([
                r['order_id'],
                str(r.get('created_at') or '')[:16],
                r.get('buyer_username') or '',
                r.get('state') or '',
                r.get('postal') or '',
                r.get('country') or 'US',
                f"{r.get('taxable_subtotal', 0):.2f}",
                f"{float(r.get('tax_amount') or 0):.2f}",
                f"{tax_rate_pct:.4f}",
                f"{float(r.get('buyer_card_fee') or 0):.2f}",
                f"{float(r.get('total_price') or 0):.2f}",
                r.get('payment_status') or '',
                r.get('refund_status') or '',
                f"{float(r.get('refunded_tax') or 0):.2f}",
                f"{float(r.get('net_tax') or 0):.2f}",
                r.get('stripe_payment_intent_id') or '',
            ])

        csv_content  = output.getvalue()
        filename     = f"tax_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return Response(
            csv_content,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        print(f'[Tax] export error: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/tax/jurisdiction-summary')
@admin_required
def tax_jurisdiction_summary():
    """
    Aggregate tax by jurisdiction (state, then country for non-US).

    Returns a list sorted by tax_collected descending.
    Only paid orders are included; refunded amounts reduced for full refunds.
    """
    try:
        conn = _get_conn()
        args = request.args
        where_str, params, _ = _build_filters(args)

        paid_rows = _fetch_tax_rows(conn, where_str=where_str, params=params,
                                    limit=100000, offset=0,
                                    paid_only=True, tax_only=False)
        conn.close()

        jurisdictions = {}
        for r in paid_rows:
            state = r.get('state') or ''
            key   = state if state else '(unknown)'
            if key not in jurisdictions:
                jurisdictions[key] = {
                    'state':             state,
                    'country':           'US' if state else '',
                    'order_count':       0,
                    'taxable_subtotal':  0.0,
                    'tax_collected':     0.0,
                    'tax_refunded':      0.0,
                    'net_tax_liability': 0.0,
                }
            j = jurisdictions[key]
            j['order_count']      += 1
            j['taxable_subtotal'] += float(r.get('taxable_subtotal') or 0)
            j['tax_collected']    += float(r.get('tax_amount') or 0)
            j['tax_refunded']     += float(r.get('refunded_tax') or 0)

        summary = []
        for j in jurisdictions.values():
            j['taxable_subtotal']  = round(j['taxable_subtotal'], 2)
            j['tax_collected']     = round(j['tax_collected'], 2)
            j['tax_refunded']      = round(j['tax_refunded'], 2)
            j['net_tax_liability'] = round(j['tax_collected'] - j['tax_refunded'], 2)
            summary.append(j)

        summary.sort(key=lambda x: x['tax_collected'], reverse=True)
        return jsonify({'success': True, 'jurisdictions': summary})
    except Exception as e:
        print(f'[Tax] jurisdiction-summary error: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500
