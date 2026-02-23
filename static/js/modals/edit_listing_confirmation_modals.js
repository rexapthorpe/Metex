// static/js/modals/edit_listing_confirmation_modals.js
'use strict';

/* ==========================================================================
   Edit Listing Confirmation Modal
   Shows before applying changes to confirm listing details
   ========================================================================== */

/**
 * Open edit listing confirmation modal with listing details
 * @param {Object} data - Listing data to display
 * @param {string} data.listingId - Listing ID
 * @param {string} data.itemDesc - Item description
 * @param {number} data.quantity - Quantity available
 * @param {boolean} data.graded - Whether item is graded
 * @param {string} data.gradingService - Grading service name
 * @param {string} data.pricingMode - Pricing mode ('static' or 'premium_to_spot')
 * @param {number} data.pricePerCoin - Static price (for static mode)
 * @param {number} data.spotPremium - Premium above spot (for variable mode)
 * @param {number} data.floorPrice - Floor/minimum price (for variable mode)
 * @param {string} data.pricingMetal - Metal for spot pricing (for variable mode)
 * @param {number} data.weight - Item weight in oz (for variable mode)
 * @param {boolean} data.hasPhoto - Whether a photo is included
 * @param {FormData} data.formData - Form data to submit on confirmation
 */
async function openEditListingConfirmModal(data) {
  const modal = document.getElementById('editListingConfirmModal');

  if (!modal) {
    console.error('Edit listing confirmation modal not found (#editListingConfirmModal)');
    return;
  }

  // Store form data for later submission (will be updated with calculated prices)
  window.editListingPendingSubmission = {
    listingId: data.listingId,
    formData: data.formData,
    data: data
  };

  // Determine pricing mode
  const pricingMode = data.pricingMode || 'static';
  const isVariablePricing = pricingMode === 'premium_to_spot';

  // For variable pricing, fetch current spot prices and calculate effective price
  let effectivePrice = null;
  let currentSpotPrice = null;

  if (isVariablePricing) {
    try {
      const response = await fetch('/api/spot-prices');
      const spotData = await response.json();

      if (spotData.success && spotData.prices) {
        const metal = data.pricingMetal || data.metal || '';
        // Extract numeric weight from string like "1 oz"
        const weightStr = data.weight || '1';
        const weightMatch = weightStr.match(/[\d.]+/);
        const weight = weightMatch ? parseFloat(weightMatch[0]) : 1.0;

        if (metal && spotData.prices[metal.toLowerCase()]) {
          currentSpotPrice = spotData.prices[metal.toLowerCase()];

          // Parse premium and floor as numbers
          const spotPremium = parseFloat(data.spotPremium) || 0;
          const floorPrice = parseFloat(data.floorPrice) || 0;

          // Calculate effective price: (spot * weight) + premium
          // NOTE: Floor is shown separately but NOT applied to display price
          const calculatedPrice = (currentSpotPrice * weight) + spotPremium;
          effectivePrice = calculatedPrice;  // Show calculated price, not floor-adjusted

          console.log('Spot price calculation for edit confirmation:', {
            metal,
            weight,
            currentSpotPrice,
            spotPremium,
            floorPrice,
            calculatedPrice,
            effectivePrice,
            note: 'Effective price = spot + premium (floor shown separately)'
          });

          // Store calculated values in data for success modal
          data.currentSpotPrice = currentSpotPrice;
          data.effectivePrice = effectivePrice;
        }
      }
    } catch (error) {
      console.error('Error fetching spot prices:', error);
      // Fall back to floor price if API fails
      effectivePrice = parseFloat(data.floorPrice) || 0;
      data.effectivePrice = effectivePrice;
    }
  }

  // Populate item detail fields
  const metalEl = document.getElementById('edit-confirm-metal');
  const productLineEl = document.getElementById('edit-confirm-product-line');
  const productTypeEl = document.getElementById('edit-confirm-product-type');
  const weightEl = document.getElementById('edit-confirm-weight');
  const yearEl = document.getElementById('edit-confirm-year');
  const mintEl = document.getElementById('edit-confirm-mint');
  const finishEl = document.getElementById('edit-confirm-finish');
  const gradeEl = document.getElementById('edit-confirm-grade');
  const quantityEl = document.getElementById('edit-confirm-quantity');
  const gradingEl = document.getElementById('edit-confirm-grading');
  const photoEl = document.getElementById('edit-confirm-photo');
  const modeEl = document.getElementById('edit-confirm-mode');

  if (metalEl) metalEl.textContent = data.metal || '—';
  if (productLineEl) productLineEl.textContent = data.productLine || '—';
  if (productTypeEl) productTypeEl.textContent = data.productType || '—';
  if (weightEl) weightEl.textContent = data.weight || '—';
  if (yearEl) yearEl.textContent = data.year || '—';
  if (mintEl) mintEl.textContent = data.mint || '—';
  if (finishEl) finishEl.textContent = data.finish || '—';
  if (gradeEl) gradeEl.textContent = data.grade || '—';
  if (quantityEl) quantityEl.textContent = data.quantity || '—';

  if (gradingEl) {
    if (data.graded) {
      gradingEl.textContent = `Yes${data.gradingService ? ` (${data.gradingService})` : ''}`;
    } else {
      gradingEl.textContent = 'No';
    }
  }

  if (modeEl) {
    modeEl.textContent = isVariablePricing ? 'Variable (Premium to Spot)' : 'Fixed Price';
  }

  if (photoEl) {
    photoEl.textContent = data.hasPhoto ? 'Attached' : 'No photo';
  }

  // Handle pricing mode display
  const currentSpotRow = document.getElementById('edit-confirm-current-spot-row');
  const currentSpotEl = document.getElementById('edit-confirm-current-spot');
  const premiumRow = document.getElementById('edit-confirm-premium-row');
  const premiumEl = document.getElementById('edit-confirm-premium');
  const floorRow = document.getElementById('edit-confirm-floor-row');
  const floorEl = document.getElementById('edit-confirm-floor');
  const effectiveRow = document.getElementById('edit-confirm-effective-row');
  const effectiveEl = document.getElementById('edit-confirm-effective');
  const staticPriceRow = document.getElementById('edit-confirm-static-price-row');
  const staticPriceEl = document.getElementById('edit-confirm-static-price');

  console.log('🔍 [Edit Confirm Modal] Display Logic:', {
    isVariablePricing,
    pricingMode,
    currentSpotPrice,
    effectivePrice,
    spotPremium: data.spotPremium,
    floorPrice: data.floorPrice,
    elementsFound: {
      currentSpotRow: !!currentSpotRow,
      currentSpotEl: !!currentSpotEl,
      premiumRow: !!premiumRow,
      premiumEl: !!premiumEl,
      floorRow: !!floorRow,
      floorEl: !!floorEl,
      effectiveRow: !!effectiveRow,
      effectiveEl: !!effectiveEl
    }
  });

  if (isVariablePricing) {
    console.log('✅ [Edit Confirm Modal] Showing variable pricing fields');

    // Show current spot price
    if (currentSpotRow) {
      currentSpotRow.style.display = 'flex';
      console.log('  → currentSpotRow display set to:', currentSpotRow.style.display);
      console.log('  → currentSpotRow COMPUTED display:', window.getComputedStyle(currentSpotRow).display);
    }
    if (currentSpotEl && currentSpotPrice !== null) {
      currentSpotEl.textContent = `$${currentSpotPrice.toFixed(2)}/oz`;
      console.log('  → currentSpotEl text set to:', currentSpotEl.textContent);
    } else if (currentSpotEl) {
      currentSpotEl.textContent = 'Loading...';
    }

    // Show variable pricing fields
    if (premiumRow) {
      premiumRow.style.display = 'flex';
      console.log('  → premiumRow display set to:', premiumRow.style.display);
    }
    if (premiumEl && data.spotPremium !== undefined && data.spotPremium !== '') {
      premiumEl.textContent = `$${parseFloat(data.spotPremium).toFixed(2)}`;
      console.log('  → premiumEl text set to:', premiumEl.textContent);
    } else if (premiumEl) {
      premiumEl.textContent = '$0.00';
    }

    if (floorRow) {
      floorRow.style.display = 'flex';
      console.log('  → floorRow display set to:', floorRow.style.display);
    }
    if (floorEl && data.floorPrice !== undefined && data.floorPrice !== '') {
      floorEl.textContent = `$${parseFloat(data.floorPrice).toFixed(2)}`;
      console.log('  → floorEl text set to:', floorEl.textContent);
    } else if (floorEl) {
      floorEl.textContent = '$0.00';
    }

    if (effectiveRow) {
      effectiveRow.style.display = 'flex';
      console.log('  → effectiveRow display set to:', effectiveRow.style.display);
    }
    if (effectiveEl && effectivePrice !== null && !isNaN(effectivePrice)) {
      effectiveEl.textContent = `$${effectivePrice.toFixed(2)}`;
      console.log('  → effectiveEl text set to:', effectiveEl.textContent);
    } else if (effectiveEl) {
      effectiveEl.textContent = 'Calculating...';
    }

    // Hide static price
    if (staticPriceRow) staticPriceRow.style.display = 'none';
  } else {
    console.log('ℹ️ [Edit Confirm Modal] Showing static pricing fields');

    // Hide variable pricing fields
    if (currentSpotRow) currentSpotRow.style.display = 'none';
    if (premiumRow) premiumRow.style.display = 'none';
    if (floorRow) floorRow.style.display = 'none';
    if (effectiveRow) effectiveRow.style.display = 'none';

    // Show static price
    if (staticPriceRow) staticPriceRow.style.display = '';
    if (staticPriceEl && data.pricePerCoin !== undefined && data.pricePerCoin !== '') {
      staticPriceEl.textContent = `$${parseFloat(data.pricePerCoin).toFixed(2)}`;
    } else if (staticPriceEl) {
      staticPriceEl.textContent = '$0.00';
    }
  }

  // Calculate and display seller proceeds preview
  let grossPrice;
  const quantity = parseInt(data.quantity) || 1;
  if (isVariablePricing && effectivePrice !== null) {
    grossPrice = effectivePrice * quantity;
  } else {
    const pricePerCoin = parseFloat(data.pricePerCoin) || 0;
    grossPrice = pricePerCoin * quantity;
  }

  // Fetch and display proceeds
  fetchAndDisplayEditProceeds('edit-confirm', grossPrice, quantity);

  // Show modal with animation
  modal.style.display = 'flex';

  // Trigger animation on next frame
  requestAnimationFrame(() => {
    modal.classList.add('active');
  });

  // Set up confirm button
  const confirmBtn = document.getElementById('editConfirmBtn');
  if (confirmBtn) {
    // Remove any existing listeners
    const newBtn = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newBtn, confirmBtn);

    // Add new listener
    newBtn.addEventListener('click', () => {
      // Call the submission function
      submitEditListingForm();
    });
  }
}

