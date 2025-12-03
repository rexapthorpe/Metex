// static/js/modals/cart_sellers_modal.js

let sellerData = [];
let currentIndex = 0;
let currentBucketId = null;

function showSellerModal() {
  const modal = document.getElementById('sellerModal');
  if (!modal) return;

  if (typeof showModal === 'function') {
    showModal(modal);
  } else {
    modal.style.display = 'flex';
    modal.classList.add('show');
    modal.setAttribute('aria-hidden', 'false');
  }

  modal.addEventListener('click', outsideClickListener);
}

function hideSellerModal() {
  const modal = document.getElementById('sellerModal');
  if (!modal) return;

  if (typeof hideModal === 'function') {
    hideModal(modal);
  } else {
    modal.classList.remove('show');
    modal.setAttribute('aria-hidden', 'true');
    modal.style.display = 'none';
  }

  modal.removeEventListener('click', outsideClickListener);
}

function openSellerPopup(bucketId) {
  // allow orders shim to override the URL
  const url = (window._sellerFetchUrl
                ? window._sellerFetchUrl(bucketId)
                : `/cart/api/bucket/${bucketId}/cart_sellers`);
  delete window._sellerFetchUrl;

  fetch(url)
    .then(res => res.json())
    .then(data => {
      sellerData = data || [];
      currentIndex = 0;
      currentBucketId = bucketId;

      if (!sellerData.length) {
        alert('No sellers found for this item.');
        return;
      }

      renderSeller();
      showSellerModal();
    })
    .catch(err => {
      console.error('[Sellers Modal] Error loading sellers:', err);
      alert('Failed to load sellers. Please try again.');
    });
}

function closeSellerPopup() {
  hideSellerModal();
}

function outsideClickListener(e) {
  if (e.target && e.target.id === 'sellerModal') {
    closeSellerPopup();
  }
}

function prevSeller() {
  if (currentIndex > 0) {
    currentIndex--;
    renderSeller();
  }
}

function nextSeller() {
  if (currentIndex < sellerData.length - 1) {
    currentIndex++;
    renderSeller();
  }
}

function renderSeller() {
  const seller = sellerData[currentIndex];
  const container = document.getElementById('sellerModalContent');

  if (!container || !seller) return;

  console.log('[Sellers Modal] Rendering seller:', seller);

  // Build rounded stars
  const rounded = Math.round(seller.rating || 0);
  let starsHtml = '';
  for (let i = 1; i <= 5; i++) {
    starsHtml += `<span class="star${i <= rounded ? ' filled' : ''}">★</span>`;
  }

  const prevDisabled = currentIndex === 0 ? 'disabled' : '';
  const nextDisabled = currentIndex === sellerData.length - 1 ? 'disabled' : '';

  // Render with loading state for the button
  container.innerHTML = `
    <div class="modal-header">
      <button class="nav-arrow" ${prevDisabled} onclick="prevSeller()">←</button>
      <div class="username-section">${seller.username}</div>
      <button class="nav-arrow" ${nextDisabled} onclick="nextSeller()">→</button>
    </div>

    <div class="modal-body">
      <div class="seller-photo">Image</div>

      <div class="stats-row">
        <div class="rating-block">
          <span class="avg-rating">${(seller.rating || 0).toFixed(1)}</span>
          <span class="stars">${starsHtml}</span>
        </div>
      </div>

      <div class="stats-row">
        <div class="review-count">
          ${seller.num_reviews} Review${seller.num_reviews === 1 ? '' : 's'}
        </div>
      </div>

      <div class="unit-count">
        ${seller.quantity} Unit${seller.quantity === 1 ? '' : 's'} In This Order
      </div>
    </div>

    <div class="modal-footer">
      <button
        type="button"
        class="remove-btn"
        id="removeSellerBtn"
        disabled>
        <i class="fas fa-trash"></i> Checking availability...
      </button>
    </div>`;

  // Now fetch the actual refill status from backend
  fetch(`/cart/api/bucket/${currentBucketId}/can_refill/${seller.seller_id}`)
    .then(res => res.json())
    .then(data => {
      const canRefill = data.canRefill;
      console.log('[Sellers Modal] canRefill:', canRefill, 'availableCount:', data.availableCount);

      const button = document.getElementById('removeSellerBtn');
      if (button) {
        button.disabled = false;
        button.innerHTML = '<i class="fas fa-trash"></i> Remove Seller';
        button.onclick = () => openRemoveSellerConfirmation(currentBucketId, seller.seller_id, canRefill);
      }
    })
    .catch(err => {
      console.error('[Sellers Modal] Error checking refill:', err);
      // Default to safe behavior - assume no refill possible
      const button = document.getElementById('removeSellerBtn');
      if (button) {
        button.disabled = false;
        button.innerHTML = '<i class="fas fa-trash"></i> Remove Seller';
        button.onclick = () => openRemoveSellerConfirmation(currentBucketId, seller.seller_id, false);
      }
    });
}

// Make sure functions are globally available
window.openSellerPopup = openSellerPopup;
window.closeSellerPopup = closeSellerPopup;
window.prevSeller = prevSeller;
window.nextSeller = nextSeller;
