// Load & show the confirmation modal
function openCancelModal(listingId) {
  console.log(`[Cancel Modal] Opening modal for listing ${listingId}`);

  // avoid duplicates
  if (document.getElementById('cancelModalWrapper-' + listingId)) {
    console.log(`[Cancel Modal] Modal already exists for listing ${listingId}`);
    return;
  }

  fetch(`/listings/cancel_listing_confirmation_modal/${listingId}`, {
    credentials: 'same-origin'  // Ensure cookies are sent
  })
    .then(r => {
      console.log(`[Cancel Modal] Fetch response status: ${r.status}`);

      // Check if redirected (login page returns 200 but is HTML redirect)
      if (r.redirected) {
        console.error('[Cancel Modal] Request was redirected - user may not be logged in');
        throw new Error('You must be logged in to cancel listings');
      }

      if (!r.ok) {
        throw new Error(`Modal fetch failed with status ${r.status}`);
      }

      return r.text();
    })
    .then(html => {
      console.log(`[Cancel Modal] Received HTML (${html.length} chars)`);

      // Verify we got modal HTML and not a login page
      if (html.includes('<!doctype html>') || html.includes('<html')) {
        console.error('[Cancel Modal] Received full HTML page instead of modal fragment');
        throw new Error('Invalid response - may need to log in again');
      }

      const container = document.getElementById('cancelModalContainer');
      if (!container) {
        console.error('[Cancel Modal] Container #cancelModalContainer not found!');
        throw new Error('Modal container not found');
      }

      container.insertAdjacentHTML('beforeend', html);
      console.log('[Cancel Modal] Modal inserted successfully');

      // Show the modal by setting display: flex
      const modal = document.getElementById(`cancelModalWrapper-${listingId}`);
      if (modal) {
        modal.style.display = 'flex';
        console.log('[Cancel Modal] Modal display set to flex - should be visible now');
      } else {
        console.error('[Cancel Modal] Could not find inserted modal to show it!');
      }
    })
    .catch(err => {
      console.error('[Cancel Modal] Error:', err);
      alert(`Could not load confirmation dialog: ${err.message}`);
    });
}

// Close without action
function closeCancelModal(listingId) {
  console.log(`[Cancel Modal] Closing modal for listing ${listingId}`);
  const wrapper = document.getElementById('cancelModalWrapper-' + listingId);
  if (wrapper) {
    wrapper.remove();
    console.log('[Cancel Modal] Modal removed from DOM');
  } else {
    console.warn(`[Cancel Modal] Modal wrapper not found for listing ${listingId}`);
  }
}

// Actually cancel via backend, then remove the tile
function confirmCancel(listingId) {
  console.log(`[Cancel Modal] Confirming cancel for listing ${listingId}`);

  fetch(`/listings/cancel_listing/${listingId}`, {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
    credentials: 'same-origin'
  })
  .then(resp => {
    console.log(`[Cancel Modal] Cancel response status: ${resp.status}`);

    if (!resp.ok) {
      throw new Error(`Cancel failed with status ${resp.status}`);
    }

    console.log(`[Cancel Modal] Listing ${listingId} cancelled successfully`);

    // Remove the listing tile from the page
    const tile = document.getElementById(`listing-${listingId}`);
    if (tile) {
      tile.remove();
      console.log(`[Cancel Modal] Removed listing tile ${listingId}`);
    } else {
      console.warn(`[Cancel Modal] Listing tile ${listingId} not found in DOM`);
    }

    closeCancelModal(listingId);
  })
  .catch(err => {
    console.error('[Cancel Modal] Error cancelling listing:', err);
    alert(`Could not cancel listing: ${err.message}`);
  });
}

// User clicked “Yes, remove”
function confirmRemoveCartBucket(bucketId) {
  fetch(`/cart/remove_bucket/${bucketId}`, {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  })
  .then(res => {
    if (!res.ok) throw new Error('Could not remove item');
    // 1) remove the tile
    const tile = document.querySelector(
      `.cart-tab .cart-item-tile[data-bucket-id="${bucketId}"]`
    );
    if (tile) tile.remove();

    // 2) close the modal
    closeRemoveItemModal(bucketId);

    // 3) if no tiles left, show empty message
    const remaining = document.querySelectorAll('.cart-tab .cart-item-tile').length;
    if (remaining === 0) {
      const column = document.querySelector('.cart-tab .cart-items-column');
      const p = document.createElement('p');
      p.className = 'empty-message';
      p.textContent = 'You have no items in your cart yet!';
      column.appendChild(p);
    }
  })
  .catch(err => {
    console.error(err);
    alert(err.message);
  });
}


// expose for inline usage
window.openCancelModal = openCancelModal;
window.closeCancelModal = closeCancelModal;
window.confirmCancel   = confirmCancel;

// Log that the script is loaded
console.log('[Cancel Listing] Script loaded. Functions exposed:', {
  openCancelModal: typeof window.openCancelModal,
  closeCancelModal: typeof window.closeCancelModal,
  confirmCancel: typeof window.confirmCancel
});
