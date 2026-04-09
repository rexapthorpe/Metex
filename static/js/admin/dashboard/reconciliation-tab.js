/**
 * Admin Financial Reconciliation Tab
 * Handles list view, filtering, pagination, and drill-down modal.
 */

let reconPage = 0;
const RECON_PAGE_SIZE = 100;
let reconLastCount = 0;

// ── Stats ────────────────────────────────────────────────────────────────────

function loadReconStats() {
  fetch('/admin/api/reconciliation/stats')
    .then(r => r.json())
    .then(data => {
      if (!data.success) return;
      const s = data.stats;
      const fmt = v => '$' + (v || 0).toLocaleString(undefined, {
        minimumFractionDigits: 2, maximumFractionDigits: 2
      });
      _setEl('recon-stat-matched',       (s.matched     || 0).toLocaleString());
      _setEl('recon-stat-problems',      (s.problems    || 0).toLocaleString());
      _setEl('recon-stat-awaiting',      (s.awaiting    || 0).toLocaleString());
      _setEl('recon-stat-volume',        fmt(s.total_volume));
      _setEl('recon-stat-matched-sub',
        `of ${(s.total_rows || 0).toLocaleString()} total payout rows`);
      _setEl('recon-stat-problems-sub',
        `${s.problems || 0} row${s.problems !== 1 ? 's' : ''} need attention`);
    })
    .catch(e => console.error('[Recon] stats error:', e));
}

// ── List ─────────────────────────────────────────────────────────────────────

function loadReconRows() {
  const tbody = document.getElementById('reconTableBody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="15" style="text-align:center;color:#6b7280;padding:40px;">' +
    '<i class="fa-solid fa-spinner fa-spin"></i> Loading…</td></tr>';

  fetch('/admin/api/reconciliation/rows?' + _buildReconParams())
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        renderReconRows(data.rows);
        reconLastCount = data.count;
        updateReconPagination();
      } else {
        tbody.innerHTML = '<tr><td colspan="15" style="text-align:center;color:#ef4444;padding:40px;">' +
          'Error loading reconciliation data</td></tr>';
      }
    })
    .catch(e => {
      console.error('[Recon] rows error:', e);
      if (tbody) tbody.innerHTML = '<tr><td colspan="15" style="text-align:center;color:#ef4444;padding:40px;">' +
        'Failed to load rows</td></tr>';
    });
}

function _buildReconParams() {
  const p = new URLSearchParams();
  p.set('limit',  RECON_PAGE_SIZE);
  p.set('offset', reconPage * RECON_PAGE_SIZE);
  _addParam(p, 'order_id',       'reconOrderId');
  _addParam(p, 'stripe_ref',     'reconStripeRef');
  _addParam(p, 'buyer',          'reconBuyer');
  _addParam(p, 'seller',         'reconSeller');
  _addParam(p, 'payment_status', 'reconPaymentStatus');
  _addParam(p, 'payout_status',  'reconPayoutStatus');
  _addParam(p, 'payment_method', 'reconPaymentMethod');
  _addParam(p, 'recon_status',   'reconReconStatus');
  _addParam(p, 'start_date',     'reconStartDate');
  _addParam(p, 'end_date',       'reconEndDate');
  return p.toString();
}

function _addParam(params, key, elId) {
  const el = document.getElementById(elId);
  if (el && el.value.trim()) params.set(key, el.value.trim());
}

