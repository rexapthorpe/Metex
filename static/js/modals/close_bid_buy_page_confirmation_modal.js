/**
 * Close Bid Buy Page Confirmation Modal
 * Handles confirmation dialog for closing/canceling bids from the buy page
 */

let pendingCloseBidAction = null;

function openCloseBidBuyPageConfirmModal(form) {
  // Store only the pathname (relative URL) to avoid protocol-upgrade issues
  // from the CSP upgrade-insecure-requests directive on HTTP dev servers.
  try {
    pendingCloseBidAction = new URL(form.action).pathname;
  } catch (_) {
    pendingCloseBidAction = form.action;
  }
  const modal = document.getElementById('closeBidBuyPageConfirmModal');
  if (modal) {
    modal.style.display = 'flex';
  }
}

function closeCloseBidBuyPageConfirmModal() {
  pendingCloseBidAction = null;
  const modal = document.getElementById('closeBidBuyPageConfirmModal');
  if (modal) window.animatedModalClose(modal, function() { modal.style.display = 'none'; });

  // Reset animation state so it replays on next open
  const content  = document.getElementById('closeBidBuyPageConfirmContent');
  const anim     = document.getElementById('closeBidBuyPageSuccessAnim');
  const closeBtn = document.getElementById('closeBidBuyPageConfirmCloseBtn');
  if (content)  content.style.display  = '';
  if (closeBtn) closeBtn.style.display = '';
  if (anim) {
    anim.style.display = 'none';
    anim.querySelectorAll('.bid-closed-circle, .bid-closed-check, .bid-closed-label').forEach(el => {
      el.style.animation = 'none';
      el.getBoundingClientRect(); // trigger reflow
      el.style.animation = '';
    });
  }
}

function confirmCloseBidBuyPage() {
  if (!pendingCloseBidAction) return;

  const actionUrl = pendingCloseBidAction;
  const content   = document.getElementById('closeBidBuyPageConfirmContent');
  const anim      = document.getElementById('closeBidBuyPageSuccessAnim');
  const closeBtn  = document.getElementById('closeBidBuyPageConfirmCloseBtn');

  fetch(actionUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'X-Requested-With': 'XMLHttpRequest'
    }
  })
  .then(resp => {
    if (resp.ok) {
      // Show animation in place of the confirm content
      if (content)  content.style.display  = 'none';
      if (closeBtn) closeBtn.style.display  = 'none';
      if (anim)     anim.style.display      = 'flex';

      // After animation completes, close modal and reload page
      setTimeout(() => {
        closeCloseBidBuyPageConfirmModal();
        window.location.reload();
      }, 1400);
    } else {
      if (window.openErrorNotificationModal) {
        openErrorNotificationModal('Failed to close bid. Please try again.', 'Error');
      } else {
        alert('Failed to close bid.');
      }
    }
  })
  .catch(err => {
    console.error('Error closing bid:', err);
    if (window.openErrorNotificationModal) {
      openErrorNotificationModal('Something went wrong. Please try again.', 'Error');
    } else {
      alert('Something went wrong.');
    }
  });
}

// Make functions globally available
window.openCloseBidBuyPageConfirmModal  = openCloseBidBuyPageConfirmModal;
window.closeCloseBidBuyPageConfirmModal = closeCloseBidBuyPageConfirmModal;
window.confirmCloseBidBuyPage           = confirmCloseBidBuyPage;
