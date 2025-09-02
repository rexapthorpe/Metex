let sellerData = [];
let currentIndex = 0;
let currentBucketId = null;

function openSellerPopup(bucketId) {
  // allow orders shim to override the URL
  const url = (window._sellerFetchUrl
                ? window._sellerFetchUrl(bucketId)
                : `/cart/api/bucket/${bucketId}/cart_sellers`);
  delete window._sellerFetchUrl;
  fetch(url)
    .then(res => res.json())
      .then(data => {
        sellerData = data;
        currentIndex = 0;
        currentBucketId = bucketId;
        renderSeller();
        const modal = document.getElementById('sellerModal');
        modal.style.display = 'block';
        modal.addEventListener('click', outsideClickListener);
      });
}

function closeSellerPopup() {
  const modal = document.getElementById('sellerModal');
  modal.style.display = 'none';
  modal.removeEventListener('click', outsideClickListener);
}

function outsideClickListener(e) {
  if (e.target.id === 'sellerModal') {
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

  // Build rounded stars
  const rounded = Math.round(seller.rating || 0);
  let starsHtml = '';
  for (let i = 1; i <= 5; i++) {
    starsHtml += `<span class="star${i <= rounded ? ' filled' : ''}">★</span>`;
  }

  const prevDisabled = currentIndex === 0 ? 'disabled' : '';
  const nextDisabled = currentIndex === sellerData.length - 1 ? 'disabled' : '';

  container.innerHTML = `
    <div class="modal-header">
      <button class="nav-arrow"${prevDisabled} onclick="prevSeller()">←</button>
      <div class="username-section">${seller.username}</div>
      <button class="nav-arrow"${nextDisabled} onclick="nextSeller()">→</button>
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
        onclick="openRemoveSellerConfirmation(${currentBucketId}, ${seller.seller_id}, ${seller.can_refill})"
      >
        <i class="fas fa-trash"></i> Remove Seller
      </button>
    </div>`;
}
