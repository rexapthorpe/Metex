let orderSellerData = [];
let orderSellerIndex = 0;

function openOrderSellerPopup(orderId) {
  fetch(`/orders/api/${orderId}/order_sellers`)
    .then(res => {
      if (!res.ok) throw new Error('Could not load sellers');
      return res.json();
    })
    .then(data => {
      console.log('order–sellers API returned:', data);
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
  const rounded = Math.round(s.rating || 0);
  let starsHtml = '';
  for (let i = 1; i <= 5; i++) {
    starsHtml += `<span class="star${i <= rounded ? ' filled' : ''}">★</span>`;
  }

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
        <div class="avg-rating">${(s.rating||0).toFixed(1)}</div>
        <div class="stars">${starsHtml}</div>
      </div>
      <div class="stats-row">
        <div class="review-count">
          ${s.num_reviews} Review${s.num_reviews === 1 ? '' : 's'}
        </div>
      </div>
    </div>
    <div class="modal-footer">

    </div>
  `;
}



// expose globally
window.openOrderSellerPopup = openOrderSellerPopup;
window.closeOrderSellerPopup = closeOrderSellerPopup;
window.prevOrderSeller = prevOrderSeller;
window.nextOrderSeller = nextOrderSeller;
