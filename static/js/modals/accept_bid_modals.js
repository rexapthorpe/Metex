// static/js/modals/accept_bid_modals.js
'use strict';

/* ==========================================================================
   Accept Bid Modal Flow
   Two-step process: Confirmation → Success
   ========================================================================== */

let pendingAcceptData = null;

/**
 * Show warning for isolated listings before accepting bids
 * @param {Object|Array} bidsData - Bid data to pass through after confirmation
 * @param {FormData} formData - Form data to pass through
 */
function showIsolatedBidWarning(bidsData, formData) {
  const confirmed = confirm(
    'This is a one-of-a-kind listing. Accepting this bid will close the listing.\n\nDo you want to proceed?'
  );

  if (confirmed) {
    // User confirmed - proceed with normal accept bid flow
    // Call the actual modal opening logic directly
    const bidsArray = Array.isArray(bidsData) ? bidsData : [bidsData];
    pendingAcceptData = { bidsData: bidsArray, formData };

    const modal = document.getElementById('acceptBidConfirmModal');
    if (!modal) return;

    // Get the bids container element
    const bidsContainer = document.getElementById('confirm-bids-container');
    if (!bidsContainer) {
      console.error('Bids container not found in confirmation modal');
      return;
    }

    // Clear previous content
    bidsContainer.innerHTML = '';

    // Populate each bid
    bidsArray.forEach((bidData, index) => {
      const bidderName = bidData.buyer_name || 'Unknown';
      const price = bidData.effective_price || bidData.price_per_coin || 0;
      const quantity = bidData.quantity || 1;
      const total = price * quantity;

      const requiresGrading = bidData.requires_grading;
      const preferredGrader = bidData.preferred_grader;
      let gradingText = 'No 3rd party grading required';

      if (requiresGrading) {
        if (preferredGrader) {
          gradingText = `Requires 3rd party grading (${preferredGrader})`;
        } else {
          gradingText = 'Requires 3rd party grading';
        }
      }

      // Create bid card HTML
      const bidCard = document.createElement('div');
      bidCard.className = 'bid-confirmation-card';
      bidCard.innerHTML = `
        <h3 class="bid-card-header">Bid #${index + 1}</h3>

        <div class="content-container">
          <h4 class="container-subheader">Transaction Details</h4>
          <div class="bid-summary-grid">
            <div class="summary-row">
              <span class="summary-label">Bidder:</span>
              <span class="summary-value">${bidderName}</span>
            </div>
            <div class="summary-row">
              <span class="summary-label">Price per item:</span>
              <span class="summary-value price-highlight">$${price.toFixed(2)} USD</span>
            </div>
            <div class="summary-row">
              <span class="summary-label">Quantity:</span>
              <span class="summary-value">${quantity}</span>
            </div>
            <div class="summary-row">
              <span class="summary-label">Total value:</span>
              <span class="summary-value total-highlight">$${total.toFixed(2)} USD</span>
            </div>
          </div>
        </div>

        <div class="content-container">
          <h4 class="container-subheader">Grading Requirement</h4>
          <div class="grading-requirement">
            <p>${gradingText}</p>
          </div>
        </div>
      `;

      bidsContainer.appendChild(bidCard);
    });

    // Show modal with animation
    modal.style.display = 'flex';
    requestAnimationFrame(() => {
      modal.classList.add('active');
    });
  }
  // If not confirmed, do nothing (user cancelled)
}

/**
 * Open confirmation modal with bid summary
 * ✅ NOW SUPPORTS SINGLE OR MULTIPLE BIDS
 * @param {Object|Array} bidsData - Single bid object OR array of bid objects
 * @param {FormData} formData - Form data to submit
 */
