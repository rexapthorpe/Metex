/**
 * Admin Sales Tax Tab
 * Handles summary stats, paginated order-level records, jurisdiction summary, and CSV export.
 */

let taxPage    = 0;
const TAX_PAGE = 50;
let taxHasMore = false;

// ── Helpers ───────────────────────────────────────────────────────────────────

function _taxParams() {
  const p = new URLSearchParams();
  _taxAddParam(p, 'start_date',      'taxStartDate');
  _taxAddParam(p, 'end_date',        'taxEndDate');
  _taxAddParam(p, 'state',           'taxState');
  _taxAddParam(p, 'payment_status',  'taxPaymentStatus');
  _taxAddParam(p, 'refund_status',   'taxRefundStatus');
  return p;
}

function _taxAddParam(params, key, elId) {
  const el = document.getElementById(elId);
  if (el && el.value.trim()) params.set(key, el.value.trim().toUpperCase
    ? (key === 'state' ? el.value.trim().toUpperCase() : el.value.trim())
    : el.value.trim());
}

function _fmtMoney(v) {
  return '$' + parseFloat(v || 0).toFixed(2);
}

function _taxSetEl(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

// ── Stats ─────────────────────────────────────────────────────────────────────

function loadTaxStats() {
  const params = _taxParams();
  fetch('/admin/api/tax/stats?' + params.toString())
    .then(r => r.json())
    .then(data => {
      if (!data.success) return;
      const s = data.stats;
      _taxSetEl('tax-stat-collected', _fmtMoney(s.total_tax_collected));
      _taxSetEl('tax-stat-refunded',  _fmtMoney(s.total_tax_refunded));
      _taxSetEl('tax-stat-net',       _fmtMoney(s.net_tax_liability));
      _taxSetEl('tax-stat-month',     _fmtMoney(s.this_month_collected));
      _taxSetEl('tax-stat-orders',    (s.taxable_orders || 0).toLocaleString() + ' taxable orders total');
    })
    .catch(e => console.error('[Tax] stats error:', e));
}

// ── Order-level rows ──────────────────────────────────────────────────────────

function loadTaxRows() {
  const tbody = document.getElementById('taxTableBody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="14" style="text-align:center;color:#6b7280;padding:40px;">' +
    '<i class="fa-solid fa-spinner fa-spin"></i> Loading…</td></tr>';

  const params = _taxParams();
  params.set('limit',  TAX_PAGE);
  params.set('offset', taxPage * TAX_PAGE);

  fetch('/admin/api/tax/rows?' + params.toString())
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        renderTaxRows(data.rows || []);
        taxHasMore = !!data.has_more;
        updateTaxPagination();
      } else {
        tbody.innerHTML = '<tr><td colspan="14" style="text-align:center;color:#ef4444;padding:40px;">' +
          'Error loading tax records</td></tr>';
      }
    })
    .catch(() => {
      if (tbody) tbody.innerHTML = '<tr><td colspan="14" style="text-align:center;color:#ef4444;padding:40px;">' +
        'Failed to load rows</td></tr>';
    });
}

function renderTaxRows(rows) {
  const tbody = document.getElementById('taxTableBody');
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="14" style="text-align:center;color:#6b7280;padding:40px;">' +
      'No tax records match current filters</td></tr>';
    return;
  }

  const trunc = (s, n) => s && s.length > n ? s.slice(0, n) + '…' : (s || '—');

  let html = '';
  rows.forEach(r => {
    const taxRate     = parseFloat(r.tax_rate || 0);
    const taxRatePct  = (taxRate * 100).toFixed(2) + '%';
    const refundBadge = _taxRefundBadge(r.refund_status);
    const piShort     = trunc(r.stripe_payment_intent_id, 18);

    html += `<tr>
      <td><a href="/admin/ledger/order/${r.order_id}" class="order-link" style="font-weight:600;">#${r.order_id}</a></td>
      <td style="font-size:11px;color:#6b7280;">${String(r.created_at || '').slice(0, 16)}</td>
      <td style="max-width:90px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
        ${r.buyer_username ? '@' + escapeHtml(r.buyer_username) : '—'}
      </td>
      <td style="font-weight:600;">${escapeHtml(r.state || '—')}</td>
      <td style="font-size:11px;color:#6b7280;">${escapeHtml(r.postal || '—')}</td>
      <td style="font-family:monospace;">${_fmtMoney(r.taxable_subtotal)}</td>
      <td style="font-family:monospace;font-weight:600;color:#0369a1;">${_fmtMoney(r.tax_amount)}</td>
      <td style="font-size:11px;color:#6b7280;">${taxRate > 0 ? taxRatePct : '—'}</td>
      <td>
        ${r.payment_status === 'paid'
          ? '<span style="color:#10b981;font-size:11px;font-weight:600;">paid</span>'
          : '<span style="color:#9ca3af;font-size:11px;">' + escapeHtml(r.payment_status || '—') + '</span>'}
      </td>
      <td>${refundBadge}</td>
      <td style="font-family:monospace;${r.refunded_tax > 0 ? 'color:#dc2626;' : 'color:#d1d5db;'}">
        ${r.refunded_tax > 0 ? _fmtMoney(r.refunded_tax) : '—'}
      </td>
      <td style="font-family:monospace;font-weight:600;">${_fmtMoney(r.net_tax)}</td>
      <td style="font-size:10px;font-family:monospace;color:#6b7280;" title="${escapeHtml(r.stripe_payment_intent_id || '')}">
        ${r.stripe_payment_intent_id
          ? `<span style="background:#f3f4f6;padding:1px 4px;border-radius:3px;">${escapeHtml(piShort)}</span>`
          : '<span style="color:#d1d5db;">—</span>'}
      </td>
      <td>
        <a href="/admin/ledger/order/${r.order_id}" class="action-icon" title="View order ledger">
          <i class="fa-solid fa-book"></i>
        </a>
      </td>
    </tr>`;
  });
  tbody.innerHTML = html;
}

