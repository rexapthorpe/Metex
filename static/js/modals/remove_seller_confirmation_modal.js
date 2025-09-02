// static/js/modals/remove_seller_confirmation_modal.js

let pendingRemoval = { bucketId: null, sellerId: null };

function openRemoveSellerConfirmation(bucketId, sellerId, canRefill = true) {
  pendingRemoval = { bucketId, sellerId };
  const warn = document.getElementById('refill-warning');
  if (warn) {
    warn.style.display = canRefill ? 'none' : 'block';
  }
  const modal = document.getElementById('removeSellerConfirmModal');
  if (modal) {
    modal.style.display = 'flex';
  }
}

function closeRemoveSellerConfirmation() {
  const modal = document.getElementById('removeSellerConfirmModal');
  if (modal) {
    modal.style.display = 'none';
  }
}

function confirmRemoveSeller() {
  const { bucketId, sellerId } = pendingRemoval;
  fetch(`/cart/remove_seller/${bucketId}/${sellerId}`, {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  })
    .then(res => {
      if (res.ok) {
        closeRemoveSellerConfirmation();
        const sellerModal = document.getElementById('sellerModal');
        if (sellerModal) {
          sellerModal.style.display = 'none';
        }
        location.reload();
      } else {
        alert('Failed to remove seller.');
      }
    })
    .catch(() => alert('Something went wrong.'));
}

document.addEventListener('DOMContentLoaded', () => {
  const keepBtn    = document.getElementById('keepSellerBtn');
  const confirmBtn = document.getElementById('confirmRemoveSellerBtn');

  if (keepBtn) {
    keepBtn.addEventListener('click', closeRemoveSellerConfirmation);
  }
  if (confirmBtn) {
    confirmBtn.addEventListener('click', confirmRemoveSeller);
  }

  // Close on outside click
  window.addEventListener('click', e => {
    const modal = document.getElementById('removeSellerConfirmModal');
    if (modal && e.target === modal) {
      closeRemoveSellerConfirmation();
    }
  });

  // Expose globally
  window.openRemoveSellerConfirmation  = openRemoveSellerConfirmation;
  window.closeRemoveSellerConfirmation = closeRemoveSellerConfirmation;
  window.confirmRemoveSeller          = confirmRemoveSeller;
});