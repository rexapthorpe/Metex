
let ledgerCurrentPage = 0;
const ledgerPageSize = 50;
let ledgerTotalLoaded = 0;

function loadLedgerStats() {
  fetch('/admin/api/ledger/stats')
    .then(response => response.json())
    .then(data => {
      if (!data.success) return;
      const s = data.stats;
      const fmt = (v) => '$' + (v||0).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
      document.getElementById('ledger-stat-total-orders').textContent = (s.total_orders||0).toLocaleString();
      document.getElementById('ledger-stat-gross-volume').textContent = fmt(s.total_gross_volume);
      document.getElementById('ledger-stat-platform-fees').textContent = fmt(s.total_platform_fees);

      // Split payout stats
      const pendEl = document.getElementById('ledger-stat-payout-pending');
      const pendCt = document.getElementById('ledger-stat-payout-pending-count');
      if (pendEl) pendEl.textContent = fmt(s.payout_pending_total);
      if (pendCt) pendCt.textContent = (s.payout_pending_count||0) + ' payouts';

      const readyEl = document.getElementById('ledger-stat-payout-ready');
      const readyCt = document.getElementById('ledger-stat-payout-ready-count');
      if (readyEl) readyEl.textContent = fmt(s.payout_ready_total);
      if (readyCt) readyCt.textContent = (s.payout_ready_count||0) + ' payouts';

      const paidEl = document.getElementById('ledger-stat-paid-out');
      const paidCt = document.getElementById('ledger-stat-paid-out-count');
      if (paidEl) paidEl.textContent = fmt(s.paid_out_total);
      if (paidCt) paidCt.textContent = (s.paid_out_count||0) + ' payouts';

      const taxEl = document.getElementById('ledger-stat-tax-collected');
      if (taxEl) taxEl.textContent = fmt(s.total_tax_collected || 0);

      const spreadEl = document.getElementById('ledger-stat-spread-revenue');
      if (spreadEl) spreadEl.textContent = fmt(s.total_spread_revenue || 0);
    })
    .catch(error => console.error('Error loading ledger stats:', error));
}

function loadLedgerOrders() {
  const tbody = document.getElementById('ledgerTableBody');
  tbody.innerHTML = '<tr><td colspan="13" style="text-align: center; color: #6b7280; padding: 40px;"><i class="fa-solid fa-spinner fa-spin"></i> Loading ledger...</td></tr>';

  const params = new URLSearchParams();
  params.append('limit', ledgerPageSize);
  params.append('offset', ledgerCurrentPage * ledgerPageSize);

  const status        = document.getElementById('ledgerStatusFilter').value;
  const paymentStatus = document.getElementById('ledgerPaymentStatusFilter') ? document.getElementById('ledgerPaymentStatusFilter').value : '';
  const payoutStatus  = document.getElementById('ledgerPayoutStatusFilter')  ? document.getElementById('ledgerPayoutStatusFilter').value  : '';
  const buyerId       = document.getElementById('ledgerBuyerIdFilter').value;
  const startDate     = document.getElementById('ledgerStartDate').value;
  const endDate       = document.getElementById('ledgerEndDate').value;
  const minGross      = document.getElementById('ledgerMinGross').value;
  const maxGross      = document.getElementById('ledgerMaxGross').value;

  if (status)        params.append('status', status);
  if (paymentStatus) params.append('payment_status', paymentStatus);
  if (payoutStatus)  params.append('payout_status', payoutStatus);
  if (buyerId)       params.append('buyer_id', buyerId);
  if (startDate)     params.append('start_date', startDate);
  if (endDate)       params.append('end_date', endDate);
  if (minGross)      params.append('min_gross', minGross);
  if (maxGross)      params.append('max_gross', maxGross);

  fetch('/admin/api/ledger/orders?' + params.toString())
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        renderLedgerOrders(data.orders);
        ledgerTotalLoaded = data.count;
        updateLedgerPagination();
      } else {
        tbody.innerHTML = '<tr><td colspan="13" style="text-align: center; color: #ef4444; padding: 40px;">Error loading ledger</td></tr>';
      }
    })
    .catch(error => {
      console.error('Error loading ledger orders:', error);
      tbody.innerHTML = '<tr><td colspan="13" style="text-align: center; color: #ef4444; padding: 40px;">Error loading ledger</td></tr>';
    });
}