/**
 * Close edit listing confirmation modal
 */
function closeEditListingConfirmModal() {
  const modal = document.getElementById('editListingConfirmModal');

  if (!modal) return;

  // Add hiding class for fade-out animation
  modal.classList.add('hiding');
  modal.classList.remove('active');

  // Wait for animation to complete before hiding
  setTimeout(() => {
    modal.style.display = 'none';
    modal.classList.remove('hiding');
  }, 300);

  // Clear pending submission data
  window.editListingPendingSubmission = null;
}

/**
 * Submit the edit listing form after confirmation
 */
async function submitEditListingForm() {
  if (!window.editListingPendingSubmission) {
    console.error('No pending edit listing submission found');
    alert('Error: No pending changes to submit');
    return;
  }

  const { listingId, formData, data } = window.editListingPendingSubmission;

  // Close confirmation modal
  closeEditListingConfirmModal();

  // Show loading state (optional - could add a loading modal here)
  console.log('Submitting edit listing form for listing', listingId);

  try {
    const url = `/listings/edit_listing/${listingId}`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      body: formData
    });

    console.log('Response received - Status:', response.status, response.statusText);

    // Handle success
    if (response.ok) {
      console.log('Listing updated successfully!');

      // Parse response data from backend
      const responseData = await response.json();
      console.log('Backend response data:', responseData);

      // Show success modal with fresh data from backend
      openEditListingSuccessModal(responseData);
    } else {
      // Handle error
      const text = await response.text();
      console.error('Server error response:', text);

      try {
        const errData = JSON.parse(text);
        const msg = errData && errData.message ? errData.message : `Save failed with status ${response.status}`;
        throw new Error(msg);
      } catch (parseErr) {
        throw new Error(text || `Save failed with status ${response.status}`);
      }
    }
  } catch (error) {
    console.error('Error submitting edit listing form:', error);
    alert('Error saving listing: ' + (error.message || 'Unknown error'));
  } finally {
    // Clear pending submission
    window.editListingPendingSubmission = null;
  }
}

