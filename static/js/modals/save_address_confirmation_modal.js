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

      // Check if we're being called from Buy Item modal
      // If so, call the callback instead of reloading
      if (typeof window.onAddressSavedFromBuyModal === 'function') {
        console.log('[SaveAddressModal] Calling onAddressSavedFromBuyModal callback');

        // For new addresses, we need to fetch the newly created address ID
        // Since the backend doesn't return it, we'll fetch all addresses and select the last one
        if (!addressId) {
          // New address was created - fetch addresses to get the new ID
          fetch('/account/get_addresses')
            .then(res => res.json())
            .then(addrData => {
              if (addrData.success && addrData.addresses && addrData.addresses.length > 0) {
                // Get the last address (most recently created)
                const newAddress = addrData.addresses[addrData.addresses.length - 1];
                window.onAddressSavedFromBuyModal(newAddress.id);
              } else {
                // Fallback: just refresh without specific ID
                window.onAddressSavedFromBuyModal(null);
              }
            })
            .catch(err => {
              console.error('Error fetching new address:', err);
              window.onAddressSavedFromBuyModal(null);
            });
        } else {
          // Edited existing address - use its ID
          window.onAddressSavedFromBuyModal(parseInt(addressId));
        }
      } else {
        // Not from Buy Item modal - reload page as before
        location.reload();
      }
    } else {
      alert('Error: ' + (data.message || 'Failed to save address'));
    }
  })
  .catch(err => {
    console.error('Error:', err);
    alert('Failed to save address');
  });
}

// Close confirmation modal on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    const confirmModal = document.getElementById('saveAddressConfirmModal');
    if (confirmModal && confirmModal.style.display === 'flex') {
      closeSaveAddressConfirmModal();
    }
  }
});

// Make functions globally available
window.openSaveAddressConfirmModal = openSaveAddressConfirmModal;
window.closeSaveAddressConfirmModal = closeSaveAddressConfirmModal;
window.confirmSaveAddress = confirmSaveAddress;