function _setEl(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

// ── Render ───────────────────────────────────────────────────────────────────

const RECON_STATUS_META = {
  MATCHED:           { label: 'Matched',               color: '#10b981', icon: 'fa-circle-check' },
  MATCHED_SPREAD:    { label: 'Matched (Spread)',       color: '#7c3aed', icon: 'fa-circle-check',
                       title: 'Buyer bid above seller ask — spread retained as platform revenue' },
  AWAITING_TRANSFER: { label: 'Awaiting Transfer',      color: '#3b82f6', icon: 'fa-hourglass-half' },
  MISSING_TRANSFER:  { label: 'Missing Transfer',       color: '#dc2626', icon: 'fa-triangle-exclamation' },
  MISSING_STRIPE_REF:{ label: 'Missing Stripe Ref',     color: '#dc2626', icon: 'fa-triangle-exclamation' },
  AMOUNT_MISMATCH:   { label: 'Amount Mismatch',        color: '#dc2626', icon: 'fa-triangle-exclamation' },
  MISSING_CARD_FEE:  { label: 'Missing Card Fee',       color: '#d97706', icon: 'fa-triangle-exclamation' },
  PENDING_PAYOUT:    { label: 'Pending Payout',         color: '#6b7280', icon: 'fa-clock' },
  UNPAID:            { label: 'Unpaid',                 color: '#9ca3af', icon: 'fa-minus' },
};

function renderReconRows(rows) {
  const tbody = document.getElementById('reconTableBody');
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="16" style="text-align:center;color:#6b7280;padding:40px;">' +
      'No rows match current filters</td></tr>';
    return;
  }

  const fmt = v => '$' + parseFloat(v || 0).toFixed(2);
  const trunc = (s, n) => s && s.length > n ? s.slice(0, n) + '…' : (s || '—');

  let html = '';
  rows.forEach(r => {
    const meta    = RECON_STATUS_META[r.recon_status] || { label: r.recon_status, color: '#9ca3af', icon: 'fa-minus' };
    const rowBg   = r.is_problem ? 'background:#fff5f5;' : '';
    const pmtIcon = _fmtMethod(r.payment_method_type || r.payment_method);
    const piShort = trunc(r.stripe_payment_intent_id, 20);
    const txShort = trunc(r.provider_transfer_id, 20);
    const spread  = parseFloat(r.spread_capture_amount || 0);

    html += `<tr style="${rowBg}">
      <td><a href="/admin/ledger/order/${r.order_id}" class="order-link" style="font-weight:600;">#${r.order_id}</a></td>
      <td style="max-width:90px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
        ${r.buyer_username ? '@' + escapeHtml(r.buyer_username) : '—'}
      </td>
      <td style="max-width:90px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
        ${r.seller_username ? '@' + escapeHtml(r.seller_username) : '—'}
      </td>
      <td>${pmtIcon}</td>
      <td style="font-family:monospace;" title="Seller-side merchandise gross">${fmt(r.gross_amount)}</td>
      <td style="font-family:monospace;${spread > 0 ? 'color:#7c3aed;font-weight:600;' : 'color:#d1d5db;'}"
          title="${spread > 0 ? 'Buyer bid above seller ask — platform retains this spread' : 'No spread'}">
        ${spread > 0 ? fmt(spread) : '—'}
      </td>
      <td style="font-family:monospace;${r.tax_amount > 0 ? 'color:#0369a1;' : 'color:#d1d5db;'}">
        ${r.tax_amount > 0 ? fmt(r.tax_amount) : '—'}
      </td>
      <td style="font-family:monospace;${r.buyer_card_fee > 0 ? 'color:#6b7280;' : 'color:#d1d5db;'}">
        ${r.buyer_card_fee > 0 ? fmt(r.buyer_card_fee) : '—'}
      </td>
      <td style="font-family:monospace;font-weight:600;">${fmt(r.total_charged)}</td>
      <td style="font-family:monospace;color:#dc2626;">${fmt(r.platform_fee_amount)}</td>
      <td style="font-family:monospace;color:#059669;">${fmt(r.seller_net_amount)}</td>
      <td style="font-size:10px;color:#6b7280;font-family:monospace;" title="${escapeHtml(r.stripe_payment_intent_id || '')}">
        ${r.stripe_payment_intent_id
          ? `<span style="background:#f3f4f6;padding:1px 4px;border-radius:3px;">${escapeHtml(piShort)}</span>`
          : '<span style="color:#dc2626;font-size:11px;">missing</span>'}
      </td>
      <td style="font-size:10px;color:#6b7280;font-family:monospace;" title="${escapeHtml(r.provider_transfer_id || '')}">
        ${r.provider_transfer_id
          ? `<span style="background:#f0fdf4;padding:1px 4px;border-radius:3px;">${escapeHtml(txShort)}</span>`
          : '<span style="color:#9ca3af;">—</span>'}
      </td>
      <td>${_fmtPayoutBadge(r.payout_status)}</td>
      <td>
        <span style="font-size:11px;font-weight:600;color:${meta.color};">
          <i class="fa-solid ${meta.icon}" style="margin-right:3px;"></i>${meta.label}
        </span>
      </td>
      <td class="actions-cell">
        <button class="action-icon" onclick="openReconDetail(${r.order_id})"
                title="Full money-flow detail">
          <i class="fa-solid fa-scale-balanced"></i>
        </button>
        <a href="/admin/ledger/order/${r.order_id}" class="action-icon" title="Ledger detail">
          <i class="fa-solid fa-book"></i>
        </a>
      </td>
    </tr>`;
  });
  tbody.innerHTML = html;
}

