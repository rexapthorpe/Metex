/**
 * Admin Refunds Tab (Phase 5)
 * ============================
 * Handles the refunds list and detail modal.
 * Read-only: refunds are created only by the dispute resolution flow.
 */

// ── State ─────────────────────────────────────────────────────────────────────
let refundsData = [];

// ── Helpers ───────────────────────────────────────────────────────────────────

function _fmtDate(s) {
  if (!s) return '—';
  try {
    return new Date(s).toLocaleDateString('en-US', {
      year: 'numeric', month: 'short', day: 'numeric',
    });
  } catch (_) { return s; }
}

function _fmtDateTime(s) {
  if (!s) return '—';
  try {
    return new Date(s).toLocaleString('en-US', {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch (_) { return s; }
}

function _fmtAmount(n) {
  if (n == null) return '—';
  return '$' + Number(n).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

// ── Load list ─────────────────────────────────────────────────────────────────

function loadRefunds() {
  const dateFrom  = document.getElementById('refundFilterDateFrom').value.trim();
  const dateTo    = document.getElementById('refundFilterDateTo').value.trim();
  const disputeId = document.getElementById('refundFilterDisputeId').value.trim();
  const buyer     = document.getElementById('refundFilterBuyer').value.trim();
  const seller    = document.getElementById('refundFilterSeller').value.trim();

  const params = new URLSearchParams();
  if (dateFrom)  params.set('date_from',  dateFrom);
  if (dateTo)    params.set('date_to',    dateTo);
  if (disputeId) params.set('dispute_id', disputeId);
  if (buyer)     params.set('buyer',      buyer);
  if (seller)    params.set('seller',     seller);

  document.getElementById('adminRefundsList').innerHTML = `
    <div class="dispute-loading">
      <i class="fa-solid fa-spinner fa-spin"></i>
      <span>Loading refunds...</span>
    </div>`;
  document.getElementById('adminRefundsEmpty').style.display = 'none';

  fetch('/admin/api/refunds?' + params.toString())
    .then(r => r.json())
    .then(data => {
      if (!data.success) {
        document.getElementById('adminRefundsList').innerHTML =
          `<p style="color:#ef4444;padding:16px;">${escapeHtml(data.error || 'Failed to load')}</p>`;
        return;
      }
      refundsData = data.refunds || [];
      const summary = data.summary || {};

      // Update shown stats
      document.getElementById('refundStatCount').textContent  = summary.count ?? refundsData.length;
      document.getElementById('refundStatTotal').textContent  = _fmtAmount(summary.total_amount);
      // 30-day stat is loaded separately on tab activation; don't overwrite if already set.

      renderRefundsList(refundsData);
    })
    .catch(err => {
      document.getElementById('adminRefundsList').innerHTML =
        `<p style="color:#ef4444;padding:16px;">Network error: ${escapeHtml(String(err))}</p>`;
    });
}

function loadRefundsLast30() {
  const now   = new Date();
  const from  = new Date(now);
  from.setDate(from.getDate() - 30);

  const fmt = d => d.toISOString().slice(0, 10);
  document.getElementById('refundFilterDateFrom').value = fmt(from);
  document.getElementById('refundFilterDateTo').value   = fmt(now);
  document.getElementById('refundFilterDisputeId').value = '';
  document.getElementById('refundFilterBuyer').value    = '';
  document.getElementById('refundFilterSeller').value   = '';
  loadRefunds();
}

// Load the 30-day total for the stat card (used on tab activation)
function _loadRefund30dStat() {
  const now   = new Date();
  const from  = new Date(now);
  from.setDate(from.getDate() - 30);
  const fmt = d => d.toISOString().slice(0, 10);

  fetch(`/admin/api/refunds?date_from=${fmt(from)}&date_to=${fmt(now)}`)
    .then(r => r.json())
    .then(data => {
      if (data.success && data.summary) {
        document.getElementById('refundStat30d').textContent = _fmtAmount(data.summary.total_amount);
      }
    })
    .catch(() => {});
}

// ── Render list ───────────────────────────────────────────────────────────────

function renderRefundsList(refunds) {
  const listEl  = document.getElementById('adminRefundsList');
  const emptyEl = document.getElementById('adminRefundsEmpty');

  if (!refunds.length) {
    listEl.innerHTML = '';
    emptyEl.style.display = '';
    return;
  }
  emptyEl.style.display = 'none';

  const rows = refunds.map(r => `
    <tr>
      <td>#${r.id}</td>
      <td>
        <a href="#disputes" onclick="switchTab('disputes'); return false;"
           style="color:#3b82f6;text-decoration:none;" title="Go to Disputes tab">
          #${r.dispute_id || '—'}
        </a>
      </td>
      <td>#${r.order_id || '—'}</td>
      <td>${escapeHtml(r.buyer_username || '—')}</td>
      <td>${escapeHtml(r.seller_username || '—')}</td>
      <td style="font-weight:600;color:#dc2626;">${_fmtAmount(r.amount)}</td>
      <td style="font-size:12px;color:#6b7280;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
          title="${escapeHtml(r.provider_refund_id || '')}">
        ${escapeHtml(r.provider_refund_id || '—')}
      </td>
      <td style="font-size:12px;color:#6b7280;">${escapeHtml(r.issued_by_admin_username || String(r.issued_by_admin_id || '—'))}</td>
      <td style="font-size:12px;">${_fmtDateTime(r.issued_at)}</td>
      <td>
        <button class="action-icon" onclick="viewRefundDetail(${r.id})" title="View detail">
          <i class="fa-solid fa-eye"></i>
        </button>
      </td>
    </tr>`).join('');

  listEl.innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>Refund ID</th>
          <th>Dispute</th>
          <th>Order</th>
          <th>Buyer</th>
          <th>Seller</th>
          <th>Amount</th>
          <th>Provider Refund ID</th>
          <th>Issued By</th>
          <th>Issued At</th>
          <th></th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

// ── Detail modal ──────────────────────────────────────────────────────────────

function viewRefundDetail(refundId) {
  const modal = document.getElementById('adminRefundDetailModal');
  const body  = document.getElementById('adminRefundDetailBody');
  const title = document.getElementById('adminRefundDetailTitle');
  title.innerHTML = `<i class="fa-solid fa-rotate-left"></i> Refund #${refundId}`;
  body.innerHTML  = `<div class="modal-loading"><i class="fa-solid fa-spinner fa-spin fa-lg"></i><span>Loading...</span></div>`;
  modal.style.display = 'flex';

  fetch(`/admin/api/refunds/${refundId}`)
    .then(r => r.json())
    .then(data => {
      if (!data.success) {
        body.innerHTML = `<p style="color:#ef4444">${escapeHtml(data.error || 'Error')}</p>`;
        return;
      }
      body.innerHTML = renderRefundDetail(data.refund);
    })
    .catch(err => {
      body.innerHTML = `<p style="color:#ef4444">Network error: ${escapeHtml(String(err))}</p>`;
    });
}

function renderRefundDetail(r) {
  const rows = [
    ['Refund ID',          `#${r.id}`],
    ['Dispute ID',         r.dispute_id ? `#${r.dispute_id}` : '—'],
    ['Order ID',           r.order_id   ? `#${r.order_id}`   : '—'],
    ['Buyer',              r.buyer_username  || '—'],
    ['Seller',             r.seller_username || '—'],
    ['Amount',             `<strong style="color:#dc2626">${_fmtAmount(r.amount)}</strong>`],
    ['Provider Refund ID', r.provider_refund_id ? `<code style="font-size:12px;">${escapeHtml(r.provider_refund_id)}</code>` : '—'],
    ['Stripe PI ID',       r.stripe_payment_intent_id ? `<code style="font-size:12px;">${escapeHtml(r.stripe_payment_intent_id)}</code>` : '—'],
    ['Issued By Admin',    r.issued_by_admin_username || String(r.issued_by_admin_id || '—')],
    ['Issued At',          _fmtDateTime(r.issued_at)],
    ['Note',               r.note ? escapeHtml(r.note) : '<em style="color:#6b7280">No note</em>'],
  ];

  const metaHtml = rows.map(([label, val]) => `
    <div class="user-info-row">
      <span class="user-info-label">${label}</span>
      <span class="user-info-value">${val}</span>
    </div>`).join('');

  // Dispute context (if available)
  const disputeHtml = r.dispute_id ? `
    <div class="user-detail-section" style="margin-top:20px;">
      <h4>Linked Dispute</h4>
      <div class="user-info-row">
        <span class="user-info-label">Dispute Type</span>
        <span class="user-info-value">${escapeHtml((r.dispute_type || '').replace(/_/g,' '))}</span>
      </div>
      <div class="user-info-row">
        <span class="user-info-label">Dispute Status</span>
        <span class="user-info-value">${escapeHtml(r.dispute_status || '—')}</span>
      </div>
      ${r.dispute_description ? `
      <div class="user-info-row" style="flex-direction:column;gap:4px;">
        <span class="user-info-label">Description</span>
        <span class="user-info-value" style="font-size:13px;white-space:pre-wrap;">${escapeHtml(r.dispute_description)}</span>
      </div>` : ''}
    </div>` : '';

  const orderHtml = r.order_id ? `
    <div class="user-detail-section" style="margin-top:20px;">
      <h4>Linked Order</h4>
      <div class="user-info-row">
        <span class="user-info-label">Order Total</span>
        <span class="user-info-value">${_fmtAmount(r.order_total)}</span>
      </div>
      <div class="user-info-row">
        <span class="user-info-label">Order Status</span>
        <span class="user-info-value">${escapeHtml(r.order_status || '—')}</span>
      </div>
    </div>` : '';

  return `
    <div class="user-detail-section">
      <h4>Refund Details</h4>
      ${metaHtml}
    </div>
    ${disputeHtml}
    ${orderHtml}`;
}

function closeRefundDetailModal() {
  document.getElementById('adminRefundDetailModal').style.display = 'none';
}

// ── Overview Metrics (Phase 5) ────────────────────────────────────────────────

let _overviewMetricsLoaded = false;

function loadOverviewMetrics() {
  fetch('/admin/api/overview-metrics')
    .then(r => r.json())
    .then(data => {
      if (!data.success) return;

      const el = id => document.getElementById(id);

      if (el('ovMetricOpenDisputes')) {
        el('ovMetricOpenDisputes').textContent =
          data.open_disputes_count != null ? data.open_disputes_count : '—';
      }
      if (el('ovMetricAvgResolution')) {
        el('ovMetricAvgResolution').textContent =
          data.avg_resolution_hours != null
            ? `${data.avg_resolution_hours}h`
            : 'N/A';
      }
      if (el('ovMetricRefunds30d')) {
        el('ovMetricRefunds30d').textContent =
          data.refunds_30d_total != null
            ? '$' + Number(data.refunds_30d_total).toFixed(2)
            : '—';
      }
      if (el('ovMetricHighRisk')) {
        el('ovMetricHighRisk').textContent =
          data.high_risk_users_count != null ? data.high_risk_users_count : '—';
      }

      _overviewMetricsLoaded = true;
    })
    .catch(() => {});
}

// Load metrics on page ready (overview tab is active by default)
document.addEventListener('DOMContentLoaded', function() {
  loadOverviewMetrics();
});

// ── Tab activation hook ───────────────────────────────────────────────────────

(function() {
  const _origSwitch = window.switchTab;
  window.switchTab = function(tab) {
    if (_origSwitch) _origSwitch(tab);

    if (tab === 'overview' && !_overviewMetricsLoaded) {
      loadOverviewMetrics();
    }
    if (tab === 'refunds' && refundsData.length === 0) {
      loadRefunds();
      _loadRefund30dStat();
    }
  };
})();
