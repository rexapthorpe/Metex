
let ledgerCurrentPage = 0;
const ledgerPageSize = 50;
let ledgerTotalLoaded = 0;

function loadLedgerStats() {
  fetch('/admin/api/ledger/stats')
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        const stats = data.stats;
        document.getElementById('ledger-stat-total-orders').textContent = stats.total_orders.toLocaleString();
        document.getElementById('ledger-stat-gross-volume').textContent = '$' + stats.total_gross_volume.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
        document.getElementById('ledger-stat-platform-fees').textContent = '$' + stats.total_platform_fees.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
        document.getElementById('ledger-stat-pending-payouts').textContent = '$' + stats.pending_payout_total.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
      }
    })
    .catch(error => console.error('Error loading ledger stats:', error));
}

function loadLedgerOrders() {
  const tbody = document.getElementById('ledgerTableBody');
  tbody.innerHTML = '<tr><td colspan="10" style="text-align: center; color: #6b7280; padding: 40px;"><i class="fa-solid fa-spinner fa-spin"></i> Loading ledger...</td></tr>';

  // Build query params
  const params = new URLSearchParams();
  params.append('limit', ledgerPageSize);
  params.append('offset', ledgerCurrentPage * ledgerPageSize);

  const status = document.getElementById('ledgerStatusFilter').value;
  const buyerId = document.getElementById('ledgerBuyerIdFilter').value;
  const startDate = document.getElementById('ledgerStartDate').value;
  const endDate = document.getElementById('ledgerEndDate').value;
  const minGross = document.getElementById('ledgerMinGross').value;
  const maxGross = document.getElementById('ledgerMaxGross').value;

  if (status) params.append('status', status);
  if (buyerId) params.append('buyer_id', buyerId);
  if (startDate) params.append('start_date', startDate);
  if (endDate) params.append('end_date', endDate);
  if (minGross) params.append('min_gross', minGross);
  if (maxGross) params.append('max_gross', maxGross);

  fetch('/admin/api/ledger/orders?' + params.toString())
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        renderLedgerOrders(data.orders);
        ledgerTotalLoaded = data.count;
        updateLedgerPagination();
      } else {
        tbody.innerHTML = '<tr><td colspan="10" style="text-align: center; color: #ef4444; padding: 40px;">Error loading ledger</td></tr>';
      }
    })
    .catch(error => {
      console.error('Error loading ledger orders:', error);
      tbody.innerHTML = '<tr><td colspan="10" style="text-align: center; color: #ef4444; padding: 40px;">Error loading ledger</td></tr>';
    });
}

function renderLedgerOrders(orders) {
  const tbody = document.getElementById('ledgerTableBody');

  if (orders.length === 0) {
    tbody.innerHTML = '<tr><td colspan="10" style="text-align: center; color: #6b7280; padding: 40px;">No ledger records found</td></tr>';
    return;
  }

  let html = '';
  orders.forEach(order => {
    const statusClass = getLedgerStatusClass(order.order_status);
    html += `
      <tr>
        <td><a href="#" onclick="viewLedgerOrder(${order.order_id}); return false;" class="order-link">#${order.order_id}</a></td>
        <td>
          <span class="user-name">@${order.buyer_username}</span>
          <span style="font-size: 11px; color: #888; margin-left: 4px;">(${order.buyer_id})</span>
        </td>
        <td><span class="status-badge ${statusClass}">${formatLedgerStatus(order.order_status)}</span></td>
        <td>${order.item_count}</td>
        <td>${order.seller_count}</td>
        <td style="font-family: monospace;">$${order.gross_amount.toFixed(2)}</td>
        <td style="font-family: monospace; color: #dc2626;">$${order.platform_fee_amount.toFixed(2)}</td>
        <td>${order.payment_method || '-'}</td>
        <td style="font-size: 12px; color: #666;">${order.created_at_display}</td>
        <td class="actions-cell">
          <button class="action-icon" title="View Ledger Details" onclick="viewLedgerOrder(${order.order_id})">
            <i class="fa-solid fa-book"></i>
          </button>
        </td>
      </tr>
    `;
  });

  tbody.innerHTML = html;
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
  document.getElementById('ledgerStatusFilter').value = '';
  document.getElementById('ledgerBuyerIdFilter').value = '';
  document.getElementById('ledgerStartDate').value = '';
  document.getElementById('ledgerEndDate').value = '';
  document.getElementById('ledgerMinGross').value = '';
  document.getElementById('ledgerMaxGross').value = '';
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
        <td style="font-family: monospace;">$${item.unit_price.toFixed(2)}</td>
        <td style="font-family: monospace;">$${item.gross_amount.toFixed(2)}</td>
        <td><span style="background: #e5e7eb; padding: 2px 6px; border-radius: 4px; font-size: 10px;">${item.fee_type}</span></td>
        <td>${item.fee_value}${item.fee_type === 'percent' ? '%' : ''}</td>
        <td style="font-family: monospace; color: #dc2626;">$${item.fee_amount.toFixed(2)}</td>
        <td style="font-family: monospace; color: #059669;">$${item.seller_net_amount.toFixed(2)}</td>
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
        <td style="font-family: monospace;">$${payout.seller_gross_amount.toFixed(2)}</td>
        <td style="font-family: monospace; color: #dc2626;">$${payout.fee_amount.toFixed(2)}</td>
        <td style="font-family: monospace; color: #059669;">$${payout.seller_net_amount.toFixed(2)}</td>
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
        <div style="font-size: 24px; font-weight: 600; font-family: monospace;">$${order.gross_amount.toFixed(2)}</div>
      </div>
      <div>
        <div style="font-size: 11px; color: #888; text-transform: uppercase; margin-bottom: 4px;">Platform Fee</div>
        <div style="font-size: 24px; font-weight: 600; font-family: monospace; color: #dc2626;">$${order.platform_fee_amount.toFixed(2)}</div>
      </div>
      <div>
        <div style="font-size: 11px; color: #888; text-transform: uppercase; margin-bottom: 4px;">Net to Sellers</div>
        <div style="font-size: 24px; font-weight: 600; font-family: monospace; color: #059669;">$${(order.gross_amount - order.platform_fee_amount).toFixed(2)}</div>
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


// ========== BUCKET MANAGEMENT ==========

let bucketPage = 1;
let bucketPerPage = 50;
let bucketTotalPages = 1;
let bucketFilters = {
  search: '',
  metal: ''
};