function renderLedgerOrders(orders) {
  const tbody = document.getElementById('ledgerTableBody');

  if (orders.length === 0) {
    tbody.innerHTML = '<tr><td colspan="13" style="text-align: center; color: #6b7280; padding: 40px;">No ledger records found</td></tr>';
    return;
  }

  let html = '';
  orders.forEach(order => {
    const statusClass  = getLedgerStatusClass(order.order_status);
    const stateLabel   = order.order_state_label || formatLedgerStatus(order.order_status);
    const stateCss     = order.order_state_css   || statusClass;
    const blockReason  = order.block_reason      || '';
    const payoutStatus = order.payout_status     || '';
    const payoutBadge  = formatPayoutStateBadge(payoutStatus);
    const pmtMethod    = formatPaymentMethodIcon(order.payment_method_type || order.payment_method);

    html += `
      <tr>
        <td><a href="/admin/ledger/order/${order.order_id}" class="order-link">#${order.order_id}</a></td>
        <td>
          <span class="user-name">@${escapeHtml(order.buyer_username)}</span>
          <span style="font-size: 11px; color: #888; margin-left: 4px;">(${order.buyer_id})</span>
        </td>
        <td>
          <span class="order-state-badge ${stateCss}">${escapeHtml(stateLabel)}</span>
        </td>
        <td style="font-size:12px;color:#6b7280;">${order.item_count} item${order.item_count !== 1 ? 's' : ''}</td>
        <td style="font-size:12px;color:#6b7280;">${order.seller_count}</td>
        <td style="font-family: monospace;">
          ${formatPrice(order.gross_amount)}
          ${(order.spread_capture_amount > 0)
            ? `<div style="font-size:10px;color:#7c3aed;font-family:sans-serif;margin-top:2px;"
                    title="Buyer bid above seller ask — spread retained as platform revenue">
                 +${formatPrice(order.spread_capture_amount)} spread
               </div>`
            : ''}
        </td>
        <td style="font-family: monospace; color: #0369a1;">
          ${order.tax_amount > 0 ? formatPrice(order.tax_amount) : '<span style="color:#d1d5db;">—</span>'}
        </td>
        <td style="font-family: monospace; color: #dc2626;">${formatPrice(order.platform_fee_amount)}</td>
        <td>${pmtMethod}</td>
        <td>${payoutBadge}</td>
        <td style="font-size:11px;max-width:160px;">
          ${blockReason
            ? `<span style="color:#ef4444;" title="${escapeHtml(blockReason)}">
                 <i class="fa-solid fa-lock" style="margin-right:3px;"></i>${escapeHtml(blockReason)}
               </span>`
            : (payoutStatus === 'PAID_OUT'
               ? '<span style="color:#10b981;font-size:11px;">✓ Paid out</span>'
               : '<span style="color:#9ca3af;">—</span>')}
        </td>
        <td style="font-size: 12px; color: #666;">${order.created_at_display}</td>
        <td class="actions-cell" style="white-space:nowrap;">
          <a href="/admin/ledger/order/${order.order_id}" class="action-icon" title="View full ledger detail">
            <i class="fa-solid fa-book"></i>
          </a>
          ${payoutStatus === 'PAYOUT_READY'
            ? `<a href="/admin/ledger/order/${order.order_id}" class="action-icon"
                 title="View payout details" style="color:#10b981;">
                 <i class="fa-solid fa-circle-dollar-to-slot"></i>
               </a>`
            : ''}
          ${(order.payment_status === 'paid' && !['PAID_OUT', 'PAYOUT_CANCELLED', 'PAYOUT_ON_HOLD'].includes(payoutStatus))
            ? `<button class="action-icon" onclick="adminNudgeSeller(${order.order_id}, this)"
                 title="Nudge seller to upload tracking" style="background:none;border:none;cursor:pointer;padding:0 4px;">
                 <i class="fa-solid fa-bell" style="color:#3b82f6;"></i>
               </button>`
            : ''}
        </td>
      </tr>
    `;
  });

  tbody.innerHTML = html;
}

function formatPayoutStateBadge(ps) {
  const map = {
    'PAID_OUT':           '<span style="color:#10b981;font-weight:600;font-size:11px;">✓ Paid Out</span>',
    'PAYOUT_READY':       '<span style="color:#059669;font-weight:600;font-size:11px;"><i class="fa-solid fa-circle-check"></i> Ready</span>',
    'PAYOUT_ON_HOLD':     '<span style="color:#d97706;font-size:11px;">On Hold</span>',
    'PAYOUT_CANCELLED':   '<span style="color:#9ca3af;font-size:11px;">Cancelled</span>',
    'PAYOUT_NOT_READY':   '<span style="color:#6b7280;font-size:11px;">Not ready</span>',
    'PAYOUT_SCHEDULED':   '<span style="color:#3b82f6;font-size:11px;">Scheduled</span>',
    'PAYOUT_IN_PROGRESS': '<span style="color:#3b82f6;font-size:11px;">In progress</span>',
  };
  return map[ps] || `<span style="font-size:11px;color:#9ca3af;">${ps ? ps.replace(/_/g,' ') : '—'}</span>`;
}

