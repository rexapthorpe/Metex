// static/js/modals/remove_seller_confirmation_modal.js

let pendingRemoval = { bucketId: null, sellerId: null };

function openRemoveSellerConfirmation(bucketId, sellerId, canRefill = true) {
  console.log('[Remove Seller] openRemoveSellerConfirmation called with:', { bucketId, sellerId, canRefill });
  pendingRemoval = { bucketId, sellerId };
  console.log('[Remove Seller] pendingRemoval updated to:', pendingRemoval);

  // Show/hide appropriate message based on whether refill is possible
  const refillMsg = document.getElementById('refill-message');
  const warn = document.getElementById('refill-warning');
  if (refillMsg && warn) {
    if (canRefill) {
      refillMsg.style.display = 'block';
      warn.style.display = 'none';
    } else {
      refillMsg.style.display = 'none';
      warn.style.display = 'block';
    }
  }

  const modal = document.getElementById('removeSellerConfirmModal');
  console.log('[Remove Seller] Modal element found:', !!modal);
  if (modal) {
    modal.style.display = 'flex';
    modal.setAttribute('aria-hidden', 'false');
    console.log('[Remove Seller] Modal opened, canRefill:', canRefill);
  } else {
    console.error('[Remove Seller] ERROR: removeSellerConfirmModal element not found in DOM!');
  }
}

function closeRemoveSellerConfirmation() {
  console.log('[Remove Seller] closeRemoveSellerConfirmation called');
  const modal = document.getElementById('removeSellerConfirmModal');
  if (modal) {
    modal.style.display = 'none';
    modal.setAttribute('aria-hidden', 'true');
  }
}

function confirmRemoveSeller() {
  console.log('[Remove Seller] ==========================================');
  console.log('[Remove Seller] confirmRemoveSeller CALLED');
  console.log('[Remove Seller] Current pendingRemoval:', pendingRemoval);
  console.log('[Remove Seller] ==========================================');

  const { bucketId, sellerId } = pendingRemoval;

  if (!bucketId || !sellerId) {
    console.error('[Remove Seller] ERROR: Missing bucketId or sellerId!', { bucketId, sellerId });
    alert('Invalid request. Please try again.');
    return;
  }

  const url = `/cart/remove_seller/${bucketId}/${sellerId}`;
  console.log('[Remove Seller] Sending POST to:', url);

  fetch(url, {
    method: 'POST',
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
      'Content-Type': 'application/json'
    }
  })
    .then(res => {
      console.log('[Remove Seller] Response received, status:', res.status);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res;
    })
    .then(() => {
      console.log('[Remove Seller] Success! Closing modals and reloading...');
      // Close confirmation modal
      closeRemoveSellerConfirmation();

      // Close seller modal
      const sellerModal = document.getElementById('sellerModal');
      if (sellerModal) {
        sellerModal.style.display = 'none';
      }

      // Reload page to show updated cart
      location.reload();
    })
    .catch(err => {
      console.error('[Remove Seller] Error:', err);
      alert(`Failed to remove seller: ${err.message}`);
    });
}

// Expose globally immediately so inline onclick handlers can find them
window.openRemoveSellerConfirmation  = openRemoveSellerConfirmation;
window.closeRemoveSellerConfirmation = closeRemoveSellerConfirmation;
window.confirmRemoveSeller           = confirmRemoveSeller;

console.log('[Remove Seller] Script loaded. Functions exposed:', {
  openRemoveSellerConfirmation: typeof window.openRemoveSellerConfirmation,
  closeRemoveSellerConfirmation: typeof window.closeRemoveSellerConfirmation,
  confirmRemoveSeller: typeof window.confirmRemoveSeller
});

// Close modal when clicking outside
document.addEventListener('click', (e) => {
  const modal = document.getElementById('removeSellerConfirmModal');
  if (modal && e.target === modal) {
    console.log('[Remove Seller] Clicked outside modal, closing');
    closeRemoveSellerConfirmation();
  }
});
