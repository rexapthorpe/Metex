/**
 * Account Details Tab JavaScript
 * Handles section switching and form submissions
 */

// Switch between sections inside Account Details
function showDetailsSection(sectionName) {
  // Hide all sections
  document.querySelectorAll('.details-section').forEach(section => {
    section.classList.remove('active');
  });

  // Show selected section
  const section = document.getElementById(`section-${sectionName}`);
  if (section) {
    section.classList.add('active');
  }

  // Update active state on secondary sidebar items
  document.querySelectorAll('.account-secondary-sidebar li').forEach(item => {
    item.classList.remove('active');
    const onclick = item.getAttribute('onclick') || '';
    if (onclick.includes(`'${sectionName}'`)) {
      item.classList.add('active');
    }
  });
}

// Make it globally accessible
window.showDetailsSection = showDetailsSection;

// Form wiring
document.addEventListener('DOMContentLoaded', () => {
  const personalForm = document.getElementById('personalInfoForm');
  if (personalForm) {
    personalForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const formData = new FormData(personalForm);

      fetch('/account/update_personal_info', {
        method: 'POST',
        body: formData
      })
      .then(resp => resp.json())
      .then(data => {
        if (data.success) {
          // Show custom confirmation modal
          openPersonalInfoSaveModal();
        } else {
          alert('Error: ' + (data.message || 'Failed to update'));
        }
      })
      .catch(err => {
        console.error('Error:', err);
        alert('Failed to update personal information');
      });
    });
  }

  const securityForm = document.getElementById('securityForm');
  if (securityForm) {
    securityForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const formData = new FormData(securityForm);

      const newPass = formData.get('new_password');
      const confirmPass = formData.get('confirm_password');

      if (newPass !== confirmPass) {
        // Show error modal instead of browser alert
        openErrorNotificationModal('New passwords do not match!', 'Password Mismatch');
        return;
      }

      // Open confirmation modal instead of submitting directly
      openChangePasswordConfirmModal(formData);
    });
  }

});

// Delete address function (add/edit handled by address_modal.js)
function deleteAddress(addressId) {
  // Open confirmation modal instead of using browser confirm()
  openDeleteAddressConfirmModal(addressId);
}

// Make deleteAddress globally available
window.deleteAddress = deleteAddress;

// Personal Info Save Modal functions
function openPersonalInfoSaveModal() {
  const modal = document.getElementById('personalInfoSaveModal');
  if (modal) {
    modal.style.display = 'flex';
  }
}

function closePersonalInfoSaveModal() {
  const modal = document.getElementById('personalInfoSaveModal');
  if (modal) {
    modal.style.display = 'none';
  }
  // Reload page to show updated information
  location.reload();
}

// Make modal functions globally available
window.openPersonalInfoSaveModal = openPersonalInfoSaveModal;
window.closePersonalInfoSaveModal = closePersonalInfoSaveModal;

// ===== Notification Settings =====

// Auto-save notification preferences when toggles are changed
function setupNotificationToggles() {
  const toggleIds = [
    'email_listing_sold',
    'email_bid_filled',
    'inapp_listing_sold',
    'inapp_bid_filled'
  ];

  toggleIds.forEach(id => {
    const toggle = document.getElementById(id);
    if (toggle) {
      toggle.addEventListener('change', saveNotificationPreferences);
    }
  });
}

// Save notification preferences to backend
function saveNotificationPreferences() {
  const preferences = {
    email_listing_sold: document.getElementById('email_listing_sold')?.checked || false,
    email_bid_filled: document.getElementById('email_bid_filled')?.checked || false,
    inapp_listing_sold: document.getElementById('inapp_listing_sold')?.checked || false,
    inapp_bid_filled: document.getElementById('inapp_bid_filled')?.checked || false
  };

  fetch('/account/update_preferences', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(preferences)
  })
  .then(resp => resp.json())
  .then(data => {
    if (data.success) {
      showNotificationSaveStatus();
    } else {
      console.error('Failed to save preferences:', data.message);
      alert('Failed to save notification preferences. Please try again.');
    }
  })
  .catch(err => {
    console.error('Error saving preferences:', err);
    alert('Failed to save notification preferences. Please try again.');
  });
}

// Show "Preferences saved" status message
function showNotificationSaveStatus() {
  const statusDiv = document.getElementById('notificationSaveStatus');
  if (statusDiv) {
    statusDiv.style.display = 'flex';

    // Hide after 3 seconds
    setTimeout(() => {
      statusDiv.style.display = 'none';
    }, 3000);
  }
}

// Initialize notification toggles when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  setupNotificationToggles();
});
