// orders_tab.js
// placeholder for any Orders-specific JS

// REMOVED: Delivery address button click handlers
// The delivery address feature has been removed from the Orders tab
/*
document.addEventListener('DOMContentLoaded', () => {
  // Setup delivery address button click handlers
  document.querySelectorAll('.delivery-address-btn').forEach(btn => {
    btn.addEventListener('click', function() {
      const orderId = parseInt(this.dataset.orderId);
      const deliveryAddressJson = this.dataset.deliveryAddress;
      const orderDate = this.dataset.orderDate;

      openOrderDeliveryAddressModal(orderId, deliveryAddressJson, orderDate);
    });
  });
});
*/

// orders_tab.js
function openOrderSellerPopup(orderId) {
  fetch(`/orders/api/${orderId}/order_sellers`)
    .then(res => {
      if (!res.ok) throw new Error("Could not load sellers");
      return res.json();
    })
    .then(data => {
      // reuse the cart_sellers_modal rendering logic
      sellerData   = data;
      currentIndex = 0;
      renderSeller();
      const modal = document.getElementById('orderSellersModal');
      modal.style.display = 'block';
      modal.addEventListener('click', outsideClickListener);
    })
    .catch(err => {
      console.error(err);
      alert(err.message);
    });
}

// expose globally
window.openOrderSellerPopup = openOrderSellerPopup;

// Portfolio toggle function
function toggleOrderPortfolio(orderId, excludedCount) {
  // If excludedCount > 0, the order is excluded, so we re-include it
  // If excludedCount === 0, the order is included, button is disabled so this shouldn't be called

  if (excludedCount === 0) {
    return; // Button is disabled, shouldn't happen
  }

  // Re-include the order in portfolio (remove all exclusions for this order)
  fetch(`/account/api/orders/${orderId}/portfolio/include`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    }
  })
    .then(res => {
      if (!res.ok) throw new Error("Could not update portfolio inclusion");
      return res.json();
    })
    .then(data => {
      if (data.success) {
        // Reload the page to refresh the order data
        location.reload();
      } else {
        alert(data.error || 'Failed to update portfolio inclusion');
      }
    })
    .catch(err => {
      console.error(err);
      alert(err.message);
    });
}

