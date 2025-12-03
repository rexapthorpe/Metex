// static/js/modals/sell_listing_modals.js
'use strict';

/* ==========================================================================
   Sell Listing Modals - Two-step confirmation flow
   1. Intercept form submission and show confirmation modal
   2. On confirm, submit via AJAX and show success modal
   3. On close success modal, redirect to Buy page
   ========================================================================== */

let pendingListingForm = null;
let pendingFormData = null;

/**
 * Open confirmation modal with listing summary
 * @param {FormData} formData - Form data from sell form
 */
function openSellConfirmModal(formData) {
  const modal = document.getElementById('sellListingConfirmModal');
  if (!modal) return;

  // Extract values from form data
  const metal = formData.get('metal') || '—';
  const productLine = formData.get('product_line') || '—';
  const productType = formData.get('product_type') || '—';
  const weight = formData.get('weight') || '—';
  const year = formData.get('year') || '—';
  const quantity = formData.get('quantity') || '0';
  const graded = formData.get('graded') === 'on' ? 'Yes' : 'No';

  // Get pricing mode
  const pricingMode = formData.get('pricing_mode') || 'static';
  const isPremiumToSpot = pricingMode === 'premium_to_spot';

  // Populate common fields
  document.getElementById('confirm-metal').textContent = metal;
  document.getElementById('confirm-product-line').textContent = productLine;
  document.getElementById('confirm-product-type').textContent = productType;
  document.getElementById('confirm-weight').textContent = weight;
  document.getElementById('confirm-year').textContent = year;
  document.getElementById('confirm-quantity').textContent = quantity;
  document.getElementById('confirm-graded').textContent = graded;

  // Display pricing mode
  document.getElementById('confirm-pricing-mode').textContent = isPremiumToSpot ? 'Premium to Spot' : 'Fixed Price';

  if (isPremiumToSpot) {
    // Premium-to-spot mode
    const spotPremium = parseFloat(formData.get('spot_premium')) || 0;
    const floorPrice = parseFloat(formData.get('floor_price')) || 0;
    const effectivePrice = parseFloat(document.getElementById('price_preview')?.querySelector('.preview-amount')?.textContent.replace(/[$,]/g, '')) || floorPrice;
    const totalValue = parseInt(quantity) * effectivePrice;

    // Hide static pricing rows
    document.getElementById('confirm-static-price-row').style.display = 'none';
    document.getElementById('confirm-static-total-row').style.display = 'none';

    // Show and populate premium-to-spot rows
    document.getElementById('confirm-premium-row').style.display = 'flex';
    document.getElementById('confirm-floor-row').style.display = 'flex';
    document.getElementById('confirm-effective-price-row').style.display = 'flex';
    document.getElementById('confirm-effective-total-row').style.display = 'flex';

    document.getElementById('confirm-premium').textContent = `+$${spotPremium.toFixed(2)} USD per unit above spot`;
    document.getElementById('confirm-floor').textContent = `$${floorPrice.toFixed(2)} USD minimum`;
    document.getElementById('confirm-effective-price').textContent = `$${effectivePrice.toFixed(2)} USD`;
    document.getElementById('confirm-effective-total').textContent = `$${totalValue.toFixed(2)} USD`;
  } else {
    // Static mode
    const pricePerCoin = parseFloat(formData.get('price_per_coin')) || 0;
    const totalValue = parseInt(quantity) * pricePerCoin;

    // Show static pricing rows
    document.getElementById('confirm-static-price-row').style.display = 'flex';
    document.getElementById('confirm-static-total-row').style.display = 'flex';

    // Hide premium-to-spot rows
    document.getElementById('confirm-premium-row').style.display = 'none';
    document.getElementById('confirm-floor-row').style.display = 'none';
    document.getElementById('confirm-effective-price-row').style.display = 'none';
    document.getElementById('confirm-effective-total-row').style.display = 'none';

    document.getElementById('confirm-price').textContent = `$${pricePerCoin.toFixed(2)} USD`;
    document.getElementById('confirm-total-value').textContent = `$${totalValue.toFixed(2)} USD`;
  }

  // Show modal with animation
  modal.style.display = 'flex';
  requestAnimationFrame(() => {
    modal.classList.add('active');
  });
}

