/**
 * Close Bid Buy Page Confirmation Modal
 * Handles confirmation dialog for closing/canceling bids from the buy page
 */

let pendingCloseBidAction = null;

function openCloseBidBuyPageConfirmModal(form) {
  // Store the form's action URL for submission
  pendingCloseBidAction = form.action;
  const modal = document.getElementById('closeBidBuyPageConfirmModal');
  if (modal) {
    modal.style.display = 'flex';
  }
}

function closeCloseBidBuyPageConfirmModal() {
  pendingCloseBidAction = null;
  const modal = document.getElementById('closeBidBuyPageConfirmModal');
  if (modal) {
    modal.style.display = 'none';
  }
}

function confirmCloseBidBuyPage() {
  if (!pendingCloseBidAction) return;

  const actionUrl = pendingCloseBidAction;
  closeCloseBidBuyPageConfirmModal();

  // Submit using fetch to avoid form submission issues
  fetch(actionUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    }
  })
  .then(resp => {
    if (resp.ok) {
      // Reload the page to show the updated bid list
      window.location.reload();
    } else {
      // Show error modal if available, otherwise use alert
      if (window.openErrorNotificationModal) {
        openErrorNotificationModal('Failed to close bid. Please try again.', 'Error');
      } else {
        alert('Failed to close bid.');
      }
    }
  })
  .catch(err => {
    console.error('Error closing bid:', err);
    // Show error modal if available, otherwise use alert
    if (window.openErrorNotificationModal) {
      openErrorNotificationModal('Something went wrong. Please try again.', 'Error');
    } else {
      alert('Something went wrong.');
    }
  });
}

// Make functions globally available
window.openCloseBidBuyPageConfirmModal = openCloseBidBuyPageConfirmModal;
window.closeCloseBidBuyPageConfirmModal = closeCloseBidBuyPageConfirmModal;
window.confirmCloseBidBuyPage = confirmCloseBidBuyPage;
