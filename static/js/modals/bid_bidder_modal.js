// static/js/modals/bid_bidder_modal.js
// Modal for viewing bidder (buyer) information on the Bucket ID page
// Styled to match the order_sellers_modal osm-* layout

function openBidderModal(bidId) {
  fetch(`/bids/api/bid/${bidId}/bidder_info`)
    .then(res => {
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      return res.json();
    })
    .then(data => {
      if (data.error) {
        alert('Error loading buyer information: ' + data.error);
        return;
      }
      renderBidder(data);
      const modal = document.getElementById('bidBidderModal');
      modal.style.display = 'flex';
      modal.addEventListener('click', _outsideBidderClick);
    })
    .catch(err => {
      console.error('[Bidder Modal] Error:', err);
      alert('Failed to load buyer information. Please try again.');
    });
}

function closeBidderModal() {
  const modal = document.getElementById('bidBidderModal');
  modal.removeEventListener('click', _outsideBidderClick);
  window.animatedModalClose(modal, function() {
    modal.style.display = 'none';
  });
}

function _outsideBidderClick(e) {
  if (e.target && e.target.id === 'bidBidderModal') closeBidderModal();
}

function _esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}

function renderBidder(b) {
  const container = document.getElementById('bidBidderModalContent');
  if (!container) return;

  // Avatar initial
  const initial = (b.display_name || b.username || '?')[0].toUpperCase();

  // Stars
  const ratingVal = parseFloat(b.rating || 0);
  let starsHtml = '';
  for (let i = 1; i <= 5; i++) {
    starsHtml += `<span class="star${i <= Math.round(ratingVal) ? '' : ' empty'}">&#9733;</span>`;
  }

  // Verified badge
  const verifiedBadge = b.is_verified
    ? `<span class="osm-verified-badge"><i class="fa-solid fa-shield-halved"></i> Verified Buyer</span>`
    : '';

  // Stats values
  const transactions = b.transaction_count != null ? Number(b.transaction_count).toLocaleString() : '--';
  const bidPriceRaw  = b.bid_price != null ? b.bid_price : null;
  const bidPriceStr  = bidPriceRaw != null
    ? '$' + Number(bidPriceRaw).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
        + (b.pricing_mode === 'premium_to_spot' ? ' (variable)' : '')
    : '--';
  const memberSince  = b.member_since || '--';
  const bidQty       = b.quantity != null ? b.quantity : '--';

  container.innerHTML = `
    <div class="osm-identity">
      <div class="osm-avatar">${initial}</div>
      <div class="osm-identity-info">
        <div class="osm-display-name">${_esc(b.display_name || b.username)}</div>
        <div class="osm-username">@${_esc(b.username)}</div>
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
            <div class="osm-reviews-count">${Number(b.num_reviews || 0).toLocaleString()} ratings</div>
          </div>
        </div>
        <div class="osm-transactions-block">
          <div class="osm-transactions-num">${transactions}</div>
          <div class="osm-transactions-label">transactions</div>
        </div>
      </div>
      <div class="osm-stats-bottom">
        <div class="osm-stat-item">
          <div class="osm-stat-icon green"><i class="fa-solid fa-tag"></i></div>
          <div>
            <div class="osm-stat-label">Bid Price</div>
            <div class="osm-stat-value">${bidPriceStr}</div>
          </div>
        </div>
        <div class="osm-stat-item">
          <div class="osm-stat-icon"><i class="fa-solid fa-cube"></i></div>
          <div>
            <div class="osm-stat-label">This Bid</div>
            <div class="osm-stat-value">${bidQty} unit${bidQty !== 1 ? 's' : ''}</div>
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
    </div>
  `;
}

window.openBidderModal  = openBidderModal;
window.closeBidderModal = closeBidderModal;