function openAcceptBidConfirmModal(bidsData, formData) {
  // Check if this is an isolated bucket - show warning first
  if (window.bucketIsIsolated) {
    showIsolatedBidWarning(bidsData, formData);
    return;
  }

  // Normalize to array (support both single bid and multiple bids)
  const bidsArray = Array.isArray(bidsData) ? bidsData : [bidsData];

  pendingAcceptData = { bidsData: bidsArray, formData };

  const modal = document.getElementById('acceptBidConfirmModal');
  if (!modal) return;

  // Get the bids container element
  const bidsContainer = document.getElementById('confirm-bids-container');
  if (!bidsContainer) {
    console.error('Bids container not found in confirmation modal');
    return;
  }

  // Clear previous content
  bidsContainer.innerHTML = '';

  // Populate each bid
  bidsArray.forEach((bidData, index) => {
    const bidderName = bidData.buyer_name || 'Unknown';
    // Use effective_price for correct display (handles both fixed and variable bids)
    const price = bidData.effective_price || bidData.price_per_coin || 0;
    const quantity = bidData.quantity || 1;
    const total = price * quantity;

    const requiresGrading = bidData.requires_grading;
    const preferredGrader = bidData.preferred_grader;
    let gradingText = 'No 3rd party grading required';

    if (requiresGrading) {
      if (preferredGrader) {
        gradingText = `Requires 3rd party grading (${preferredGrader})`;
      } else {
        gradingText = 'Requires 3rd party grading';
      }
    }

    // Create bid card HTML
    const bidCard = document.createElement('div');
    bidCard.className = 'bid-confirmation-card';
    bidCard.innerHTML = `
      <h3 class="bid-card-header">Bid #${index + 1}</h3>

      <div class="content-container">
        <h4 class="container-subheader">Transaction Details</h4>
        <div class="bid-summary-grid">
          <div class="summary-row">
            <span class="summary-label">Bidder:</span>
            <span class="summary-value">${bidderName}</span>
          </div>
          <div class="summary-row">
            <span class="summary-label">Price per item:</span>
            <span class="summary-value price-highlight">$${price.toFixed(2)} USD</span>
          </div>
          <div class="summary-row">
            <span class="summary-label">Quantity:</span>
            <span class="summary-value">${quantity}</span>
          </div>
          <div class="summary-row">
            <span class="summary-label">Total value:</span>
            <span class="summary-value total-highlight">$${total.toFixed(2)} USD</span>
          </div>
        </div>
      </div>

      <div class="content-container">
        <h4 class="container-subheader">Grading Requirement</h4>
        <div class="grading-requirement">
          <p>${gradingText}</p>
        </div>
      </div>
    `;

    bidsContainer.appendChild(bidCard);
  });

  // Show modal with animation
  modal.style.display = 'flex';
  requestAnimationFrame(() => {
    modal.classList.add('active');
  });
}

/**
 * Close confirmation modal
 */
function closeAcceptBidConfirmModal() {
  const modal = document.getElementById('acceptBidConfirmModal');
  if (!modal) return;

  modal.classList.remove('active');
  setTimeout(() => {
    modal.style.display = 'none';
    pendingAcceptData = null;
  }, 300);
}

/**
 * Open success modal with order details
 * ✅ NOW SUPPORTS SINGLE OR MULTIPLE ORDERS
 * @param {Object|Array} ordersData - Single order object OR array of order objects
 */
