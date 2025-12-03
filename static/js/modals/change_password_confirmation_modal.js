/**
 * Change Password Confirmation Modal
 * Handles confirmation dialog for changing password
 */

let pendingPasswordFormData = null;

function openChangePasswordConfirmModal(formData) {
  pendingPasswordFormData = formData;
  const modal = document.getElementById('changePasswordConfirmModal');
  if (modal) {
    modal.style.display = 'flex';
  }
}

function closeChangePasswordConfirmModal() {
  pendingPasswordFormData = null;
  const modal = document.getElementById('changePasswordConfirmModal');
  if (modal) {
    modal.style.display = 'none';
  }
}

function confirmChangePassword() {
  if (!pendingPasswordFormData) return;

  const formData = pendingPasswordFormData;
  closeChangePasswordConfirmModal();

  fetch('/account/change_password', {
    method: 'POST',
    body: formData
  })
  .then(resp => resp.json())
  .then(data => {
    if (data.success) {
      // Password changed successfully - just reset the form
      document.getElementById('securityForm').reset();
      // Optionally reload the page to ensure fresh state
      location.reload();
    } else {
      // Show error modal instead of browser alert
      openErrorNotificationModal(data.message || 'Failed to change password');
    }
  })
  .catch(err => {
    console.error('Error:', err);
    openErrorNotificationModal('Failed to change password. Please try again.');
  });
}

// Make functions globally available
window.openChangePasswordConfirmModal = openChangePasswordConfirmModal;
window.closeChangePasswordConfirmModal = closeChangePasswordConfirmModal;
window.confirmChangePassword = confirmChangePassword;
