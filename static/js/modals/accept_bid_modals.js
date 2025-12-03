// static/js/modals/accept_bid_modals.js
'use strict';

/* ==========================================================================
   Accept Bid Modal Flow
   Two-step process: Confirmation → Success
   ========================================================================== */

let pendingAcceptData = null;

/**
 * Open confirmation modal with bid summary
 * @param {Object} bidData - Bid information
 * @param {FormData} formData - Form data to submit
 */
function openAcceptBidConfirmModal(bidData, formData) {
  pendingAcceptData = { bidData, formData };

  const modal = document.getElementById('acceptBidConfirmModal');
  if (!modal) return;

  // Populate modal with bid details
  const bidderName = bidData.buyer_name || 'Unknown';
  const price = bidData.price_per_coin || 0;
  const quantity = bidData.quantity || 1;
  const total = price * quantity;

  document.getElementById('confirm-bidder-name').textContent = bidderName;
  document.getElementById('confirm-price').textContent = `$${price.toFixed(2)} USD`;
  document.getElementById('confirm-quantity').textContent = quantity;
  document.getElementById('confirm-total').textContent = `$${total.toFixed(2)} USD`;

  // Populate item specs (8 attributes)
  const specs = window.bucketSpecs || {};
  const specMap = {
    'confirm-spec-metal': specs.Metal || specs.metal || '—',
    'confirm-spec-product-line': specs['Product line'] || specs.product_line || '—',
    'confirm-spec-product-type': specs['Product type'] || specs.product_type || '—',
    'confirm-spec-weight': specs.Weight || specs.weight || '—',
    'confirm-spec-grade': specs.Grading || specs.grade || '—',
    'confirm-spec-year': specs.Year || specs.year || '—',
    'confirm-spec-mint': specs.Mint || specs.mint || '—',
    'confirm-spec-purity': specs.Purity || specs.purity || '—'
  };

  Object.entries(specMap).forEach(([id, value]) => {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  });

  // Populate grading requirement
  const requiresGrading = bidData.requires_grading;
  const preferredGrader = bidData.preferred_grader;
  let gradingText = 'This item does not require 3rd party grading';

  if (requiresGrading) {
    if (preferredGrader) {
      gradingText = `This item requires 3rd party grading (${preferredGrader})`;
    } else {
      gradingText = 'This item requires 3rd party grading';
    }
  }

  document.getElementById('confirm-grading-text').textContent = gradingText;

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
 * @param {Object} orderData - Order information from backend
 */
function openAcceptBidSuccessModal(orderData) {
  const modal = document.getElementById('acceptBidSuccessModal');
  if (!modal) return;

  // Populate buyer information
  document.getElementById('success-buyer-name').textContent = orderData.buyer_name || 'Unknown';

  // Parse and populate delivery address
  console.log('[SUCCESS MODAL] Raw delivery_address:', orderData.delivery_address);
  console.log('[SUCCESS MODAL] Type:', typeof orderData.delivery_address);

  let address = orderData.delivery_address || '';
  let street = '';
  let street2 = '';
  let city = '';
  let state = '';
  let zip = '';

  // Handle different address formats
  if (!address || address === 'Not provided') {
    console.log('[SUCCESS MODAL] No address provided');
  } else if (typeof address === 'object') {
    // Address is an object with separate fields
    console.log('[SUCCESS MODAL] Address is object:', address);
    street = address.line1 || address.street || '';
    street2 = address.line2 || address.street2 || '';
    city = address.city || '';
    state = address.state || '';
    zip = address.zip || address.zip_code || '';
  } else if (typeof address === 'string' && address.includes('•')) {
    // Address uses bullet separator format: "Name • Line1 • [Line2 •] City, State ZIP"
    console.log('[SUCCESS MODAL] Parsing bullet-separated address');

    // Clean delivery address (remove name prefix if present)
    let cleanAddress = address;
    if (address.includes(' - ')) {
      cleanAddress = address.split(' - ').slice(1).join(' - ');
    }

    const addressParts = cleanAddress.split('•').map(p => p.trim());
    console.log('[SUCCESS MODAL] Address parts:', addressParts);

    // Extract name if it's in the first part (before first •)
    if (addressParts.length >= 1) {
      street = addressParts[0];
    }

    // Check for 2, 3, or 4 parts
    let cityStateZip = '';
    if (addressParts.length === 4) {
      // Format: Name • Line1 • Line2 • City, State ZIP
      street = addressParts[1];
      street2 = addressParts[2];
      cityStateZip = addressParts[3];
    } else if (addressParts.length === 3) {
      // Format: Line1 • Line2 • City, State ZIP  OR  Name • Line1 • City, State ZIP
      // Check if last part looks like city, state, zip
      const lastPart = addressParts[2];
      if (lastPart.includes(',')) {
        // Has comma, likely city,state format
        street2 = addressParts[1];
        cityStateZip = lastPart;
      } else {
        // No comma, treat as name • line1 • line2
        street = addressParts[0];
        street2 = addressParts[1];
        cityStateZip = addressParts[2];
      }
    } else if (addressParts.length === 2) {
      // Format: Line1 • City, State ZIP
      cityStateZip = addressParts[1];
    }

    // Parse "City, State ZIP" or "City, State, ZIP"
    if (cityStateZip && cityStateZip.includes(',')) {
      const cityParts = cityStateZip.split(',').map(p => p.trim());
      city = cityParts[0];

      if (cityParts.length === 2) {
        // Format: "City, State ZIP"
        const stateZipParts = cityParts[1].split(/\s+/);
        if (stateZipParts.length >= 1) {
          state = stateZipParts[0];
        }
        if (stateZipParts.length >= 2) {
          zip = stateZipParts.slice(1).join(' ');
        }
      } else if (cityParts.length >= 3) {
        // Format: "City, State, ZIP"
        state = cityParts[1];
        zip = cityParts.slice(2).join(', ');
      }
    }
  } else if (typeof address === 'string') {
    // Simple text address - display as Line 1
    console.log('[SUCCESS MODAL] Simple text address, displaying as Line 1');
    street = address;
  }

  console.log('[SUCCESS MODAL] Parsed address:', {
    street, street2, city, state, zip
  });

  // Get all address elements and populate them
  const line1El = document.getElementById('success-address-line1');
  const line2El = document.getElementById('success-address-line2');
  const cityEl = document.getElementById('success-address-city');
  const stateEl = document.getElementById('success-address-state');
  const zipEl = document.getElementById('success-address-zip');

  // Populate each component (or leave as "—" if empty)
  if (line1El) {
    line1El.textContent = street || '—';
    console.log('[SUCCESS MODAL] Line 1:', street || '—');
  }

  if (line2El) {
    line2El.textContent = street2 || '—';
    console.log('[SUCCESS MODAL] Line 2:', street2 || '—');
  }

  if (cityEl) {
    cityEl.textContent = city || '—';
    console.log('[SUCCESS MODAL] City:', city || '—');
  }

  if (stateEl) {
    stateEl.textContent = state || '—';
    console.log('[SUCCESS MODAL] State:', state || '—');
  }

  if (zipEl) {
    zipEl.textContent = zip || '—';
    console.log('[SUCCESS MODAL] ZIP:', zip || '—');
  }

  // Check if any address fields were populated
  const hasAddress = street || street2 || city || state || zip;
  console.log('[SUCCESS MODAL] Has address data:', hasAddress);

  // Populate transaction details
  const price = orderData.price_per_coin || 0;
  const quantity = orderData.quantity || 1;
  const total = orderData.total_price || (price * quantity);

  document.getElementById('success-price').textContent = `$${price.toFixed(2)} USD`;
  document.getElementById('success-quantity').textContent = quantity;
  document.getElementById('success-total').textContent = `$${total.toFixed(2)} USD`;

  // Populate item specs (all 9 attributes)
  const specs = window.bucketSpecs || {};

  const specMap = {
    'success-spec-metal': specs.Metal || specs.metal || '—',
    'success-spec-product-line': specs['Product line'] || specs.product_line || '—',
    'success-spec-product-type': specs['Product type'] || specs.product_type || '—',
    'success-spec-weight': specs.Weight || specs.weight || '—',
    'success-spec-grade': specs.Grading || specs.grade || '—',
    'success-spec-year': specs.Year || specs.year || '—',
    'success-spec-mint': specs.Mint || specs.mint || '—',
    'success-spec-purity': specs.Purity || specs.purity || '—',
    'success-spec-finish': specs.Finish || specs.finish || '—'
  };

  Object.entries(specMap).forEach(([id, value]) => {
    const el = document.getElementById(id);
    if (el) {
      const valueEl = el.querySelector('.spec-value');
      if (valueEl) valueEl.textContent = value;
    }
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
 */
function handleConfirmAccept() {
  if (!pendingAcceptData) return;

  const { bidData, formData } = pendingAcceptData;
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
          if (data.order_details) {
            // Use order details from backend (includes fresh delivery_address)
            openAcceptBidSuccessModal(data.order_details);
          } else {
            // Fallback to bidData if order_details not provided
            openAcceptBidSuccessModal({
              buyer_name: bidData.buyer_name,
              delivery_address: bidData.delivery_address,
              price_per_coin: bidData.price_per_coin,
              quantity: bidData.quantity,
              total_price: data.total_price || (bidData.price_per_coin * bidData.quantity)
            });
          }
        }, 350);
      } else {
        // Show error
        alert(data.message || 'Failed to accept bid. Please try again.');
        closeAcceptBidConfirmModal();
      }
    })
    .catch(err => {
      console.error('Accept bid error:', err);
      alert('An error occurred while accepting the bid. Please try again.');
      closeAcceptBidConfirmModal();
    })
    .finally(() => {
      // Reset button
      if (confirmBtn) {
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'Yes, Accept Bid';
      }
    });
}

/**
 * Intercept "Accept Bids" form submission
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

    // For now, only handle single bid selection for modal flow
    // (Could be extended to handle multiple bids)
    if (selectedCheckboxes.length > 1) {
      alert('Please select only one bid at a time for acceptance.');
      return;
    }

    const checkbox = selectedCheckboxes[0];
    const bidId = parseInt(checkbox.value, 10);
    const hiddenInput = form.querySelector(`#accept_qty_${bidId}`);
    const quantity = parseInt(hiddenInput?.value || '0', 10);

    if (quantity <= 0) {
      alert('Please set a quantity greater than 0.');
      return;
    }

    // Find bid data
    const allBids = window.allBids || [];
    const bid = allBids.find(b => b.id === bidId);

    if (!bid) {
      alert('Bid data not found.');
      return;
    }

    // Prepare form data
    const formData = new FormData(form);

    // Prepare bid data
    const bidData = {
      ...bid,
      quantity: quantity
    };

    // Show confirmation modal
    openAcceptBidConfirmModal(bidData, formData);
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