function formatPaymentMethodIcon(pmt) {
  if (!pmt) return '<span style="color:#d1d5db;">—</span>';
  const p = pmt.toLowerCase();
  if (p.includes('ach') || p.includes('bank') || p.includes('us_bank'))
    return '<span style="color:#d97706;font-size:12px;"><i class="fa-solid fa-building-columns"></i> ACH</span>';
  if (p === 'card')
    return '<span style="color:#6b7280;font-size:12px;"><i class="fa-solid fa-credit-card"></i> Card</span>';
  return `<span style="font-size:12px;color:#6b7280;">${escapeHtml(pmt)}</span>`;
}

function getLedgerStatusClass(status) {
  const statusClasses = {
    'CHECKOUT_INITIATED': 'status-pending',
    'PAYMENT_PENDING': 'status-pending',
    'PAID_IN_ESCROW': 'status-processing',
    'UNDER_REVIEW': 'status-investigating',
    'AWAITING_SHIPMENT': 'status-active',
    'PARTIALLY_SHIPPED': 'status-active',
    'SHIPPED': 'status-active',
    'COMPLETED': 'status-completed',
    'CANCELLED': 'status-dismissed',
    'REFUNDED': 'status-dismissed'
  };
  return statusClasses[status] || 'status-pending';
}

function formatLedgerStatus(status) {
  return status.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, l => l.toUpperCase());
}

function applyLedgerFilters() {
  ledgerCurrentPage = 0;
  loadLedgerOrders();
}

function clearLedgerFilters() {
  ['ledgerStatusFilter','ledgerPaymentStatusFilter','ledgerPayoutStatusFilter',
   'ledgerBuyerIdFilter','ledgerStartDate','ledgerEndDate',
   'ledgerMinGross','ledgerMaxGross'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  ledgerCurrentPage = 0;
  loadLedgerOrders();
}

function updateLedgerPagination() {
  const pageInfo = document.getElementById('ledgerPageInfo');
  const btnPrev = document.getElementById('ledgerPrevBtn');
  const btnNext = document.getElementById('ledgerNextBtn');

  pageInfo.textContent = `Page ${ledgerCurrentPage + 1}`;
  btnPrev.disabled = ledgerCurrentPage === 0;
  btnNext.disabled = ledgerTotalLoaded < ledgerPageSize;
}

function ledgerPrevPage() {
  if (ledgerCurrentPage > 0) {
    ledgerCurrentPage--;
    loadLedgerOrders();
  }
}

function ledgerNextPage() {
  ledgerCurrentPage++;
  loadLedgerOrders();
}

function viewLedgerOrder(orderId) {
  const modal = document.getElementById('ledgerOrderModal');
  const content = document.getElementById('ledgerOrderContent');
  document.getElementById('ledgerOrderIdTitle').textContent = '#' + orderId;

  // Show modal with loading state
  modal.style.display = 'flex';
  content.innerHTML = `
    <div class="modal-loading">
      <i class="fa-solid fa-spinner fa-spin"></i>
      <span>Loading order details...</span>
    </div>
  `;

  // Fetch order details
  fetch(`/admin/api/ledger/order/${orderId}`)
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        renderLedgerOrderDetails(data.data);
      } else {
        content.innerHTML = `<p class="error" style="color: #ef4444; text-align: center; padding: 40px;">Error: ${data.error}</p>`;
      }
    })
    .catch(error => {
      content.innerHTML = `<p class="error" style="color: #ef4444; text-align: center; padding: 40px;">Failed to load order details</p>`;
      console.error('Error:', error);
    });
}