/**
 * Close confirmation modal
 */
function closeSellConfirmModal() {
  const modal = document.getElementById('sellListingConfirmModal');
  if (!modal) return;

  modal.classList.remove('active');
  setTimeout(() => {
    modal.style.display = 'none';
    pendingListingForm = null;
    pendingFormData = null;
  }, 300);
}

/**
 * Open success modal with listing details
 * @param {Object} data - Response data from backend
 */
function openSellSuccessModal(data) {
  const modal = document.getElementById('sellListingSuccessModal');
  if (!modal) return;

  // Build item description
  const listing = data.listing || {};
  let itemDesc = [];
  if (listing.metal) itemDesc.push(listing.metal);
  if (listing.product_line) itemDesc.push(listing.product_line);
  if (listing.weight) itemDesc.push(listing.weight);
  if (listing.year) itemDesc.push(listing.year);
  const itemDescText = itemDesc.join(' ') || 'Item';

  const quantity = listing.quantity || 0;
  const pricingMode = listing.pricing_mode || 'static';
  const isPremiumToSpot = pricingMode === 'premium_to_spot';

  // Populate common fields
  document.getElementById('success-item-desc').textContent = itemDescText;
  document.getElementById('success-quantity').textContent = quantity;

  // Display pricing mode
  document.getElementById('success-pricing-mode').textContent = isPremiumToSpot ? 'Premium to Spot' : 'Fixed Price';

  if (isPremiumToSpot) {
    // Premium-to-spot mode
    const spotPremium = parseFloat(listing.spot_premium) || 0;
    const floorPrice = parseFloat(listing.floor_price) || 0;
    // Use effective_price from backend if available, otherwise use price_per_coin or floor
    const effectivePrice = parseFloat(listing.effective_price || listing.price_per_coin) || floorPrice;
    const totalValue = quantity * effectivePrice;

    // Hide static pricing rows
    document.getElementById('success-static-price-row').style.display = 'none';
    document.getElementById('success-static-total-row').style.display = 'none';

    // Show and populate premium-to-spot rows
    document.getElementById('success-premium-row').style.display = 'flex';
    document.getElementById('success-floor-row').style.display = 'flex';
    document.getElementById('success-effective-price-row').style.display = 'flex';
    document.getElementById('success-effective-total-row').style.display = 'flex';

    document.getElementById('success-premium').textContent = `+$${spotPremium.toFixed(2)} USD per unit above spot`;
    document.getElementById('success-floor').textContent = `$${floorPrice.toFixed(2)} USD minimum`;
    document.getElementById('success-effective-price').textContent = `$${effectivePrice.toFixed(2)} USD`;
    document.getElementById('success-effective-total').textContent = `$${totalValue.toFixed(2)} USD`;
  } else {
    // Static mode
    const pricePerCoin = parseFloat(listing.price_per_coin) || 0;
    const totalValue = quantity * pricePerCoin;

    // Show static pricing rows
    document.getElementById('success-static-price-row').style.display = 'flex';
    document.getElementById('success-static-total-row').style.display = 'flex';

    // Hide premium-to-spot rows
    document.getElementById('success-premium-row').style.display = 'none';
    document.getElementById('success-floor-row').style.display = 'none';
    document.getElementById('success-effective-price-row').style.display = 'none';
    document.getElementById('success-effective-total-row').style.display = 'none';

    document.getElementById('success-price').textContent = `$${pricePerCoin.toFixed(2)} USD`;
    document.getElementById('success-total-value').textContent = `$${totalValue.toFixed(2)} USD`;
  }

  // Show modal with animation
  modal.style.display = 'flex';
  requestAnimationFrame(() => {
    modal.classList.add('active');
  });
}

