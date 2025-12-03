// static/js/modals/bid_bidder_modal.js
// Modal for viewing bidder information on the Bucket ID page

function openBidderModal(bidId) {
  console.log('[Bidder Modal] Opening modal for bid:', bidId);

  fetch(`/bids/api/bid/${bidId}/bidder_info`)
    .then(res => {
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }
      return res.json();
    })
    .then(data => {
      console.log('[Bidder Modal] Received bidder data:', data);

      if (data.error) {
        alert('Error loading bidder information: ' + data.error);
        return;
      }

      renderBidder(data);

      // Show modal - match Orders modal pattern
      const modal = document.getElementById('bidBidderModal');
      modal.style.display = 'flex';
      modal.addEventListener('click', outsideBidderClickListener);
    })
    .catch(err => {
      console.error('[Bidder Modal] Error loading bidder:', err);
      alert('Failed to load bidder information. Please try again.');
    });
}

function closeBidderModal() {
  const modal = document.getElementById('bidBidderModal');
  modal.style.display = 'none';
  modal.removeEventListener('click', outsideBidderClickListener);
}

function outsideBidderClickListener(e) {
  if (e.target && e.target.id === 'bidBidderModal') {
    closeBidderModal();
  }
}

function renderBidder(bidder) {
  const container = document.getElementById('bidBidderModalContent');

  if (!container || !bidder) {
    console.error('[Bidder Modal] Missing container or bidder data');
    return;
  }

  console.log('[Bidder Modal] Rendering bidder:', bidder);

  // Build rounded stars
  const rounded = Math.round(bidder.rating || 0);
  let starsHtml = '';
  for (let i = 1; i <= 5; i++) {
    starsHtml += `<span class="star${i <= rounded ? ' filled' : ''}">★</span>`;
  }

  // Render bidder information (no navigation arrows, no remove button)
  container.innerHTML = `
    <div class="modal-header">
      <div class="modal-title">${bidder.username}</div>
    </div>

    <div class="modal-body">
      <div class="seller-photo">Image</div>

      <div class="stats-row">
        <div class="rating-block">
          <span class="avg-rating">${(bidder.rating || 0).toFixed(1)}</span>
          <span class="stars">${starsHtml}</span>
        </div>
      </div>

      <div class="stats-row">
        <div class="review-count">
          ${bidder.num_reviews} Review${bidder.num_reviews === 1 ? '' : 's'}
        </div>
      </div>

      <div class="unit-count">
        ${bidder.quantity} Unit${bidder.quantity === 1 ? '' : 's'} In This Bid
      </div>
    </div>
  `;
}

// Make functions globally available
window.openBidderModal = openBidderModal;
window.closeBidderModal = closeBidderModal;
