let orderSellerData = [];
let orderSellerIndex = 0;
let orderSellerOrderId = null;
let _osmIsCartContext = false;

function _osmEsc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}

function openOrderSellerPopup(orderId) {
  _osmIsCartContext = false;
  orderSellerOrderId = orderId;
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
      overlay.addEventListener('click', _osmOutsideClick);
    })
    .catch(err => {
      console.error(err);
      alert(err.message);
    });
}

function closeOrderSellerPopup() {
  const overlay = document.getElementById('orderSellersModal');
  overlay.style.display = 'none';
  overlay.removeEventListener('click', _osmOutsideClick);
}

function _osmOutsideClick(e) {
  if (e.target.id === 'orderSellersModal') closeOrderSellerPopup();
}

function prevOrderSeller() {
  if (orderSellerIndex > 0) { orderSellerIndex--; renderOrderSeller(); }
}

function nextOrderSeller() {
  if (orderSellerIndex < orderSellerData.length - 1) { orderSellerIndex++; renderOrderSeller(); }
}

function renderOrderSeller() {
  const s = orderSellerData[orderSellerIndex];
  const total = orderSellerData.length;
  const esc = _osmEsc;

  // Avatar initial
  const initial = (s.display_name || s.username || '?')[0].toUpperCase();

  // Stars (rounded to nearest whole)
  const ratingVal = parseFloat(s.rating || 0);
  let starsHtml = '';
  for (let i = 1; i <= 5; i++) {
    starsHtml += `<span class="star${i <= Math.round(ratingVal) ? '' : ' empty'}">&#9733;</span>`;
  }

  // Verified badge
  const verifiedBadge = s.is_verified
    ? `<span class="osm-verified-badge"><i class="fa-solid fa-shield-halved"></i> Verified Seller</span>`
    : '';

  // Nav (only shown when multiple sellers in order)
  const navHtml = total > 1 ? `
    <div class="osm-nav">
      <button class="osm-nav-arrow" ${orderSellerIndex === 0 ? 'disabled' : ''} onclick="prevOrderSeller()">&#8592;</button>
      <span class="osm-nav-counter">${orderSellerIndex + 1} of ${total}</span>
      <button class="osm-nav-arrow" ${orderSellerIndex === total - 1 ? 'disabled' : ''} onclick="nextOrderSeller()">&#8594;</button>
    </div>
  ` : '';

  const transactions = (s.transaction_count != null)
    ? Number(s.transaction_count).toLocaleString()
    : '--';
  const fulfillmentPct = (s.fulfillment_pct != null) ? `${s.fulfillment_pct}%` : '--';
  const repeatBuyersPct = (s.repeat_buyers_pct != null) ? `${s.repeat_buyers_pct}%` : '--';
  const memberSince = s.member_since || '--';
  const avgShipTime = s.avg_ship_time || '--';

  document.getElementById('orderSellersModalContent').innerHTML = `
    ${navHtml}

    <div class="osm-identity">
      <div class="osm-avatar">${initial}</div>
      <div class="osm-identity-info">
        <div class="osm-display-name">${esc(s.display_name || s.username)}</div>
        <div class="osm-username">@${esc(s.username)}</div>
        ${verifiedBadge}
      </div>
    </div>

    <hr class="osm-divider">

    <div class="osm-stats-card">
      <div class="osm-stats-top">
        <div class="osm-rating-block">
          <div class="osm-rating-number">${ratingVal.toFixed(1)}</div>
          <div class="osm-stars-col">
            <div class="osm-stars">${starsHtml}</div>
            <div class="osm-reviews-count">${Number(s.num_reviews || 0).toLocaleString()} ratings</div>
          </div>
        </div>
        <div class="osm-transactions-block">
          <div class="osm-transactions-num">${transactions}</div>
          <div class="osm-transactions-label">transactions</div>
        </div>
      </div>
      <div class="osm-stats-bottom">
        <div class="osm-stat-item">
          <div class="osm-stat-icon"><i class="fa-solid fa-cube"></i></div>
          <div>
            <div class="osm-stat-label">Fulfillment</div>
            <div class="osm-stat-value">${fulfillmentPct}</div>
          </div>
        </div>
        <div class="osm-stat-item">
          <div class="osm-stat-icon green"><i class="fa-solid fa-arrow-trend-up"></i></div>
          <div>
            <div class="osm-stat-label">Repeat Buyers</div>
            <div class="osm-stat-value">${repeatBuyersPct}</div>
          </div>
        </div>
      </div>
    </div>

    <div class="osm-info-grid">
      <div class="osm-info-item">
        <div class="osm-info-icon"><i class="fa-regular fa-calendar"></i></div>
        <div>
          <span class="osm-info-label">Member since</span>
          <span class="osm-info-value">${memberSince}</span>
        </div>
      </div>
      <div class="osm-info-item">
        <div class="osm-info-icon"><i class="fa-solid fa-truck"></i></div>
        <div>
          <span class="osm-info-label">Avg. ship time</span>
          <span class="osm-info-value">${avgShipTime}</span>
        </div>
      </div>
    </div>

    ${!_osmIsCartContext && orderSellerOrderId != null ? `
    <button class="osm-contact-btn" onclick="openMessageModal(${orderSellerOrderId}, 'seller'); closeOrderSellerPopup();">
      <i class="fa-regular fa-comment"></i> Contact Seller
    </button>` : ''}
  `;
}

function openCartSellerPopup(bucketId) {
  _osmIsCartContext = true;
  orderSellerOrderId = null;
  fetch(`/cart/api/bucket/${bucketId}/cart_sellers`)
    .then(res => {
      if (!res.ok) throw new Error('Could not load sellers');
      return res.json();
    })
    .then(data => {
      if (!Array.isArray(data) || data.length === 0) {
        alert('No sellers found for this item.');
        return;
      }
      orderSellerData = data;
      orderSellerIndex = 0;
      renderOrderSeller();
      const overlay = document.getElementById('orderSellersModal');
      overlay.style.display = 'flex';
      overlay.addEventListener('click', _osmOutsideClick);
    })
    .catch(err => {
      console.error(err);
      alert(err.message);
    });
}

// expose globally
window.openOrderSellerPopup = openOrderSellerPopup;
window.openCartSellerPopup = openCartSellerPopup;
window.closeOrderSellerPopup = closeOrderSellerPopup;
window.prevOrderSeller = prevOrderSeller;
window.nextOrderSeller = nextOrderSeller;