/**
 * Close success modal and redirect to Buy page
 */
function closeSellSuccessModal() {
  const modal = document.getElementById('sellListingSuccessModal');
  if (!modal) return;

  modal.classList.remove('active');
  setTimeout(() => {
    modal.style.display = 'none';
    // Redirect to Buy page
    window.location.href = '/buy';
  }, 300);
}

/**
 * Handle confirm listing button click - submit via AJAX
 */
function handleConfirmListing() {
  if (!pendingListingForm || !pendingFormData) {
    console.error('No pending listing data found');
    return;
  }

  const confirmBtn = document.getElementById('confirmListingBtn');
  if (!confirmBtn) return;

  // Disable button and show loading state
  confirmBtn.disabled = true;
  confirmBtn.textContent = 'Creating Listing...';

  // Submit via AJAX to sell route
  fetch('/sell', {
    method: 'POST',
    body: pendingFormData,
    headers: {
      'X-Requested-With': 'XMLHttpRequest'
    }
  })
    .then(async res => {
      const contentType = res.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        return res.json();
      } else {
        throw new Error('Server returned non-JSON response');
      }
    })
    .then(data => {
      if (data.success) {
        // Close confirmation modal
        closeSellConfirmModal();

        // Show success modal with listing details
        setTimeout(() => {
          openSellSuccessModal(data);
        }, 350);
      } else {
        // Show error
        alert(data.message || 'Failed to create listing. Please try again.');
        closeSellConfirmModal();
      }
    })
    .catch(err => {
      console.error('Sell listing error:', err);
      alert('An error occurred while creating your listing. Please try again.');
      closeSellConfirmModal();
    })
    .finally(() => {
      // Reset button
      if (confirmBtn) {
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'Confirm Listing';
      }
    });
}

/**
 * Intercept sell form submission to validate first, then show confirmation modal
 */
function interceptSellForm() {
  const sellForm = document.getElementById('sellForm');
  if (!sellForm) return;

  // Skip if already intercepted
  if (sellForm.dataset.intercepted) return;
  sellForm.dataset.intercepted = 'true';

  sellForm.addEventListener('submit', (e) => {
    e.preventDefault();
    e.stopPropagation();

    // STEP 1: Validate the form first
    const validation = window.validateSellForm(sellForm);

    if (!validation.isValid) {
      // Show validation error modal
      window.showFieldValidationModal(validation.errors);
      return;
    }

    // STEP 2: If validation passes, proceed to confirmation
    // Store form reference and data
    pendingListingForm = sellForm;
    pendingFormData = new FormData(sellForm);

    // Show confirmation modal
    openSellConfirmModal(pendingFormData);
  });
}

/**
 * Initialize modal system
 */
document.addEventListener('DOMContentLoaded', () => {
  // Wire up confirmation button
  const confirmBtn = document.getElementById('confirmListingBtn');
  if (confirmBtn) {
    confirmBtn.addEventListener('click', handleConfirmListing);
  }

  // Intercept sell form
  interceptSellForm();

  // Close confirm modal on overlay click
  document.getElementById('sellListingConfirmModal')?.addEventListener('click', (e) => {
    if (e.target.id === 'sellListingConfirmModal') {
      closeSellConfirmModal();
    }
  });

  // Close success modal on overlay click
  document.getElementById('sellListingSuccessModal')?.addEventListener('click', (e) => {
    if (e.target.id === 'sellListingSuccessModal') {
      closeSellSuccessModal();
    }
  });

  // Close modals on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeSellConfirmModal();
      closeSellSuccessModal();
    }
  });
});

// Expose functions globally
window.openSellConfirmModal = openSellConfirmModal;
window.closeSellConfirmModal = closeSellConfirmModal;
window.openSellSuccessModal = openSellSuccessModal;
window.closeSellSuccessModal = closeSellSuccessModal;