function _fmtMethod(pmt) {
  if (!pmt) return '<span style="color:#d1d5db;">—</span>';
  const p = pmt.toLowerCase();
  if (p.includes('ach') || p.includes('bank') || p.includes('us_bank'))
    return '<span style="color:#d97706;font-size:12px;"><i class="fa-solid fa-building-columns"></i> ACH</span>';
  if (p === 'card')
    return '<span style="color:#6b7280;font-size:12px;"><i class="fa-solid fa-credit-card"></i> Card</span>';
  return `<span style="font-size:12px;color:#6b7280;">${escapeHtml(pmt)}</span>`;
}

function _fmtPayoutBadge(ps) {
  const m = {
    PAID_OUT:           '<span style="color:#10b981;font-weight:600;font-size:11px;">✓ Paid Out</span>',
    PAYOUT_READY:       '<span style="color:#059669;font-size:11px;"><i class="fa-solid fa-circle-check"></i> Ready</span>',
    PAYOUT_ON_HOLD:     '<span style="color:#d97706;font-size:11px;">On Hold</span>',
    PAYOUT_CANCELLED:   '<span style="color:#9ca3af;font-size:11px;">Cancelled</span>',
    PAYOUT_NOT_READY:   '<span style="color:#6b7280;font-size:11px;">Not Ready</span>',
    PAYOUT_SCHEDULED:   '<span style="color:#3b82f6;font-size:11px;">Scheduled</span>',
    PAYOUT_IN_PROGRESS: '<span style="color:#3b82f6;font-size:11px;">In Progress</span>',
  };
  return m[ps] || `<span style="font-size:11px;color:#9ca3af;">${ps ? ps.replace(/_/g, ' ') : '—'}</span>`;
}

// ── Filter controls ───────────────────────────────────────────────────────────

function applyReconFilters() {
  reconPage = 0;
  loadReconRows();
}

function clearReconFilters() {
  ['reconOrderId','reconStripeRef','reconBuyer','reconSeller',
   'reconPaymentStatus','reconPayoutStatus','reconPaymentMethod',
   'reconReconStatus','reconStartDate','reconEndDate'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  reconPage = 0;
  loadReconRows();
}

function reconShowProblems() {
  const el = document.getElementById('reconReconStatus');
  // Cycle through problem statuses by setting the dropdown if it exists
  if (el) {
    // If already filtered to a problem status, clear; otherwise set AMOUNT_MISMATCH first
    const problems = ['AMOUNT_MISMATCH','MISSING_CARD_FEE','MISSING_STRIPE_REF','MISSING_TRANSFER'];
    const cur = el.value;
    const idx = problems.indexOf(cur);
    el.value = problems[(idx + 1) % problems.length];
    reconPage = 0;
    loadReconRows();
  }
}

// ── Pagination ────────────────────────────────────────────────────────────────

function updateReconPagination() {
  _setEl('reconPageInfo', `Page ${reconPage + 1}`);
  const prev = document.getElementById('reconPrevBtn');
  const next = document.getElementById('reconNextBtn');
  if (prev) prev.disabled = reconPage === 0;
  if (next) next.disabled = reconLastCount < RECON_PAGE_SIZE;
}

function reconPrevPage() {
  if (reconPage > 0) { reconPage--; loadReconRows(); }
}

function reconNextPage() {
  reconPage++;
  loadReconRows();
}

// ── Detail modal ──────────────────────────────────────────────────────────────

function openReconDetail(orderId) {
  const modal   = document.getElementById('reconDetailModal');
  const content = document.getElementById('reconDetailContent');
  const title   = document.getElementById('reconDetailOrderId');
  if (!modal) return;

  title.textContent = '#' + orderId;
  modal.style.display = 'flex';
  content.innerHTML = '<div style="text-align:center;padding:40px;color:#6b7280;">' +
    '<i class="fa-solid fa-spinner fa-spin"></i> Loading…</div>';

  fetch(`/admin/api/reconciliation/order/${orderId}`)
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        content.innerHTML = renderReconDetail(data);
      } else {
        content.innerHTML = `<p style="color:#ef4444;text-align:center;padding:40px;">
          Error: ${escapeHtml(data.error || 'Unknown error')}</p>`;
      }
    })
    .catch(() => {
      content.innerHTML = '<p style="color:#ef4444;text-align:center;padding:40px;">' +
        'Failed to load detail</p>';
    });
}

