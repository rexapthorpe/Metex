let orderSellerData = [];
let orderSellerIndex = 0;
let orderSellerOrderId = null;
let _osmIsCartContext = false;
let _osmIsBucketContext = false;
let _osmBucketId = null;

function _osmHandleRemoveSeller(bucketId, sellerId) {
  fetch(`/cart/api/bucket/${bucketId}/can_refill/${sellerId}`)
    .then(res => res.json())
    .then(data => openRemoveSellerConfirmation(bucketId, sellerId, data.canRefill))
    .catch(() => openRemoveSellerConfirmation(bucketId, sellerId, false));
}

function _osmEsc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}

function openOrderSellerPopup(orderId) {
  _osmIsCartContext = false;
  _osmIsBucketContext = false;
  _osmBucketId = null;
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

  // Reset title (may have been changed by openOrderBuyerPopup)
  const titleEl = document.querySelector('#orderSellersModal .osm-title');
  if (titleEl) titleEl.textContent = total > 1 ? 'Seller Information' : 'Seller Information';

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
  const unitsListed = s.total_qty != null ? Number(s.total_qty).toLocaleString() : '--';
  const avgPrice = s.avg_price != null
    ? '$' + Number(s.avg_price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : '--';

  const sellerId = s.seller_id;
  const removeHtml = _osmIsCartContext && _osmBucketId != null ? `
    <button class="osm-contact-btn osm-contact-btn--remove" type="button"
            onclick="_osmHandleRemoveSeller(${_osmBucketId}, ${sellerId})">
      <i class="fa-solid fa-user-minus"></i> Remove Seller
    </button>` : '';

  const contactHtml = orderSellerOrderId != null ? `
    <button class="osm-contact-btn" onclick="openMessageModal(${orderSellerOrderId}, 'seller'); closeOrderSellerPopup();">
      <i class="fa-regular fa-comment"></i> Contact Seller
    </button>` : `
    <button class="osm-contact-btn osm-contact-btn--locked" type="button" disabled>
      <i class="fa-solid fa-lock"></i> Contact Seller
    </button>
    <p class="osm-contact-locked-note">Buy this item to contact the seller</p>`;


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
        ${_osmIsBucketContext ? `
        <div class="osm-stat-item">
          <div class="osm-stat-icon"><i class="fa-solid fa-layer-group"></i></div>
          <div>
            <div class="osm-stat-label">Units listed</div>
            <div class="osm-stat-value">${unitsListed}</div>
          </div>
        </div>
        <div class="osm-stat-item">
          <div class="osm-stat-icon"><i class="fa-solid fa-tag"></i></div>
          <div>
            <div class="osm-stat-label">Avg. price</div>
            <div class="osm-stat-value">${avgPrice}</div>
          </div>
        </div>
        ` : `
        <div class="osm-stat-item">
          <div class="osm-stat-icon"><i class="fa-solid fa-truck"></i></div>
          <div>
            <div class="osm-stat-label">Avg. ship time</div>
            <div class="osm-stat-value">${avgShipTime}</div>
          </div>
        </div>
        <div class="osm-stat-item">
          <div class="osm-stat-icon"><i class="fa-regular fa-calendar"></i></div>
          <div>
            <div class="osm-stat-label">Member since</div>
            <div class="osm-stat-value">${memberSince}</div>
          </div>
        </div>
        `}
      </div>
    </div>

    ${removeHtml}
    ${contactHtml}
  `;
}

function openCartSellerPopup(bucketId) {
  _osmIsCartContext = true;
  _osmIsBucketContext = false;
  _osmBucketId = bucketId;
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

function openBucketSellerPopup(bucketId) {
  _osmIsCartContext = false;
  _osmIsBucketContext = true;
  _osmBucketId = null;
  orderSellerOrderId = null;
  fetch(`/api/bucket/${bucketId}/sellers`)
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
      const titleEl = document.querySelector('#orderSellersModal .osm-title');
      if (titleEl) titleEl.textContent = data.length > 1 ? 'Available Sellers' : 'Seller Information';
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

function openOrderBuyerPopup(orderId) {
  fetch(`/orders/api/${orderId}/buyer_info`)
    .then(res => {
      if (!res.ok) throw new Error('Could not load buyer info');
      return res.json();
    })
    .then(data => {
      if (data.error) {
        alert('Error loading buyer information: ' + data.error);
        return;
      }
      const esc = _osmEsc;
      const initial = (data.display_name || data.username || '?')[0].toUpperCase();
      const ratingVal = parseFloat(data.rating || 0);
      let starsHtml = '';
      for (let i = 1; i <= 5; i++) {
        starsHtml += `<span class="star${i <= Math.round(ratingVal) ? '' : ' empty'}">&#9733;</span>`;
      }
      const verifiedBadge = data.is_verified
        ? `<span class="osm-verified-badge"><i class="fa-solid fa-shield-halved"></i> Verified Buyer</span>`
        : '';
      const transactions = data.transaction_count != null ? Number(data.transaction_count).toLocaleString() : '--';
      const repeatSellersPct = data.repeat_sellers_pct != null ? `${data.repeat_sellers_pct}%` : '--';
      const memberSince = data.member_since || '--';

      const titleEl = document.querySelector('#orderSellersModal .osm-title');
      if (titleEl) titleEl.textContent = 'Buyer Information';

      document.getElementById('orderSellersModalContent').innerHTML = `
        <div class="osm-identity">
          <div class="osm-avatar">${initial}</div>
          <div class="osm-identity-info">
            <div class="osm-display-name">${esc(data.display_name || data.username)}</div>
            <div class="osm-username">@${esc(data.username)}</div>
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
                <div class="osm-reviews-count">${Number(data.num_reviews || 0).toLocaleString()} ratings</div>
              </div>
            </div>
            <div class="osm-transactions-block">
              <div class="osm-transactions-num">${transactions}</div>
              <div class="osm-transactions-label">purchases</div>
            </div>
          </div>
          <div class="osm-stats-bottom">
            <div class="osm-stat-item">
              <div class="osm-stat-icon green"><i class="fa-solid fa-arrow-trend-up"></i></div>
              <div>
                <div class="osm-stat-label">Repeat Sellers</div>
                <div class="osm-stat-value">${repeatSellersPct}</div>
              </div>
            </div>
            <div class="osm-stat-item">
              <div class="osm-stat-icon"><i class="fa-regular fa-calendar"></i></div>
              <div>
                <div class="osm-stat-label">Member since</div>
                <div class="osm-stat-value">${memberSince}</div>
              </div>
            </div>
          </div>
        </div>

        <button class="osm-contact-btn" onclick="openMessageModal(${orderId}, 'buyer'); closeOrderSellerPopup();">
          <i class="fa-regular fa-comment"></i> Contact Buyer
        </button>
      `;

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
window._osmHandleRemoveSeller = _osmHandleRemoveSeller;
window.openOrderSellerPopup = openOrderSellerPopup;
window.openOrderBuyerPopup = openOrderBuyerPopup;
window.openCartSellerPopup = openCartSellerPopup;
window.openBucketSellerPopup = openBucketSellerPopup;
window.closeOrderSellerPopup = closeOrderSellerPopup;
window.prevOrderSeller = prevOrderSeller;
window.nextOrderSeller = nextOrderSeller;
