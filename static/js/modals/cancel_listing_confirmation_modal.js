// Load & show the confirmation modal
function openCancelModal(listingId) {
  // avoid duplicates
  if (document.getElementById('cancelModalWrapper-' + listingId)) return;

  fetch(`/listings/cancel_listing_confirmation_modal/${listingId}`)
    .then(r => {
      if (!r.ok) throw new Error('Modal fetch failed');
      return r.text();
    })
    .then(html => {
      document.getElementById('cancelModalContainer').insertAdjacentHTML('beforeend', html);
    })
    .catch(err => {
      console.error(err);
      alert('Could not load confirmation dialog.');
    });
}

// Close without action
function closeCancelModal(listingId) {
  const wrapper = document.getElementById('cancelModalWrapper-' + listingId);
  if (wrapper) wrapper.remove();
}

// Actually cancel via backend, then remove the tile
function confirmCancel(listingId) {
  fetch(`/listings/cancel_listing/${listingId}`, {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  })
  .then(resp => {
    if (!resp.ok) throw new Error('Cancel failed');
    document.getElementById(`listing-${listingId}`).remove();
    closeCancelModal(listingId);
  })
  .catch(err => {
    console.error(err);
    alert('Could not cancel listing.');
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