function closeReconModal() {
  const m = document.getElementById('reconDetailModal');
  if (m) m.style.display = 'none';
}

// ── Issue explanations ────────────────────────────────────────────────────────

const PROBLEM_STATUSES = new Set([
  'AMOUNT_MISMATCH', 'MISSING_STRIPE_REF', 'MISSING_TRANSFER', 'MISSING_CARD_FEE'
]);

function renderReconIssues(data) {
  const fmt   = v => '$' + parseFloat(v || 0).toFixed(2);
  const mf    = data.money_flow;
  const pmt   = data.payment;
  const rows  = data.payout_rows || [];

  const problemRows = rows.filter(r => PROBLEM_STATUSES.has(r.recon_status));
  if (!problemRows.length) return '';

  // Deduplicate by status so we show each issue type once (with per-seller detail where needed)
  const seen = new Set();
  const issues = [];

  problemRows.forEach(r => {
    const status = r.recon_status;

    if (status === 'AMOUNT_MISMATCH' && !seen.has('AMOUNT_MISMATCH')) {
      seen.add('AMOUNT_MISMATCH');
      const stored    = parseFloat(pmt.total_price_stored || 0);
      const spread    = parseFloat(mf.spread_capture || 0);
      const expected  = parseFloat(mf.subtotal || 0) + spread
                      + parseFloat(mf.tax_amount || 0)
                      + parseFloat(mf.buyer_card_fee || 0);
      const diff      = Math.abs(stored - expected);
      const parts     = [];
      parts.push(`seller gross ${fmt(mf.subtotal)}`);
      if (spread > 0) parts.push(`spread ${fmt(spread)}`);
      if (parseFloat(mf.tax_amount) > 0) parts.push(`tax ${fmt(mf.tax_amount)}`);
      if (parseFloat(mf.buyer_card_fee) > 0) parts.push(`card fee ${fmt(mf.buyer_card_fee)}`);

      issues.push({
        icon:  'fa-not-equal',
        color: '#dc2626',
        bg:    '#fff5f5',
        border:'#fecaca',
        title: 'Amount mismatch',
        body:  `The total charged to the buyer (${fmt(stored)}) doesn't match what the components add up to. `
             + `Expected: ${parts.join(' + ')} = ${fmt(expected)}, but the stored total is ${fmt(stored)} `
             + `— an unexplained difference of ${fmt(diff)}. `
             + `Note: valid bid/ask spread is already accounted for above. `
             + `This unexplained delta usually means a fee, discount, or tax was applied inconsistently at checkout. `
             + `Check the order at the Stripe Dashboard level to confirm what was actually captured.`,
      });
    }

    if (status === 'MISSING_STRIPE_REF' && !seen.has('MISSING_STRIPE_REF')) {
      seen.add('MISSING_STRIPE_REF');
      issues.push({
        icon:  'fa-link-slash',
        color: '#dc2626',
        bg:    '#fff5f5',
        border:'#fecaca',
        title: 'No Stripe PaymentIntent ID on record',
        body:  `Payment is marked as "${pmt.payment_status || 'paid'}" but no Stripe PaymentIntent ID is stored for this order. `
             + `Without it, we can't confirm this payment with Stripe or trace the funds. `
             + `This can happen if the order was manually created, if a webhook was missed, or if the ID was lost during a migration. `
             + `Search the Stripe Dashboard for a charge of ${fmt(pmt.total_price_stored)} `
             + `${pmt.payment_method ? `via ${pmt.payment_method} ` : ''}`
             + `near the order date to locate the matching PaymentIntent.`,
      });
    }

    if (status === 'MISSING_TRANSFER') {
      const key = 'MISSING_TRANSFER:' + (r.seller_username || r.seller_id);
      if (!seen.has(key)) {
        seen.add(key);
        issues.push({
          icon:  'fa-paper-plane-slash',
          color: '#dc2626',
          bg:    '#fff5f5',
          border:'#fecaca',
          title: `Missing transfer — @${escapeHtml(r.seller_username || String(r.seller_id))}`,
          body:  `Seller @${escapeHtml(r.seller_username || String(r.seller_id))} is recorded as Paid Out `
               + `(${fmt(r.seller_net_amount)}) but no Stripe transfer ID was saved. `
               + `We can't confirm this transfer actually reached the seller's account. `
               + `Go to the Stripe Dashboard → Transfers and search for transfers to this seller's connected account `
               + `around the payout date to verify, then record the transfer ID manually if found.`,
        });
      }
    }

    if (status === 'MISSING_CARD_FEE' && !seen.has('MISSING_CARD_FEE')) {
      seen.add('MISSING_CARD_FEE');
      const stored   = parseFloat(pmt.total_price_stored || 0);
      const noFee    = parseFloat(mf.subtotal || 0) + parseFloat(mf.tax_amount || 0);
      issues.push({
        icon:  'fa-credit-card',
        color: '#d97706',
        bg:    '#fffbeb',
        border:'#fcd34d',
        title: 'Card fee not recorded',
        body:  `This was a card payment, but no card processing fee is on record (expected > $0.00). `
             + `The stored total (${fmt(stored)}) matches items + tax (${fmt(noFee)}) with nothing added for the card fee. `
             + `Either the fee was waived, the buyer was on an ACH plan, or the fee calculation was skipped at checkout. `
             + `If a card fee should have been charged, the shortfall is coming out of platform revenue.`,
      });
    }
  });

  if (!issues.length) return '';

  let html = `
    <div style="margin-bottom:20px;">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
        <i class="fa-solid fa-triangle-exclamation" style="color:#dc2626;font-size:14px;"></i>
        <span style="font-size:13px;font-weight:700;color:#dc2626;">
          ${issues.length === 1 ? '1 issue detected' : issues.length + ' issues detected'}
        </span>
      </div>`;

  issues.forEach(issue => {
    html += `
      <div style="background:${issue.bg};border:1px solid ${issue.border};border-radius:8px;
                  padding:14px 16px;margin-bottom:10px;">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
          <i class="fa-solid ${issue.icon}" style="color:${issue.color};font-size:13px;"></i>
          <span style="font-size:13px;font-weight:700;color:${issue.color};">${issue.title}</span>
        </div>
        <p style="margin:0;font-size:13px;color:#374151;line-height:1.6;">${issue.body}</p>
      </div>`;
  });

  html += `</div>`;
  return html;
}