function openAcceptBidSuccessModal(ordersData) {
  // Normalize to array (support both single order and multiple orders)
  const ordersArray = Array.isArray(ordersData) ? ordersData : [ordersData];

  const modal = document.getElementById('acceptBidSuccessModal');
  if (!modal) return;

  // Get the orders container element
  const ordersContainer = document.getElementById('success-orders-container');
  if (!ordersContainer) {
    console.error('Orders container not found in success modal');
    return;
  }

  // Clear previous content
  ordersContainer.innerHTML = '';

  // Populate each order
  ordersArray.forEach((orderData, index) => {
    const buyerName = orderData.buyer_name || 'Unknown';
    // Use effective_price for correct display (handles both fixed and variable bids)
    // Backend sends this as price_per_coin in order_details, which is already the effective price
    const price = orderData.price_per_coin || 0;
    const quantity = orderData.quantity || 1;
    const total = orderData.total_price || (price * quantity);

    // Parse 3rd party grading info
    const requiresGrading = orderData.requires_grading || false;
    const preferredGrader = orderData.preferred_grader || '';

    // Parse delivery address
    let address = orderData.delivery_address || '';
    let street = '';
    let street2 = '';
    let city = '';
    let state = '';
    let zip = '';

    // Handle different address formats
    if (!address || address === 'Not provided') {
      // No address
    } else if (typeof address === 'object') {
      street = address.line1 || address.street || '';
      street2 = address.line2 || address.street2 || '';
      city = address.city || '';
      state = address.state || '';
      zip = address.zip || address.zip_code || '';
    } else if (typeof address === 'string' && address.includes('•')) {
      // Parse bullet-separated format: "Name • Line1 • Line2 • City, State ZIP"
      const addressParts = address.split('•').map(p => p.trim());

      if (addressParts.length >= 2) {
        // First part might be name, or might be line1
        street = addressParts[0];

        // Last part should be city, state, zip
        const lastPart = addressParts[addressParts.length - 1];
        if (lastPart.includes(',')) {
          const cityParts = lastPart.split(',').map(p => p.trim());
          city = cityParts[0] || '';

          if (cityParts.length >= 2) {
            // Parse "State ZIP" from "City, State ZIP"
            const stateZipStr = cityParts[1].trim();
            const stateZipParts = stateZipStr.split(/\s+/);
            state = stateZipParts[0] || '';
            zip = stateZipParts.slice(1).join(' ') || '';
          }
        }

        // Middle parts
        if (addressParts.length === 3) {
          // Format: Line1 • Line2 • City,State ZIP
          street2 = addressParts[1];
        } else if (addressParts.length === 4) {
          // Format: Name • Line1 • Line2 • City,State ZIP
          street = addressParts[1];
          street2 = addressParts[2];
        }
      }
    } else if (typeof address === 'string') {
      street = address;
    }

    // Create order card HTML with THREE SECTIONS
    const orderCard = document.createElement('div');
    orderCard.className = 'order-success-card';
    orderCard.innerHTML = `
      <h3 class="order-card-header">Order #${index + 1}</h3>

      <!-- ✅ SECTION 1: Price Details -->
      <div class="success-section price-details-section">
        <h4 class="section-title">Price Details</h4>
        <div class="section-content">
          <div class="detail-row">
            <span class="detail-label">Price per item:</span>
            <span class="detail-value price-highlight">$${price.toFixed(2)} USD</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Quantity:</span>
            <span class="detail-value">${quantity}</span>
          </div>
          <div class="detail-row total-row">
            <span class="detail-label">Total value:</span>
            <span class="detail-value total-highlight">$${total.toFixed(2)} USD</span>
          </div>
        </div>
      </div>

      <!-- ✅ SECTION 2: Bidder ID (Buyer Information) -->
      <div class="success-section bidder-id-section">
        <h4 class="section-title">Bidder ID</h4>
        <div class="section-content">
          <div class="detail-row">
            <span class="detail-label">Name:</span>
            <span class="detail-value">${buyerName}</span>
          </div>
        </div>
      </div>

      <!-- ✅ SECTION 3: 3rd Party Grading -->
      <div class="success-section grading-section">
        <h4 class="section-title">3rd Party Grading</h4>
        <div class="section-content">
          <div class="detail-row">
            <span class="detail-label">Requires 3rd Party Grading:</span>
            <span class="detail-value">${requiresGrading ? 'Yes' : 'No'}</span>
          </div>
          ${requiresGrading && preferredGrader ? `
            <div class="detail-row">
              <span class="detail-label">Grader:</span>
              <span class="detail-value">${preferredGrader}</span>
            </div>
          ` : ''}
        </div>
      </div>

      <!-- ✅ Delivery Address (with proper label/value rows) -->
      <div class="success-section delivery-address-section">
        <h4 class="section-title">Delivery Address</h4>
        <div class="section-content address-rows">
          <div class="address-row">
            <span class="address-label">Address line 1:</span>
            <span class="address-value">${street || '—'}</span>
          </div>
          <div class="address-row">
            <span class="address-label">Address line 2:</span>
            <span class="address-value">${street2 || '—'}</span>
          </div>
          <div class="address-row">
            <span class="address-label">City:</span>
            <span class="address-value">${city || '—'}</span>
          </div>
          <div class="address-row">
            <span class="address-label">State:</span>
            <span class="address-value">${state || '—'}</span>
          </div>
          <div class="address-row">
            <span class="address-label">Zip code:</span>
            <span class="address-value">${zip || '—'}</span>
          </div>
        </div>
      </div>
    `;

    ordersContainer.appendChild(orderCard);
  });

  // Show modal with animation
  modal.style.display = 'flex';
  requestAnimationFrame(() => {
    modal.classList.add('active');
  });
}

/**
 * Close success modal
 */
function closeAcceptBidSuccessModal() {
  const modal = document.getElementById('acceptBidSuccessModal');
  if (!modal) return;

  modal.classList.remove('active');
  setTimeout(() => {
    modal.style.display = 'none';
    // Reload page to show updated bids
    location.reload();
  }, 300);
}

/**
 * Handle confirmation button click - submit via AJAX
 * ✅ NOW SUPPORTS MULTIPLE BIDS
 */
