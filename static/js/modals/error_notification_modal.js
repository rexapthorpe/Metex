/**
 * Error Notification Modal
 * Generic modal for displaying error messages
 */

function openErrorNotificationModal(message, title = 'Error') {
  const modal = document.getElementById('errorNotificationModal');
  const titleEl = document.getElementById('errorNotificationTitle');
  const messageEl = document.getElementById('errorNotificationMessage');

  if (modal && titleEl && messageEl) {
    titleEl.textContent = title;
    messageEl.textContent = message;
    modal.style.display = 'flex';
  }
}

function closeErrorNotificationModal() {
  const modal = document.getElementById('errorNotificationModal');
  if (modal) {
    modal.style.display = 'none';
  }
}

// Make functions globally available
window.openErrorNotificationModal = openErrorNotificationModal;
window.closeErrorNotificationModal = closeErrorNotificationModal;