// REMOVED: Delivery address modal functions
// The delivery address feature has been removed from the Orders tab
/*
let currentOrderId = null;
let savedAddresses = [];
let countdownInterval = null;

function openOrderDeliveryAddressModal(orderId, deliveryAddressJson, orderDate) {
  currentOrderId = orderId;

  // Parse the delivery address if it's a string
  let deliveryAddress = null;
  if (deliveryAddressJson && deliveryAddressJson !== 'null' && deliveryAddressJson !== 'None') {
    try {
      deliveryAddress = JSON.parse(deliveryAddressJson);
    } catch (e) {
      // If it's not JSON, treat it as a plain string
      deliveryAddress = deliveryAddressJson;
    }
  }

  // Display current address
  const addressDisplay = document.getElementById('currentDeliveryAddress');
  if (deliveryAddress) {
    if (typeof deliveryAddress === 'string') {
      // Plain text address - split by newline or comma
      const lines = deliveryAddress.includes('\n') ? deliveryAddress.split('\n') : deliveryAddress.split(',');
      addressDisplay.innerHTML = lines.map(line =>
        `<div>${line.trim()}</div>`
      ).join('');
    } else if (typeof deliveryAddress === 'object') {
      // Structured address object
      addressDisplay.innerHTML = `
        ${deliveryAddress.name ? `<div><strong>${deliveryAddress.name}</strong></div>` : ''}
        <div>${deliveryAddress.street || ''}</div>
        ${deliveryAddress.street_line2 ? `<div>${deliveryAddress.street_line2}</div>` : ''}
        <div>${deliveryAddress.city || ''}, ${deliveryAddress.state || ''} ${deliveryAddress.zip_code || ''}</div>
        ${deliveryAddress.country ? `<div>${deliveryAddress.country}</div>` : ''}
      `;
    }
  } else {
    addressDisplay.innerHTML = '<div style="color: #6b7280; font-style: italic;">No delivery address set for this order</div>';
  }

  // Calculate time remaining for address changes (24 hours from order creation)
  const orderCreatedAt = new Date(orderDate);
  const now = new Date();
  const hoursElapsed = (now - orderCreatedAt) / (1000 * 60 * 60);
  const canChangeAddress = hoursElapsed < 24;

  // Update countdown timer and enable/disable controls
  updateCountdownTimer(orderCreatedAt, canChangeAddress);

  // Load saved addresses
  loadSavedAddresses(canChangeAddress);

  // Show modal
  const modal = document.getElementById('orderDeliveryAddressModal');
  modal.style.display = 'block';

  // Close modal on outside click
  modal.addEventListener('click', function(event) {
    if (event.target === modal) {
      closeOrderDeliveryAddressModal();
    }
  });
}

function updateCountdownTimer(orderCreatedAt, canChangeAddress) {
  const countdownElement = document.getElementById('addressChangeCountdown');
  const savedAddressesSection = document.getElementById('savedAddressesSection');
  const addAddressSection = document.getElementById('addAddressSection');

  // Clear any existing interval
  if (countdownInterval) {
    clearInterval(countdownInterval);
  }

  if (canChangeAddress) {
    // Calculate and display countdown
    const updateCountdown = () => {
      const now = new Date();
      const deadline = new Date(orderCreatedAt.getTime() + 24 * 60 * 60 * 1000);
      const timeRemaining = deadline - now;

      if (timeRemaining <= 0) {
        countdownElement.innerHTML = '<div class="countdown-expired">Delivery address can no longer be changed for this order.</div>';
        if (savedAddressesSection) savedAddressesSection.style.display = 'none';
        if (addAddressSection) addAddressSection.style.display = 'none';
        clearInterval(countdownInterval);
      } else {
        const hours = Math.floor(timeRemaining / (1000 * 60 * 60));
        const minutes = Math.floor((timeRemaining % (1000 * 60 * 60)) / (1000 * 60));
        countdownElement.innerHTML = `<div class="countdown-active"><i class="fas fa-clock"></i> Address changes allowed for: ${hours} hours ${minutes} minutes</div>`;
        if (savedAddressesSection) savedAddressesSection.style.display = 'block';
        if (addAddressSection) addAddressSection.style.display = 'block';
      }
    };

    updateCountdown();
    countdownInterval = setInterval(updateCountdown, 60000); // Update every minute
  } else {
    // Past 24 hours - disable all controls
    countdownElement.innerHTML = '<div class="countdown-expired">Delivery address can no longer be changed for this order.</div>';
    if (savedAddressesSection) savedAddressesSection.style.display = 'none';
    if (addAddressSection) addAddressSection.style.display = 'none';
  }
}

function loadSavedAddresses(canChangeAddress) {
  fetch('/account/api/addresses')
    .then(res => res.json())
    .then(data => {
      savedAddresses = data.addresses || [];
      renderSavedAddresses(canChangeAddress);
    })
    .catch(err => {
      console.error('Failed to load saved addresses:', err);
      document.getElementById('savedAddressesList').innerHTML =
        '<div style="color: #ef4444; padding: 12px;">Failed to load saved addresses</div>';
    });
}

function renderSavedAddresses(canChangeAddress) {
  const container = document.getElementById('savedAddressesList');

  if (savedAddresses.length === 0) {
    container.innerHTML = '<div style="color: #6b7280; padding: 12px; font-style: italic;">No saved addresses yet</div>';
    return;
  }

  container.innerHTML = savedAddresses.map(addr => `
    <div class="saved-address-item ${!canChangeAddress ? 'disabled' : ''}" ${canChangeAddress ? `onclick="selectSavedAddress(${addr.id})"` : ''}>
      <div class="address-label">${addr.name || 'Address'}</div>
      <div class="address-details">
        <div>${addr.street || ''}</div>
        ${addr.street_line2 ? `<div>${addr.street_line2}</div>` : ''}
        <div>${addr.city || ''}, ${addr.state || ''} ${addr.zip_code || ''}</div>
        ${addr.country ? `<div>${addr.country}</div>` : ''}
      </div>
    </div>
  `).join('');
}

function selectSavedAddress(addressId) {
  // Find the selected address
  const selectedAddress = savedAddresses.find(addr => addr.id === addressId);
  if (!selectedAddress) {
    alert('Address not found');
    return;
  }

  // Update order delivery address
  fetch(`/account/api/orders/${currentOrderId}/delivery-address`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      address_id: addressId
    })
  })
    .then(res => {
      if (!res.ok) throw new Error('Failed to update delivery address');
      return res.json();
    })
    .then(data => {
      if (data.success) {
        // Update the current address display immediately
        const addressDisplay = document.getElementById('currentDeliveryAddress');
        if (addressDisplay && data.updated_address) {
          const addr = data.updated_address;
          addressDisplay.innerHTML = `
            ${addr.name ? `<div><strong>${addr.name}</strong></div>` : ''}
            <div>${addr.street || ''}</div>
            ${addr.street_line2 ? `<div>${addr.street_line2}</div>` : ''}
            <div>${addr.city || ''}, ${addr.state || ''} ${addr.zip_code || ''}</div>
            ${addr.country ? `<div>${addr.country}</div>` : ''}
          `;
        }

        // Show warning banner
        const warningBanner = document.getElementById('addressChangeWarning');
        if (warningBanner) {
          warningBanner.style.display = 'block';
        }

        // Show success modal after a brief delay
        setTimeout(() => {
          closeOrderDeliveryAddressModal();
          openAddressChangeSuccessModal();
        }, 2000);
      } else {
        alert(data.error || 'Failed to update delivery address');
      }
    })
    .catch(err => {
      console.error(err);
      alert(err.message);
    });
}

function closeOrderDeliveryAddressModal() {
  const modal = document.getElementById('orderDeliveryAddressModal');
  modal.style.display = 'none';
  currentOrderId = null;

  // Clear countdown interval
  if (countdownInterval) {
    clearInterval(countdownInterval);
    countdownInterval = null;
  }

  // Hide warning banner
  const warningBanner = document.getElementById('addressChangeWarning');
  if (warningBanner) {
    warningBanner.style.display = 'none';
  }
}

function openAddressModalForOrder() {
  // Close the delivery address modal
  closeOrderDeliveryAddressModal();

  // Open the existing address modal (from address_modal.html)
  // This assumes the address modal exists and has an openAddAddressModal function
  if (typeof openAddAddressModal === 'function') {
    openAddAddressModal();
  } else {
    alert('Address form not available. Please add address from Account Details tab.');
  }
}

// Address Change Success Modal
function openAddressChangeSuccessModal() {
  const modal = document.getElementById('addressChangeSuccessModal');
  if (modal) {
    modal.style.display = 'block';
  }
}

function closeAddressChangeSuccessModal() {
  const modal = document.getElementById('addressChangeSuccessModal');
  if (modal) {
    modal.style.display = 'none';
  }
  // Reload the page to show updated address
  location.reload();
}
*/
// END REMOVED: Delivery address modal functions

// Expose functions globally
window.toggleOrderPortfolio = toggleOrderPortfolio;
// REMOVED: Delivery address modal functions
// window.openOrderDeliveryAddressModal = openOrderDeliveryAddressModal;
// window.closeOrderDeliveryAddressModal = closeOrderDeliveryAddressModal;
// window.selectSavedAddress = selectSavedAddress;
// window.openAddressModalForOrder = openAddressModalForOrder;
// window.closeAddressChangeSuccessModal = closeAddressChangeSuccessModal;