function handleConfirmAccept() {
  if (!pendingAcceptData) return;

  const { bidsData, formData } = pendingAcceptData;
  const confirmBtn = document.getElementById('confirmAcceptBtn');

  if (!confirmBtn) return;

  // Disable button and show loading state
  confirmBtn.disabled = true;
  confirmBtn.textContent = 'Processing...';

  // Submit via AJAX
  fetch(`/bids/accept_bid/${window.bucketId}`, {
    method: 'POST',
    body: formData,
    headers: {
      'X-Requested-With': 'XMLHttpRequest'
    }
  })
    .then(async res => {
      // Handle 401 Unauthorized
      if (res.status === 401) {
        const data = await res.json().catch(() => ({}));
        throw new Error('AUTHENTICATION_REQUIRED: ' + (data.message || 'Please log in'));
      }

      const contentType = res.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        return res.json();
      } else {
        // Backend returned HTML (redirect or error page)
        throw new Error('Server returned non-JSON response');
      }
    })
    .then(data => {
      if (data.success) {
        // Close confirmation modal
        closeAcceptBidConfirmModal();

        // Show success modal with order details from backend response
        setTimeout(() => {
          if (data.all_order_details) {
            // ✅ Use all order details from backend (multiple orders)
            openAcceptBidSuccessModal(data.all_order_details);
          } else if (data.order_details) {
            // Legacy: single order (backward compatibility)
            openAcceptBidSuccessModal([data.order_details]);
          } else {
            // Fallback: construct from bidsData
            const fallbackOrders = bidsData.map(bid => {
              // Use effective_price for correct display (handles both fixed and variable bids)
              const effectivePrice = bid.effective_price || bid.price_per_coin || 0;
              return {
                buyer_name: bid.buyer_name,
                delivery_address: bid.delivery_address,
                price_per_coin: effectivePrice,
                quantity: bid.quantity,
                total_price: effectivePrice * bid.quantity
              };
            });
            openAcceptBidSuccessModal(fallbackOrders);
          }
        }, 350);
      } else {
        // Show error
        alert(data.message || 'Failed to accept bids. Please try again.');
        closeAcceptBidConfirmModal();
      }
    })
    .catch(err => {
      console.error('Accept bid error:', err);

      // Show specific message for authentication errors
      if (err.message.startsWith('AUTHENTICATION_REQUIRED')) {
        alert('You must be logged in to accept bids. Please log in and try again.');
        closeAcceptBidConfirmModal();
        // Redirect to login after a short delay
        setTimeout(() => {
          window.location.href = '/login';
        }, 1000);
      } else {
        alert('An error occurred while accepting the bids. Please try again.');
        closeAcceptBidConfirmModal();
      }
    })
    .finally(() => {
      // Reset button
      if (confirmBtn) {
        confirmBtn.disabled = false;
        confirmBtn.textContent = `Yes, Accept ${bidsData.length > 1 ? 'Bids' : 'Bid'}`;
      }
    });
}

/**
 * Intercept "Accept Bids" form submission
 * ✅ NOW SUPPORTS MULTIPLE BIDS
 */
function interceptAcceptBidsForm() {
  const form = document.getElementById('accept-bids-form');
  if (!form) return;

  form.addEventListener('submit', (e) => {
    e.preventDefault();

    // Get selected bids
    const selectedCheckboxes = form.querySelectorAll('.selected-checkbox:checked');
    if (selectedCheckboxes.length === 0) {
      alert('Please select at least one bid to accept.');
      return;
    }

    // Collect all selected bids with their quantities
    const allBids = window.allBids || [];
    const selectedBidsData = [];

    for (const checkbox of selectedCheckboxes) {
      const bidId = parseInt(checkbox.value, 10);
      const hiddenInput = form.querySelector(`#accept_qty_${bidId}`);
      const quantity = parseInt(hiddenInput?.value || '0', 10);

      if (quantity <= 0) {
        alert(`Please set a quantity greater than 0 for Bid #${bidId}.`);
        return;
      }

      // Find bid data
      const bid = allBids.find(b => b.id === bidId);
      if (!bid) {
        alert(`Bid #${bidId} data not found.`);
        return;
      }

      // Add to selected bids array
      selectedBidsData.push({
        ...bid,
        quantity: quantity
      });
    }

    // Prepare form data
    const formData = new FormData(form);

    // Show confirmation modal with all selected bids
    openAcceptBidConfirmModal(selectedBidsData, formData);
  });
}

/**
 * Initialize modal system
 */
document.addEventListener('DOMContentLoaded', () => {
  // Wire up confirmation button
  const confirmBtn = document.getElementById('confirmAcceptBtn');
  if (confirmBtn) {
    confirmBtn.addEventListener('click', handleConfirmAccept);
  }

  // Intercept accept bids form
  interceptAcceptBidsForm();

  // Close modals on overlay click
  document.getElementById('acceptBidConfirmModal')?.addEventListener('click', (e) => {
    if (e.target.id === 'acceptBidConfirmModal') {
      closeAcceptBidConfirmModal();
    }
  });

  document.getElementById('acceptBidSuccessModal')?.addEventListener('click', (e) => {
    if (e.target.id === 'acceptBidSuccessModal') {
      closeAcceptBidSuccessModal();
    }
  });

  // Close modals on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeAcceptBidConfirmModal();
      closeAcceptBidSuccessModal();
    }
  });
});

// Expose functions globally
window.openAcceptBidConfirmModal = openAcceptBidConfirmModal;
window.closeAcceptBidConfirmModal = closeAcceptBidConfirmModal;
window.openAcceptBidSuccessModal = openAcceptBidSuccessModal;
window.closeAcceptBidSuccessModal = closeAcceptBidSuccessModal;
