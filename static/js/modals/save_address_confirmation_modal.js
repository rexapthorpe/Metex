/**
 * Save Address Confirmation Modal
 * Handles confirmation dialog for saving address changes
 */

let pendingSaveAddressForm = null;

function openSaveAddressConfirmModal(formData, isEdit) {
  pendingSaveAddressForm = { formData, isEdit };
  const modal = document.getElementById('saveAddressConfirmModal');
  if (modal) {
    modal.style.display = 'flex';
  }
}

function closeSaveAddressConfirmModal() {
  pendingSaveAddressForm = null;
  const modal = document.getElementById('saveAddressConfirmModal');
  if (modal) {
    modal.style.display = 'none';
  }
}

function confirmSaveAddress() {
  if (!pendingSaveAddressForm) return;

  const { formData, isEdit } = pendingSaveAddressForm;
  closeSaveAddressConfirmModal();

  const addressId = document.getElementById('addressId').value;
  const url = addressId
    ? `/account/edit_address/${addressId}`
    : '/account/add_address';

  fetch(url, {
    method: 'POST',
    body: formData
  })
  .then(resp => resp.json())
  .then(data => {
    if (data.success) {
      closeAddressModal();
      location.reload(); // Reload to show updated addresses
    } else {
      alert('Error: ' + (data.message || 'Failed to save address'));
    }
  })
  .catch(err => {
    console.error('Error:', err);
    alert('Failed to save address');
  });
}

// Make functions globally available
window.openSaveAddressConfirmModal = openSaveAddressConfirmModal;
window.closeSaveAddressConfirmModal = closeSaveAddressConfirmModal;
window.confirmSaveAddress = confirmSaveAddress;
