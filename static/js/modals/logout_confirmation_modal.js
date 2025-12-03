/**
 * Logout Confirmation Modal
 * Handles confirmation dialog for logging out
 */

function openLogoutConfirmModal() {
  const modal = document.getElementById('logoutConfirmModal');
  if (modal) {
    modal.style.display = 'flex';
  }
}

function closeLogoutConfirmModal() {
  const modal = document.getElementById('logoutConfirmModal');
  if (modal) {
    modal.style.display = 'none';
  }
}

function confirmLogout() {
  closeLogoutConfirmModal();
  // Redirect to logout URL
  window.location.href = '/logout';
}

// Make functions globally available
window.openLogoutConfirmModal = openLogoutConfirmModal;
window.closeLogoutConfirmModal = closeLogoutConfirmModal;
window.confirmLogout = confirmLogout;
