let _cancelTargetId = null;

// Show the modal and remember which listing
function openCancelModal(listingId) {
  _cancelTargetId = listingId;
  document.getElementById('confirmCancelListingModal').classList.remove('hidden');
}

// Hide the modal and clear target
function closeCancelModal() {
  document.getElementById('confirmCancelListingModal').classList.add('hidden');
  _cancelTargetId = null;
}

// Perform the actual cancel via AJAX
function cancelListing(listingId) {
  fetch(`/listings/cancel_listing/${listingId}`, {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  })
  .then(resp => {
    if (!resp.ok) throw new Error("Cancel failed");
    // remove the tile from the DOM
    const tile = document.getElementById(`listing-${listingId}`);
    if (tile) tile.remove();
  })
  .catch(err => {
    console.error(err);
    alert("Could not cancel listing.");
  });
}

// Wire up buttons once DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  const confirmBtn = document.getElementById('confirmCancelBtn');
  const dismissBtn = document.getElementById('dismissCancelBtn');
  const overlay   = document.getElementById('confirmCancelListingModal');

  confirmBtn.addEventListener('click', () => {
    if (_cancelTargetId !== null) {
      cancelListing(_cancelTargetId);
    }
    closeCancelModal();
  });

  dismissBtn.addEventListener('click', closeCancelModal);

  // click outside to dismiss
  overlay.addEventListener('click', e => {
    if (e.target === overlay) closeCancelModal();
  });
});

// expose globally for inline onclicks
window.openCancelModal = openCancelModal;
window.closeCancelModal = closeCancelModal;