function renderLedgerOrderDetails(data) {
  const content = document.getElementById('ledgerOrderContent');
  const order = data.order;
  const items = data.items;
  const payouts = data.payouts;
  const events = data.events;

  const statusClass = getLedgerStatusClass(order.order_status);

  // Items HTML
  let itemsHtml = '';
  items.forEach(item => {
    itemsHtml += `
      <tr>
        <td>#${item.listing_id}</td>
        <td>@${escapeHtml(item.seller_username)} (${item.seller_id})</td>
        <td>${item.quantity}</td>
        <td style="font-family: monospace;">${formatPrice(item.unit_price)}</td>
        <td style="font-family: monospace;">${formatPrice(item.gross_amount)}</td>
        <td><span style="background: #e5e7eb; padding: 2px 6px; border-radius: 4px; font-size: 10px;">${item.fee_type}</span></td>
        <td>${item.fee_value}${item.fee_type === 'percent' ? '%' : ''}</td>
        <td style="font-family: monospace; color: #dc2626;">${formatPrice(item.fee_amount)}</td>
        <td style="font-family: monospace; color: #059669;">${formatPrice(item.seller_net_amount)}</td>
      </tr>
    `;
  });

  // Payouts HTML
  let payoutsHtml = '';
  payouts.forEach(payout => {
    const payoutStatusClass = getPayoutStatusClass(payout.payout_status);
    payoutsHtml += `
      <tr>
        <td>@${escapeHtml(payout.seller_username)} (${payout.seller_id})</td>
        <td><span class="status-badge ${payoutStatusClass}">${formatLedgerStatus(payout.payout_status)}</span></td>
        <td style="font-family: monospace;">${formatPrice(payout.seller_gross_amount)}</td>
        <td style="font-family: monospace; color: #dc2626;">${formatPrice(payout.fee_amount)}</td>
        <td style="font-family: monospace; color: #059669;">${formatPrice(payout.seller_net_amount)}</td>
        <td>${payout.scheduled_for || '-'}</td>
        <td style="font-size: 10px; color: #888;">${payout.provider_transfer_id || '-'}</td>
      </tr>
    `;
  });

  // Events HTML
  let eventsHtml = '';
  events.forEach(event => {
    const payload = event.payload ? JSON.stringify(event.payload, null, 2) : '';
    eventsHtml += `
      <div class="ledger-event-item" style="margin-bottom: 12px; padding: 10px; background: #f9fafb; border-radius: 6px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
          <strong style="font-size: 13px;">${formatLedgerStatus(event.event_type)}</strong>
          <span style="font-size: 11px; color: #888;">${event.created_at}</span>
        </div>
        <div style="font-size: 11px; color: #666;">
          <span style="background: #e5e7eb; padding: 1px 6px; border-radius: 3px; font-size: 10px; text-transform: uppercase;">${event.actor_type}</span>
          ${event.actor_id ? `<span style="margin-left: 4px;">(ID: ${event.actor_id})</span>` : ''}
        </div>
        ${payload ? `<pre style="margin-top: 8px; padding: 8px; background: #fff; border: 1px solid #e5e7eb; border-radius: 4px; font-size: 10px; overflow-x: auto;">${escapeHtml(payload)}</pre>` : ''}
      </div>
    `;
  });

  content.innerHTML = `
    <!-- Order Header -->
    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; padding: 16px; background: #f9fafb; border-radius: 8px;">
      <div>
        <div style="font-size: 11px; color: #888; text-transform: uppercase; margin-bottom: 4px;">Status</div>
        <span class="status-badge ${statusClass}">${formatLedgerStatus(order.order_status)}</span>
      </div>
      <div>
        <div style="font-size: 11px; color: #888; text-transform: uppercase; margin-bottom: 4px;">Buyer</div>
        <span style="font-weight: 500;">@${escapeHtml(order.buyer_username)}</span>
        <span style="font-size: 11px; color: #888;"> (${order.buyer_id})</span>
      </div>
      <div>
        <div style="font-size: 11px; color: #888; text-transform: uppercase; margin-bottom: 4px;">Payment</div>
        <span>${order.payment_method || 'Not Set'}</span>
      </div>
      <div>
        <div style="font-size: 11px; color: #888; text-transform: uppercase; margin-bottom: 4px;">Created</div>
        <span style="font-size: 12px;">${order.created_at}</span>
      </div>
    </div>

    <!-- Amount Summary -->
    <div style="display: flex; gap: 32px; margin-bottom: 24px;">
      <div>
        <div style="font-size: 11px; color: #888; text-transform: uppercase; margin-bottom: 4px;">Gross Amount</div>
        <div style="font-size: 24px; font-weight: 600; font-family: monospace;">${formatPrice(order.gross_amount)}</div>
      </div>
      <div>
        <div style="font-size: 11px; color: #888; text-transform: uppercase; margin-bottom: 4px;">Platform Fee</div>
        <div style="font-size: 24px; font-weight: 600; font-family: monospace; color: #dc2626;">${formatPrice(order.platform_fee_amount)}</div>
      </div>
      <div>
        <div style="font-size: 11px; color: #888; text-transform: uppercase; margin-bottom: 4px;">Net to Sellers</div>
        <div style="font-size: 24px; font-weight: 600; font-family: monospace; color: #059669;">${formatPrice(order.gross_amount - order.platform_fee_amount)}</div>
      </div>
    </div>

    <!-- Items Table -->
    <div style="margin-bottom: 24px;">
      <h4 style="margin-bottom: 12px; font-size: 14px; font-weight: 600;">Order Items (${items.length})</h4>
      <div style="overflow-x: auto;">
        <table class="data-table" style="font-size: 12px;">
          <thead>
            <tr>
              <th>Listing</th>
              <th>Seller</th>
              <th>Qty</th>
              <th>Unit Price</th>
              <th>Gross</th>
              <th>Fee Type</th>
              <th>Fee Value</th>
              <th>Fee</th>
              <th>Seller Net</th>
            </tr>
          </thead>
          <tbody>${itemsHtml}</tbody>
        </table>
      </div>
    </div>

    <!-- Payouts Table -->
    <div style="margin-bottom: 24px;">
      <h4 style="margin-bottom: 12px; font-size: 14px; font-weight: 600;">Seller Payouts (${payouts.length})</h4>
      <div style="overflow-x: auto;">
        <table class="data-table" style="font-size: 12px;">
          <thead>
            <tr>
              <th>Seller</th>
              <th>Status</th>
              <th>Gross</th>
              <th>Fee</th>
              <th>Net</th>
              <th>Scheduled For</th>
              <th>Transfer ID</th>
            </tr>
          </thead>
          <tbody>${payoutsHtml}</tbody>
        </table>
      </div>
    </div>

    <!-- Events Timeline -->
    <div>
      <h4 style="margin-bottom: 12px; font-size: 14px; font-weight: 600;">Event Timeline (${events.length})</h4>
      <div style="max-height: 300px; overflow-y: auto;">
        ${eventsHtml}
      </div>
    </div>
  `;
}