/* ==========================================================================
   Edit Listing Success Modal
   Shows after successful listing update
   ========================================================================== */

/**
 * Open edit listing success modal with listing details
 * @param {Object} data - Listing data to display
 */
function openEditListingSuccessModal(data) {
  const modal = document.getElementById('editListingSuccessModal');

  if (!modal) {
    console.error('Edit listing success modal not found (#editListingSuccessModal)');
    return;
  }

  console.log('========================================');
  console.log('🎯 SUCCESS MODAL OPENING - FULL DIAGNOSTIC');
  console.log('========================================');
  console.log('openEditListingSuccessModal called with data:', JSON.stringify(data, null, 2));
  console.log('Data keys present:', Object.keys(data));
  console.log('Pricing-related fields in data:', {
    pricingMode: data.pricingMode,
    currentSpotPrice: data.currentSpotPrice,
    effectivePrice: data.effectivePrice,
    spotPremium: data.spotPremium,
    floorPrice: data.floorPrice,
    pricingMetal: data.pricingMetal,
    metal: data.metal,
    weight: data.weight
  });

  // Determine pricing mode
  const pricingMode = data.pricingMode || 'static';
  const isVariablePricing = pricingMode === 'premium_to_spot';

  // Populate item detail fields
  const metalEl = modal.querySelector('#success-metal');
  const productLineEl = modal.querySelector('#success-product-line');
  const productTypeEl = modal.querySelector('#success-product-type');
  const weightEl = modal.querySelector('#success-weight');
  const yearEl = modal.querySelector('#success-year');
  const mintEl = modal.querySelector('#success-mint');
  const finishEl = modal.querySelector('#success-finish');
  const gradeEl = modal.querySelector('#success-grade');
  const quantityEl = modal.querySelector('#success-quantity');
  const gradingEl = modal.querySelector('#success-grading');
  const photoEl = modal.querySelector('#success-photo');
  const pricingModeEl = document.getElementById('edit-success-pricing-mode');

  if (metalEl) metalEl.textContent = data.metal || '—';
  if (productLineEl) productLineEl.textContent = data.productLine || '—';
  if (productTypeEl) productTypeEl.textContent = data.productType || '—';
  if (weightEl) weightEl.textContent = data.weight || '—';
  if (yearEl) yearEl.textContent = data.year || '—';
  if (mintEl) mintEl.textContent = data.mint || '—';
  if (finishEl) finishEl.textContent = data.finish || '—';
  if (gradeEl) gradeEl.textContent = data.grade || '—';
  if (quantityEl) quantityEl.textContent = data.quantity || '—';

  if (gradingEl) {
    if (data.graded) {
      gradingEl.textContent = `Yes${data.gradingService ? ` (${data.gradingService})` : ''}`;
    } else {
      gradingEl.textContent = 'No';
    }
  }

  if (photoEl) {
    photoEl.textContent = data.hasPhoto ? 'Attached' : 'No photo';
  }

  if (pricingModeEl) {
    pricingModeEl.textContent = isVariablePricing ? 'Variable (Premium to Spot)' : 'Fixed Price';
  }

  // Handle pricing display - USE UNIQUE IDs FOR EDIT MODAL
  const currentSpotRow = document.getElementById('edit-success-current-spot-row');
  const currentSpotEl = document.getElementById('edit-success-current-spot');
  const premiumRow = document.getElementById('edit-success-premium-row');
  const premiumEl = document.getElementById('edit-success-premium');
  const floorRow = document.getElementById('edit-success-floor-row');
  const floorEl = document.getElementById('edit-success-floor');
  const effectiveRow = document.getElementById('edit-success-effective-row');
  const effectiveEl = document.getElementById('edit-success-effective');
  const staticPriceRow = document.getElementById('edit-success-static-price-row');
  const staticPriceEl = document.getElementById('edit-success-static-price');

  console.log('🔍 [Edit Success Modal] Display Logic:', {
    isVariablePricing,
    pricingMode,
    currentSpotPrice: data.currentSpotPrice,
    effectivePrice: data.effectivePrice,
    spotPremium: data.spotPremium,
    floorPrice: data.floorPrice,
    elementsFound: {
      currentSpotRow: !!currentSpotRow,
      currentSpotEl: !!currentSpotEl,
      premiumRow: !!premiumRow,
      premiumEl: !!premiumEl,
      floorRow: !!floorRow,
      floorEl: !!floorEl,
      effectiveRow: !!effectiveRow,
      effectiveEl: !!effectiveEl
    }
  });

  if (isVariablePricing) {
    console.log('✅ [Edit Success Modal] Showing variable pricing fields');
    console.log('');

    // Show current spot price
    if (currentSpotRow) {
      console.log('📍 BEFORE setting currentSpotRow display:');
      console.log('  → inline style:', currentSpotRow.style.display);
      console.log('  → computed style:', window.getComputedStyle(currentSpotRow).display);

      currentSpotRow.style.display = 'flex';

      console.log('📍 AFTER setting currentSpotRow.style.display = "flex":');
      console.log('  → inline style:', currentSpotRow.style.display);
      console.log('  → computed style:', window.getComputedStyle(currentSpotRow).display);
      console.log('  → offsetWidth (0 = hidden):', currentSpotRow.offsetWidth);
      console.log('  → offsetHeight (0 = hidden):', currentSpotRow.offsetHeight);
      console.log('');
    } else {
      console.error('❌ currentSpotRow element NOT FOUND!');
    }

    if (currentSpotEl && data.currentSpotPrice !== undefined && !isNaN(data.currentSpotPrice)) {
      currentSpotEl.textContent = `$${parseFloat(data.currentSpotPrice).toFixed(2)}/oz`;
      console.log('  → currentSpotEl text set to:', currentSpotEl.textContent);
    } else if (currentSpotEl) {
      currentSpotEl.textContent = '—';
      console.log('⚠️ currentSpotEl found but data.currentSpotPrice is invalid:', data.currentSpotPrice);
    } else {
      console.error('❌ currentSpotEl element NOT FOUND!');
    }
    console.log('');

    // Show variable pricing fields
    if (premiumRow) {
      premiumRow.style.display = 'flex';
      console.log('  → premiumRow display set to:', premiumRow.style.display);
      console.log('  → premiumRow computed display:', window.getComputedStyle(premiumRow).display);
    }
    if (premiumEl && data.spotPremium !== undefined && data.spotPremium !== '') {
      premiumEl.textContent = `$${parseFloat(data.spotPremium).toFixed(2)}`;
      console.log('  → premiumEl text set to:', premiumEl.textContent);
    } else if (premiumEl) {
      premiumEl.textContent = '$0.00';
    }
    console.log('');

    if (floorRow) {
      floorRow.style.display = 'flex';
      console.log('  → floorRow display set to:', floorRow.style.display);
      console.log('  → floorRow computed display:', window.getComputedStyle(floorRow).display);
    }
    if (floorEl && data.floorPrice !== undefined && data.floorPrice !== '') {
      floorEl.textContent = `$${parseFloat(data.floorPrice).toFixed(2)}`;
      console.log('  → floorEl text set to:', floorEl.textContent);
    } else if (floorEl) {
      floorEl.textContent = '$0.00';
    }
    console.log('');

    if (effectiveRow) {
      effectiveRow.style.display = 'flex';
      console.log('  → effectiveRow display set to:', effectiveRow.style.display);
      console.log('  → effectiveRow computed display:', window.getComputedStyle(effectiveRow).display);
    }
    if (effectiveEl && data.effectivePrice !== undefined && !isNaN(data.effectivePrice)) {
      effectiveEl.textContent = `$${parseFloat(data.effectivePrice).toFixed(2)}`;
      console.log('  → effectiveEl text set to:', effectiveEl.textContent);
    } else if (effectiveEl) {
      effectiveEl.textContent = '—';
      console.log('⚠️ effectiveEl found but data.effectivePrice is invalid:', data.effectivePrice);
    }
    console.log('');
    console.log('========================================');
    console.log('🎯 SUCCESS MODAL DISPLAY LOGIC COMPLETE');
    console.log('========================================');

    // Hide static price
    if (staticPriceRow) staticPriceRow.style.display = 'none';
  } else {
    // Hide variable pricing fields
    if (currentSpotRow) currentSpotRow.style.display = 'none';
    if (premiumRow) premiumRow.style.display = 'none';
    if (floorRow) floorRow.style.display = 'none';
    if (effectiveRow) effectiveRow.style.display = 'none';

    // Show static price
    if (staticPriceRow) staticPriceRow.style.display = '';
    if (staticPriceEl && data.pricePerCoin !== undefined && data.pricePerCoin !== '') {
      staticPriceEl.textContent = `$${parseFloat(data.pricePerCoin).toFixed(2)}`;
    } else if (staticPriceEl) {
      staticPriceEl.textContent = '$0.00';
    }
  }

  // Calculate and display seller proceeds preview
  let grossPrice;
  const quantity = parseInt(data.quantity) || 1;
  if (isVariablePricing && data.effectivePrice !== undefined && !isNaN(data.effectivePrice)) {
    grossPrice = parseFloat(data.effectivePrice) * quantity;
  } else {
    const pricePerCoin = parseFloat(data.pricePerCoin) || 0;
    grossPrice = pricePerCoin * quantity;
  }

  // Fetch and display proceeds for success modal
  fetchAndDisplayEditProceeds('edit-success', grossPrice, quantity);

  // Show modal
  modal.style.display = 'flex';

  // Trigger animation on next frame
  requestAnimationFrame(() => {
    modal.classList.add('active');
  });
}

