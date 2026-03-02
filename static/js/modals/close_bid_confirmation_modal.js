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
  if (modal) modal.style.display = 'none';

  // Reset animation state so it replays on next open
  const content = document.getElementById('closeBidConfirmContent');
  const anim    = document.getElementById('closeBidSuccessAnim');
  const closeBtn = document.getElementById('closeBidConfirmCloseBtn');
  if (content)  content.style.display  = '';
  if (closeBtn) closeBtn.style.display = '';
  if (anim) {
    anim.style.display = 'none';
    // Force animation restart by toggling animation off/on
    anim.querySelectorAll('.bid-closed-circle, .bid-closed-check, .bid-closed-label').forEach(el => {
      el.style.animation = 'none';
      el.getBoundingClientRect(); // trigger reflow
      el.style.animation = '';
    });
  }
}

function confirmCloseBid() {
  if (!pendingCloseBidId) return;

  const bidId   = pendingCloseBidId;
  const content = document.getElementById('closeBidConfirmContent');
  const anim    = document.getElementById('closeBidSuccessAnim');
  const closeBtn = document.getElementById('closeBidConfirmCloseBtn');

  fetch(`/bids/cancel/${bidId}`, {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  })
    .then(res => {
      if (res.ok) {
        // Show animation in place of the confirm content
        if (content)  content.style.display  = 'none';
        if (closeBtn) closeBtn.style.display  = 'none';
        if (anim)     anim.style.display      = 'flex';

        // After animation completes, close modal and remove bid card
        setTimeout(() => {
          closeCloseBidConfirmModal();
          const btn = document.querySelector(`button[onclick="closeBid(${bidId})"]`);
          if (btn) {
            const card = btn.closest('.bid-card');
            if (card) card.remove();
          }
        }, 1400);
      } else {
        alert('Failed to close bid.');
      }
    })
    .catch(() => alert('Something went wrong.'));
}

// Make functions globally available
window.openCloseBidConfirmModal  = openCloseBidConfirmModal;
window.closeCloseBidConfirmModal = closeCloseBidConfirmModal;
window.confirmCloseBid           = confirmCloseBid;