function getPayoutStatusClass(status) {
  const statusClasses = {
    'PAYOUT_NOT_READY': 'status-pending',
    'PAYOUT_READY': 'status-active',
    'PAYOUT_ON_HOLD': 'status-investigating',
    'PAYOUT_SCHEDULED': 'status-processing',
    'PAYOUT_IN_PROGRESS': 'status-processing',
    'PAID_OUT': 'status-completed',
    'PAYOUT_CANCELLED': 'status-dismissed'
  };
  return statusClasses[status] || 'status-pending';
}

function closeLedgerOrderModal() {
  document.getElementById('ledgerOrderModal').style.display = 'none';
}

// ============================================================
// Inline Refund Modal (used from the Ledger tab order list)
// ============================================================

var _inlineRefundOrderId = null;

function refundBuyer(orderId) {
  _inlineRefundOrderId = orderId;
  var overlay = document.getElementById('inlineRefundModal');
  var body    = document.getElementById('inlineRefundModalBody');
  if (!overlay || !body) { alert('Refund modal not available.'); return; }
  body.innerHTML = '<div style="text-align:center;padding:30px;"><i class="fa-solid fa-spinner fa-spin fa-lg"></i> Loading refund details…</div>';
  overlay.style.display = 'flex';

  fetch('/admin/api/orders/' + orderId + '/refund-preview')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data.success) {
        body.innerHTML = '<p style="color:#ef4444;padding:20px;">Error: ' + _escInline(data.error || 'Unknown error') + '</p>';
        return;
      }
      _renderInlineRefundModal(data, orderId);
    })
    .catch(function(err) {
      body.innerHTML = '<p style="color:#ef4444;padding:20px;">Network error: ' + _escInline(String(err)) + '</p>';
    });
}