function _taxRefundBadge(status) {
  const m = {
    'not_refunded':       '<span style="color:#10b981;font-size:11px;">Not refunded</span>',
    'refunded':           '<span style="color:#dc2626;font-size:11px;font-weight:600;">Refunded</span>',
    'partially_refunded': '<span style="color:#d97706;font-size:11px;">Partial</span>',
  };
  return m[status] || `<span style="color:#9ca3af;font-size:11px;">${escapeHtml(status || '—')}</span>`;
}

// ── Jurisdiction Summary ──────────────────────────────────────────────────────

function loadTaxJurisdictions() {
  const tbody = document.getElementById('taxJurisdictionBody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#6b7280;padding:40px;">' +
    '<i class="fa-solid fa-spinner fa-spin"></i> Loading…</td></tr>';

  const params = _taxParams();
  fetch('/admin/api/tax/jurisdiction-summary?' + params.toString())
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        renderTaxJurisdictions(data.jurisdictions || []);
      } else {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#ef4444;padding:40px;">' +
          'Error loading jurisdiction data</td></tr>';
      }
    })
    .catch(() => {
      if (tbody) tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#ef4444;padding:40px;">' +
        'Failed to load jurisdictions</td></tr>';
    });
}

function renderTaxJurisdictions(rows) {
  const tbody = document.getElementById('taxJurisdictionBody');
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#6b7280;padding:40px;">' +
      'No jurisdiction data for the selected filters</td></tr>';
    return;
  }

  let html = '';
  rows.forEach(j => {
    html += `<tr>
      <td style="font-weight:600;">${j.state ? escapeHtml(j.state) : '<em style="color:#9ca3af;">(unknown)</em>'}</td>
      <td style="color:#6b7280;">${j.country ? escapeHtml(j.country) : '—'}</td>
      <td style="color:#6b7280;">${j.order_count.toLocaleString()}</td>
      <td style="font-family:monospace;">${_fmtMoney(j.taxable_subtotal)}</td>
      <td style="font-family:monospace;font-weight:600;color:#0369a1;">${_fmtMoney(j.tax_collected)}</td>
      <td style="font-family:monospace;color:#dc2626;">${j.tax_refunded > 0 ? _fmtMoney(j.tax_refunded) : '—'}</td>
      <td style="font-family:monospace;font-weight:600;">${_fmtMoney(j.net_tax_liability)}</td>
    </tr>`;
  });
  tbody.innerHTML = html;
}

// ── Filters ───────────────────────────────────────────────────────────────────

function applyTaxFilters() {
  taxPage = 0;
  loadTaxStats();
  loadTaxRows();
  loadTaxJurisdictions();
}

function clearTaxFilters() {
  ['taxStartDate', 'taxEndDate', 'taxState',
   'taxPaymentStatus', 'taxRefundStatus'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  taxPage = 0;
  loadTaxStats();
  loadTaxRows();
  loadTaxJurisdictions();
}

// ── Pagination ────────────────────────────────────────────────────────────────

function updateTaxPagination() {
  _taxSetEl('taxPageInfo', `Page ${taxPage + 1}`);
  const prev = document.getElementById('taxPrevBtn');
  const next = document.getElementById('taxNextBtn');
  if (prev) prev.disabled = taxPage === 0;
  if (next) next.disabled = !taxHasMore;
}

function taxPrevPage() {
  if (taxPage > 0) { taxPage--; loadTaxRows(); }
}

function taxNextPage() {
  taxPage++;
  loadTaxRows();
}

// ── CSV Export ────────────────────────────────────────────────────────────────

function exportTaxCSV() {
  const params = _taxParams();
  // Trigger download via link click (keeps admin session cookies)
  const url = '/admin/api/tax/export?' + params.toString();
  const a   = document.createElement('a');
  a.href    = url;
  a.click();
}

// ── Bootstrap (called from dashboard.js on tab switch) ────────────────────────

window.loadTaxStats          = loadTaxStats;
window.loadTaxRows           = loadTaxRows;
window.loadTaxJurisdictions  = loadTaxJurisdictions;
window.applyTaxFilters       = applyTaxFilters;
window.clearTaxFilters       = clearTaxFilters;
window.taxPrevPage           = taxPrevPage;
window.taxNextPage           = taxNextPage;
window.exportTaxCSV          = exportTaxCSV;
