/**
 * Close Bid Confirmation Modal
 * Handles confirmation dialog for closing/canceling bids
 */

let pendingCloseBidId = null;

function openCloseBidConfirmModal(bidId) {
  pendingCloseBidId = bidId;
  const modal = document.getElementById('closeBidConfirmModal');
  if (modal) {
    modal.style.display = 'flex';
  }
}

function closeCloseBidConfirmModal() {
  pendingCloseBidId = null;
  const modal = document.getElementById('closeBidConfirmModal');
  if (modal) {
    modal.style.display = 'none';
  }
}

function confirmCloseBid() {
  if (!pendingCloseBidId) return;

  const bidId = pendingCloseBidId;
  closeCloseBidConfirmModal();

  // Make the fetch request to close the bid
  fetch(`/bids/cancel/${bidId}`, {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  })
    .then(res => {
      if (res.ok) {
        const btn = document.querySelector(`button[onclick="closeBid(${bidId})"]`);
        if (btn) {
          const card = btn.closest('.bid-card');
          if (card) card.remove();
        }
      } else {
        alert('Failed to close bid.');
      }
    })
    .catch(() => alert('Something went wrong.'));
}

// Make functions globally available
window.openCloseBidConfirmModal = openCloseBidConfirmModal;
window.closeCloseBidConfirmModal = closeCloseBidConfirmModal;
window.confirmCloseBid = confirmCloseBid;
