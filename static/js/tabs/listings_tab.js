// listings_tab.js

// Cancel an active listing (AJAX) and remove its tile
function cancelListing(listingId) {
  fetch(`/listings/cancel_listing/${listingId}`, {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  })
    .then(resp => {
      if (!resp.ok) throw new Error("Cancel failed");
      const tile = document.getElementById(`listing-${listingId}`);
      if (tile) tile.remove();
    })
    .catch(err => {
      console.error(err);
      alert("Could not cancel listing.");
    });
}

// —– Custom confirmation modal logic —–

let _cancelTargetId = null;

// Show the modal
function openCancelModal(listingId) {
  _cancelTargetId = listingId;
  const overlay = document.getElementById('cancelListingModal');
  if (overlay) overlay.classList.remove('hidden');
}

// Hide the modal
function closeCancelModal() {
  const overlay = document.getElementById('cancelListingModal');
  if (overlay) overlay.classList.add('hidden');
  _cancelTargetId = null;
}

// After DOM is ready, wire up the modal buttons
document.addEventListener('DOMContentLoaded', () => {
  const confirmBtn = document.getElementById('confirmCancelBtn');
  const dismissBtn = document.getElementById('dismissCancelBtn');
  const overlay    = document.getElementById('cancelListingModal');

  if (confirmBtn) {
    confirmBtn.addEventListener('click', () => {
      closeCancelModal();
      if (_cancelTargetId !== null) cancelListing(_cancelTargetId);
    });
  }

  if (dismissBtn) {
    dismissBtn.addEventListener('click', closeCancelModal);
  }

  // Clicking outside the content closes too
  if (overlay) {
    overlay.addEventListener('click', e => {
      if (e.target === overlay) closeCancelModal();
    });
  }
});

// Expose for inline onclicks used in the template
window.openCancelModal  = openCancelModal;
window.closeCancelModal = closeCancelModal;

// ————————————————————————————————
// Optional live UI sync for quantity changes
// ————————————————————————————————

/**
 * Update the Listings tab DOM when a listing's quantity changes.
 * - If newQuantity <= 0: remove the tile immediately.
 * - Else: update the visible quantity and the tile's data attribute.
 */
function handleListingQuantityChange(listingId, newQuantity) {
  const tile = document.getElementById(`listing-${listingId}`);
  if (!tile) return;

  const qtyNum = Number(newQuantity);
  if (!Number.isFinite(qtyNum)) return;

  if (qtyNum <= 0) {
    tile.remove();
    return;
  }

  const qtyEl = document.getElementById(`listing-qty-${listingId}`);
  if (qtyEl) qtyEl.textContent = `Quantity: ${qtyNum}`;

  tile.dataset.quantity = String(qtyNum);
}

// Listen for a custom event that other modules (e.g., edit modal)
// can dispatch after a successful update.
document.addEventListener('listing:quantity-updated', (e) => {
  const { listingId, newQuantity } = e.detail || {};
  if (listingId == null) return;
  handleListingQuantityChange(listingId, newQuantity);
});

// Also expose the helper in case you prefer direct calls
window.handleListingQuantityChange = handleListingQuantityChange;