function _escInline(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function _fmtAmtInline(n) {
  if (n == null || n === '') return '—';
  return '$' + Number(n).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

function _renderInlineRefundModal(data, orderId) {
  var body = document.getElementById('inlineRefundModalBody');
  var o = data.order || {};

  if (!data.can_refund) {
    body.innerHTML = '<div style="padding:20px;color:#b91c1c;background:#fef2f2;border-radius:8px;">'
      + '<i class="fa-solid fa-ban"></i> <strong>Cannot Refund:</strong> ' + _escInline(data.block_reason) + '</div>';
    return;
  }

  var subtotal   = o.subtotal != null ? o.subtotal : (o.total_price - o.tax_amount - o.buyer_card_fee);
  var maxRefund  = data.refundable_amount;
  var alreadyRef = data.already_refunded || 0;

  var recoveryNote = data.requires_recovery
    ? '<div style="margin:8px 0;padding:8px;background:#fffbeb;border:1px solid #fde68a;border-radius:6px;font-size:12px;">'
      + '<i class="fa-solid fa-triangle-exclamation" style="color:#d97706;"></i>'
      + ' <strong>Recovery Required</strong> — ' + data.paid_out_payout_count + ' payout(s) already transferred. Auto-reversal will be attempted.'
      + '</div>'
    : '<div style="margin:8px 0;padding:8px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;font-size:12px;">'
      + '<i class="fa-solid fa-circle-check" style="color:#16a34a;"></i> No seller recovery needed.</div>';

  body.innerHTML = '<div style="display:flex;flex-direction:column;gap:12px;">'
    + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:13px;">'
    + '<div><span style="color:#6b7280;font-size:11px;">ORDER</span><br><strong>#' + _escInline(orderId) + '</strong></div>'
    + '<div><span style="color:#6b7280;font-size:11px;">BUYER</span><br><strong>@' + _escInline(o.buyer_username) + '</strong></div>'
    + '</div>'

    // Breakdown
    + '<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;padding:10px;font-size:12px;">'
    + '<div style="font-weight:600;margin-bottom:6px;">Charge Breakdown</div>'
    + '<div style="display:flex;justify-content:space-between;"><span style="color:#6b7280;">Subtotal</span><span style="font-family:monospace;">' + _fmtAmtInline(subtotal) + '</span></div>'
    + (o.tax_amount > 0 ? '<div style="display:flex;justify-content:space-between;"><span style="color:#6b7280;">Tax</span><span style="font-family:monospace;">' + _fmtAmtInline(o.tax_amount) + '</span></div>' : '')
    + (o.buyer_card_fee > 0 ? '<div style="display:flex;justify-content:space-between;"><span style="color:#6b7280;">Card Fee</span><span style="font-family:monospace;">' + _fmtAmtInline(o.buyer_card_fee) + '</span></div>' : '')
    + '<div style="display:flex;justify-content:space-between;border-top:1px solid #e5e7eb;margin-top:4px;padding-top:4px;font-weight:600;"><span>Total Charged</span><span style="font-family:monospace;">' + _fmtAmtInline(o.total_price) + '</span></div>'
    + (alreadyRef > 0 ? '<div style="display:flex;justify-content:space-between;color:#d97706;"><span>Already Refunded</span><span style="font-family:monospace;">-' + _fmtAmtInline(alreadyRef) + '</span></div>' : '')
    + '<div style="display:flex;justify-content:space-between;font-weight:600;color:#dc2626;"><span>Refundable Remaining</span><span style="font-family:monospace;">' + _fmtAmtInline(maxRefund) + '</span></div>'
    + '</div>'

    + recoveryNote

    // Amount input
    + '<div>'
    + '<label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">Refund Amount</label>'
    + '<div style="display:flex;align-items:center;gap:6px;">'
    + '<span>$</span>'
    + '<input id="inlineRefundAmountInput" type="number" min="0.01" max="' + maxRefund + '" step="0.01" value="' + maxRefund.toFixed(2) + '" '
    + 'style="flex:1;padding:6px 10px;border:1px solid #d1d5db;border-radius:6px;font-size:13px;font-family:monospace;">'
    + '</div>'
    + '</div>'

    + '<div>'
    + '<label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">Reason (optional)</label>'
    + '<textarea id="inlineRefundReasonInput" rows="2" style="width:100%;box-sizing:border-box;padding:8px;border:1px solid #d1d5db;border-radius:6px;font-size:12px;resize:vertical;" placeholder="Reason for refund…"></textarea>'
    + '</div>'

    + '<div style="font-size:11px;color:#b91c1c;background:#fef2f2;border:1px solid #fecaca;border-radius:6px;padding:8px;">'
    + '<i class="fa-solid fa-triangle-exclamation"></i> <strong>Irreversible.</strong> Stripe refund issued immediately.'
    + '</div>'

    + '<div style="display:flex;gap:8px;justify-content:flex-end;">'
    + '<button onclick="closeInlineRefundModal()" style="padding:8px 14px;background:#6b7280;color:#fff;border:none;border-radius:6px;cursor:pointer;">Cancel</button>'
    + '<button id="inlineRefundConfirmBtn" onclick="executeInlineRefund()" style="padding:8px 14px;background:#dc2626;color:#fff;border:none;border-radius:6px;cursor:pointer;">'
    + '<i class="fa-solid fa-rotate-left"></i> Confirm Refund</button>'
    + '</div>'
    + '</div>';
}

function closeInlineRefundModal() {
  var overlay = document.getElementById('inlineRefundModal');
  if (overlay) overlay.style.display = 'none';
  _inlineRefundOrderId = null;
}

function executeInlineRefund() {
  var btn    = document.getElementById('inlineRefundConfirmBtn');
  var reason = (document.getElementById('inlineRefundReasonInput') || {}).value || '';
  var amtEl  = document.getElementById('inlineRefundAmountInput');
  var amount = amtEl ? parseFloat(amtEl.value) : null;
  var orderId = _inlineRefundOrderId;

  if (!orderId) return;
  if (btn && btn.disabled) return;
  if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing…'; }

  var payload = {reason: reason || 'Admin refund'};
  if (amount && amount > 0) payload.amount = amount;

  // CSRF token — try window.getCsrfToken if defined, else read meta tag
  var csrfToken = (typeof getCsrfToken === 'function') ? getCsrfToken()
    : (document.querySelector('meta[name="csrf-token"]') || {}).content || '';

  fetch('/admin/api/orders/' + orderId + '/refund-stripe', {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
    credentials: 'same-origin',
    body: JSON.stringify(payload),
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    var body = document.getElementById('inlineRefundModalBody');
    if (data.success) {
      // ── Buyer Refund Status ──────────────────────────────────────────────
      var buyerStatusHtml =
        '<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;">'
        + '<span style="color:#6b7280;font-size:12px;">Buyer Refund</span>'
        + '<span style="font-size:12px;font-weight:600;color:#16a34a;"><i class="fa-solid fa-circle-check"></i> Succeeded</span>'
        + '</div>'
        + '<div style="font-size:11px;color:#6b7280;padding-bottom:6px;">Stripe ID: <code>' + _escInline(data.refund_id) + '</code></div>';

      // ── Seller Recovery Status ───────────────────────────────────────────
      var recoveryOutcomes = data.recovery_outcomes || [];
      var sellerStatusHtml;
      if (recoveryOutcomes.length === 0) {
        // No paid-out payouts — no recovery needed
        sellerStatusHtml =
          '<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;">'
          + '<span style="color:#6b7280;font-size:12px;">Seller Recovery</span>'
          + '<span style="font-size:12px;color:#6b7280;"><i class="fa-solid fa-minus"></i> Not Required</span>'
          + '</div>';
      } else {
        var allRecovered = recoveryOutcomes.every(function(r) { return r.outcome === 'recovered'; });
        var anyManual    = recoveryOutcomes.some(function(r)  { return r.outcome === 'manual_review'; });
        var anyFailed    = recoveryOutcomes.some(function(r)  { return r.outcome === 'failed'; });
        var recoveryLabel, recoveryColor, recoveryIcon;
        if (allRecovered) {
          recoveryLabel = 'Succeeded'; recoveryColor = '#16a34a'; recoveryIcon = 'fa-circle-check';
        } else if (anyManual) {
          recoveryLabel = 'Manual Review Required'; recoveryColor = '#d97706'; recoveryIcon = 'fa-triangle-exclamation';
        } else {
          recoveryLabel = 'Failed'; recoveryColor = '#dc2626'; recoveryIcon = 'fa-xmark-circle';
        }
        sellerStatusHtml =
          '<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;">'
          + '<span style="color:#6b7280;font-size:12px;">Seller Recovery</span>'
          + '<span style="font-size:12px;font-weight:600;color:' + recoveryColor + ';">'
          + '<i class="fa-solid ' + recoveryIcon + '"></i> ' + _escInline(recoveryLabel) + '</span>'
          + '</div>';
        // Per-payout detail
        sellerStatusHtml += '<div style="font-size:11px;color:#6b7280;padding-bottom:6px;">';
        recoveryOutcomes.forEach(function(r) {
          var icon = r.outcome === 'recovered' ? '✅' : (r.outcome === 'manual_review' ? '⚠️' : '❌');
          sellerStatusHtml += icon + ' Payout #' + r.payout_id + ' — ' + _escInline(r.outcome)
            + (r.reversal_id ? ' (<code>' + _escInline(r.reversal_id) + '</code>)' : '')
            + '<br>';
        });
        sellerStatusHtml += '</div>';
      }

      // ── Platform Coverage Status ─────────────────────────────────────────
      var platformCovered = data.platform_covered_amount || 0;
      var platformStatusHtml;
      if (platformCovered <= 0) {
        platformStatusHtml =
          '<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;">'
          + '<span style="color:#6b7280;font-size:12px;">Platform Coverage</span>'
          + '<span style="font-size:12px;color:#6b7280;"><i class="fa-solid fa-minus"></i> Not Used</span>'
          + '</div>';
      } else {
        platformStatusHtml =
          '<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;">'
          + '<span style="color:#6b7280;font-size:12px;">Platform Coverage</span>'
          + '<span style="font-size:12px;font-weight:600;color:#7c3aed;">'
          + '<i class="fa-solid fa-building-columns"></i> ' + _fmtAmtInline(platformCovered) + ' covered by Metex</span>'
          + '</div>'
          + '<div style="font-size:11px;color:#7c3aed;background:#f5f3ff;border:1px solid #ddd6fe;border-radius:6px;padding:7px;margin-bottom:6px;">'
          + '<i class="fa-solid fa-circle-info"></i> Seller funds could not be recovered. This refund was covered by Metex.'
          + '</div>';
      }

      // ── Financial Breakdown ────────────────────────────────────────────
      var recoveredFromSeller = 0;
      recoveryOutcomes.forEach(function(r) {
        if (r.outcome === 'recovered') recoveredFromSeller += (r.seller_net_amount || 0);
      });
      function _ilBkRow(label, val, bold, color) {
        var lStyle = 'color:' + (color || '#6b7280') + ';' + (bold ? 'font-weight:700;color:' + (color || '#111827') + ';' : '');
        var vStyle = 'font-family:monospace;' + (bold ? 'font-weight:700;' : '') + (color ? 'color:' + color + ';' : '');
        return '<div style="display:flex;justify-content:space-between;padding:2px 0;">'
          + '<span style="font-size:12px;' + lStyle + '">' + label + '</span>'
          + '<span style="font-size:12px;' + vStyle + '">' + _fmtAmtInline(val) + '</span>'
          + '</div>';
      }
      var breakdownHtml =
        '<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:10px 14px;margin-top:10px;">'
        + '<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:#6b7280;margin-bottom:6px;">Refund Breakdown</div>'
        + _ilBkRow('Subtotal refunded', data.refund_subtotal)
        + (data.refund_tax_amount > 0 ? _ilBkRow('Tax refunded', data.refund_tax_amount) : '')
        + (data.refund_processing_fee > 0 ? _ilBkRow('Processing fee refunded', data.refund_processing_fee) : '')
        + _ilBkRow('Total refunded', data.amount, true)
        + (recoveryOutcomes.length > 0 ? _ilBkRow('Recovered from seller', recoveredFromSeller, false, '#16a34a') : '')
        + (platformCovered > 0 ? _ilBkRow('Covered by platform', platformCovered, false, '#7c3aed') : '')
        + '</div>';

      body.innerHTML =
        '<div style="padding:16px;">'
        // Success header
        + '<div style="text-align:center;margin-bottom:14px;">'
        + '<div style="font-size:32px;color:#16a34a;margin-bottom:6px;"><i class="fa-solid fa-circle-check"></i></div>'
        + '<h3 style="margin:0 0 2px;">' + (data.is_partial ? 'Partial ' : '') + 'Refund Issued</h3>'
        + '<div style="font-size:13px;font-weight:600;color:#dc2626;">' + _fmtAmtInline(data.amount) + '</div>'
        + '</div>'

        // Three-way status section
        + '<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:10px 14px;margin-bottom:10px;">'
        + '<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:#374151;margin-bottom:4px;">Refund Method &amp; Recovery Status</div>'
        + buyerStatusHtml
        + '<div style="border-top:1px solid #e5e7eb;"></div>'
        + sellerStatusHtml
        + '<div style="border-top:1px solid #e5e7eb;"></div>'
        + platformStatusHtml
        + '</div>'

        // Platform coverage alert
        + (platformCovered > 0
          ? '<div style="background:#f5f3ff;border:1px solid #ddd6fe;border-radius:8px;padding:10px 12px;display:flex;gap:8px;align-items:flex-start;margin-bottom:10px;">'
            + '<i class="fa-solid fa-building-columns" style="color:#7c3aed;font-size:14px;margin-top:2px;flex-shrink:0;"></i>'
            + '<div><strong style="color:#5b21b6;font-size:12px;">Platform-Covered Refund</strong><br>'
            + '<span style="font-size:12px;color:#6b21a8;">Seller funds could not be recovered. This refund of <strong>' + _fmtAmtInline(platformCovered) + '</strong> was covered by Metex.</span>'
            + '</div></div>'
          : '')

        // Financial breakdown
        + breakdownHtml

        + '<div style="text-align:center;margin-top:14px;">'
        + '<button onclick="closeInlineRefundModal();if(typeof loadLedgerOrders===\'function\')loadLedgerOrders();" '
        + 'style="padding:8px 20px;background:#374151;color:#fff;border:none;border-radius:6px;cursor:pointer;">Done</button>'
        + '</div>'
        + '</div>';
    } else {
      if (body) body.innerHTML += '<div style="margin-top:8px;padding:8px;background:#fef2f2;border:1px solid #fecaca;border-radius:6px;font-size:12px;color:#b91c1c;">'
        + '<i class="fa-solid fa-xmark"></i> Error: ' + _escInline(data.error) + '</div>';
      if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-rotate-left"></i> Confirm Refund'; }
    }
  })
  .catch(function(err) {
    var body = document.getElementById('inlineRefundModalBody');
    if (body) body.innerHTML += '<div style="margin-top:8px;padding:8px;background:#fef2f2;border:1px solid #fecaca;border-radius:6px;font-size:12px;color:#b91c1c;">'
      + 'Network error: ' + _escInline(String(err)) + '</div>';
    if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-rotate-left"></i> Confirm Refund'; }
  });
}

// Export ledger functions
window.loadLedgerStats = loadLedgerStats;
window.loadLedgerOrders = loadLedgerOrders;
window.applyLedgerFilters = applyLedgerFilters;
window.clearLedgerFilters = clearLedgerFilters;
window.ledgerPrevPage = ledgerPrevPage;
window.ledgerNextPage = ledgerNextPage;
window.viewLedgerOrder = viewLedgerOrder;
window.closeLedgerOrderModal = closeLedgerOrderModal;

// Export new functions
window.loadDisputes = loadDisputes;
window.viewReportDetails = viewReportDetails;
window.closeAdminReportModal = closeAdminReportModal;
window.viewUserStats = viewUserStats;
window.closeUserStatsModal = closeUserStatsModal;
window.openResolveModal = openResolveModal;
window.closeResolveReportModal = closeResolveReportModal;
window.submitResolveReport = submitResolveReport;
window.quickResolve = quickResolve;
window.haltFunds = haltFunds;
window.refundBuyer = refundBuyer;
window.closeInlineRefundModal = closeInlineRefundModal;
window.executeInlineRefund = executeInlineRefund;


// ========== BUCKET MANAGEMENT ==========

let bucketPage = 1;
let bucketPerPage = 50;
let bucketTotalPages = 1;
let bucketFilters = {
  search: '',
  metal: ''
};