/**
 * Close edit listing success modal
 */
function closeEditListingSuccessModal() {
  const modal = document.getElementById('editListingSuccessModal');

  if (!modal) return;

  // Add hiding class for fade-out animation
  modal.classList.add('hiding');
  modal.classList.remove('active');

  // Wait for animation to complete before hiding
  setTimeout(() => {
    modal.style.display = 'none';
    modal.classList.remove('hiding');

    // Reload page to show updated listing
    location.reload();
  }, 300);
}

/**
 * Fetch fee preview from API and display proceeds for edit listing modals
 * @param {string} prefix - 'edit-confirm' or 'edit-success' for element IDs
 * @param {number} grossPrice - Total gross price
 * @param {number} quantity - Quantity of items
 */
async function fetchAndDisplayEditProceeds(prefix, grossPrice, quantity) {
  const netEl = document.getElementById(`${prefix}-net-proceeds`);
  const grossEl = document.getElementById(`${prefix}-gross-price`);
  const feePercentEl = document.getElementById(`${prefix}-fee-percent`);
  const feeAmountEl = document.getElementById(`${prefix}-fee-amount`);
  const feeIndicatorRow = document.getElementById(`${prefix}-fee-indicator-row`);
  const feeBadge = document.getElementById(`${prefix}-fee-badge`);

  try {
    // Fetch fee preview from API
    const unitPrice = quantity > 0 ? grossPrice / quantity : grossPrice;
    const response = await fetch(`/api/fee-preview?gross_price=${unitPrice}&quantity=${quantity}`);
    const data = await response.json();

    if (data.success) {
      // Populate proceeds display
      if (netEl) netEl.textContent = `$${data.net_amount.toFixed(2)}`;
      if (grossEl) grossEl.textContent = `$${data.gross_price.toFixed(2)}`;
      if (feePercentEl) feePercentEl.textContent = data.fee_percent ? data.fee_percent.toFixed(1) : '—';
      if (feeAmountEl) feeAmountEl.textContent = `−$${data.fee_amount.toFixed(2)}`;

      // Show fee indicator if non-default
      if (data.fee_indicator && feeIndicatorRow && feeBadge) {
        feeIndicatorRow.style.display = 'flex';
        feeBadge.className = `edit-proceeds-fee-badge fee-${data.fee_indicator}`;
        if (data.fee_indicator === 'reduced') {
          feeBadge.textContent = 'Reduced Fee';
        } else if (data.fee_indicator === 'elevated') {
          feeBadge.textContent = 'Higher Fee';
        } else if (data.fee_indicator === 'custom') {
          feeBadge.textContent = 'Custom Fee';
        }
      } else if (feeIndicatorRow) {
        feeIndicatorRow.style.display = 'none';
      }
    } else {
      // Fallback: calculate with default 2.5% fee
      const defaultFeePercent = 2.5;
      const feeAmount = Math.round(grossPrice * (defaultFeePercent / 100) * 100) / 100;
      const netAmount = grossPrice - feeAmount;

      if (netEl) netEl.textContent = `$${netAmount.toFixed(2)}`;
      if (grossEl) grossEl.textContent = `$${grossPrice.toFixed(2)}`;
      if (feePercentEl) feePercentEl.textContent = defaultFeePercent.toFixed(1);
      if (feeAmountEl) feeAmountEl.textContent = `−$${feeAmount.toFixed(2)}`;
      if (feeIndicatorRow) feeIndicatorRow.style.display = 'none';
    }
  } catch (error) {
    console.error('Error fetching fee preview:', error);
    // Fallback: calculate with default 2.5% fee
    const defaultFeePercent = 2.5;
    const feeAmount = Math.round(grossPrice * (defaultFeePercent / 100) * 100) / 100;
    const netAmount = grossPrice - feeAmount;

    if (netEl) netEl.textContent = `$${netAmount.toFixed(2)}`;
    if (grossEl) grossEl.textContent = `$${grossPrice.toFixed(2)}`;
    if (feePercentEl) feePercentEl.textContent = defaultFeePercent.toFixed(1);
    if (feeAmountEl) feeAmountEl.textContent = `−$${feeAmount.toFixed(2)}`;
    if (feeIndicatorRow) feeIndicatorRow.style.display = 'none';
  }
}

// Global exposure
window.openEditListingConfirmModal = openEditListingConfirmModal;
window.closeEditListingConfirmModal = closeEditListingConfirmModal;
window.submitEditListingForm = submitEditListingForm;
window.openEditListingSuccessModal = openEditListingSuccessModal;
window.closeEditListingSuccessModal = closeEditListingSuccessModal;

// Close on overlay click
window.addEventListener('click', (e) => {
  const confirmModal = document.getElementById('editListingConfirmModal');
  const successModal = document.getElementById('editListingSuccessModal');

  if (e.target === confirmModal) {
    closeEditListingConfirmModal();
  }
  if (e.target === successModal) {
    closeEditListingSuccessModal();
  }
});

// Close on Escape
window.addEventListener('keydown', (e) => {
  const confirmModal = document.getElementById('editListingConfirmModal');
  const successModal = document.getElementById('editListingSuccessModal');

  if (e.key === 'Escape') {
    if (confirmModal && confirmModal.style.display !== 'none') {
      closeEditListingConfirmModal();
    }
    if (successModal && successModal.style.display !== 'none') {
      closeEditListingSuccessModal();
    }
  }
});
