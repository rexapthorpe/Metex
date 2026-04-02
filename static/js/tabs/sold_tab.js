// sold_tab.js

// placeholder for future sold-tab behaviors
document.addEventListener('DOMContentLoaded', () => {
  // e.g. wire up tracking modals, etc.
});

// open the existing message modal, but fetch buyers instead of sellers
function openMessageModalForBuyer(orderId) {
  currentOrderId = orderId;
  fetch(`/orders/api/${orderId}/message_buyers`)
    .then(res => res.json())
    .then(data => {
      // map buyers into the modal's expected structure (participant_id + username)
      messageSellers = data.map(item => ({
        seller_id: item.buyer_id,
        username: item.username
      }));
      currentIndex = 0;
      renderConversation();
      document.getElementById('messageModal').style.display = 'block';
    })
    .catch(console.error);
}
// expose globally for HTML onclick
window.openMessageModalForBuyer = openMessageModalForBuyer;

/**
 * Null-safe wrapper for getElementById + textContent assignment.
 * Silently no-ops if the element doesn't exist.
 */
function _setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

// Phase 0A: grading removed — these are no-op stubs so any cached/old pages
// that still reference these functions don't throw JS errors.
function openGradingInstructionsModal(buttonElement) { /* grading deactivated */ }
function submitGradingTracking() { /* grading deactivated */ }
function closeGradingInstructionsModal() { /* grading deactivated */ }
function closeGradingInstructionsModalOnOverlayClick(event) { /* grading deactivated */ }
}

/**
 * Parses the buyer address string into components
 * Format: "Street • [Street2 •] City, State ZIP"
 * @param {string} addressRaw - The raw address string
 * @returns {object} Parsed address components
 */
function parseBuyerAddress(addressRaw) {
  const parsed = {
    street: '',
    street2: '',
    city: '',
    state: '',
    zip: ''
  };

  if (!addressRaw || addressRaw.trim() === '') {
    return parsed;
  }

  // Split by bullet points
  const parts = addressRaw.split('•').map(p => p.trim());

  if (parts.length >= 1) {
    parsed.street = parts[0];
  }

  let cityStateZip = '';

  if (parts.length === 3) {
    // Format: street • street2 • city,state zip
    parsed.street2 = parts[1];
    cityStateZip = parts[2];
  } else if (parts.length === 2) {
    // Format: street • city,state zip
    cityStateZip = parts[1];
  } else if (parts.length === 1) {
    // No bullet points, try to parse as is
    cityStateZip = parts[0];
  }

  // Parse "City, State ZIP"
  if (cityStateZip.includes(',')) {
    const cityParts = cityStateZip.split(',');
    parsed.city = cityParts[0].trim();

    if (cityParts.length > 1) {
      const stateZip = cityParts[1].trim().split(/\s+/);
      if (stateZip.length >= 1) {
        parsed.state = stateZip[0];
      }
      if (stateZip.length >= 2) {
        parsed.zip = stateZip[1];
      }
    }
  }

  return parsed;
}

// Expose functions globally for HTML onclick
window.openGradingInstructionsModal = openGradingInstructionsModal;
window.closeGradingInstructionsModal = closeGradingInstructionsModal;
window.closeGradingInstructionsModalOnOverlayClick = closeGradingInstructionsModalOnOverlayClick;
window.submitGradingTracking = submitGradingTracking;