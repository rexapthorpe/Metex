// static/js/modals/remove_listing_confirmation_modal.js

let pendingListingRemoval = { listingId: null, callback: null };

function openRemoveListingConfirmation(listingId, callback = null, canRefill = true) {
  console.log('[Remove Listing] openRemoveListingConfirmation called with:', { listingId, callback: typeof callback, canRefill });
  pendingListingRemoval = { listingId, callback };
  console.log('[Remove Listing] pendingListingRemoval updated to:', pendingListingRemoval);

  // Show/hide appropriate message based on whether refill is possible
  const refillMsg = document.getElementById('refill-listing-message');
  const warn = document.getElementById('refill-listing-warning');
  if (refillMsg && warn) {
    if (canRefill) {
      refillMsg.style.display = 'block';
      warn.style.display = 'none';
    } else {
      refillMsg.style.display = 'none';
      warn.style.display = 'block';
    }
  }

  const modal = document.getElementById('removeListingConfirmModal');
  console.log('[Remove Listing] Modal element found:', !!modal);
  if (modal) {
    modal.style.display = 'flex';
    modal.setAttribute('aria-hidden', 'false');
    console.log('[Remove Listing] Modal opened, canRefill:', canRefill);
  } else {
    console.error('[Remove Listing] ERROR: removeListingConfirmModal element not found in DOM!');
  }
}

function closeRemoveListingConfirmation() {
  console.log('[Remove Listing] closeRemoveListingConfirmation called');
  const modal = document.getElementById('removeListingConfirmModal');
  if (modal) {
    modal.style.display = 'none';
    modal.setAttribute('aria-hidden', 'true');
  }
}

function confirmRemoveListing() {
  console.log('[Remove Listing] ==========================================');
  console.log('[Remove Listing] confirmRemoveListing CALLED');
  console.log('[Remove Listing] Current pendingListingRemoval:', pendingListingRemoval);
  console.log('[Remove Listing] ==========================================');

  const { listingId, callback } = pendingListingRemoval;

  if (!listingId) {
    console.error('[Remove Listing] ERROR: Missing listingId!', { listingId });
    alert('Invalid request. Please try again.');
    return;
  }

  const url = `/cart/remove_item/${listingId}`;
  console.log('[Remove Listing] Sending POST to:', url);

  fetch(url, {
    method: 'POST',
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
      'Content-Type': 'application/json'
    }
  })
    .then(res => {
      console.log('[Remove Listing] Response received, status:', res.status);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res;
    })
    .then(() => {
      console.log('[Remove Listing] Success! Closing modal...');
      closeRemoveListingConfirmation();

      // If a callback was provided, call it instead of reloading
      if (callback && typeof callback === 'function') {
        console.log('[Remove Listing] Calling provided callback');
        callback();
      } else {
        console.log('[Remove Listing] Reloading page');
        location.reload();
      }
    })
    .catch(err => {
      console.error('[Remove Listing] Error:', err);
      alert(`Failed to remove item: ${err.message}`);
    });
}

// Expose globally immediately so inline onclick handlers can find them
window.openRemoveListingConfirmation  = openRemoveListingConfirmation;
window.closeRemoveListingConfirmation = closeRemoveListingConfirmation;
window.confirmRemoveListing           = confirmRemoveListing;

console.log('[Remove Listing] Script loaded. Functions exposed:', {
  openRemoveListingConfirmation: typeof window.openRemoveListingConfirmation,
  closeRemoveListingConfirmation: typeof window.closeRemoveListingConfirmation,
  confirmRemoveListing: typeof window.confirmRemoveListing
});

// Close modal when clicking outside
document.addEventListener('click', (e) => {
  const modal = document.getElementById('removeListingConfirmModal');
  if (modal && e.target === modal) {
    console.log('[Remove Listing] Clicked outside modal, closing');
    closeRemoveListingConfirmation();
  }
});
