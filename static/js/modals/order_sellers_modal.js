let orderSellerData = [];
let orderSellerIndex = 0;

function openOrderSellerPopup(orderId) {
  fetch(`/orders/api/${orderId}/order_sellers`)
    .then(res => {
      if (!res.ok) throw new Error('Could not load sellers');
      return res.json();
    })
    .then(data => {
      if (!Array.isArray(data) || data.length === 0) {
        alert('No sellers found for this order.');
        return;
      }
      orderSellerData = data;
      orderSellerIndex = 0;
      renderOrderSeller();
      const overlay = document.getElementById('orderSellersModal');
      overlay.style.display = 'flex';
      overlay.addEventListener('click', outsideClick);
    })
    .catch(err => {
      console.error(err);
      alert(err.message);
    });
}

function closeOrderSellerPopup() {
  const overlay = document.getElementById('orderSellersModal');
  overlay.style.display = 'none';
  overlay.removeEventListener('click', outsideClick);
}

function outsideClick(e) {
  if (e.target.id === 'orderSellersModal') closeOrderSellerPopup();
}

function prevOrderSeller() {
  if (orderSellerIndex > 0) {
    orderSellerIndex--;
    renderOrderSeller();
  }
}

function nextOrderSeller() {
  if (orderSellerIndex < orderSellerData.length - 1) {
    orderSellerIndex++;
    renderOrderSeller();
  }
}

function renderOrderSeller() {
  const s = orderSellerData[orderSellerIndex];

  // Build rounded stars like cart modal
  const rounded = Math.round(s.rating || 0);
  let starsHtml = '';
  for (let i = 1; i <= 5; i++) {
    starsHtml += `<span class="star${i <= rounded ? ' filled' : ''}">★</span>`;
  }

  // Optional unit-count line if API includes quantity
  const unitLine = (typeof s.quantity === 'number')
    ? `<div class="unit-count">${s.quantity} Unit${s.quantity === 1 ? '' : 's'} In This Order</div>`
    : '';

  document.getElementById('orderSellersModalContent').innerHTML = `
    <div class="modal-header">
      <button class="nav-arrow" ${orderSellerIndex === 0 ? 'disabled' : ''}
              onclick="prevOrderSeller()">←</button>
      <div class="modal-title">${s.username}</div>
      <button class="nav-arrow" ${orderSellerIndex === orderSellerData.length - 1 ? 'disabled' : ''}
              onclick="nextOrderSeller()">→</button>
    </div>

    <div class="modal-body">
      <div class="seller-photo">Image</div>

      <div class="stats-row">
        <div class="rating-block">
          <span class="avg-rating">${(s.rating || 0).toFixed(1)}</span>
          <span class="stars">${starsHtml}</span>
        </div>
      </div>

      <div class="stats-row">
        <div class="review-count">
          ${s.num_reviews} Review${s.num_reviews === 1 ? '' : 's'}
        </div>
      </div>

      ${unitLine}
    </div>

    <div class="modal-footer"></div>
  `;
}

// expose globally
window.openOrderSellerPopup = openOrderSellerPopup;
window.closeOrderSellerPopup = closeOrderSellerPopup;
window.prevOrderSeller = prevOrderSeller;
window.nextOrderSeller = nextOrderSeller;
