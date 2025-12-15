/**
 * Address Modal JavaScript
 * Handles adding and editing shipping addresses
 */

// Open modal for adding a new address
function openAddAddressModal() {
  const modal = document.getElementById('addressModal');
  const title = document.getElementById('addressModalTitle');
  const form = document.getElementById('addressForm');

  // Reset form
  form.reset();
  document.getElementById('addressId').value = '';

  // Set title for adding
  title.textContent = 'Add Shipping Address';

  // Show modal (use flex so centering works)
  modal.style.display = 'flex';

  // Focus on first input for accessibility
  requestAnimationFrame(() => {
    const firstInput = document.getElementById('addressName');
    if (firstInput) {
      firstInput.focus();
    }
  });
}

// Open modal for editing an existing address
function editAddress(addressId) {
  const modal = document.getElementById('addressModal');
  const title = document.getElementById('addressModalTitle');

  // Set title for editing
  title.textContent = 'Edit Shipping Address';

  // Fetch address data
  fetch(`/account/get_address/${addressId}`)
    .then(resp => resp.json())
    .then(data => {
      if (data.success) {
        const addr = data.address;
        document.getElementById('addressId').value = addr.id;
        document.getElementById('addressName').value = addr.name;
        document.getElementById('addressStreet').value = addr.street;
        document.getElementById('addressStreet2').value = addr.street_line2 || '';
        document.getElementById('addressCity').value = addr.city;
        document.getElementById('addressState').value = addr.state;
        document.getElementById('addressZip').value = addr.zip_code;
        document.getElementById('addressCountry').value = addr.country;

        // Show modal (use flex so centering works)
        modal.style.display = 'flex';
      } else {
        alert('Error: ' + (data.message || 'Failed to load address'));
      }
    })
    .catch(err => {
      console.error('Error:', err);
      alert('Failed to load address');
    });
}

// Close the address modal
function closeAddressModal() {
  const modal = document.getElementById('addressModal');
  modal.style.display = 'none';

  // Return focus to Buy Item modal's delivery address dropdown if it exists
  // This ensures proper focus flow when closing address modal from Buy flow
  requestAnimationFrame(() => {
    const deliverySelect = document.getElementById('deliveryAddressSelect');
    if (deliverySelect && deliverySelect.offsetParent !== null) {
      // deliverySelect is visible, so we're in the Buy Item modal flow
      deliverySelect.focus();
    }
  });
}

// Handle form submission
document.addEventListener('DOMContentLoaded', () => {
  const addressForm = document.getElementById('addressForm');
  if (addressForm) {
    addressForm.addEventListener('submit', (e) => {
      e.preventDefault();

      const addressId = document.getElementById('addressId').value;
      const formData = new FormData(addressForm);
      const isEdit = !!addressId;

      // Open confirmation modal instead of submitting directly
      openSaveAddressConfirmModal(formData, isEdit);
    });
  }

  // Close modal when clicking outside
  const modal = document.getElementById('addressModal');
  if (modal) {
    window.addEventListener('click', (event) => {
      if (event.target === modal) {
        closeAddressModal();
      }
    });
  }

  // Close address modal on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const modal = document.getElementById('addressModal');
      const confirmModal = document.getElementById('saveAddressConfirmModal');

      const addressModalOpen = modal && modal.style.display === 'flex';
      const confirmModalOpen = confirmModal && confirmModal.style.display === 'flex';

      // Close address modal if it's open and confirmation modal is NOT open
      if (addressModalOpen && !confirmModalOpen) {
        closeAddressModal();
      }
      // If confirmation modal is open, let it handle the Escape key
    }
  });

  // Check for URL parameter to auto-open address modal
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get('open_address_modal') === 'true') {
    // Remove the parameter from URL without reloading
    window.history.replaceState({}, document.title, '/account');

    // Open the address modal
    openAddAddressModal();
  }
});

// Make functions globally available
window.openAddAddressModal = openAddAddressModal;
window.editAddress = editAddress;
window.closeAddressModal = closeAddressModal;
