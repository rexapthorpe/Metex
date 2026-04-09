/**
 * Admin Refunds Tab (Phase 5)
 * ============================
 * Handles the refunds list and detail modal.
 * Read-only: refunds are created only by the dispute resolution flow.
 */

// ── Column info icon — matches the existing col-help-btn / showColInfo(key) pattern ──
function _refundColIcon(key) {
  return '<button class="col-help-btn" type="button" title="What does this mean?" ' +
    'onclick="if(typeof showColInfo===\'function\')showColInfo(\'' + key + '\')">' +
    '<i class="fa-regular fa-circle-question"></i></button>';
}

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
          <th>Refund ID ${_refundColIcon('refund_id')}</th>
          <th>Dispute ${_refundColIcon('refund_dispute')}</th>
          <th>Order ${_refundColIcon('refund_order')}</th>
          <th>Buyer ${_refundColIcon('refund_buyer')}</th>
          <th>Seller ${_refundColIcon('refund_seller')}</th>
          <th>Amount ${_refundColIcon('refund_amount')}</th>
          <th>Provider Refund ID ${_refundColIcon('refund_provider_id')}</th>
          <th>Issued By ${_refundColIcon('refund_issued_by')}</th>
          <th>Issued At ${_refundColIcon('refund_issued_at')}</th>
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
  // ── Status banner ──────────────────────────────────────────────────────────
  const rs = r.refund_status || (r.amount ? 'refunded' : 'not_refunded');
  const statusLabel = rs === 'refunded' ? 'Fully Refunded'
                    : rs === 'partially_refunded' ? 'Partially Refunded'
                    : 'Refunded';
  const refundedAt = r.refunded_at ? r.refunded_at.slice(0, 16).replace('T', ' ') : _fmtDateTime(r.issued_at);
  const statusBanner = `
    <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:10px;
                padding:12px 16px;display:flex;align-items:center;gap:10px;margin-bottom:16px;">
      <i class="fa-solid fa-rotate-left" style="color:#dc2626;"></i>
      <div>
        <strong style="color:#dc2626;">${statusLabel}</strong>
        <span style="font-size:12px;color:#9ca3af;margin-left:8px;">${refundedAt}</span>
      </div>
    </div>`;

  // ── Method & Recovery ──────────────────────────────────────────────────────
  const stripeRefundId = r.stripe_refund_id || r.provider_refund_id || null;
  const buyerRow = `
    <div style="display:flex;justify-content:space-between;align-items:flex-start;padding:10px 0;border-bottom:1px solid #f3f4f6;">
      <div>
        <div style="font-size:13px;font-weight:600;color:#374151;">A. Buyer Refund</div>
        ${stripeRefundId ? `<div style="font-size:12px;color:#6b7280;margin-top:2px;">Stripe: <code>${escapeHtml(stripeRefundId)}</code></div>` : ''}
        ${r.refund_reason || r.note ? `<div style="font-size:12px;color:#6b7280;margin-top:1px;">Reason: ${escapeHtml(r.refund_reason || r.note)}</div>` : ''}
      </div>
      <span style="background:#dcfce7;color:#16a34a;border-radius:20px;padding:3px 10px;font-size:12px;font-weight:600;white-space:nowrap;">
        <i class="fa-solid fa-circle-check"></i> Succeeded
      </span>
    </div>`;

  // Per-seller recovery rows
  const payouts = r.payouts || [];
  const recoveryRows = payouts.map(p => {
    const recStatus = p.payout_recovery_status || 'not_needed';
    let badge = '';
    if (recStatus === 'recovered') {
      badge = `<span style="background:#dcfce7;color:#16a34a;border-radius:20px;padding:3px 10px;font-size:12px;font-weight:600;white-space:nowrap;"><i class="fa-solid fa-circle-check"></i> Recovered</span>`;
    } else if (recStatus === 'pending') {
      badge = `<span style="background:#fef3c7;color:#d97706;border-radius:20px;padding:3px 10px;font-size:12px;font-weight:600;white-space:nowrap;"><i class="fa-solid fa-clock"></i> Pending</span>`;
    } else if (recStatus === 'manual_review') {
      badge = `<span style="background:#fef2f2;color:#dc2626;border-radius:20px;padding:3px 10px;font-size:12px;font-weight:600;white-space:nowrap;"><i class="fa-solid fa-triangle-exclamation"></i> Manual Review</span>`;
    } else {
      badge = `<span style="background:#f3f4f6;color:#6b7280;border-radius:20px;padding:3px 10px;font-size:12px;font-weight:600;white-space:nowrap;">— Not Needed</span>`;
    }
    return `
      <div style="display:flex;justify-content:space-between;align-items:flex-start;padding:10px 0;border-bottom:1px solid #f3f4f6;">
        <div>
          <div style="font-size:13px;font-weight:600;color:#374151;">B. Seller Recovery</div>
          <div style="font-size:12px;color:#6b7280;margin-top:2px;">
            @${escapeHtml(p.seller_username || String(p.seller_id))}:
            <span style="color:${recStatus === 'recovered' ? '#16a34a' : '#6b7280'}">${recStatus.replace(/_/g,' ')}</span>
            ${p.provider_reversal_id ? `<code style="margin-left:4px;">${escapeHtml(p.provider_reversal_id)}</code>` : ''}
          </div>
          ${p.recovery_failure_reason ? `<div style="font-size:12px;color:#dc2626;margin-top:1px;">${escapeHtml(p.recovery_failure_reason)}</div>` : ''}
        </div>
        ${badge}
      </div>`;
  }).join('');

  const platformCovered = parseFloat(r.platform_covered_amount || 0);
  const platformRow = `
    <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 0;">
      <div style="font-size:13px;font-weight:600;color:#374151;">C. Platform Coverage</div>
      ${platformCovered > 0
        ? `<span style="background:#ede9fe;color:#7c3aed;border-radius:20px;padding:3px 10px;font-size:12px;font-weight:600;">
             <i class="fa-solid fa-shield-halved"></i> ${_fmtAmount(platformCovered)}
           </span>`
        : `<span style="background:#f3f4f6;color:#6b7280;border-radius:20px;padding:3px 10px;font-size:12px;font-weight:600;">— Not Used</span>`
      }
    </div>`;

  const methodSection = `
    <div style="background:#f9fafb;border-radius:10px;padding:14px 16px;margin-bottom:16px;">
      <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#6b7280;margin-bottom:8px;">Refund Method &amp; Recovery Status</div>
      ${buyerRow}
      ${recoveryRows}
      ${platformRow}
    </div>`;

  // ── Refund Breakdown ───────────────────────────────────────────────────────
  const sub    = parseFloat(r.refund_subtotal || 0);
  const tax    = parseFloat(r.refund_tax_amount || 0);
  const fee    = parseFloat(r.refund_processing_fee || 0);
  const total  = parseFloat(r.amount || 0);
  const recovered = payouts.reduce((sum, p) =>
    p.payout_recovery_status === 'recovered' ? sum + parseFloat(p.seller_net_amount || 0) : sum, 0);

  function _bkRow(label, val, opts = {}) {
    const color = opts.color || '#1a1a2e';
    const bold  = opts.bold ? 'font-weight:700;' : '';
    return `<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f3f4f6;">
      <span style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:#6b7280;">${label}</span>
      <span style="font-family:monospace;font-size:13px;${bold}color:${color};">${val}</span>
    </div>`;
  }

  const breakdownSection = `
    <div style="margin-bottom:16px;">
      <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#6b7280;margin-bottom:8px;">Refund Breakdown</div>
      ${_bkRow('Subtotal Refunded', _fmtAmount(sub))}
      ${tax > 0 ? _bkRow('Tax Refunded', _fmtAmount(tax)) : ''}
      ${fee > 0 ? _bkRow('Processing Fee Refunded', _fmtAmount(fee)) : ''}
      ${_bkRow('Total Refunded', _fmtAmount(total), {bold: true})}
      ${recovered > 0 ? _bkRow('Recovered from Seller', _fmtAmount(recovered), {color: '#16a34a'}) : ''}
    </div>`;

  // ── Meta rows (IDs, parties, admin) ───────────────────────────────────────
  const metaRows = [
    ['Refund ID',        `#${r.id}`],
    ['Order ID',         r.order_id ? `#${r.order_id}` : '—'],
    r.dispute_id ? ['Dispute ID', `#${r.dispute_id}`] : null,
    ['Buyer',            r.buyer_username  || '—'],
    ['Seller',           r.seller_username || '—'],
    ['Issued By',        r.issued_by_admin_username || String(r.issued_by_admin_id || '—')],
    ['Issued At',        _fmtDateTime(r.issued_at)],
    r.stripe_payment_intent_id ? ['Stripe PI', `<code style="font-size:12px;">${escapeHtml(r.stripe_payment_intent_id)}</code>`] : null,
  ].filter(Boolean);

  const metaSection = `
    <div class="user-detail-section">
      <h4>Reference</h4>
      ${metaRows.map(([label, val]) => `
        <div class="user-info-row">
          <span class="user-info-label">${label}</span>
          <span class="user-info-value">${val}</span>
        </div>`).join('')}
    </div>`;

  // ── Dispute context ────────────────────────────────────────────────────────
  const disputeSection = r.dispute_id ? `
    <div class="user-detail-section" style="margin-top:16px;">
      <h4>Linked Dispute</h4>
      <div class="user-info-row">
        <span class="user-info-label">Type</span>
        <span class="user-info-value">${escapeHtml((r.dispute_type || '').replace(/_/g,' '))}</span>
      </div>
      <div class="user-info-row">
        <span class="user-info-label">Status</span>
        <span class="user-info-value">${escapeHtml(r.dispute_status || '—')}</span>
      </div>
      ${r.dispute_description ? `
      <div class="user-info-row" style="flex-direction:column;gap:4px;">
        <span class="user-info-label">Description</span>
        <span class="user-info-value" style="font-size:13px;white-space:pre-wrap;">${escapeHtml(r.dispute_description)}</span>
      </div>` : ''}
    </div>` : '';

  return statusBanner + methodSection + breakdownSection + metaSection + disputeSection;
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
