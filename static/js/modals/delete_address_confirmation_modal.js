/**
 * Delete Address Confirmation Modal
 * Handles confirmation dialog for deleting shipping addresses
 */

let pendingDeleteAddressId = null;

function openDeleteAddressConfirmModal(addressId) {
  pendingDeleteAddressId = addressId;
  const modal = document.getElementById('deleteAddressConfirmModal');
  if (modal) {
    modal.style.display = 'flex';
  }
}

function closeDeleteAddressConfirmModal() {
  pendingDeleteAddressId = null;
  const modal = document.getElementById('deleteAddressConfirmModal');
  if (modal) {
    modal.style.display = 'none';
  }
}

function confirmDeleteAddress() {
  if (!pendingDeleteAddressId) return;

  const addressId = pendingDeleteAddressId;
  closeDeleteAddressConfirmModal();

  fetch(`/account/delete_address/${addressId}`, {
    method: 'POST'
  })
  .then(resp => resp.json())
  .then(data => {
    if (data.success) {
      location.reload();
    } else {
      alert('Error: ' + (data.message || 'Failed to delete'));
    }
  })
  .catch(err => {
    console.error('Error:', err);
    alert('Failed to delete address');
  });
}

// Make functions globally available
window.openDeleteAddressConfirmModal = openDeleteAddressConfirmModal;
window.closeDeleteAddressConfirmModal = closeDeleteAddressConfirmModal;
window.confirmDeleteAddress = confirmDeleteAddress;