function renderReconDetail(data) {
  const fmt = v => '$' + parseFloat(v || 0).toFixed(2);
  const mf  = data.money_flow;
  const pmt = data.payment;
  const ref = data.refund;
  const rows = data.payout_rows || [];

  // Money-flow chain
  const spread = parseFloat(mf.spread_capture || 0);
  const flowSteps = [
    { label: 'Seller Gross (merchandise)',  value: fmt(mf.subtotal),               color: '#1f2937' },
    { label: '+ Spread Capture (platform)', value: fmt(mf.spread_capture),         color: '#7c3aed',
      skip: spread === 0,
      title: 'Buyer bid above seller ask — this premium is platform revenue, not seller revenue' },
    { label: spread > 0 ? '= Buyer Subtotal' : '= Items Subtotal',
                                            value: fmt(mf.buyer_subtotal),         color: '#1f2937',
      bold: spread > 0, skip: spread === 0 },
    { label: '+ Sales Tax (liability)',     value: fmt(mf.tax_amount),             color: '#0369a1',
      skip: !mf.tax_amount || mf.tax_amount === 0 },
    { label: '+ Buyer Card Fee',            value: fmt(mf.buyer_card_fee),         color: '#6b7280',
      skip: mf.buyer_card_fee === 0 },
    { label: '= Total Charged to Buyer',    value: fmt(mf.total_charged),          color: '#1f2937', bold: true },
    { label: '− Platform Fee (on seller ⊕ spread)', value: fmt(mf.total_platform_revenue),
      color: '#dc2626',
      skip: (mf.total_platform_revenue || 0) === 0 },
    { label: spread > 0 ? '  ↳ Percentage Fee (seller gross)' : '− Platform Fee Retained',
                                            value: fmt(mf.platform_fee),           color: '#dc2626',
      skip: spread === 0 },
    { label: '  ↳ Spread Capture Revenue',  value: fmt(mf.spread_capture),        color: '#7c3aed',
      skip: spread === 0 },
    { label: '= Total to Sellers',          value: fmt(mf.total_seller_net),       color: '#059669', bold: true },
  ];

  let flowHtml = '';
  flowSteps.forEach(s => {
    if (s.skip) return;
    const titleAttr = s.title ? ` title="${escapeHtml(s.title)}"` : '';
    flowHtml += `
      <div style="display:flex;justify-content:space-between;align-items:center;
                  padding:8px 12px;border-bottom:1px solid #f3f4f6;"${titleAttr}>
        <span style="font-size:13px;color:#4b5563;">${s.label}</span>
        <span style="font-family:monospace;font-size:14px;color:${s.color};
                     ${s.bold ? 'font-weight:700;' : ''}">${s.value}</span>
      </div>`;
  });

  // Stripe IDs block
  const stripeRows = [
    ['Payment Intent', pmt.stripe_payment_intent_id],
    ['Stripe Refund',  ref.stripe_refund_id],
  ];
  let stripeHtml = '';
  stripeRows.forEach(([label, val]) => {
    stripeHtml += `
      <div style="display:flex;gap:12px;align-items:baseline;margin-bottom:6px;">
        <span style="font-size:11px;color:#9ca3af;min-width:110px;">${label}</span>
        ${val
          ? `<code style="font-size:11px;background:#f3f4f6;padding:2px 6px;border-radius:4px;">${escapeHtml(val)}</code>`
          : '<span style="color:#d1d5db;font-size:12px;">—</span>'}
      </div>`;
  });

  // Per-seller payout rows
  let payoutHtml = '';
  rows.forEach(r => {
    const meta = RECON_STATUS_META[r.recon_status] || { label: r.recon_status, color: '#9ca3af', icon: 'fa-minus' };
    const rowSpread = parseFloat(r.payout_spread_capture || 0);
    payoutHtml += `
      <tr>
        <td>@${escapeHtml(r.seller_username || String(r.seller_id))}</td>
        <td style="font-family:monospace;" title="Seller-side merchandise gross">${fmt(r.seller_gross_amount)}</td>
        <td style="font-family:monospace;${rowSpread > 0 ? 'color:#7c3aed;' : 'color:#d1d5db;'}"
            title="${rowSpread > 0 ? 'Buyer bid above seller ask — platform keeps this' : 'No spread'}">
          ${rowSpread > 0 ? fmt(rowSpread) : '—'}
        </td>
        <td style="font-family:monospace;color:#dc2626;">${fmt(r.payout_fee_amount)}</td>
        <td style="font-family:monospace;color:#059669;">${fmt(r.seller_net_amount)}</td>
        <td>${_fmtPayoutBadge(r.payout_status)}</td>
        <td style="font-size:10px;font-family:monospace;">
          ${r.provider_transfer_id
            ? `<code style="background:#f0fdf4;padding:1px 4px;border-radius:3px;font-size:10px;">${escapeHtml(r.provider_transfer_id)}</code>`
            : '<span style="color:#9ca3af;">—</span>'}
        </td>
        <td>
          <span style="font-size:11px;font-weight:600;color:${meta.color};">
            <i class="fa-solid ${meta.icon}" style="margin-right:2px;"></i>${meta.label}
          </span>
        </td>
      </tr>`;
  });

  // Refund section (only if refund exists)
  let refundHtml = '';
  if (ref.refund_status && ref.refund_status !== 'not_refunded') {
    refundHtml = `
      <div style="margin-top:20px;padding:14px;background:#fff5f5;border:1px solid #fecaca;border-radius:8px;">
        <div style="font-size:13px;font-weight:600;color:#dc2626;margin-bottom:8px;">
          <i class="fa-solid fa-rotate-left" style="margin-right:6px;"></i>Refund
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px;">
          <div><span style="color:#9ca3af;">Status</span><br><strong>${escapeHtml(ref.refund_status)}</strong></div>
          <div><span style="color:#9ca3af;">Amount</span><br><strong style="color:#dc2626;">${fmt(ref.refund_amount)}</strong></div>
          <div><span style="color:#9ca3af;">Refunded At</span><br>${ref.refunded_at ? escapeHtml(String(ref.refunded_at).slice(0,16)) : '—'}</div>
          <div><span style="color:#9ca3af;">Stripe Refund ID</span><br>
            ${ref.stripe_refund_id
              ? `<code style="font-size:10px;">${escapeHtml(ref.stripe_refund_id)}</code>`
              : '<span style="color:#d1d5db;">—</span>'}
          </div>
        </div>
        ${ref.refund_reason ? `<div style="margin-top:8px;font-size:12px;color:#6b7280;">Reason: ${escapeHtml(ref.refund_reason)}</div>` : ''}
      </div>`;
  }

  const issuesHtml = renderReconIssues(data);

  return `
    ${issuesHtml}
    <!-- Money flow chain -->
    <div style="margin-bottom:24px;">
      <h4 style="font-size:13px;font-weight:600;margin-bottom:10px;color:#374151;">
        <i class="fa-solid fa-arrow-right-arrow-left" style="margin-right:6px;color:#3b82f6;"></i>
        Money Flow Chain
      </h4>
      <div style="border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;">${flowHtml}</div>
    </div>

    <!-- Payment summary -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px;">
      <div style="padding:14px;background:#f9fafb;border-radius:8px;">
        <div style="font-size:11px;color:#9ca3af;text-transform:uppercase;margin-bottom:8px;">Payment</div>
        <div style="font-size:12px;margin-bottom:4px;">
          <span style="color:#6b7280;">Status:</span>
          <strong style="margin-left:6px;${pmt.payment_status === 'paid' ? 'color:#10b981;' : 'color:#dc2626;'}">
            ${escapeHtml(pmt.payment_status || '—')}
          </strong>
        </div>
        <div style="font-size:12px;margin-bottom:4px;">
          <span style="color:#6b7280;">Method:</span>
          <strong style="margin-left:6px;">${escapeHtml(pmt.payment_method || '—')}</strong>
        </div>
        <div style="font-size:12px;">
          <span style="color:#6b7280;">stored total_price:</span>
          <strong style="font-family:monospace;margin-left:6px;">${fmt(pmt.total_price_stored)}</strong>
        </div>
      </div>
      <div style="padding:14px;background:#f9fafb;border-radius:8px;">
        <div style="font-size:11px;color:#9ca3af;text-transform:uppercase;margin-bottom:8px;">Stripe References</div>
        ${stripeHtml}
      </div>
    </div>

    <!-- Per-seller payout rows -->
    <div style="margin-bottom:16px;">
      <h4 style="font-size:13px;font-weight:600;margin-bottom:10px;color:#374151;">
        <i class="fa-solid fa-circle-dollar-to-slot" style="margin-right:6px;color:#059669;"></i>
        Seller Payouts (${rows.length})
      </h4>
      <div style="overflow-x:auto;">
        <table class="data-table" style="font-size:12px;">
          <thead>
            <tr>
              <th>Seller</th><th>Seller Gross</th><th>Spread</th>
              <th>Platform Fee</th><th>Seller Net</th><th>Payout Status</th>
              <th>Transfer ID</th><th>Recon Status</th>
            </tr>
          </thead>
          <tbody>${payoutHtml}</tbody>
        </table>
      </div>
    </div>

    ${refundHtml}`;
}

// ── Bootstrap ─────────────────────────────────────────────────────────────────

window.loadReconStats    = loadReconStats;
window.loadReconRows     = loadReconRows;
window.applyReconFilters = applyReconFilters;
window.clearReconFilters = clearReconFilters;
window.reconShowProblems = reconShowProblems;
window.reconPrevPage     = reconPrevPage;
window.reconNextPage     = reconNextPage;
window.openReconDetail   = openReconDetail;
window.closeReconModal   = closeReconModal;
