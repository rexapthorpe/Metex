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

  // Extract ALL values from form data
  const metal = formData.get('metal') || '—';
  const productLine = formData.get('product_line') || '—';
  const productType = formData.get('product_type') || '—';
  const weight = formData.get('weight') || '—';
  const purity = formData.get('purity') || '—';
  const mint = formData.get('mint') || '—';
  const year = formData.get('year') || '—';
  const grade = formData.get('grade') || '—';
  const finish = formData.get('finish') || '—';
  const quantity = formData.get('quantity') || '0';

  // Get grading information
  const isGraded = formData.get('graded') === '1';
  let gradedText = 'No';
  if (isGraded) {
    const gradingService = formData.get('grading_service') || '';
    if (gradingService) {
      gradedText = `Yes (${gradingService})`;
    } else {
      gradedText = 'Yes';
    }
  }

  // Get isolated/set/numismatic information
  const isIsolated = formData.get('is_isolated') === '1';
  const isSet = formData.get('is_set') === '1';
  const issueNumber = formData.get('issue_number') || '';
  const issueTotal = formData.get('issue_total') || '';

  // Determine listing type classification
  let listingTypeText = 'Standard pooled listing';
  let showNumismaticRow = false;
  let showSetItemsRow = false;
  let numismaticText = '';
  let setItemsCountText = '';

  if (isSet) {
    listingTypeText = 'Set listing (isolated)';
    showSetItemsRow = true;
    // Count set items from form (set_items[N][...])
    const setItemsCount = Array.from(formData.keys()).filter(key => key.startsWith('set_items[')).reduce((acc, key) => {
      const match = key.match(/set_items\[(\d+)\]/);
      if (match) {
        const index = parseInt(match[1]);
        return Math.max(acc, index + 1);
      }
      return acc;
    }, 0);
    setItemsCountText = `${setItemsCount + 1} items (1 main + ${setItemsCount} additional)`;
  } else if (issueNumber && issueTotal) {
    listingTypeText = 'Numismatic item (isolated)';
    showNumismaticRow = true;
    numismaticText = `Issue #${issueNumber} of ${issueTotal}`;
  } else if (isIsolated) {
    listingTypeText = 'One-of-a-kind (isolated)';
  }

  // Get pricing mode
  const pricingMode = formData.get('pricing_mode') || 'static';
  const isPremiumToSpot = pricingMode === 'premium_to_spot';

  // Populate ALL item detail fields
  document.getElementById('confirm-metal').textContent = metal;
  document.getElementById('confirm-product-line').textContent = productLine;
  document.getElementById('confirm-product-type').textContent = productType;
  document.getElementById('confirm-weight').textContent = weight;
  document.getElementById('confirm-purity').textContent = purity;
  document.getElementById('confirm-mint').textContent = mint;
  document.getElementById('confirm-year').textContent = year;
  document.getElementById('confirm-grade').textContent = grade;
  document.getElementById('confirm-finish').textContent = finish;
  document.getElementById('confirm-graded').textContent = gradedText;

  // Populate listing classification fields
  document.getElementById('confirm-listing-type').textContent = listingTypeText;

  // Show/hide and populate numismatic row
  const numismaticRow = document.getElementById('confirm-numismatic-row');
  if (showNumismaticRow) {
    numismaticRow.style.display = 'flex';
    document.getElementById('confirm-numismatic-issue').textContent = numismaticText;
  } else {
    numismaticRow.style.display = 'none';
  }

  // Show/hide and populate set items row
  const setItemsRow = document.getElementById('confirm-set-items-row');
  if (showSetItemsRow) {
    setItemsRow.style.display = 'flex';
    document.getElementById('confirm-set-items-count').textContent = setItemsCountText;
  } else {
    setItemsRow.style.display = 'none';
  }

  // Populate pricing fields
  document.getElementById('confirm-quantity').textContent = quantity;

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

  // Extract listing data
  const listing = data.listing || {};

  // Extract all item detail fields
  const metal = listing.metal || '—';
  const productLine = listing.product_line || '—';
  const productType = listing.product_type || '—';
  const weight = listing.weight || '—';
  const purity = listing.purity || '—';
  const mint = listing.mint || '—';
  const year = listing.year || '—';
  const grade = listing.grade || '—';
  const finish = listing.finish || '—';

  // Get grading information
  const isGraded = listing.graded === 1 || listing.graded === '1' || listing.graded === true;
  let gradedText = 'No';
  if (isGraded) {
    const gradingService = listing.grading_service || '';
    if (gradingService) {
      gradedText = `Yes (${gradingService})`;
    } else {
      gradedText = 'Yes';
    }
  }

  // Get isolated/set/numismatic information from backend response
  const isIsolated = listing.is_isolated === 1 || listing.is_isolated === '1' || listing.is_isolated === true;
  const isolatedType = listing.isolated_type || '';
  const issueNumber = listing.issue_number || '';
  const issueTotal = listing.issue_total || '';

  // Determine listing type classification
  let listingTypeText = 'Standard pooled listing';
  let showNumismaticRow = false;
  let showSetItemsRow = false;
  let numismaticText = '';
  let setItemsCountText = '';

  if (isolatedType === 'set') {
    listingTypeText = 'Set listing (isolated)';
    showSetItemsRow = true;
    // Get set items count from backend data if available
    const setItems = data.set_items || [];
    setItemsCountText = `${setItems.length} items total`;
  } else if (issueNumber && issueTotal) {
    listingTypeText = 'Numismatic item (isolated)';
    showNumismaticRow = true;
    numismaticText = `Issue #${issueNumber} of ${issueTotal}`;
  } else if (isIsolated) {
    listingTypeText = 'One-of-a-kind (isolated)';
  }

  const quantity = listing.quantity || 0;
  const pricingMode = listing.pricing_mode || 'static';
  const isPremiumToSpot = pricingMode === 'premium_to_spot';

  // Populate ALL item detail fields
  const metalEl = modal.querySelector('#success-metal');
  const productLineEl = modal.querySelector('#success-product-line');
  const productTypeEl = modal.querySelector('#success-product-type');
  const weightEl = modal.querySelector('#success-weight');
  const purityEl = modal.querySelector('#success-purity');
  const mintEl = modal.querySelector('#success-mint');
  const yearEl = modal.querySelector('#success-year');
  const gradeEl = modal.querySelector('#success-grade');
  const finishEl = modal.querySelector('#success-finish');
  const gradedEl = modal.querySelector('#success-graded');

  if (metalEl) metalEl.textContent = metal;
  if (productLineEl) productLineEl.textContent = productLine;
  if (productTypeEl) productTypeEl.textContent = productType;
  if (weightEl) weightEl.textContent = weight;
  if (purityEl) purityEl.textContent = purity;
  if (mintEl) mintEl.textContent = mint;
  if (yearEl) yearEl.textContent = year;
  if (gradeEl) gradeEl.textContent = grade;
  if (finishEl) finishEl.textContent = finish;
  if (gradedEl) gradedEl.textContent = gradedText;

  // Populate listing classification fields
  const listingTypeEl = modal.querySelector('#success-listing-type');
  if (listingTypeEl) listingTypeEl.textContent = listingTypeText;

  // Show/hide and populate numismatic row
  const numismaticRowSuccess = modal.querySelector('#success-numismatic-row');
  const numismaticIssueEl = modal.querySelector('#success-numismatic-issue');
  if (numismaticRowSuccess) {
    if (showNumismaticRow) {
      numismaticRowSuccess.style.display = 'flex';
      if (numismaticIssueEl) numismaticIssueEl.textContent = numismaticText;
    } else {
      numismaticRowSuccess.style.display = 'none';
    }
  }

  // Show/hide and populate set items row
  const setItemsRowSuccess = modal.querySelector('#success-set-items-row');
  const setItemsCountEl = modal.querySelector('#success-set-items-count');
  if (setItemsRowSuccess) {
    if (showSetItemsRow) {
      setItemsRowSuccess.style.display = 'flex';
      if (setItemsCountEl) setItemsCountEl.textContent = setItemsCountText;
    } else {
      setItemsRowSuccess.style.display = 'none';
    }
  }

  // Populate pricing fields
  const quantityEl = modal.querySelector('#success-quantity');
  const pricingModeEl = modal.querySelector('#success-pricing-mode');

  if (quantityEl) quantityEl.textContent = quantity;
  if (pricingModeEl) pricingModeEl.textContent = isPremiumToSpot ? 'Premium to Spot' : 'Fixed Price';

  if (isPremiumToSpot) {
    // Premium-to-spot mode
    const spotPremium = parseFloat(listing.spot_premium) || 0;
    const floorPrice = parseFloat(listing.floor_price) || 0;
    const effectivePrice = parseFloat(listing.effective_price || listing.price_per_coin) || floorPrice;
    const totalValue = quantity * effectivePrice;

    // Get all rows
    const staticPriceRow = modal.querySelector('#success-static-price-row');
    const staticTotalRow = modal.querySelector('#success-static-total-row');
    const premiumRow = modal.querySelector('#success-premium-row');
    const floorRow = modal.querySelector('#success-floor-row');
    const effectivePriceRow = modal.querySelector('#success-effective-price-row');
    const effectiveTotalRow = modal.querySelector('#success-effective-total-row');

    // Hide static pricing rows
    if (staticPriceRow) staticPriceRow.style.display = 'none';
    if (staticTotalRow) staticTotalRow.style.display = 'none';

    // Show and populate premium-to-spot rows
    if (premiumRow) {
      premiumRow.style.display = 'flex';
      const premiumEl = modal.querySelector('#success-premium');
      if (premiumEl) premiumEl.textContent = `+$${spotPremium.toFixed(2)} USD per unit above spot`;
    }
    if (floorRow) {
      floorRow.style.display = 'flex';
      const floorEl = modal.querySelector('#success-floor');
      if (floorEl) floorEl.textContent = `$${floorPrice.toFixed(2)} USD minimum`;
    }
    if (effectivePriceRow) {
      effectivePriceRow.style.display = 'flex';
      const effectivePriceEl = modal.querySelector('#success-effective-price');
      if (effectivePriceEl) effectivePriceEl.textContent = `$${effectivePrice.toFixed(2)} USD`;
    }
    if (effectiveTotalRow) {
      effectiveTotalRow.style.display = 'flex';
      const effectiveTotalEl = modal.querySelector('#success-effective-total');
      if (effectiveTotalEl) effectiveTotalEl.textContent = `$${totalValue.toFixed(2)} USD`;
    }
  } else {
    // Static mode
    const pricePerCoin = parseFloat(listing.price_per_coin) || 0;
    const totalValue = quantity * pricePerCoin;

    // Get all rows
    const staticPriceRow = modal.querySelector('#success-static-price-row');
    const staticTotalRow = modal.querySelector('#success-static-total-row');
    const premiumRow = modal.querySelector('#success-premium-row');
    const floorRow = modal.querySelector('#success-floor-row');
    const effectivePriceRow = modal.querySelector('#success-effective-price-row');
    const effectiveTotalRow = modal.querySelector('#success-effective-total-row');

    // Show static pricing rows
    if (staticPriceRow) {
      staticPriceRow.style.display = 'flex';
      const priceEl = modal.querySelector('#success-price');
      if (priceEl) priceEl.textContent = `$${pricePerCoin.toFixed(2)} USD`;
    }
    if (staticTotalRow) {
      staticTotalRow.style.display = 'flex';
      const totalValueEl = modal.querySelector('#success-total-value');
      if (totalValueEl) totalValueEl.textContent = `$${totalValue.toFixed(2)} USD`;
    }

    // Hide premium-to-spot rows
    if (premiumRow) premiumRow.style.display = 'none';
    if (floorRow) floorRow.style.display = 'none';
    if (effectivePriceRow) effectivePriceRow.style.display = 'none';
    if (effectiveTotalRow) effectiveTotalRow.style.display = 'none';
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
