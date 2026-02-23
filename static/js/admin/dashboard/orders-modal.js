function viewOrder(orderId) {
  const modal = document.getElementById('orderDetailModal');
  const content = document.getElementById('orderDetailContent');

  // Show modal with loading state
  modal.style.display = 'flex';
  content.innerHTML = `
    <div class="modal-loading">
      <i class="fa-solid fa-spinner fa-spin"></i>
      <span>Loading order details...</span>
    </div>
  `;

  // Fetch order details
  fetch(`/admin/api/order/${orderId}`)
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        renderOrderDetails(data.order);
      } else {
        content.innerHTML = `<p class="error">Error: ${data.error}</p>`;
      }
    })
    .catch(error => {
      content.innerHTML = `<p class="error">Failed to load order details</p>`;
      console.error('Error:', error);
    });
}

function renderOrderDetails(order) {
  const content = document.getElementById('orderDetailContent');

  const statusClass = order.status.toLowerCase().includes('completed') ? 'status-completed' :
                      order.status.toLowerCase().includes('pending') ? 'status-processing' : 'status-active';

  let itemsHtml = '';
  order.items.forEach(item => {
    itemsHtml += `
      <div class="order-item">
        <div class="order-item-info">
          <span class="order-item-title">${item.title}</span>
          <span class="order-item-meta">Qty: ${formatQuantity(item.quantity)} × ${formatPrice(item.price_each)} • Seller: @${item.seller}</span>
        </div>
        <span class="order-item-price">${formatPrice(item.subtotal)}</span>
      </div>
    `;
  });

  content.innerHTML = `
    <div class="order-detail-header">
      <div>
        <div class="order-id">Order #${order.id}</div>
        <div class="order-date">${order.created_ago}</div>
      </div>
      <span class="status-badge ${statusClass}">${order.status}</span>
    </div>

    <div class="order-parties">
      <div class="order-party">
        <div class="order-party-label">Buyer</div>
        <div class="order-party-value">@${order.buyer}</div>
      </div>
      <div class="order-party">
        <div class="order-party-label">Seller(s)</div>
        <div class="order-party-value">${order.sellers.map(s => '@' + s).join(', ')}</div>
      </div>
    </div>

    <div class="order-items-section">
      <h4>Items (${order.item_count})</h4>
      ${itemsHtml}
    </div>

    <div class="order-total">
      <span class="order-total-label">Total</span>
      <span class="order-total-value">${formatPrice(order.total_price)}</span>
    </div>

    ${order.shipping_address !== 'N/A' ? `
    <div class="order-shipping">
      <h4>Shipping Address</h4>
      <p>${order.shipping_address}</p>
      ${order.tracking_number ? `<p><strong>Tracking:</strong> ${order.tracking_number}</p>` : ''}
    </div>
    ` : ''}
  `;
}

// ============================================
// MODAL MANAGEMENT
// ============================================

function closeUserModal() {
  document.getElementById('userDetailModal').style.display = 'none';
  currentUserId = null;
}

function closeOrderModal() {
  document.getElementById('orderDetailModal').style.display = 'none';
}

function closeConfirmModal() {
  const modal = document.getElementById('confirmModal');
  const dialog = document.getElementById('confirmModalDialog');
  const successContent = document.getElementById('confirmSuccessContent');

  modal.style.display = 'none';
  pendingAction = null;

  // Reset success state
  if (dialog) dialog.classList.remove('success');
  if (successContent) successContent.classList.remove('show');
}
