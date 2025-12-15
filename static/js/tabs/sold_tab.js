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
 * Opens the Grading Instructions modal and populates it with order data
 * @param {HTMLElement} buttonElement - The button element that was clicked
 */
function openGradingInstructionsModal(buttonElement) {
  // Extract data from button's data attributes
  const orderId = buttonElement.dataset.orderId;
  const itemDescription = buttonElement.dataset.itemDescription;
  const quantity = buttonElement.dataset.quantity;
  const gradingService = buttonElement.dataset.gradingService;
  const serviceName = buttonElement.dataset.serviceName;
  const serviceLine1 = buttonElement.dataset.serviceLine1;
  const serviceLine2 = buttonElement.dataset.serviceLine2;
  const serviceCity = buttonElement.dataset.serviceCity;
  const serviceState = buttonElement.dataset.serviceState;
  const serviceZip = buttonElement.dataset.serviceZip;
  const buyerName = buttonElement.dataset.buyerName;
  const buyerAddressRaw = buttonElement.dataset.buyerAddress;

  // Parse buyer address (format: "Street • [Street2 •] City, State ZIP")
  const buyerAddress = parseBuyerAddress(buyerAddressRaw);

  // Populate modal fields
  // Order ID (appears in multiple places)
  const orderIdElements = document.querySelectorAll('#grading-order-id, #grading-order-id-copy');
  orderIdElements.forEach(el => el.textContent = orderId);

  // Item description
  document.getElementById('grading-item-description').textContent = itemDescription || '—';
  document.getElementById('grading-item-description-copy').textContent = itemDescription || '—';

  // Quantity
  document.getElementById('grading-quantity').textContent = quantity || '—';

  // Grading service address
  document.getElementById('grading-service-name').textContent = serviceName || '—';
  document.getElementById('grading-service-line1').textContent = serviceLine1 || '—';

  const line2Element = document.getElementById('grading-service-line2');
  if (serviceLine2 && serviceLine2.trim() !== '') {
    line2Element.textContent = serviceLine2;
    line2Element.style.display = '';
  } else {
    line2Element.style.display = 'none';
  }

  document.getElementById('grading-service-city').textContent = serviceCity || '—';
  document.getElementById('grading-service-state').textContent = serviceState || '—';
  document.getElementById('grading-service-zip').textContent = serviceZip || '—';

  // Buyer information
  document.getElementById('buyer-name').textContent = buyerName || '—';
  document.getElementById('buyer-name-copy').textContent = buyerName || '—';

  document.getElementById('buyer-address-line1').textContent = buyerAddress.street || '—';

  const buyerLine2Element = document.getElementById('buyer-address-line2');
  if (buyerAddress.street2 && buyerAddress.street2.trim() !== '') {
    buyerLine2Element.textContent = buyerAddress.street2;
    buyerLine2Element.style.display = '';
  } else {
    buyerLine2Element.style.display = 'none';
  }

  document.getElementById('buyer-city').textContent = buyerAddress.city || '—';
  document.getElementById('buyer-state').textContent = buyerAddress.state || '—';
  document.getElementById('buyer-zip').textContent = buyerAddress.zip || '—';

  // Show the modal with animation (matching buy modal pattern)
  const modal = document.getElementById('gradingInstructionsModal');
  modal.style.display = 'flex';
  requestAnimationFrame(() => {
    modal.classList.add('active');
  });
}

/**
 * Closes the Grading Instructions modal
 */
function closeGradingInstructionsModal() {
  const modal = document.getElementById('gradingInstructionsModal');
  if (!modal) return;

  // Remove active class for transition, then hide after animation
  modal.classList.remove('active');
  setTimeout(() => {
    modal.style.display = 'none';
  }, 300); // Match CSS transition duration
}

/**
 * Closes the modal when clicking on the overlay background (not the dialog itself)
 * @param {Event} event - Click event
 */
function closeGradingInstructionsModalOnOverlayClick(event) {
  // Only close if the click was directly on the overlay, not on child elements
  if (event.target.id === 'gradingInstructionsModal') {
    closeGradingInstructionsModal();
  }
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